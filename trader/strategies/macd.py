"""
MACD Strategy — buys when MACD line crosses above the signal line.

Entry only. Exit is handled externally via GTT stop-loss.

Config keys (under strategies.macd in config.yaml):
    fast   : fast EMA period (default 12)
    slow   : slow EMA period (default 26)
    signal : signal line EMA period (default 9)
"""

from collections import deque

from trader.core.logger import get_logger
from trader.strategies.base import Direction, Signal, SignalType, Strategy

logger = get_logger(__name__)


class MACDStrategy(Strategy):
    def __init__(self, instrument: str, params: dict):
        super().__init__(instrument, params)
        self._fast: int = params.get("fast", 12)
        self._slow: int = params.get("slow", 26)
        self._signal_period: int = params.get("signal", 9)
        self._closes: deque[float] = deque(maxlen=self._slow + self._signal_period)
        self._macd_history: deque[float] = deque(maxlen=self._signal_period)
        self._prev_macd: float | None = None
        self._prev_signal: float | None = None

    @property
    def name(self) -> str:
        return f"MACD({self._fast},{self._slow},{self._signal_period})"

    def on_candle(self, candle: dict) -> Signal | None:
        close = candle["close"]
        self._closes.append(close)

        if len(self._closes) < self._slow:
            return None

        macd_val = self._ema(list(self._closes), self._fast) - self._ema(list(self._closes), self._slow)
        self._macd_history.append(macd_val)

        if len(self._macd_history) < self._signal_period:
            return None

        sig_val = self._ema(list(self._macd_history), self._signal_period)

        signal = None
        if (self.is_flat()
                and self._prev_macd is not None
                and self._prev_signal is not None
                and self._prev_macd <= self._prev_signal
                and macd_val > sig_val):
            logger.info(
                "MACD BUY signal | %s | MACD=%.4f crossed above Signal=%.4f",
                self.instrument, macd_val, sig_val,
            )
            signal = Signal(
                instrument=self.instrument,
                direction=Direction.BUY,
                signal_type=SignalType.ENTRY,
                price_hint=close,
                strategy=self.name,
            )

        self._prev_macd = macd_val
        self._prev_signal = sig_val
        return signal

    @staticmethod
    def _ema(values: list[float], period: int) -> float:
        data = values[-period:]
        if not data:
            return 0.0
        k = 2 / (period + 1)
        ema = data[0]
        for price in data[1:]:
            ema = price * k + ema * (1 - k)
        return ema
