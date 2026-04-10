"""
RSI + EMA Combo Strategy (interday / daily candles)
----------------------------------------------------
Combines two conditions that must both hold for an entry:
  1. RSI is oversold (daily RSI < oversold threshold) — price is beaten down
  2. Price is above the slow EMA — the longer-term trend is still up

Only buying in confirmed uptrends prevents catching falling knives.

Entry  (BUY) : RSI < oversold AND close > slow EMA (oversold within uptrend)
Exit (SELL)  : RSI reverts above midpoint

Config keys (under strategies.rsi_ema in config.yaml):
    rsi_period : RSI lookback period (default 14)
    ema_period : slow EMA period for trend filter (default 50)
    oversold   : RSI level to trigger entry (default 35)
    midpoint   : RSI level to trigger exit (default 50)
"""

from collections import deque

from trader.strategies.base import Direction, Signal, SignalType, Strategy


class RSIEMAStrategy(Strategy):
    def __init__(self, instrument: str, params: dict):
        super().__init__(instrument, params)
        self._rsi_period: int = params.get("rsi_period", 14)
        self._ema_period: int = params.get("ema_period", 50)
        self._oversold: float = float(params.get("oversold", 35))
        self._midpoint: float = float(params.get("midpoint", 50))

        self._closes: deque[float] = deque(maxlen=max(self._rsi_period + 1, self._ema_period))
        self._rsi: float | None = None
        self._prev_rsi: float | None = None
        self._slow_ema: float | None = None

    @property
    def name(self) -> str:
        return f"RSI+EMA({self._rsi_period},{self._ema_period})"

    def on_candle(self, candle: dict) -> Signal | None:
        close = candle["close"]
        self._closes.append(close)

        closes = list(self._closes)
        if len(closes) < self._rsi_period + 1:
            return None

        self._prev_rsi = self._rsi
        self._rsi = self._calc_rsi(closes[-self._rsi_period - 1:])

        if len(closes) >= self._ema_period:
            self._slow_ema = self._calc_ema(closes[-self._ema_period:], self._ema_period)

        return self._evaluate(close)

    def _evaluate(self, close: float) -> Signal | None:
        if self._rsi is None or self._prev_rsi is None or self._slow_ema is None:
            return None

        in_uptrend = close > self._slow_ema

        # Entry: RSI crosses below oversold threshold while price is in uptrend
        if self.is_flat() and in_uptrend and self._prev_rsi >= self._oversold and self._rsi < self._oversold:
            return Signal(
                instrument=self.instrument,
                direction=Direction.BUY,
                signal_type=SignalType.ENTRY,
                price_hint=close,
                strategy=self.name,
            )

        # Exit: RSI reverts above midpoint
        if self.position == Direction.BUY and self._rsi >= self._midpoint:
            return Signal(
                instrument=self.instrument,
                direction=Direction.SELL,
                signal_type=SignalType.EXIT,
                price_hint=close,
                strategy=self.name,
            )

        return None

    def _calc_rsi(self, closes: list[float]) -> float:
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [d for d in deltas if d > 0]
        losses = [-d for d in deltas if d < 0]
        avg_gain = sum(gains) / self._rsi_period if gains else 0.0
        avg_loss = sum(losses) / self._rsi_period if losses else 0.0
        if avg_loss == 0:
            return 100.0
        return 100 - (100 / (1 + avg_gain / avg_loss))

    def _calc_ema(self, closes: list[float], period: int) -> float:
        k = 2 / (period + 1)
        ema = closes[0]
        for price in closes[1:]:
            ema = price * k + ema * (1 - k)
        return ema
