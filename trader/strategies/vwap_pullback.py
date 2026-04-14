"""
VWAP Pullback Continuation (intraday)
--------------------------------------
Enters long when a stock that is trending up (above SMA) pulls back to
touch the day's VWAP and then resumes its upward move.

Entry logic (three-step):
  1. Close is above the rolling sma_period SMA (trend filter — spans multiple days)
  2. Previous candle closed above VWAP; current candle's low touches VWAP
     AND close stays within vwap_touch_tolerance_pct of VWAP (didn't crash through)
     → record pullback_high = current candle's high, enter AWAITING_RESUME state
  3. A subsequent candle closes above pullback_high → BUY signal

Exit:
  - Close falls below VWAP (lost trend support)

This is distinct from VWAPReversionStrategy, which buys dips below VWAP
expecting mean reversion. This strategy requires a pre-existing uptrend and
enters only on trend continuation, not reversal.

Note on SMA: the rolling SMA is NOT reset at day boundaries — it spans multiple
trading days to function as a meaningful trend filter. The VWAP, pullback state,
and prev_close ARE reset each day since they are intraday-scoped.

Config keys (under strategies.vwap_pullback in config.yaml):
    sma_period               : SMA period (default 50; 50 × 5min ≈ 4hrs of price history
                               that accumulates across days until warm)
    vwap_touch_tolerance_pct : proximity to VWAP that counts as a touch (default 0.2)
"""

from collections import deque
from datetime import datetime

from trader.core.logger import get_logger
from trader.strategies.base import Direction, Signal, SignalType, Strategy

logger = get_logger(__name__)

_WATCHING = "watching"
_AWAITING_RESUME = "awaiting_resume"


class VWAPPullbackStrategy(Strategy):
    def __init__(self, instrument: str, params: dict):
        super().__init__(instrument, params)
        self._sma_period: int = int(params.get("sma_period", 50))
        self._vwap_touch_tol: float = float(params.get("vwap_touch_tolerance_pct", 0.2)) / 100

        # VWAP accumulators — reset each trading day
        self._cum_tp_vol: float = 0.0
        self._cum_vol: float = 0.0
        self._vwap: float | None = None
        self._current_date = None

        # Trend SMA — rolling window across days (NOT reset daily)
        self._close_window: deque = deque(maxlen=self._sma_period)
        self._sma: float | None = None

        # Intraday pullback state — reset at day boundary
        self._state: str = _WATCHING
        self._pullback_high: float | None = None
        self._prev_close: float | None = None

    @property
    def name(self) -> str:
        return f"VWAPPullback({self._sma_period})"

    def on_candle(self, candle: dict) -> Signal | None:
        ts: datetime = candle["timestamp"]
        candle_date = ts.date()

        # Reset VWAP and intraday state at day boundary
        if self._current_date != candle_date:
            self._current_date = candle_date
            self._cum_tp_vol = 0.0
            self._cum_vol = 0.0
            self._vwap = None
            self._state = _WATCHING
            self._pullback_high = None
            self._prev_close = None

        close = candle["close"]
        high = candle["high"]
        low = candle["low"]
        volume = candle["volume"]

        # Update VWAP
        typical_price = (high + low + close) / 3
        self._cum_tp_vol += typical_price * volume
        self._cum_vol += volume
        if self._cum_vol > 0:
            self._vwap = self._cum_tp_vol / self._cum_vol

        # Update SMA (persists across days)
        self._close_window.append(close)
        if len(self._close_window) >= self._sma_period:
            self._sma = sum(self._close_window) / len(self._close_window)

        signal = self._evaluate(candle)
        self._prev_close = close
        return signal

    def _evaluate(self, candle: dict) -> Signal | None:
        if self._vwap is None or self._sma is None or self._prev_close is None:
            return None

        close = candle["close"]
        high = candle["high"]
        low = candle["low"]

        # EXIT: position open and close falls below VWAP
        if self.position == Direction.BUY:
            if close < self._vwap:
                logger.info(
                    "VWAPPullback EXIT | %s | close=%.2f < VWAP=%.2f",
                    self.instrument, close, self._vwap,
                )
                return Signal(
                    instrument=self.instrument,
                    direction=Direction.SELL,
                    signal_type=SignalType.EXIT,
                    price_hint=close,
                    strategy=self.name,
                )
            return None

        # ENTRY LOGIC (flat only)
        if not self.is_flat():
            return None

        # Trend gate: must be above SMA
        if close < self._sma:
            if self._state == _AWAITING_RESUME:
                self._state = _WATCHING
                self._pullback_high = None
            return None

        if self._state == _WATCHING:
            # Detect VWAP touch: previous close was above VWAP,
            # this candle's low touched VWAP but close didn't crash through
            if self._prev_close > self._vwap and self._is_vwap_touch(low, close):
                self._state = _AWAITING_RESUME
                self._pullback_high = high
                logger.debug(
                    "VWAPPullback: VWAP touch detected on %s, pullback_high=%.2f",
                    self.instrument, high,
                )

        elif self._state == _AWAITING_RESUME:
            # Abandon if price fell too far below VWAP (pullback failed)
            if close < self._vwap * (1 - self._vwap_touch_tol * 3):
                self._state = _WATCHING
                self._pullback_high = None
                return None

            # Entry: close breaks above the pullback candle's high
            if self._pullback_high is not None and close > self._pullback_high:
                logger.info(
                    "VWAPPullback ENTRY | %s | close=%.2f > pullback_high=%.2f"
                    " (VWAP=%.2f SMA=%.2f)",
                    self.instrument, close, self._pullback_high, self._vwap, self._sma,
                )
                self._state = _WATCHING
                self._pullback_high = None
                return Signal(
                    instrument=self.instrument,
                    direction=Direction.BUY,
                    signal_type=SignalType.ENTRY,
                    price_hint=close,
                    strategy=self.name,
                )

        return None

    def _is_vwap_touch(self, low: float, close: float) -> bool:
        """
        True if the candle touched VWAP without closing far below it:
          - low reached VWAP or within the touch tolerance band above it
          - close stayed within the touch tolerance band of VWAP
        """
        return (
            low <= self._vwap * (1 + self._vwap_touch_tol)
            and close >= self._vwap * (1 - self._vwap_touch_tol)
        )
