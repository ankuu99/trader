"""
Supertrend Strategy (intraday + interday)
------------------------------------------
ATR-based trailing trend line. When price is above the Supertrend line the
system is in an uptrend; when below it is in a downtrend.

Entry  (BUY) : trend flips from bearish to bullish (Supertrend line flips below price)
Exit (SELL)  : trend flips from bullish to bearish (Supertrend line flips above price)

Config keys (under strategies.supertrend in config.yaml):
    period : ATR lookback period (default 7)
    factor : ATR multiplier for band width (default 3.0)

Excellent as a confirmation filter: confirm_entry(BUY) is True while in an uptrend.
"""

from collections import deque

from trader.core.logger import get_logger
from trader.strategies.base import Direction, Signal, SignalType, Strategy

logger = get_logger(__name__)


class SupertrendStrategy(Strategy):
    def __init__(self, instrument: str, params: dict):
        super().__init__(instrument, params)
        self._period: int = params.get("period", 7)
        self._factor: float = float(params.get("factor", 3.0))

        self._highs: deque[float] = deque(maxlen=self._period)
        self._lows: deque[float] = deque(maxlen=self._period)
        self._closes: deque[float] = deque(maxlen=self._period + 1)

        self._upper: float | None = None   # final upper band
        self._lower: float | None = None   # final lower band
        self._supertrend: float | None = None
        self._trend: int = 1               # 1 = bullish, -1 = bearish

    @property
    def name(self) -> str:
        return f"Supertrend({self._period},{self._factor})"

    def on_candle(self, candle: dict) -> Signal | None:
        high = candle["high"]
        low = candle["low"]
        close = candle["close"]

        self._highs.append(high)
        self._lows.append(low)
        self._closes.append(close)

        if len(self._closes) < self._period + 1:
            return None

        atr = self._calc_atr()
        mid = (max(self._highs) + min(self._lows)) / 2  # basic mid using window H/L

        raw_upper = mid + self._factor * atr
        raw_lower = mid - self._factor * atr

        # Adjust bands: only tighten, never widen (standard Supertrend rule)
        prev_upper = self._upper if self._upper is not None else raw_upper
        prev_lower = self._lower if self._lower is not None else raw_lower
        prev_close = list(self._closes)[-2]

        new_upper = raw_upper if raw_upper < prev_upper or prev_close > prev_upper else prev_upper
        new_lower = raw_lower if raw_lower > prev_lower or prev_close < prev_lower else prev_lower

        prev_trend = self._trend
        prev_supertrend = self._supertrend

        if prev_supertrend is None or prev_supertrend == prev_upper:
            # Was bearish
            if close > new_upper:
                self._trend = 1
                self._supertrend = new_lower
            else:
                self._trend = -1
                self._supertrend = new_upper
        else:
            # Was bullish
            if close < new_lower:
                self._trend = -1
                self._supertrend = new_upper
            else:
                self._trend = 1
                self._supertrend = new_lower

        self._upper = new_upper
        self._lower = new_lower

        return self._evaluate(close, prev_trend)

    def _evaluate(self, close: float, prev_trend: int) -> Signal | None:
        if self._supertrend is None:
            return None

        # Trend flipped to bullish → entry
        if self.is_flat() and prev_trend == -1 and self._trend == 1:
            logger.info(
                "Supertrend ENTRY signal | %s | close=%.2f flipped bullish | ST=%.2f lower=%.2f upper=%.2f",
                self.instrument, close, self._supertrend, self._lower, self._upper,
            )
            return Signal(
                instrument=self.instrument,
                direction=Direction.BUY,
                signal_type=SignalType.ENTRY,
                price_hint=close,
                strategy=self.name,
            )

        # Trend flipped to bearish → exit long
        if self.position == Direction.BUY and prev_trend == 1 and self._trend == -1:
            logger.info(
                "Supertrend EXIT signal | %s | close=%.2f flipped bearish | ST=%.2f",
                self.instrument, close, self._supertrend,
            )
            return Signal(
                instrument=self.instrument,
                direction=Direction.SELL,
                signal_type=SignalType.EXIT,
                price_hint=close,
                strategy=self.name,
            )

        return None

    def _calc_atr(self) -> float:
        closes = list(self._closes)
        highs = list(self._highs)
        lows = list(self._lows)
        trs = []
        for i in range(len(highs)):
            prev_c = closes[i]  # closes has period+1 items; highs/lows have period
            h = highs[i]
            l = lows[i]
            tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
            trs.append(tr)
        return sum(trs) / len(trs)

    def confirm_entry(self, direction: Direction) -> bool:
        """True when Supertrend is currently in the matching trend direction."""
        if self._trend is None:
            return False
        if direction == Direction.BUY:
            return self._trend == 1
        return self._trend == -1
