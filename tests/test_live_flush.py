"""
LiveFeed.flush_closed_partials — deliver the closed 15:00–15:15 base candle at
the 15:16 EOD flush so aggregated (day/4h) decisions and their orders fire while
the market is still open, without disturbing the still-open 15:15–15:30 partial.

See the design note in trader/data/live.py::flush_closed_partials and
docs/Aggregated_Timeframes_Design.md.
"""
from datetime import datetime, time, timedelta

from trader.data.aggregator import CandleAggregator
from trader.data.live import LiveFeed


def _feed():
    # KiteTicker() only stores creds at construction (no network until connect),
    # so a dummy feed is safe to build in-process.
    return LiveFeed(api_key="x", access_token="y", timeframe_minutes=15)


def _partial(candle_start, close=100.0):
    return {
        "candle_start": candle_start,
        "open": close, "high": close, "low": close, "close": close, "volume": 100,
    }


def test_flush_closed_partials_emits_closed_leaves_open():
    feed = _feed()
    emitted = []
    feed.register_candle_handler(emitted.append)

    day = datetime(2026, 7, 13)
    closed = day.replace(hour=15, minute=0)   # 15:00–15:15 bucket — closed by 15:15
    open_ = day.replace(hour=15, minute=15)   # 15:15–15:30 bucket — still open
    feed._partials[111] = _partial(closed)
    feed._partials[222] = _partial(open_)

    feed.flush_closed_partials(time(15, 15))

    # Only the 15:00 candle is delivered; the 15:15 partial is untouched.
    assert [e["timestamp"] for e in emitted] == [closed]
    assert 111 not in feed._partials
    assert 222 in feed._partials


def test_flushed_candle_completes_day_bar():
    """The delivered 15:00 candle is the day bar's last member — feeding it to a
    day aggregator (after the earlier session) completes the full 09:15 bar."""
    agg = CandleAggregator("day")
    day = datetime(2026, 7, 13)

    for i in range(23):  # 09:15 … 14:45 — no bar yet (last member not reached)
        ts = day.replace(hour=9, minute=15) + timedelta(minutes=15 * i)
        assert agg.add({"timestamp": ts, "open": 100, "high": 101, "low": 99,
                        "close": 100, "volume": 100, "_symbol": "NSE:X"}) is None

    # The 15:00 candle delivered by flush_closed_partials completes the day bar.
    bar = agg.add({"timestamp": day.replace(hour=15, minute=0),
                   "open": 100, "high": 110, "low": 95, "close": 108,
                   "volume": 100, "_symbol": "NSE:X"})
    assert bar is not None
    assert bar["timestamp"] == day.replace(hour=9, minute=15)
    assert bar["high"] == 110      # 15:00 candle's high folded in
    assert bar["close"] == 108     # 15:00 candle's close is the bar close


# --------------------------------------------------------------------------- #
# Pre-close early emission (15:29:15) — last-candle decisions must beat CAS
# --------------------------------------------------------------------------- #

def test_flush_open_partials_early_emits_and_keeps_partial():
    feed = _feed()
    emitted = []
    feed.register_candle_handler(emitted.append)
    last = datetime(2026, 8, 27, 15, 15)
    feed._partials[111] = _partial(last, close=897.9)

    feed.flush_open_partials_early()

    # Delivered once, as a normal decision candle (no final tag) …
    assert len(emitted) == 1
    assert emitted[0]["timestamp"] == last and emitted[0]["close"] == 897.9
    assert "_early_final" not in emitted[0]
    # … and the partial stays open (flagged) so late ticks still shape it.
    assert 111 in feed._partials and feed._partials[111]["early_emitted"] is True

    # Idempotent: a second pre-close call does not re-deliver.
    feed.flush_open_partials_early()
    assert len(emitted) == 1


def test_final_emission_after_early_flush_is_tagged_persist_only():
    feed = _feed()
    emitted = []
    feed.register_candle_handler(emitted.append)
    last = datetime(2026, 8, 27, 15, 15)
    feed._partials[111] = _partial(last, close=897.9)
    feed.flush_open_partials_early()

    # Late tick inside the same bucket updates the open partial silently.
    feed._partials[111]["close"] = 898.4
    feed._partials[111]["high"] = 899.0

    # 15:30 market-close flush: the bucket's real completion goes out tagged.
    feed.flush_partials()
    assert len(emitted) == 2
    final = emitted[1]
    assert final["_early_final"] is True
    assert final["timestamp"] == last and final["close"] == 898.4 and final["high"] == 899.0
    assert not feed._partials


def test_rollover_after_early_flush_is_tagged_and_normal_otherwise():
    feed = _feed()
    emitted = []
    feed.register_candle_handler(emitted.append)
    day = datetime(2026, 8, 27)
    feed._partials[111] = _partial(day.replace(hour=15, minute=15), close=100.0)
    feed.flush_open_partials_early()

    # Next-day first tick rolls the bucket: final emission tagged, new partial clean.
    feed._process_tick({"instrument_token": 111, "last_price": 101.0, "volume_traded": 10,
                        "exchange_timestamp": day.replace(day=28, hour=9, minute=16)})
    assert len(emitted) == 2 and emitted[1]["_early_final"] is True
    assert "early_emitted" not in feed._partials[111]

    # A bucket that was never early-emitted completes as a plain candle.
    feed._process_tick({"instrument_token": 111, "last_price": 102.0, "volume_traded": 20,
                        "exchange_timestamp": day.replace(day=28, hour=9, minute=31)})
    assert len(emitted) == 3 and "_early_final" not in emitted[2]
