"""
Plan 5 — WindowFeaturePipeline + MLPModel tests.

Covers the window vector shape/normalization, the feature-pipeline factory
default (parity-preserving), and the MLP model's fit/predict contract.
"""

import numpy as np
import pytest

from trader.features.extrema_features import ExtremaFeaturePipeline
from trader.features.registry import build_feature_pipeline
from trader.features.window_features import WindowFeaturePipeline
from trader.models.mlp import MLPModel
from trader.models.registry import build_model


def _candles(n: int) -> list[dict]:
    out = []
    for i in range(n):
        c = 100.0 + 5.0 * np.sin(i / 6.0)
        out.append({
            "open": c, "high": c + 1.0, "low": c - 1.0,
            "close": c, "volume": 1000 + (i % 7) * 50,
        })
    return out


# --- factory ---------------------------------------------------------------

def test_factory_default_is_extrema():
    assert isinstance(build_feature_pipeline({}), ExtremaFeaturePipeline)
    assert isinstance(build_feature_pipeline(None), ExtremaFeaturePipeline)


def test_factory_window():
    p = build_feature_pipeline({"type": "window", "window": 16})
    assert isinstance(p, WindowFeaturePipeline)
    assert p.min_history == 16


def test_factory_unknown_raises():
    with pytest.raises(ValueError):
        build_feature_pipeline({"type": "nope"})


# --- window pipeline -------------------------------------------------------

def test_window_shape_and_min_history():
    p = WindowFeaturePipeline({"window": 20})
    assert p.compute(_candles(19)) is None
    feat = p.compute(_candles(40))
    assert feat is not None
    assert len(feat) == 20 * 3        # close, volume, norm_price
    assert len(p.feature_names) == 60


def test_window_channel_selection():
    p = WindowFeaturePipeline({"window": 10, "channels": ["close"]})
    feat = p.compute(_candles(30))
    assert len(feat) == 10


def test_window_close_channel_is_zscored():
    p = WindowFeaturePipeline({"window": 20, "channels": ["close"]})
    feat = p.compute(_candles(40))
    # z-score => ~zero mean, unit std within the window
    assert abs(float(np.mean(feat))) < 1e-9
    assert abs(float(np.std(feat)) - 1.0) < 1e-6


def test_window_flat_series_is_zero_not_nan():
    flat = [{"open": 50, "high": 50, "low": 50, "close": 50, "volume": 0} for _ in range(30)]
    p = WindowFeaturePipeline({"window": 20})
    feat = p.compute(flat)
    assert feat is not None
    assert not np.isnan(feat).any()


def test_window_bad_channel_raises():
    with pytest.raises(ValueError):
        WindowFeaturePipeline({"channels": ["close", "rsi"]})


# --- MLP model -------------------------------------------------------------

def test_mlp_registered():
    m = build_model({"type": "mlp"})
    assert isinstance(m, MLPModel)
    assert m.is_trained is False


def test_mlp_fit_predict_contract():
    rng = np.random.default_rng(0)
    # Two separable blobs so the net can actually learn something.
    X0 = rng.normal(-1.0, 0.3, size=(40, 8))
    X1 = rng.normal(1.0, 0.3, size=(40, 8))
    X = np.vstack([X0, X1])
    y = np.array([0] * 40 + [1] * 40)
    m = MLPModel({"hidden_layer_sizes": [8], "max_iter": 500})
    m.fit(X, y)
    assert m.is_trained
    p_min, p_max = m.predict_proba(X0[0])
    assert 0.0 <= p_min <= 1.0 and 0.0 <= p_max <= 1.0
    assert abs((p_min + p_max) - 1.0) < 1e-6
    assert p_min > p_max          # an X0-like point should read as class 0


def test_mlp_is_deterministic():
    rng = np.random.default_rng(1)
    X = rng.normal(0, 1, size=(60, 6))
    y = np.array([0, 1] * 30)
    a = MLPModel({"hidden_layer_sizes": [6], "max_iter": 200}); a.fit(X, y)
    b = MLPModel({"hidden_layer_sizes": [6], "max_iter": 200}); b.fit(X, y)
    assert a.predict_proba(X[0]) == b.predict_proba(X[0])
