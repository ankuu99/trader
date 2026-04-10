"""
RSI Mean Reversion Strategy
----------------------------
- Buys when RSI crosses below the oversold threshold (default 30)
- Sells (exits) when RSI crosses above the overbought threshold (default 70)
- Only one position open at a time per instrument
- Exits the position when RSI reverts to the midpoint (default 50)

Config keys (under strategies.rsi in config.yaml):
    period     : RSI lookback period (default 14)
    oversold   : RSI level to trigger BUY entry (default 30)
    overbought : RSI level to trigger SELL exit (default 70)
    midpoint   : RSI level to trigger exit when in a position (default 50)
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
        self._overbought: float = params.get("overbought", 70)
        self._midpoint: float = params.get("midpoint", 50)

        # Rolling closes — we need period+1 to compute first RSI
        self._closes: deque[float] = deque(maxlen=self._period + 1)
        self._rsi: float | None = None
        self._prev_rsi: float | None = None

    @property
    def name(self) -> str:
        return f"RSI({self._period})"

    def on_candle(self, candle: dict) -> Signal | None:
        close = candle["close"]
        self._closes.append(close)

        if len(self._closes) < self._period + 1:
            return None  # not enough data yet

        self._prev_rsi = self._rsi
        self._rsi = self._compute_rsi()

        return self._evaluate()

    def _evaluate(self) -> Signal | None:
        rsi = self._rsi
        prev = self._prev_rsi

        if rsi is None or prev is None:
            return None

        # Entry: RSI crosses below oversold threshold and we are flat
        if self.is_flat() and prev >= self._oversold and rsi < self._oversold:
            logger.info(
                "RSI ENTRY signal | %s | RSI=%.1f crossed below oversold=%.1f (prev=%.1f)",
                self.instrument, rsi, self._oversold, prev,
            )
            return Signal(
                instrument=self.instrument,
                direction=Direction.BUY,
                signal_type=SignalType.ENTRY,
                price_hint=list(self._closes)[-1],
                strategy=self.name,
            )

        # Exit long: RSI reverts above midpoint
        if self.position == Direction.BUY and rsi >= self._midpoint:
            logger.info(
                "RSI EXIT signal | %s | RSI=%.1f crossed above midpoint=%.1f",
                self.instrument, rsi, self._midpoint,
            )
            return Signal(
                instrument=self.instrument,
                direction=Direction.SELL,
                signal_type=SignalType.EXIT,
                price_hint=list(self._closes)[-1],
                strategy=self.name,
            )

        return None

    def _compute_rsi(self) -> float:
        closes = list(self._closes)
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [d for d in deltas if d > 0]
        losses = [-d for d in deltas if d < 0]

        avg_gain = sum(gains) / self._period if gains else 0.0
        avg_loss = sum(losses) / self._period if losses else 0.0

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
