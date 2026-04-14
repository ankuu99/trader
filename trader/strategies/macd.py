"""
MACD Strategy (Moving Average Convergence Divergence)
------------------------------------------------------
- MACD line  = EMA(fast) − EMA(slow)
- Signal line = EMA(signal_period) of MACD values
- ENTRY BUY : MACD line crosses above Signal line (while flat)
- EXIT      : MACD line crosses below Signal line (while long)
- Also implements confirm_entry() so it can act as a filter in a StrategyGroup.

Works on any timeframe; suitable for both intraday (5-min) and interday (daily).

Config keys (under strategies.macd in config yaml):
    fast   : fast EMA period (default 12)
    slow   : slow EMA period (default 26)
    signal : Signal line EMA period (default 9)
"""

from collections import deque

from trader.core.logger import get_logger
from trader.strategies.base import Direction, Signal, SignalType, Strategy

logger = get_logger(__name__)


class MACDStrategy(Strategy):
    def __init__(self, instrument: str, params: dict):
        super().__init__(instrument, params)
        self._fast_period: int = params.get("fast", 12)
        self._slow_period: int = params.get("slow", 26)
        self._signal_period: int = params.get("signal", 9)

        # Keep enough closes to seed the slow EMA; MACD history seeds signal EMA
        self._closes: deque[float] = deque(maxlen=self._slow_period + self._signal_period)
        self._macd_history: deque[float] = deque(maxlen=self._signal_period)

        self._macd: float | None = None
        self._signal_line: float | None = None
        self._prev_macd: float | None = None
        self._prev_signal: float | None = None

    @property
    def name(self) -> str:
        return f"MACD({self._fast_period},{self._slow_period},{self._signal_period})"

    def on_candle(self, candle: dict) -> Signal | None:
        close = candle["close"]
        self._closes.append(close)

        if len(self._closes) < self._slow_period:
            return None  # not enough data to compute slow EMA

        fast_ema = self._ema(list(self._closes), self._fast_period)
        slow_ema = self._ema(list(self._closes), self._slow_period)
        macd_val = fast_ema - slow_ema
        self._macd_history.append(macd_val)

        if len(self._macd_history) < self._signal_period:
            return None  # not enough MACD values to compute signal line

        self._prev_macd = self._macd
        self._prev_signal = self._signal_line
        self._macd = macd_val
        self._signal_line = self._ema(list(self._macd_history), self._signal_period)

        return self._evaluate(close)

    def _evaluate(self, close: float) -> Signal | None:
        macd = self._macd
        sig = self._signal_line
        prev_macd = self._prev_macd
        prev_sig = self._prev_signal

        if None in (macd, sig, prev_macd, prev_sig):
            return None

        # Bullish crossover: MACD crosses above Signal line
        if self.is_flat() and prev_macd <= prev_sig and macd > sig:
            logger.info(
                "MACD ENTRY signal | %s | MACD=%.4f crossed above Signal=%.4f",
                self.instrument, macd, sig,
            )
            return Signal(
                instrument=self.instrument,
                direction=Direction.BUY,
                signal_type=SignalType.ENTRY,
                price_hint=close,
                strategy=self.name,
            )

        # Bearish crossover: MACD crosses below Signal line → exit long
        if self.position == Direction.BUY and prev_macd >= prev_sig and macd < sig:
            logger.info(
                "MACD EXIT signal | %s | MACD=%.4f crossed below Signal=%.4f",
                self.instrument, macd, sig,
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
        """True when MACD is above Signal line — usable as a trend filter in a StrategyGroup."""
        if self._macd is None or self._signal_line is None:
            return False
        if direction == Direction.BUY:
            return self._macd > self._signal_line
        return self._macd < self._signal_line

    @staticmethod
    def _ema(values: list[float], period: int) -> float:
        """EMA over the last `period` values using the standard smoothing formula."""
        data = values[-period:]
        if len(data) < period:
            return sum(data) / len(data)
        k = 2 / (period + 1)
        ema = data[0]
        for price in data[1:]:
            ema = price * k + ema * (1 - k)
        return ema
