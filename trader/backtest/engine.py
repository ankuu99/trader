"""
Backtest engine — core replay loop shared by backtest.py, calibrate.py, and screen.py.

    from trader.backtest.engine import run_backtest, compute_metrics

    trades = run_backtest(kite, store, symbols, symbol_to_token, params, from_dt, to_dt)
    metrics = compute_metrics(trades, capital)
"""

import math
from datetime import datetime

from trader.core.config import config
from trader.core.logger import get_logger
from trader.costs import round_trip_cost
from trader.data.historical import get_candles
from trader.data.store import Store
from trader.orders.manager import OrderManager
from trader.risk.manager import RiskManager
from trader.strategies.lr_extrema import LRExtremaStrategy

logger = get_logger(__name__)


def _net_pnl(entry_price: float, exit_price: float, qty: int,
             entry_date, exit_date) -> tuple[float, float, str]:
    """
    Returns (gross_pnl, cost, product) for a completed trade.

    Product is MIS if entry and exit are on the same calendar date (same-day
    square-off of a CNC position incurs intraday brokerage charges), otherwise CNC.
    """
    same_day = (
        entry_date is not None
        and exit_date is not None
        and str(entry_date)[:10] == str(exit_date)[:10]
    )
    product = "MIS" if same_day else "CNC"
    gross = (exit_price - entry_price) * qty
    cost = round_trip_cost(product=product, quantity=qty,
                           entry_price=entry_price, exit_price=exit_price)
    return gross - cost, cost, product


def run_backtest(
    kite,
    store: Store,
    symbols: list[str],
    symbol_to_token: dict,
    params: dict,
    from_dt: datetime,
    to_dt: datetime,
) -> list[dict]:
    """
    Replay historical candles through LRExtremaStrategy and return the trades list.

    Creates fresh RiskManager, OrderManager, and LRExtremaStrategy instances on
    every call — no state leaks between runs.

    Args:
        kite:             Authenticated KiteConnect instance (or None for cached-only runs)
        store:            Store instance for SQLite candle cache
        symbols:          List of instrument strings e.g. ["NSE:RELIANCE"]
        symbol_to_token:  Pre-built map from symbol string to Kite instrument token
        params:           LRExtremaStrategy parameter dict (bypasses registry)
        from_dt:          Backtest start datetime
        to_dt:            Backtest end datetime

    Returns:
        List of trade dicts with keys:
            instrument, entry, exit, qty, pnl, reason, entry_date, exit_date
    """
    risk = RiskManager()
    orders = OrderManager(kite=None, store=store, mode="paper")

    open_positions: dict[str, dict] = {}
    trades: list[dict] = []
    current_ts: list = [None]
    # Populated after candle fetch; closure captures by reference so handle_order_update
    # sees the final map even though it is defined first.
    strategy_map: dict[str, LRExtremaStrategy] = {}

    def handle_order_update(update: dict):
        if update.get("status") != "COMPLETE":
            return
        instrument = update["instrument"]
        fill_price = update.get("fill_price") or update.get("price") or 0.0
        direction = update.get("direction", "BUY")
        quantity = update["quantity"]

        if direction == "SELL" and instrument in open_positions:
            pos = open_positions.pop(instrument)
            net, cost, product = _net_pnl(
                pos["entry"], fill_price, pos["qty"], pos["entry_date"], current_ts[0]
            )
            trades.append({
                "instrument": instrument,
                "entry": pos["entry"],
                "exit": fill_price,
                "qty": pos["qty"],
                "pnl": net,
                "cost": cost,
                "product": product,
                "reason": "STRATEGY",
                "entry_date": pos["entry_date"],
                "exit_date": current_ts[0],
            })
            risk.close_position(instrument)
            s = strategy_map.get(instrument)
            if s:
                s.on_order_update(update)
            return

        # BUY fill — open new position
        sl_price = update.get("trigger_price") or 0.0
        target = (
            update.get("target_price")
            or round(fill_price + (fill_price - sl_price) * config.risk_reward, 2)
        )
        open_positions[instrument] = {
            "entry": fill_price,
            "sl": sl_price,
            "target": target,
            "qty": quantity,
            "entry_date": current_ts[0],
        }
        risk.on_order_filled(instrument, fill_price, quantity)
        s = strategy_map.get(instrument)
        if s:
            s.on_order_update(update)

    orders.register_update_callback(handle_order_update)

    # --- Fetch all candles upfront, then merge into one chronological stream ---
    symbol_candles: dict[str, list[dict]] = {}
    for symbol in symbols:
        token = symbol_to_token.get(symbol)
        if token is None:
            logger.warning("No token for %s — skipping", symbol)
            continue
        df = get_candles(kite, store, token, symbol, config.candle_timeframe, from_dt, to_dt)
        if df.empty:
            logger.warning("No candles for %s in range %s – %s", symbol, from_dt.date(), to_dt.date())
            continue
        symbol_candles[symbol] = [
            {
                "instrument_token": symbol_to_token[symbol],
                "timestamp": row["timestamp"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"]),
                "_symbol": symbol,
            }
            for _, row in df.iterrows()
        ]

    merged_candles = sorted(
        (c for candles in symbol_candles.values() for c in candles),
        key=lambda c: c["timestamp"],
    )

    strategy_map.update({symbol: LRExtremaStrategy(symbol, params) for symbol in symbol_candles})

    for candle in merged_candles:
        symbol = candle["_symbol"]
        current_ts[0] = candle["timestamp"]

        orders.on_candle(candle)

        # Intrabar SL/target simulation — always active in backtest.
        # Checks candle low/high against stored SL/target prices so exits fire
        # at the correct price rather than slipping to the next candle's open.
        if symbol in open_positions:
            pos = open_positions[symbol]
            sl_hit = pos["sl"] > 0 and candle["low"] <= pos["sl"]
            tgt_hit = pos["target"] > 0 and candle["high"] >= pos["target"]
            if sl_hit or tgt_hit:
                if sl_hit and tgt_hit:
                    # Both levels spanned by this candle — use proximity to open as heuristic
                    sl_dist = abs(candle["open"] - pos["sl"])
                    tgt_dist = abs(candle["open"] - pos["target"])
                    exit_price, reason = (pos["sl"], "SL") if sl_dist <= tgt_dist else (pos["target"], "TARGET")
                elif sl_hit:
                    exit_price, reason = pos["sl"], "SL"
                else:
                    exit_price, reason = pos["target"], "TARGET"
                net, cost, product = _net_pnl(
                    pos["entry"], exit_price, pos["qty"],
                    pos["entry_date"], candle["timestamp"]
                )
                trades.append({
                    "instrument": symbol,
                    "entry": pos["entry"],
                    "exit": exit_price,
                    "qty": pos["qty"],
                    "pnl": net,
                    "cost": cost,
                    "product": product,
                    "reason": reason,
                    "entry_date": pos["entry_date"],
                    "exit_date": candle["timestamp"],
                })
                del open_positions[symbol]
                risk.close_position(symbol)
                # Sync strategy state so it doesn't attempt a duplicate exit
                s = strategy_map.get(symbol)
                if s:
                    s.on_order_update({
                        "status": "COMPLETE",
                        "instrument": symbol,
                        "direction": "SELL",
                        "signal_type": "EXIT",
                        "quantity": pos["qty"],
                        "price": exit_price,
                        "fill_price": exit_price,
                    })

        strategy = strategy_map.get(symbol)
        if strategy is None:
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
        last_close = pos["entry"]  # conservative: assume no price change
        net, cost, product = _net_pnl(
            pos["entry"], last_close, pos["qty"], pos["entry_date"], to_dt
        )
        trades.append({
            "instrument": symbol,
            "entry": pos["entry"],
            "exit": last_close,
            "qty": pos["qty"],
            "pnl": net,
            "cost": cost,
            "product": product,
            "reason": "OPEN@END",
            "entry_date": pos["entry_date"],
            "exit_date": to_dt,
        })

    return trades


def compute_metrics(trades: list[dict], capital: float) -> dict:
    """
    Compute summary metrics from a trades list.

    Returns dict with:
        total_trades, wins, losses, win_rate (0-100),
        total_pnl, return_pct, avg_win, avg_loss, sharpe_proxy

    sharpe_proxy = mean(pnl) / std(pnl) across trades — useful for relative
    ranking only, not a true Sharpe ratio. Labelled "Sharpe*" in output.
    """
    if not trades:
        return {
            "total_trades": 0, "wins": 0, "losses": 0,
            "win_rate": 0.0, "total_pnl": 0.0, "return_pct": 0.0,
            "avg_win": 0.0, "avg_loss": 0.0, "sharpe_proxy": 0.0,
        }

    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    total_pnl = sum(pnls)

    mean_pnl = total_pnl / len(pnls)
    variance = sum((p - mean_pnl) ** 2 for p in pnls) / len(pnls)
    std_pnl = math.sqrt(variance)
    sharpe_proxy = mean_pnl / std_pnl if std_pnl > 0 else 0.0

    return {
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(trades) * 100,
        "total_pnl": total_pnl,
        "return_pct": total_pnl / capital * 100 if capital > 0 else 0.0,
        "avg_win": sum(wins) / len(wins) if wins else 0.0,
        "avg_loss": sum(losses) / len(losses) if losses else 0.0,
        "sharpe_proxy": sharpe_proxy,
    }
