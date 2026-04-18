"""
Trader entry point.

    python main.py                   # uses config/config.yaml
    python main.py --config <path>   # uses alternate config file
"""

import argparse
import os
import sys
import time
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
    valid_watchlist = [s for s in config.watchlist if s in symbol_to_token]
    missing = set(config.watchlist) - set(valid_watchlist)
    if missing:
        logger.warning("Instruments not found on NSE: %s", missing)

    # Build strategies
    strategies = []
    for symbol in valid_watchlist:
        strategies.extend(build_strategies(symbol, config))
    logger.info("Strategies loaded: %d", len(strategies))

    # Order fill callback
    def handle_order_update(update: dict):
        if update.get("status") != "COMPLETE":
            return
        instrument = update["instrument"]
        fill_price = update.get("fill_price") or update.get("price") or 0.0
        quantity = update["quantity"]
        direction = update["direction"]
        strategy = update.get("strategy", "")
        if direction == "BUY":
            risk.on_order_filled(instrument, fill_price, quantity)
        else:
            risk.close_position(instrument)
        portfolio.on_order_filled(instrument, direction, quantity, fill_price)
        telegram.notify_order_filled(instrument, direction, quantity, fill_price,
                                     strategy=strategy, mode=config.env)
        for strat in strategies:
            if strat.instrument == instrument:
                strat.on_order_update(update)

    orders.register_update_callback(handle_order_update)

    # Candle handler
    def handle_candle(candle: dict):
        symbol = next(
            (s for s, t in symbol_to_token.items() if t == candle.get("instrument_token")),
            None,
        )
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

    def post_market():
        portfolio.log_summary()
        positions = [p for p in portfolio._positions.values() if p.quantity != 0]
        telegram.notify_daily_pnl(
            realised=sum(p.realised_pnl for p in positions),
            unrealised=sum(p.unrealised_pnl for p in positions),
            total_trades=len(positions),
            mode=config.env,
            capital=config.total_capital,
        )
        risk.reset_day()

    scheduler.on_pre_market(pre_market)
    scheduler.on_post_market(post_market)

    # Live feed
    tokens = [symbol_to_token[s] for s in valid_watchlist]
    feed = LiveFeed(
        api_key=config.kite_api_key,
        access_token=config.kite_access_token,
        timeframe_minutes=config.candle_minutes,
    )
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
