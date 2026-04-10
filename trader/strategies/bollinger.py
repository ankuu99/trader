"""
Bollinger Band Mean Reversion Strategy (intraday)
--------------------------------------------------
Trades when price stretches beyond the Bollinger Bands and then reverts
back toward the moving average.

Entry  (BUY) : close crosses below the lower band (oversold)
Exit (SELL)  : close crosses back above the middle band (SMA)

Config keys (under strategies.bollinger in config.yaml):
    period : SMA lookback period (default 20)
    std    : number of standard deviations for band width (default 2.0)

Can act as a filter: confirm_entry(BUY) is True when price is below the lower band.
"""

import math
from collections import deque

from trader.strategies.base import Direction, Signal, SignalType, Strategy


class BollingerBandStrategy(Strategy):
    def __init__(self, instrument: str, params: dict):
        super().__init__(instrument, params)
        self._period: int = params.get("period", 20)
        self._std_factor: float = float(params.get("std", 2.0))

        self._closes: deque[float] = deque(maxlen=self._period)
        self._middle: float | None = None
        self._lower: float | None = None
        self._upper: float | None = None
        self._prev_close: float | None = None

    @property
    def name(self) -> str:
        return f"BB({self._period},{self._std_factor})"

    def on_candle(self, candle: dict) -> Signal | None:
        close = candle["close"]
        self._closes.append(close)

        if len(self._closes) < self._period:
            self._prev_close = close
            return None

        closes = list(self._closes)
        self._middle = sum(closes) / self._period
        variance = sum((c - self._middle) ** 2 for c in closes) / self._period
        std = math.sqrt(variance)
        self._upper = self._middle + self._std_factor * std
        self._lower = self._middle - self._std_factor * std

        signal = self._evaluate(close)
        self._prev_close = close
        return signal

    def _evaluate(self, close: float) -> Signal | None:
        if self._lower is None or self._prev_close is None:
            return None

        # Entry: close crosses below lower band
        if self.is_flat() and self._prev_close >= self._lower and close < self._lower:
            return Signal(
                instrument=self.instrument,
                direction=Direction.BUY,
                signal_type=SignalType.ENTRY,
                price_hint=close,
                strategy=self.name,
            )

        # Exit: close crosses back above the middle band (SMA)
        if self.position == Direction.BUY and self._prev_close < self._middle and close >= self._middle:
            return Signal(
                instrument=self.instrument,
                direction=Direction.SELL,
                signal_type=SignalType.EXIT,
                price_hint=close,
                strategy=self.name,
            )

        return None

    def confirm_entry(self, direction: Direction) -> bool:
        """True when price is currently below the lower band (oversold)."""
        if self._lower is None or self._prev_close is None:
            return False
        if direction == Direction.BUY:
            return self._prev_close < self._lower
        if direction == Direction.SELL and self._upper is not None:
            return self._prev_close > self._upper
        return False
