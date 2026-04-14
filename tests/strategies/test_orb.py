from datetime import datetime

import pytest

from trader.strategies.base import Direction, SignalType
from trader.strategies.orb import ORBStrategy


def make_strategy(**kwargs):
    params = {"range_minutes": 15}
    params.update(kwargs)
    return ORBStrategy("NSE:INFY", params)


def candle(ts_str, o, h, l, c, vol=1000):
    return {
        "timestamp": datetime.fromisoformat(ts_str),
        "open": o, "high": h, "low": l, "close": c, "volume": vol,
    }


# ------------------------------------------------------------------ #
# Original behaviour (filters disabled)                               #
# ------------------------------------------------------------------ #

class TestORBCoreLogic:
    """Core ORB logic — filters explicitly disabled so they don't interfere."""

    def make(self, **kwargs):
        return make_strategy(volume_filter=False, gap_filter=False, **kwargs)

    def test_no_signal_during_opening_range(self):
        orb = self.make()
        sig1 = orb.on_candle(candle("2024-01-15 09:15:00", 100, 105, 99, 102))
        sig2 = orb.on_candle(candle("2024-01-15 09:20:00", 102, 106, 101, 104))
        assert sig1 is None
        assert sig2 is None

    def test_no_signal_on_first_candle_after_range_without_breakout(self):
        orb = self.make()
        orb.on_candle(candle("2024-01-15 09:15:00", 100, 105, 99, 102))
        orb.on_candle(candle("2024-01-15 09:20:00", 102, 106, 101, 104))
        # Range high = 106; this candle closes at 104 — no breakout
        sig = orb.on_candle(candle("2024-01-15 09:30:00", 104, 107, 103, 104))
        assert sig is None

    def test_buy_signal_on_breakout_above_range_high(self):
        orb = self.make()
        orb.on_candle(candle("2024-01-15 09:15:00", 100, 105, 99, 102))
        orb.on_candle(candle("2024-01-15 09:20:00", 102, 106, 101, 104))
        orb.on_candle(candle("2024-01-15 09:30:00", 104, 107, 103, 104))  # lock range
        # Close at 108 > range high (106) — breakout
        sig = orb.on_candle(candle("2024-01-15 09:35:00", 104, 110, 104, 108))
        assert sig is not None
        assert sig.direction == Direction.BUY
        assert sig.signal_type == SignalType.ENTRY
        assert sig.price_hint == 108

    def test_only_one_trade_per_day(self):
        orb = self.make()
        orb.on_candle(candle("2024-01-15 09:15:00", 100, 105, 99, 102))
        orb.on_candle(candle("2024-01-15 09:20:00", 102, 106, 101, 104))
        orb.on_candle(candle("2024-01-15 09:30:00", 104, 107, 103, 104))
        orb.on_candle(candle("2024-01-15 09:35:00", 104, 110, 104, 108))  # first trade
        # Another breakout candle — should be ignored
        sig = orb.on_candle(candle("2024-01-15 09:40:00", 108, 115, 107, 113))
        assert sig is None

    def test_state_resets_on_new_day(self):
        orb = self.make()
        # Day 1
        orb.on_candle(candle("2024-01-15 09:15:00", 100, 105, 99, 102))
        orb.on_candle(candle("2024-01-15 09:20:00", 102, 106, 101, 104))
        orb.on_candle(candle("2024-01-15 09:30:00", 104, 107, 103, 108))  # breakout day 1
        # Day 2 — fresh state
        orb.on_candle(candle("2024-01-16 09:15:00", 200, 205, 199, 202))
        orb.on_candle(candle("2024-01-16 09:20:00", 202, 206, 201, 204))
        orb.on_candle(candle("2024-01-16 09:30:00", 204, 207, 203, 204))
        sig = orb.on_candle(candle("2024-01-16 09:35:00", 204, 210, 204, 208))
        assert sig is not None
        assert sig.direction == Direction.BUY

    def test_strategy_name(self):
        orb = make_strategy(range_minutes=30)
        assert orb.name == "ORB(30m)"


# ------------------------------------------------------------------ #
# Gap filter                                                           #
# ------------------------------------------------------------------ #

class TestGapFilter:
    def make(self, **kwargs):
        return make_strategy(volume_filter=False, gap_filter=True, gap_pct=2.0, **kwargs)

    def _run_day1(self, orb, close=100.0):
        """Seed day 1 data to establish _prev_close."""
        orb.on_candle(candle("2024-01-15 09:15:00", 100, 105, 99, 102))
        orb.on_candle(candle("2024-01-15 09:20:00", 102, 106, 101, 104))
        orb.on_candle(candle("2024-01-15 09:30:00", 104, 107, 103, close))

    def test_no_signal_on_gap_up_day(self):
        orb = self.make()
        self._run_day1(orb, close=100.0)
        # Day 2: open 103.5 → gap = 3.5% > 2%
        orb.on_candle(candle("2024-01-16 09:15:00", 103.5, 108, 103, 104))
        orb.on_candle(candle("2024-01-16 09:20:00", 104, 109, 103, 105))
        orb.on_candle(candle("2024-01-16 09:30:00", 105, 110, 104, 105))
        sig = orb.on_candle(candle("2024-01-16 09:35:00", 105, 115, 104, 112))
        assert sig is None

    def test_signal_allowed_on_small_gap(self):
        orb = self.make()
        self._run_day1(orb, close=100.0)
        # Day 2: open 101 → gap = 1% < 2%
        orb.on_candle(candle("2024-01-16 09:15:00", 101, 106, 100, 103))
        orb.on_candle(candle("2024-01-16 09:20:00", 103, 107, 102, 104))
        orb.on_candle(candle("2024-01-16 09:30:00", 104, 108, 103, 104))
        sig = orb.on_candle(candle("2024-01-16 09:35:00", 104, 112, 103, 110))
        assert sig is not None

    def test_no_filter_on_first_day_no_prev_close(self):
        """Day 1 has no previous close, so gap filter must not block it."""
        orb = self.make()
        # Large open, but it's day 1 so no prev_close
        orb.on_candle(candle("2024-01-15 09:15:00", 200, 210, 199, 202))
        orb.on_candle(candle("2024-01-15 09:20:00", 202, 211, 201, 204))
        orb.on_candle(candle("2024-01-15 09:30:00", 204, 212, 203, 204))
        sig = orb.on_candle(candle("2024-01-15 09:35:00", 204, 215, 203, 213))
        assert sig is not None

    def test_gap_filter_disabled(self):
        orb = make_strategy(volume_filter=False, gap_filter=False)
        self._run_day1(orb, close=100.0)
        # Day 2: huge gap — but filter is off, signal should still come through
        orb.on_candle(candle("2024-01-16 09:15:00", 110, 115, 109, 112))
        orb.on_candle(candle("2024-01-16 09:20:00", 112, 116, 111, 113))
        orb.on_candle(candle("2024-01-16 09:30:00", 113, 117, 112, 113))
        sig = orb.on_candle(candle("2024-01-16 09:35:00", 113, 120, 112, 118))
        assert sig is not None


# ------------------------------------------------------------------ #
# Volume filter                                                        #
# ------------------------------------------------------------------ #

class TestVolumeFilter:
    def make(self, **kwargs):
        return make_strategy(
            gap_filter=False,
            volume_filter=True,
            volume_lookback=5,
            volume_multiplier=1.5,
            **kwargs,
        )

    def _feed_day(self, orb, date_str, open_vol=1000, close_vol=1000, trigger=False):
        """Feed a single day's worth of range candles + optional breakout candle."""
        orb.on_candle(candle(f"{date_str} 09:15:00", 100, 105, 99, 102, vol=open_vol))
        orb.on_candle(candle(f"{date_str} 09:20:00", 102, 106, 101, 104, vol=open_vol))
        orb.on_candle(candle(f"{date_str} 09:30:00", 104, 107, 103, 104, vol=close_vol))
        if trigger:
            return orb.on_candle(candle(f"{date_str} 09:35:00", 104, 110, 104, 108, vol=500))
        return None

    def test_volume_filter_passes_when_insufficient_history(self):
        """With < _MIN_VOLUME_HISTORY days, the filter should not block."""
        orb = self.make()
        # Day 1 only — no history yet
        orb.on_candle(candle("2024-01-15 09:15:00", 100, 105, 99, 102, vol=100))
        orb.on_candle(candle("2024-01-15 09:20:00", 102, 106, 101, 104, vol=100))
        orb.on_candle(candle("2024-01-15 09:30:00", 104, 107, 103, 104, vol=100))
        sig = orb.on_candle(candle("2024-01-15 09:35:00", 104, 110, 104, 108, vol=100))
        assert sig is not None

    def test_volume_filter_blocks_low_volume_breakout(self):
        orb = self.make()
        dates = [
            "2024-01-08", "2024-01-09", "2024-01-10",
            "2024-01-11", "2024-01-12",
        ]
        for d in dates:
            self._feed_day(orb, d, open_vol=2000)  # history: 4000 vol/day

        # Day 6: range volume = 300 (avg≈4000, threshold = 1.5×4000=6000) — blocked
        orb.on_candle(candle("2024-01-15 09:15:00", 100, 105, 99, 102, vol=150))
        orb.on_candle(candle("2024-01-15 09:20:00", 102, 106, 101, 104, vol=150))
        orb.on_candle(candle("2024-01-15 09:30:00", 104, 107, 103, 104, vol=0))
        sig = orb.on_candle(candle("2024-01-15 09:35:00", 104, 110, 104, 108, vol=500))
        assert sig is None

    def test_volume_filter_allows_high_volume_breakout(self):
        orb = self.make()
        dates = [
            "2024-01-08", "2024-01-09", "2024-01-10",
            "2024-01-11", "2024-01-12",
        ]
        for d in dates:
            self._feed_day(orb, d, open_vol=1000)  # history: 2000 vol/day

        # Day 6: range volume = 6000 (avg≈2000, threshold = 3000) — allowed
        orb.on_candle(candle("2024-01-15 09:15:00", 100, 105, 99, 102, vol=3000))
        orb.on_candle(candle("2024-01-15 09:20:00", 102, 106, 101, 104, vol=3000))
        orb.on_candle(candle("2024-01-15 09:30:00", 104, 107, 103, 104, vol=0))
        sig = orb.on_candle(candle("2024-01-15 09:35:00", 104, 110, 104, 108, vol=500))
        assert sig is not None

    def test_volume_filter_disabled(self):
        orb = make_strategy(gap_filter=False, volume_filter=False)
        dates = [
            "2024-01-08", "2024-01-09", "2024-01-10",
            "2024-01-11", "2024-01-12",
        ]
        for d in dates:
            orb.on_candle(candle(f"{d} 09:15:00", 100, 105, 99, 102, vol=2000))
            orb.on_candle(candle(f"{d} 09:20:00", 102, 106, 101, 104, vol=2000))
            orb.on_candle(candle(f"{d} 09:30:00", 104, 107, 103, 104, vol=0))

        # Low volume but filter off — should pass
        orb.on_candle(candle("2024-01-15 09:15:00", 100, 105, 99, 102, vol=1))
        orb.on_candle(candle("2024-01-15 09:20:00", 102, 106, 101, 104, vol=1))
        orb.on_candle(candle("2024-01-15 09:30:00", 104, 107, 103, 104, vol=0))
        sig = orb.on_candle(candle("2024-01-15 09:35:00", 104, 110, 104, 108, vol=500))
        assert sig is not None
