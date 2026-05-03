"""
Calibrate LRExtremaStrategy parameters systematically on the watchlist.

    python scripts/calibrate.py --from 2024-01-01
    python scripts/calibrate.py --from 2024-01-01 --to 2025-01-01 --mode random --iterations 50
    python scripts/calibrate.py --from 2024-01-01 --mode grid   # all 8640 combinations
"""

import argparse
import itertools
import logging
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
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
    "warmup_bars":   [100, 150, 200, 300, 400],
    "lookback_bars": [400, 500, 600, 800],
    "threshold":     [0.75, 0.80, 0.85, 0.90],
    "profit_pct":    [6.0, 8.0, 10.0, 15.0, 20.0, 25.0, 30.0],
    "trail_pct":     [1.5, 2.0, 2.5, 3.0],
    "stop_pct":      [4.0, 5.0, 6.0],
    "hold_bars":     [200, 250, 300],
    "retrain_every": [25, 50],
    "extrema_order": [3, 5, 7],
}

_KEYS = list(PARAM_GRID.keys())


def _build_active_grid(active_params: list[str] | None, base_params: dict) -> dict:
    """
    Build effective search grid.
    - Specified params (or all, if none given) → use PARAM_GRID ranges.
    - Remaining params → fixed at their config value.
    """
    grid = {}
    for key in PARAM_GRID:
        if active_params is None or key in active_params:
            grid[key] = PARAM_GRID[key]
        else:
            grid[key] = [base_params.get(key, PARAM_GRID[key][0])]
    return grid


def _all_combinations(grid: dict) -> list[dict]:
    keys = list(grid.keys())
    return [dict(zip(keys, combo)) for combo in itertools.product(*grid.values())]


def _random_combinations(n: int, grid: dict) -> list[dict]:
    return [{k: random.choice(v) for k, v in grid.items()} for _ in range(n)]


def _prefetch_candles(kite, store, symbols, symbol_to_token, from_dt, to_dt):
    print(f"Pre-fetching candle data for {symbols}...")
    for symbol in symbols:
        token = symbol_to_token.get(symbol)
        if token is None:
            print(f"  WARNING: {symbol} not found in NSE instruments — will be skipped")
            continue
        df = get_candles(kite, store, token, symbol, config.candle_timeframe, from_dt, to_dt)
        print(f"  {symbol}: {len(df)} candles cached")


def _run_single(job: tuple) -> dict:
    """Worker — run one backtest combination. Top-level for multiprocessing pickling."""
    # Worker processes (spawn) don't inherit parent's logging config — silence them.
    logging.getLogger().setLevel(logging.CRITICAL)
    params, symbols, symbol_to_token, from_dt, to_dt, db_path, total_capital, timeframe = job
    if timeframe:
        config._data["candle_timeframe"] = timeframe
    store = Store(db_path)
    trades = run_backtest(None, store, symbols, symbol_to_token, params, from_dt, to_dt)
    metrics = compute_metrics(trades, total_capital)
    return {**params, **metrics}


def _print_results(results: list[dict]):
    if not results:
        print("No results to display.")
        return

    print(f"\n{'='*130}")
    print(f"  Calibration Results — sorted by Return%")
    print(f"{'='*130}")
    print(
        f"  {'Rank':>4}  {'warmup':>6}  {'lookbk':>6}  {'thresh':>6}  {'profit':>6}  {'trail':>5}  "
        f"{'stop':>5}  {'hold':>5}  {'retrain':>7}  {'extrema':>7}  "
        f"{'Trades':>6}  {'Win%':>5}  {'P&L':>10}  {'Return%':>8}  {'Sharpe*':>8}"
    )
    print(f"  {'-'*126}")
    for i, r in enumerate(results, 1):
        print(
            f"  {i:>4}  {r['warmup_bars']:>6}  {r['lookback_bars']:>6}  {r['threshold']:>6.2f}  "
            f"{r['profit_pct']:>6.1f}  {r['trail_pct']:>5.1f}  "
            f"{r['stop_pct']:>5.1f}  {r['hold_bars']:>5}  {r['retrain_every']:>7}  "
            f"{r['extrema_order']:>7}  "
            f"{r['total_trades']:>6}  {r['money_weighted_win_rate']:>4.0f}%  "
            f"₹{r['total_pnl']:>9,.0f}  {r['return_pct']:>7.2f}%  {r['sharpe_proxy']:>8.3f}"
        )
    print(f"{'='*130}\n")

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
    parser.add_argument("--timeframe", default=None,
                        choices=["5minute", "15minute", "30minute", "60minute", "day"],
                        help="Candle timeframe (default: from config)")
    parser.add_argument("--params", nargs="+", default=None,
                        choices=_KEYS, metavar="PARAM",
                        help=f"Params to calibrate (default: all). Rest fixed at config values. "
                             f"Choices: {', '.join(_KEYS)}")
    parser.add_argument("--workers", type=int, default=None,
                        help="Parallel worker processes (default: CPU count)")
    args = parser.parse_args()
    if args.timeframe:
        config._data["candle_timeframe"] = args.timeframe

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

    base_params = config.strategy_config("lr_extrema")
    active_grid = _build_active_grid(args.params, base_params)

    if args.mode == "grid":
        combinations = _all_combinations(active_grid)
        if len(combinations) > 1000:
            print(
                f"WARNING: Grid mode has {len(combinations):,} combinations. "
                f"This may take a while. Use --mode random --iterations 200 for faster results."
            )
    else:
        combinations = _random_combinations(args.iterations, active_grid)

    print(f"\nCalibration | {args.from_date} → {args.to_date} | {args.mode} mode | "
          f"{len(combinations)} combinations | watchlist={valid_watchlist}")

    _prefetch_candles(kite, store, valid_watchlist, symbol_to_token, from_dt, to_dt)
    print()

    n_workers = args.workers or os.cpu_count() or 1
    width = len(str(len(combinations)))
    jobs = [
        (params, valid_watchlist, symbol_to_token, from_dt, to_dt,
         config.db_path, config.total_capital, args.timeframe)
        for params in combinations
    ]

    results = []
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        future_to_params = {executor.submit(_run_single, job): job[0] for job in jobs}
        done = 0
        for future in as_completed(future_to_params):
            done += 1
            params = future_to_params[future]
            param_str = (
                f"warmup={params['warmup_bars']} thresh={params['threshold']:.2f} "
                f"profit={params['profit_pct']} stop={params['stop_pct']} "
                f"hold={params['hold_bars']} retrain={params['retrain_every']} "
                f"extrema={params['extrema_order']}"
            )
            try:
                result = future.result()
                results.append(result)
                m = result
                print(
                    f"[{done:{width}}/{len(combinations)}] {param_str}  "
                    f"Trades={m['total_trades']}  Wt.Win={m['money_weighted_win_rate']:.0f}%  "
                    f"P&L=₹{m['total_pnl']:,.0f}  Return={m['return_pct']:.2f}%",
                    flush=True,
                )
            except Exception as exc:
                print(f"[{done:{width}}/{len(combinations)}] {param_str}  ERROR: {exc}", flush=True)

    results.sort(key=lambda r: r["return_pct"], reverse=True)
    _print_results(results)


if __name__ == "__main__":
    main()
