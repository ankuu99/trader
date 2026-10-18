"""Model Lab L1a — split engine (synthetic only)."""
import numpy as np
import pandas as pd

from research.model_lab import splits as sp
from research.model_lab import targets as tg
from research.model_lab.source import label_end_ts
from research.model_lab.synth import synthetic_15m

T = pd.Timestamp


def test_test_windows_aligned_half_years():
    w = sp.test_windows("2018-01-03", "2021-03-10", "6M", "2Y")
    assert w[0] == (T("2020-07-01"), T("2021-01-01"))
    assert w[1][0] == T("2021-01-01")
    assert all(s.month in (1, 7) and s.day == 1 for s, _ in w[:-1])
    # partial last window: Jan 1 -> Mar 10 is 68 days -> kept, clipped
    assert w[-1] == (T("2021-01-01"), T("2021-03-10"))
    # a < 30 day tail is dropped
    w2 = sp.test_windows("2018-01-03", "2021-01-20", "6M", "2Y")
    assert w2[-1][0] == T("2020-07-01")


def test_test_windows_quarters():
    w = sp.test_windows("2018-01-03", "2021-01-01", "3M", "2Y")
    assert [s for s, _ in w] == [T("2020-04-01"), T("2020-07-01"), T("2020-10-01")]
    assert all(e - s <= pd.Timedelta(days=92) for s, e in w)


def test_expanding_rolling_anchor_shapes():
    ds, de = T("2016-01-04"), T("2021-01-01")
    ex = sp.expanding(ds, de)
    assert [f.fold_id for f in ex] == list(range(len(ex)))
    assert all(f.train_start == ds and f.train_end == f.test_start for f in ex)
    assert all(a.test_start < b.test_start for a, b in zip(ex, ex[1:]))
    ro = sp.rolling(ds, de, "1Y")
    assert all(f.train_end == f.test_start and f.train_start == max(ds, f.test_start - pd.DateOffset(years=1))
               for f in ro)
    assert ro[0].scheme == "rolling_1Y"
    an = sp.anchor_sweep(ds, de, ["2016-01-01", "2017-01-01"])
    assert {f.scheme for f in an} == {"anchor_2016", "anchor_2017"}
    assert [f.fold_id for f in an] == list(range(len(an)))
    assert all(f.test_start - f.train_start >= pd.Timedelta(days=730) for f in an)
    assert all(f.train_start == T(f.scheme[-4:] + "-01-01") for f in an)


def test_train_mask_purges_by_label_end():
    fo = sp.Fold(0, "expanding", T("2020-01-01"), T("2020-07-01"), T("2020-07-01"), T("2021-01-01"))
    avail = np.array(["2020-03-01", "2020-06-29", "2020-06-29", "2020-06-30 15:00", "2020-02-01"],
                     dtype="datetime64[ns]")
    le = np.array(["2020-03-02", "2020-06-29 15:00", "2020-07-02", "2020-07-01 10:00", "NaT"],
                  dtype="datetime64[ns]")
    m = sp.train_mask(fo, avail, le, np.array(["A"] * 5), "15m")
    # embargo 1D: label end must be < 2020-06-30
    assert m.tolist() == [True, True, False, False, False]


def test_loyo_embargo_both_sides():
    fo = sp.leave_one_year_out(T("2018-01-01"), T("2022-01-01"))[2]
    assert fo.scheme == "loyo" and fo.test_start == T("2020-01-01")
    rng = pd.date_range("2018-01-01", "2021-12-31", freq="D")
    av = rng.values.astype("datetime64[ns]")
    le = (rng + pd.Timedelta(hours=2)).values.astype("datetime64[ns]")
    m = sp.train_mask(fo, av, le, np.array(["A"] * len(av)), "15m")
    emb = pd.Timedelta("1D")
    used = rng[m]
    assert not ((used >= fo.test_start - emb) & (used < fo.test_end + emb)).any()
    assert (used >= fo.test_end + emb).any() and (used < fo.test_start - emb).any()
    assert used[used >= fo.test_end].min() == fo.test_end + emb


def test_stock_groups_stable_and_disjoint():
    syms = [f"NSE:S{i}" for i in range(40)]
    assert [sp.stock_group(s, 5) for s in syms] == [sp.stock_group(s, 5) for s in syms]
    assert sp.stock_group("NSE:S1", 5) == int(__import__("hashlib").md5(b"NSE:S1").hexdigest(), 16) % 5
    base = sp.expanding(T("2016-01-04"), T("2019-01-01"))
    folds = sp.with_stock_groups(base, 5)
    assert len(folds) == 5 * len(base) and [f.fold_id for f in folds] == list(range(len(folds)))
    rows = np.array(syms)
    av = np.full(len(rows), np.datetime64(base[0].test_start.to_datetime64()), dtype="datetime64[ns]")
    le = av - np.timedelta64(10, "D")
    tested = np.zeros(len(rows), int)
    for f in folds[:5]:
        trm = sp.train_mask(f, av - np.timedelta64(20, "D"), le, rows, "15m", 5)
        tem = sp.test_mask(f, av, rows, 5)
        assert not (trm & tem).any()
        assert set(rows[trm]).isdisjoint(rows[tem])
        tested += tem
    assert (tested == 1).all()


def test_label_end_ts_fixed_and_zigzag():
    from research.model_lab.bars import derive
    b = derive(synthetic_15m(60, seed=3), "15m")
    t = tg.build_targets(b, "15m")
    ts = b["timestamp"]
    le = label_end_ts(t, ts, "t4_ret_h4")
    assert le.iloc[0] == ts.iloc[4] and le.iloc[10] == ts.iloc[14]
    assert le.iloc[-4:].isna().all() == t["t4_ret_h4"].iloc[-4:].isna().all()
    assert (le.isna().to_numpy() == t["t4_ret_h4"].isna().to_numpy()).all()
    lz = label_end_ts(t, ts, "t1z_min_k2")
    eb = t["t1z_endbars_k2"].to_numpy()
    ok = ~np.isnan(eb)
    assert ok.any()
    i = np.flatnonzero(ok)[0]
    assert lz.iloc[i] == ts.iloc[i + int(eb[i])]
    assert (lz.isna().to_numpy() == np.isnan(t["t1z_min_k2"].to_numpy())).all()
