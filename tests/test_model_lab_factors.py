"""Model Lab L0b — causal factor library (synthetic data only)."""
from datetime import date

import numpy as np
import pandas as pd
import pytest
from numpy.testing import assert_allclose

from research.model_lab import factors as fx
from research.model_lab.bars import SOURCE, TFS, derive
from research.model_lab.synth import synthetic_15m, synthetic_day

QUARTER = pd.Timedelta(minutes=15)
CLOSE = pd.Timedelta(hours=15, minutes=30)


def _num(df):
    return df.drop(columns=[c for c in ("timestamp", "avail_ts") if c in df.columns]).astype(float)


def test_own_factors_causal():
    bars = derive(synthetic_15m(70, seed=2), "15m")
    full = fx.own_factors(bars)
    n = len(bars)
    for cut in (1100, 1400, n - 1):
        part = fx.own_factors(bars.iloc[:cut + 1].reset_index(drop=True))
        assert list(part.columns) == list(full.columns)
        assert_allclose(part.iloc[cut].values.astype(float), full.iloc[cut].values.astype(float),
                        rtol=1e-9, atol=1e-12, equal_nan=True)


# --- every-timeframe causality --------------------------------------------------------------

def _sources():
    s15 = synthetic_15m(90, seed=3, missing_frac=0.01)
    first = pd.Timestamp("2020-01-06")
    dstart = pd.bdate_range(end=first, periods=301)[0]
    mk = lambda seed: synthetic_day(301 + 90 + 10, seed=seed, start=str(dstart.date()))
    return {"s15": s15, "sday": mk(4), "n15": synthetic_15m(90, seed=5, missing_frac=0.01),
            "nday": mk(6), "vix": mk(7)}


def _avail(df, kind):
    return df.timestamp + QUARTER if kind == "15" else df.timestamp.dt.normalize() + CLOSE


def _truncate(src, T, extra_days=0):
    out = {}
    for k, df in src.items():
        kind = "15" if k.endswith("15") else "day"
        lim = T + pd.Timedelta(days=extra_days) if (extra_days and k in ("sday", "nday")) else T
        out[k] = df[_avail(df, kind) <= lim].reset_index(drop=True)
    return out


def _factors(src, tf):
    key = lambda who: (who + "15") if SOURCE[tf] == "15minute" else (who + "day")
    bars = derive(src[key("s")], tf)
    nifty = derive(src[key("n")], tf)
    higher = {h: derive(src["s15"] if SOURCE[h] == "15minute" else src["sday"], h) for h in fx.HIGHER_TF[tf]}
    return bars, fx.compute_factors(bars, tf, nifty=nifty, vix_day=src["vix"], higher=higher)


def _complete(tf, avail):
    if tf in ("15m", "day", "week"):
        return True
    last = avail - QUARTER
    m = last.hour * 60 + last.minute
    if tf == "4h":
        return m in (13 * 60, 15 * 60)
    if tf == "dayagg":
        return m == 15 * 60
    n = 30 if tf == "30m" else 60
    return (m - 555) % n == n - 15 or m == 15 * 60 + 15


@pytest.mark.parametrize("tf", TFS)
def test_compute_factors_causal_every_tf(tf):
    src = _sources()
    bars, full = _factors(src, tf)
    assert len(full) == len(bars)
    n = len(full)
    cuts, used = [], set()
    for frac in (0.6, 0.8, 0.95):
        c = int(n * frac)
        while c < n - 3 and not _complete(tf, bars.avail_ts[c]):
            c += 1
        cuts.append(c)
    for c in cuts:
        T = full.avail_ts[c]
        # weekly bars (own TF or higher TF) drop the final week of a frame, so keep the next trading day(s) of the
        # daily source as a marker; the strict avail_ts join means they cannot reach row c unless the code leaks
        sub = _truncate(src, T, extra_days=3 if "week" in (tf, *fx.HIGHER_TF[tf]) else 0)
        tb, tr = _factors(sub, tf)
        hit = np.flatnonzero(tr.timestamp.values == full.timestamp.values[c])
        assert len(hit) == 1, f"{tf}: row {c} missing after truncation"
        a, b = tr.iloc[hit[0]], full.iloc[c]
        assert a.avail_ts == b.avail_ts
        assert_allclose(a.drop(["timestamp", "avail_ts"]).values.astype(float),
                        b.drop(["timestamp", "avail_ts"]).values.astype(float),
                        rtol=1e-9, atol=1e-12, equal_nan=True, err_msg=f"{tf} row {c}")


def test_cross_section_causal():
    inputs = {}
    for i, seed in enumerate(range(10, 22)):
        b = derive(synthetic_15m(70, seed=seed), "15m")
        o = fx.own_factors(b)
        inputs[f"S{i}"] = pd.DataFrame({"timestamp": b.timestamp, "ret_16": o.ret_16, "ret_64": o.ret_64,
                                        "close": b.close})
    full = fx.cross_section(inputs)
    cut = 1500
    part = fx.cross_section({k: v.iloc[:cut + 1].reset_index(drop=True) for k, v in inputs.items()})
    for k in inputs:
        assert_allclose(part[k].iloc[cut].values, full[k].iloc[cut].values, equal_nan=True)
        assert len(full[k]) == len(inputs[k])
    row = full["S0"].iloc[cut]
    assert row.xs_n == 12 and 0 < row.xs_rank_ret16 <= 1 and 0 <= row.xs_breadth_100 <= 1
    small = fx.cross_section({k: inputs[k] for k in list(inputs)[:9]})
    s0 = small["S0"]
    assert s0.xs_n.iloc[cut] == 9
    assert s0[["xs_rank_ret16", "xs_rank_ret64", "xs_breadth_100"]].isna().all().all()


def test_higher_join_strictly_completed():
    s15 = synthetic_15m(60, seed=11)
    sday = synthetic_day(400, seed=12, start="2019-01-01")
    bars = derive(s15, "15m")
    dayb = derive(sday, "day")
    f = fx.compute_factors(bars, "15m", higher={"60m": derive(s15, "60m"), "day": dayb})
    rsi = fx.own_factors(dayb).rsi_14.values
    h60 = derive(s15, "60m")
    rsi60 = fx.own_factors(h60).rsi_14.values
    rng = np.random.default_rng(0)
    for i in rng.choice(len(bars), 50, replace=False):
        a = bars.avail_ts[i]
        exp = np.nan
        for j in range(len(dayb)):
            if dayb.avail_ts[j] < a:
                exp = rsi[j]
        e60 = np.nan
        for j in range(len(h60)):
            if h60.avail_ts[j] < a:
                e60 = rsi60[j]
        assert_allclose(f.hday_rsi_14[i], exp, equal_nan=True)
        assert_allclose(f.h60m_rsi_14[i], e60, equal_nan=True)


def test_vix_is_prior_day():
    s15 = synthetic_15m(40, seed=13)
    vix = synthetic_day(300, seed=14, start="2019-06-03")
    bars = derive(s15, "15m")
    f = fx.compute_factors(bars, "15m", vix_day=vix)
    vdates = vix.timestamp.dt.normalize().values
    d = bars.timestamp.dt.normalize().values
    checked = 0
    for day in np.unique(d):
        j = np.searchsorted(vdates, day, side="left") - 1      # last VIX date strictly before `day`
        rows = d == day
        if j < 0:
            assert f.vix_close_d1[rows].isna().all()
        else:
            assert_allclose(f.vix_close_d1[rows].values, vix.close.values[j])
            checked += 1
    assert checked > 20


def test_bars_since_extreme_matches_bruteforce():
    rng = np.random.default_rng(5)
    n = 1300
    lo = rng.integers(0, 12, n).astype(float) + 100       # many ties
    hi = lo + rng.integers(0, 4, n)
    mid = (lo + hi) / 2
    bars = pd.DataFrame({"open": mid, "high": hi, "low": lo, "close": mid, "volume": rng.integers(1, 9, n)})
    out = fx.own_factors(bars)
    for nn in (20, 50, 100, 250, 500, 1000):
        for name, arr, fn in (("bsl", lo, np.min), ("bsh", hi, np.max)):
            exp = np.full(n, np.nan)
            for t in range(nn - 1, n):
                w = arr[t - nn + 1:t + 1]
                idx = np.flatnonzero(w == fn(w))[-1]                # most recent tie
                exp[t] = (nn - 1) - idx
            assert_allclose(out[f"{name}_{nn}"].values, exp, equal_nan=True, err_msg=f"{name}_{nn}")


def test_monthly_expiry():
    assert fx.monthly_expiry(date(2024, 10, 3)) == date(2024, 10, 31)
    assert fx.monthly_expiry(date(2024, 10, 31)) == date(2024, 10, 31)
    assert fx.monthly_expiry(date(2025, 8, 1)) == date(2025, 8, 28)
    assert fx.monthly_expiry(date(2025, 9, 1)) == date(2025, 9, 30)
    assert fx.monthly_expiry(date(2025, 9, 30)).weekday() == 1
    assert fx.monthly_expiry(date(2024, 10, 31 - 0)).weekday() == 3
    # after the month's expiry -> next month
    assert fx.monthly_expiry(date(2024, 10, 31) + pd.Timedelta(days=1).to_pytimedelta()) == date(2024, 11, 28)
    assert fx.monthly_expiry(date(2025, 8, 29)) == date(2025, 9, 30)
    assert fx.monthly_expiry(date(2024, 12, 30)) == date(2025, 1, 30)


def test_schema_stable_without_market():
    s15 = synthetic_15m(20, seed=15)
    bars = derive(s15, "15m")
    bare = fx.compute_factors(bars, "15m")
    sday = synthetic_day(300, seed=16, start="2019-06-03")
    full = fx.compute_factors(bars, "15m", nifty=bars, vix_day=sday,
                              higher={"60m": derive(s15, "60m"), "day": derive(sday, "day")})
    assert list(bare.columns) == list(full.columns)
    assert bare.vix_close_d1.isna().all() and bare.hday_rsi_14.isna().all() and bare.beta_250.isna().all()
    assert len(bare) == len(bars)
