"""
Calibrate LRExtremaStrategy parameters systematically on the watchlist.

    python scripts/calibrate.py --from 2024-01-01
    python scripts/calibrate.py --from 2024-01-01 --to 2025-01-01 --mode random --iterations 50
    python scripts/calibrate.py --from 2024-01-01 --mode grid   # all 8640 combinations
"""

import argparse
import itertools
import random
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")

from trader.auth.session import create_kite
from trader.backtest.engine import compute_metrics, run_backtest
from trader.core.config import config
from trader.core.logger import get_logger, setup
from trader.data.historical import get_candles
from trader.data.store import Store
from trader.notifications import telegram
telegram.disable()

setup(log_dir=config.log_dir, level="WARNING")  # suppress info noise during calibration
logger = get_logger(__name__)

PARAM_GRID = {
    "warmup_bars":   [100, 150, 200, 300],
    "threshold":     [0.65, 0.70, 0.75, 0.80, 0.85, 0.90],
    "profit_pct":    [3.0, 4.0, 5.0, 6.0, 8.0],
    "stop_pct":      [1.5, 2.0, 2.5, 3.0],
    "hold_bars":     [50, 100, 150, 200],
    "retrain_every": [25, 50, 100],
    "extrema_order": [3, 5, 7],
}

_KEYS = list(PARAM_GRID.keys())


def _all_combinations() -> list[dict]:
    return [
        dict(zip(_KEYS, combo))
        for combo in itertools.product(*PARAM_GRID.values())
    ]


def _random_combinations(n: int) -> list[dict]:
    return [
        {k: random.choice(v) for k, v in PARAM_GRID.items()}
        for _ in range(n)
    ]


def _prefetch_candles(kite, store, symbols, symbol_to_token, from_dt, to_dt):
    print(f"Pre-fetching candle data for {symbols}...")
    for symbol in symbols:
        token = symbol_to_token.get(symbol)
        if token is None:
            print(f"  WARNING: {symbol} not found in NSE instruments — will be skipped")
            continue
        df = get_candles(kite, store, token, symbol, config.candle_timeframe, from_dt, to_dt)
        print(f"  {symbol}: {len(df)} candles cached")


def _print_results(results: list[dict]):
    if not results:
        print("No results to display.")
        return

    print(f"\n{'='*110}")
    print(f"  Calibration Results — sorted by Return%")
    print(f"{'='*110}")
    print(
        f"  {'Rank':>4}  {'warmup':>6}  {'thresh':>6}  {'profit':>6}  {'stop':>5}  "
        f"{'hold':>5}  {'retrain':>7}  {'extrema':>7}  "
        f"{'Trades':>6}  {'Win%':>5}  {'P&L':>10}  {'Return%':>8}  {'Sharpe*':>8}"
    )
    print(f"  {'-'*106}")
    for i, r in enumerate(results, 1):
        print(
            f"  {i:>4}  {r['warmup_bars']:>6}  {r['threshold']:>6.2f}  {r['profit_pct']:>6.1f}  "
            f"{r['stop_pct']:>5.1f}  {r['hold_bars']:>5}  {r['retrain_every']:>7}  "
            f"{r['extrema_order']:>7}  "
            f"{r['total_trades']:>6}  {r['win_rate']:>4.0f}%  "
            f"₹{r['total_pnl']:>9,.0f}  {r['return_pct']:>7.2f}%  {r['sharpe_proxy']:>8.3f}"
        )
    print(f"{'='*110}\n")

    best = results[0]
    print("Best params to use in config.yaml:")
    print(f"  lr_extrema:")
    for k in _KEYS:
        print(f"    {k}: {best[k]}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Calibrate LRExtremaStrategy parameters")
    parser.add_argument("--from", dest="from_date", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", default=datetime.now().strftime("%Y-%m-%d"),
                        help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--mode", choices=["grid", "random"], default="random",
                        help="Search mode: grid (all combinations) or random (sampled)")
    parser.add_argument("--iterations", type=int, default=50,
                        help="Number of random combinations to try (random mode only)")
    args = parser.parse_args()

    from_dt = datetime.strptime(args.from_date, "%Y-%m-%d")
    to_dt = datetime.strptime(args.to_date, "%Y-%m-%d").replace(hour=23, minute=59)

    kite = create_kite()
    store = Store(config.db_path)

    instruments = kite.instruments("NSE")
    symbol_to_token = {
        f"NSE:{i['tradingsymbol']}": i["instrument_token"] for i in instruments
    }
    valid_watchlist = [s for s in config.watchlist if s in symbol_to_token]
    if not valid_watchlist:
        print("No valid instruments in watchlist.")
        return

    if args.mode == "grid":
        combinations = _all_combinations()
        if len(combinations) > 1000:
            print(
                f"WARNING: Grid mode has {len(combinations):,} combinations. "
                f"This may take a while. Use --mode random --iterations 200 for faster results."
            )
    else:
        combinations = _random_combinations(args.iterations)

    print(f"\nCalibration | {args.from_date} → {args.to_date} | {args.mode} mode | "
          f"{len(combinations)} combinations | watchlist={valid_watchlist}")

    _prefetch_candles(kite, store, valid_watchlist, symbol_to_token, from_dt, to_dt)
    print()

    results = []
    for i, params in enumerate(combinations, 1):
        param_str = (
            f"warmup={params['warmup_bars']} thresh={params['threshold']:.2f} "
            f"profit={params['profit_pct']} stop={params['stop_pct']} "
            f"hold={params['hold_bars']} retrain={params['retrain_every']} "
            f"extrema={params['extrema_order']}"
        )
        print(f"[{i:>{len(str(len(combinations)))}}/{len(combinations)}] {param_str}", end="  ", flush=True)

        trades = run_backtest(kite, store, valid_watchlist, symbol_to_token, params, from_dt, to_dt)
        metrics = compute_metrics(trades, config.total_capital)

        results.append({**params, **metrics})
        print(
            f"Trades={metrics['total_trades']}  Win={metrics['win_rate']:.0f}%  "
            f"P&L=₹{metrics['total_pnl']:,.0f}  Return={metrics['return_pct']:.2f}%"
        )

    results.sort(key=lambda r: r["return_pct"], reverse=True)
    _print_results(results)


if __name__ == "__main__":
    main()
