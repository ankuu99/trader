"""
CandleAggregator — bar boundaries, tail-drop, flush, replay-rebuild.

Boundaries under test (frozen in docs/Aggregated_Timeframes_Design.md):
    day     09:15–15:15                 (15:15 candle = trigger, dropped)
    4hour   09:15–13:15, 13:15–15:15    (15:15 candle = trigger, dropped)
"""
from datetime import datetime, timedelta

import pytest

from trader.data.aggregator import BARS_PER_DAY, CandleAggregator


def c(ts, o, h, l, cl, v=100, **meta):
    d = {"timestamp": ts, "open": o, "high": h, "low": l, "close": cl, "volume": v}
    d.update(meta)
    return d


def day_candles(day: datetime, n=25, base=100.0):
    """A full session of 15m candles: 09:15, 09:30, … 15:15 (n=25)."""
    out = []
    for i in range(n):
        ts = day.replace(hour=9, minute=15) + timedelta(minutes=15 * i)
        px = base + i
        out.append(c(ts, px, px + 1, px - 1, px + 0.5, v=100, _symbol="NSE:X"))
    return out


DAY1 = datetime(2026, 6, 1)
DAY2 = datetime(2026, 6, 2)


def feed(agg, candles):
    return [bar for candle in candles if (bar := agg.add(candle)) is not None]


# ---------------------------------------------------------------- passthrough

def test_15minute_passthrough_identity():
    agg = CandleAggregator("15minute")
    candle = c(DAY1.replace(hour=10, minute=0), 1, 2, 0, 1.5)
    assert agg.add(candle) is candle
    assert agg.flush() is None


def test_invalid_timeframe_rejected():
    with pytest.raises(ValueError):
        CandleAggregator("30minute")


# ------------------------------------------------------------------- day bar

def test_day_bar_composition():
    agg = CandleAggregator("day")
    candles = day_candles(DAY1)  # 09:15 … 15:15
    bars = feed(agg, candles)

    assert len(bars) == 1
    bar = bars[0]
    # Members are 09:15..15:00 (24 candles); the 15:15 tail is never a member.
    members = candles[:24]
    assert bar["timestamp"] == DAY1.replace(hour=9, minute=15)
    assert bar["open"] == members[0]["open"]
    assert bar["close"] == members[-1]["close"]
    assert bar["high"] == max(m["high"] for m in members)
    assert bar["low"] == min(m["low"] for m in members)
    assert bar["volume"] == sum(m["volume"] for m in members)


def test_tail_candle_ohlcv_never_included():
    agg = CandleAggregator("day")
    candles = day_candles(DAY1)
    candles[-1]["high"] = 9999.0   # spike in the 15:15 candle
    candles[-1]["volume"] = 10**9
    bar = feed(agg, candles)[0]
    assert bar["high"] < 9999.0
    assert bar["volume"] < 10**9
    # After the trigger, nothing is left in progress.
    assert agg.flush() is None


def test_emission_is_completion_based_not_trigger_based():
    # The bar must emit the moment its LAST MEMBER (15:00 candle) is added —
    # live, the 15:15 "trigger" candle doesn't complete until 15:30, far too
    # late to place a same-day order.
    agg = CandleAggregator("day")
    candles = day_candles(DAY1, n=24)  # 09:15 … 15:00, no tail candle at all
    emissions = [agg.add(c) for c in candles]
    assert all(e is None for e in emissions[:23])
    assert emissions[23] is not None  # emitted on the 15:00 candle itself
    assert agg.flush() is None


def test_4hour_emission_timing():
    agg = CandleAggregator("4hour")
    candles = day_candles(DAY1)
    emissions = [agg.add(c) for c in candles]
    fired = [i for i, e in enumerate(emissions) if e is not None]
    assert fired == [15, 23]  # the 13:00 candle and the 15:00 candle


def test_missing_last_member_emits_on_next_day():
    agg = CandleAggregator("day")
    candles = day_candles(DAY1, n=23)  # 09:15 … 14:45, 15:00 candle missing
    assert feed(agg, candles) == []
    bar = agg.add(day_candles(DAY2, n=1)[0])
    assert bar is not None
    assert bar["timestamp"] == DAY1.replace(hour=9, minute=15)
    assert bar["close"] == candles[-1]["close"]


def test_two_full_days_two_bars():
    agg = CandleAggregator("day")
    bars = feed(agg, day_candles(DAY1) + day_candles(DAY2, base=200.0))
    assert [b["timestamp"] for b in bars] == [
        DAY1.replace(hour=9, minute=15), DAY2.replace(hour=9, minute=15),
    ]
    assert bars[1]["open"] == 200.0


def test_partial_session_emitted_with_available_members():
    # Early close: candles only until 12:30. Emitted by next day's first candle.
    agg = CandleAggregator("day")
    short = day_candles(DAY1, n=14)  # 09:15 … 12:30
    assert feed(agg, short) == []
    bar = agg.add(day_candles(DAY2, n=1)[0])
    assert bar["close"] == short[-1]["close"]
    assert bar["volume"] == sum(m["volume"] for m in short)


# ------------------------------------------------------------------ 4h bars

def test_4hour_boundaries():
    agg = CandleAggregator("4hour")
    candles = day_candles(DAY1)
    bars = feed(agg, candles)

    assert len(bars) == 2
    first, second = bars
    # First bar: members 09:15..13:00 (16 candles), emitted by the 13:15 candle.
    assert first["timestamp"] == DAY1.replace(hour=9, minute=15)
    assert first["open"] == candles[0]["open"]
    assert first["close"] == candles[15]["close"]
    assert first["volume"] == sum(m["volume"] for m in candles[:16])
    # Second bar: members 13:15..15:00 (8 candles), emitted by the 15:15 tail.
    assert second["timestamp"] == DAY1.replace(hour=13, minute=15)
    assert second["open"] == candles[16]["open"]
    assert second["close"] == candles[23]["close"]
    assert second["volume"] == sum(m["volume"] for m in candles[16:24])


# ---------------------------------------------------------------------- flush

def test_flush_emits_partial_and_resets():
    agg = CandleAggregator("day")
    morning = day_candles(DAY1, n=5)  # 09:15 … 10:15
    feed(agg, morning)
    bar = agg.flush()
    assert bar["timestamp"] == DAY1.replace(hour=9, minute=15)
    assert bar["close"] == morning[-1]["close"]
    assert agg.flush() is None
    # Next add starts a fresh bucket rather than resuming the flushed one.
    nxt = day_candles(DAY1, n=7)[6]  # 10:45
    assert agg.add(nxt) is None
    assert agg.flush()["open"] == nxt["open"]


def test_flush_empty_returns_none():
    assert CandleAggregator("4hour").flush() is None


# ------------------------------------------------------------------ metadata

def test_metadata_inherited_from_last_member():
    agg = CandleAggregator("day")
    candles = day_candles(DAY1)
    for i, candle in enumerate(candles):
        candle["_htf_rsi"] = float(i)
        candle["instrument_token"] = 42
    bar = feed(agg, candles)[0]
    assert bar["_symbol"] == "NSE:X"
    assert bar["instrument_token"] == 42
    assert bar["_htf_rsi"] == 23.0  # last member (15:00), not the tail (15:15)


# -------------------------------------------------------------- replay rebuild

def test_replay_rebuilds_identical_partial_state():
    # Mid-day restart: replaying today's stored 15m candles into a fresh
    # aggregator must reproduce the exact in-progress bar.
    candles = day_candles(DAY1, n=11)  # 09:15 … 11:45
    a, b = CandleAggregator("day"), CandleAggregator("day")
    feed(a, candles)
    feed(b, candles)
    assert a.flush() == b.flush()


def test_bars_per_day_constants():
    assert BARS_PER_DAY == {"15minute": 25, "4hour": 2, "day": 1}
