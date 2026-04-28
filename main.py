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

    # Restore paper positions from SQLite so exits fire correctly after restart.
    if config.env == "paper":
        open_paper = store.read_open_positions()
        lr_cfg = config.strategy_config("lr_extrema")
        restored = []
        for pos in open_paper:
            instrument = pos["instrument"]
            strats_for_instrument = [s for s in strategies if s.instrument == instrument]
            if not strats_for_instrument:
                logger.warning("Paper position in DB has no matching strategy | %s — skipping", instrument)
                continue

            # Compute held_bars from candle history and sweep for missed exits.
            # held_bars is inferred by counting candles since entry_time — no
            # per-candle DB write needed. All post-entry candles are checked:
            # if an exit condition was met while the system was live it would
            # have already fired and deleted the position from DB, so any
            # position still in DB means those candles were safe.
            entry_time_dt = datetime.fromisoformat(pos["entry_time"])
            post_df = store.read_candles(instrument, config.candle_timeframe, entry_time_dt, datetime.now())
            stop_price   = round(pos["entry_price"] * (1 - lr_cfg.get("stop_pct",   3.0) / 100), 2)
            target_price = round(pos["entry_price"] * (1 + lr_cfg.get("profit_pct", 3.0) / 100), 2)
            hold_bars_limit = lr_cfg.get("hold_bars", 150)
            held = 0
            missed_exit: tuple | None = None
            for _, row in post_df.iterrows():
                held += 1
                if float(row["low"]) <= stop_price:
                    missed_exit = ("SL", stop_price)
                    break
                elif float(row["high"]) >= target_price:
                    missed_exit = ("TARGET", target_price)
                    break
                elif held >= hold_bars_limit:
                    missed_exit = ("HOLD_BARS", float(row["close"]))
                    break

            if missed_exit:
                reason, exit_price = missed_exit
                logger.warning(
                    "Catch-up exit | %s | reason=%s exit_price=%.2f | missed during downtime — removing position",
                    instrument, reason, exit_price,
                )
                store.delete_open_position(instrument)
                continue

            synthetic_fill = {
                "status": "COMPLETE",
                "signal_type": SignalType.ENTRY,
                "direction": "BUY",
                "price": pos["entry_price"],
                "instrument": instrument,
                "quantity": pos["quantity"],
                "_held_bars": held,  # includes any catch-up bars counted above
            }
            for strat in strats_for_instrument:
                strat.on_order_update(synthetic_fill)
            risk.on_order_filled(instrument, pos["entry_price"], pos["quantity"])
            restored.append(pos)
            logger.info(
                "Paper position restored | %s | entry=%.2f qty=%d held_bars=%d",
                instrument, pos["entry_price"], pos["quantity"], held,
            )
        if restored:
            telegram.notify_positions_restored(restored)

    # Reconcile state from broker after warm-up — overrides any position state
    # set during warm-up with the actual broker reality.
    # R6-1: seed from bot's own DB (open_positions table) not kite.positions() which
    #        only returns today's traded positions and misses multi-day CNC holds.
    # R6-2: seed today's realised P&L from kite.positions() so daily loss limit is
    #        correctly enforced even if GTT fired while the system was down.
    if config.env == "live":
        # R6-2: seed realised P&L for today from Kite (covers GTT exits while down)
        kite_pos = kite.positions()
        today_realised = sum(
            float(p.get("realised", 0.0)) for p in kite_pos.get("net", [])
        )
        risk.seed_realised_pnl(today_realised)

        # R6-1: seed open positions from DB (bot-placed only) verified against Kite.
        # CNC positions go through 3 states on Kite:
        #   T+0 (trade day)      : appear in kite.positions()["net"] with qty > 0
        #   T+1 (next day, pre-settlement) : kite.holdings() with t1_quantity > 0, quantity = 0
        #   T+1+ (after settlement): kite.holdings() with quantity > 0
        # We must check all three sources before concluding a position was closed externally.
        db_positions = store.read_open_positions()
        kite_holdings = {h["tradingsymbol"]: h for h in kite.holdings()}
        kite_net_positions = {
            p["tradingsymbol"]: p
            for p in kite_pos.get("net", [])
            if int(p.get("quantity", 0)) > 0
        }
        open_instruments = set()

        for pos in db_positions:
            instrument = pos["instrument"]
            symbol = instrument.split(":")[-1]
            holding = kite_holdings.get(symbol)
            net_pos = kite_net_positions.get(symbol)

            held_qty = int(holding.get("quantity", 0)) if holding else 0
            t1_qty = int(holding.get("t1_quantity", 0)) if holding else 0
            pos_qty = int(net_pos.get("quantity", 0)) if net_pos else 0

            if held_qty <= 0 and t1_qty <= 0 and pos_qty <= 0:
                # Position closed externally (GTT or manual) while bot was down
                logger.warning(
                    "Position %s in DB but not in holdings or positions — closed externally, removing from DB",
                    instrument,
                )
                store.delete_open_position(instrument)
                continue

            qty = pos["quantity"]
            avg = pos["entry_price"]
            risk.seed_position(instrument, qty, avg)
            open_instruments.add(instrument)

            entry_time_str = pos.get("entry_time")
            if entry_time_str:
                entry_time_dt = datetime.fromisoformat(entry_time_str)
                post_df = store.read_candles(instrument, config.candle_timeframe, entry_time_dt, datetime.now())
                held_bars = len(post_df)
            else:
                held_bars = 0

            synthetic_fill = {
                "status": "COMPLETE",
                "signal_type": SignalType.ENTRY,
                "direction": "BUY",
                "price": avg,
                "instrument": instrument,
                "_held_bars": held_bars,
            }
            for strat in strategies:
                if strat.instrument == instrument:
                    strat.on_order_update(synthetic_fill)
            logger.info(
                "Live position restored | %s x%d @ %.2f | held_bars=%d",
                instrument, qty, avg, held_bars,
            )

        # Clear residual phantom state for instruments not in DB positions
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
            risk.on_order_cancelled(instrument)
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
            if config.env in ("paper", "live"):
                store.upsert_open_position(instrument, fill_price, quantity, 0, datetime.now())
        else:
            risk.close_position(instrument, fill_price)
            if config.env in ("paper", "live"):
                store.delete_open_position(instrument)
        portfolio.on_order_filled(instrument, direction, quantity, fill_price)
        telegram.notify_order_filled(instrument, direction, quantity, fill_price,
                                     strategy=strategy, mode=config.env,
                                     stop_loss=update.get("trigger_price") or None,
                                     target_price=update.get("target_price") or None)
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

        logger.info(
            "Candle | %s | O=%.2f H=%.2f L=%.2f C=%.2f V=%d | %s",
            symbol,
            candle["open"], candle["high"], candle["low"], candle["close"],
            candle.get("volume", 0), candle.get("timestamp"),
        )

        for strategy in strategies:
            if strategy.instrument != symbol:
                continue
            signal = strategy.on_candle(candle)
            if signal is None:
                logger.debug(
                    "No signal | %s | held_bars=%d entry=%.2f",
                    symbol,
                    getattr(strategy, "_held_bars", 0),
                    getattr(strategy, "_entry_price", 0) or 0,
                )
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

    def heartbeat():
        open_pos = list(risk._open_positions.keys())
        logger.info(
            "Heartbeat | mode=%s | open_positions=%d %s | capital_available=%.0f",
            config.env, len(open_pos), open_pos, risk.capital_available,
        )

    scheduler.on_pre_market(pre_market)
    scheduler.on_post_market(post_market)
    scheduler.on_heartbeat(heartbeat)

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
