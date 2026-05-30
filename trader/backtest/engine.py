"""
Backtest engine — core replay loop shared by backtest.py, calibrate.py, and screen.py.

    from trader.backtest.engine import run_backtest, compute_metrics

    trades = run_backtest(kite, store, symbols, symbol_to_token, params, from_dt, to_dt)
    metrics = compute_metrics(trades, capital)
"""

import bisect
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
    pre_warmup_days: int | None = None,
    progress_callback=None,
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
    pending_exit_reasons: dict[str, str] = {}  # symbol → exit reason for next strategy EXIT fill
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
                "reason": pending_exit_reasons.pop(instrument, "STRATEGY"),
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

    pre_warmup_days = pre_warmup_days if pre_warmup_days is not None else config.historical_cache_days
    pre_warmup_from = from_dt - timedelta(days=pre_warmup_days)

    # --- Fetch regime candles (NIFTY 50 + India VIX) for market context features ---
    # Must come BEFORE stock pre-warmup fetch so _regime_at is defined for injection.
    # Fetched once for the full window [pre_warmup_from, to_dt] then forward-filled
    # into every candle dict.  Gracefully skipped when tokens are unavailable.
    _regime_nifty_sym = params.get("regime_nifty_symbol", "NSE:NIFTY 50")
    _regime_vix_sym   = params.get("regime_vix_symbol",   "NSE:INDIA VIX")
    _nifty_ts: list = []
    _nifty_cl: list[float] = []
    _vix_ts: list = []
    _vix_cl: list[float] = []

    for _rsym, _rts, _rcl in (
        (_regime_nifty_sym, _nifty_ts, _nifty_cl),
        (_regime_vix_sym,   _vix_ts,   _vix_cl),
    ):
        _rtok = symbol_to_token.get(_rsym)
        if _rtok is None:
            logger.debug("Regime symbol %s not in token map — skipping", _rsym)
            continue
        _rdf = get_candles(kite, store, _rtok, _rsym, config.candle_timeframe,
                           pre_warmup_from, to_dt)
        if _rdf.empty:
            logger.info("No candles for regime symbol %s — regime features will be neutral", _rsym)
            continue
        _rts.extend(_rdf["timestamp"].tolist())
        _rcl.extend(_rdf["close"].astype(float).tolist())
        logger.info("Regime data | %s | %d candles", _rsym, len(_rdf))

    def _regime_at(ts_list: list, close_list: list[float], ts) -> float | None:
        """Return the most recent close at or before *ts* (forward-fill)."""
        if not ts_list:
            return None
        idx = bisect.bisect_right(ts_list, ts) - 1
        return close_list[idx] if idx >= 0 else None

    # --- Fetch pre-warmup candles (DB empty at this point) ---
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
                "_nifty_close": _regime_at(_nifty_ts, _nifty_cl, row["timestamp"]),
                "_vix_close":   _regime_at(_vix_ts,   _vix_cl,   row["timestamp"]),
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
                "_nifty_close": _regime_at(_nifty_ts, _nifty_cl, row["timestamp"]),
                "_vix_close":   _regime_at(_vix_ts,   _vix_cl,   row["timestamp"]),
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
            strategy._entry_stop = None
            strategy._held_bars = 0
            strategy._peak_close = None
            strategy._trailing_active = False

    _total_days = max((to_dt - from_dt).days, 1)
    _last_notified_date = None
    prev_date = None
    for candle in merged_candles:
        symbol = candle["_symbol"]
        current_ts[0] = candle["timestamp"]
        candle_date = candle["timestamp"].date()

        if progress_callback is not None and candle_date != _last_notified_date:
            _last_notified_date = candle_date
            _elapsed = max((candle_date - from_dt.date()).days, 0)
            progress_callback(candle_date, min(_elapsed / _total_days, 1.0))

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
        # Also skip candles outside the trading window — mirrors on_tick gate in live mode.
        _candle_time = candle["timestamp"].time()
        _in_window = config.trading_start <= _candle_time <= config.trading_end
        if symbol in open_positions and current_ts[0] != open_positions[symbol]["entry_date"] and _in_window:
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
                        "exit_reason": reason,  # "SL" or "TARGET" — used by strategy for cooldown
                        "quantity": pos["qty"],
                        "price": exit_price,
                        "fill_price": exit_price,
                    })

        strategy = strategy_map.get(symbol)
        if strategy is None:
            continue

        # Trailing stop simulation via on_tick.
        # Tick sequence: high → intrabar-low-check → close.
        # (1) high: updates _peak_close; may fire trailing if high < previous peak's floor.
        # (2) intrabar low check: if candle["low"] dips below the trailing floor after the
        #     high tick updated _peak_close, the trailing stop fires at the floor price.
        #     This prevents a systematic over-optimisation where PATTERN_TOP fires at close
        #     on candles where trailing would have already exited intraday.
        # (3) close: fires trailing if close ends below the floor (candle didn't recover).
        # Hard SL is already handled intrabar above; if it fired, strategy state
        # is already reset and on_tick returns None safely.
        if symbol in open_positions and _in_window and current_ts[0] != open_positions[symbol]["entry_date"]:
            _trail_pct_val = params.get("trail_pct", 0.0)
            _fired_tick_price: float | None = None
            _tick_signal_result = None

            # Capture the trailing state BEFORE the high tick updates _peak_close.
            # We use the old (pre-candle) peak to detect intrabar trailing hits that
            # occurred against a floor that was already set from previous candles.
            # This avoids the "high before low" assumption: we only fire intrabar if the
            # candle's low breaches a floor that was established BEFORE this candle started.
            _old_pk_for_intrabar = getattr(strategy, "_peak_close", None)
            _old_ta_for_intrabar = getattr(strategy, "_trailing_active", False)

            # --- Tick 1: high ---
            _tick_signal_result = strategy.on_tick({
                "last_price": candle["high"],
                "instrument_token": candle.get("instrument_token"),
                "timestamp": candle["timestamp"],
            })
            _fired_tick_price = candle["high"]

            # --- Tick 1.5: intrabar low trailing check (against PRE-CANDLE peak) ---
            # Fires when the candle's low breaches the trailing floor that existed at
            # candle open — i.e., the floor from a PREVIOUS candle's peak.
            # This is unambiguous: price definitely passed through that floor intraday
            # regardless of whether the high or low came first within this candle.
            # We do NOT use the post-high peak here, which would require assuming "high
            # before low" — an assumption we cannot verify from OHLC data alone.
            _intrabar_trail_fired = False
            if _tick_signal_result is None and _trail_pct_val > 0 and symbol in open_positions:
                if _old_ta_for_intrabar and _old_pk_for_intrabar is not None:
                    _old_trail_floor = _old_pk_for_intrabar * (1 - _trail_pct_val / 100)
                    if candle["low"] <= _old_trail_floor:
                        _tick_signal_result = strategy.on_tick({
                            "last_price": _old_trail_floor,
                            "instrument_token": candle.get("instrument_token"),
                            "timestamp": candle["timestamp"],
                        })
                        _fired_tick_price = _old_trail_floor
                        _intrabar_trail_fired = True

            # --- Tick 2: close ---
            if _tick_signal_result is None and symbol in open_positions:
                _tick_signal_result = strategy.on_tick({
                    "last_price": candle["close"],
                    "instrument_token": candle.get("instrument_token"),
                    "timestamp": candle["timestamp"],
                })
                _fired_tick_price = candle["close"]

            if _tick_signal_result is not None:
                pos = open_positions.pop(symbol)
                # Gap-adjust: if candle opened through the exit level, fill at open.
                # Exception: the intrabar trail floor was created by this candle's own high
                # (price path open→high→floor), so the open-gap adjustment doesn't apply —
                # the stop level was always achievable intraday regardless of where open was.
                if _intrabar_trail_fired:
                    exit_price = _fired_tick_price  # trail_floor, always achievable
                else:
                    exit_price = min(_fired_tick_price, candle["open"])
                tick_reason = getattr(_tick_signal_result, "exit_reason", None) or "TRAILING"
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
                    "reason": tick_reason,
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

        signal = strategy.on_candle(candle)
        if signal is None:
            continue
        if signal.signal_type == "EXIT":
            reason = getattr(signal, "exit_reason", None)
            if reason:
                pending_exit_reasons[symbol] = reason
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
        max_drawdown (absolute ₹), max_drawdown_pct (% of capital),
        profit_factor, sortino_ratio, calmar_ratio,
        monthly_returns {"YYYY-MM": {"pnl", "return_pct", "trades"}}

    sharpe_proxy = mean(pnl) / std(pnl) across trades — relative ranking only.
    sortino_ratio = mean(pnl) / downside_std — penalises losing trades only.
    calmar_ratio  = annualised_return_pct / max_drawdown_pct.
    profit_factor = total_wins / |total_losses|.
    """
    _empty: dict = {
        "total_trades": 0, "wins": 0, "losses": 0,
        "win_rate": 0.0, "money_weighted_win_rate": 0.0,
        "total_pnl": 0.0, "return_pct": 0.0, "annualized_return_pct": 0.0,
        "avg_win": 0.0, "avg_loss": 0.0, "sharpe_proxy": 0.0,
        "max_drawdown": 0.0, "max_drawdown_pct": 0.0,
        "profit_factor": 0.0, "sortino_ratio": 0.0, "calmar_ratio": 0.0,
        "monthly_returns": {},
    }
    if not trades:
        return _empty

    pnls = [t["pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    total_pnl = sum(pnls)

    mean_pnl = total_pnl / len(pnls)
    variance = sum((p - mean_pnl) ** 2 for p in pnls) / len(pnls)
    std_pnl = math.sqrt(variance)
    sharpe_proxy = mean_pnl / std_pnl if std_pnl > 0 else 0.0

    # Sortino — penalise downside only; use all n trades in denominator
    neg_pnls = [p for p in pnls if p < 0]
    if neg_pnls:
        downside_var = sum(p ** 2 for p in neg_pnls) / len(pnls)
        sortino_ratio = mean_pnl / math.sqrt(downside_var)
    else:
        sortino_ratio = 0.0  # no losses — undefined; 0 is a safe neutral value

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

    max_dd_pct = max_dd / capital * 100 if capital > 0 else 0.0

    # Annualised return (CAGR) and Calmar ratio
    annualized_return_pct = 0.0
    calmar_ratio = 0.0
    try:
        all_dates = (
            [t["entry_date"] for t in trades if t.get("entry_date")]
            + [t["exit_date"] for t in trades if t.get("exit_date")]
        )
        if len(all_dates) >= 2:
            start_d = min(all_dates)
            end_d = max(all_dates)
            days = (end_d - start_d).days
            if days > 0 and capital > 0:
                years = days / 365.25
                total_return = total_pnl / capital
                annualized_return_pct = ((1 + total_return) ** (1 / years) - 1) * 100
                if max_dd_pct > 0:
                    calmar_ratio = annualized_return_pct / max_dd_pct
    except Exception:
        pass  # date subtraction failed — leave at 0.0

    total_win_amt = sum(wins)
    total_loss_amt = abs(sum(losses))
    money_weighted_win_rate = (
        total_win_amt / (total_win_amt + total_loss_amt) * 100
        if (total_win_amt + total_loss_amt) > 0 else 0.0
    )
    profit_factor = total_win_amt / total_loss_amt if total_loss_amt > 0 else 0.0

    # Monthly returns — grouped by exit_date month
    monthly: dict[str, dict] = {}
    for t in trades:
        date = t.get("exit_date") or t.get("entry_date")
        if date is None:
            continue
        try:
            month_key = date.strftime("%Y-%m")
        except AttributeError:
            month_key = str(date)[:7]
        if month_key not in monthly:
            monthly[month_key] = {"pnl": 0.0, "trades": 0}
        monthly[month_key]["pnl"] += t["pnl"]
        monthly[month_key]["trades"] += 1
    monthly_returns = {
        k: {
            "pnl": v["pnl"],
            "return_pct": v["pnl"] / capital * 100 if capital > 0 else 0.0,
            "trades": v["trades"],
        }
        for k, v in sorted(monthly.items())
    }

    return {
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(trades) * 100,
        "money_weighted_win_rate": money_weighted_win_rate,
        "total_pnl": total_pnl,
        "return_pct": total_pnl / capital * 100 if capital > 0 else 0.0,
        "annualized_return_pct": annualized_return_pct,
        "avg_win": sum(wins) / len(wins) if wins else 0.0,
        "avg_loss": sum(losses) / len(losses) if losses else 0.0,
        "sharpe_proxy": sharpe_proxy,
        "max_drawdown": max_dd,
        "max_drawdown_pct": max_dd_pct,
        "profit_factor": profit_factor,
        "sortino_ratio": sortino_ratio,
        "calmar_ratio": calmar_ratio,
        "monthly_returns": monthly_returns,
    }
