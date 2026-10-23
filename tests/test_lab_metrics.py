"""Unit tests for the extrema lab's pure metric functions."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.lab.metrics import (
    extract_crossings,
    match_events,
    shrink_mask,
)


def _scores(vals):
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01 09:15", periods=len(vals), freq="15min"),
        "close": 100.0,
        "p_min": vals,
        "p_max": 0.0,
    })


class TestExtractCrossings:
    def test_rising_edges_only(self):
        s = _scores([0.1, 0.95, 0.96, 0.2, 0.91, 0.3])
        assert extract_crossings(s, "p_min", 0.9) == [1, 4]

    def test_nan_prefix_counts_as_below(self):
        s = _scores([np.nan, np.nan, 0.95, 0.95])
        assert extract_crossings(s, "p_min", 0.9) == [2]

    def test_first_bar_crossing(self):
        s = _scores([0.95, 0.2])
        assert extract_crossings(s, "p_min", 0.9) == [0]

    def test_no_crossings(self):
        s = _scores([0.1, 0.5, 0.89])
        assert extract_crossings(s, "p_min", 0.9) == []


class TestMatchEvents:
    def test_perfect_match(self):
        res = match_events([10, 50], [10, 50], tol_bars=5)
        assert (res.tp, res.fp, res.fn) == (2, 0, 0)
        assert res.lags == [0, 0]
        assert res.precision == 1.0 and res.recall == 1.0

    def test_late_detection_within_tolerance(self):
        res = match_events([13], [10], tol_bars=5)
        assert res.tp == 1 and res.lags == [3]

    def test_outside_tolerance_is_fp_and_fn(self):
        res = match_events([20], [10], tol_bars=5)
        assert (res.tp, res.fp, res.fn) == (0, 1, 1)
        assert res.fp_idx == [20] and res.fn_idx == [10]

    def test_one_pred_cannot_match_two_truths(self):
        res = match_events([10], [8, 12], tol_bars=5)
        assert (res.tp, res.fn) == (1, 1)

    def test_nearest_pred_wins(self):
        res = match_events([7, 11], [10], tol_bars=5)
        assert res.tp == 1
        assert res.matched == [(10, 11)]
        assert res.fp == 1 and res.fp_idx == [7]

    def test_empty_inputs(self):
        res = match_events([], [], tol_bars=5)
        assert (res.tp, res.fp, res.fn) == (0, 0, 0)
        assert np.isnan(res.precision) and np.isnan(res.recall)


class TestCoverageMask:
    def test_shrink_erodes_edges(self):
        mask = np.zeros(20, dtype=bool)
        mask[5:15] = True
        s = shrink_mask(mask, 2)
        assert s[7:13].all()
        assert not s[5] and not s[6] and not s[13] and not s[14]

    def test_short_range_vanishes(self):
        mask = np.zeros(10, dtype=bool)
        mask[4:7] = True  # 3 bars < 2*tol
        assert not shrink_mask(mask, 2).any()

    def test_uncovered_truth_excluded(self):
        mask = np.zeros(100, dtype=bool)
        mask[0:50] = True
        # truth at 80 is outside coverage -> not an FN; pred at 20 matches truth 22
        res = match_events([20], [22, 80], tol_bars=5, mask=mask)
        assert (res.tp, res.fp, res.fn) == (1, 0, 0)

    def test_boundary_pred_not_penalised(self):
        # pred at 49, right at coverage edge: potential truth at 51 is unreviewed.
        # shrunk mask excludes the pred from FP counting.
        mask = np.zeros(100, dtype=bool)
        mask[0:50] = True
        res = match_events([49], [], tol_bars=5, mask=mask)
        assert res.fp == 0

    def test_interior_pred_still_fp(self):
        mask = np.zeros(100, dtype=bool)
        mask[0:50] = True
        res = match_events([25], [], tol_bars=5, mask=mask)
        assert res.fp == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
