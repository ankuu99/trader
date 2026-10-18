"""Model Lab L0b — timeframe bars and avail_ts (synthetic data only)."""
import numpy as np
import pandas as pd

from research.model_lab.bars import TFS, derive
from research.model_lab.synth import synthetic_15m, synthetic_day
from trader.data.aggregator import CandleAggregator

QUARTER = pd.Timedelta(minutes=15)


def _run_agg(src, tf):
    agg = CandleAggregator(tf)
    out = []
    for r in src.itertuples(index=False):
        e = agg.add({"timestamp": r.timestamp.to_pydatetime(), "open": r.open, "high": r.high,
                     "low": r.low, "close": r.close, "volume": r.volume})
        if e:
            out.append(e)
    e = agg.flush()
    if e:
        out.append(e)
    return pd.DataFrame(out)


def test_4h_and_dayagg_match_candle_aggregator():
    src = synthetic_15m(30, seed=1)
    for tf, prod in (("4h", "4hour"), ("dayagg", "day")):
        ref = _run_agg(src, prod)
        got = derive(src, tf)
        assert len(ref) == len(got)
        assert (pd.to_datetime(ref["timestamp"]).values == got["timestamp"].values).all()
        for c in ("open", "high", "low", "close"):
            np.testing.assert_allclose(ref[c].values, got[c].values, rtol=1e-12)
        np.testing.assert_allclose(ref["volume"].values.astype(float), got["volume"].values.astype(float))


def _session(n=25, day="2024-03-05"):
    ts = pd.Timestamp(day + " 09:15") + QUARTER * np.arange(n)
    c = 100 + np.arange(n, dtype=float)
    return pd.DataFrame({"timestamp": ts, "open": c - 0.5, "high": c + 1, "low": c - 1, "close": c,
                         "volume": np.arange(1, n + 1) * 10})


def test_30m_60m_buckets():
    s = _session()
    b30 = derive(s, "30m")
    assert len(b30) == 13
    assert b30.timestamp.iloc[0] == pd.Timestamp("2024-03-05 09:15")
    assert b30.timestamp.iloc[1] == pd.Timestamp("2024-03-05 09:45")
    assert b30.timestamp.iloc[-1] == pd.Timestamp("2024-03-05 15:15")
    assert b30.n_members.iloc[-1] == 1 and (b30.n_members.iloc[:-1] == 2).all()
    r = b30.iloc[0]
    assert r.open == s.open[0] and r.close == s.close[1] and r.high == s.high[1] and r.low == s.low[0]
    assert r.volume == s.volume[0] + s.volume[1]
    b60 = derive(s, "60m")
    assert len(b60) == 7 and b60.timestamp.iloc[-1] == pd.Timestamp("2024-03-05 15:15")
    assert (b60.n_members.iloc[:-1] == 4).all() and b60.n_members.iloc[-1] == 1
    assert b60.timestamp.iloc[1] == pd.Timestamp("2024-03-05 10:15")
    assert b60.close.iloc[0] == s.close[3] and b60.volume.iloc[0] == s.volume[:4].sum()


def test_avail_ts_last_member_plus_15m():
    src = synthetic_15m(10, seed=2)
    for tf in ("15m", "30m", "60m", "4h", "dayagg"):
        b = derive(src, tf)
        assert b.avail_ts.is_monotonic_increasing and b.avail_ts.is_unique
        # last member of each bucket: the source bar with the largest timestamp < avail_ts
        last = src.timestamp.values[np.searchsorted(src.timestamp.values, b.avail_ts.values - np.timedelta64(15, "m"))]
        assert (last == (b.avail_ts - QUARTER).values).all()
    d = derive(synthetic_day(30, seed=3), "day")
    assert (d.avail_ts == d.timestamp.dt.normalize() + pd.Timedelta(hours=15, minutes=30)).all()
    w = derive(synthetic_day(30, seed=3), "week")
    assert (w.avail_ts.dt.hour == 15).all() and (w.avail_ts.dt.minute == 30).all()
    assert (w.avail_ts.dt.weekday == 4).all()                       # full synthetic weeks end Friday
    assert w.avail_ts.is_monotonic_increasing


def test_incomplete_final_bucket_dropped():
    src = synthetic_15m(3, seed=4)
    last_day = src.timestamp.iloc[-1].normalize()
    cut = src[src.timestamp <= last_day + pd.Timedelta(hours=10, minutes=45)]    # last row 10:45
    at = lambda h, m: last_day + pd.Timedelta(hours=h, minutes=m)
    b60 = derive(cut, "60m")                     # 10:15 bucket has 10:15..10:45 -> incomplete
    assert at(10, 15) not in set(b60.timestamp) and b60.timestamp.iloc[-1] == at(9, 15)
    b30 = derive(cut, "30m")                     # 10:45 bucket has one of two members -> dropped
    assert at(10, 45) not in set(b30.timestamp) and b30.timestamp.iloc[-1] == at(10, 15)
    for tf in ("4h", "dayagg"):
        assert derive(cut, tf).timestamp.iloc[-1].normalize() < last_day
    # a bucket completed exactly at the cut is kept
    cut2 = src[src.timestamp <= at(11, 0)]
    assert derive(cut2, "60m").timestamp.iloc[-1] == at(10, 15)
    # complete series keeps its last bucket
    assert derive(src, "dayagg").timestamp.iloc[-1].normalize() == last_day
    assert derive(src, "30m").timestamp.iloc[-1] == at(15, 15)
    # weeks: the final week of the frame is always dropped
    d = synthetic_day(15, seed=5)
    w = derive(d, "week")
    assert len(w) == d.timestamp.dt.to_period("W-SUN").nunique() - 1
    assert w.avail_ts.iloc[-1] < d.timestamp.iloc[-1]


def test_week_grouping():
    ts = pd.bdate_range("2024-03-04", periods=10)            # Mon 03-04 .. Fri 03-15
    d = pd.DataFrame({"timestamp": ts, "open": np.arange(10) + 100.0, "high": np.arange(10) + 102.0,
                      "low": np.arange(10) + 99.0, "close": np.arange(10) + 101.0, "volume": np.ones(10) * 5})
    w = derive(d, "week")
    assert len(w) == 1                                       # 2nd week is the (dropped) final week
    r = w.iloc[0]
    assert r.timestamp == pd.Timestamp("2024-03-04")
    assert r.open == 100 and r.close == 105 and r.high == 106 and r.low == 99 and r.volume == 25
    assert r.n_members == 5
    assert r.avail_ts == pd.Timestamp("2024-03-08 15:30")
    # week starting mid-week (holiday Monday): stamped on first trading day
    d2 = d.iloc[1:].reset_index(drop=True)
    assert derive(d2, "week").timestamp.iloc[0] == pd.Timestamp("2024-03-05")
    assert set(TFS) >= {"15m", "week"}
