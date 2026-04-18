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
from trader.core.config import config
from trader.core.logger import get_logger, setup
from trader.data.historical import get_candles
from trader.data.store import Store
from trader.orders.manager import OrderManager
from trader.risk.manager import RiskManager
from trader.strategies.registry import build_strategies

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

    risk = RiskManager()
    # kite=None is safe: OrderManager never calls kite in paper mode
    orders = OrderManager(kite=None, store=store, mode="paper")

    # Track open positions for SL simulation: { instrument: {entry, sl, qty, entry_date} }
    open_positions: dict[str, dict] = {}
    trades: list[dict] = []
    current_ts: list = [None]  # mutable container so the closure can read it

    def handle_order_update(update: dict):
        if update.get("status") != "COMPLETE":
            return
        instrument = update["instrument"]
        fill_price = update.get("fill_price") or update.get("price") or 0.0
        direction = update.get("direction", "BUY")
        quantity = update["quantity"]

        if direction == "SELL" and instrument in open_positions:
            # Strategy-driven exit fill
            pos = open_positions.pop(instrument)
            pnl = (fill_price - pos["entry"]) * pos["qty"]
            trades.append({
                "instrument": instrument,
                "entry": pos["entry"],
                "exit": fill_price,
                "qty": pos["qty"],
                "pnl": pnl,
                "reason": "STRATEGY",
                "entry_date": pos["entry_date"],
                "exit_date": current_ts[0],
            })
            risk.close_position(instrument)
            logger.info("BT STRATEGY exit | %s | exit=%.2f | pnl=%.2f", instrument, fill_price, pnl)
            return

        # BUY fill — open new position
        sl_price = update.get("trigger_price") or 0.0
        open_positions[instrument] = {
            "entry": fill_price,
            "sl": sl_price,
            "target": round(fill_price + (fill_price - sl_price) * config.risk_reward, 2),
            "qty": quantity,
            "entry_date": current_ts[0],
        }
        risk.on_order_filled(instrument, fill_price, quantity)
        logger.info(
            "BT fill | %s x%d @ %.2f | SL=%.2f target=%.2f",
            instrument, quantity, fill_price, sl_price, open_positions[instrument]["target"],
        )

    orders.register_update_callback(handle_order_update)

    strategies = []
    for symbol in valid_watchlist:
        strategies.extend(build_strategies(symbol, config))

    logger.info(
        "Backtest | %s to %s | instruments=%s | strategies=%d",
        args.from_date, args.to_date, valid_watchlist, len(strategies),
    )

    # Replay candles per instrument
    for symbol in valid_watchlist:
        token = symbol_to_token[symbol]
        df = get_candles(kite, store, token, symbol, config.candle_timeframe, from_dt, to_dt)

        if df.empty:
            logger.warning("No candles for %s in range %s – %s", symbol, args.from_date, args.to_date)
            continue

        logger.info("Replaying %d candles for %s", len(df), symbol)

        for _, row in df.iterrows():
            current_ts[0] = row["timestamp"]
            candle = {
                "instrument_token": token,
                "timestamp": row["timestamp"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"]),
                "_symbol": symbol,
            }

            # Fill any pending entry orders at this candle's open
            orders.on_candle(candle)

            # Simulate GTT OCO: check SL (low) and target (high) hits
            if config.gtt_enabled and symbol in open_positions:
                pos = open_positions[symbol]
                sl_hit = pos["sl"] > 0 and candle["low"] <= pos["sl"]
                tgt_hit = pos["target"] > 0 and candle["high"] >= pos["target"]
                if sl_hit or tgt_hit:
                    # If both hit in same candle, assume SL (conservative)
                    if sl_hit:
                        exit_price, reason = pos["sl"], "SL"
                    else:
                        exit_price, reason = pos["target"], "TARGET"
                    pnl = (exit_price - pos["entry"]) * pos["qty"]
                    trades.append({
                        "instrument": symbol,
                        "entry": pos["entry"],
                        "exit": exit_price,
                        "qty": pos["qty"],
                        "pnl": pnl,
                        "reason": reason,
                        "entry_date": pos["entry_date"],
                        "exit_date": candle["timestamp"],
                    })
                    del open_positions[symbol]
                    risk.close_position(symbol)
                    logger.info("BT %s | %s | exit=%.2f | pnl=%.2f", reason, symbol, exit_price, pnl)

            # Run strategies
            for strategy in strategies:
                if strategy.instrument != symbol:
                    continue
                signal = strategy.on_candle(candle)
                if signal is None:
                    continue
                order = risk.validate(signal)
                if order is None:
                    continue
                orders.place(order)

    # Close any remaining open positions at last known price
    for symbol, pos in list(open_positions.items()):
        last_close = pos["entry"]  # fallback if we can't get last price
        pnl = (last_close - pos["entry"]) * pos["qty"]  # 0 if same price
        trades.append({
            "instrument": symbol,
            "entry": pos["entry"],
            "exit": last_close,
            "qty": pos["qty"],
            "pnl": pnl,
            "reason": "OPEN@END",
            "entry_date": pos["entry_date"],
            "exit_date": to_dt,
        })

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


    print(f"\n  {'Entry Date':<19} {'Exit Date':<19} {'Instrument':<15} {'Entry':>8} {'Exit':>8} {'Qty':>5} {'P&L':>10} {'P&L%':>7}  Reason")
    print(f"  {'-'*19} {'-'*19} {'-'*15} {'-'*8} {'-'*8} {'-'*5} {'-'*10} {'-'*7}  ------")
    for t in trades:
        entry_date_str = str(t["entry_date"])[:19] if t["entry_date"] else "—"
        exit_date_str  = str(t["exit_date"])[:19]
        pnl_str = f"Rs.{t['pnl']:,.2f}"
        cost = t["entry"] * t["qty"]
        pnl_pct_str = f"{t['pnl'] / cost * 100:+.2f}%" if cost else "—"
        print(
            f"  {entry_date_str:<19} {exit_date_str:<19} {t['instrument']:<15} "
            f"{t['entry']:>8.2f} {t['exit']:>8.2f} {t['qty']:>5} "
            f"{pnl_str:>12} {pnl_pct_str:>7}  {t['reason']}"
        )
    print(f"\n  Trades     : {len(trades)}  (W:{len(wins)}  L:{len(losses)})")
    print(f"  Win rate   : {win_rate:.1f}%")
    print(f"  Total P&L  : ₹{total_pnl:,.2f}")
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
