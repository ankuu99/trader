"""Unit tests for CausalGaussianSmoother (features.smoothing) and its wiring
into the feature pipelines."""

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trader.features.extrema_features import ExtremaFeaturePipeline
from trader.features.smoothing import (CausalGaussianSmoother, build_smoother,
                                       gaussian_kernel)

import pandas as pd


def _candles(closes):
    ts = pd.date_range("2025-01-01 09:15", periods=len(closes), freq="15min")
    return [{"timestamp": t, "close": float(c), "open": float(c),
             "high": float(c) + 0.5, "low": float(c) - 0.5, "volume": 1000}
            for t, c in zip(ts, closes)]


class TestKernel:
    def test_normalised_and_symmetric(self):
        k = gaussian_kernel(21)
        assert len(k) == 21
        assert abs(k.sum() - 1.0) < 1e-12
        assert np.allclose(k, k[::-1])
        assert k[10] == k.max()

    def test_even_window_bumped_to_odd(self):
        sm = CausalGaussianSmoother({"window": 20})
        assert sm._window == 21


class TestCausality:
    def test_values_never_change_when_future_arrives(self):
        rng = np.random.default_rng(7)
        closes = 100 + np.cumsum(rng.normal(0, 0.5, 400))
        candles = _candles(closes)
        # A sees only the first 250 bars; B sees everything. Values on the
        # overlap must be identical — the smoother must not read the future.
        a = CausalGaussianSmoother({"window": 21})
        b = CausalGaussianSmoother({"window": 21})
        va = a.series(candles[:250], 250)
        vb = b.series(candles, 400)
        assert np.allclose(va, vb[:250])

    def test_cache_returns_stable_values(self):
        closes = 100 + 5 * np.sin(np.arange(300) / 20.0)
        candles = _candles(closes)
        sm = CausalGaussianSmoother({"window": 21})
        first = sm.series(candles, 300)
        again = sm.series(candles, 50)
        assert np.allclose(first[-50:], again)


class TestSmoothing:
    def test_noise_is_suppressed(self):
        rng = np.random.default_rng(3)
        t = np.arange(2000)
        clean = 100 + 5 * np.sin(2 * math.pi * t / 400)
        noisy = clean + rng.normal(0, 1.0, len(t))
        sm = CausalGaussianSmoother({"window": 21})
        smoothed = np.array(sm.series(_candles(noisy), len(t)))
        raw_err = np.abs(noisy[100:] - clean[100:]).mean()
        sm_err = np.abs(smoothed[100:] - clean[100:]).mean()
        # causal smoothing can't match a centered kernel (the extension re-weights
        # the current bar), but must still cut noise error meaningfully
        assert sm_err < raw_err * 0.7

    def test_edge_modes_differ_on_a_decline(self):
        closes = list(np.linspace(200, 100, 300))  # steady fall, zero accel
        const = CausalGaussianSmoother({"window": 21, "edge": "constant"})
        linear = CausalGaussianSmoother({"window": 21, "edge": "linear"})
        vc = const.series(_candles(closes), 10)
        vl = linear.series(_candles(closes), 10)
        # linear extension continues the fall; constant flattens — so the
        # linear-smoothed edge sits strictly below the constant-smoothed one
        assert all(l < c for l, c in zip(vl, vc))

    def test_accel_mode_runs_and_tracks_signal(self):
        t = np.arange(600)
        closes = 100 + 5 * np.sin(2 * math.pi * t / 150)
        sm = CausalGaussianSmoother({"window": 21, "edge": "accel"})
        vals = np.array(sm.series(_candles(closes), 600))
        assert np.isfinite(vals).all()
        assert np.abs(vals[50:] - closes[50:]).mean() < 1.0

    def test_build_smoother_gating(self):
        assert build_smoother(None) is None
        assert build_smoother({"smoothing": {"enabled": False}}) is None
        assert build_smoother({"smoothing": {"enabled": True}}) is not None


class TestPipelineWiring:
    def test_disabled_is_byte_identical_to_no_config(self):
        closes = 100 + 5 * np.sin(np.arange(100) / 10.0)
        candles = _candles(closes)
        base = ExtremaFeaturePipeline({})
        off = ExtremaFeaturePipeline({"smoothing": {"enabled": False}})
        assert np.array_equal(base.compute(candles), off.compute(candles))

    def test_enabled_changes_only_slope_features(self):
        rng = np.random.default_rng(11)
        closes = 100 + np.cumsum(rng.normal(0, 0.8, 200))
        candles = _candles(closes)
        raw = ExtremaFeaturePipeline({}).compute(candles)
        sm = ExtremaFeaturePipeline(
            {"smoothing": {"enabled": True, "window": 21}}).compute(candles)
        # [volume_ratio, norm_price] untouched; slopes recomputed on smoothed closes
        assert np.array_equal(raw[:2], sm[:2])
        assert not np.array_equal(raw[2:], sm[2:])
        assert np.isfinite(sm).all()
