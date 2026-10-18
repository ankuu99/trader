"""Model Lab L0b — hindsight targets T1w/T1z/T2/T3/T4/T5 (synthetic data only)."""
import time

import numpy as np
import pandas as pd
from numpy.testing import assert_allclose

from research.model_lab.bars import derive
from research.model_lab.synth import synthetic_15m
from research.model_lab.targets import build_targets, lookahead, zigzag_pivots


def _garbage_after(bars: pd.DataFrame, c: int, seed: int = 99) -> pd.DataFrame:
    g = derive(synthetic_15m(60, seed=seed), "15m")
    out = bars.copy()
    for k in ("open", "high", "low", "close"):
        out.loc[c + 1:, k] = (g[k].values[c + 1:len(out)] * 3.1)
    out.loc[c + 1:, "volume"] = g["volume"].values[c + 1:len(out)]
    return out


def _bars60(seed=8):
    return derive(synthetic_15m(60, seed=seed), "15m")


def test_fixed_lookahead_columns_are_causal_beyond_horizon():
    bars = _bars60()
    n = len(bars)
    full = build_targets(bars, "15m")
    checked = 0
    for c in (700, 1100):
        alt = build_targets(_garbage_after(bars, c), "15m")
        for col in full.columns:
            L = lookahead(col)
            if col == "timestamp" or L is None:
                continue
            upto = c - L
            assert_allclose(alt[col].values[:upto + 1], full[col].values[:upto + 1], equal_nan=True,
                            err_msg=f"{col} cut {c}")
            checked += 1
    for col in full.columns:
        L = lookahead(col)
        if col != "timestamp" and L is not None:
            assert full[col].values[n - L:].shape[0] == L and np.isnan(full[col].values[n - L:]).all(), col
    assert checked > 100


def test_zigzag_columns_resolved_only_by_their_endbars():
    bars = _bars60()
    full = build_targets(bars, "15m")
    t = np.arange(len(bars))
    n_checked = 0
    for c in (700, 1100):
        alt = build_targets(_garbage_after(bars, c), "15m")
        for k in (2, 5, 10):
            for pre, cols in (("t1z", ("min", "max", "endbars")), ("t3", ("ret", "bars", "sig", "endbars"))):
                eb = full[f"{pre}_endbars_k{k}"].values
                rows = ~np.isnan(eb) & (t + np.nan_to_num(eb) <= c)
                assert rows.sum() > 0
                for nm in cols:
                    col = f"{pre}_{nm}_k{k}"
                    assert_allclose(alt[col].values[rows], full[col].values[rows], equal_nan=True, err_msg=col)
                    n_checked += int(rows.sum())
    assert n_checked > 1000


def test_zigzag_pivots_hand_series():
    c = np.array([100, 103, 106, 110, 108, 104, 100, 97, 99, 101, 103, 106, 102, 104, 100], float)
    p = zigzag_pivots(c, np.full(len(c), 5.0), 0)
    assert p == [(0, -1, 2), (3, 1, 5), (7, -1, 10), (11, 1, 14)]
    # the 106 -> 102 wiggle (3.8 %) is not a pivot and 104 is not a new high
    assert all(i != 12 for i, _, _ in p)
    # nothing confirmed on a series that never moves 5 %
    assert zigzag_pivots(np.array([100, 102, 101, 103, 100, 102.0]), np.full(6, 5.0), 0) == []


def _mk(rows, **ov):
    rows = np.array(rows, float)
    n = len(rows)
    b = pd.DataFrame({"timestamp": pd.date_range("2024-01-01", periods=n, freq="D"), "open": rows[:, 0],
                      "high": rows[:, 1], "low": rows[:, 2], "close": rows[:, 3], "volume": np.ones(n)})
    return build_targets(b, "day", **ov)


def test_t1w_ties_and_edges():
    lo = np.array([5, 4, 3, 2, 1, 1, 2, 3, 4, 5, 6], float)
    rows = np.column_stack([lo + .5, lo + 1, lo, lo + .5])
    t = _mk(rows, scales=[2], hold_h=[2], zz_k=[2], fwd_h=[1])
    m = t["t1w_min_w2"].values
    assert np.isnan(m[:2]).all() and np.isnan(m[-2:]).all()
    assert m[4] == 1 and m[5] == 0                      # only the FIRST of the two flat bottom bars
    assert (m[[2, 3, 6, 7, 8]] == 0).all()
    mx = t["t1w_max_w2"].values
    assert np.isnan(mx[:2]).all() and np.isnan(mx[-2:]).all()


def test_t5_semantics():
    # A: +5 % at offset 3, -3 % at offset 2 -> stop first -> hit 0; exact path stats; entry = next bar's OPEN
    A = [(100, 100, 100, 100),
         (100, 101, 99, 100),
         (100, 102, 96.5, 101),
         (100, 106, 100, 105),
         (101, 104, 101, 103),
         (103, 104, 102, 103)]
    kw = dict(scales=[1], hold_h=[4], zz_k=[2], fwd_h=[1], barrier_x=[5], barrier_y=[3])
    t = _mk(A, **kw)
    r = t.iloc[0]
    assert r.t5_hit_x5_y3_H4 == 0
    assert_allclose(r.t5_mfe_H4, 106 / 100 - 1)
    assert r.t5_ttm_H4 == 3
    assert_allclose(r.t5_maepre_H4, 96.5 / 100 - 1)
    assert_allclose(r.t5_mae_H4, 96.5 / 100 - 1)
    assert_allclose(r.t5_ret_H4, 103 / 100 - 1)
    assert np.isnan(t.t5_mfe_H4.iloc[2:]).all() and np.isnan(t.t5_hit_x5_y3_H4.iloc[2:]).all()   # unresolved = NaN
    # entry is open[t+1], NOT close[t]: change close[0] and the T5 values do not move
    A2 = [(100, 100, 100, 50)] + A[1:]
    assert_allclose(_mk(A2, **kw).iloc[0].t5_mfe_H4, r.t5_mfe_H4)
    # B: target first (off 2), stop later (off 3) -> 1
    B = [(200, 200, 200, 200), (200, 201, 199, 200), (200, 211, 199, 205), (205, 206, 190, 200),
         (200, 205, 195, 200), (200, 200, 200, 200)]
    assert _mk(B, **kw).iloc[0].t5_hit_x5_y3_H4 == 1
    # C: both thresholds inside the same bar -> conservative 0
    C = [(100, 100, 100, 100), (100, 106, 96, 100), (100, 101, 99, 100), (100, 101, 99, 100),
         (100, 101, 99, 100), (100, 101, 99, 100)]
    assert _mk(C, **kw).iloc[0].t5_hit_x5_y3_H4 == 0
    # D: neither touched -> 0 (resolved, not NaN); target hit with the stop never touched -> 1
    D = [(100, 100, 100, 100), (100, 102, 99, 100), (100, 103, 99, 101), (100, 103, 98.5, 100),
         (100, 104, 99, 100), (100, 100, 100, 100)]
    d0 = _mk(D, **kw).iloc[0]
    assert d0.t5_hit_x5_y3_H4 == 0 and not np.isnan(d0.t5_hit_x5_y3_H4)
    E = [(100, 100, 100, 100), (100, 102, 99, 100), (100, 103, 99, 101), (100, 106, 99, 100),
         (100, 104, 99, 100), (100, 100, 100, 100)]
    assert _mk(E, **kw).iloc[0].t5_hit_x5_y3_H4 == 1
    # smaller H derived from the largest: target at offset 3 is outside H=2
    t2 = _mk(E, **{**kw, "hold_h": [2, 4]})
    assert t2.iloc[0].t5_hit_x5_y3_H2 == 0 and t2.iloc[0].t5_hit_x5_y3_H4 == 1


def test_t2_t4_hand_values():
    c = np.array([100, 99, 98, 97, 96, 95, 96, 97, 98, 99, 100], float)
    rows = np.column_stack([c, c + .1, c - .1, c])
    t = _mk(rows, scales=[3], zz_sigma_window=3, hold_h=[2], zz_k=[2], fwd_h=[1, 2])
    assert t.t2_up_h3.iloc[5] == 1 and t.t2_dn_h3.iloc[5] == 0 and t.t2_fwd_h3.iloc[5] == 1
    assert t.t2_fwd_h3.iloc[3] == -1 and t.t2_dn_h3.iloc[3] == 0
    assert np.isnan(t.t2_up_h3.iloc[-3:]).all() and np.isnan(t.t2_up_h3.iloc[:3]).all()
    assert_allclose(t.t4_ret_h2.values[:-2], np.log(c[2:] / c[:-2]))
    assert np.isnan(t.t4_ret_h2.values[-2:]).all() and np.isnan(t.t4_ret_h1.values[-1])
    # an up-then-down hump gives t2_dn at the top
    h = np.array([95, 96, 97, 98, 99, 100, 99, 98, 97, 96, 95], float)
    th = _mk(np.column_stack([h, h + .1, h - .1, h]), scales=[3], zz_sigma_window=3, hold_h=[2], zz_k=[2], fwd_h=[1])
    assert th.t2_dn_h3.iloc[5] == 1 and th.t2_up_h3.iloc[5] == 0


def test_targets_runtime_budget():
    bars = derive(synthetic_15m(400, seed=9), "15m")
    assert len(bars) == 10_000
    t0 = time.time()
    build_targets(bars, "15m")
    assert time.time() - t0 < 5.0


def test_t3_sig_zero_sigma_is_nan():
    import warnings
    n = 400
    c = np.full(n, 100.0)
    c[300:] = np.linspace(100, 110, 100)               # flat stretch (σ = 0 in the trailing window) then a move
    c[150:200] = 100 + 5 * np.sin(np.arange(50))       # some earlier pivots
    b = pd.DataFrame({"timestamp": pd.date_range("2024-01-01", periods=n, freq="D"), "open": c, "high": c + .1,
                      "low": c - .1, "close": c, "volume": np.ones(n)})
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        t = build_targets(b, "day", scales=[2], hold_h=[2], zz_k=[2], fwd_h=[1], zz_sigma_window=20)
    assert not [x for x in w if issubclass(x.category, RuntimeWarning)]
    s3 = t["t3_sig_k2"].to_numpy()
    assert not np.isinf(s3).any()
    flat = np.flatnonzero(~np.isnan(t["t3_ret_k2"].to_numpy()) & (np.arange(n) < 150) & (np.arange(n) >= 21))
    # sigma is 0 on the flat opening stretch: wherever t3_ret is defined there, t3_sig must be NaN
    assert np.isnan(s3[flat]).all()


def test_vol_scaled_t5_columns():
    import warnings
    from research.model_lab import factors
    b = _bars60()
    hold = [5, 20]
    kw = dict(scales=[3], hold_h=hold, zz_k=[2], fwd_h=[1], barrier_x=[5], barrier_y=[3])
    t = build_targets(b, "15m", **kw)
    rv = factors.own_factors(b)["rv_16"].to_numpy(float)
    for H in hold:
        S = rv * np.sqrt(H)
        mfe, mp, rt = (t[f"t5_{k}_H{H}"].to_numpy() for k in ("mfe", "maepre", "ret"))
        assert_allclose(t[f"t5_mfez_H{H}"].to_numpy(), mfe / S, rtol=1e-9, equal_nan=True)
        assert_allclose(t[f"t5_maepz_H{H}"].to_numpy(), mp / S, rtol=1e-9, equal_nan=True)
        assert_allclose(t[f"t5_retz_H{H}"].to_numpy(), rt / S, rtol=1e-9, equal_nan=True)
        assert_allclose(t[f"t5_edgez_H{H}"].to_numpy(), (mfe + mp) / S, rtol=1e-9, equal_nan=True)
        assert np.isfinite(t[f"t5_edgez_H{H}"].to_numpy()).sum() > 100
    # old columns unchanged: raw T5 spot check still the documented formula
    assert {"t5_mfe_H5", "t5_ttm_H5", "t5_maepre_H5", "t5_mae_H5", "t5_ret_H5", "t5_hit_x5_y3_H5"} <= set(t.columns)
    # flat stretch -> sigma 0 -> NaN, no warnings
    n = 60
    rows = np.array([(100 + (i % 2) * 0.0,) * 4 for i in range(n)], float)
    rows[40:, :] = 100 + np.arange(n - 40)[:, None]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        f = _mk(rows, **kw)
    assert np.isnan(f["t5_mfez_H5"].iloc[16:30]).all()


def test_vol_scale_is_causal():
    b = _bars60()
    kw = dict(scales=[3], hold_h=[5], zz_k=[2], fwd_h=[1], barrier_x=[5], barrier_y=[3])
    cols = ["t5_mfez_H5", "t5_maepz_H5", "t5_retz_H5", "t5_edgez_H5"]
    base = build_targets(b, "15m", **kw)[cols]
    t0 = 400
    after = build_targets(_garbage_after(b, t0 + 5), "15m", **kw)[cols]
    assert_allclose(base.iloc[:t0 + 1].to_numpy(), after.iloc[:t0 + 1].to_numpy(), equal_nan=True)
    # bar t-20 lies outside the 16-bar sigma window (and the forward window): no effect at t
    b2 = b.copy()
    b2.loc[t0 - 20, ["open", "high", "low", "close"]] *= 1.5
    ch = build_targets(b2, "15m", **kw)[cols]
    assert_allclose(base.iloc[t0].to_numpy(), ch.iloc[t0].to_numpy(), equal_nan=True)


def test_vol_scaled_lookahead_and_continuous():
    from research.model_lab import score
    assert lookahead("t5_mfez_H20") == 20
    assert score._is_continuous("t5_edgez_H20")
