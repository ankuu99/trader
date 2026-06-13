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
            return ExitDecision(price_hint=close, timestamp=ts)

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
                    if not pos.pattern_top_trailing:
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
        if not pos.trailing_active and pct >= self._profit_pct:
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

        reason: str | None = None
        if self._breakeven_stop_enabled and pos.breakeven_active:
            be_floor = pos.entry_price * (1.0 + self._breakeven_buffer_pct / 100.0)
            if last_price <= be_floor:
                reason = f"breakeven stop price={last_price:.2f} <= floor={be_floor:.2f}"
        if reason is None and pct <= -self._stop_pct:
            reason = f"stop-loss {pct:.2f}%"
        elif reason is None and pos.trailing_active:
            drawdown = (last_price - pos.peak_close) / pos.peak_close * 100.0
            if drawdown <= -self._trail_pct:
                reason = f"trailing stop {drawdown:.2f}% from peak {pos.peak_close:.2f}"
        # Trailing floor — pattern-top trailing uses sell_min_pct as floor; regular uses profit_pct.
        _use_floor = (not pos.pattern_top_trailing) or self._pattern_top_floor_enabled
        _floor_pct = self._sell_min_pct if pos.pattern_top_trailing else self._profit_pct
        if reason is None and pos.trailing_active and _use_floor and pct < _floor_pct:
            reason = f"trailing floor pct={pct:.2f}% < {_floor_pct:.2f}%"

        if reason:
            logger.info(
                "LR-Extrema EXIT (tick) | %s | %s | entry=%.2f price=%.2f",
                strat.instrument, reason, pos.entry_price, last_price,
            )
            pos.reset()
            return ExitDecision(price_hint=last_price, timestamp=tick.get("timestamp"))

        return None
