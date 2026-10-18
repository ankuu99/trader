"""TradeableLabeler (`labels.type: tradeable`) + simulate_exit_outcomes(indices=)."""

import logging
import math
import time

import numpy as np

from trader.core.config import flatten_strategy_params
from trader.features.labels import ExtremaLabeler, TradeableLabeler, build_labeler
from trader.policy.outcome import simulate_exit_outcomes
from trader.strategies.lr_extrema import LRExtremaStrategy


def _candles(closes, volume=1000):
    return [{"open": c, "high": c + 1, "low": c - 1, "close": c, "volume": volume,
             "timestamp": None} for c in closes]


def _params(tradeable=None, **over):
    nested = {
        "extrema_order": 2,
        "exits": {"trailing": {"profit_pct": 5}, "stale": {"check_bars": 5, "min_gain_pct": 0.5},
                  "hold_bars": 30, "hard_stop": {"stop_pct": 20}},
        "labels": {"type": "tradeable", "tradeable": tradeable or {}},
    }
    nested.update(over)
    return flatten_strategy_params(nested)


# Two paying V's (minima 94 and 97, each rallies >= +5 % within a few bars, maxima at 112/114)
# then a drop to a failing flat minimum (90) followed by a drift too slow to arm the trail.
_A = [100, 98, 96, 95, 94, 96, 98, 100, 103, 106, 108, 110, 111, 112, 110]
_B = [105, 100, 97, 100, 103, 106, 109, 112, 114, 112]
_C = [108, 104, 100, 96, 92, 90]
_FLAT = [90.1, 90.2, 90.1, 90.3, 90.2, 90.3, 90.2, 90.3, 90.2, 90.3, 90.2, 90.3]
_SERIES = _A + _B + _C + _FLAT
_FAIL = _SERIES.index(90)


def _labelled(params, closes=_SERIES):
    idx, cls = TradeableLabeler("T", params).label(_candles(closes))
    return {c: [i for i, k in zip(idx, cls) if k == c] for c in (0, 1, 2)}, idx, cls


def test_paying_minimum_is_class0():
    d, _, _ = _labelled(_params())
    assert 4 in d[0] and 17 in d[0]


def test_failing_minimum_is_neutral():
    d, _, _ = _labelled(_params())
    fail = _FAIL
    assert fail in d[2] and fail not in d[0]


def test_failed_drop_mode():
    d, idx, _ = _labelled(_params({"failed_class": "drop"}))
    assert _FAIL not in idx
    assert d[2] == []


def test_unresolved_tail_dropped():
    # minimum two bars before the end of the window; no +5 % and hold not reached -> NaN
    closes = _A + _B + _C[:-1] + [90, 90.2, 90.1]
    p = _params()
    ret = simulate_exit_outcomes(closes, p)[1]
    mn = closes.index(90)
    assert mn == len(closes) - 3 and math.isnan(ret[mn])
    d, idx, _ = _labelled(p, closes)
    assert mn not in idx


def test_maxima_class1_unchanged():
    p = _params()
    d, _, _ = _labelled(p)
    _, maxima = __import__("trader.features.indicators", fromlist=["x"]).find_local_extrema(
        [c["close"] for c in _candles(_SERIES)], 2)
    assert d[1] == list(maxima)
    ei, ec = ExtremaLabeler("T", p).label(_candles(_SERIES))
    assert d[1] == [i for i, k in zip(ei, ec) if k == 1]


def test_all_candidates_stride():
    p = _params({"candidates": "all", "stride": 3})
    closes = [100 + 8 * math.sin(i / 5.0) for i in range(160)]
    d, idx, cls = _labelled(p, closes)
    assert d[0] and d[1] and d[2]
    assert len(set(idx)) == len(idx)
    allowed = set(range(20, len(closes), 3))
    assert set(d[0]) | set(d[2]) <= allowed
    assert TradeableLabeler("T", p).dense is True
    assert TradeableLabeler("T", _params()).dense is False


def test_fallback_geometric(caplog):
    # oscillation too shallow to ever pay +5 % -> no class 0 from simulation
    closes = [100, 101, 102, 101, 100, 99, 100, 101, 102, 101, 100, 99] * 6
    p = _params()
    ei, ec = ExtremaLabeler("T", p).label(_candles(closes))
    geo0 = [i for i, k in zip(ei, ec) if k == 0]
    with caplog.at_level(logging.WARNING):
        d, _, _ = _labelled(p, closes)
    assert d[0] == geo0 and d[0] and d[2] == []
    assert any("falling back" in r.message for r in caplog.records)


def test_outcome_indices_subset():
    rng = np.random.default_rng(1)
    closes = 100 + np.cumsum(rng.normal(0, 1, 120))
    p = _params()
    g, r, e = simulate_exit_outcomes(closes, p)
    for i in (25, 60, 90):
        g1, r1, e1 = simulate_exit_outcomes(closes, p, indices=[i])
        assert g1[i] == g[i] and e1[i] == e[i]
        assert (math.isnan(r1[i]) and math.isnan(r[i])) or r1[i] == r[i]
        others = [j for j in range(len(closes)) if j != i]
        assert not g1[others].any() and np.isnan(r1[others]).all()


def test_strategy_trains_with_tradeable():
    n = 400
    closes = [100 + 8 * math.sin(i / 6.0) + 0.02 * i for i in range(n)]
    params = _params(
        warmup_bars=5, retrain_every=50, lookback_bars=400,
        exits={"trailing": {"profit_pct": 5}, "stale": {"check_bars": 20, "min_gain_pct": 0.5},
               "hold_bars": 60, "hard_stop": {"stop_pct": 20}})
    strat = LRExtremaStrategy("NSE:TEST", params)
    assert isinstance(strat._labeler, TradeableLabeler)
    t0 = time.perf_counter()
    import datetime as dt
    t = dt.datetime(2025, 1, 1, 9, 15)
    for i, c in enumerate(_candles(closes)):
        c["timestamp"] = t + dt.timedelta(minutes=15 * i)
        c["instrument"] = "NSE:TEST"
        strat.on_candle(c)
    print("test9 train seconds", time.perf_counter() - t0)
    assert strat._model.is_trained
    s = strat.score_current()
    assert s is not None and len(s) == 2 and all(isinstance(v, float) for v in s)


def test_label_timing_1200_all_stride5(capsys):
    rng = np.random.default_rng(2)
    closes = list(100 + np.cumsum(rng.normal(0, 0.6, 1200)))
    lab = build_labeler("T", _params({"candidates": "all", "stride": 5}))
    t0 = time.perf_counter()
    idx, cls = lab.label(_candles(closes))
    print("label() 1200 candles all/stride5 seconds", time.perf_counter() - t0, len(idx))
    assert idx
