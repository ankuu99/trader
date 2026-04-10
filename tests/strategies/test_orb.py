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


class TestORBStrategy:
    def test_no_signal_during_opening_range(self):
        orb = make_strategy()
        sig1 = orb.on_candle(candle("2024-01-15 09:15:00", 100, 105, 99, 102))
        sig2 = orb.on_candle(candle("2024-01-15 09:20:00", 102, 106, 101, 104))
        assert sig1 is None
        assert sig2 is None

    def test_no_signal_on_first_candle_after_range_without_breakout(self):
        orb = make_strategy()
        orb.on_candle(candle("2024-01-15 09:15:00", 100, 105, 99, 102))
        orb.on_candle(candle("2024-01-15 09:20:00", 102, 106, 101, 104))
        # Range high = 106; this candle closes at 104 — no breakout
        sig = orb.on_candle(candle("2024-01-15 09:30:00", 104, 107, 103, 104))
        assert sig is None

    def test_buy_signal_on_breakout_above_range_high(self):
        orb = make_strategy()
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
        orb = make_strategy()
        orb.on_candle(candle("2024-01-15 09:15:00", 100, 105, 99, 102))
        orb.on_candle(candle("2024-01-15 09:20:00", 102, 106, 101, 104))
        orb.on_candle(candle("2024-01-15 09:30:00", 104, 107, 103, 104))
        orb.on_candle(candle("2024-01-15 09:35:00", 104, 110, 104, 108))  # first trade
        # Another breakout candle — should be ignored
        sig = orb.on_candle(candle("2024-01-15 09:40:00", 108, 115, 107, 113))
        assert sig is None

    def test_state_resets_on_new_day(self):
        orb = make_strategy()
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
