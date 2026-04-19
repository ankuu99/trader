"""
Backtest runner — replays historical candles through the same pipeline as main.py.

    python scripts/backtest.py --from 2025-01-01
    python scripts/backtest.py --from 2025-01-01 --to 2025-12-31

Uses the same RiskManager, OrderManager (paper mode), and Strategy instances as live.
The only backtest-specific addition is SL simulation: checks candle low against the
stop-loss price placed with each order.
"""

import argparse
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

setup(log_dir=config.log_dir, level=config.log_level)
logger = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Backtest strategies on historical data")
    parser.add_argument("--from", dest="from_date", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", default=datetime.now().strftime("%Y-%m-%d"),
                        help="End date YYYY-MM-DD (default: today)")
    args = parser.parse_args()

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
    win_rate = len(wins) / len(trades) * 100


    total_costs = sum(t.get("cost", 0.0) for t in trades)
    print(f"\n  {'Entry Date':<19} {'Exit Date':<19} {'Instrument':<15} {'Entry':>8} {'Exit':>8} {'Qty':>5} {'Cost':>8} {'Net P&L':>10} {'P&L%':>7}  Prod  Reason")
    print(f"  {'-'*19} {'-'*19} {'-'*15} {'-'*8} {'-'*8} {'-'*5} {'-'*8} {'-'*10} {'-'*7}  ----  ------")
    for t in trades:
        entry_date_str = str(t["entry_date"])[:19] if t["entry_date"] else "—"
        exit_date_str  = str(t["exit_date"])[:19]
        cost_str = f"₹{t.get('cost', 0.0):,.2f}"
        pnl_str = f"₹{t['pnl']:,.2f}"
        invested = t["entry"] * t["qty"]
        pnl_pct_str = f"{t['pnl'] / invested * 100:+.2f}%" if invested else "—"
        prod = t.get("product", "CNC")
        print(
            f"  {entry_date_str:<19} {exit_date_str:<19} {t['instrument']:<15} "
            f"{t['entry']:>8.2f} {t['exit']:>8.2f} {t['qty']:>5} "
            f"{cost_str:>8} {pnl_str:>10} {pnl_pct_str:>7}  {prod:<4}  {t['reason']}"
        )
    print(f"\n  Trades     : {len(trades)}  (W:{len(wins)}  L:{len(losses)})")
    print(f"  Win rate   : {win_rate:.1f}%")
    print(f"  Total cost : ₹{total_costs:,.2f}")
    print(f"  Total P&L  : ₹{total_pnl:,.2f}  (net of costs)")
    print(f"  Return     : {total_pnl / config.total_capital * 100:.2f}%")

    if wins:
        avg_win = sum(t["pnl"] for t in wins) / len(wins)
        print(f"  Avg win    : ₹{avg_win:,.2f}")
    if losses:
        avg_loss = sum(t["pnl"] for t in losses) / len(losses)
        print(f"  Avg loss   : ₹{avg_loss:,.2f}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
