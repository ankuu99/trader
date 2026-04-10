"""
Interday (positional / swing) trading entry point.

Differences from main.py:
  - Product type: CNC (delivery — holds overnight)
  - Candle timeframe: daily (390-minute bucket)
  - No square-off job — positions hold until strategy signals exit
  - Post-market resets daily P&L only; open positions are preserved
  - Uses EMA crossover strategy on daily candles
  - Separate SQLite DB (data/market_interday.db)
"""

import os

# Must be set before any trader module is imported — selects the interday config
os.environ["TRADER_CONFIG"] = "config/config_interday.yaml"

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
from trader.strategies.adx import ADXFilter
from trader.strategies.base import SignalType
from trader.strategies.breakout import BreakoutStrategy
from trader.strategies.ema_crossover import EMACrossoverStrategy
from trader.strategies.group import StrategyGroup
from trader.strategies.rsi_ema import RSIEMAStrategy

setup(log_dir=config.log_dir, level=config.log_level)
logger = get_logger(__name__)


def main():
    logger.info("Starting interday trader | env=%s | product=%s", config.env, config.product)
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
    # Strategies — daily candles                                         #
    # ------------------------------------------------------------------ #
    strategies = []
    for symbol in valid_watchlist:
        ema_cfg = config.strategy_config("ema_crossover")
        rsi_ema_cfg = config.strategy_config("rsi_ema")
        breakout_cfg = config.strategy_config("breakout")
        adx_cfg = config.strategy_config("adx")

        if ema_cfg.get("enabled"):
            strategies.append(EMACrossoverStrategy(symbol, ema_cfg))
        if rsi_ema_cfg.get("enabled"):
            strategies.append(RSIEMAStrategy(symbol, rsi_ema_cfg))
        if breakout_cfg.get("enabled"):
            strategies.append(BreakoutStrategy(symbol, breakout_cfg))

        # EMA crossover confirmed by ADX trend strength
        if config.strategy_config("ema_adx").get("enabled"):
            strategies.append(StrategyGroup(
                primary=EMACrossoverStrategy(symbol, ema_cfg),
                filters=[ADXFilter(symbol, adx_cfg)],
            ))

    # ------------------------------------------------------------------ #
    # Signal → risk → order pipeline                                      #
    # ------------------------------------------------------------------ #
    def handle_candle(candle: dict):
        symbol = next(
            (s for s, t in symbol_to_token.items() if t == candle.get("instrument_token")),
            None,
        )
        candle["_symbol"] = symbol

        orders.on_candle(candle)
        portfolio.refresh()

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

        from trader.strategies.base import Direction
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
    # Scheduler — pre/post market only; no square-off                    #
    # ------------------------------------------------------------------ #
    scheduler = Scheduler()

    def pre_market():
        logger.info("Pre-market: warming up 1-year daily candle cache")
        for symbol in valid_watchlist:
            token = symbol_to_token[symbol]
            warm_up(kite, store, token, symbol, "day",
                    lookback_days=config.historical_cache_days)

    def post_market():
        """Refresh portfolio and log P&L. Positions are NOT reset — they carry forward."""
        portfolio.log_summary()
        snapshot = portfolio.snapshot()
        telegram.notify_daily_pnl(
            realised=snapshot.total_realised_pnl,
            unrealised=snapshot.total_unrealised_pnl,
            total_trades=len(snapshot.positions),
            mode=config.env,
            capital=config.total_capital,
        )
        # Reset daily P&L counter only — open positions persist overnight
        risk.reset_day()
        logger.info("Post-market update complete (positions held)")

    scheduler.on_pre_market(pre_market)
    scheduler.on_post_market(post_market)
    # Note: no on_square_off — interday positions hold overnight

    # ------------------------------------------------------------------ #
    # Live feed — 390-minute candles (one per trading day)               #
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
        "Interday system ready | mode=%s | instruments=%s | strategies=%d",
        config.env, valid_watchlist, len(strategies),
    )
    telegram.notify_startup(config.env, valid_watchlist, len(strategies))

    pre_market()

    feed.start(threaded=True)

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
        logger.info("Interday trader stopped cleanly")


if __name__ == "__main__":
    main()
