"""
MACD + RSI Combined Strategy
-----------------------------
Entry requires both indicators to align simultaneously:
  - RSI is in oversold territory (RSI < oversold_threshold) — stock is beaten down
  - MACD line is above the Signal line — momentum is turning bullish

Exit when either condition breaks:
  - RSI recovers above the midpoint, OR
  - MACD line crosses below the Signal line

The dual confirmation reduces false entries significantly vs using either alone.

Works on any timeframe — suitable for CNC trades from intraday to multi-week holds.

Config keys (under strategies.macd_rsi in config.yaml):
    rsi_period     : RSI lookback period (default 14)
    rsi_oversold   : RSI level for oversold entry condition (default 35)
    rsi_midpoint   : RSI level to trigger exit (default 55)
    macd_fast      : fast EMA period (default 12)
    macd_slow      : slow EMA period (default 26)
    macd_signal    : Signal line EMA period (default 9)
"""

from collections import deque

from trader.core.logger import get_logger
from trader.strategies.base import Direction, Signal, SignalType, Strategy

logger = get_logger(__name__)


class MACDRSIStrategy(Strategy):
    def __init__(self, instrument: str, params: dict):
        super().__init__(instrument, params)

        # RSI params
        self._rsi_period: int = params.get("rsi_period", 14)
        self._rsi_oversold: float = params.get("rsi_oversold", 35)
        self._rsi_midpoint: float = params.get("rsi_midpoint", 55)

        # MACD params
        self._fast_period: int = params.get("macd_fast", 12)
        self._slow_period: int = params.get("macd_slow", 26)
        self._signal_period: int = params.get("macd_signal", 9)

        # RSI state — need period+1 closes to compute first RSI
        self._closes: deque[float] = deque(maxlen=self._slow_period + self._signal_period)
        self._rsi: float | None = None

        # MACD state
        self._macd_history: deque[float] = deque(maxlen=self._signal_period)
        self._macd: float | None = None
        self._signal_line: float | None = None
        self._prev_macd: float | None = None
        self._prev_signal: float | None = None

    @property
    def name(self) -> str:
        return (
            f"MACD_RSI({self._fast_period},{self._slow_period},{self._signal_period}"
            f",RSI{self._rsi_period})"
        )

    def on_candle(self, candle: dict) -> Signal | None:
        close = candle["close"]
        self._closes.append(close)

        closes_list = list(self._closes)

        # MACD requires at least slow_period closes
        if len(closes_list) < self._slow_period:
            return None

        fast_ema = self._ema(closes_list, self._fast_period)
        slow_ema = self._ema(closes_list, self._slow_period)
        macd_val = fast_ema - slow_ema
        self._macd_history.append(macd_val)

        if len(self._macd_history) < self._signal_period:
            return None

        self._prev_macd = self._macd
        self._prev_signal = self._signal_line
        self._macd = macd_val
        self._signal_line = self._ema(list(self._macd_history), self._signal_period)

        # RSI requires rsi_period+1 closes; reuse the same window
        if len(closes_list) >= self._rsi_period + 1:
            self._rsi = self._compute_rsi(closes_list)

        return self._evaluate(close)

    def _evaluate(self, close: float) -> Signal | None:
        if None in (self._macd, self._signal_line, self._prev_macd,
                    self._prev_signal, self._rsi):
            return None

        macd_bullish = self._macd > self._signal_line
        rsi_oversold = self._rsi < self._rsi_oversold

        # Entry: RSI in oversold territory AND MACD above Signal (momentum turning up)
        if self.is_flat() and rsi_oversold and macd_bullish:
            logger.info(
                "MACD_RSI ENTRY | %s | RSI=%.1f (oversold<%.0f) MACD=%.4f > Signal=%.4f",
                self.instrument, self._rsi, self._rsi_oversold, self._macd, self._signal_line,
            )
            return Signal(
                instrument=self.instrument,
                direction=Direction.BUY,
                signal_type=SignalType.ENTRY,
                price_hint=close,
                strategy=self.name,
            )

        # Exit: RSI recovered to midpoint OR MACD turned bearish
        if self.position == Direction.BUY:
            rsi_recovered = self._rsi >= self._rsi_midpoint
            macd_turned = self._prev_macd >= self._prev_signal and self._macd < self._signal_line

            if rsi_recovered or macd_turned:
                reason = "RSI midpoint" if rsi_recovered else "MACD crossdown"
                logger.info(
                    "MACD_RSI EXIT | %s | %s | RSI=%.1f MACD=%.4f Signal=%.4f",
                    self.instrument, reason, self._rsi, self._macd, self._signal_line,
                )
                return Signal(
                    instrument=self.instrument,
                    direction=Direction.SELL,
                    signal_type=SignalType.EXIT,
                    price_hint=close,
                    strategy=self.name,
                )

        return None

    def _compute_rsi(self, closes: list[float]) -> float:
        # Use the last rsi_period+1 closes
        window = closes[-(self._rsi_period + 1):]
        deltas = [window[i] - window[i - 1] for i in range(1, len(window))]
        gains = [d for d in deltas if d > 0]
        losses = [-d for d in deltas if d < 0]

        avg_gain = sum(gains) / self._rsi_period if gains else 0.0
        avg_loss = sum(losses) / self._rsi_period if losses else 0.0

        if avg_loss == 0:
            return 100.0
        return 100 - (100 / (1 + avg_gain / avg_loss))

    @staticmethod
    def _ema(values: list[float], period: int) -> float:
        data = values[-period:]
        if len(data) < period:
            return sum(data) / len(data)
        k = 2 / (period + 1)
        ema = data[0]
        for price in data[1:]:
            ema = price * k + ema * (1 - k)
        return ema
