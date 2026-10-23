"""Feature add-on registry + LagPipeline (TD-018)."""

from collections import deque

import numpy as np

from trader.features import addons as addons_mod
from trader.features.addons import AddonPipeline, FeatureAddon, LagPipeline
from trader.features.extrema_features import ExtremaFeaturePipeline
from trader.features.registry import build_feature_pipeline
from trader.features.swing_features import SwingFeaturePipeline


def _candles(n=60):
    rng = np.random.default_rng(3)
    c = 100 + np.cumsum(rng.normal(0, 1, n))
    return [{"open": x, "high": x + 1, "low": x - 1, "close": float(x), "volume": 1000 + 10 * i}
            for i, x in enumerate(c)]


class _Dummy(FeatureAddon):
    name = "dummy"

    @property
    def feature_names(self):
        return ["d_close", "d_n"]

    @property
    def min_history(self):
        return 30

    def compute(self, candles):
        return [float(candles[-1]["close"]), float(len(candles))]


def test_default_pipeline_type_unchanged():
    assert type(build_feature_pipeline({})) is ExtremaFeaturePipeline
    assert type(build_feature_pipeline({"type": "swing"})) is SwingFeaturePipeline


def test_addon_appends_columns(monkeypatch):
    monkeypatch.setattr(addons_mod, "ADDONS", {"dummy": _Dummy})
    import trader.features.registry as reg
    monkeypatch.setattr(reg, "ADDONS", {"dummy": _Dummy})
    base = build_feature_pipeline({})
    pipe = build_feature_pipeline({"dummy": {"enabled": True}})
    assert isinstance(pipe, AddonPipeline)
    assert pipe.feature_names == base.feature_names + ["d_close", "d_n"]
    assert pipe.min_history == max(base.min_history, 30)
    cs = _candles()
    x, xb = pipe.compute(cs), base.compute(cs)
    assert len(x) == 8
    assert np.array_equal(x[:6], xb)
    assert x[6] == cs[-1]["close"] and x[7] == len(cs)
    assert pipe.compute(cs[:25]) is None
    # disabled -> plain base
    assert type(build_feature_pipeline({"dummy": {"enabled": False}})) is ExtremaFeaturePipeline


def test_lag_pipeline_values():
    base = build_feature_pipeline({})
    pipe = build_feature_pipeline({"lags": [2, 1]})
    assert isinstance(pipe, LagPipeline)
    cs = _candles()
    x = pipe.compute(cs)
    assert len(x) == 18
    assert np.array_equal(x[:6], base.compute(cs))
    assert np.array_equal(x[6:12], base.compute(cs[:-1]))
    assert np.array_equal(x[12:], base.compute(cs[:-2]))
    assert pipe.feature_names[6] == f"{base.feature_names[0]}_lag1"
    assert pipe.min_history == base.min_history + 2
    assert pipe.compute(cs[:pipe.min_history - 1]) is None


def test_lags_wrap_addons(monkeypatch):
    import trader.features.registry as reg
    monkeypatch.setattr(reg, "ADDONS", {"dummy": _Dummy})
    pipe = build_feature_pipeline({"dummy": {"enabled": True}, "lags": [1]})
    assert isinstance(pipe, LagPipeline) and isinstance(pipe.inner, AddonPipeline)
    cs = _candles()
    inner = pipe.inner
    x = pipe.compute(cs)
    assert len(x) == 16
    assert np.array_equal(x[:8], inner.compute(cs))
    assert np.array_equal(x[8:], inner.compute(cs[:-1]))
    assert pipe.feature_names[8:10] == [f"{n}_lag1" for n in inner.feature_names[:2]]
    assert pipe.feature_names[14:] == ["d_close_lag1", "d_n_lag1"]


def test_deque_input(monkeypatch):
    import trader.features.registry as reg
    monkeypatch.setattr(reg, "ADDONS", {"dummy": _Dummy})
    pipe = build_feature_pipeline({"dummy": {"enabled": True}, "lags": [1, 2]})
    cs = _candles()
    assert np.array_equal(pipe.compute(deque(cs)), pipe.compute(cs))
    assert pipe.compute(deque(cs)) is not None
