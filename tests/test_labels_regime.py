"""Unit tests for ZigZagLabeler / collapse_clusters and the regime measures."""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trader.features.labels import (ZigZagLabeler, build_labeler,
                                    collapse_clusters, zigzag_pivots)
from trader.features.regime import (_rolling_tstat, efficiency_ratio_at,
                                    regime_states, regime_vector_at,
                                    slope_tstat_at, variance_ratio_at)


def _candles(closes):
    return [{"close": float(c), "open": float(c), "high": float(c) + 0.5,
             "low": float(c) - 0.5, "volume": 1000} for c in closes]


class TestCollapseClusters:
    def test_plateau_run_collapses_to_centre(self):
        assert collapse_clusters([10, 11, 12, 13, 14], max_gap=2) == [12]

    def test_separate_clusters_survive(self):
        # centre of [10, 11] is index len//2 = 1 -> 11
        assert collapse_clusters([10, 11, 50, 51, 52], max_gap=3) == [11, 51]

    def test_empty(self):
        assert collapse_clusters([], max_gap=5) == []


class TestZigZagPivots:
    def test_sine_finds_one_pivot_per_half_cycle(self):
        t = np.arange(1000)
        closes = 100 + 5 * np.sin(2 * math.pi * t / 200)  # 5% amplitude
        lows, highs = zigzag_pivots(closes.tolist(), reversal_pct=2.0)
        assert 4 <= len(lows) <= 6 and 4 <= len(highs) <= 6
        # pivots must sit at the actual extremes (within a couple of bars)
        for lo in lows:
            assert closes[lo] <= closes[max(0, lo - 5):lo + 6].min() + 1e-9

    def test_rising_baseline_does_not_hide_dips(self):
        t = np.arange(2000)
        closes = 100 + 4 * np.sin(2 * math.pi * t / 250) + 0.01 * t  # strong trend
        lows, _ = zigzag_pivots(closes.tolist(), reversal_pct=1.5)
        assert len(lows) >= 6  # roughly one per cycle

    def test_monotonic_series_yields_no_interior_pivots(self):
        closes = list(np.linspace(100, 200, 500))
        lows, highs = zigzag_pivots(closes, reversal_pct=2.0)
        # the series start is legitimately its minimum; nothing else qualifies
        assert lows in ([], [0])
        assert highs == []

    def test_labeler_classes(self):
        t = np.arange(1000)
        closes = 100 + 5 * np.sin(2 * math.pi * t / 200)
        lab = ZigZagLabeler("T", {"labels": {"zigzag": {"reversal_pct": 2.0}}})
        idx, cls = lab.label(_candles(closes))
        assert set(cls) == {0, 1}
        assert len(idx) == len(cls) > 0

    def test_build_labeler_zigzag(self):
        lab = build_labeler("T", {"labels": {"type": "zigzag"}})
        assert isinstance(lab, ZigZagLabeler)


class TestCollapseTiesOption:
    def test_plateau_extrema_single_labeled(self):
        # square-ish wave with flat plateaus: without the fix every tied bar in a
        # plateau is an extremum
        closes = ([100] * 5 + [90] * 5 + [100] * 5 + [90] * 5) * 8
        cand = _candles(closes)
        base = build_labeler("T", {"extrema_order": 3})
        fixed = build_labeler("T", {"extrema_order": 3,
                                    "labels": {"collapse_ties": True}})
        i_base, _ = base.label(cand)
        i_fix, _ = fixed.label(cand)
        assert len(i_fix) < len(i_base)


class TestRegimeMeasures:
    def test_er_near_one_on_ramp(self):
        closes = list(np.linspace(100, 200, 300))
        assert efficiency_ratio_at(closes, 100) > 0.99

    def test_er_near_zero_on_fast_oscillation(self):
        t = np.arange(400)
        closes = (100 + 3 * np.sin(2 * math.pi * t / 10)).tolist()
        assert efficiency_ratio_at(closes, 100) < 0.1

    def test_vr_below_one_on_mean_reverting_noise(self):
        # iid noise around a level is maximally mean-reverting: VR ~ 1/q
        rng = np.random.default_rng(0)
        closes = (100 + rng.normal(0, 1, 3000)).tolist()
        assert variance_ratio_at(closes, 400) < 0.5

    def test_vr_above_one_on_persistent_returns(self):
        # positively autocorrelated returns (AR(1), phi=0.6) -> VR > 1
        rng = np.random.default_rng(0)
        r = np.zeros(3000)
        for i in range(1, 3000):
            r[i] = 0.6 * r[i - 1] + rng.normal(0, 0.001)
        closes = (100 * np.exp(np.cumsum(r))).tolist()
        assert variance_ratio_at(closes, 400) > 1.5

    def test_tstat_sign_matches_trend(self):
        up = list(np.linspace(100, 120, 300))
        down = list(np.linspace(120, 100, 300))
        assert slope_tstat_at(up, 200) > 10
        assert slope_tstat_at(down, 200) < -10

    def test_rolling_tstat_matches_pointwise(self):
        rng = np.random.default_rng(1)
        y = np.cumsum(rng.normal(0, 1, 200)) + 50
        w = 60
        roll = _rolling_tstat(y, w)
        for i in (80, 150, 199):
            assert roll[i] == pytest.approx(slope_tstat_at(y[: i + 1].tolist(), w), rel=1e-6)

    def test_regime_vector_shape_and_fallbacks(self):
        v = regime_vector_at([100.0] * 30, (100, 400, 1600))
        assert len(v) == 9
        assert v[0] == 0.5 and v[1] == 1.0 and v[2] == 0.0  # neutral fallbacks

    def test_regime_states_on_composite(self):
        n = 4000
        t = np.arange(n, dtype=float)
        closes = np.concatenate([
            100 + 2 * np.sin(2 * math.pi * t[:2000] / 100),   # sideways
            np.linspace(100, 160, 2000),                       # strong uptrend
        ])
        states = regime_states(closes, (100, 400, 1600))
        assert states[0] == "NA"                     # pre-warmup
        assert (states[3000:] == "UP").mean() > 0.9  # deep in the ramp
        mid = states[1700:1900]
        assert (mid == "SIDEWAYS").mean() > 0.5


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))


# --- Volatility-scaled zigzag reversal ---

def _sine_candles(n=300, amp_pct=6.0, period=60, base=100.0, seed=7):
    import math, random
    rng = random.Random(seed)
    out = []
    for i in range(n):
        px = base * (1 + amp_pct / 100 * math.sin(2 * math.pi * i / period))
        out.append({"close": px + rng.gauss(0, 0.1), "high": px, "low": px,
                    "open": px, "volume": 1000, "timestamp": i})
    return out


def test_vol_scaled_reversal_tracks_volatility():
    from trader.features.labels import ZigZagLabeler
    lab = ZigZagLabeler("T", {"labels": {"zigzag": {
        "reversal_pct": 5.0, "vol_scaled": {"enabled": True, "k": 2.5}}}})
    quiet = [100 * (1 + 0.001) ** i for i in range(100)]          # ~0.1%/bar drift, no noise
    wild = []
    px = 100.0
    import random
    rng = random.Random(3)
    for _ in range(100):
        px *= 1 + rng.gauss(0, 0.03)                              # σ ≈ 3%/bar
        wild.append(px)
    r_quiet = lab._effective_reversal_pct(quiet)
    r_wild = lab._effective_reversal_pct(wild)
    assert r_quiet < r_wild
    assert r_quiet >= 1.0           # min clamp
    assert r_wild <= 10.0           # max clamp
    assert 5.0 < r_wild             # 2.5 × ~3% ≈ 7.5


def test_vol_scaled_disabled_uses_fixed():
    from trader.features.labels import ZigZagLabeler
    lab = ZigZagLabeler("T", {"labels": {"zigzag": {"reversal_pct": 4.0}}})
    assert lab._effective_reversal_pct([100.0] * 50) == 4.0


def test_vol_scaled_short_history_falls_back():
    from trader.features.labels import ZigZagLabeler
    lab = ZigZagLabeler("T", {"labels": {"zigzag": {
        "reversal_pct": 4.0, "vol_scaled": {"enabled": True, "k": 2.0}}}})
    assert lab._effective_reversal_pct([100.0, 101.0]) == 4.0


def test_vol_scaled_labeler_still_labels():
    from trader.features.labels import ZigZagLabeler
    lab = ZigZagLabeler("T", {"labels": {"zigzag": {
        "reversal_pct": 99.0,   # fixed value would find nothing
        "vol_scaled": {"enabled": True, "k": 1.5}},
        "neutral": {"enabled": True, "ratio": 2.0}}})
    idx, cls = lab.label(_sine_candles())
    assert len(idx) > 10
    assert {0, 1, 2} == set(cls)
