"""
Rolling-window backtest — slides a fixed-width window across a date range and
consolidates results to show how strategy performance varies by market regime.

    python scripts/backtest_rolling.py --from 2024-01-01 --to 2025-12-31
    python scripts/backtest_rolling.py --from 2024-01-01 --to 2025-12-31 --window 6 --step 3
    python scripts/backtest_rolling.py --from 2024-01-01 --to 2025-12-31 --symbols NSE:RELIANCE NSE:TCS

--window : window width in months (default 6)
--step   : slide step in months (default 3)

Each window is an independent backtest with its own fresh strategy + risk state.
Candles are cached in SQLite so subsequent windows reuse already-fetched data.

Note: trades may overlap between windows (a trade opened near the end of one window
may also appear at the start of the next). The per-window stats are self-contained;
the "total trades" in the consolidated summary counts overlapping trades separately.
"""

import argparse
import calendar
import csv
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
from trader.data.store import Store
from trader.notifications import telegram
telegram.disable()

setup(log_dir=config.log_dir, level=config.log_level)
logger = get_logger(__name__)


def _add_months(dt: datetime, months: int) -> datetime:
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def _generate_windows(
    from_dt: datetime, to_dt: datetime, window_months: int, step_months: int
) -> list[tuple[datetime, datetime]]:
    windows = []
    win_start = from_dt
    while win_start < to_dt:
        win_end = _add_months(win_start, window_months).replace(
            hour=23, minute=59, second=59
        )
        if win_end > to_dt:
            win_end = to_dt
        windows.append((win_start, win_end))
        win_start = _add_months(win_start, step_months)
    return windows


def main():
    parser = argparse.ArgumentParser(description="Rolling-window backtest")
    parser.add_argument("--from", dest="from_date", required=True,
                        help="Overall start date YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date",
                        default=datetime.now().strftime("%Y-%m-%d"),
                        help="Overall end date YYYY-MM-DD (default: today)")
    parser.add_argument("--window", type=int, default=6,
                        help="Window width in months (default 6)")
    parser.add_argument("--step", type=int, default=3,
                        help="Slide step in months (default 3)")
    parser.add_argument("--symbols", nargs="+", default=None,
                        help="Override watchlist e.g. NSE:RELIANCE NSE:TCS")
    args = parser.parse_args()

    from_dt = datetime.strptime(args.from_date, "%Y-%m-%d")
    to_dt   = datetime.strptime(args.to_date,   "%Y-%m-%d").replace(
        hour=23, minute=59, second=59
    )

    kite  = create_kite()
    store = Store(config.db_path)
    store.clear_backtest_data()

    instruments     = kite.instruments("NSE")
    symbol_to_token = {
        f"NSE:{i['tradingsymbol']}": i["instrument_token"] for i in instruments
    }

    symbols       = args.symbols if args.symbols else config.watchlist
    valid_symbols = [s for s in symbols if s in symbol_to_token]
    if not valid_symbols:
        print("No valid instruments found.")
        return

    params  = config.strategy_config("lr_extrema")
    windows = _generate_windows(from_dt, to_dt, args.window, args.step)

    print(
        f"\nRolling backtest | {args.from_date} → {args.to_date} "
        f"| window={args.window}m  step={args.step}m"
    )
    print(f"Instruments : {', '.join(valid_symbols)}")
    print(f"Windows     : {len(windows)}\n")

    window_results: list[dict] = []
    all_trades:     list[dict] = []

    for i, (win_start, win_end) in enumerate(windows, 1):
        label = f"{win_start.strftime('%Y-%m-%d')} → {win_end.strftime('%Y-%m-%d')}"
        print(f"[{i}/{len(windows)}] {label} ...", end=" ", flush=True)

        trades = run_backtest(
            kite, store, valid_symbols, symbol_to_token, params, win_start, win_end
        )
        m = compute_metrics(trades, config.total_capital)

        for t in trades:
            t["window"] = label
        all_trades.extend(trades)
        window_results.append({"window": label, **m})

        print(
            f"{m['total_trades']:>3} trades | "
            f"WR {m['win_rate']:>5.1f}% | "
            f"avg win ₹{m['avg_win']:>7,.0f}  avg loss ₹{m['avg_loss']:>7,.0f} | "
            f"₹{m['total_pnl']:>+9,.0f}  ({m['return_pct']:+.2f}%)"
        )

    _print_consolidated(window_results, args.window, args.step)
    _dump_csv(all_trades, args.from_date, args.to_date, args.window, args.step)


def _print_consolidated(results: list[dict], window: int, step: int):
    SEP = "=" * 100
    print(f"\n{SEP}")
    print(f"  Consolidated summary  (window={window}m  step={step}m)")
    print(SEP)

    if not results:
        print("  No windows produced results.")
        return

    print(
        f"  {'Window':<25} {'Trades':>6} {'Win%':>6} "
        f"{'AvgWin':>9} {'AvgLoss':>9} {'Net P&L':>11} {'Return%':>8} {'Sharpe*':>7}"
    )
    print(
        f"  {'-'*25} {'-'*6} {'-'*6} "
        f"{'-'*9} {'-'*9} {'-'*11} {'-'*8} {'-'*7}"
    )

    for r in results:
        sign = "+" if r["total_pnl"] >= 0 else "-"
        print(
            f"  {r['window']:<25} {r['total_trades']:>6} {r['win_rate']:>5.1f}% "
            f"{r['avg_win']:>9,.0f} {r['avg_loss']:>9,.0f} "
            f" {sign}₹{abs(r['total_pnl']):>8,.0f} {r['return_pct']:>8.2f}% "
            f"{r['sharpe_proxy']:>7.2f}"
        )

    profitable = [r for r in results if r["total_pnl"] > 0]
    consistency = len(profitable) / len(results) * 100
    avg_return  = sum(r["return_pct"]   for r in results) / len(results)
    avg_wr      = sum(r["win_rate"]     for r in results) / len(results)
    total_trades = sum(r["total_trades"] for r in results)
    best  = max(results, key=lambda r: r["return_pct"])
    worst = min(results, key=lambda r: r["return_pct"])

    print()
    print(f"  Profitable windows : {len(profitable)}/{len(results)}  ({consistency:.0f}% consistency)")
    print(f"  Total trades       : {total_trades}  (across all windows; may include overlaps)")
    print(f"  Avg return/window  : {avg_return:+.2f}%")
    print(f"  Avg win rate       : {avg_wr:.1f}%")
    print(f"  Best window        : {best['window']}  ({best['return_pct']:+.2f}%)")
    print(f"  Worst window       : {worst['window']}  ({worst['return_pct']:+.2f}%)")
    print(f"{SEP}\n")


def _dump_csv(
    trades: list[dict], from_date: str, to_date: str, window: int, step: int
):
    if not trades:
        return
    now      = datetime.now().strftime("%Y%m%d_%H%M%S")
    from_str = from_date.replace("-", "")
    to_str   = to_date.replace("-", "")
    tf       = config.candle_timeframe.replace("minute", "m").replace("day", "1d")
    filename = f"rolling_{from_str}_{to_str}_{tf}_w{window}s{step}_{now}.csv"
    out_path = Path(__file__).resolve().parents[1] / "backtest_results" / filename

    fields = [
        "window", "instrument", "entry_date", "exit_date",
        "entry", "exit", "qty", "cost", "pnl", "product", "reason", "held_candles",
    ]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(trades)
    print(f"  CSV saved : {out_path}")


if __name__ == "__main__":
    main()
