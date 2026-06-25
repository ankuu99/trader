"""
ExtremaExitPolicy — the exit stack.

Moved verbatim from LRExtremaStrategy.on_candle / on_tick (Stage 3), preserving the
exact check order (first match wins) and all state mutations / display side-effects.

candle-speed (candle_exit): hold-bars timeout, stale tier 1/2, momentum-decay, and
pattern-top trailing *activation* (mutates state, never returns an exit itself).
tick-speed (tick_exit): force-EOD close, breakeven stop, hard stop-loss, trailing stop,
trailing floor.

The policy receives the strategy as context (reads its model/features/position state,
mutates PositionState, updates display fields). The parity golden enforces byte-identical
behaviour.
"""

from datetime import time

from trader.core.config import config
from trader.core.logger import get_logger
from trader.policy.base import ExitDecision

logger = get_logger(__name__)


def _parse_time(val, default: time) -> time:
    if val is None:
        return default
    h, m = str(val).split(":")
    return time(int(h), int(m))


class ExtremaExitPolicy:
    def __init__(self, params: dict):
        self._hold_bars: int = params.get("hold_bars", 150)
        self._profit_pct: float = params.get("profit_pct", 3.0)
        self._trail_pct: float = params.get("trail_pct", 1.5)
        self._stop_pct: float = params.get("stop_pct", 3.0)
        self._sell_threshold: float = params.get("sell_threshold", 0.65)
        self._sell_min_pct: float = params.get("sell_min_pct", 2.0)
        self._min_hold_before_exit: int = params.get("min_hold_before_exit", 3)
        # Master switch for ALL trailing (fixed-percent activation + pattern-top
        # trailing). Default True = unchanged behaviour.
        self._trailing_enabled: bool = bool(params.get("trailing_enabled", True))
        # When True, a pattern-top fires an immediate EXIT at the candle close
        # instead of arming trailing — "exit exactly where the model says".
        self._pattern_top_direct_exit: bool = bool(params.get("pattern_top_direct_exit", False))
        # Confidence-sized trailing (Step 1): when enabled, the trailing distance is
        # interpolated from the model's live P(max) — loose (trail_loose) while no top
        # is suspected, tightening to trail_tight once P(max) >= p_hi. Falls back to the
        # static trail_pct when disabled.
        self._trail_conf_enabled: bool = bool(params.get("trail_conf_enabled", False))
        self._trail_loose: float = float(params.get("trail_loose", self._trail_pct))
        self._trail_tight: float = float(params.get("trail_tight", self._trail_pct))
        self._trail_conf_p_lo: float = float(params.get("trail_conf_p_lo", 0.5))
        self._trail_conf_p_hi: float = float(params.get("trail_conf_p_hi", 0.9))
        # Scale-out (Step 2): on a pattern-top, sell a fraction and trail the rest.
        self._scale_out_enabled: bool = bool(params.get("pattern_top_scale_out_enabled", False))
        self._scale_out_fraction: float = float(params.get("pattern_top_scale_out_fraction", 0.5))

        self._stale_exit_enabled: bool = bool(params.get("stale_exit_enabled", False))
        self._stale_check_bars: int = int(params.get("stale_check_bars", 20))
        self._stale_min_gain_pct: float = float(params.get("stale_min_gain_pct", 0.5))
        self._stale_exit_2_enabled: bool = bool(params.get("stale_exit_2_enabled", False))
        self._stale_check_bars_2: int = int(params.get("stale_check_bars_2", 80))
        self._stale_min_gain_pct_2: float = float(params.get("stale_min_gain_pct_2", 0.0))

        self._breakeven_stop_enabled: bool = bool(params.get("breakeven_stop_enabled", False))
        self._breakeven_trigger_pct: float = float(params.get("breakeven_trigger_pct", 1.0))
        self._breakeven_buffer_pct: float = float(params.get("breakeven_buffer_pct", 0.0))

        self._momentum_exit_enabled: bool = bool(params.get("momentum_exit_enabled", False))
        self._momentum_exit_p_min_floor: float = float(params.get("momentum_exit_p_min_floor", 0.35))
        self._momentum_exit_min_bars: int = int(params.get("momentum_exit_min_bars", 5))

        self._pattern_top_floor_enabled: bool = bool(params.get("pattern_top_floor_enabled", True))

        _ftic = params.get("force_trailing_close_time")
        self._force_trailing_close = _parse_time(_ftic, time(15, 25)) if _ftic else None

    def _effective_trail_pct(self, strat) -> float:
        """Trailing distance for the current bar. Static (trail_pct) unless
        confidence-sizing is enabled, in which case it interpolates between
        trail_loose (at/below p_lo) and trail_tight (at/above p_hi) using the
        model's latest P(max) — a firming top tightens the trail to lock gains."""
        if not self._trail_conf_enabled:
            return self._trail_pct
        p_max = getattr(strat, "_last_p_max", 0.0) or 0.0
        lo, hi = self._trail_conf_p_lo, self._trail_conf_p_hi
        f = 0.0 if hi <= lo else (p_max - lo) / (hi - lo)
        f = max(0.0, min(1.0, f))
        return self._trail_loose - (self._trail_loose - self._trail_tight) * f

    # ------------------------------------------------------------------
    # Candle-speed exits
    # ------------------------------------------------------------------

    def candle_exit(self, strat, candle: dict, close: float) -> ExitDecision | None:
        """Evaluate candle-granularity exits in order. Returns an ExitDecision to
        exit, or None (possibly after mutating pattern-top trailing state)."""
        pos = strat._pos
        ts = candle.get("timestamp")

        # --- Hold-bars timeout (candle-granularity time cap) ---
        if not strat.is_flat() and pos.held_bars >= self._hold_bars:
            logger.info(
                "LR-Extrema EXIT | %s | max hold (%d bars) | entry=%.2f close=%.2f | candle=%s",
                strat.instrument, pos.held_bars, pos.entry_price or 0, close, ts,
            )
            pos.reset()
            return ExitDecision(price_hint=close, exit_reason="STRATEGY", timestamp=ts)

        # --- Progress gate: track best gain, exit if stale ---
        _pct_gain = (
            (close - pos.entry_price) / pos.entry_price * 100.0
            if pos.entry_price else 0.0
        )
        if not strat.is_flat() and pos.entry_price is not None:
            if _pct_gain > pos.max_gain_pct:
                pos.max_gain_pct = _pct_gain

        if (self._stale_exit_enabled
                and not strat.is_flat()
                and pos.entry_price is not None
                and pos.held_bars >= self._stale_check_bars
                and pos.max_gain_pct < self._stale_min_gain_pct):
            logger.info(
                "LR-Extrema EXIT (stale) | %s | held=%d bars, best_gain=%.2f%% < %.2f%% | entry=%.2f close=%.2f | candle=%s",
                strat.instrument, pos.held_bars, pos.max_gain_pct, self._stale_min_gain_pct,
                pos.entry_price, close, ts,
            )
            pos.reset()
            return ExitDecision(price_hint=close, exit_reason="STALE", timestamp=ts)

        # Stale tier 2: at exactly stale_check_bars_2, exit if current gain still too low
        if (self._stale_exit_2_enabled
                and not strat.is_flat()
                and pos.entry_price is not None
                and pos.held_bars == self._stale_check_bars_2
                and _pct_gain < self._stale_min_gain_pct_2):
            logger.info(
                "LR-Extrema EXIT (stale-2) | %s | held=%d bars, gain=%.2f%% < %.2f%% | entry=%.2f close=%.2f | candle=%s",
                strat.instrument, pos.held_bars, _pct_gain, self._stale_min_gain_pct_2,
                pos.entry_price, close, ts,
            )
            pos.reset()
            return ExitDecision(price_hint=close, exit_reason="STALE", timestamp=ts)

        # --- Momentum-decay exit (model lost confidence in the bottom thesis) ---
        if (self._momentum_exit_enabled
                and not strat.is_flat()
                and strat._model.is_trained
                and pos.entry_price is not None
                and pos.held_bars >= self._momentum_exit_min_bars
                and _pct_gain < self._sell_min_pct):
            x = strat._features.compute(strat._candles)
            if x is not None:
                p_min, _ = strat._model.predict_proba(x)
                if p_min < self._momentum_exit_p_min_floor:
                    logger.info(
                        "LR-Extrema EXIT (momentum-decay) | %s | P(min)=%.3f < %.3f | gain=%.2f%% | held=%d | candle=%s",
                        strat.instrument, p_min, self._momentum_exit_p_min_floor,
                        _pct_gain, pos.held_bars, ts,
                    )
                    pos.reset()
                    return ExitDecision(price_hint=close, exit_reason="MOMENTUM_DECAY", timestamp=ts)

        # --- Pattern-top detection: activates trailing, never exits directly ---
        if (not strat.is_flat() and strat._model.is_trained
                and pos.held_bars >= self._min_hold_before_exit
                and _pct_gain >= self._sell_min_pct):
            x = strat._features.compute(strat._candles)
            if x is not None:
                p_min, p_max = strat._model.predict_proba(x)
                strat._last_p_min = p_min
                strat._last_p_max = p_max
                if p_max >= self._sell_threshold:
                    strat.signal_log.append({
                        "timestamp": ts,
                        "close": close,
                        "p_min": p_min,
                        "p_max": p_max,
                        "type": "PATTERN_TOP",
                    })
                    # Scale-out mode: sell a fraction now, arm trailing on the rest.
                    # Fires once per position (partial_taken guard).
                    if self._scale_out_enabled and not pos.partial_taken:
                        # Arm trailing so the remainder rides with downside protection.
                        if self._trailing_enabled and not pos.trailing_active:
                            pos.trailing_active = True
                            if pos.peak_close is None:
                                pos.peak_close = close
                        pos.pattern_top_trailing = True
                        pos.partial_taken = True
                        logger.info(
                            "LR-Extrema EXIT (pattern-top scale-out %.0f%%) | %s | P(max)=%.3f >= %.3f | "
                            "gain=%.2f%% | held=%d | close=%.2f | candle=%s",
                            self._scale_out_fraction * 100, strat.instrument, p_max,
                            self._sell_threshold, _pct_gain, pos.held_bars, close, ts,
                        )
                        return ExitDecision(price_hint=close, exit_reason="PATTERN_TOP_PARTIAL",
                                            timestamp=ts, exit_fraction=self._scale_out_fraction)
                    # Direct-exit mode: exit at this candle close, no trailing.
                    if self._pattern_top_direct_exit:
                        logger.info(
                            "LR-Extrema EXIT (pattern-top direct) | %s | P(max)=%.3f >= %.3f | "
                            "gain=%.2f%% | held=%d | close=%.2f | candle=%s",
                            strat.instrument, p_max, self._sell_threshold, _pct_gain,
                            pos.held_bars, close, ts,
                        )
                        pos.reset()
                        return ExitDecision(price_hint=close, exit_reason="PATTERN_TOP", timestamp=ts)
                    if self._trailing_enabled and not pos.pattern_top_trailing:
                        if not pos.trailing_active:
                            pos.trailing_active = True
                            if pos.peak_close is None:
                                pos.peak_close = close
                        pos.pattern_top_trailing = True
                        logger.info(
                            "LR-Extrema PATTERN-TOP TRAILING | %s | P(max)=%.3f >= %.3f | price=%.2f | candle=%s",
                            strat.instrument, p_max, self._sell_threshold, close, ts,
                        )

        return None

    # ------------------------------------------------------------------
    # Tick-speed exits
    # ------------------------------------------------------------------

    def tick_exit(self, strat, tick: dict, last_price: float) -> ExitDecision | None:
        """Evaluate tick-granularity exits. Assumes the caller has already checked
        position/window/last_price guards. Mutates trailing/peak/breakeven state."""
        pos = strat._pos

        # Update high-water mark
        if pos.peak_close is None or last_price > pos.peak_close:
            pos.peak_close = last_price

        # Activate trailing once minimum profit floor is reached
        pct = (last_price - pos.entry_price) / pos.entry_price * 100.0
        if self._trailing_enabled and not pos.trailing_active and pct >= self._profit_pct:
            pos.trailing_active = True
            logger.info(
                "LR-Extrema TRAILING activated | %s | pct=+%.2f%% >= floor=%.2f%% | peak=%.2f",
                strat.instrument, pct, self._profit_pct, pos.peak_close,
            )

        # Force close trailing positions before overnight gap risk (tick-level precision)
        if pos.trailing_active and self._force_trailing_close is not None:
            _tick_ts = tick.get("timestamp")
            _tick_time = _tick_ts.time() if hasattr(_tick_ts, "time") else None
            if _tick_time is not None and _tick_time >= self._force_trailing_close:
                logger.info(
                    "LR-Extrema TRAILING EOD CLOSE | %s | price=%.2f",
                    strat.instrument, last_price,
                )
                pos.reset()
                return ExitDecision(price_hint=last_price, exit_reason="TRAILING_EOD_CLOSE")

        # Breakeven stop — arm once trigger_pct gain is reached
        if self._breakeven_stop_enabled and not pos.breakeven_active and pct >= self._breakeven_trigger_pct:
            pos.breakeven_active = True
            logger.info(
                "LR-Extrema BREAKEVEN armed | %s | pct=+%.2f%% >= trigger=%.2f%% | floor=entry+%.2f%%",
                strat.instrument, pct, self._breakeven_trigger_pct, self._breakeven_buffer_pct,
            )

        # `reason` is the human-readable log string; `reason_code` is the exit
        # reason recorded on the signal (and shown in the UI). Both set together.
        reason: str | None = None
        reason_code: str | None = None
        if self._breakeven_stop_enabled and pos.breakeven_active:
            be_floor = pos.entry_price * (1.0 + self._breakeven_buffer_pct / 100.0)
            if last_price <= be_floor:
                reason = f"breakeven stop price={last_price:.2f} <= floor={be_floor:.2f}"
                reason_code = "BREAKEVEN"
        if reason is None and pct <= -self._stop_pct:
            reason = f"stop-loss {pct:.2f}%"
            reason_code = "SL"
        elif reason is None and pos.trailing_active:
            drawdown = (last_price - pos.peak_close) / pos.peak_close * 100.0
            trail_dist = self._effective_trail_pct(strat)
            if drawdown <= -trail_dist:
                reason = f"trailing stop {drawdown:.2f}% from peak {pos.peak_close:.2f} (dist={trail_dist:.2f}%)"
                reason_code = "TRAILING"
        # Trailing floor — pattern-top trailing uses sell_min_pct as floor; regular uses profit_pct.
        _use_floor = (not pos.pattern_top_trailing) or self._pattern_top_floor_enabled
        _floor_pct = self._sell_min_pct if pos.pattern_top_trailing else self._profit_pct
        if reason is None and pos.trailing_active and _use_floor and pct < _floor_pct:
            reason = f"trailing floor pct={pct:.2f}% < {_floor_pct:.2f}%"
            reason_code = "TRAILING"

        if reason:
            logger.info(
                "LR-Extrema EXIT (tick) | %s | %s | entry=%.2f price=%.2f",
                strat.instrument, reason, pos.entry_price, last_price,
            )
            pos.reset()
            return ExitDecision(price_hint=last_price, exit_reason=reason_code,
                                timestamp=tick.get("timestamp"))

        return None
