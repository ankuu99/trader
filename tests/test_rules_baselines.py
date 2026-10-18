"""W5 — no-ML baselines: ou helper/add-on, rules pipeline, passthrough model."""
import math
from datetime import datetime, timedelta

import numpy as np
import pytest

import trader.features.registry  # noqa: F401  (registers the ou add-on)
from trader.features.addon_ou import OUAddon
from trader.features.addons import ADDONS
from trader.features.ou import ou_score
from trader.features.registry import build_feature_pipeline
from trader.features.rules_features import RulesFeaturePipeline
from trader.models.passthrough import PassthroughModel
from trader.models.registry import build_model
from trader.strategies.base import SignalType
from trader.strategies.lr_extrema import LRExtremaStrategy


def _c(close):
    return {"open": close, "high": close, "low": close, "close": close, "volume": 1000}


def _sine(n, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    return list(100 + 5 * np.sin(2 * np.pi * t / 30) + rng.normal(0, 0.3, n))


def test_ou_score_reverting():
    # n=165 -> last bar at phase 0.5 (a crest... use sin phase): trough at t where sin=-1
    closes = _sine(300)
    t_trough = 22 + 30 * 5   # sin(2*pi*22.5/30) = -1 -> index 22/23 area
    s_trough, hl = ou_score(closes[: t_trough + 1], 60)
    t_crest = 7 + 30 * 5
    s_crest, _ = ou_score(closes[: t_crest + 1], 60)
    assert math.isfinite(hl) and hl > 0
    assert s_trough < -1.0
    assert s_crest > 1.0


def test_ou_score_random_walk_guard():
    closes = [100 * 1.01 ** i for i in range(80)]
    assert ou_score(closes, 60) == (0.0, math.inf)
    assert ou_score(closes[:30], 60) == (0.0, math.inf)


def test_ou_addon():
    assert ADDONS["ou"] is OUAddon
    a = OUAddon({"window": 60})
    assert a.feature_names == ["ou_s", "ou_hl_norm"]
    assert a.min_history == 61
    vals = a.compute([_c(v) for v in _sine(200)])
    assert len(vals) == 2 and all(math.isfinite(v) for v in vals)
    assert 0.0 < vals[1] <= 2.0
    flat = a.compute([_c(100.0) for _ in range(80)])
    assert flat == [0.0, 2.0]
    pipe = build_feature_pipeline({"ou": {"enabled": True}})
    assert pipe.feature_names[-2:] == ["ou_s", "ou_hl_norm"]


def test_rules_rsi_bounce_ema():
    p = RulesFeaturePipeline({"rules": {"kind": "rsi_bounce_ema"}})
    # long uptrend (price far above the 50-EMA), 14 small declines (RSI low), then a small up-close
    closes = [100 + 2.0 * i for i in range(60)]
    for _ in range(14):
        closes.append(closes[-1] - 0.5)
    closes.append(closes[-1] + 0.3)
    assert list(p.compute([_c(v) for v in closes])) == [1.0, 0.0]
    flipped = closes[:-1] + [closes[-2] - 0.3]  # down-close: entry condition off
    assert p.compute([_c(v) for v in flipped])[0] == 0.0


def test_rules_lowest_turn():
    p = RulesFeaturePipeline({"rules": {"kind": "lowest_turn", "lowest_of": 20}})
    closes = [110 - i * 0.5 for i in range(25)] + [100.0]  # falling, last up-close
    closes[-2] = min(closes[:-1]) - 1  # prev bar is the low
    closes[-1] = closes[-2] + 1
    assert list(p.compute([_c(v) for v in closes])) == [1.0, 0.0]
    closes[-1] = closes[-2] - 0.5  # no up-close
    assert p.compute([_c(v) for v in closes])[0] == 0.0
    # top side
    up = [100 + i * 0.5 for i in range(25)] + [0.0]
    up[-2] = max(up[:-1]) + 1
    up[-1] = up[-2] - 1
    assert list(p.compute([_c(v) for v in up])) == [0.0, 1.0]


def test_rules_ou_graded():
    p = RulesFeaturePipeline({"rules": {"kind": "ou", "window": 60}})
    closes = _sine(300)
    seen = []
    for i in (22 + 150, 7 + 150):
        x = p.compute([_c(v) for v in closes[: i + 1]])
        assert all(0.0 <= v <= 1.0 for v in x)
        seen.append(x)
    assert seen[0][0] > 0.0
    assert seen[1][1] > 0.0
    assert p.compute([_c(v) for v in closes[:10]]) is None


def test_passthrough_model():
    m = PassthroughModel({})
    assert not m.is_trained
    m.fit(np.zeros((2, 2)), np.array([0, 1]))
    assert m.is_trained
    assert m.predict_proba(np.array([0.3, 0.8])) == (0.3, 0.8)
    assert m.feature_contributions(np.array([0.3, 0.8])) is None
    assert isinstance(build_model({"type": "passthrough"}), PassthroughModel)


def test_strategy_with_rules():
    params = {
        "warmup_bars": 60, "threshold": 0.99, "veto_threshold": 0.5, "retrain_every": 50,
        "extrema_order": 3, "hold_bars": 20,
        "features": {"type": "rules", "rules": {"kind": "lowest_turn", "lowest_of": 5}},
        "model": {"type": "passthrough"},
    }
    strat = LRExtremaStrategy("NSE:TEST", params)
    t0 = datetime(2025, 6, 2, 10, 0)
    sigs = []
    for i, v in enumerate(_sine(400)):
        c = {"open": v, "high": v + 0.1, "low": v - 0.1, "close": v, "volume": 1000,
             "timestamp": t0 + timedelta(minutes=15 * (i % 20), days=i // 20)}
        s = strat.on_candle(c)
        if s is not None and s.signal_type == SignalType.ENTRY:
            sigs.append(s)
            strat._pos.entry_price = None  # no fills in this harness
    assert len(sigs) >= 1


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        RulesFeaturePipeline({"rules": {"kind": "nope"}})
    with pytest.raises(ValueError):
        build_feature_pipeline({"type": "rules", "rules": {"kind": "nope"}})
