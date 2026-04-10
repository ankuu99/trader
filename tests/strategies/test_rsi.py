from datetime import datetime

import pytest

from trader.strategies.base import Direction, SignalType
from trader.strategies.rsi import RSIStrategy


def make_strategy(**kwargs):
    params = {"period": 5, "oversold": 40, "overbought": 70, "midpoint": 50}
    params.update(kwargs)
    return RSIStrategy("NSE:RELIANCE", params)


def feed(strategy, prices):
    """Feed a list of closing prices and return the first non-None signal."""
    for p in prices:
        sig = strategy.on_candle({"close": p, "timestamp": datetime.now()})
        if sig is not None:
            return sig
    return None


class TestRSIStrategy:
    def test_no_signal_before_enough_data(self):
        rsi = make_strategy(period=5)
        # Feed fewer than period+1 candles
        for p in [100, 99, 98, 97]:
            sig = rsi.on_candle({"close": p, "timestamp": datetime.now()})
        assert sig is None

    def test_entry_on_oversold_crossover(self):
        rsi = make_strategy(period=5, oversold=40)
        # Establish RSI above oversold first (rising prices)
        feed(rsi, [100, 102, 104, 106, 108, 110])
        # Then drop sharply to push RSI below oversold
        signal = feed(rsi, [110, 90, 80, 70, 60, 50])
        assert signal is not None
        assert signal.direction == Direction.BUY
        assert signal.signal_type == SignalType.ENTRY

    def test_no_entry_when_already_in_position(self):
        rsi = make_strategy(period=5, oversold=40)
        feed(rsi, [100, 102, 104, 106, 108, 110])
        feed(rsi, [110, 90, 80, 70, 60, 50])
        rsi.position = Direction.BUY  # already in position
        # Another oversold drop — should not re-enter
        signal = feed(rsi, [50, 45, 40, 35, 30, 25])
        assert signal is None or signal.signal_type == SignalType.EXIT

    def test_exit_when_rsi_reverts_to_midpoint(self):
        rsi = make_strategy(period=5, oversold=40, midpoint=50)
        rsi.position = Direction.BUY
        # Need period+2 prices for two RSI readings (crossover requires prev + current)
        signal = feed(rsi, [80, 85, 90, 95, 100, 105, 110])
        assert signal is not None
        assert signal.direction == Direction.SELL
        assert signal.signal_type == SignalType.EXIT

    def test_no_exit_when_flat(self):
        rsi = make_strategy(period=5, midpoint=50)
        # Flat (no position) — recovery should not produce an exit signal
        signal = feed(rsi, [80, 85, 90, 95, 100, 105])
        assert signal is None or signal.signal_type == SignalType.ENTRY

    def test_strategy_name(self):
        rsi = make_strategy(period=14)
        assert rsi.name == "RSI(14)"
