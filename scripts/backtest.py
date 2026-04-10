"""
Run backtests for all configured strategies and instruments.

    python scripts/backtest.py [--config config/config_interday.yaml] \
                               [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--save]

Defaults to the last 90 days. Results are printed to stdout.
Pass --save to also write per-strategy CSV trade logs to backtest_results/.
Pass --config to use a different config file (e.g. interday).
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Parse --config early so TRADER_CONFIG is set before trader modules are imported
_pre = argparse.ArgumentParser(add_help=False)
_pre.add_argument("--config", default=None)
_pre_args, _ = _pre.parse_known_args()
if _pre_args.config:
    os.environ["TRADER_CONFIG"] = _pre_args.config

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")

from trader.auth.session import create_kite
from trader.backtest.engine import Backtest
from trader.core.config import config
from trader.core.logger import setup, get_logger
from trader.data.historical import warm_up
from trader.data.store import Store
from trader.strategies.orb import ORBStrategy
from trader.strategies.rsi import RSIStrategy

setup(log_dir=config.log_dir, level="WARNING")  # suppress info noise during backtest
logger = get_logger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Run backtests")
    parser.add_argument("--config", default=None,
                        help="Path to config file (default: config/config.yaml)")
    parser.add_argument("--from", dest="from_dt", default=None,
                        help="Start date YYYY-MM-DD (default: 90 days ago)")
    parser.add_argument("--to", dest="to_dt", default=None,
                        help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--save", action="store_true",
                        help="Save trade logs to backtest_results/")
    return parser.parse_args()


def _build_strategies(symbol: str):
    """Instantiate enabled strategies for a symbol based on active config."""
    from trader.strategies.adx import ADXFilter
    from trader.strategies.bollinger import BollingerBandStrategy
    from trader.strategies.breakout import BreakoutStrategy
    from trader.strategies.ema_crossover import EMACrossoverStrategy
    from trader.strategies.ema_pullback import EMAPullbackStrategy
    from trader.strategies.group import StrategyGroup
    from trader.strategies.rsi_ema import RSIEMAStrategy
    from trader.strategies.supertrend import SupertrendStrategy
    from trader.strategies.vwap import VWAPReversionStrategy

    strategies = []

    # Intraday
    rsi_cfg = config.strategy_config("rsi")
    if rsi_cfg.get("enabled"):
        strategies.append(RSIStrategy(symbol, rsi_cfg))

    orb_cfg = config.strategy_config("orb")
    if orb_cfg.get("enabled"):
        strategies.append(ORBStrategy(symbol, orb_cfg))

    vwap_cfg = config.strategy_config("vwap")
    if vwap_cfg.get("enabled"):
        strategies.append(VWAPReversionStrategy(symbol, vwap_cfg))

    st_cfg = config.strategy_config("supertrend")
    if st_cfg.get("enabled"):
        strategies.append(SupertrendStrategy(symbol, st_cfg))

    bb_cfg = config.strategy_config("bollinger")
    if bb_cfg.get("enabled"):
        strategies.append(BollingerBandStrategy(symbol, bb_cfg))

    ep_cfg = config.strategy_config("ema_pullback")
    if ep_cfg.get("enabled"):
        strategies.append(EMAPullbackStrategy(symbol, ep_cfg))

    # Intraday groups
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

    # Interday
    ema_cfg = config.strategy_config("ema_crossover")
    if ema_cfg.get("enabled"):
        strategies.append(EMACrossoverStrategy(symbol, ema_cfg))

    rsi_ema_cfg = config.strategy_config("rsi_ema")
    if rsi_ema_cfg.get("enabled"):
        strategies.append(RSIEMAStrategy(symbol, rsi_ema_cfg))

    breakout_cfg = config.strategy_config("breakout")
    if breakout_cfg.get("enabled"):
        strategies.append(BreakoutStrategy(symbol, breakout_cfg))

    adx_cfg = config.strategy_config("adx")
    if config.strategy_config("ema_adx").get("enabled"):
        strategies.append(StrategyGroup(
            primary=EMACrossoverStrategy(symbol, ema_cfg),
            filters=[ADXFilter(symbol, adx_cfg)],
        ))

    return strategies


def main():
    args = parse_args()

    to_dt = datetime.strptime(args.to_dt, "%Y-%m-%d") if args.to_dt else datetime.now()
    from_dt = (datetime.strptime(args.from_dt, "%Y-%m-%d") if args.from_dt
               else to_dt - timedelta(days=config.historical_cache_days))
    to_dt = to_dt.replace(hour=23, minute=59, second=59)

    # Interday uses daily candles; intraday uses 5-minute candles
    timeframe = "day" if config.product == "CNC" else "5minute"
    reset_daily = config.product != "CNC"

    print(f"\nBacktest period: {from_dt.date()} → {to_dt.date()}")
    print(f"Instruments    : {', '.join(config.watchlist)}")
    print(f"Capital        : ₹{config.total_capital:,.0f}")
    print(f"Mode           : {'interday (CNC/daily)' if not reset_daily else 'intraday (MIS/5min)'}\n")

    kite = create_kite()
    store = Store(config.db_path)

    # Resolve instrument tokens
    instruments = kite.instruments("NSE")
    symbol_to_token = {
        f"NSE:{i['tradingsymbol']}": i["instrument_token"] for i in instruments
    }

    if args.save:
        out_dir = Path("backtest_results")
        out_dir.mkdir(exist_ok=True)

    all_reports = []

    for symbol in config.watchlist:
        token = symbol_to_token.get(symbol)
        if token is None:
            print(f"  ⚠ {symbol} not found on NSE — skipping")
            continue

        print(f"Fetching historical data for {symbol}...")
        warm_up(kite, store, token, symbol, timeframe,
                lookback_days=(to_dt - from_dt).days + 5)

        for strategy in _build_strategies(symbol):
            bt = Backtest(store, strategy, capital=config.total_capital,
                          reset_daily=reset_daily)
            report = bt.run(symbol, timeframe, from_dt, to_dt)
            report.print_summary()
            all_reports.append(report)

            if args.save and report.trades:
                fname = f"{out_dir}/{symbol.replace(':', '_')}_{strategy.name}.csv"
                report.save_trades(fname)
                print(f"  Trades saved → {fname}")

    # Overall summary
    if all_reports:
        total_pnl = sum(r.total_pnl() for r in all_reports)
        total_trades = sum(r.total_trades() for r in all_reports)
        wins = sum(r.winning_trades() for r in all_reports)
        print("=" * 55)
        print(f"  OVERALL SUMMARY")
        print(f"  Total P&L    : ₹{total_pnl:,.2f}")
        print(f"  Overall return: {total_pnl / config.total_capital:.2%}")
        print(f"  Total trades : {total_trades}")
        print(f"  Overall win% : {wins/total_trades:.1%}" if total_trades else "  No trades")
        print("=" * 55)


if __name__ == "__main__":
    main()
