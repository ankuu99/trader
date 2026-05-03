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
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")

from trader.auth.session import create_kite
from trader.backtest.engine import run_backtest
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
    args = parser.parse_args()
    if args.timeframe:
        config._data["candle_timeframe"] = args.timeframe

    from_dt = datetime.strptime(args.from_date, "%Y-%m-%d")
    to_dt = datetime.strptime(args.to_date, "%Y-%m-%d").replace(hour=23, minute=59)

    kite = create_kite()
    store = Store(config.db_path)
    store.clear_backtest_data()

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
    trades = run_backtest(kite, store, valid_watchlist, symbol_to_token, params, from_dt, to_dt)
    _print_summary(trades, args.from_date, args.to_date)
    _dump_csv(trades, args.from_date, args.to_date)


def _print_summary(trades: list[dict], from_date: str, to_date: str):
    print(f"\n{'='*55}")
    print(f"  Backtest: {from_date}  →  {to_date}")
    print(f"{'='*55}")

    if not trades:
        print("  No trades executed.")
        print(f"{'='*55}\n")
        return

    total_pnl = sum(t["pnl"] for t in trades)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    win_amt = sum(t["pnl"] for t in wins)
    loss_amt = abs(sum(t["pnl"] for t in losses))
    win_rate = win_amt / (win_amt + loss_amt) * 100 if (win_amt + loss_amt) > 0 else 0.0

    total_costs = sum(t.get("cost", 0.0) for t in trades)
    print(f"\n  {'Entry Date':<19} {'Exit Date':<19} {'Days':>4} {'Bars':>5} {'Instrument':<15} {'Entry':>8} {'Exit':>8} {'Qty':>5} {'Cost':>8} {'Net P&L':>10} {'P&L%':>7}  Prod  Reason")
    print(f"  {'-'*19} {'-'*19} {'-'*4} {'-'*5} {'-'*15} {'-'*8} {'-'*8} {'-'*5} {'-'*8} {'-'*10} {'-'*7}  ----  ------")
    for t in trades:
        entry_date_str = str(t["entry_date"])[:19] if t["entry_date"] else "—"
        exit_date_str  = str(t["exit_date"])[:19]
        if t["entry_date"] and t["exit_date"]:
            entry_dt = t["entry_date"] if isinstance(t["entry_date"], datetime) else datetime.fromisoformat(str(t["entry_date"])[:19])
            exit_dt  = t["exit_date"]  if isinstance(t["exit_date"],  datetime) else datetime.fromisoformat(str(t["exit_date"])[:19])
            hold_days = (exit_dt - entry_dt).days
            hold_str = str(hold_days)
        else:
            hold_str = "—"
        bars_str = str(t.get("held_candles", "—"))
        cost_str = f"₹{t.get('cost', 0.0):,.2f}"
        pnl_str = f"₹{t['pnl']:,.2f}"
        invested = t["entry"] * t["qty"]
        pnl_pct_str = f"{t['pnl'] / invested * 100:+.2f}%" if invested else "—"
        prod = t.get("product", "CNC")
        print(
            f"  {entry_date_str:<19} {exit_date_str:<19} {hold_str:>4} {bars_str:>5} {t['instrument']:<15} "
            f"{t['entry']:>8.2f} {t['exit']:>8.2f} {t['qty']:>5} "
            f"{cost_str:>8} {pnl_str:>10} {pnl_pct_str:>7}  {prod:<4}  {t['reason']}"
        )
    # Max drawdown — peak-to-trough on cumulative equity curve
    sorted_trades = sorted(trades, key=lambda t: t.get("entry_date") or "")
    cum_pnl = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in sorted_trades:
        cum_pnl += t["pnl"]
        if cum_pnl > peak:
            peak = cum_pnl
        dd = peak - cum_pnl
        if dd > max_dd:
            max_dd = dd
    max_dd_pct = max_dd / config.total_capital * 100

    print(f"\n  Trades     : {len(trades)}  (W:{len(wins)}  L:{len(losses)})")
    print(f"  Wt. Win%   : {win_rate:.1f}%")
    print(f"  Total cost : ₹{total_costs:,.2f}")
    print(f"  Total P&L  : ₹{total_pnl:,.2f}  (net of costs)")
    print(f"  Return     : {total_pnl / config.total_capital * 100:.2f}%")
    print(f"  Max DD     : ₹{max_dd:,.2f}  ({max_dd_pct:.2f}% of capital)")

    if wins:
        avg_win = sum(t["pnl"] for t in wins) / len(wins)
        print(f"  Avg win    : ₹{avg_win:,.2f}")
    if losses:
        avg_loss = sum(t["pnl"] for t in losses) / len(losses)
        print(f"  Avg loss   : ₹{avg_loss:,.2f}")
    print(f"{'='*55}\n")


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
