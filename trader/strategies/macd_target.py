"""
MACD Target Strategy
--------------------
Entry  : MACD line crosses above Signal line (bullish crossover)
         AND RSI is in oversold territory (RSI < oversold_threshold).
Exit   : Delegated to the engine/order manager:
           - Backtest : engine checks candle HIGH >= target_price each bar
           - Live     : GTT OCO order (SL + target) placed at entry; Zerodha fires on tick

The ENTRY signal carries target_price = entry_close * (1 + target_pct/100).
No candle-close exit check in this strategy — both backtest and live
resolve exit intra-candle, not at candle close.

Config keys (under strategies.macd_target in config.yaml):
    fast           : fast EMA period (default 12)
    slow           : slow EMA period (default 26)
    signal         : Signal line EMA period (default 9)
    target_pct     : profit target as % of entry price (default 5.0)
    rsi_period     : RSI lookback period (default 14)
    rsi_oversold   : RSI level for oversold entry condition (default 35)
    atr_period     : ATR window for SL sizing (default 14)
"""

from collections import deque

from trader.core.logger import get_logger
from trader.strategies.base import Direction, Signal, SignalType, Strategy

logger = get_logger(__name__)


class MACDTargetStrategy(Strategy):
    def __init__(self, instrument: str, params: dict):
        super().__init__(instrument, params)
        self._fast_period: int = params.get("fast", 12)
        self._slow_period: int = params.get("slow", 26)
        self._signal_period: int = params.get("signal", 9)
        self._target_pct: float = params.get("target_pct", 5.0)

        self._rsi_period: int = params.get("rsi_period", 14)
        self._rsi_oversold: float = params.get("rsi_oversold", 35)
        self._atr_period: int = params.get("atr_period", 14)

        self._closes: deque[float] = deque(maxlen=self._slow_period + self._signal_period)
        self._macd_history: deque[float] = deque(maxlen=self._signal_period)
        self._tr_window: deque[float] = deque(maxlen=self._atr_period)

        self._macd: float | None = None
        self._signal_line: float | None = None
        self._prev_macd: float | None = None
        self._prev_signal: float | None = None
        self._rsi: float | None = None
        self._atr: float | None = None
        self._prev_close: float | None = None

    @property
    def name(self) -> str:
        return (
            f"MACDTarget({self._fast_period},{self._slow_period},{self._signal_period}"
            f",tgt={self._target_pct}%,RSI{self._rsi_period})"
        )

    def on_candle(self, candle: dict) -> Signal | None:
        close = candle["close"]
        self._closes.append(close)

        # Update ATR (True Range)
        if self._prev_close is not None:
            tr = max(
                candle["high"] - candle["low"],
                abs(candle["high"] - self._prev_close),
                abs(candle["low"] - self._prev_close),
            )
            self._tr_window.append(tr)
            if len(self._tr_window) >= self._atr_period:
                self._atr = sum(self._tr_window) / len(self._tr_window)
        self._prev_close = close

        if len(self._closes) < self._slow_period:
            return None

        fast_ema = self._ema(list(self._closes), self._fast_period)
        slow_ema = self._ema(list(self._closes), self._slow_period)
        macd_val = fast_ema - slow_ema
        self._macd_history.append(macd_val)

        if len(self._macd_history) < self._signal_period:
            return None

        self._prev_macd = self._macd
        self._prev_signal = self._signal_line
        self._macd = macd_val
        self._signal_line = self._ema(list(self._macd_history), self._signal_period)

        if None in (self._prev_macd, self._prev_signal):
            return None

        if len(self._closes) >= self._rsi_period + 1:
            self._rsi = self._compute_rsi(list(self._closes))

        # --- MACD bullish crossover + RSI oversold entry ---
        if self.is_flat() and self._rsi is not None:
            if (
                self._prev_macd <= self._prev_signal
                and self._macd > self._signal_line
                and self._rsi < self._rsi_oversold
            ):
                target_price = round(close * (1 + self._target_pct / 100), 2)
                logger.info(
                    "MACDTarget ENTRY | %s | MACD=%.4f crossed above Signal=%.4f"
                    " | RSI=%.1f (oversold<%.0f) | target=%.2f (+%.1f%%)",
                    self.instrument, self._macd, self._signal_line,
                    self._rsi, self._rsi_oversold, target_price, self._target_pct,
                )
                return Signal(
                    instrument=self.instrument,
                    direction=Direction.BUY,
                    signal_type=SignalType.ENTRY,
                    price_hint=close,
                    strategy=self.name,
                    atr=self._atr,
                    target_price=target_price,
                )

        return None

    def _compute_rsi(self, closes: list[float]) -> float:
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
