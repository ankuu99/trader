"""Unit tests for AvgTrendLabeler (Bruni et al. 2026 averaged directional labels)
and the lab's transition-index scoring for dense labelers."""

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.lab.metrics import transition_indices
from trader.features.labels import AvgTrendLabeler, build_labeler


def _candles(closes):
    return [{"close": float(c), "open": float(c), "high": float(c) + 0.5,
             "low": float(c) - 0.5, "volume": 1000} for c in closes]


def _labeler(**avg_trend):
    return AvgTrendLabeler("TEST", {"labels": {"type": "avg_trend",
                                               "avg_trend": avg_trend}})


class TestAvgTrendLabeler:
    def test_factory_and_dense_flag(self):
        lab = build_labeler("TEST", {"labels": {"type": "avg_trend"}})
        assert isinstance(lab, AvgTrendLabeler)
        assert lab.dense is True

    def test_sine_transitions_sit_near_extremes(self):
        t = np.arange(1500)
        period = 300
        closes = 100 + 5 * np.sin(2 * math.pi * t / period)
        indices, classes = _labeler(window=10).label(_candles(closes))
        dips, peaks = transition_indices(indices, classes)
        assert len(dips) >= 4 and len(peaks) >= 4
        # true minima at 3/4·period + k·period; label flips lag by ~window/2
        for d in dips:
            nearest = min(abs((d % period) - period * 3 / 4),
                          abs((d % period) - period * 3 / 4 + period),
                          abs((d % period) - period * 3 / 4 - period))
            assert nearest <= 12, f"dip flip at {d} too far from a trough"

    def test_labels_are_dense_and_two_sided(self):
        t = np.arange(1000)
        closes = 100 + 5 * np.sin(2 * math.pi * t / 200)
        indices, classes = _labeler(window=10).label(_candles(closes))
        # every eligible bar labeled: [max(20, w-1), n-1-w]
        assert indices[0] == 20 and indices[-1] == 989
        assert len(indices) == 989 - 20 + 1
        assert classes.count(0) > 100 and classes.count(1) > 100

    def test_truncation_guard_excludes_unresolved_futures(self):
        closes = list(100 + np.sin(np.arange(400) / 20.0) * 5)
        w = 25
        indices, _ = _labeler(window=w).label(_candles(closes))
        assert max(indices) <= len(closes) - 1 - w
        assert min(indices) >= max(20, w - 1)

    def test_monotonic_series_is_one_sided_and_rejected(self):
        closes = list(np.linspace(100, 200, 500))
        indices, classes = _labeler(window=10).label(_candles(closes))
        assert (indices, classes) == ([], [])

    def test_deadband_drops_flat_regions(self):
        # flat first half, sine second half — deadband should drop the flat bars
        flat = np.full(500, 100.0)
        wave = 100 + 5 * np.sin(2 * math.pi * np.arange(500) / 100)
        closes = np.concatenate([flat, wave])
        base_idx, _ = _labeler(window=10).label(_candles(closes))
        db_idx, _ = _labeler(window=10, deadband_pct=0.25).label(_candles(closes))
        flat_kept = [i for i in db_idx if i < 480]
        assert len(db_idx) < len(base_idx)
        assert len(flat_kept) < 20  # nearly the whole flat region dropped

    def test_stride_subsamples(self):
        closes = 100 + 5 * np.sin(2 * math.pi * np.arange(1000) / 200)
        full, _ = _labeler(window=10).label(_candles(closes))
        strided, _ = _labeler(window=10, stride=5).label(_candles(closes))
        assert len(strided) == math.ceil(len(full) / 5)
        assert set(strided) <= set(full)

    def test_short_series_returns_empty(self):
        assert _labeler(window=10).label(_candles([100.0] * 30)) == ([], [])


class TestTransitionIndices:
    def test_flips_only(self):
        idx = [10, 11, 12, 13, 14, 15]
        cls = [1, 1, 0, 0, 1, 0]
        dips, peaks = transition_indices(idx, cls)
        assert dips == [12, 15]
        assert peaks == [14]

    def test_neutral_class_ignored(self):
        idx = [1, 2, 3, 4]
        cls = [1, 2, 0, 2]
        dips, peaks = transition_indices(idx, cls)
        assert dips == [3] and peaks == []

    def test_no_flip_no_events(self):
        assert transition_indices([1, 2, 3], [0, 0, 0]) == ([], [])
        assert transition_indices([], []) == ([], [])
