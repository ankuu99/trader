"""
Tests for VWAPPullbackStrategy.

The strategy fires a BUY entry when:
  1. Close > SMA (trend up)
  2. Previous close was above VWAP; current candle low touches VWAP but close stays near it
  3. Next candle closes above the pullback candle's high

And exits when close < VWAP.

For test clarity we use a small sma_period (3) so the SMA warms up quickly.
"""

from datetime import datetime

import pytest

from trader.strategies.base import Direction, SignalType
from trader.strategies.vwap_pullback import VWAPPullbackStrategy


def make_strategy(**kwargs):
    # 1.0% tolerance gives room for the coarse integer candle values used in tests.
    # (VWAP with high/low candles drifts above close, making 0.5% too tight with integers.)
    params = {"sma_period": 3, "vwap_touch_tolerance_pct": 1.0}
    params.update(kwargs)
    return VWAPPullbackStrategy("NSE:INFY", params)


def candle(ts_str, o, h, l, c, vol=10000):
    return {
        "timestamp": datetime.fromisoformat(ts_str),
        "open": o, "high": h, "low": l, "close": c, "volume": vol,
    }


def feed(strategy, candles):
    """Feed a list of candles, return list of signals (None or Signal)."""
    return [strategy.on_candle(c) for c in candles]


class TestVWAPPullbackEntry:
    def test_no_signal_before_sma_warmup(self):
        """SMA needs sma_period candles; no signal on first candle."""
        strat = make_strategy(sma_period=5)
        sig = strat.on_candle(candle("2024-01-15 09:15:00", 100, 110, 99, 105))
        assert sig is None

    def test_no_signal_when_close_below_sma(self):
        """Price below SMA blocks entry."""
        strat = make_strategy()
        # Feed 3 candles to warm SMA at ~100; close ends at 85 (below SMA)
        strat.on_candle(candle("2024-01-15 09:15:00", 100, 105, 99, 100, vol=10000))
        strat.on_candle(candle("2024-01-15 09:20:00", 100, 105, 99, 100, vol=10000))
        strat.on_candle(candle("2024-01-15 09:25:00", 100, 105, 99, 100, vol=10000))
        # VWAP ≈ 100; close=85 < SMA(100) — no entry
        sig = strat.on_candle(candle("2024-01-15 09:30:00", 85, 90, 84, 85, vol=10000))
        assert sig is None

    def test_full_entry_sequence(self):
        """Complete pullback-to-VWAP and resumption produces BUY signal."""
        strat = make_strategy()
        # Candle 1-3: warm up SMA at ~100, VWAP builds up
        strat.on_candle(candle("2024-01-15 09:15:00", 100, 105, 99, 100, vol=10000))
        strat.on_candle(candle("2024-01-15 09:20:00", 100, 105, 99, 100, vol=10000))
        strat.on_candle(candle("2024-01-15 09:25:00", 100, 105, 99, 100, vol=10000))
        # SMA ≈ 100, VWAP ≈ 100

        # Candle 4: price above VWAP at 102 (prev_close = 102 > VWAP ≈ 100)
        strat.on_candle(candle("2024-01-15 09:30:00", 100, 106, 100, 102, vol=10000))

        # Candle 5: VWAP touch — low dips to ~VWAP, close stays near VWAP; high = 103
        # prev_close=102 > VWAP; low=100 touches VWAP; close=100.4 ≈ VWAP (within 0.5%)
        # SMA ≈ 100.67 — close=100.4 < SMA — this will FAIL the trend gate!
        # Let's push close higher: close=101 (above SMA and within VWAP tolerance)
        sig5 = strat.on_candle(candle("2024-01-15 09:35:00", 101, 103, 100, 101, vol=10000))
        # At this point AWAITING_RESUME should be set, pullback_high = 103
        assert sig5 is None

        # Candle 6: close > pullback_high (103) — ENTRY
        sig6 = strat.on_candle(candle("2024-01-15 09:40:00", 101, 108, 101, 105, vol=10000))
        assert sig6 is not None
        assert sig6.direction == Direction.BUY
        assert sig6.signal_type == SignalType.ENTRY
        assert sig6.price_hint == 105

    def test_failed_pullback_resets_state(self):
        """If price falls far below VWAP after touch, state resets — no entry on next candle."""
        strat = make_strategy()
        strat.on_candle(candle("2024-01-15 09:15:00", 100, 105, 99, 100, vol=10000))
        strat.on_candle(candle("2024-01-15 09:20:00", 100, 105, 99, 100, vol=10000))
        strat.on_candle(candle("2024-01-15 09:25:00", 100, 105, 99, 100, vol=10000))
        # Above VWAP
        strat.on_candle(candle("2024-01-15 09:30:00", 100, 106, 100, 102, vol=10000))
        # VWAP touch → AWAITING_RESUME
        strat.on_candle(candle("2024-01-15 09:35:00", 101, 103, 100, 101, vol=10000))
        # Crash: close far below VWAP → abandon, reset to WATCHING
        strat.on_candle(candle("2024-01-15 09:40:00", 101, 101, 96,  96, vol=10000))
        # Next candle close above old pullback_high (103) — but state reset, no signal
        sig = strat.on_candle(candle("2024-01-15 09:45:00", 96, 110, 95, 107, vol=10000))
        assert sig is None

    def test_no_entry_without_vwap_touch(self):
        """Straight up move without touching VWAP — no signal."""
        strat = make_strategy()
        strat.on_candle(candle("2024-01-15 09:15:00", 100, 105, 99, 100, vol=10000))
        strat.on_candle(candle("2024-01-15 09:20:00", 100, 105, 99, 100, vol=10000))
        strat.on_candle(candle("2024-01-15 09:25:00", 100, 105, 99, 100, vol=10000))
        # Rises steadily well above VWAP — never touches it
        sig1 = strat.on_candle(candle("2024-01-15 09:30:00", 105, 110, 104, 108, vol=10000))
        sig2 = strat.on_candle(candle("2024-01-15 09:35:00", 108, 115, 107, 113, vol=10000))
        assert sig1 is None
        assert sig2 is None

    def test_state_resets_on_new_day(self):
        """Pullback state from day 1 does not carry into day 2."""
        strat = make_strategy()
        strat.on_candle(candle("2024-01-15 09:15:00", 100, 105, 99, 100, vol=10000))
        strat.on_candle(candle("2024-01-15 09:20:00", 100, 105, 99, 100, vol=10000))
        strat.on_candle(candle("2024-01-15 09:25:00", 100, 105, 99, 100, vol=10000))
        strat.on_candle(candle("2024-01-15 09:30:00", 100, 106, 100, 102, vol=10000))
        # VWAP touch — enters AWAITING_RESUME
        strat.on_candle(candle("2024-01-15 09:35:00", 101, 103, 100, 101, vol=10000))
        assert strat._state == "awaiting_resume"

        # Day 2: state should reset
        strat.on_candle(candle("2024-01-16 09:15:00", 100, 110, 99, 108, vol=10000))
        assert strat._state == "watching"
        assert strat._pullback_high is None


class TestVWAPPullbackExit:
    def test_exit_when_close_below_vwap(self):
        """After entry, exit when close falls below VWAP."""
        strat = make_strategy()
        strat.on_candle(candle("2024-01-15 09:15:00", 100, 105, 99, 100, vol=10000))
        strat.on_candle(candle("2024-01-15 09:20:00", 100, 105, 99, 100, vol=10000))
        strat.on_candle(candle("2024-01-15 09:25:00", 100, 105, 99, 100, vol=10000))
        strat.on_candle(candle("2024-01-15 09:30:00", 100, 106, 100, 102, vol=10000))
        # VWAP touch
        strat.on_candle(candle("2024-01-15 09:35:00", 101, 103, 100, 101, vol=10000))
        # Entry signal
        entry = strat.on_candle(candle("2024-01-15 09:40:00", 101, 108, 101, 105, vol=10000))
        assert entry is not None
        # Simulate position fill
        strat.on_order_update({"status": "COMPLETE", "direction": "BUY", "signal_type": "ENTRY"})
        # Price falls below VWAP — exit
        exit_sig = strat.on_candle(candle("2024-01-15 09:45:00", 105, 106, 98, 98, vol=10000))
        assert exit_sig is not None
        assert exit_sig.direction == Direction.SELL
        assert exit_sig.signal_type == SignalType.EXIT

    def test_no_exit_while_above_vwap(self):
        """No exit while price stays above VWAP."""
        strat = make_strategy()
        strat.on_candle(candle("2024-01-15 09:15:00", 100, 105, 99, 100, vol=10000))
        strat.on_candle(candle("2024-01-15 09:20:00", 100, 105, 99, 100, vol=10000))
        strat.on_candle(candle("2024-01-15 09:25:00", 100, 105, 99, 100, vol=10000))
        strat.on_candle(candle("2024-01-15 09:30:00", 100, 106, 100, 102, vol=10000))
        strat.on_candle(candle("2024-01-15 09:35:00", 101, 103, 100, 101, vol=10000))
        entry = strat.on_candle(candle("2024-01-15 09:40:00", 101, 108, 101, 105, vol=10000))
        assert entry is not None
        strat.on_order_update({"status": "COMPLETE", "direction": "BUY", "signal_type": "ENTRY"})
        # Price stays above VWAP
        sig = strat.on_candle(candle("2024-01-15 09:45:00", 105, 115, 103, 112, vol=10000))
        assert sig is None

    def test_strategy_name(self):
        strat = make_strategy(sma_period=20)
        assert strat.name == "VWAPPullback(20)"
