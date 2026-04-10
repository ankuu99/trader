"""
EMA Crossover Strategy (interday / daily candles)
---------------------------------------------------
- Buys when fast EMA crosses above slow EMA (golden cross)
- Exits when fast EMA crosses below slow EMA (death cross)
- One position per instrument at a time
- Designed for daily candles; works on any timeframe

Config keys (under strategies.ema_crossover in config yaml):
    fast : fast EMA period (default 9)
    slow : slow EMA period (default 21)
"""

from collections import deque

from trader.strategies.base import Direction, Signal, SignalType, Strategy


class EMACrossoverStrategy(Strategy):
    def __init__(self, instrument: str, params: dict):
        super().__init__(instrument, params)
        self._fast_period: int = params.get("fast", 9)
        self._slow_period: int = params.get("slow", 21)

        # Keep enough closes to seed both EMAs
        self._closes: deque[float] = deque(maxlen=self._slow_period + 1)

        self._fast_ema: float | None = None
        self._slow_ema: float | None = None
        self._prev_fast: float | None = None
        self._prev_slow: float | None = None

    @property
    def name(self) -> str:
        return f"EMA({self._fast_period},{self._slow_period})"

    def on_candle(self, candle: dict) -> Signal | None:
        close = candle["close"]
        self._closes.append(close)

        if len(self._closes) < self._slow_period:
            return None  # not enough data to compute slow EMA

        self._prev_fast = self._fast_ema
        self._prev_slow = self._slow_ema
        self._fast_ema = self._ema(self._fast_period)
        self._slow_ema = self._ema(self._slow_period)

        return self._evaluate(close)

    def _evaluate(self, close: float) -> Signal | None:
        fast, slow = self._fast_ema, self._slow_ema
        prev_fast, prev_slow = self._prev_fast, self._prev_slow

        if None in (fast, slow, prev_fast, prev_slow):
            return None

        # Golden cross: fast crosses above slow → buy entry
        if self.is_flat() and prev_fast <= prev_slow and fast > slow:
            return Signal(
                instrument=self.instrument,
                direction=Direction.BUY,
                signal_type=SignalType.ENTRY,
                price_hint=close,
                strategy=self.name,
            )

        # Death cross: fast crosses below slow → exit long
        if self.position == Direction.BUY and prev_fast >= prev_slow and fast < slow:
            return Signal(
                instrument=self.instrument,
                direction=Direction.SELL,
                signal_type=SignalType.EXIT,
                price_hint=close,
                strategy=self.name,
            )

        return None

    def _ema(self, period: int) -> float:
        """Compute EMA over the last `period` closes using the smoothing formula."""
        closes = list(self._closes)[-period:]
        if len(closes) < period:
            return sum(closes) / len(closes)
        k = 2 / (period + 1)
        ema = closes[0]
        for price in closes[1:]:
            ema = price * k + ema * (1 - k)
        return ema
