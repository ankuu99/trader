"""
VWAP Reversion Strategy (intraday)
------------------------------------
Buys when price dips below VWAP (below the day's average price), expecting
it to revert back up. Exits when price crosses back above VWAP.

VWAP resets at market open each day (9:15 AM IST).

Config keys (under strategies.vwap in config.yaml):
    (no required params — VWAP is purely price/volume derived)

Can also act as a filter: confirm_entry(BUY) is True when price is below VWAP,
meaning a buy signal from another strategy is supported by VWAP context.
"""

from datetime import datetime

from trader.core.logger import get_logger
from trader.strategies.base import Direction, Signal, SignalType, Strategy

logger = get_logger(__name__)


class VWAPReversionStrategy(Strategy):
    def __init__(self, instrument: str, params: dict):
        super().__init__(instrument, params)
        # Minimum % price must be below VWAP before triggering an entry.
        # Guards against noise-triggered signals on tiny VWAP crossovers.
        self._min_deviation_pct: float = float(params.get("min_deviation_pct", 0.3)) / 100

        self._cum_tp_vol: float = 0.0   # cumulative (typical_price * volume)
        self._cum_vol: float = 0.0      # cumulative volume
        self._vwap: float | None = None
        self._prev_close: float | None = None
        self._current_date = None

    @property
    def name(self) -> str:
        return "VWAP"

    def on_candle(self, candle: dict) -> Signal | None:
        ts: datetime = candle["timestamp"]
        candle_date = ts.date()

        # Reset cumulative sums at the start of each trading day
        if self._current_date != candle_date:
            self._current_date = candle_date
            self._cum_tp_vol = 0.0
            self._cum_vol = 0.0
            self._vwap = None
            self._prev_close = None

        high = candle["high"]
        low = candle["low"]
        close = candle["close"]
        volume = candle["volume"]

        typical_price = (high + low + close) / 3
        self._cum_tp_vol += typical_price * volume
        self._cum_vol += volume

        if self._cum_vol > 0:
            self._vwap = self._cum_tp_vol / self._cum_vol

        signal = self._evaluate(close)
        self._prev_close = close
        return signal

    def _evaluate(self, close: float) -> Signal | None:
        if self._vwap is None or self._prev_close is None:
            return None

        # Entry: price crosses from above VWAP to below VWAP AND is far enough below it
        deviation = (self._vwap - close) / self._vwap if self._vwap > 0 else 0
        if self.is_flat() and self._prev_close >= self._vwap and close < self._vwap \
                and deviation >= self._min_deviation_pct:
            logger.info(
                "VWAP ENTRY signal | %s | close=%.2f crossed below VWAP=%.2f"
                " (prev_close=%.2f deviation=%.2f%%)",
                self.instrument, close, self._vwap, self._prev_close, deviation * 100,
            )
            return Signal(
                instrument=self.instrument,
                direction=Direction.BUY,
                signal_type=SignalType.ENTRY,
                price_hint=close,
                strategy=self.name,
            )

        # Exit: price reverts above VWAP
        if self.position == Direction.BUY and self._prev_close < self._vwap and close >= self._vwap:
            logger.info(
                "VWAP EXIT signal | %s | close=%.2f crossed above VWAP=%.2f (prev_close=%.2f)",
                self.instrument, close, self._vwap, self._prev_close,
            )
            return Signal(
                instrument=self.instrument,
                direction=Direction.SELL,
                signal_type=SignalType.EXIT,
                price_hint=close,
                strategy=self.name,
            )

        return None

    def confirm_entry(self, direction: Direction) -> bool:
        """True when price is currently below VWAP (supports a mean-reversion buy)."""
        if self._vwap is None or self._prev_close is None:
            return False
        if direction == Direction.BUY:
            return self._prev_close < self._vwap
        return self._prev_close > self._vwap
