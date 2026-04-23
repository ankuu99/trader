"""
Trader entry point.

    python main.py                   # uses config/config.yaml
    python main.py --config <path>   # uses alternate config file
"""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta
from datetime import time as dtime
from pathlib import Path

_pre = argparse.ArgumentParser(add_help=False)
_pre.add_argument("--config", default=None)
_pre_args, _ = _pre.parse_known_args()
if _pre_args.config:
    os.environ["TRADER_CONFIG"] = _pre_args.config

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / "config" / ".env")

from trader.auth.session import create_kite
from trader.core.config import config
from trader.core.logger import get_logger, setup
from trader.data.historical import warm_up
from trader.data.live import LiveFeed
from trader.data.store import Store
from trader.notifications import telegram
from trader.orders.manager import OrderManager
from trader.portfolio.tracker import PortfolioTracker
from trader.risk.manager import RiskManager
from trader.scheduler.jobs import Scheduler
from trader.strategies.base import SignalType
from trader.strategies.registry import build_strategies

setup(log_dir=config.log_dir, level=config.log_level)
logger = get_logger(__name__)

_MARKET_OPEN = dtime(9, 15)
_MARKET_CLOSE = dtime(15, 30)
_INTRADAY_TIMEFRAMES = {"5minute", "15minute", "30minute", "60minute"}


def main():
    logger.info(
        "Starting trader | env=%s | timeframe=%s | capital=%.0f",
        config.env, config.candle_timeframe, config.total_capital,
    )

    kite = create_kite()
    store = Store(config.db_path)
    risk = RiskManager()
    orders = OrderManager(kite=kite, store=store, mode=config.env)
    portfolio = PortfolioTracker(kite=kite, mode=config.env)

    # Resolve instrument tokens
    instruments = kite.instruments("NSE")
    symbol_to_token = {
        f"NSE:{i['tradingsymbol']}": i["instrument_token"] for i in instruments
    }
    token_to_symbol = {v: k for k, v in symbol_to_token.items()}
    valid_watchlist = [s for s in config.watchlist if s in symbol_to_token]
    missing = set(config.watchlist) - set(valid_watchlist)
    if missing:
        logger.warning("Instruments not found on NSE: %s", missing)

    # Build strategies
    strategies = []
    for symbol in valid_watchlist:
        strategies.extend(build_strategies(symbol, config))
    logger.info("Strategies loaded: %d", len(strategies))

    # Refresh candle cache before warm-up so strategies train on current data.
    logger.info("Refreshing candle cache before strategy warm-up")
    for symbol in valid_watchlist:
        token = symbol_to_token[symbol]
        warm_up(kite, store, token, symbol, config.candle_timeframe,
                config.historical_cache_days)

    # Warm up strategies from cached historical candles so they don't need
    # 200+ live candles (33+ trading days) before emitting any signal.
    # NOTE: reconciliation must come AFTER warm-up so warm-up candles don't
    # override the reconciled position state (R3-2).
    warmup_from = datetime.now() - timedelta(days=config.historical_cache_days)
    for symbol in valid_watchlist:
        df = store.read_candles(symbol, config.candle_timeframe, warmup_from, datetime.now())
        strats_for_symbol = [s for s in strategies if s.instrument == symbol]
        for _, row in df.iterrows():
            candle = row.to_dict()
            candle["_symbol"] = symbol
            candle["instrument_token"] = symbol_to_token.get(symbol)
            for strat in strats_for_symbol:
                strat.on_candle(candle)  # warm-up only — signals discarded
    logger.info("Strategy warm-up complete")
    for strat in strategies:
        candle_count = len(getattr(strat, "_candles", []))
        trained = getattr(strat, "_trained", None)
        status = "TRAINED" if trained else ("WARMING_UP" if trained is not None else "N/A")
        logger.info(
            "Warm-up status | %s | %s | candles=%d",
            strat.instrument, status, candle_count,
        )

    # Clear any phantom entry state left by warm-up signal triggers that never
    # received a fill callback (position=None but _entry_price set).
    for strat in strategies:
        if getattr(strat, "_entry_price", None) is not None and strat.position is None:
            logger.info("Clearing phantom warm-up entry state | %s", strat.instrument)
            strat._entry_price = None
            if hasattr(strat, "_held_bars"):
                strat._held_bars = 0

    # Reconcile state from broker after warm-up — overrides any position state
    # set during warm-up with the actual broker reality.
    if config.env == "live":
        kite_pos = kite.positions()
        risk.seed_from_kite(kite_pos)
        open_instruments = {
            f"NSE:{p['tradingsymbol']}" for p in kite_pos.get("net", []) if p["quantity"] > 0
        }
        for p in kite_pos.get("net", []):
            if p["quantity"] <= 0:
                continue
            instrument = f"NSE:{p['tradingsymbol']}"
            synthetic_fill = {
                "status": "COMPLETE",
                "signal_type": SignalType.ENTRY,
                "direction": "BUY",
                "price": float(p["average_price"]),
                "instrument": instrument,
            }
            for strat in strategies:
                if strat.instrument == instrument:
                    strat.on_order_update(synthetic_fill)
        # Clear residual phantom state for instruments not held in Kite
        for strat in strategies:
            if strat.instrument not in open_instruments:
                strat._entry_price = None
                strat.position = None

    # Order fill callback
    def handle_order_update(update: dict):
        status = update.get("status")
        instrument = update["instrument"]
        direction = update.get("direction", "")

        if status in ("REJECTED", "CANCELLED"):
            telegram.notify_order_rejected(
                instrument, direction,
                update.get("status_message", status), config.env,
            )
            for strat in strategies:
                if strat.instrument == instrument:
                    strat.on_order_update(update)
            return

        if status != "COMPLETE":
            return

        fill_price = update.get("fill_price") or update.get("price") or 0.0
        quantity = update["quantity"]
        strategy = update.get("strategy", "")
        if direction == "BUY":
            risk.on_order_filled(instrument, fill_price, quantity)
        else:
            risk.close_position(instrument, fill_price)
        portfolio.on_order_filled(instrument, direction, quantity, fill_price)
        telegram.notify_order_filled(instrument, direction, quantity, fill_price,
                                     strategy=strategy, mode=config.env)
        for strat in strategies:
            if strat.instrument == instrument:
                strat.on_order_update(update)

    orders.register_update_callback(handle_order_update)

    # Candle handler
    def handle_candle(candle: dict):
        symbol = token_to_symbol.get(candle.get("instrument_token"))
        candle["_symbol"] = symbol
        orders.on_candle(candle)

        if config.candle_timeframe in _INTRADAY_TIMEFRAMES:
            ts = candle.get("timestamp")
            candle_time = ts.time() if ts is not None else None
            if candle_time is None or not (_MARKET_OPEN <= candle_time <= _MARKET_CLOSE):
                return

        for strategy in strategies:
            if strategy.instrument != symbol:
                continue
            signal = strategy.on_candle(candle)
            if signal is None:
                continue
            order = risk.validate(signal)
            if order is None:
                continue
            orders.place(order)

    # Scheduler
    scheduler = Scheduler()

    def pre_market():
        logger.info("Pre-market: warming up candle cache")
        for symbol in valid_watchlist:
            token = symbol_to_token[symbol]
            warm_up(kite, store, token, symbol, config.candle_timeframe,
                    config.historical_cache_days)
        feed.reconnect()  # no-op on first startup; resumes after market-close disconnect

    def post_market():
        portfolio.refresh()  # fetch live P&L from Kite before summarising
        # Evict phantom positions from risk tracker that were closed by GTT
        # but whose order updates were never received (known edge case).
        if config.env == "live":
            try:
                kite_pos = kite.positions()
                live_instruments = {
                    f"NSE:{p['tradingsymbol']}" for p in kite_pos.get("net", [])
                    if p["quantity"] > 0
                }
                stale = set(risk._open_positions.keys()) - live_instruments
                for inst in stale:
                    logger.warning("Removing stale position from risk tracker | %s", inst)
                    risk.close_position(inst, 0.0)
            except Exception as e:
                logger.error("Failed to reconcile positions in post_market: %s", e)
        portfolio.log_summary()
        positions = list(portfolio._positions.values())
        telegram.notify_daily_pnl(
            realised=sum(p.realised_pnl for p in positions),
            unrealised=sum(p.unrealised_pnl for p in positions),
            total_trades=len(positions),
            mode=config.env,
            capital=config.total_capital,
        )
        risk.reset_day()
        orders.clear_pending()
        feed.disconnect()

    scheduler.on_pre_market(pre_market)
    scheduler.on_post_market(post_market)

    # Live feed
    tokens = [symbol_to_token[s] for s in valid_watchlist]
    feed = LiveFeed(
        api_key=config.kite_api_key,
        access_token=config.kite_access_token,
        timeframe_minutes=config.candle_minutes,
    )
    scheduler.on_market_close(feed.flush_partials)
    feed.subscribe(tokens)
    feed.register_candle_handler(handle_candle)
    feed.register_tick_handler(lambda _tick: None)
    if config.env == "live":
        feed.register_order_update_handler(orders.on_kite_order_update)

    scheduler.start()
    pre_market()
    feed.start(threaded=True)

    logger.info(
        "System ready | mode=%s | instruments=%s | strategies=%d",
        config.env, valid_watchlist, len(strategies),
    )
    telegram.notify_startup(config.env, valid_watchlist, len(strategies))

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        feed.stop()
        scheduler.stop()
        logger.info("Trader stopped")


if __name__ == "__main__":
    main()
