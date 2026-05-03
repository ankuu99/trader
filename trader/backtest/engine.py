"""
Backtest engine — core replay loop shared by backtest.py, calibrate.py, and screen.py.

    from trader.backtest.engine import run_backtest, compute_metrics

    trades = run_backtest(kite, store, symbols, symbol_to_token, params, from_dt, to_dt)
    metrics = compute_metrics(trades, capital)
"""

import math
from datetime import datetime, timedelta

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
        status = update.get("status")
        instrument = update["instrument"]

        # CANCELLED: unfilled LIMIT order expired at day boundary.
        # Release capital and clear strategy entry guard so next day's signals fire.
        if status == "CANCELLED":
            risk.on_order_cancelled(instrument)
            s = strategy_map.get(instrument)
            if s:
                s.on_order_update(update)
            return

        if status != "COMPLETE":
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
                "held_candles": pos.get("candle_count", 0),
            })
            risk.close_position(instrument, fill_price)
            s = strategy_map.get(instrument)
            if s:
                s.on_order_update(update)
            return

        # BUY fill — open new position
        sl_price = update.get("trigger_price") or 0.0
        # When trailing stop is configured there is no fixed profit target —
        # the exit is dynamic and managed via on_tick. Set target=0 to disable
        # the engine's intrabar target check; hard SL intrabar check is kept.
        _trailing = "trail_pct" in params
        if _trailing:
            target = 0.0
        else:
            target = (
                update.get("target_price")
                or round(fill_price + (fill_price - sl_price) * config.risk_reward, 2)
            )
        # Guard: if signal was generated at a different price than fill (e.g. gap
        # open), SL may be stale. Rebase from fill_price using strategy's own pct.
        if fill_price > 0 and (sl_price <= 0 or sl_price >= fill_price):
            stop_pct = params.get("stop_pct", 3.0) / 100
            sl_price = round(fill_price * (1 - stop_pct), 2)
            if not _trailing:
                profit_pct = params.get("profit_pct", 3.0) / 100
                target = round(fill_price * (1 + profit_pct), 2)
            logger.debug(
                "SL rebased to fill price | %s | fill=%.2f sl=%.2f",
                instrument, fill_price, sl_price,
            )
        open_positions[instrument] = {
            "entry": fill_price,
            "sl": sl_price,
            "target": target,
            "qty": quantity,
            "entry_date": current_ts[0],
            "candle_count": 0,
        }
        risk.on_order_filled(instrument, fill_price, quantity)
        s = strategy_map.get(instrument)
        if s:
            s.on_order_update(update)

    orders.register_update_callback(handle_order_update)

    # Pre-warmup window: enough history before from_dt to fully train the model.
    # Must be fetched BEFORE the main [from_dt, to_dt] fetch so the cache is
    # populated in chronological order — otherwise get_candles sees cached_latest
    # pointing past from_dt and skips the pre-warmup range entirely.

    pre_warmup_days = config.historical_cache_days
    pre_warmup_from = from_dt - timedelta(days=pre_warmup_days)

    # --- Fetch pre-warmup candles first (DB empty at this point) ---
    pre_warmup_candles: dict[str, list[dict]] = {}
    for symbol in symbols:
        token = symbol_to_token.get(symbol)
        if token is None:
            continue
        pre_df = get_candles(
            kite, store, token, symbol, config.candle_timeframe,
            pre_warmup_from, from_dt - timedelta(minutes=1),
        )
        if pre_df.empty:
            logger.info("No pre-warmup candles for %s before %s — model will be cold", symbol, from_dt.date())
            continue
        pre_warmup_candles[symbol] = [
            {
                "instrument_token": token,
                "timestamp": row["timestamp"],
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"]),
                "_symbol": symbol,
            }
            for _, row in pre_df.iterrows()
        ]
        logger.info(
            "Pre-warmup fetched | %s | %d candles over %d days before %s",
            symbol, len(pre_df), pre_warmup_days, from_dt.date(),
        )

    # --- Fetch main backtest candles (cache now has pre-warmup data) ---
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

    # Replay pre-warmup candles through each strategy (no trade recording)
    for symbol, strategy in strategy_map.items():
        warmup_feed = pre_warmup_candles.get(symbol, [])
        for candle in warmup_feed:
            strategy.on_candle(candle)
        if warmup_feed:
            logger.info("Pre-warmup complete | %s | %d candles", symbol, len(warmup_feed))

    # Clear phantom entry state left by signals that fired during pre-warmup
    # but never received a fill (no orders are placed during warmup).
    # Without this, the first real candle triggers a phantom EXIT that consumes
    # the signal without placing a trade — causing missing trades vs a wider window.
    for strategy in strategy_map.values():
        if getattr(strategy, "_entry_price", None) is not None and strategy.position is None:
            logger.debug("Clearing phantom pre-warmup entry state | %s", strategy.instrument)
            strategy._entry_price = None
            strategy._held_bars = 0
            strategy._peak_close = None
            strategy._trailing_active = False

    prev_date = None
    for candle in merged_candles:
        symbol = candle["_symbol"]
        current_ts[0] = candle["timestamp"]
        candle_date = candle["timestamp"].date()

        # Simulate Zerodha's EOD LIMIT order cancellation: unfilled LIMIT orders
        # are cancelled at day boundary, not carried forward to the next session.
        if prev_date is not None and candle_date != prev_date:
            if config.order_type == "LIMIT":
                orders.clear_pending()
            # Reset daily P&L and halt state so a daily-loss-limit breach on one
            # day doesn't permanently halt the rest of the backtest.
            risk.reset_day()
        prev_date = candle_date

        orders.on_candle(candle)

        # Increment candle counter for the open position on this symbol.
        # Done after order fill so the entry candle itself counts as 1.
        if symbol in open_positions:
            open_positions[symbol]["candle_count"] += 1

        # Intrabar SL/target simulation — always active in backtest.
        # Checks candle low/high against stored SL/target prices so exits fire
        # at the correct price rather than slipping to the next candle's open.
        # Skip the fill candle itself — GTT is disabled so same-candle entry+exit
        # cannot happen in live trading (strategy only sees exits on closed candles).
        if symbol in open_positions and current_ts[0] != open_positions[symbol]["entry_date"]:
            pos = open_positions[symbol]
            sl_hit = pos["sl"] > 0 and candle["low"] <= pos["sl"]
            tgt_hit = pos["target"] > 0 and candle["high"] >= pos["target"]
            if sl_hit or tgt_hit:
                if sl_hit and tgt_hit:
                    # Both levels spanned by this candle — use proximity to open as heuristic
                    sl_dist = abs(candle["open"] - pos["sl"])
                    tgt_dist = abs(candle["open"] - pos["target"])
                    reason = "SL" if sl_dist <= tgt_dist else "TARGET"
                elif sl_hit:
                    reason = "SL"
                else:
                    reason = "TARGET"
                # Gap-adjusted fill: if the candle opened through the SL/target level
                # (overnight gap), fill at the open price — the SL/target price was never
                # tradeable. For intraday hits (open is on the safe side), use the exact level.
                if reason == "SL":
                    exit_price = min(pos["sl"], candle["open"])
                else:
                    exit_price = max(pos["target"], candle["open"])
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
                    "held_candles": pos.get("candle_count", 0),
                })
                del open_positions[symbol]
                risk.close_position(symbol, exit_price)
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

        # Trailing stop simulation via on_tick.
        # Feed candle high first (updates _peak_close), then close (checks trail).
        # Hard SL is already handled intrabar above; if it fired, strategy state
        # is already reset and on_tick returns None safely.
        if symbol in open_positions:
            for tick_price in (candle["high"], candle["close"]):
                tick_signal = strategy.on_tick({
                    "last_price": tick_price,
                    "instrument_token": candle.get("instrument_token"),
                })
                if tick_signal is not None:
                    pos = open_positions.pop(symbol)
                    exit_price = candle["close"]
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
                        "reason": "TRAILING",
                        "entry_date": pos["entry_date"],
                        "exit_date": candle["timestamp"],
                        "held_candles": pos.get("candle_count", 0),
                    })
                    risk.close_position(symbol, exit_price)
                    strategy.on_order_update({
                        "status": "COMPLETE",
                        "instrument": symbol,
                        "direction": "SELL",
                        "signal_type": "EXIT",
                        "quantity": pos["qty"],
                        "price": exit_price,
                        "fill_price": exit_price,
                    })
                    break

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
            "held_candles": pos.get("candle_count", 0),
        })

    return trades


def compute_metrics(trades: list[dict], capital: float) -> dict:
    """
    Compute summary metrics from a trades list.

    Returns dict with:
        total_trades, wins, losses, win_rate (0-100),
        total_pnl, return_pct, avg_win, avg_loss, sharpe_proxy,
        max_drawdown (absolute ₹), max_drawdown_pct (% of capital)

    sharpe_proxy = mean(pnl) / std(pnl) across trades — useful for relative
    ranking only, not a true Sharpe ratio. Labelled "Sharpe*" in output.

    max_drawdown = largest peak-to-trough decline in the cumulative P&L equity
    curve, ordered by entry_date. Represents the worst losing streak experienced.
    """
    if not trades:
        return {
            "total_trades": 0, "wins": 0, "losses": 0,
            "win_rate": 0.0, "money_weighted_win_rate": 0.0,
            "total_pnl": 0.0, "return_pct": 0.0,
            "avg_win": 0.0, "avg_loss": 0.0, "sharpe_proxy": 0.0,
            "max_drawdown": 0.0, "max_drawdown_pct": 0.0,
        }

    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    total_pnl = sum(pnls)

    mean_pnl = total_pnl / len(pnls)
    variance = sum((p - mean_pnl) ** 2 for p in pnls) / len(pnls)
    std_pnl = math.sqrt(variance)
    sharpe_proxy = mean_pnl / std_pnl if std_pnl > 0 else 0.0

    # Max drawdown — peak-to-trough on equity curve ordered by entry_date
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

    total_win_amt = sum(wins)
    total_loss_amt = abs(sum(losses))
    money_weighted_win_rate = (
        total_win_amt / (total_win_amt + total_loss_amt) * 100
        if (total_win_amt + total_loss_amt) > 0 else 0.0
    )

    return {
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(trades) * 100,
        "money_weighted_win_rate": money_weighted_win_rate,
        "total_pnl": total_pnl,
        "return_pct": total_pnl / capital * 100 if capital > 0 else 0.0,
        "avg_win": sum(wins) / len(wins) if wins else 0.0,
        "avg_loss": sum(losses) / len(losses) if losses else 0.0,
        "sharpe_proxy": sharpe_proxy,
        "max_drawdown": max_dd,
        "max_drawdown_pct": max_dd / capital * 100 if capital > 0 else 0.0,
    }
