"""
RSI Strategy — buys when RSI crosses below the oversold threshold.

Entry only. Exit is handled externally via GTT stop-loss.

Config keys (under strategies.rsi in config.yaml):
    period   : RSI lookback period (default 14)
    oversold : RSI level to trigger BUY entry (default 30)
"""

from collections import deque

from trader.core.logger import get_logger
from trader.strategies.base import Direction, Signal, SignalType, Strategy

logger = get_logger(__name__)


class RSIStrategy(Strategy):
    def __init__(self, instrument: str, params: dict):
        super().__init__(instrument, params)
        self._period: int = params.get("period", 14)
        self._oversold: float = params.get("oversold", 30)
        self._closes: deque[float] = deque(maxlen=self._period + 1)
        self._prev_rsi: float | None = None

    @property
    def name(self) -> str:
        return f"RSI({self._period})"

    def on_candle(self, candle: dict) -> Signal | None:
        close = candle["close"]
        self._closes.append(close)

        if len(self._closes) < self._period + 1:
            return None

        rsi = self._compute_rsi()

        signal = None
        if self.is_flat() and self._prev_rsi is not None:
            if self._prev_rsi >= self._oversold and rsi < self._oversold:
                logger.info(
                    "RSI BUY signal | %s | RSI=%.1f crossed below oversold=%.1f",
                    self.instrument, rsi, self._oversold,
                )
                signal = Signal(
                    instrument=self.instrument,
                    direction=Direction.BUY,
                    signal_type=SignalType.ENTRY,
                    price_hint=close,
                    strategy=self.name,
                )

        self._prev_rsi = rsi
        return signal

    def _compute_rsi(self) -> float:
        closes = list(self._closes)
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        avg_gain = sum(d for d in deltas if d > 0) / self._period
        avg_loss = sum(-d for d in deltas if d < 0) / self._period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
