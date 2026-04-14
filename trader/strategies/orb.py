"""
Opening Range Breakout (ORB) Strategy
--------------------------------------
- Observes candles during the opening range window (default: 9:15–9:30 AM)
- Records the high and low of that window as the range
- Buys on first candle close above range high
- Sells (exits) at 3:15 PM or when stop-loss is hit (enforced by risk manager)
- Only one trade per instrument per day

Optional signal quality filters (enabled by default, disable in config if desired):

  Gap filter      — skip the day if today's open gaps more than gap_pct% vs previous
                    close. Gap days have different breakout dynamics and wider spreads.

  Volume filter   — skip the breakout if opening-range volume is below
                    volume_multiplier × 20-day average of opening-range volume.
                    Requires volume_lookback days of history before engaging;
                    passes through unconditionally until enough history is built.

Config keys (under strategies.orb in config.yaml):
    range_minutes    : length of the opening range in minutes (default 15)
    volume_filter    : enable volume filter (default true)
    volume_lookback  : rolling window for average range volume (default 20)
    volume_multiplier: minimum volume multiple vs average (default 1.5)
    gap_filter       : enable gap filter (default true)
    gap_pct          : max open-gap % before day is skipped (default 2.0)
"""

from collections import deque
from datetime import datetime, time

from trader.core.logger import get_logger
from trader.strategies.base import Direction, Signal, SignalType, Strategy

logger = get_logger(__name__)

_MARKET_OPEN = time(9, 15)
# Minimum days of range-volume history required before the volume filter engages
_MIN_VOLUME_HISTORY = 5


class ORBStrategy(Strategy):
    def __init__(self, instrument: str, params: dict):
        super().__init__(instrument, params)
        self._range_minutes: int = params.get("range_minutes", 15)

        # Volume filter
        self._volume_filter: bool = bool(params.get("volume_filter", True))
        self._volume_lookback: int = int(params.get("volume_lookback", 20))
        self._volume_multiplier: float = float(params.get("volume_multiplier", 1.5))
        self._past_range_volumes: deque = deque(maxlen=self._volume_lookback)
        self._range_volume: float = 0.0

        # Gap filter
        self._gap_filter: bool = bool(params.get("gap_filter", True))
        self._gap_pct: float = float(params.get("gap_pct", 2.0)) / 100

        # Cross-day state
        self._prev_close: float | None = None
        self._last_close: float | None = None

        # Per-day state
        self._range_high: float | None = None
        self._range_low: float | None = None
        self._range_complete: bool = False
        self._traded_today: bool = False
        self._skip_today: bool = False
        self._current_date: datetime | None = None

    @property
    def name(self) -> str:
        return f"ORB({self._range_minutes}m)"

    def on_candle(self, candle: dict) -> Signal | None:
        ts: datetime = candle["timestamp"]
        candle_date = ts.date()

        if self._current_date != candle_date:
            self._reset_day(candle_date, first_open=candle["open"])

        # Track last close every candle so we have it for the next day's gap check
        self._last_close = candle["close"]

        if self._traded_today or self._skip_today:
            return None

        candle_time = ts.time()
        range_end = self._range_end_time()

        if not self._range_complete:
            if candle_time <= range_end:
                self._update_range(candle)
            else:
                self._range_complete = True

        if self._range_complete and self.is_flat():
            return self._check_breakout(candle)

        return None

    def _check_breakout(self, candle: dict) -> Signal | None:
        if self._range_high is None:
            return None

        if self._volume_filter and not self._volume_ok():
            logger.info(
                "ORB volume filter: skipping breakout for %s"
                " (range_vol=%.0f, threshold=%.0f×avg)",
                self.instrument, self._range_volume, self._volume_multiplier,
            )
            return None

        close = candle["close"]

        if close > self._range_high:
            self._traded_today = True
            logger.info(
                "ORB ENTRY signal | %s | close=%.2f broke above range_high=%.2f"
                " (range_low=%.2f)",
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

    def _volume_ok(self) -> bool:
        """True if today's range volume meets the multiplier threshold vs history."""
        if len(self._past_range_volumes) < _MIN_VOLUME_HISTORY:
            return True  # not enough history — don't penalise early days
        avg = sum(self._past_range_volumes) / len(self._past_range_volumes)
        return self._range_volume >= self._volume_multiplier * avg

    def _update_range(self, candle: dict):
        high = candle["high"]
        low = candle["low"]
        if self._range_high is None:
            self._range_high = high
            self._range_low = low
        else:
            self._range_high = max(self._range_high, high)
            self._range_low = min(self._range_low, low)
        self._range_volume += float(candle.get("volume", 0))

    def _range_end_time(self) -> time:
        total_minutes = _MARKET_OPEN.hour * 60 + _MARKET_OPEN.minute + self._range_minutes
        return time(total_minutes // 60, total_minutes % 60)

    def _reset_day(self, date, first_open: float | None = None):
        # Commit completed range volume to rolling history
        if self._range_volume > 0:
            self._past_range_volumes.append(self._range_volume)

        # Carry last close forward as previous close for the gap check
        if self._last_close is not None:
            self._prev_close = self._last_close

        self._current_date = date
        self._range_high = None
        self._range_low = None
        self._range_complete = False
        self._traded_today = False
        self._skip_today = False
        self._range_volume = 0.0
        self._last_close = None
        self.position = None

        # Gap filter: skip if today's open is too far from previous close
        if self._gap_filter and self._prev_close and first_open:
            gap = abs(first_open / self._prev_close - 1)
            if gap > self._gap_pct:
                self._skip_today = True
                logger.info(
                    "ORB gap filter: skipping %s (gap=%.2f%% > %.1f%%)",
                    self.instrument, gap * 100, self._gap_pct * 100,
                )
