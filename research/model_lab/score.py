"""Curve-based scorer: a model is judged on its own terms against hindsight truth, never through the strategy.

Events, not bars: firing bars at/above a threshold cluster into picks; picks are matched one-to-one to hindsight
pivots (T1w/T1z) within a tolerance. Thresholds sweep a grid of firing RATES, so every model yields a
precision/recall curve; production P(min), a coin and simple rules are scored on the identical rows.
"""
import argparse
import json
import re

import numpy as np
import pandas as pd

from research.model_lab import bars as bars_mod
from research.model_lab import paths, references, store
from research.model_lab import targets as tgt_mod

RATES = [0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2]   # share of bars at/above the threshold
TOL = {tf: tgt_mod.SCALES[tf][0] for tf in tgt_mod.SCALES}          # pick window in bars (15m: 4)


def truth_tol(truth: str, tf: str) -> int:
    """Match tolerance for one truth column: TOL[tf], but never wider than half a ±w window (w // 2, ≥ 1).
    Main session 2026-10-18: with tol == w (day t1w_w3, tol 3) a coin reached AP 0.41 — the truth saturated."""
    m = re.match(r"^t1w_(?:min|max)_w(\d+)$", truth)
    return min(TOL[tf], max(1, int(m.group(1)) // 2)) if m else TOL[tf]
BARS_PER_YEAR = {"15m": 25 * 248, "30m": 13 * 248, "60m": 7 * 248, "4h": 2 * 248, "dayagg": 248, "day": 248, "week": 52}
COST = 0.0022
PROFILE_RATES = (0.002, 0.01, 0.05)
MIN_PIVOTS = 10
WIN_SHARE = 2 / 3
YEARS = list(range(2000, 2041))
VIX_LABELS = ("low", "mid", "high", "na")
NIFTY_LABELS = ("up", "flat", "down", "na")
_SCOPES = ("all", "fold", "year", "vix", "nifty")
_BIG = 1 << 40


# ---------------------------------------------------------------- event primitives

def picks(score: np.ndarray, tau, tol: int, pos: np.ndarray | None = None) -> np.ndarray:
    """Indices (into `score`) of pick starts. Firings (score >= tau) form runs (gap to the previous firing
    <= tol); within a run, a pick claims only its tolerance window: firings within tol bars of the pick are the
    same event, and a run that keeps firing opens a new pick every tol + 1 bars (main session 2026-10-18 —
    unbounded chaining made recall FALL as the firing rate rose). `pos` defaults to the index."""
    fi = np.flatnonzero(np.asarray(score) >= tau)
    if len(fi) == 0:
        return fi
    p = fi if pos is None else np.asarray(pos)[fi]
    p = np.asarray(p, dtype=np.int64)
    new_run = np.concatenate([[True], np.diff(p) > tol])
    run_id = np.cumsum(new_run) - 1
    run_start = p[new_run][run_id]
    bucket = (p - run_start) // (tol + 1)
    start = new_run | np.concatenate([[False], np.diff(bucket) != 0])
    return fi[start]


def _match(pp: np.ndarray, qq: np.ndarray, tol: int) -> tuple[np.ndarray, np.ndarray]:
    """Greedy one-to-one matching, candidate pairs in increasing |distance| (ties: earlier pick, then earlier
    pivot). Returns (pick_idx, pivot_idx) arrays. Vectorised in rounds: a pair is accepted when it is the
    earliest remaining pair for both endpoints, which is exactly what the sequential greedy would do."""
    empty = (np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64))
    if len(pp) == 0 or len(qq) == 0:
        return empty
    lo = np.searchsorted(qq, pp - tol, side="left")
    hi = np.searchsorted(qq, pp + tol, side="right")
    cnt = hi - lo
    tot = int(cnt.sum())
    if tot == 0:
        return empty
    pi = np.repeat(np.arange(len(pp)), cnt)
    qi = np.arange(tot) - np.repeat(np.cumsum(cnt) - cnt, cnt) + np.repeat(lo, cnt)
    d = np.abs(pp[pi] - qq[qi])
    order = np.lexsort((qi, pi, d))
    pi, qi = pi[order], qi[order]
    out_p, out_q = [], []
    while len(pi):
        k = np.arange(len(pi))
        fp = np.full(len(pp), len(pi) + 1); fp[pi[::-1]] = k[::-1]
        fq = np.full(len(qq), len(pi) + 1); fq[qi[::-1]] = k[::-1]
        ok = (fp[pi] == k) & (fq[qi] == k)
        out_p.append(pi[ok]); out_q.append(qi[ok])
        used_p = np.zeros(len(pp), dtype=bool); used_p[pi[ok]] = True
        used_q = np.zeros(len(qq), dtype=bool); used_q[qi[ok]] = True
        keep = ~(used_p[pi] | used_q[qi])
        pi, qi = pi[keep], qi[keep]
    return np.concatenate(out_p), np.concatenate(out_q)


def match_events(pick_pos, pivot_pos, tol) -> list[tuple[int, int]]:
    """Pairs (pick_pos, pivot_pos), one-to-one, nearest first (tolerance inclusive)."""
    pp = np.asarray(pick_pos); qq = np.asarray(pivot_pos)
    a, b = _match(pp, qq, tol)
    return [(int(pp[i]), int(qq[j])) for i, j in zip(a, b)]


def _dist_pct(close_p, ref_q, side: str):
    return 100.0 * (close_p / ref_q - 1.0) if side == "min" else 100.0 * (1.0 - close_p / ref_q)


def event_counts(score, truth, pos, low, high, close, tau, tol, side) -> dict:
    """Counts for one score series at one threshold. Arrays are aligned evaluated rows (pos = bar position)."""
    score = np.asarray(score, float); truth = np.asarray(truth, float); pos = np.asarray(pos)
    pk = picks(score, tau, tol, pos)
    judged = pk[~np.isnan(truth[pk])]
    unjudged = len(pk) - len(judged)
    pv = np.flatnonzero(truth == 1)
    mp, mq = _match(pos[judged], pos[pv], tol)
    lat = pos[judged][mp] - pos[pv][mq]
    ref = np.asarray(low if side == "min" else high, float)[pv][mq]
    dist = _dist_pct(np.asarray(close, float)[judged][mp], ref, side)
    return {"picks": int(len(pk)), "unjudged": int(unjudged), "matched": int(len(mp)), "pivots": int(len(pv)),
            "lateness_med": float(np.median(lat)) if len(lat) else float("nan"),
            "dist_med_pct": float(np.median(dist)) if len(dist) else float("nan"),
            "bars": int(len(score))}


def event_ap(points: list[dict]) -> float:
    pts = [(p["recall"], p["precision"]) for p in points
           if p["recall"] is not None and p["precision"] is not None
           and not (np.isnan(p["recall"]) or np.isnan(p["precision"]))]
    if not pts:
        return float("nan")
    best: dict[float, float] = {}
    for r, pr in pts:
        best[r] = max(pr, best.get(r, -1.0))
    ap, prev = 0.0, 0.0
    for r in sorted(best):
        ap += (r - prev) * best[r]
        prev = r
    return float(ap)


def spearman(a, b) -> float:
    a = np.asarray(a, float); b = np.asarray(b, float)
    ok = ~(np.isnan(a) | np.isnan(b))
    if ok.sum() < 3:
        return float("nan")
    ra = pd.Series(a[ok]).rank().to_numpy(); rb = pd.Series(b[ok]).rank().to_numpy()
    if ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def pinball(y, pred, q) -> float:
    y = np.asarray(y, float); pred = np.asarray(pred, float)
    ok = ~(np.isnan(y) | np.isnan(pred))
    if not ok.any():
        return float("nan")
    e = y[ok] - pred[ok]
    return float(np.mean(np.maximum(q * e, (q - 1) * e)))


def coverage(y, lo, hi) -> float:
    y = np.asarray(y, float); lo = np.asarray(lo, float); hi = np.asarray(hi, float)
    ok = ~(np.isnan(y) | np.isnan(lo) | np.isnan(hi))
    if not ok.any():
        return float("nan")
    return float(np.mean((y[ok] >= lo[ok]) & (y[ok] <= hi[ok])))


# ---------------------------------------------------------------- regimes

def _regime_labels(ts: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """(vix, nifty) label arrays for row timestamps, joined strictly to the PREVIOUS session."""
    n = len(ts)
    vix_out = np.full(n, "na", dtype=object); nif_out = np.full(n, "na", dtype=object)
    dates = pd.DataFrame({"d": pd.to_datetime(ts).dt.normalize().to_numpy(), "i": np.arange(n)}).sort_values("d")

    def prior(series: pd.Series, dts: pd.Series) -> np.ndarray:
        left = dates.copy()
        right = pd.DataFrame({"d": pd.to_datetime(dts).dt.normalize().to_numpy(), "v": series.to_numpy(float)})
        right = right.dropna().sort_values("d")
        m = pd.merge_asof(left, right, on="d", allow_exact_matches=False)
        out = np.full(n, np.nan); out[m["i"].to_numpy()] = m["v"].to_numpy()
        return out

    vix = store.read_bars("NSE:INDIA VIX", "day")
    if len(vix):
        pct = vix["close"].rolling(252, min_periods=200).rank(pct=True)
        v = prior(pct, vix["timestamp"])
        ok = ~np.isnan(v)
        vix_out[ok] = np.where(v[ok] < 1 / 3, "low", np.where(v[ok] < 2 / 3, "mid", "high"))
    nif = store.read_bars("NSE:NIFTY 50", "day")
    if len(nif):
        tr = nif["close"] / nif["close"].shift(50) - 1
        v = prior(tr, nif["timestamp"])
        ok = ~np.isnan(v)
        nif_out[ok] = np.where(v[ok] > 0.03, "up", np.where(v[ok] < -0.03, "down", "flat"))
    return vix_out, nif_out


# ---------------------------------------------------------------- run scoring

_REF_MAX = {"prod_pmin": "prod_pmax", "rsi": "rsi_hi", "low10": "high10", "low20": "high20", "low50": "high50"}
_T1 = re.compile(r"^t1([wz])_(min|max)_")


def _side(target: str) -> str:
    m = _T1.match(target or "")
    return m.group(2) if m else "min"


def detection_truths(tgt_cols, tf: str, side: str, run_target: str | None) -> list[str]:
    cols = [c for c in tgt_cols if re.match(rf"^t1w_{side}_w\d+$", c) or re.match(rf"^t1z_{side}_k\d+$", c)]
    if run_target and _T1.match(run_target) and run_target in tgt_cols and run_target not in cols:
        cols.insert(0, run_target)
    elif run_target in cols:
        cols.remove(run_target); cols.insert(0, run_target)
    return cols


def _is_continuous(target: str | None) -> bool:
    """Run targets scored on magnitude: T3/T4/T5 continuous columns (not the T5 hit flags or endbars)."""
    t = target or ""
    return t.startswith(("t3_", "t4_", "t5_")) and not t.startswith("t5_hit_") and "_endbars_" not in t


def decile_table(score, y, n: int = 10) -> dict:
    """Bin rows by deciles of `score` (rank-based, ties broken by order); mean / median realised y per bin."""
    score = np.asarray(score, float); y = np.asarray(y, float)
    ok = ~(np.isnan(score) | np.isnan(y))
    score, y = score[ok], y[ok]
    if len(y) < n:
        return {"rows": [], "spread": float("nan")}
    r = pd.Series(score).rank(method="first").to_numpy()
    b = np.minimum(((r - 1) * n / len(r)).astype(int), n - 1)
    rows = [{"decile": i + 1, "n": int((b == i).sum()), "mean": float(y[b == i].mean()),
             "median": float(np.median(y[b == i]))} for i in range(n)]
    return {"rows": rows, "spread": float(rows[-1]["mean"] - rows[0]["mean"])}


def magnitude_verdict(score_mat: np.ndarray, models: list[str], y: np.ndarray, fold_idx: np.ndarray,
                      year: np.ndarray, side: str, fold_ids: list[int], min_rows: int = 200) -> dict:
    """Does the model (column 0) rank the realised run target better than each reference, fold by fold and year
    by year? model: signed Spearman; refs: |Spearman| (a reference may rank either way)."""
    y = np.asarray(y, float)
    M = len(models)

    def groups(labels):
        out = {}
        for g in np.unique(labels):
            sel = (labels == g) & ~np.isnan(y)
            if sel.sum() >= min_rows:
                out[g] = sel
        return out

    def shares(grp):
        res = {}
        for j in range(1, M):
            wins = n = 0
            for sel in grp.values():
                rm = spearman(score_mat[sel, 0], y[sel]); rr = abs(spearman(score_mat[sel, j], y[sel]))
                if np.isnan(rm) or np.isnan(rr):
                    continue
                n += 1; wins += int(rm > rr)
            res[j] = (wins / n if n else float("nan"), n)
        return res

    fg = groups(fold_idx); yg = groups(year)
    fs, ys = shares(fg), shares(yg)
    vs = {}
    for j in range(1, M):
        f_, nf_ = fs[j]; y_, ny_ = ys[j]
        vs[models[j]] = {"fold_win_share": f_, "n_folds": nf_, "year_win_share": y_, "n_years": ny_,
                         "win": bool(nf_ > 0 and ny_ > 0 and f_ >= WIN_SHARE and y_ >= WIN_SHARE)}
    allsel = ~np.isnan(y)
    pooled = {models[j]: spearman(score_mat[allsel, j], y[allsel]) for j in range(M)}
    pooled_abs = {k: (abs(v) if not np.isnan(v) else float("nan")) for k, v in pooled.items()}
    need = ["prod_pmax", "rsi_hi", "vol"] if side == "max" else ["prod_pmin", "rsi", "vol"]
    overall = "NO_REF" if any(r not in vs for r in need) else ("PASS" if all(vs[r]["win"] for r in need) else "FAIL")
    return {"verdicts": vs, "pooled_rho": pooled, "pooled_abs_rho": pooled_abs, "overall": overall,
            "required_refs": need, "n_folds": len(fg), "n_years": len(yg)}


def afterpick_by_year(arrs: dict, model: str, prod: str | None, qa_available: bool) -> dict:
    """arrs: name -> array [year, net_ret, qa_flag] of the picks at one rate (net_ret may be NaN).
    Per calendar year mean / median / count for each name; years the model beats prod; pooled ex-QA, ex-2020."""
    out: dict = {"by_year": {}, "years_model_mean_gt_prod": None, "years_model_median_gt_prod": None,
                 "years_compared": None, "pooled": {}}
    clean = {k: (a[~np.isnan(a[:, 1])] if len(a) else np.zeros((0, 3))) for k, a in arrs.items()}
    years = sorted({int(y) for a in clean.values() for y in a[:, 0]})
    for y in years:
        out["by_year"][str(y)] = {}
        for k, a in clean.items():
            v = a[a[:, 0] == y, 1]
            out["by_year"][str(y)][k] = {"picks": int(len(v)), "mean": float(v.mean()) if len(v) else np.nan,
                                         "median": float(np.median(v)) if len(v) else np.nan}
    if prod and prod in clean and model in clean:
        gm = gd = n = 0
        for y in years:
            m_, p_ = out["by_year"][str(y)][model], out["by_year"][str(y)][prod]
            if m_["picks"] == 0 or p_["picks"] == 0:
                continue
            n += 1; gm += int(m_["mean"] > p_["mean"]); gd += int(m_["median"] > p_["median"])
        out["years_model_mean_gt_prod"] = gm; out["years_model_median_gt_prod"] = gd; out["years_compared"] = n

    def pool(filt):
        res = {}
        for k, a in clean.items():
            v = a[filt(a), 1] if len(a) else np.zeros(0)
            res[k] = {"picks": int(len(v)), "mean": float(v.mean()) if len(v) else np.nan,
                      "median": float(np.median(v)) if len(v) else np.nan}
        return res

    out["pooled"]["all"] = pool(lambda a: np.ones(len(a), bool))
    if qa_available:
        out["pooled"]["ex_qa"] = pool(lambda a: a[:, 2] == 0)
    out["pooled"]["ex_2020"] = pool(lambda a: a[:, 0] != 2020)
    return out


def _qa_flagged(tf: str) -> set | None:
    p = paths.LAB_ROOT / f"qa_{bars_mod.SOURCE[tf]}.csv"
    if not p.exists():
        return None
    q = pd.read_csv(p)
    if "symbol" not in q.columns or "n_jumps_30" not in q.columns:
        return None
    return set(q.loc[q["n_jumps_30"] > 0, "symbol"])


def _gid_tables(fold_ids: list[int]):
    keys = [("all", "all")] + [("fold", str(f)) for f in fold_ids] + [("year", str(y)) for y in YEARS] \
        + [("vix", k) for k in VIX_LABELS] + [("nifty", k) for k in NIFTY_LABELS]
    return keys, {k: i for i, k in enumerate(keys)}


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    return o


def score_run(run_id: str, refs: list[str], targets: list[str] | None = None, tf: str | None = None) -> dict:
    run_dir = paths.RUNS_DIR / run_id
    meta = json.loads((run_dir / "meta.json").read_text())
    tf = tf or meta["tf"]
    tol = TOL[tf]
    model_name = str(meta.get("model", "model"))
    run_target = meta.get("target")
    side = _side(run_target)
    folds = pd.read_parquet(run_dir / "folds.parquet")
    fold_ids = sorted(int(f) for f in folds["fold_id"])
    fidx_of = {f: i for i, f in enumerate(fold_ids)}
    keys, gid = _gid_tables(fold_ids)
    NG = len(keys)
    used_refs = [(_REF_MAX.get(r, r) if side == "max" else r) for r in refs]
    models = [model_name] + used_refs
    truth_override = targets
    M = len(models)
    Hmid = int(tgt_mod.HOLD_H[tf][1])
    syms = [s for s in meta["symbols"] if (run_dir / "scores" / f"{paths.sym_file(s)}.parquet").exists()]
    mfe, mae, ttm, ret, hit = (f"t5_mfe_H{Hmid}", f"t5_maepre_H{Hmid}", f"t5_ttm_H{Hmid}", f"t5_ret_H{Hmid}",
                               f"t5_hit_x5_y3_H{Hmid}")
    sp_cols = ["t3_ret_k5", "t4_ret_h16", mfe, mae, ttm]
    continuous = _is_continuous(run_target)
    qa_set = _qa_flagged(tf)
    t2_pat = "t2_up_h" if side == "min" else "t2_dn_h"

    data: list[dict] = []
    total_rows = 0
    ref_nonnan = np.zeros(M, dtype=np.int64)
    truths: list[str] | None = None
    t2_cols: list[str] = []
    pred_cols: list[str] = []
    pred_bases: list[str] = []
    for sym in syms:
        b = bars_mod.load(sym, tf)
        if len(b) == 0:
            continue
        sc = pd.read_parquet(run_dir / "scores" / f"{paths.sym_file(sym)}.parquet")
        pos = pd.Index(b["timestamp"]).get_indexer(pd.to_datetime(sc["timestamp"]))
        keep = pos >= 0
        sc = sc[keep].reset_index(drop=True); pos = pos[keep]
        total_rows += len(sc)
        mat = np.full((len(sc), M), np.nan)
        mat[:, 0] = sc["score"].to_numpy(float)
        ref_nonnan[0] += int((~np.isnan(mat[:, 0])).sum())
        for j, rn in enumerate(models[1:], start=1):
            r = references.read_ref(tf, rn, sym)
            if r is None:
                continue
            col = "score"
            vals = pd.Series(r[col].to_numpy(float), index=pd.to_datetime(r["timestamp"])).reindex(
                pd.to_datetime(sc["timestamp"])).to_numpy()
            mat[:, j] = vals
            ref_nonnan[j] += int((~np.isnan(vals)).sum())
        ev = ~np.isnan(mat).any(axis=1)
        if not ev.any():
            continue
        tgt = tgt_mod.build_targets(b, tf)
        if truths is None:
            truths = list(truth_override) if truth_override else detection_truths(tgt.columns, tf, side, run_target)
            t2_cols = [c for c in tgt.columns if c.startswith(t2_pat)]
            pred_cols = [c for c in sc.columns if c.startswith("pred_")]
            pred_bases = list(dict.fromkeys(
                (re.match(r"^pred_(.+)_q(\d+)$", c).group(1) if re.match(r"^pred_(.+)_q(\d+)$", c) else c[5:])
                for c in pred_cols))
        sc = sc[ev].reset_index(drop=True); pos = pos[ev]; mat = mat[ev]
        fidx = sc["fold_id"].map(fidx_of).to_numpy()
        if np.isnan(fidx.astype(float)).any():
            raise ValueError(f"{sym}: scores contain fold_id not in folds.parquet")
        fidx = fidx.astype(np.int64)
        order = np.lexsort((pos, fidx))
        sc = sc.iloc[order].reset_index(drop=True); pos = pos[order]; mat = mat[order]; fidx = fidx[order]
        comp = fidx.astype(np.int64) * _BIG + pos
        ts = pd.to_datetime(sc["timestamp"])
        vix_l, nif_l = _regime_labels(ts)
        G = np.empty((len(sc), 5), dtype=np.int32)
        G[:, 0] = 0
        G[:, 1] = [gid[("fold", str(fold_ids[i]))] for i in fidx]
        G[:, 2] = [gid[("year", str(y))] for y in ts.dt.year]
        G[:, 3] = [gid[("vix", v)] for v in vix_l]
        G[:, 4] = [gid[("nifty", v)] for v in nif_l]
        tt = np.full((len(sc), len(truths)), -1, dtype=np.int8)
        for k, c in enumerate(truths):
            v = tgt[c].to_numpy(float)[pos]
            tt[:, k] = np.where(np.isnan(v), -1, np.nan_to_num(v).astype(np.int8))
        extra = {c: tgt[c].to_numpy(float)[pos] for c in dict.fromkeys(sp_cols + [ret, hit] + t2_cols + pred_bases + ([run_target] if continuous else []))
                 if c in tgt.columns}
        pred = {c: sc[c].to_numpy(float) for c in pred_cols}
        data.append({"sym": sym, "comp": comp, "pos": pos, "fidx": fidx, "G": G, "score": mat, "truth": tt,
                     "close": b["close"].to_numpy(float)[pos], "low": b["low"].to_numpy(float)[pos],
                     "high": b["high"].to_numpy(float)[pos], "extra": extra, "pred": pred,
                     "year": ts.dt.year.to_numpy(), "qa": float(qa_set is not None and sym in qa_set)})
    truths = truths or []
    tol_t = [truth_tol(tc, tf) for tc in truths]
    T = len(truths)
    R = len(RATES)
    coverage_out = {m: (float(ref_nonnan[i] / total_rows) if total_rows else float("nan")) for i, m in enumerate(models)}

    # per (model, fold) thresholds from pooled evaluated rows
    nf = len(fold_ids)
    tau = np.full((M, nf, R), np.inf)
    for m in range(M):
        for f in range(nf):
            v = np.concatenate([d["score"][d["fidx"] == f, m] for d in data]) if data else np.zeros(0)
            if len(v) == 0:
                continue
            if np.isin(np.unique(v), (0.0, 1.0)).all():
                tau[m, f, :] = 1.0                      # binary rule: natural threshold at every rate
            else:
                for r, rate in enumerate(RATES):
                    tau[m, f, r] = np.quantile(v, 1.0 - rate)

    shp = (M, T, R, NG)
    a_picks = np.zeros(shp); a_unj = np.zeros(shp); a_match = np.zeros(shp)
    a_piv = np.zeros((T, NG)); a_bars = np.zeros(NG)
    lat_l: dict = {}; dst_l: dict = {}; grp_l: dict = {}
    prof: dict = {(m, r): [] for m in range(M) for r in PROFILE_RATES}
    for d in data:
        n = len(d["comp"])
        a_bars += np.bincount(d["G"].ravel(), minlength=NG)
        piv_rows = []
        for t in range(T):
            pr = np.flatnonzero(d["truth"][:, t] == 1)
            piv_rows.append(pr)
            a_piv[t] += np.bincount(d["G"][pr].ravel(), minlength=NG)
        for m in range(M):
            for ri, rate in enumerate(RATES):
                tau_row = tau[m, d["fidx"], ri]
                pk = picks(d["score"][:, m], tau_row, tol, d["comp"])
                if len(pk) == 0:
                    continue
                if rate in PROFILE_RATES:
                    prof[(m, rate)].append(np.column_stack([d["extra"][c][pk] for c in (mfe, mae, ttm, ret, hit)]
                                                      + [d["year"][pk], np.full(len(pk), d["qa"])]))
                cg = np.bincount(d["G"][pk].ravel(), minlength=NG)
                for t in range(T):
                    tr = d["truth"][pk, t]
                    jm = tr != -1
                    jp = pk[jm]
                    ug = np.bincount(d["G"][pk[~jm]].ravel(), minlength=NG)
                    a_picks[m, t, ri] += cg
                    a_unj[m, t, ri] += ug
                    mp, mq = _match(d["comp"][jp], d["comp"][piv_rows[t]], tol_t[t])
                    if len(mp) == 0:
                        continue
                    pr_ = jp[mp]; qr_ = piv_rows[t][mq]
                    a_match[m, t, ri] += np.bincount(d["G"][pr_].ravel(), minlength=NG)
                    ref = d["low" if side == "min" else "high"][qr_]
                    k = (m, t, ri)
                    lat_l.setdefault(k, []).append((d["comp"][pr_] - d["comp"][qr_]).astype(np.float32))
                    dst_l.setdefault(k, []).append(_dist_pct(d["close"][pr_], ref, side).astype(np.float32))
                    grp_l.setdefault(k, []).append(d["G"][pr_])

    # medians per group
    lat_med = np.full(shp, np.nan); dst_med = np.full(shp, np.nan)
    for k in lat_l:
        lat = np.concatenate(lat_l[k]); dst = np.concatenate(dst_l[k]); g = np.concatenate(grp_l[k])
        for s in range(5):
            gs = pd.Series(lat).groupby(g[:, s]).median()
            lat_med[k][gs.index.to_numpy()] = gs.to_numpy()
            gs = pd.Series(dst).groupby(g[:, s]).median()
            dst_med[k][gs.index.to_numpy()] = gs.to_numpy()

    # curves
    bpy = BARS_PER_YEAR[tf]
    rows = []
    for m in range(M):
        for t in range(T):
            for ri, rate in enumerate(RATES):
                for gi, (scope, key) in enumerate(keys):
                    if scope not in ("all", "fold", "year") or a_bars[gi] == 0:
                        continue
                    pk = a_picks[m, t, ri, gi]; uj = a_unj[m, t, ri, gi]; mt = a_match[m, t, ri, gi]
                    pv = a_piv[t, gi]
                    judged = pk - uj
                    fold_tau = (tau[m, fold_ids.index(int(key)), ri] if scope == "fold" else np.nan)
                    rows.append({"scope": scope, "key": key, "model": models[m], "truth": truths[t], "rate": rate,
                                 "tau": float(fold_tau), "picks": int(pk), "unjudged": int(uj), "matched": int(mt),
                                 "pivots": int(pv),
                                 "precision": float(mt / judged) if judged > 0 else np.nan,
                                 "recall": float(mt / pv) if pv > 0 else np.nan,
                                 "picks_per_stock_year": float(pk / (a_bars[gi] / bpy)),
                                 "lateness_med": float(lat_med[m, t, ri, gi]),
                                 "dist_med_pct": float(dst_med[m, t, ri, gi])})
    curves = pd.DataFrame(rows, columns=["scope", "key", "model", "truth", "rate", "tau", "picks", "unjudged",
                                         "matched", "pivots", "precision", "recall", "picks_per_stock_year",
                                         "lateness_med", "dist_med_pct"])

    # AP per group
    def group_ap(m, t, gi):
        pts = []
        judged = a_picks[m, t, :, gi] - a_unj[m, t, :, gi]
        for ri in range(R):
            pv = a_piv[t, gi]
            pts.append({"recall": a_match[m, t, ri, gi] / pv if pv > 0 else np.nan,
                        "precision": a_match[m, t, ri, gi] / judged[ri] if judged[ri] > 0 else np.nan})
        return event_ap(pts)

    ap: dict = {}
    for t, tc in enumerate(truths):
        ap[tc] = {}
        for m, mn in enumerate(models):
            ap[tc][mn] = {"all": group_ap(m, t, 0)}
            for scope in ("fold", "year", "vix", "nifty"):
                ap[tc][mn][scope] = {key: group_ap(m, t, gid[(scope, key)]) for (sc_, key) in keys
                                     if sc_ == scope and a_bars[gid[(sc_, key)]] > 0}
    pivots = {tc: {scope: {key: int(a_piv[t, gid[(scope, key)]]) for (sc_, key) in keys if sc_ == scope
                           and a_bars[gid[(sc_, key)]] > 0} for scope in ("all", "fold", "year", "vix", "nifty")}
              for t, tc in enumerate(truths)}

    # verdicts
    def share(tc, mn, rn, scope):
        wins = n = 0
        for key, pv in pivots[tc][scope].items():
            if pv < MIN_PIVOTS:
                continue
            a, b_ = ap[tc][mn][scope].get(key, np.nan), ap[tc][rn][scope].get(key, np.nan)
            if np.isnan(a) or np.isnan(b_):
                continue
            n += 1; wins += int(a > b_)
        return (wins / n if n else float("nan")), n

    verdicts: dict = {}
    for tc in truths:
        verdicts[tc] = {}
        for rn in models[1:]:
            fs, nf_ = share(tc, models[0], rn, "fold"); ys, ny = share(tc, models[0], rn, "year")
            verdicts[tc][rn] = {"fold_win_share": fs, "n_folds": nf_, "year_win_share": ys, "n_years": ny,
                                "win": bool(nf_ > 0 and ny > 0 and fs >= WIN_SHARE and ys >= WIN_SHARE)}
    prod = "prod_pmax" if side == "max" else "prod_pmin"

    def overall_for(tc):
        if prod not in models[1:]:
            return "NO_REF"
        need = [prod] + (["coin"] if "coin" in models[1:] else [])
        return "PASS" if all(verdicts[tc][r]["win"] for r in need) and "coin" in models[1:] else "FAIL"

    primary = truths[0] if truths else None
    overall_by_truth = {tc: overall_for(tc) for tc in truths}
    if not truths:
        overall = "NO_REF"
    else:
        overall = overall_by_truth[primary]
    overall_all = ("NO_REF" if overall == "NO_REF" else
                   "PASS" if all(v == "PASS" for v in overall_by_truth.values()) else "FAIL")

    # T2 / Spearman / pred tables over pooled rows, per fold
    def pooled(fn_cols):
        return {c: np.concatenate([d["extra"][c] for d in data]) for c in fn_cols if data and c in data[0]["extra"]}

    fold_all = np.concatenate([d["fidx"] for d in data]) if data else np.zeros(0, dtype=int)
    score_all = np.vstack([d["score"] for d in data]) if data else np.zeros((0, M))
    ex = pooled(sp_cols + t2_cols)
    from sklearn.metrics import average_precision_score, roc_auc_score
    t2: dict = {}
    for c in t2_cols:
        y = ex[c]
        t2[c] = {}
        for m, mn in enumerate(models):
            t2[c][mn] = {}
            for f in range(nf):
                sel = (fold_all == f) & ~np.isnan(y)
                yy = y[sel]
                if len(yy) and 0 < yy.sum() < len(yy):
                    t2[c][mn][str(fold_ids[f])] = {"auc": float(roc_auc_score(yy, score_all[sel, m])),
                                                   "ap": float(average_precision_score(yy, score_all[sel, m]))}
    spear: dict = {}
    for c in sp_cols:
        if c not in ex:
            continue
        spear[c] = {mn: {str(fold_ids[f]): spearman(score_all[fold_all == f, m], ex[c][fold_all == f])
                         for f in range(nf)} for m, mn in enumerate(models)}
    preds: dict = {}
    if data and pred_cols:
        tg_all: dict = {}
        for pc in pred_cols:
            mq = re.match(r"^pred_(.+)_q(\d+)$", pc)
            base = mq.group(1) if mq else pc[len("pred_"):]
            if base not in tg_all:
                tg_all[base] = np.concatenate([d["extra"][base] for d in data])
        pv_all = {pc: np.concatenate([d["pred"][pc] for d in data]) for pc in pred_cols}
        qcols: dict = {}
        for pc in pred_cols:
            mq = re.match(r"^pred_(.+)_q(\d+)$", pc)
            if mq:
                base, q = mq.group(1), int(mq.group(2))
                qcols.setdefault(base, {})[q] = pc
                y = tg_all[base]
                preds[pc] = {str(fold_ids[f]): {"pinball": pinball(y[fold_all == f], pv_all[pc][fold_all == f], q / 100)}
                             for f in range(nf)}
            else:
                y = tg_all[pc[len("pred_"):]]
                preds[pc] = {str(fold_ids[f]): {"spearman": spearman(pv_all[pc][fold_all == f], y[fold_all == f])}
                             for f in range(nf)}
        for base, qs in qcols.items():
            if len(qs) >= 2:
                lo, hi = qs[min(qs)], qs[max(qs)]
                for f in range(nf):
                    preds[f"coverage_{base}"] = preds.get(f"coverage_{base}", {})
                    preds[f"coverage_{base}"][str(fold_ids[f])] = {
                        "coverage": coverage(tg_all[base][fold_all == f], pv_all[lo][fold_all == f],
                                             pv_all[hi][fold_all == f])}

    # after-pick profile (informational)
    after = {}
    for rate in PROFILE_RATES:
        after[str(rate)] = {}
        for m, mn in enumerate(models):
            parts = prof[(m, rate)]
            arr = np.vstack(parts) if parts else np.zeros((0, 7))
            out = {"picks": int(len(arr))}
            for j, nm in enumerate(("mfe", "maepre", "ttm", "ret")):
                v = arr[:, j]; v = v[~np.isnan(v)]
                out[f"{nm}_mean"] = float(v.mean()) if len(v) else np.nan
                out[f"{nm}_median"] = float(np.median(v)) if len(v) else np.nan
            v = arr[:, 3]; v = v[~np.isnan(v)] - COST
            out["net_ret_mean"] = float(v.mean()) if len(v) else np.nan
            out["net_ret_median"] = float(np.median(v)) if len(v) else np.nan
            h_ = arr[:, 4]; h_ = h_[~np.isnan(h_)]
            out["hit_x5_y3_rate"] = float(h_.mean()) if len(h_) else np.nan
            out["t5_nan_excluded"] = int(np.isnan(arr[:, 3]).sum())
            after[str(rate)][mn] = out

    # after-pick by year (every run, informational): picks at rate 0.01, net of COST
    prod_name = prod if prod in models[1:] else None
    abyy = afterpick_by_year(
        {mn: (lambda a: np.column_stack([a[:, 5], a[:, 3] - COST, a[:, 6]]) if len(a) else np.zeros((0, 3)))(
            np.vstack(prof[(m, 0.01)]) if prof[(m, 0.01)] else np.zeros((0, 7))) for m, mn in enumerate(models)},
        models[0], prod_name, qa_set is not None)
    abyy["rate"] = 0.01; abyy["hold_H"] = Hmid; abyy["qa_file_found"] = qa_set is not None

    # magnitude verdict + deciles (continuous run targets only)
    magnitude = None; deciles = None
    if continuous and data and run_target in data[0]["extra"]:
        y_all = np.concatenate([d["extra"][run_target] for d in data])
        year_all = np.concatenate([d["year"] for d in data])
        magnitude = magnitude_verdict(score_all, models, y_all, fold_all, year_all, side, fold_ids)
        deciles = {"model": decile_table(score_all[:, 0], y_all)}
        if prod_name:
            j = models.index(prod_name)
            deciles[prod_name] = decile_table(score_all[:, j], y_all)
        if "vol" in models[1:]:
            deciles["vol"] = decile_table(score_all[:, models.index("vol")], y_all)
        deciles["target"] = run_target
        overall_detection = overall
        overall = magnitude["overall"]
    else:
        overall_detection = overall

    summary = {"run_id": run_id, "tf": tf, "side": side, "tol": tol, "truth_tol": dict(zip(truths, tol_t)), "models": models, "truths": truths,
               "primary_truth": primary, "meta": {k: meta.get(k) for k in
                                                  ("tf", "scheme", "target", "model", "symbols",
                                                   "universe_top_n", "seed", "created")},
               "folds": fold_ids, "rows_total": int(total_rows),
               "rows_evaluated": int(a_bars[0]), "symbols_scored": [d["sym"] for d in data],
               "coverage": coverage_out, "verdicts": verdicts, "overall": overall,
               "overall_detection": overall_detection, "continuous": continuous,
               "magnitude": magnitude, "deciles": deciles, "afterpick_by_year": abyy,
               "overall_by_truth": overall_by_truth, "overall_all_truths": overall_all,
               "ap": ap, "pivots": pivots, "t2": t2, "spearman": spear, "preds": preds,
               "after_pick_informational": after, "rates": RATES, "hold_H": Hmid}
    summary = _clean(summary)
    (run_dir / "score_summary.json").write_text(json.dumps(summary, indent=1))
    paths.check_disk()
    store._atomic_write(run_dir / "curves.parquet", lambda t: curves.to_parquet(
        t, engine="pyarrow", compression="zstd", index=False))
    summary["_curves"] = curves
    return summary


def main() -> None:
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("--run", required=True)
    ap_.add_argument("--refs", nargs="*", default=["prod_pmin", "coin", "rsi", "low10", "low20", "low50", "vol"])
    ap_.add_argument("--tf", default=None)
    a = ap_.parse_args()
    s = score_run(a.run, a.refs, tf=a.tf)
    from research.model_lab import report
    out = report.write_report(a.run, s)
    print(f"{s['overall']} -> {out}")


if __name__ == "__main__":
    main()
