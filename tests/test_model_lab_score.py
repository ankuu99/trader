"""Model Lab L1b: reference scores, event/curve scorer, run report (synthetic, tmp dirs, no network)."""
import json

import numpy as np
import pandas as pd
import pytest

from research.model_lab import bars as bars_mod
from research.model_lab import paths, references, report, score, store, synth, targets


# ---------------------------------------------------------------- primitives

def test_picks_cluster_events():
    s = np.zeros(40)
    s[[10, 11, 13, 30]] = 1.0
    assert list(score.picks(s, 0.5, 4)) == [10, 30]


def test_picks_long_run_opens_new_pick_every_window():
    # continuous firing 10..30 with tol 4: one pick per 5-bar window, not one pick for the whole run
    s = np.zeros(40)
    s[10:31] = 1.0
    assert list(score.picks(s, 0.5, 4)) == [10, 15, 20, 25, 30]


def test_recall_monotone_in_firing_rate():
    # widening the firing set (lower threshold) must never lose a caught pivot
    rng = np.random.default_rng(0)
    n = 3000
    truth = np.zeros(n); truth[rng.choice(n, 60, replace=False)] = 1.0
    sc = rng.random(n) + 0.8 * truth
    close = np.full(n, 100.0); low = close.copy(); high = close.copy()
    pos = np.arange(n)
    rec = []
    for q in (0.99, 0.95, 0.9, 0.8, 0.6):
        c = score.event_counts(sc, truth, pos, low, high, close, np.quantile(sc, q), 4, "min")
        rec.append(c["matched"] / c["pivots"])
    assert all(b >= a - 0.02 for a, b in zip(rec, rec[1:])), rec


def test_match_events_one_to_one_nearest():
    # two picks near one pivot -> only the nearer matches
    assert score.match_events([48, 51], [50], 4) == [(51, 50)]
    # a pick between two pivots matches the nearer one
    assert score.match_events([53], [50, 58], 5) == [(53, 50)]
    # tolerance boundary inclusive / exclusive
    assert score.match_events([54], [50], 4) == [(54, 50)]
    assert score.match_events([55], [50], 4) == []


def test_event_counts_lateness_and_distance():
    n = 100
    pos = np.arange(n)
    low = np.full(n, 110.0); low[50] = 100.0
    high = low * 1.01
    close = np.full(n, 110.0); close[52] = 101.5
    truth = np.zeros(n); truth[50] = 1.0
    truth[80] = np.nan
    sc = np.zeros(n); sc[52] = 1.0; sc[80] = 1.0           # second pick sits on a NaN-truth row
    r = score.event_counts(sc, truth, pos, low, high, close, 0.5, 4, "min")
    assert (r["picks"], r["unjudged"], r["matched"], r["pivots"]) == (2, 1, 1, 1)
    assert r["lateness_med"] == 2
    assert r["dist_med_pct"] == pytest.approx(1.5)
    assert r["bars"] == n
    # max side: close 2% below the high
    high2 = np.full(n, 110.0); high2[50] = 100.0
    close2 = np.full(n, 98.0)
    t2 = np.zeros(n); t2[50] = 1.0
    s2 = np.zeros(n); s2[50] = 1.0
    r2 = score.event_counts(s2, t2, pos, low, high2, close2, 0.5, 4, "max")
    assert r2["dist_med_pct"] == pytest.approx(2.0)


def test_event_ap_hand_points():
    pts = [{"recall": 0.5, "precision": 1.0}, {"recall": 1.0, "precision": 0.5}]
    assert score.event_ap(pts) == pytest.approx(0.5 * 1.0 + 0.5 * 0.5)
    dup = pts + [{"recall": 0.5, "precision": 0.2}, {"recall": 1.0, "precision": 0.4}]
    assert score.event_ap(dup) == pytest.approx(0.75)           # duplicates keep max precision


def test_pinball_and_coverage():
    y = np.array([1.0, 2.0, 3.0]); pred = np.array([2.0, 2.0, 2.0])
    # q=0.9: errors -1,0,1 -> 0.1*1, 0, 0.9*1 -> mean 1/3
    assert score.pinball(y, pred, 0.9) == pytest.approx(1 / 3)
    assert score.coverage(y, np.array([0.0, 2.5, 2.0]), np.array([1.5, 3.0, 3.5])) == pytest.approx(2 / 3)


def test_perfect_and_random_scores():
    b = synth.synthetic_15m(160, seed=3)
    t = targets.build_targets(b, "15m")
    truth = t["t1w_min_w4"].to_numpy()
    ok = ~np.isnan(truth)
    rng = np.random.default_rng(0)
    perfect = np.nan_to_num(truth) + rng.normal(0, 1e-4, len(b))
    coin = rng.random(len(b))
    pos = np.arange(len(b))
    args = (truth, pos, b["low"].to_numpy(), b["high"].to_numpy(), b["close"].to_numpy())

    def curve(sc, taus, tol):
        pts = []
        for tau in taus:
            r = score.event_counts(sc, *args, tau, tol, "min")
            j = r["picks"] - r["unjudged"]
            pts.append({"recall": r["matched"] / r["pivots"], "precision": r["matched"] / j if j else np.nan})
        return pts, score.event_counts(sc, *args, 0.5, tol, "min")

    pts, at_half = curve(perfect, [0.99, 0.9, 0.5, 0.1], 4)
    assert at_half["matched"] / at_half["pivots"] > 0.99
    assert score.event_ap(pts) > 0.9
    cpts, _ = curve(coin, np.quantile(coin, [0.999, 0.99, 0.95, 0.9, 0.8]), 1)
    assert score.event_ap(cpts) < 0.6
    # on the same grid, perfect beats coin
    ppts, _ = curve(perfect, np.quantile(perfect, [0.999, 0.99, 0.95, 0.9, 0.8]), 1)
    assert score.event_ap(ppts) > score.event_ap(cpts)
    assert ok.sum() > 0


# ---------------------------------------------------------------- references

def test_vol_ref_equals_rv16():
    from research.model_lab import factors
    bb = synth.synthetic_15m(10, seed=1)
    v = references.ref_scores(bb, "vol", "NSE:X")
    exp = factors.own_factors(bb)["rv_16"].to_numpy(float)
    assert np.allclose(v, exp, equal_nan=True) and np.isnan(v).any()
    assert "vol" in references.REFS_MIN and "vol" in references.REFS_MAX


def test_refs_rules():
    c = np.array([5, 4, 3, 4, 5, 4, 3, 2, 3], float)
    b = pd.DataFrame({"timestamp": pd.date_range("2024-01-01", periods=len(c), freq="15min"),
                      "open": c, "high": c + 0.5, "low": c - 0.5, "close": c, "volume": 100})
    low = references.ref_scores(b, "low3", "NSE:X")
    high = references.ref_scores(b, "high3", "NSE:X")
    # t=3: close 4 > 3 and prev(3) == min(5,4,3); t=8: close 3 > 2 and prev(2) == min(4,3,2)
    assert list(np.flatnonzero(low == 1.0)) == [3, 8]
    assert np.isnan(low[:3]).all() and not np.isnan(low[3:]).any()
    # t=5: close 4 < 5 and prev(5) == max(3,4,5)
    assert list(np.flatnonzero(high == 1.0)) == [5]
    a1 = references.ref_scores(b, "coin", "NSE:X"); a2 = references.ref_scores(b, "coin", "NSE:X")
    o = references.ref_scores(b, "coin", "NSE:Y")
    assert np.array_equal(a1, a2) and not np.array_equal(a1, o)
    bb = synth.synthetic_15m(10, seed=1)
    rsi = references.ref_scores(bb, "rsi", "NSE:X"); hi = references.ref_scores(bb, "rsi_hi", "NSE:X")
    assert np.nansum(np.abs(rsi + hi - 100)) < 1e-9 and np.isnan(rsi[:14]).all()


# ---------------------------------------------------------------- end to end

def _fake_run(tmp_path, monkeypatch, with_vix=False):
    monkeypatch.setattr(paths, "BARS_DIR", tmp_path / "bars")
    monkeypatch.setattr(paths, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(paths, "REFS_DIR", tmp_path / "refs")
    monkeypatch.setattr(report, "REPORT_DIR", tmp_path / "reports")
    syms = ["NSE:AAA", "NSE:BBB", "NSE:CCC"]
    rng = np.random.default_rng(5)
    run_dir = paths.RUNS_DIR / "r1"
    (run_dir / "scores").mkdir(parents=True)
    for i, s in enumerate(syms):
        store.write_bars(s, "15minute", synth.synthetic_15m(120, seed=10 + i))
    if with_vix:
        store.write_bars("NSE:INDIA VIX", "day", synth.synthetic_day(600, seed=1, start="2018-01-01"))
    references.write_refs("15m", syms, ["coin", "rsi", "low10", "vol"])
    for s in syms:
        b = bars_mod.load(s, "15m")
        n = len(b)
        t = targets.build_targets(b, "15m")
        truth = np.nan_to_num(t["t1w_min_w4"].to_numpy())
        a, c = n // 3, 2 * n // 3
        parts = []
        for fid, (lo, hi) in enumerate([(a, c), (c, n)]):
            sl = slice(lo, hi)
            d = pd.DataFrame({"timestamp": b["timestamp"].to_numpy()[sl], "fold_id": np.int32(fid),
                              "score": (truth[sl] + rng.normal(0, 1e-4, hi - lo)).astype("float32")})
            r16 = t["t4_ret_h16"].to_numpy()[sl]
            d["pred_t4_ret_h16"] = (r16 + rng.normal(0, 0.01, hi - lo)).astype("float32")
            d["pred_t4_ret_h16_q05"] = (r16 - 0.05).astype("float32")
            d["pred_t4_ret_h16_q95"] = (r16 + 0.05).astype("float32")
            parts.append(d)
        pd.concat(parts).to_parquet(run_dir / "scores" / f"{paths.sym_file(s)}.parquet", index=False)
        # production stand-in: random scores
        ts = b["timestamp"]
        pm = pd.DataFrame({"timestamp": ts, "score": rng.random(n).astype("float32")})
        pm.loc[n - 100:, "score"] = np.nan        # replay not available at the end
        p = references.ref_path("15m", "prod_pmin", s)
        p.parent.mkdir(parents=True, exist_ok=True)
        pm.to_parquet(p, index=False)
    b0 = bars_mod.load(syms[0], "15m")
    pd.DataFrame({"fold_id": np.array([0, 1], dtype="int32"), "scheme": "expanding",
                  "train_start": b0["timestamp"].iloc[0], "train_end": b0["timestamp"].iloc[0],
                  "test_start": b0["timestamp"].iloc[0], "test_end": b0["timestamp"].iloc[-1],
                  "holdout_group": np.array([-1, -1], dtype="int32")}).to_parquet(run_dir / "folds.parquet")
    (run_dir / "meta.json").write_text(json.dumps({
        "run_id": "r1", "tf": "15m", "scheme": "expanding", "target": "t1w_min_w4", "model": "oracle",
        "model_params": {}, "features": [], "universe_top_n": None, "symbols": syms,
        "train_rows_per_fold": 0, "seed": 1, "created": "2026-10-18", "elapsed_s": 0.0}))
    return syms


def test_score_run_contract_end_to_end(tmp_path, monkeypatch):
    _fake_run(tmp_path, monkeypatch, with_vix=True)
    refs = ["prod_pmin", "coin", "rsi", "low10"]
    s = score.score_run("r1", refs)
    run_dir = paths.RUNS_DIR / "r1"
    assert (run_dir / "score_summary.json").exists()
    cv = pd.read_parquet(run_dir / "curves.parquet")
    assert list(cv.columns) == ["scope", "key", "model", "truth", "rate", "tau", "picks", "unjudged", "matched",
                                "pivots", "precision", "recall", "picks_per_stock_year", "lateness_med",
                                "dist_med_pct"]
    assert set(cv.scope) == {"all", "fold", "year"}
    assert set(cv.model) == {"oracle"} | set(refs)
    assert cv.truth.iloc[0] == "t1w_min_w4"
    js = json.loads((run_dir / "score_summary.json").read_text())
    assert set(js["verdicts"]["t1w_min_w4"]) == set(refs)
    assert js["coverage"]["coin"] == pytest.approx(1.0)
    assert js["coverage"]["prod_pmin"] < 1.0                 # NaN tail rows are dropped
    assert js["verdicts"]["t1w_min_w4"]["coin"]["win"] is True
    assert js["overall"] == "PASS"
    assert js["ap"]["t1w_min_w4"]["oracle"]["all"] > 0.8
    assert "vix" in js["ap"]["t1w_min_w4"]["oracle"]
    assert js["t2"] and js["spearman"]["t4_ret_h16"]["oracle"]
    assert "pred_t4_ret_h16_q05" in js["preds"] and "coverage_t4_ret_h16" in js["preds"]
    assert set(js["after_pick_informational"]) == {"0.002", "0.01", "0.05"}
    assert (cv[(cv.scope == "all") & (cv.model == "oracle")].recall.max() > 0.95)
    out = report.write_report("r1", s)
    text = out.read_text()
    assert out == tmp_path / "reports" / "r1.md"
    assert "Arms tried so far" in text and "informational" in text and "PASS" in text
    assert "does not judge the model" in text
    # deterministic
    s2 = score.score_run("r1", refs)
    assert s2["ap"] == s["ap"]


def test_no_prod_ref_gives_no_ref(tmp_path, monkeypatch):
    _fake_run(tmp_path, monkeypatch)
    s = score.score_run("r1", ["coin", "rsi"])
    assert s["overall"] == "NO_REF"


def test_arms_counter(tmp_path):
    p = tmp_path / "L.md"
    p.write_text("# x\n\n## Infrastructure\n\n| a |\n|---|\n| r1 |\n\n## Arms\n\nArms tried so far: **0**.\n\n"
                 "| ID | M |\n|---|---|\n| A1 | x |\n| A2 | y |\n")
    assert report.arms_tried(p) == 2


def test_truth_tol_never_wider_than_half_window():
    assert score.truth_tol("t1w_min_w3", "day") == 1
    assert score.truth_tol("t1w_min_w10", "day") == 3
    assert score.truth_tol("t1w_max_w4", "15m") == 2
    assert score.truth_tol("t1z_min_k5", "day") == score.TOL["day"]


# ---------------------------------------------------------------- L2a: magnitude, deciles, after-pick by year

def _mag_inputs(n=6000, seed=0):
    rng = np.random.default_rng(seed)
    y = rng.normal(size=n)
    fold = np.repeat([0, 1, 2], n // 3)
    year = np.tile([2021, 2022, 2023], n // 3)
    return rng, y, fold, year


def test_magnitude_verdict_hand_case():
    rng, y, fold, year = _mag_inputs()
    model = y + rng.normal(0, 0.1, len(y))
    mat = np.column_stack([model, rng.random(len(y)), rng.random(len(y)), rng.random(len(y))])
    names = ["m", "prod_pmin", "rsi", "vol"]
    v = score.magnitude_verdict(mat, names, y, fold, year, "min", [0, 1, 2])
    assert v["verdicts"]["prod_pmin"]["win"] and v["verdicts"]["rsi"]["win"]
    assert v["overall"] == "PASS" and v["n_folds"] == 3 and v["n_years"] == 3
    # perfect inverse reference: |rho| = 1 > model's rho -> not beaten
    mat2 = np.column_stack([model, -y, mat[:, 2], mat[:, 3]])
    v2 = score.magnitude_verdict(mat2, names, y, fold, year, "min", [0, 1, 2])
    assert not v2["verdicts"]["prod_pmin"]["win"] and v2["overall"] == "FAIL"
    assert v2["pooled_rho"]["prod_pmin"] == pytest.approx(-1.0)
    # PASS needs both prod and rsi
    v3 = score.magnitude_verdict(mat[:, :3], ["m", "prod_pmin", "rsi"], y, fold, year, "min", [0, 1, 2])
    assert v3["overall"] == "NO_REF"
    # groups under 200 rows are ignored
    v4 = score.magnitude_verdict(mat[:150], names, y[:150], fold[:150], year[:150], "min", [0])
    assert v4["n_folds"] == 0 and not v4["verdicts"]["rsi"]["win"]


def test_magnitude_verdict_requires_vol():
    rng, y, fold, year = _mag_inputs()
    model = y + rng.normal(0, 0.1, len(y))
    names = ["m", "prod_pmin", "rsi", "vol"]
    bad = np.column_stack([model, rng.random(len(y)), rng.random(len(y)), y])   # vol ref equals the target
    v = score.magnitude_verdict(bad, names, y, fold, year, "min", [0, 1, 2])
    assert v["verdicts"]["prod_pmin"]["win"] and v["verdicts"]["rsi"]["win"]
    assert not v["verdicts"]["vol"]["win"] and v["overall"] == "FAIL"
    v2 = score.magnitude_verdict(bad[:, :3], names[:3], y, fold, year, "min", [0, 1, 2])
    assert v2["overall"] == "NO_REF"
    good = np.column_stack([model, rng.random(len(y)), rng.random(len(y)), rng.random(len(y))])
    assert score.magnitude_verdict(good, names, y, fold, year, "min", [0, 1, 2])["overall"] == "PASS"
    vmax = score.magnitude_verdict(good, ["m", "prod_pmax", "rsi_hi", "vol"], y, fold, year, "max", [0, 1, 2])
    assert vmax["overall"] == "PASS"


def test_is_continuous():
    for t in ("t5_ret_H20", "t5_mfe_H20", "t5_ttm_H20", "t4_ret_h4", "t3_ret_k5", "t3_sig_k5"):
        assert score._is_continuous(t)
    for t in ("t1w_min_w4", "t1z_min_k5", "t5_hit_x5_y3_H20", "t3_endbars_k5", "t2_up_h3", None):
        assert not score._is_continuous(t)


def test_deciles_monotone_for_perfect_score():
    rng = np.random.default_rng(1)
    y = rng.normal(size=1000)
    d = score.decile_table(y, y)
    means = [r["mean"] for r in d["rows"]]
    assert all(b > a for a, b in zip(means, means[1:])) and len(means) == 10
    assert d["spread"] == pytest.approx(means[-1] - means[0])
    assert sum(r["n"] for r in d["rows"]) == 1000


def test_afterpick_by_year_counts():
    # columns: year, net_ret, qa flag
    model = np.array([[2019, .03, 0], [2019, .01, 0], [2020, .02, 1], [2020, .04, 0], [2021, -.01, 0],
                      [2021, np.nan, 0]])
    prod = np.array([[2019, .01, 0], [2020, .05, 0], [2020, .03, 0], [2021, -.02, 0]])
    r = score.afterpick_by_year({"m": model, "prod_pmin": prod}, "m", "prod_pmin", qa_available=True)
    assert r["by_year"]["2019"]["m"]["picks"] == 2 and r["by_year"]["2021"]["m"]["picks"] == 1   # NaN excluded
    assert r["years_compared"] == 3
    assert r["years_model_mean_gt_prod"] == 2           # 2019 (.02>.01), 2021 (-.01>-.02); 2020 .03<.04 ... model < prod
    assert r["years_model_median_gt_prod"] == 2
    assert r["pooled"]["ex_2020"]["m"]["picks"] == 3 and r["pooled"]["ex_2020"]["m"]["mean"] == pytest.approx(0.01)
    assert r["pooled"]["ex_qa"]["m"]["picks"] == 4
    nq = score.afterpick_by_year({"m": model, "prod_pmin": prod}, "m", "prod_pmin", qa_available=False)
    assert "ex_qa" not in nq["pooled"] and "ex_2020" in nq["pooled"]


def test_continuous_run_end_to_end_and_report(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LAB_ROOT", tmp_path / "lab")        # no QA file there
    _fake_run(tmp_path, monkeypatch, with_vix=True)
    mp = paths.RUNS_DIR / "r1" / "meta.json"
    m = json.loads(mp.read_text()); m["target"] = "t4_ret_h16"; mp.write_text(json.dumps(m))
    refs = ["prod_pmin", "coin", "rsi", "low10", "vol"]
    s = score.score_run("r1", refs)
    assert s["continuous"] is True and s["magnitude"]["overall"] == s["overall"]
    assert "overall_detection" in s and s["deciles"]["model"]["rows"] and "prod_pmin" in s["deciles"] and "vol" in s["deciles"]
    ay = s["afterpick_by_year"]
    assert ay["by_year"] and "ex_2020" in ay["pooled"] and "ex_qa" not in ay["pooled"]
    js = json.loads((paths.RUNS_DIR / "r1" / "score_summary.json").read_text())
    assert {"magnitude", "deciles", "afterpick_by_year"} <= set(js)
    text = report.write_report("r1", s).read_text()
    assert "Magnitude verdict" in text and "Deciles" in text and "trailing volatility" in text
    assert "After-pick by year (informational" in text
    # a classification run carries the by-year table too, but no magnitude block
    m["target"] = "t1w_min_w4"; mp.write_text(json.dumps(m))
    s2 = score.score_run("r1", refs)
    assert s2["magnitude"] is None and s2["afterpick_by_year"]["by_year"]
    assert s2["overall"] == "PASS"
