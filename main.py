"""
Unified trading entry point — intraday and interday both run from here.
All behaviour is driven by the active config file.

    python main.py                                         # intraday (MIS, 5-min candles)
    python main.py --config config/config_interday.yaml   # interday (CNC, daily candles)

Config controls:
    product          : MIS → market hours gate + square-off + daily position reset
                       CNC → no gate, no square-off, positions persist overnight
    candle_minutes   : LiveFeed bucket size (5 for intraday, 390 for daily)
    square_off_enabled: whether to register the square-off scheduler job
"""

import argparse
import os
import sys
from datetime import time as dtime
from pathlib import Path

# Parse --config early so TRADER_CONFIG is set before trader modules are imported
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
from trader.strategies.base import Direction, SignalType
from trader.strategies.registry import build_strategies

setup(log_dir=config.log_dir, level=config.log_level)
logger = get_logger(__name__)

_MARKET_OPEN  = dtime(9, 15)
_MARKET_CLOSE = dtime(15, 25)   # last candle that can generate a new entry


def main():
    logger.info("Starting trader | env=%s | product=%s", config.env, config.product)
    logger.info(
        "Capital: %.0f | Max risk/trade: %.0f | Daily loss limit: %.0f",
        config.total_capital,
        config.max_risk_per_trade,
        config.daily_loss_limit,
    )

    # ------------------------------------------------------------------ #
    # Core components                                                      #
    # ------------------------------------------------------------------ #
    kite = create_kite()
    store = Store(config.db_path)
    risk = RiskManager()
    orders = OrderManager(kite=kite, store=store, mode=config.env)
    portfolio = PortfolioTracker(kite=kite, mode=config.env)

    # ------------------------------------------------------------------ #
    # Instrument token lookup                                              #
    # ------------------------------------------------------------------ #
    instruments = kite.instruments("NSE")
    symbol_to_token = {
        f"NSE:{i['tradingsymbol']}": i["instrument_token"] for i in instruments
    }
    valid_watchlist = [s for s in config.watchlist if s in symbol_to_token]
    missing = set(config.watchlist) - set(valid_watchlist)
    if missing:
        logger.warning("Instruments not found on NSE: %s", missing)

    # ------------------------------------------------------------------ #
    # Strategies — one instance per instrument per strategy type          #
    # ------------------------------------------------------------------ #
    strategies = []
    for symbol in valid_watchlist:
        strategies.extend(build_strategies(symbol, config))

    # ------------------------------------------------------------------ #
    # Signal → risk → order pipeline                                      #
    # ------------------------------------------------------------------ #
    def handle_candle(candle: dict):
        # Resolve symbol first — needed for instrument-specific paper fills
        symbol = next(
            (s for s, t in symbol_to_token.items() if t == candle.get("instrument_token")),
            None,
        )
        candle["_symbol"] = symbol  # injected for order manager

        # Always fill pending paper orders (candle arrived regardless of time)
        orders.on_candle(candle)
        portfolio.refresh()

        # Gate: no new strategy signals outside market hours (intraday only)
        if config.product == "MIS":
            ts = candle.get("timestamp")
            candle_time = ts.time() if ts is not None else None
            if candle_time is None or not (_MARKET_OPEN <= candle_time <= _MARKET_CLOSE):
                return

        # Run all strategies for this instrument's candle
        for strategy in strategies:
            if strategy.instrument != symbol:
                continue
            signal = strategy.on_candle(candle)
            if signal is None:
                continue
            order = risk.validate(signal)
            if order is None:
                continue
            order_id = orders.place(order)
            logger.info("Order placed | id=%s | strategy=%s", order_id, signal.strategy)

    def handle_order_update(update: dict):
        status = update.get("status")
        instrument = update["instrument"]
        direction = update["direction"]
        qty = update["quantity"]
        fill_price = update.get("fill_price") or update.get("price") or 0.0
        signal_type = update.get("signal_type", SignalType.ENTRY.value)

        if status == "REJECTED":
            telegram.notify_order_rejected(
                instrument, direction,
                reason=update.get("status_message", "unknown"),
                mode=config.env,
            )
            return

        if status != "COMPLETE":
            return

        risk.on_order_filled(
            instrument, Direction(direction), qty, fill_price, SignalType(signal_type)
        )
        portfolio.on_order_filled(instrument, direction, qty, fill_price, signal_type)

        for strategy in strategies:
            if strategy.instrument == instrument:
                strategy.on_order_update(update)

        telegram.notify_order_filled(
            instrument, direction, qty, fill_price,
            strategy=update.get("strategy", ""),
            mode=config.env,
        )

        if risk.is_halted():
            telegram.notify_halt(
                daily_pnl=risk.realised_pnl(),
                limit=config.daily_loss_limit,
                mode=config.env,
            )

    orders.register_update_callback(handle_order_update)

    # ------------------------------------------------------------------ #
    # Scheduler                                                            #
    # ------------------------------------------------------------------ #
    scheduler = Scheduler()

    # Warm up the timeframes needed by the active strategies
    warmup_timeframes = ["5minute", "day"] if config.candle_minutes < 390 else ["day"]

    def pre_market():
        logger.info("Pre-market: warming up candle cache %s", warmup_timeframes)
        for symbol in valid_watchlist:
            token = symbol_to_token[symbol]
            for tf in warmup_timeframes:
                warm_up(kite, store, token, symbol, tf,
                        lookback_days=config.historical_cache_days)

    def post_market():
        portfolio.log_summary()
        snapshot = portfolio.snapshot()
        telegram.notify_daily_pnl(
            realised=snapshot.total_realised_pnl,
            unrealised=snapshot.total_unrealised_pnl,
            total_trades=len(snapshot.positions),
            mode=config.env,
            capital=config.total_capital,
        )
        risk.reset_day()
        if config.product == "MIS":
            risk.reset_positions()
            logger.info("Post-market teardown complete")
        else:
            logger.info("Post-market update complete (positions held)")

    scheduler.on_pre_market(pre_market)
    scheduler.on_post_market(post_market)

    if config.square_off_enabled:
        def on_square_off():
            logger.info("Square-off time reached — exiting all positions")
            sq_orders = risk.square_off_all()
            for sq_order in sq_orders:
                orders.place(sq_order)
        scheduler.on_square_off(on_square_off)

    # ------------------------------------------------------------------ #
    # Live feed                                                            #
    # ------------------------------------------------------------------ #
    tokens = [symbol_to_token[s] for s in valid_watchlist]
    feed = LiveFeed(
        api_key=config.kite_api_key,
        access_token=config.kite_access_token,
        timeframe_minutes=config.candle_minutes,
    )
    feed.subscribe(tokens)
    feed.register_candle_handler(handle_candle)
    feed.register_tick_handler(lambda _tick: None)

    scheduler.start()

    logger.info(
        "System ready | mode=%s | product=%s | instruments=%s | strategies=%d",
        config.env, config.product, valid_watchlist, len(strategies),
    )
    telegram.notify_startup(config.env, valid_watchlist, len(strategies))

    pre_market()

    feed.start(threaded=True)  # non-blocking so we can catch KeyboardInterrupt

    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutdown requested (Ctrl+C)")
    finally:
        logger.info("Stopping feed and scheduler...")
        feed.stop()
        scheduler.stop()
        logger.info("Trader stopped cleanly")


if __name__ == "__main__":
    main()
