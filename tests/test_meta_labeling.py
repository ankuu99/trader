"""
Meta-labeling tests — triple-barrier labels, meta features, meta model, and the
MetaFilter gate (disabled no-op + enabled train/gate).
"""

import numpy as np
import pytest

from trader.features.indicators import atr_at, linreg_tstat
from trader.features.labels import triple_barrier_label, build_labeler, TrendScanningLabeler
from trader.features.meta_features import MetaFeaturePipeline
from trader.models.meta import MetaModel
from trader.strategies.meta_filter import MetaFilter


def _c(close, high=None, low=None, vol=1000):
    return {"open": close, "close": close,
            "high": high if high is not None else close + 0.5,
            "low": low if low is not None else close - 0.5,
            "volume": vol}


# --- triple_barrier_label ---------------------------------------------------

def test_tb_profit_hit_first():
    # entry 100, PT=105 (5%), SL=90 (10%); candle 2 spikes high to 106 → win
    candles = [_c(100), _c(101), _c(102, high=106), _c(103)]
    assert triple_barrier_label(candles, 0, profit_pct=5, stop_pct=10, max_bars=3) == 1


def test_tb_stop_hit_first():
    candles = [_c(100), _c(99), _c(95, low=89), _c(101)]
    assert triple_barrier_label(candles, 0, profit_pct=5, stop_pct=10, max_bars=3) == 0


def test_tb_tie_resolves_to_stop():
    # same candle touches both barriers → conservative loss
    candles = [_c(100), _c(100, high=106, low=89)]
    assert triple_barrier_label(candles, 0, profit_pct=5, stop_pct=10, max_bars=1) == 0


def test_tb_time_barrier_positive():
    candles = [_c(100), _c(101), _c(103)]  # neither barrier hit, ends up
    assert triple_barrier_label(candles, 0, profit_pct=20, stop_pct=20, max_bars=2) == 1


def test_tb_time_barrier_negative():
    candles = [_c(100), _c(99), _c(98)]
    assert triple_barrier_label(candles, 0, profit_pct=20, stop_pct=20, max_bars=2) == 0


def test_tb_incomplete_window_returns_none():
    # max_bars extends past available candles → unknown outcome → None (leakage guard)
    candles = [_c(100), _c(101)]
    assert triple_barrier_label(candles, 0, profit_pct=5, stop_pct=10, max_bars=5) is None


# --- MetaFeaturePipeline ----------------------------------------------------

def _series(n):
    return [_c(100 + 5 * np.sin(i / 6.0)) for i in range(n)]


def test_meta_features_shape_with_primary():
    p = MetaFeaturePipeline({"vol_bars": 20, "rsi_period": 14, "depth_bars": 50})
    assert p.compute(_series(40)) is None        # < min_history (50)
    feat = p.compute(_series(80), p_min=0.8, p_max=0.1, threshold=0.7)
    assert feat is not None and len(feat) == 9   # 6 context + 3 primary
    assert p.feature_names[-3:] == ["p_min", "p_max", "p_min_margin"]
    assert feat[-1] == pytest.approx(0.8 - 0.7)


def test_meta_features_without_primary_scores():
    p = MetaFeaturePipeline({"include_primary_scores": False, "depth_bars": 30})
    feat = p.compute(_series(60))
    assert len(feat) == 6


def test_meta_features_no_nan_on_flat_series():
    flat = [_c(50, high=50, low=50, vol=0) for _ in range(60)]
    feat = MetaFeaturePipeline({}).compute(flat, p_min=0.9, p_max=0.0, threshold=0.7)
    assert not np.isnan(feat).any()


# --- MetaModel --------------------------------------------------------------

@pytest.mark.parametrize("mtype", ["logistic", "xgboost"])
def test_meta_model_fit_predict(mtype):
    rng = np.random.default_rng(0)
    X = np.vstack([rng.normal(-1, 0.3, (40, 6)), rng.normal(1, 0.3, (40, 6))])
    y = np.array([0] * 40 + [1] * 40)
    m = MetaModel({"type": mtype})
    assert m.is_trained is False
    m.fit(X, y)
    assert m.is_trained
    p_win_pos = m.predict_proba(X[60])   # a class-1-like row
    p_win_neg = m.predict_proba(X[0])    # a class-0-like row
    assert 0.0 <= p_win_pos <= 1.0
    assert p_win_pos > p_win_neg


# --- MetaFilter -------------------------------------------------------------

def test_meta_filter_disabled_is_noop():
    mf = MetaFilter("NSE:TEST", {})            # no meta_label block
    assert mf.enabled is False
    assert mf.allow(None) == (True, 1.0)
    # train is a no-op (no crash, stays untrained)
    mf.train([], None, None, 0.7, 1.0, {"profit_pct": 5, "stop_pct": 10, "max_bars": 50})
    assert mf.is_trained is False


def test_meta_filter_allow_passthrough_when_untrained():
    mf = MetaFilter("NSE:TEST", {"meta_label": {"enabled": True}})
    assert mf.enabled is True and mf.is_trained is False
    # untrained → pass through (gate only acts once trained)
    assert mf.allow(np.zeros(9)) == (True, 1.0)


def test_meta_filter_sizing_disabled_returns_none():
    mf = MetaFilter("NSE:TEST", {"meta_label": {"enabled": True, "meta_threshold": 0.55}})
    assert mf.size_weight(0.9) is None      # sizing off => full size


def test_meta_filter_sizing_maps_pwin_to_fraction():
    mf = MetaFilter("NSE:TEST", {"meta_label": {
        "enabled": True, "meta_threshold": 0.55,
        "sizing": {"enabled": True, "min_fraction": 0.5, "max_fraction": 1.0},
    }})
    assert mf.size_weight(0.55) == pytest.approx(0.5)    # barely passes -> min
    assert mf.size_weight(1.0) == pytest.approx(1.0)     # fully confident -> max
    mid = mf.size_weight(0.775)                          # halfway
    assert mid == pytest.approx(0.75, abs=0.02)
    assert mf.size_weight(0.40) == pytest.approx(0.5)    # below threshold clamps to min


def test_meta_filter_barrier_defaults_inherit_exits():
    mf = MetaFilter("NSE:TEST", {"meta_label": {"enabled": True}})
    assert mf._barriers({"profit_pct": 5, "stop_pct": 20, "max_bars": 200}) == (5.0, 20.0, 200)
    mf2 = MetaFilter("NSE:TEST", {"meta_label": {"enabled": True, "barriers": {"profit_pct": 3}}})
    assert mf2._barriers({"profit_pct": 5, "stop_pct": 20, "max_bars": 200}) == (3.0, 20.0, 200)


# --- Phase 3a: ATR helpers + ATR-scaled barriers ----------------------------

def test_atr_at_basic():
    candles = [_c(100, high=101, low=99) for _ in range(20)]
    assert atr_at(candles, 19, period=14) == pytest.approx(2.0, abs=0.5)
    assert atr_at(candles, 0) == 0.0          # no history before idx 0


def test_linreg_tstat_signs():
    up = [float(i) for i in range(20)]
    flat = [5.0] * 20
    s_up, t_up = linreg_tstat(up)
    assert s_up > 0 and t_up > 100             # perfect line -> huge t-stat
    _s, t_flat = linreg_tstat(flat)
    assert t_flat == pytest.approx(0.0)


def test_tb_atr_barriers_used_when_supplied():
    # entry 100, ATR 2, atr_mult_pt 2 => PT=104; candle spikes to 105 -> win
    candles = [_c(100), _c(101), _c(102, high=105), _c(103)]
    label = triple_barrier_label(
        candles, 0, profit_pct=99, stop_pct=99, max_bars=3,
        atr=2.0, atr_mult_pt=2.0, atr_mult_sl=2.0,
    )
    assert label == 1     # ATR PT (104) hit, not the 99% pct barrier


# --- Phase 3b: trend-scanning labeler ---------------------------------------

def test_trend_scan_factory():
    lab = build_labeler("NSE:TEST", {"labels": {"type": "trend_scan"}})
    assert isinstance(lab, TrendScanningLabeler)


def test_trend_scan_labels_both_classes():
    # Up ramp then down ramp then up ramp -> both up- and down-trend regions.
    closes = ([100 + 2 * i for i in range(40)]      # up
              + [180 - 2 * i for i in range(40)]     # down
              + [100 + 2 * i for i in range(40)])    # up
    candles = [_c(c) for c in closes]
    lab = TrendScanningLabeler("NSE:TEST", {"labels": {"trend_scan": {
        "min_bars": 5, "max_bars": 20, "t_threshold": 2.0}}})
    idx, classes = lab.label(candles)
    assert 0 in classes and 1 in classes        # both bottoms (up-trend) and tops (down-trend)
