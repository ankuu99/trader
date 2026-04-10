from datetime import time as dtime

from trader.auth.session import create_kite
from trader.core.config import config
from trader.core.logger import get_logger, setup
from trader.data.historical import warm_up
from trader.data.live import LiveFeed
from trader.data.store import Store
from trader.notifications import telegram
from trader.orders.manager import OrderManager
from trader.portfolio.tracker import PortfolioTracker
from trader.risk.manager import RiskManager, should_square_off
from trader.scheduler.jobs import Scheduler
from trader.strategies.base import SignalType
from trader.strategies.bollinger import BollingerBandStrategy
from trader.strategies.ema_pullback import EMAPullbackStrategy
from trader.strategies.group import StrategyGroup
from trader.strategies.orb import ORBStrategy
from trader.strategies.rsi import RSIStrategy

from trader.strategies.supertrend import SupertrendStrategy
from trader.strategies.vwap import VWAPReversionStrategy

setup(log_dir=config.log_dir, level=config.log_level)
logger = get_logger(__name__)


def main():
    logger.info("Starting trader | env=%s", config.env)
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
        rsi_cfg = config.strategy_config("rsi")
        orb_cfg = config.strategy_config("orb")
        vwap_cfg = config.strategy_config("vwap")
        st_cfg = config.strategy_config("supertrend")
        bb_cfg = config.strategy_config("bollinger")
        ep_cfg = config.strategy_config("ema_pullback")

        if rsi_cfg.get("enabled"):
            strategies.append(RSIStrategy(symbol, rsi_cfg))
        if orb_cfg.get("enabled"):
            strategies.append(ORBStrategy(symbol, orb_cfg))
        if vwap_cfg.get("enabled"):
            strategies.append(VWAPReversionStrategy(symbol, vwap_cfg))
        if st_cfg.get("enabled"):
            strategies.append(SupertrendStrategy(symbol, st_cfg))
        if bb_cfg.get("enabled"):
            strategies.append(BollingerBandStrategy(symbol, bb_cfg))
        if ep_cfg.get("enabled"):
            strategies.append(EMAPullbackStrategy(symbol, ep_cfg))

        # Strategy groups (signal combination)
        if config.strategy_config("orb_supertrend").get("enabled"):
            strategies.append(StrategyGroup(
                primary=ORBStrategy(symbol, orb_cfg),
                filters=[SupertrendStrategy(symbol, st_cfg)],
            ))
        if config.strategy_config("rsi_bollinger").get("enabled"):
            strategies.append(StrategyGroup(
                primary=RSIStrategy(symbol, rsi_cfg),
                filters=[BollingerBandStrategy(symbol, bb_cfg)],
            ))

    # ------------------------------------------------------------------ #
    # Signal → risk → order pipeline                                      #
    # ------------------------------------------------------------------ #
    _MARKET_OPEN  = dtime(9, 15)
    _MARKET_CLOSE = dtime(15, 25)   # last candle that can generate a new entry

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

        # Gate: no new strategy signals outside market hours
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

        from trader.strategies.base import Direction
        risk.on_order_filled(
            instrument, Direction(direction), qty, fill_price, SignalType(signal_type)
        )
        portfolio.on_order_filled(instrument, direction, qty, fill_price, signal_type)

        # Notify the relevant strategy
        for strategy in strategies:
            if strategy.instrument == instrument:
                strategy.on_order_update(update)

        telegram.notify_order_filled(
            instrument, direction, qty, fill_price,
            strategy=update.get("strategy", ""),
            mode=config.env,
        )

        # Check if halt was triggered after this fill
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

    def pre_market():
        logger.info("Pre-market: warming up data cache")
        for symbol in valid_watchlist:
            token = symbol_to_token[symbol]
            for timeframe in ("5minute", "day"):
                warm_up(kite, store, token, symbol, timeframe,
                        lookback_days=config.historical_cache_days)

    def on_square_off():
        logger.info("Square-off time reached — exiting all positions")
        sq_orders = risk.square_off_all()
        for sq_order in sq_orders:
            orders.place(sq_order)

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
        risk.reset_positions()
        logger.info("Post-market teardown complete")

    scheduler.on_pre_market(pre_market)
    scheduler.on_square_off(on_square_off)
    scheduler.on_post_market(post_market)

    # ------------------------------------------------------------------ #
    # Live feed                                                            #
    # ------------------------------------------------------------------ #
    tokens = [symbol_to_token[s] for s in valid_watchlist]
    feed = LiveFeed(
        api_key=config.kite_api_key,
        access_token=config.kite_access_token,
        timeframe_minutes=5,
    )
    feed.subscribe(tokens)
    feed.register_candle_handler(handle_candle)
    feed.register_tick_handler(lambda tick: None)  # placeholder for tick-level use

    scheduler.start()

    logger.info(
        "System ready | mode=%s | instruments=%s | strategies=%d",
        config.env, valid_watchlist, len(strategies),
    )
    telegram.notify_startup(config.env, valid_watchlist, len(strategies))

    # Warm up immediately on startup (in addition to scheduled pre-market)
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
