"""
Walk-forward backtest — true out-of-sample validation.

Two modes:

1. Fixed-param (default) — validates that the self-training MODEL generalises.
   Each fold trains the model only on data before the test window, then records
   trades on the unseen test window using the config params unchanged.

2. Calibrated (--calibrate) — validates that PARAMETER SELECTION generalises.
   This is the honest answer to the curve-fitting risk in calibrate.py/screen.py:
   per fold we search the param grid on the TRAIN window, pick the best params,
   then evaluate THOSE EXACT params on the unseen TEST window. The train-vs-OOS
   gap is the overfitting tell — if calibrated train returns are great but OOS
   collapses, the calibration was fitting noise.

    python scripts/walk_forward.py --from 2024-01-01 --to 2025-12-31
    python scripts/walk_forward.py --from 2024-01-01 --to 2025-12-31 --train 6 --test 3
    python scripts/walk_forward.py --from 2024-01-01 --to 2025-12-31 --cache-only
    # calibrated walk-forward (per-stock or global param selection):
    python scripts/walk_forward.py --from 2024-01-01 --to 2025-12-31 --calibrate --unit per-stock --iterations 40 --cache-only
    python scripts/walk_forward.py --from 2024-01-01 --to 2025-12-31 --calibrate --unit global --mode grid --cache-only

--train : training window width in months (default 6)
--test  : test window width in months (default 3); also the slide step

Fold structure (train=6, test=3, from=2024-01-01):
  Fold 1: train Jul–Dec 2023  →  test Jan–Mar 2024
  Fold 2: train Oct 2023–Mar 2024  →  test Apr–Jun 2024
  Fold 3: train Jan–Jun 2024  →  test Jul–Sep 2024
  ...

Test windows are non-overlapping.  The model entering each test window was
trained ONLY on data before that window — no future leakage.

Consistency (% profitable folds) is the key metric: a robust strategy should
be profitable in >60% of folds across different market regimes.
"""

import argparse
import calendar
import csv
import logging
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for sibling calibrate import

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

setup(log_dir=config.log_dir, level="ERROR")
logger = get_logger(__name__)


def _add_months(dt: datetime, months: int) -> datetime:
    month = dt.month - 1 + months
    year  = dt.year + month // 12
    month = month % 12 + 1
    day   = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _months_to_days(dt: datetime, months: int) -> int:
    """Approximate day count for *months* months starting at *dt*."""
    end = _add_months(dt, months)
    return (end - dt).days


def _generate_folds(
    from_dt: datetime,
    to_dt: datetime,
    train_months: int,
    test_months: int,
) -> list[tuple[datetime, datetime, int]]:
    """
    Returns list of (test_start, test_end, train_days).
    Test windows are non-overlapping and advance by test_months each fold.
    train_days is the pre-warmup window fed to run_backtest as pre_warmup_days.
    """
    folds = []
    test_start = from_dt
    while test_start < to_dt:
        test_end = _add_months(test_start, test_months).replace(hour=23, minute=59, second=59)
        if test_end > to_dt:
            test_end = to_dt
        train_days = _months_to_days(
            test_start - timedelta(days=_months_to_days(test_start, train_months)),
            train_months,
        )
        folds.append((test_start, test_end, train_days))
        test_start = _add_months(test_start, test_months)
    return folds


def _run_calib_job(job: tuple) -> dict:
    """Phase-1 worker — search one combo for one (fold, key) on its TRAIN window.
    Top-level for multiprocessing pickling."""
    # Worker processes (spawn) don't inherit parent's logging config — silence them.
    logging.getLogger().setLevel(logging.CRITICAL)
    (fold, key, params, symbols, symbol_to_token,
     train_from, train_end, pre_warmup_days, db_path, capital, timeframe) = job
    if timeframe:
        config._data["candle_timeframe"] = timeframe
    store = Store(db_path)
    trades = run_backtest(
        None, store, symbols, symbol_to_token, params,
        train_from, train_end, pre_warmup_days=pre_warmup_days,
    )
    return {
        "fold": fold, "key": key, "params": params,
        "return_pct": compute_metrics(trades, capital)["return_pct"],
    }


def _run_oos_job(job: tuple) -> dict:
    """Phase-2 worker — run the OOS backtest for one fold. Top-level for pickling."""
    logging.getLogger().setLevel(logging.CRITICAL)
    (fold, params, per_symbol_params, symbols, symbol_to_token,
     test_start, test_end, train_days, db_path, timeframe) = job
    if timeframe:
        config._data["candle_timeframe"] = timeframe
    store = Store(db_path)
    trades = run_backtest(
        None, store, symbols, symbol_to_token, params,
        test_start, test_end, pre_warmup_days=train_days,
        per_symbol_params=per_symbol_params,
    )
    return {"fold": fold, "trades": trades}


def _prefetch_range(kite, store, symbols, symbol_to_token, from_dt, to_dt):
    """Warm the candle cache for [from_dt, to_dt] so worker processes (kite=None)
    hit cache only. Covers regime symbols (NIFTY 50, INDIA VIX) too."""
    if kite is None:
        return
    for sym in set(symbols) | {"NSE:NIFTY 50", "NSE:INDIA VIX"}:
        token = symbol_to_token.get(sym)
        if token is None:
            continue
        get_candles(kite, store, token, sym, config.candle_timeframe, from_dt, to_dt)


def main():
    parser = argparse.ArgumentParser(description="Walk-forward out-of-sample backtest")
    parser.add_argument("--from", dest="from_date", required=True,
                        help="Test period start date YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date",
                        default=datetime.now().strftime("%Y-%m-%d"),
                        help="Test period end date YYYY-MM-DD (default: today)")
    parser.add_argument("--train", type=int, default=6,
                        help="Training window in months (default 6)")
    parser.add_argument("--test", type=int, default=3,
                        help="Test window in months, also the slide step (default 3)")
    parser.add_argument("--symbols", nargs="+", default=None,
                        help="Override watchlist e.g. NSE:RELIANCE NSE:TCS")
    parser.add_argument("--timeframe", default=None,
                        choices=["5minute", "15minute", "30minute", "60minute", "day"],
                        help="Candle timeframe (default: from config)")
    parser.add_argument("--cache-only", action="store_true",
                        help="Skip Kite auth — use only locally cached candle data")
    # --- Calibrated walk-forward (param selection on train, validated on OOS) ---
    parser.add_argument("--calibrate", action="store_true",
                        help="Calibrate params on each train window and validate on the OOS test window")
    parser.add_argument("--unit", choices=["per-stock", "global"], default="per-stock",
                        help="Calibrate per stock or one shared global param set (default per-stock)")
    parser.add_argument("--mode", choices=["grid", "random"], default="random",
                        help="Param search mode for --calibrate (default random)")
    parser.add_argument("--iterations", type=int, default=40,
                        help="Random-search iterations per train window (random mode; default 40)")
    parser.add_argument("--cal-params", nargs="+", default=None, metavar="PARAM",
                        help="Restrict calibration to these params (default: full PARAM_GRID)")
    parser.add_argument("--workers", type=int, default=None,
                        help="Parallel worker processes for --calibrate (default: CPU count)")
    args = parser.parse_args()

    if args.timeframe:
        config._data["candle_timeframe"] = args.timeframe

    from_dt = datetime.strptime(args.from_date, "%Y-%m-%d")
    to_dt   = datetime.strptime(args.to_date,   "%Y-%m-%d").replace(hour=23, minute=59, second=59)

    store = Store(config.db_path)

    if args.cache_only:
        kite = None
        symbols = args.symbols or list(config.watchlist)
        symbol_to_token = {s: 0 for s in symbols}
        valid_symbols = symbols
    else:
        store.clear_backtest_data()
        kite = create_kite()
        instruments     = kite.instruments("NSE")
        symbol_to_token = {
            f"NSE:{i['tradingsymbol']}": i["instrument_token"] for i in instruments
        }
        symbols       = args.symbols or config.watchlist
        valid_symbols = [s for s in symbols if s in symbol_to_token]

    if not valid_symbols:
        print("No valid instruments found.")
        return

    params = config.strategy_config("lr_extrema")
    folds  = _generate_folds(from_dt, to_dt, args.train, args.test)
    capital = config.total_capital

    # Build the calibration combo list once (same grid reused on every train window).
    combos = None
    if args.calibrate:
        from calibrate import PARAM_GRID, _build_active_grid, _all_combinations, _random_combinations
        grid = _build_active_grid(args.cal_params, params)
        combos = (_all_combinations(grid) if args.mode == "grid"
                  else _random_combinations(args.iterations, grid))

    n_workers = args.workers or os.cpu_count() or 1

    mode_label = (f"CALIBRATED ({args.unit}, {args.mode}"
                  + (f"×{len(combos)}" if combos else "") + ")") if args.calibrate else "fixed-param"
    print(
        f"\nWalk-forward backtest [{mode_label}] | {args.from_date} → {args.to_date}"
        f" | train={args.train}m  test={args.test}m"
    )
    print(f"Instruments : {', '.join(valid_symbols)}")
    print(f"Folds       : {len(folds)}")
    print(f"Workers     : {n_workers}\n")

    # Pre-warm the candle cache for the full span covered by every fold (train+test)
    # so all worker processes below run cache-only (kite=None).
    if folds:
        earliest = min(test_start - timedelta(days=2 * train_days) for test_start, _, train_days in folds)
        _prefetch_range(kite, store, valid_symbols, symbol_to_token, earliest, to_dt)

    # --- Phase 1: calibrate params per fold (all folds × keys × combos run in parallel) ---
    fold_per_symbol_params: dict[int, dict] = {}
    fold_train_return: dict[int, dict] = {}
    if args.calibrate:
        jobs = []
        for i, (test_start, test_end, train_days) in enumerate(folds, 1):
            train_from = test_start - timedelta(days=train_days)
            if args.unit == "global":
                jobs.extend(
                    (i, "global", combo, valid_symbols, symbol_to_token,
                     train_from, test_start, train_days, config.db_path, capital, args.timeframe)
                    for combo in combos
                )
            else:
                jobs.extend(
                    (i, sym, combo, [sym], symbol_to_token,
                     train_from, test_start, train_days, config.db_path, capital, args.timeframe)
                    for sym in valid_symbols for combo in combos
                )

        print(f"Calibrating {len(jobs)} (fold × key × combo) jobs across {n_workers} workers...")
        best: dict[tuple[int, str], tuple[float, dict]] = {}
        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            futures = {executor.submit(_run_calib_job, job): job for job in jobs}
            done = 0
            for future in as_completed(futures):
                done += 1
                result = future.result()
                bk = (result["fold"], result["key"])
                if bk not in best or result["return_pct"] > best[bk][0]:
                    best[bk] = (result["return_pct"], result["params"])
                print(f"\r  [{done}/{len(jobs)}]", end="", flush=True)
        print()

        for i in range(1, len(folds) + 1):
            if args.unit == "global":
                ret, combo = best[(i, "global")]
                fold_per_symbol_params[i] = {s: combo for s in valid_symbols}
                fold_train_return[i] = {"global": ret}
            else:
                fold_per_symbol_params[i] = {s: best[(i, s)][1] for s in valid_symbols}
                fold_train_return[i] = {s: best[(i, s)][0] for s in valid_symbols}

    # --- Phase 2: OOS backtest per fold (all folds run in parallel) ---
    oos_jobs = [
        (i, params, fold_per_symbol_params.get(i), valid_symbols, symbol_to_token,
         test_start, test_end, train_days, config.db_path, args.timeframe)
        for i, (test_start, test_end, train_days) in enumerate(folds, 1)
    ]

    print(f"Running {len(oos_jobs)} OOS fold backtests across {n_workers} workers...\n")
    fold_trades: dict[int, list[dict]] = {}
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        futures = {executor.submit(_run_oos_job, job): job[0] for job in oos_jobs}
        for future in as_completed(futures):
            result = future.result()
            fold_trades[result["fold"]] = result["trades"]

    # --- Assemble + print results in fold order ---
    fold_results: list[dict] = []
    all_trades:   list[dict] = []

    for i, (test_start, test_end, train_days) in enumerate(folds, 1):
        train_from = test_start - timedelta(days=train_days)
        trades = fold_trades[i]
        m = compute_metrics(trades, capital)

        for t in trades:
            t["fold"] = i
            t["test_window"] = f"{test_start.strftime('%Y-%m-%d')}→{test_end.strftime('%Y-%m-%d')}"
        all_trades.extend(trades)

        train_ret_mean = None
        if i in fold_train_return:
            tr = fold_train_return[i]
            train_ret_mean = sum(tr.values()) / len(tr)

        fold_results.append({
            "fold": i,
            "train_from": train_from.strftime("%Y-%m-%d"),
            "test_start": test_start.strftime("%Y-%m-%d"),
            "test_end":   test_end.strftime("%Y-%m-%d"),
            "train_return_pct": train_ret_mean,
            **m,
        })

        label = (
            f"train {train_from.strftime('%Y-%m-%d')}→{test_start.strftime('%Y-%m-%d')}"
            f"  test {test_start.strftime('%Y-%m-%d')}→{test_end.strftime('%Y-%m-%d')}"
        )
        prefix = f"[{i}/{len(folds)}] {label} ... "
        if train_ret_mean is not None:
            prefix += f"[train {train_ret_mean:+.2f}%] "
        print(
            prefix +
            f"{m['total_trades']:>3} trades | "
            f"WR {m['money_weighted_win_rate']:>5.1f}% | "
            f"PF {m['profit_factor']:>4.2f} | "
            f"avg win ₹{m['avg_win']:>7,.0f}  avg loss ₹{m['avg_loss']:>7,.0f} | "
            f"₹{m['total_pnl']:>+9,.0f}  ({m['return_pct']:+.2f}%)"
        )

    _print_summary(fold_results, args.train, args.test)
    _dump_csv(all_trades, args.from_date, args.to_date, args.train, args.test)


def _print_summary(results: list[dict], train: int, test: int):
    SEP = "=" * 110
    print(f"\n{SEP}")
    print(f"  Walk-forward summary  (train={train}m  test={test}m  —  test windows are non-overlapping OOS)")
    print(SEP)

    if not results:
        print("  No folds produced results.")
        return

    print(
        f"  {'Fold':>4}  {'Test window':<23}  {'Trades':>6}  {'WR%':>6}  {'PF':>5}  "
        f"{'AvgWin':>9}  {'AvgLoss':>9}  {'Net P&L':>11}  {'Return%':>8}  {'MaxDD%':>7}"
    )
    print(
        f"  {'----':>4}  {'-'*23}  {'-'*6}  {'-'*6}  {'-'*5}  "
        f"{'-'*9}  {'-'*9}  {'-'*11}  {'-'*8}  {'-'*7}"
    )

    for r in results:
        sign = "+" if r["total_pnl"] >= 0 else "-"
        print(
            f"  {r['fold']:>4}  {r['test_start']}→{r['test_end']:<10}  "
            f"{r['total_trades']:>6}  {r['money_weighted_win_rate']:>5.1f}%  "
            f"{r['profit_factor']:>5.2f}  "
            f"{r['avg_win']:>9,.0f}  {r['avg_loss']:>9,.0f}  "
            f" {sign}₹{abs(r['total_pnl']):>8,.0f}  {r['return_pct']:>8.2f}%  "
            f"{r['max_drawdown_pct']:>6.1f}%"
        )

    profitable   = [r for r in results if r["total_pnl"] > 0]
    consistency  = len(profitable) / len(results) * 100
    avg_return   = sum(r["return_pct"]              for r in results) / len(results)
    avg_wr       = sum(r["money_weighted_win_rate"] for r in results) / len(results)
    avg_pf       = sum(r["profit_factor"]           for r in results) / len(results)
    avg_dd       = sum(r["max_drawdown_pct"]        for r in results) / len(results)
    total_trades = sum(r["total_trades"]            for r in results)
    best  = max(results, key=lambda r: r["return_pct"])
    worst = min(results, key=lambda r: r["return_pct"])

    print()
    print(f"  Profitable folds   : {len(profitable)}/{len(results)}  ({consistency:.0f}% consistency)")
    print(f"  Total trades       : {total_trades}  (across all folds; test windows are non-overlapping)")
    # Calibrated mode: expose the train→OOS degradation (the overfitting tell).
    _train = [r["train_return_pct"] for r in results if r.get("train_return_pct") is not None]
    if _train:
        avg_train = sum(_train) / len(_train)
        print(f"  Avg TRAIN return   : {avg_train:+.2f}%  (in-sample, calibrated)")
        print(f"  Avg OOS  return    : {avg_return:+.2f}%  (out-of-sample)")
        print(f"  Train→OOS gap      : {avg_train - avg_return:+.2f}%  "
              f"(large positive = calibration overfitting train noise)")
    print(f"  Avg return/fold    : {avg_return:+.2f}%")
    print(f"  Avg win rate       : {avg_wr:.1f}%")
    print(f"  Avg profit factor  : {avg_pf:.2f}")
    print(f"  Avg max drawdown   : {avg_dd:.1f}%")
    print(f"  Best fold          : {best['test_start']}→{best['test_end']}  ({best['return_pct']:+.2f}%)")
    print(f"  Worst fold         : {worst['test_start']}→{worst['test_end']}  ({worst['return_pct']:+.2f}%)")
    print()
    print("  Interpretation:")
    print("  - Consistency >60% → strategy is robust across market regimes")
    print("  - Avg return significantly below regular backtest → training look-ahead was inflating results")
    print("  - Stable avg profit factor >1.2 across folds → edge is real, not period-specific")
    print(f"{SEP}\n")


def _dump_csv(
    trades: list[dict], from_date: str, to_date: str, train: int, test: int
):
    if not trades:
        return
    now      = datetime.now().strftime("%Y%m%d_%H%M%S")
    from_str = from_date.replace("-", "")
    to_str   = to_date.replace("-", "")
    tf       = config.candle_timeframe.replace("minute", "m").replace("day", "1d")
    filename = f"walkfwd_{from_str}_{to_str}_{tf}_tr{train}te{test}_{now}.csv"
    out_path = Path(__file__).resolve().parents[1] / "backtest_results" / filename

    fields = [
        "fold", "test_window", "instrument", "entry_date", "exit_date",
        "entry", "exit", "qty", "cost", "pnl", "product", "reason", "held_candles",
    ]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(trades)
    print(f"  CSV saved : {out_path}")


if __name__ == "__main__":
    main()
