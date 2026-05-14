"""
Walk-forward backtest — true out-of-sample validation.

Each fold has a dedicated training window (pre-warmup only, no trades recorded)
followed by a non-overlapping test window (trades recorded).  This prevents the
rolling training buffer from "seeing" the test period and inflating metrics.

    python scripts/walk_forward.py --from 2024-01-01 --to 2025-12-31
    python scripts/walk_forward.py --from 2024-01-01 --to 2025-12-31 --train 6 --test 3
    python scripts/walk_forward.py --from 2024-01-01 --to 2025-12-31 --cache-only

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
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")

from trader.auth.session import create_kite
from trader.backtest.engine import compute_metrics, run_backtest
from trader.core.config import config
from trader.core.logger import get_logger, setup
from trader.data.store import Store
from trader.notifications import telegram
telegram.disable()

setup(log_dir=config.log_dir, level=config.log_level)
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

    print(
        f"\nWalk-forward backtest | {args.from_date} → {args.to_date}"
        f" | train={args.train}m  test={args.test}m"
    )
    print(f"Instruments : {', '.join(valid_symbols)}")
    print(f"Folds       : {len(folds)}\n")

    fold_results: list[dict] = []
    all_trades:   list[dict] = []

    for i, (test_start, test_end, train_days) in enumerate(folds, 1):
        train_from = test_start - timedelta(days=train_days)
        label = (
            f"train {train_from.strftime('%Y-%m-%d')}→{test_start.strftime('%Y-%m-%d')}"
            f"  test {test_start.strftime('%Y-%m-%d')}→{test_end.strftime('%Y-%m-%d')}"
        )
        print(f"[{i}/{len(folds)}] {label} ...", end=" ", flush=True)

        trades = run_backtest(
            kite, store, valid_symbols, symbol_to_token, params,
            test_start, test_end,
            pre_warmup_days=train_days,
        )
        m = compute_metrics(trades, config.total_capital)

        for t in trades:
            t["fold"] = i
            t["test_window"] = f"{test_start.strftime('%Y-%m-%d')}→{test_end.strftime('%Y-%m-%d')}"
        all_trades.extend(trades)
        fold_results.append({
            "fold": i,
            "train_from": train_from.strftime("%Y-%m-%d"),
            "test_start": test_start.strftime("%Y-%m-%d"),
            "test_end":   test_end.strftime("%Y-%m-%d"),
            **m,
        })

        print(
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
