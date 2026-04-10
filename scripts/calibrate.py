"""
Strategy parameter calibration — finds optimal params via backtest grid/random search.

    python scripts/calibrate.py --strategy rsi --from 2026-03-01 --iterations 20
    python scripts/calibrate.py --strategy orb_supertrend --from 2026-03-01 --mode grid
    python scripts/calibrate.py --strategy vwap --from 2026-03-01 --iterations 20 --update-config

Supported strategies : rsi, orb, vwap, supertrend, bollinger, ema_pullback,
                       orb_supertrend, rsi_bollinger
Optimization metrics : sharpe (default), total_pnl, win_rate, max_drawdown

NOTE: This script assumes historical candle data is already cached in the SQLite DB.
      Run `scripts/backtest.py` or `python main.py` first to warm up the data cache.
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

# Pre-parse --config so TRADER_CONFIG is set before trader modules import
_pre = argparse.ArgumentParser(add_help=False)
_pre.add_argument("--config", default=None)
_pre_args, _ = _pre.parse_known_args()
if _pre_args.config:
    os.environ["TRADER_CONFIG"] = _pre_args.config

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")

from trader.calibration.param_space import ALL_STRATEGIES
from trader.calibration.runner import (
    CalibrationRunner,
    print_ranked_table,
    print_best_params,
    write_best_params,
)
from trader.core.config import config, CONFIG_FILE
from trader.core.logger import setup
from trader.data.store import Store

setup(log_dir=config.log_dir, level="WARNING")  # suppress info noise during calibration


def parse_args():
    parser = argparse.ArgumentParser(description="Calibrate strategy parameters via backtest")
    parser.add_argument(
        "--strategy", required=True,
        choices=sorted(ALL_STRATEGIES),
        help="Strategy or group to calibrate",
    )
    parser.add_argument(
        "--symbols", nargs="+", default=None,
        metavar="NSE:XXX",
        help="Instruments to test (default: config.watchlist)",
    )
    parser.add_argument(
        "--from", dest="from_dt", required=True,
        help="Start date YYYY-MM-DD",
    )
    parser.add_argument(
        "--to", dest="to_dt", default=None,
        help="End date YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--iterations", type=int, default=20,
        help="Parameter combinations to test in random mode (default: 20)",
    )
    parser.add_argument(
        "--metric", default="sharpe",
        choices=["sharpe", "total_pnl", "win_rate", "max_drawdown"],
        help="Metric to optimise (default: sharpe)",
    )
    parser.add_argument(
        "--mode", default="random", choices=["random", "grid"],
        help="Search mode: random (default) or grid (all combinations)",
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="RNG seed for reproducible random search",
    )
    parser.add_argument(
        "--top", type=int, default=10,
        help="Rows to show in ranked table (default: 10)",
    )
    parser.add_argument(
        "--config", default=None,
        help="Path to config file (default: config/config.yaml)",
    )
    parser.add_argument(
        "--update-config", action="store_true",
        help="Write best params back to config.yaml after calibration",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    symbols = args.symbols or config.watchlist
    from_dt = datetime.strptime(args.from_dt, "%Y-%m-%d")
    to_dt = (
        datetime.strptime(args.to_dt, "%Y-%m-%d")
        if args.to_dt else datetime.now()
    ).replace(hour=23, minute=59, second=59)

    # Intraday calibration always uses 5-minute candles
    timeframe = "5minute"

    print(f"\n{'=' * 60}")
    print(f"  STRATEGY CALIBRATION — {args.strategy.upper()}")
    print(f"{'=' * 60}")
    print(f"  Symbols    : {', '.join(symbols)}")
    print(f"  Period     : {from_dt.date()} → {to_dt.date()}")
    print(f"  Metric     : {args.metric}")
    print(f"  Capital    : ₹{config.total_capital:,.0f}")
    print(f"  Timeframe  : {timeframe}")
    print()

    store = Store(config.db_path)

    runner = CalibrationRunner(
        strategy_name=args.strategy,
        symbols=symbols,
        from_dt=from_dt,
        to_dt=to_dt,
        timeframe=timeframe,
        capital=config.total_capital,
        store=store,
    )

    results = runner.run(
        iterations=args.iterations,
        metric=args.metric,
        mode=args.mode,
        seed=args.seed,
    )

    if not results:
        print("\n  No results — check that candle data is cached for these symbols.")
        return

    print_ranked_table(results, args.strategy, args.metric, top_n=args.top)
    print_best_params(results[0], args.strategy, symbols, args.metric)

    if args.update_config:
        print(f"  Writing best params to config...")
        write_best_params(args.strategy, results[0].params, CONFIG_FILE)


if __name__ == "__main__":
    main()
