"""
EMA Pullback Strategy (intraday)
----------------------------------
Trades pullbacks to the fast EMA during an established uptrend.

Conditions:
  - Uptrend: close is above the slow EMA
  - Pullback: close touches or crosses below the fast EMA from above

Entry  (BUY) : price in uptrend (above slow EMA) and pulls back to fast EMA
Exit (SELL)  : close drops below the slow EMA (trend is broken)

Config keys (under strategies.ema_pullback in config.yaml):
    fast : fast EMA period (default 20)
    slow : slow EMA period (default 50)

Can act as a filter: confirm_entry(BUY) is True when price is in an uptrend
(above slow EMA), which is useful for filtering other entry strategies.
"""

from collections import deque

from trader.strategies.base import Direction, Signal, SignalType, Strategy


class EMAPullbackStrategy(Strategy):
    def __init__(self, instrument: str, params: dict):
        super().__init__(instrument, params)
        self._fast_period: int = params.get("fast", 20)
        self._slow_period: int = params.get("slow", 50)

        self._closes: deque[float] = deque(maxlen=self._slow_period + 1)
        self._fast_ema: float | None = None
        self._slow_ema: float | None = None
        self._prev_close: float | None = None

    @property
    def name(self) -> str:
        return f"EMAPullback({self._fast_period},{self._slow_period})"

    def on_candle(self, candle: dict) -> Signal | None:
        close = candle["close"]
        self._closes.append(close)

        if len(self._closes) < self._slow_period:
            self._prev_close = close
            return None

        self._fast_ema = self._ema(self._fast_period)
        self._slow_ema = self._ema(self._slow_period)

        signal = self._evaluate(close)
        self._prev_close = close
        return signal

    def _evaluate(self, close: float) -> Signal | None:
        if self._fast_ema is None or self._slow_ema is None or self._prev_close is None:
            return None

        in_uptrend = close > self._slow_ema
        pullback_to_fast = self._prev_close > self._fast_ema and close <= self._fast_ema

        # Entry: uptrend + price pulls back to touch fast EMA
        if self.is_flat() and in_uptrend and pullback_to_fast:
            return Signal(
                instrument=self.instrument,
                direction=Direction.BUY,
                signal_type=SignalType.ENTRY,
                price_hint=close,
                strategy=self.name,
            )

        # Exit: close breaks below slow EMA (trend is over)
        if self.position == Direction.BUY and close < self._slow_ema:
            return Signal(
                instrument=self.instrument,
                direction=Direction.SELL,
                signal_type=SignalType.EXIT,
                price_hint=close,
                strategy=self.name,
            )

        return None

    def _ema(self, period: int) -> float:
        closes = list(self._closes)[-period:]
        k = 2 / (period + 1)
        ema = closes[0]
        for price in closes[1:]:
            ema = price * k + ema * (1 - k)
        return ema

    def confirm_entry(self, direction: Direction) -> bool:
        """True when price is in an uptrend (above slow EMA) — useful as a trend filter."""
        if self._slow_ema is None or self._prev_close is None:
            return False
        if direction == Direction.BUY:
            return self._prev_close > self._slow_ema
        return self._prev_close < self._slow_ema
