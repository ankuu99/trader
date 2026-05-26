"""
Backtest runner — replays historical candles through the same pipeline as main.py.

    python scripts/backtest.py --from 2025-01-01
    python scripts/backtest.py --from 2025-01-01 --to 2025-12-31

Uses the same RiskManager, OrderManager (paper mode), and Strategy instances as live.
The only backtest-specific addition is SL simulation: checks candle low against the
stop-loss price placed with each order.
"""

import argparse
import csv
import sys
import time
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


def main():
    parser = argparse.ArgumentParser(description="Backtest strategies on historical data")
    parser.add_argument("--from", dest="from_date", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", default=datetime.now().strftime("%Y-%m-%d"),
                        help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--timeframe", default=None,
                        choices=["minute", "5minute", "15minute", "30minute", "60minute", "day"],
                        help="Candle timeframe (default: from config)")
    parser.add_argument("--cache-only", action="store_true",
                        help="Skip Kite authentication and use only locally cached candle data")
    args = parser.parse_args()
    if args.timeframe:
        config._data["candle_timeframe"] = args.timeframe

    from_dt = datetime.strptime(args.from_date, "%Y-%m-%d")
    to_dt = datetime.strptime(args.to_date, "%Y-%m-%d").replace(hour=23, minute=59)

    store = Store(config.db_path)
    if not args.cache_only:
        store.clear_backtest_data()

    if args.cache_only:
        kite = None
        valid_watchlist = list(config.watchlist)
        symbol_to_token = {s: 0 for s in valid_watchlist}
        logger.info("Cache-only mode — skipping Kite authentication")
    else:
        kite = create_kite()
        instruments = kite.instruments("NSE")
        symbol_to_token = {
            f"NSE:{i['tradingsymbol']}": i["instrument_token"] for i in instruments
        }
        valid_watchlist = [s for s in config.watchlist if s in symbol_to_token]

    if not valid_watchlist:
        print("No valid instruments in watchlist.")
        return

    logger.info("Backtest | %s to %s | instruments=%s", args.from_date, args.to_date, valid_watchlist)

    params = config.strategy_config("lr_extrema")

    def _progress(date, pct):
        print(f"\r  Progress: {date}  [{pct*100:5.1f}%]", end="", flush=True)

    t0 = time.perf_counter()
    trades = run_backtest(kite, store, valid_watchlist, symbol_to_token, params, from_dt, to_dt,
                          progress_callback=_progress)
    print()  # newline after progress line
    elapsed = time.perf_counter() - t0
    _print_summary(trades, args.from_date, args.to_date)
    _dump_csv(trades, args.from_date, args.to_date)
    print(f"  Elapsed    : {elapsed:.2f}s")
    print(f"  Params     : {', '.join(f'{k}={v}' for k, v in params.items())}")


def _print_summary(trades: list[dict], from_date: str, to_date: str):
    W = 62
    print(f"\n{'='*W}")
    print(f"  Backtest: {from_date}  →  {to_date}")
    print(f"{'='*W}")

    if not trades:
        print("  No trades executed.")
        print(f"{'='*W}\n")
        return

    m = compute_metrics(trades, config.total_capital)
    total_costs = sum(t.get("cost", 0.0) for t in trades)

    # Effective capital at entry of each trade
    sorted_for_capital = sorted(trades, key=lambda t: t.get("entry_date") or "")
    running_pnl = 0.0
    capital_at_entry: dict[int, float] = {}
    for t in sorted_for_capital:
        capital_at_entry[id(t)] = config.total_capital + running_pnl
        running_pnl += t["pnl"]

    print(f"\n  {'Entry Date':<19} {'Exit Date':<19} {'Days':>4} {'Bars':>5} {'Instrument':<15} {'Entry':>8} {'Exit':>8} {'Qty':>5} {'Cost':>8} {'Net P&L':>10} {'P&L%':>7} {'Capital':>10}  Prod  Reason")
    print(f"  {'-'*19} {'-'*19} {'-'*4} {'-'*5} {'-'*15} {'-'*8} {'-'*8} {'-'*5} {'-'*8} {'-'*10} {'-'*7} {'-'*10}  ----  ------")
    for t in trades:
        entry_date_str = str(t["entry_date"])[:19] if t["entry_date"] else "—"
        exit_date_str  = str(t["exit_date"])[:19]
        if t["entry_date"] and t["exit_date"]:
            entry_dt = t["entry_date"] if isinstance(t["entry_date"], datetime) else datetime.fromisoformat(str(t["entry_date"])[:19])
            exit_dt  = t["exit_date"]  if isinstance(t["exit_date"],  datetime) else datetime.fromisoformat(str(t["exit_date"])[:19])
            hold_str = str((exit_dt - entry_dt).days)
        else:
            hold_str = "—"
        bars_str = str(t.get("held_candles", "—"))
        invested = t["entry"] * t["qty"]
        pnl_pct_str = f"{t['pnl'] / invested * 100:+.2f}%" if invested else "—"
        cap_str = f"₹{capital_at_entry[id(t)]:,.0f}"
        print(
            f"  {entry_date_str:<19} {exit_date_str:<19} {hold_str:>4} {bars_str:>5} {t['instrument']:<15} "
            f"{t['entry']:>8.2f} {t['exit']:>8.2f} {t['qty']:>5} "
            f"₹{t.get('cost', 0.0):>7,.2f} ₹{t['pnl']:>9,.2f} {pnl_pct_str:>7} {cap_str:>10}  "
            f"{t.get('product','CNC'):<4}  {t['reason']}"
        )

    mr = m.get("monthly_returns", {})
    if mr:
        print(f"  {'─'*W}")
        print(f"  Monthly P&L:")
        for month, data in mr.items():
            bar_width = int(abs(data['pnl']) / max(abs(v['pnl']) for v in mr.values()) * 20) if mr else 0
            sign = "+" if data['pnl'] >= 0 else "-"
            bar = ("█" * bar_width) if data['pnl'] >= 0 else ("░" * bar_width)
            print(f"    {month}  {sign}₹{abs(data['pnl']):>8,.0f}  ({data['return_pct']:+.2f}%)  {bar}  [{data['trades']}t]")


    C = 28  # width of each column (excluding separator)
    col1 = [
        f"{'Trades':<12}: {m['total_trades']}",
        f"{'W / L':<12}: {m['wins']} / {m['losses']}",
        f"{'Win Rate':<12}: {m['win_rate']:.1f}%",
        f"{'Wt. Win%':<12}: {m['money_weighted_win_rate']:.1f}%",
        f"{'Avg Win':<12}: ₹{m['avg_win']:,.2f}",
        f"{'Avg Loss':<12}: ₹{m['avg_loss']:,.2f}",
        f"{'Prof.Factor':<12}: {m['profit_factor']:.2f}",
    ]
    col2 = [
        f"{'Total costs':<12}: ₹{total_costs:,.2f}",
        f"{'Total P&L':<12}: ₹{m['total_pnl']:,.2f}",
        f"{'Return':<12}: {m['return_pct']:.2f}%",
        f"{'Max DD':<12}: ₹{m['max_drawdown']:,.0f}  ({m['max_drawdown_pct']:.1f}%)",
    ]
    col3 = [
        f"{'Sharpe*':<8}: {m['sharpe_proxy']:.3f}",
        f"{'Sortino':<8}: {m['sortino_ratio']:.3f}",
        f"{'Calmar':<8}: {m['calmar_ratio']:.3f}",
    ]
    n = max(len(col1), len(col2), len(col3))
    col1 += [""] * (n - len(col1))
    col2 += [""] * (n - len(col2))
    col3 += [""] * (n - len(col3))

    print(f"\n  {'─'*(C*3+6)}")
    for a, b, c in zip(col1, col2, col3):
        print(f"  {a:<{C}}  │  {b:<{C}}  │  {c}")

    from collections import defaultdict
    reason_stats: dict[str, dict] = defaultdict(lambda: {"count": 0, "pnl": 0.0, "wins": 0, "held": 0})
    for t in trades:
        r = t.get("reason", "UNKNOWN")
        reason_stats[r]["count"] += 1
        reason_stats[r]["pnl"] += t["pnl"]
        reason_stats[r]["held"] += t.get("held_candles", 0)
        if t["pnl"] > 0:
            reason_stats[r]["wins"] += 1
    print(f"  {'─'*W}")
    print(f"  Exit reasons:                              avg_bars")
    max_count = max(s["count"] for s in reason_stats.values()) if reason_stats else 1
    for reason in ["SL", "TRAILING", "STAGNATION", "MODEL_EXIT", "PATTERN_TOP", "TARGET", "STRATEGY", "OPEN@END"]:
        if reason not in reason_stats:
            continue
        s = reason_stats[reason]
        bar = "█" * int(s["count"] / max_count * 20)
        wr = s["wins"] / s["count"] * 100
        avg_bars = s["held"] / s["count"]
        print(f"    {reason:<12} {s['count']:>3}t  wr:{wr:4.0f}%  ₹{s['pnl']:>9,.0f}  {bar:<20}  {avg_bars:>5.0f}b")

    # Per-stock exit breakdown — one line per instrument
    _REASON_ABBREV = {
        "SL": "SL", "TRAILING": "TRL", "PATTERN_TOP": "PAT",
        "STRATEGY": "STR", "TARGET": "TGT", "OPEN@END": "END",
        "STAGNATION": "STG", "MODEL_EXIT": "MOD",
    }
    def _fmt_pnl(v: float) -> str:
        if abs(v) >= 1000:
            return f"{'+'if v>=0 else '-'}₹{abs(v)/1000:.1f}k"
        return f"{'+'if v>=0 else ''}₹{v:.0f}"

    per_stock: dict[str, dict] = defaultdict(lambda: defaultdict(lambda: {"count": 0, "pnl": 0.0}))
    for t in trades:
        per_stock[t["instrument"]][t.get("reason", "UNKNOWN")]["count"] += 1
        per_stock[t["instrument"]][t.get("reason", "UNKNOWN")]["pnl"] += t["pnl"]

    _REASON_ORDER = ["SL", "TRAILING", "STAGNATION", "MODEL_EXIT", "PATTERN_TOP", "TARGET", "STRATEGY", "OPEN@END"]
    print(f"  {'─'*W}")
    print(f"  Per-stock exits:")
    for sym, reasons in sorted(per_stock.items()):
        total_t = sum(r["count"] for r in reasons.values())
        sym_short = sym.replace("NSE:", "")
        parts = []
        for reason in _REASON_ORDER:
            if reason not in reasons:
                continue
            abbr = _REASON_ABBREV.get(reason, reason[:3])
            cnt = reasons[reason]["count"]
            pnl = reasons[reason]["pnl"]
            parts.append(f"{abbr}×{cnt}({_fmt_pnl(pnl)})")
        for reason in sorted(set(reasons) - set(_REASON_ORDER)):
            abbr = _REASON_ABBREV.get(reason, reason[:3])
            cnt = reasons[reason]["count"]
            pnl = reasons[reason]["pnl"]
            parts.append(f"{abbr}×{cnt}({_fmt_pnl(pnl)})")
        print(f"    {sym_short:<16} {total_t:>3}t  {'  '.join(parts)}")

    print(f"  {'='*W}\n")



def _dump_csv(trades: list[dict], from_date: str, to_date: str):
    if not trades:
        return
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    from_str = from_date.replace("-", "")
    to_str = to_date.replace("-", "")
    timeframe = config.candle_timeframe.replace("minute", "m").replace("day", "1d")
    filename = f"portfolio_{from_str}_{to_str}_{timeframe}_{now}.csv"
    out_path = Path(__file__).resolve().parents[1] / "backtest_results" / filename
    fields = ["instrument", "entry_date", "exit_date", "entry", "exit", "qty",
              "cost", "pnl", "product", "reason", "held_candles", "sl", "peak_high"]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(trades)
    print(f"  CSV saved : {out_path}")


if __name__ == "__main__":
    main()
