"""
Opening Range Breakout (ORB) Strategy
--------------------------------------
- Observes candles during the opening range window (default: 9:15–9:30 AM)
- Records the high and low of that window as the range
- Buys on first candle close above range high
- Sells (exits) at 3:15 PM or when stop-loss is hit (enforced by risk manager)
- Only one trade per instrument per day

Config keys (under strategies.orb in config.yaml):
    range_minutes : length of the opening range in minutes (default 15)
"""

from datetime import datetime, time

from trader.core.logger import get_logger
from trader.strategies.base import Direction, Signal, SignalType, Strategy

logger = get_logger(__name__)

_MARKET_OPEN = time(9, 15)


class ORBStrategy(Strategy):
    def __init__(self, instrument: str, params: dict):
        super().__init__(instrument, params)
        self._range_minutes: int = params.get("range_minutes", 15)

        self._range_high: float | None = None
        self._range_low: float | None = None
        self._range_complete: bool = False
        self._traded_today: bool = False
        self._current_date: datetime | None = None

    @property
    def name(self) -> str:
        return f"ORB({self._range_minutes}m)"

    def on_candle(self, candle: dict) -> Signal | None:
        ts: datetime = candle["timestamp"]
        candle_date = ts.date()

        # Reset state at the start of each new trading day
        if self._current_date != candle_date:
            self._reset_day(candle_date)

        # Skip if we already traded today
        if self._traded_today:
            return None

        candle_time = ts.time()
        range_end = self._range_end_time()

        if not self._range_complete:
            if candle_time <= range_end:
                # Still inside the opening range window — track high/low
                self._update_range(candle)
            else:
                # First candle after the window — range is now locked
                self._range_complete = True

        if self._range_complete and self.is_flat():
            return self._check_breakout(candle)

        return None

    def _check_breakout(self, candle: dict) -> Signal | None:
        if self._range_high is None:
            return None

        close = candle["close"]

        if close > self._range_high:
            self._traded_today = True
            logger.info(
                "ORB ENTRY signal | %s | close=%.2f broke above range_high=%.2f (range_low=%.2f)",
                self.instrument, close, self._range_high, self._range_low,
            )
            return Signal(
                instrument=self.instrument,
                direction=Direction.BUY,
                signal_type=SignalType.ENTRY,
                price_hint=close,
                strategy=self.name,
            )

        return None

    def _update_range(self, candle: dict):
        high = candle["high"]
        low = candle["low"]
        if self._range_high is None:
            self._range_high = high
            self._range_low = low
        else:
            self._range_high = max(self._range_high, high)
            self._range_low = min(self._range_low, low)

    def _range_end_time(self) -> time:
        total_minutes = _MARKET_OPEN.hour * 60 + _MARKET_OPEN.minute + self._range_minutes
        return time(total_minutes // 60, total_minutes % 60)

    def _reset_day(self, date):
        self._current_date = date
        self._range_high = None
        self._range_low = None
        self._range_complete = False
        self._traded_today = False
        self.position = None
