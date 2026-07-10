"""
Backtest engine — core replay loop shared by backtest.py, calibrate.py, and screen.py.

    from trader.backtest.engine import run_backtest, compute_metrics

    trades = run_backtest(kite, store, symbols, symbol_to_token, params, from_dt, to_dt)
    metrics = compute_metrics(trades, capital)
"""

import bisect
import math
import time
from datetime import datetime, time as dtime, timedelta

from trader.core.config import config
from trader.core.logger import get_logger
from trader.costs import round_trip_cost
from trader.data.aggregator import BARS_PER_DAY, CandleAggregator
from trader.data.historical import get_candles
from trader.data.store import Store
from trader.features.indicators import htf_trend_regime
from trader.notifications import telegram as _telegram
from trader.orders.manager import OrderManager
from trader.risk.manager import RiskManager
from trader.strategies.lr_extrema import LRExtremaStrategy

_telegram.disable()  # backtest engine never sends live notifications

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
    per_symbol_params: dict[str, dict] | None = None,
    strategy_cls=None,
    model_scores: dict[str, list[dict]] | None = None,
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
        model_scores:     Optional sink dict — when provided, the engine appends
                          {timestamp, close, p_min, p_max} per strategy-TF bar per
                          symbol (via strategy.score_current(), pure — no state
                          side effects). In-memory only; the SQLite model_scores
                          table remains live-only. No cost when omitted.

    Returns:
        List of trade dicts with keys:
            instrument, entry, exit, qty, pnl, reason, entry_date, exit_date
    """
    risk = RiskManager()
    orders = OrderManager(kite=None, store=store, mode="paper")

    open_positions: dict[str, dict] = {}
    trades: list[dict] = []

    def _consume_lots(symbol: str, pos: dict, sell_qty: int, exit_price: float,
                      reason: str, exit_date) -> None:
        """FIFO-consume sell_qty shares from the position's lots, appending one
        trade record per lot slice (per-lot entry price/date → correct per-lot
        costs and MIS/CNC detection). Mutates pos['lots'] and pos['qty'].
        Used by every exit path: strategy SELL (full/partial), intrabar SL/target,
        tick trailing, and OPEN@END (the caller picks exit_price/reason)."""
        remaining = sell_qty
        while remaining > 0 and pos["lots"]:
            lot = pos["lots"][0]
            take = min(remaining, lot["qty"])
            net, cost, product = _net_pnl(
                lot["entry"], exit_price, take, lot["entry_date"], exit_date
            )
            trades.append({
                "instrument": symbol,
                "entry": lot["entry"],
                "exit": exit_price,
                "qty": take,
                "pnl": net,
                "cost": cost,
                "product": product,
                "reason": reason,
                "entry_date": lot["entry_date"],
                "exit_date": exit_date,
                "held_candles": lot.get("candle_count", 0),
                "addon_tier": lot.get("tier", 0),
            })
            lot["qty"] -= take
            remaining -= take
            if lot["qty"] == 0:
                pos["lots"].pop(0)
        pos["qty"] = max(0, pos["qty"] - sell_qty)
    current_ts: list = [None]
    pending_exit_reasons: dict[str, str] = {}  # symbol → exit reason for next strategy EXIT fill
    # Populated after candle fetch; closure captures by reference so handle_order_update
    # sees the final map even though it is defined first.
    strategy_map: dict[str, LRExtremaStrategy] = {}

    def _params_for(symbol: str) -> dict:
        if per_symbol_params and symbol in per_symbol_params:
            return per_symbol_params[symbol]
        return params

    def _tf_for(symbol: str) -> str:
        """Strategy decision timeframe — base feed TF unless overridden per-stock."""
        return _params_for(symbol).get("timeframe", config.candle_timeframe)

    def _warmup_days_for(symbol: str, default_days: int) -> int:
        """Calendar days of base-TF history needed to warm up this symbol's model.
        Aggregated TFs consume ~BARS_PER_DAY-fewer bars per day, so the fetch
        window is derived from (warmup_bars + lookback_bars) at the strategy TF."""
        tf = _tf_for(symbol)
        if tf == config.candle_timeframe or tf not in BARS_PER_DAY:
            return default_days
        p = _params_for(symbol)
        bars_needed = int(p.get("warmup_bars", 200)) + int(p.get("lookback_bars", 600))
        # ~1.45 calendar days per trading day (weekends + holidays)
        derived = math.ceil(bars_needed / BARS_PER_DAY[tf] * 1.45)
        return max(default_days, derived)

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
            pos = open_positions[instrument]
            # Partial (scale-out) fill: sold qty is less than the open qty — record the
            # sold portion as a trade, shrink the position, and keep it open. The
            # remainder exits later via trailing/hold/stale/hard-stop.
            is_partial = 0 < quantity < pos["qty"]
            sold_qty = quantity if is_partial else pos["qty"]
            _reason = pending_exit_reasons.pop(instrument, "STRATEGY")
            _consume_lots(instrument, pos, sold_qty, fill_price, _reason, current_ts[0])
            s = strategy_map.get(instrument)
            if is_partial:
                risk.reduce_position(instrument, sold_qty, fill_price)
                if s:
                    s.on_order_update({**update, "partial": True})
            else:
                open_positions.pop(instrument)
                risk.close_position(instrument, fill_price)
                if s:
                    s.on_order_update(update)
            return

        # BUY fill — scale-in add-on lot on an existing position: append the lot,
        # grow the blended qty, leave entry/SL/target and the parent candle_count
        # untouched (all exit anchors stay on the original entry).
        if update.get("addon") and instrument in open_positions:
            pos = open_positions[instrument]
            pos["lots"].append({
                "entry": fill_price, "qty": quantity, "entry_date": current_ts[0],
                "tier": len(pos["lots"]), "candle_count": 0,
            })
            pos["qty"] += quantity
            risk.on_order_filled(instrument, fill_price, quantity,
                                 addon=True, fill_ts=current_ts[0])
            s = strategy_map.get(instrument)
            if s:
                s.on_order_update(update)  # no-op for addon fills (state stays parent-anchored)
            return

        # BUY fill — open new position
        sl_price = update.get("trigger_price") or 0.0
        # When trailing stop is configured there is no fixed profit target —
        # the exit is dynamic and managed via on_tick. Set target=0 to disable
        # the engine's intrabar target check; hard SL intrabar check is kept.
        _sym_params = _params_for(instrument)
        _trailing = "trail_pct" in _sym_params
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
            stop_pct = _sym_params.get("stop_pct", 3.0) / 100
            sl_price = round(fill_price * (1 - stop_pct), 2)
            if not _trailing:
                profit_pct = _sym_params.get("profit_pct", 3.0) / 100
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
            # lots[0] = parent; scale-in add-ons append here. All exit paths emit
            # one trade record per lot via _consume_lots.
            "lots": [{"entry": fill_price, "qty": quantity,
                      "entry_date": current_ts[0], "tier": 0, "candle_count": 0}],
        }
        risk.on_order_filled(instrument, fill_price, quantity, fill_ts=current_ts[0])
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

    _bt_start = time.time()
    logger.info(
        "Backtest starting | symbols=%d | %s → %s | warmup=%d days",
        len(symbols), from_dt.date(), to_dt.date(), pre_warmup_days,
    )

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

    # --- Fetch 4h candles for the ht_trend gate (one series per symbol that has
    # the gate enabled — params and 4h closes are per-instrument, unlike NIFTY/VIX) ---
    _htf_regime_series: dict[str, tuple[list, list[dict]]] = {}
    for symbol in symbols:
        _sym_params = _params_for(symbol)
        if not _sym_params.get("ht_trend_gate_enabled"):
            continue
        token = symbol_to_token.get(symbol)
        if token is None:
            continue
        _htf_df = get_candles(kite, store, token, symbol, "4hour", pre_warmup_from, to_dt)
        if _htf_df.empty:
            logger.info("No 4h candles for %s — ht_trend gate will be neutral", symbol)
            continue

        _htf_closes = _htf_df["close"].astype(float).tolist()
        _htf_open_ts = _htf_df["timestamp"].tolist()

        _ht_rsi_period = _sym_params.get("ht_trend_rsi_period", 14)
        _ht_macd_fast = _sym_params.get("ht_trend_macd_fast", 12)
        _ht_macd_slow = _sym_params.get("ht_trend_macd_slow", 26)
        _ht_macd_signal = _sym_params.get("ht_trend_macd_signal_period", 9)
        _ht_macd_slope_ma = _sym_params.get("ht_trend_macd_slope_ma_period", 3)
        _ht_rsi_downtrend_max = _sym_params.get("ht_trend_rsi_downtrend_max", 50.0)
        _ht_rsi_oversold = _sym_params.get("ht_trend_rsi_oversold", 30.0)
        _ht_oversold_lookback = _sym_params.get("ht_trend_oversold_lookback", 6)
        _ht_min_bars = max(_ht_rsi_period + 1, _ht_macd_slow + _ht_macd_signal + _ht_macd_slope_ma)

        _close_times: list = []
        _regime_dicts: list[dict] = []
        for i in range(_ht_min_bars - 1, len(_htf_closes)):
            regime = htf_trend_regime(
                _htf_closes[: i + 1],
                rsi_period=_ht_rsi_period,
                macd_fast=_ht_macd_fast, macd_slow=_ht_macd_slow,
                macd_signal_period=_ht_macd_signal, macd_slope_ma_period=_ht_macd_slope_ma,
                rsi_downtrend_max=_ht_rsi_downtrend_max, rsi_oversold=_ht_rsi_oversold,
                oversold_lookback=_ht_oversold_lookback,
            )
            if regime is None:
                continue
            # NSE 4h bars open at 09:15 (closes 13:15) and 13:15 (closes at
            # market close 15:30, not 17:15) — fixed schedule, verified empirically.
            open_ts = _htf_open_ts[i]
            if open_ts.time() == dtime(9, 15):
                close_ts = open_ts + timedelta(hours=4)
            else:
                close_ts = open_ts + timedelta(hours=2, minutes=15)
            _close_times.append(close_ts)
            _regime_dicts.append(regime)

        _htf_regime_series[symbol] = (_close_times, _regime_dicts)
        logger.info("HTF regime series | %s | %d bars", symbol, len(_regime_dicts))

    def _htf_regime_at(symbol: str, ts) -> dict | None:
        """Return the most recent CLOSED 4h regime dict at or before *ts* (forward-fill).
        No-lookahead: a 4h bar's regime is only usable once that bar has closed."""
        series = _htf_regime_series.get(symbol)
        if not series:
            return None
        close_times, regime_dicts = series
        idx = bisect.bisect_right(close_times, ts) - 1
        return regime_dicts[idx] if idx >= 0 else None

    def _build_candle(row, token: int, symbol: str) -> dict:
        ts = row["timestamp"]
        _htf = _htf_regime_at(symbol, ts)
        return {
            "instrument_token": token,
            "timestamp": ts,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": int(row["volume"]),
            "_symbol": symbol,
            "_nifty_close": _regime_at(_nifty_ts, _nifty_cl, ts),
            "_vix_close":   _regime_at(_vix_ts,   _vix_cl,   ts),
            "_htf_rsi":        _htf["rsi"]        if _htf else None,
            "_htf_macd_hist":  _htf["macd_hist"]  if _htf else None,
            "_htf_macd_slope": _htf["macd_slope"] if _htf else None,
            "_htf_downtrend":  _htf["downtrend"]  if _htf else None,
            "_htf_inversion":  _htf["inversion"]  if _htf else None,
        }

    # Progress phases: 0-20% pre-warmup fetch, 20-35% main fetch,
    #                  35-45% warmup replay, 45-100% main replay loop.
    _n_sym = max(len(symbols), 1)

    def _phase_progress(label: str, pct: float):
        if progress_callback is not None:
            progress_callback(label, pct)

    # --- Fetch pre-warmup candles (DB empty at this point) ---
    # Window is per-symbol: aggregated-TF stocks (4hour/day) need far more
    # calendar depth to accumulate warmup_bars + lookback_bars at their TF.
    _fetch_start = time.time()
    pre_warmup_candles: dict[str, list[dict]] = {}
    for _i, symbol in enumerate(symbols):
        _phase_progress(f"Fetching warmup data: {symbol}", 0.20 * _i / _n_sym)
        token = symbol_to_token.get(symbol)
        if token is None:
            continue
        _sym_warmup_days = _warmup_days_for(symbol, pre_warmup_days)
        pre_df = get_candles(
            kite, store, token, symbol, config.candle_timeframe,
            from_dt - timedelta(days=_sym_warmup_days), from_dt - timedelta(minutes=1),
        )
        if pre_df.empty:
            logger.info("No pre-warmup candles for %s before %s — model will be cold", symbol, from_dt.date())
            continue
        pre_warmup_candles[symbol] = [_build_candle(row, token, symbol) for _, row in pre_df.iterrows()]
        logger.info(
            "Pre-warmup fetched | %s | %d candles over %d days before %s",
            symbol, len(pre_df), _sym_warmup_days, from_dt.date(),
        )

    logger.info("Pre-warmup fetch done | %.1fs", time.time() - _fetch_start)

    # --- Fetch main backtest candles (cache now has pre-warmup data) ---
    _main_fetch_start = time.time()
    symbol_candles: dict[str, list[dict]] = {}
    for _i, symbol in enumerate(symbols):
        _phase_progress(f"Fetching candles: {symbol}", 0.20 + 0.15 * _i / _n_sym)
        token = symbol_to_token.get(symbol)
        if token is None:
            logger.warning("No token for %s — skipping", symbol)
            continue
        df = get_candles(kite, store, token, symbol, config.candle_timeframe, from_dt, to_dt)
        if df.empty:
            logger.warning("No candles for %s in range %s – %s", symbol, from_dt.date(), to_dt.date())
            continue
        symbol_candles[symbol] = [_build_candle(row, token, symbol) for _, row in df.iterrows()]

    total_main_candles = sum(len(v) for v in symbol_candles.values())
    logger.info(
        "Main candle fetch done | %.1fs | %d symbols | %d total candles",
        time.time() - _main_fetch_start, len(symbol_candles), total_main_candles,
    )

    # Mark the last in-window candle of each trading day per symbol as the EOD bar.
    # Live force-closes active-trailing positions intraday (force_close_time, ~15:25),
    # but intraday candle timestamps are start-labelled (last 15m bar is 15:15 < 15:25),
    # so that force-close never fires from candle ticks. We flag the EOD bar here and
    # feed an extra tick stamped at trading_end on it (below) so the strategy's own
    # force-close logic triggers — keeping backtest in sync with live and preventing
    # trailing positions from riding overnight (which massively inflates P&L).
    for _clist in symbol_candles.values():
        _last_by_date: dict = {}
        for c in _clist:
            t = c["timestamp"].time()
            if config.trading_start <= t <= config.trading_end:
                _last_by_date[c["timestamp"].date()] = c  # chronological → last wins
        for c in _last_by_date.values():
            c["_is_eod"] = True

    merged_candles = sorted(
        (c for candles in symbol_candles.values() for c in candles),
        key=lambda c: c["timestamp"],
    )

    _strategy_cls = strategy_cls or LRExtremaStrategy
    strategy_map.update({symbol: _strategy_cls(symbol, _params_for(symbol)) for symbol in symbol_candles})

    # Per-symbol aggregators: None = passthrough (strategy runs on base candles).
    # Aggregated-TF strategies see composed bars; fills, intrabar SL/target and
    # tick simulation below stay on the base 15m stream.
    aggregator_map: dict[str, CandleAggregator | None] = {
        symbol: (CandleAggregator(_tf_for(symbol))
                 if _tf_for(symbol) != config.candle_timeframe else None)
        for symbol in symbol_candles
    }

    # Replay pre-warmup candles through each strategy (no trade recording).
    # Same aggregator instance as the main loop — a bucket left partially
    # filled at from_dt carries over seamlessly.
    _warmup_start = time.time()
    _n_strat = max(len(strategy_map), 1)
    for _i, (symbol, strategy) in enumerate(strategy_map.items()):
        _phase_progress(f"Warming up model: {symbol}", 0.35 + 0.10 * _i / _n_strat)
        warmup_feed = pre_warmup_candles.get(symbol, [])
        _agg = aggregator_map.get(symbol)
        for candle in warmup_feed:
            bar = candle if _agg is None else _agg.add(candle)
            if bar is not None:
                strategy.on_candle(bar)
        if warmup_feed:
            logger.info("Pre-warmup complete | %s | %d candles", symbol, len(warmup_feed))

    logger.info("Strategy warmup replay done | %.1fs", time.time() - _warmup_start)

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

    def _process_decision(symbol: str, bar: dict):
        """Run one strategy decision on a (base or aggregated) bar: signal →
        risk validation → order placement. Shared by the main loop and the
        day-boundary aggregator flush."""
        strategy = strategy_map.get(symbol)
        if strategy is None:
            return
        signal = strategy.on_candle(bar)
        # Per-candle model-score collection (UI explainability). score_current is
        # pure and position-independent, so this reflects the exact model the run
        # traded with — including its retrain cadence and warmup carry-over.
        if model_scores is not None:
            _score_fn = getattr(strategy, "score_current", None)
            _score = _score_fn() if _score_fn is not None else None
            if _score is not None:
                model_scores.setdefault(symbol, []).append({
                    "timestamp": bar.get("timestamp"),
                    "close": bar.get("close"),
                    "p_min": _score[0],
                    "p_max": _score[1],
                })
        if signal is None:
            return
        if signal.signal_type == "EXIT":
            reason = getattr(signal, "exit_reason", None)
            if reason:
                pending_exit_reasons[symbol] = reason
        order = risk.validate(signal)
        if order is None:
            return
        orders.place(order)

    _total_days = max((to_dt - from_dt).days, 1)
    _last_notified_date = None
    _last_logged_date = None
    _replay_start = time.time()
    logger.info("Replay starting | %d candles across %d symbols", len(merged_candles), len(strategy_map))
    prev_date = None
    for candle in merged_candles:
        symbol = candle["_symbol"]
        current_ts[0] = candle["timestamp"]
        candle_date = candle["timestamp"].date()

        if candle_date != _last_notified_date:
            _last_notified_date = candle_date
            _elapsed_days = max((candle_date - from_dt.date()).days, 0)
            _replay_pct = min(_elapsed_days / _total_days, 1.0)
            _phase_progress(str(candle_date), 0.45 + 0.55 * _replay_pct)
            # Log progress every 30 calendar days
            if _last_logged_date is None or (candle_date - _last_logged_date).days >= 30:
                _last_logged_date = candle_date
                _overall_pct = (0.45 + 0.55 * _replay_pct) * 100
                logger.info(
                    "Replay progress | %s | %.0f%% | %.1fs elapsed | trades so far: %d",
                    candle_date, _overall_pct, time.time() - _replay_start, len(trades),
                )

        # Simulate Zerodha's EOD LIMIT order cancellation: unfilled LIMIT orders
        # are cancelled at day boundary, not carried forward to the next session.
        if prev_date is not None and candle_date != prev_date:
            if config.order_type == "LIMIT":
                orders.clear_pending()
            # Reset daily P&L and halt state so a daily-loss-limit breach on one
            # day doesn't permanently halt the rest of the backtest.
            risk.reset_day()
            # Flush stale aggregator partials (missing last-member candle on the
            # previous day — the backtest analogue of the live ~15:16 clock
            # flush). Normal days emit on the last member; this is fallback only.
            for _fsym, _fagg in aggregator_map.items():
                if _fagg is None:
                    continue
                stale_bar = _fagg.flush()
                if stale_bar is not None:
                    _process_decision(_fsym, stale_bar)
        prev_date = candle_date

        orders.on_candle(candle)

        # Increment candle counter for the open position on this symbol.
        # Done after order fill so the entry candle itself counts as 1.
        if symbol in open_positions:
            open_positions[symbol]["candle_count"] += 1
            for _lot in open_positions[symbol]["lots"]:
                _lot["candle_count"] += 1

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
                _full_qty = pos["qty"]
                _consume_lots(symbol, pos, _full_qty, exit_price, reason, candle["timestamp"])
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
                        "quantity": _full_qty,
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
        #
        # On the EOD bar, append a third tick stamped at trading_end so the strategy's
        # force-close (force_close_time, e.g. 15:25) fires — intraday candle stamps top
        # out at 15:15 (< 15:25) so it never would otherwise, letting trailing positions
        # ride overnight in backtest only (live force-closes via real ticks). The EOD
        # tick is a no-op when force_close_time is disabled (None).
        _ticks = [(candle["high"], candle["timestamp"], False),
                  (candle["close"], candle["timestamp"], False)]
        if candle.get("_is_eod"):
            _eod_ts = datetime.combine(candle["timestamp"].date(), config.trading_end)
            _ticks.append((candle["close"], _eod_ts, True))
        if symbol in open_positions and _in_window and current_ts[0] != open_positions[symbol]["entry_date"]:
            for tick_price, tick_ts, _is_eod_tick in _ticks:
                if symbol not in open_positions:
                    break
                tick_signal = strategy.on_tick({
                    "last_price": tick_price,
                    "instrument_token": candle.get("instrument_token"),
                    "timestamp": tick_ts,
                })
                if tick_signal is not None:
                    pos = open_positions.pop(symbol)
                    # Intraday trail exits gap-adjust to the open; the EOD force-close
                    # fills at the closing price (the last tradeable price of the day).
                    exit_price = candle["close"] if _is_eod_tick else min(tick_price, candle["open"])
                    tick_reason = getattr(tick_signal, "exit_reason", None) or "TRAILING"
                    _full_qty = pos["qty"]
                    _consume_lots(symbol, pos, _full_qty, exit_price, tick_reason,
                                  candle["timestamp"])
                    risk.close_position(symbol, exit_price)
                    strategy.on_order_update({
                        "status": "COMPLETE",
                        "instrument": symbol,
                        "direction": "SELL",
                        "signal_type": "EXIT",
                        "quantity": _full_qty,
                        "price": exit_price,
                        "fill_price": exit_price,
                    })
                    break

        # Strategy decision — on the base candle (passthrough) or only when the
        # aggregator completes a higher-TF bar.
        _agg = aggregator_map.get(symbol)
        bar = candle if _agg is None else _agg.add(candle)
        if bar is None:
            continue
        _process_decision(symbol, bar)

    logger.info(
        "Replay done | %.1fs | %d trades",
        time.time() - _replay_start, len(trades),
    )

    # Close any remaining open positions at last known price
    for symbol, pos in list(open_positions.items()):
        last_close = pos["entry"]  # conservative: assume no price change from parent entry
        _consume_lots(symbol, pos, pos["qty"], last_close, "OPEN@END", to_dt)

    logger.info(
        "Backtest complete | total=%.1fs | %d trades | symbols=%d",
        time.time() - _bt_start, len(trades), len(symbols),
    )
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
        "total_pnl": 0.0, "return_pct": 0.0,
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

    # Calmar — annualised return / max drawdown %
    calmar_ratio = 0.0
    if max_dd_pct > 0 and capital > 0:
        try:
            all_dates = (
                [t["entry_date"] for t in trades if t.get("entry_date")]
                + [t["exit_date"] for t in trades if t.get("exit_date")]
            )
            if len(all_dates) >= 2:
                start_d = min(all_dates)
                end_d = max(all_dates)
                days = (end_d - start_d).days
                if days > 0:
                    years = days / 365.25
                    total_return = total_pnl / capital
                    cagr_pct = ((1 + total_return) ** (1 / years) - 1) * 100
                    calmar_ratio = cagr_pct / max_dd_pct
        except Exception:
            pass  # date subtraction failed — leave calmar at 0.0

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


# compute_utilisation moved to trader.analytics (pure, shared by UI + backtest).
# Re-exported here so existing `from trader.backtest.engine import compute_utilisation`
# callers keep working.
from trader.analytics import compute_utilisation  # noqa: E402,F401
