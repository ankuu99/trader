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

    print(f"\n  {'─'*W}")
    print(f"  Trades       : {m['total_trades']}  (W:{m['wins']}  L:{m['losses']})")
    print(f"  Win Rate     : {m['win_rate']:.1f}%  (count)   Wt. Win%: {m['money_weighted_win_rate']:.1f}%  (by ₹)")
    print(f"  Avg Win      : ₹{m['avg_win']:>10,.2f}    Avg Loss : ₹{m['avg_loss']:>10,.2f}")
    print(f"  Profit Factor: {m['profit_factor']:.2f}")
    print(f"  {'─'*W}")
    print(f"  Total costs  : ₹{total_costs:,.2f}")
    print(f"  Total P&L    : ₹{m['total_pnl']:,.2f}  (net of costs)")
    print(f"  Return       : {m['return_pct']:.2f}%")
    print(f"  Max DD       : ₹{m['max_drawdown']:,.2f}  ({m['max_drawdown_pct']:.2f}% of capital)")
    print(f"  {'─'*W}")
    print(f"  Sharpe*      : {m['sharpe_proxy']:.3f}")
    print(f"  Sortino      : {m['sortino_ratio']:.3f}")
    print(f"  Calmar       : {m['calmar_ratio']:.3f}")

    mr = m.get("monthly_returns", {})
    if mr:
        print(f"  {'─'*W}")
        print(f"  Monthly P&L:")
        for month, data in mr.items():
            bar_width = int(abs(data['pnl']) / max(abs(v['pnl']) for v in mr.values()) * 20) if mr else 0
            sign = "+" if data['pnl'] >= 0 else "-"
            bar = ("█" * bar_width) if data['pnl'] >= 0 else ("░" * bar_width)
            print(f"    {month}  {sign}₹{abs(data['pnl']):>8,.0f}  ({data['return_pct']:+.2f}%)  {bar}  [{data['trades']}t]")

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
              "cost", "pnl", "product", "reason", "held_candles"]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(trades)
    print(f"  CSV saved : {out_path}")


if __name__ == "__main__":
    main()
