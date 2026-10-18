"""
Stage A — detection quality against "tradeable trough" truth (docs/01_Extrema_Model_Campaign.md).

1. SCORE RUN: one cache-only portfolio backtest 2023-01-01 → 2026-10-16 with the engine's
   model_scores sink → the walk-forward (p_min, p_max) series every stock's strategy actually
   produced on its own strategy timeframe. Cached under lab_data/campaign/scores/<label>.pkl.
2. TRUTH (model-independent, per stock): bar t is a GOOD TROUGH iff a long entered at close[t]
   reaches +profit_pct before any of the stock's own non-model exits fires on the close path —
   hard stop, stale tier-1 (best gain < min_gain by check_bars), stale re-arm (rolling), stale_2,
   hold_bars timeout. The same simulation gives each bar's outcome return (EV proxy: +profit_pct
   on success, the exit return otherwise) and its exit bar.
3. METRICS on the TEST window (2025-01-01 →): AUC(p_min vs good) over all bars; firings with
   position-blocking dedupe (after a firing, the next one is only counted after that bar's
   simulated exit) at the configured threshold and at the MATCHED threshold — the per-stock
   threshold that gives the baseline's firing count over the CALIBRATION window (2023-01-01 →
   2024-12-31). Precision, lift, EV, event recall. ATHERENERG also vs the 191 hand labels.

    python scripts/campaign/stage_a.py --label baseline
    python scripts/campaign/stage_a.py --label exp01 --overlay config/experiments/exp01.yaml \
        --baseline baseline --emit-overlay config/experiments/exp01_matched.yaml
    python scripts/campaign/stage_a.py --label exp01 --score-only   # just build the cache

Gate to Stage B (pre-registered): median ΔAUC ≥ +0.03 with ΔAUC < 0 on ≤ 1/3 of stocks, OR
median ΔEV@matched ≥ +0.25 pp with ΔEV < 0 on ≤ 1/3 of stocks.
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from trader.policy.outcome import simulate_exit_outcomes as simulate_exits  # noqa: E402

SCORE_FROM, SCORE_TO = "2023-01-01", "2026-10-16"
CALIB_END = datetime(2025, 1, 1)
SCORES_DIR = ROOT / "lab_data" / "campaign" / "scores"
HUMAN_LABELS = ROOT / "lab_data" / "ATHERENERG_15minute" / "labels.csv"
THR_GRID = np.round(np.arange(0.30, 0.9951, 0.005), 3)


# ---------------------------------------------------------------- score run

def score_run(label: str, overlay: str | None) -> dict:
    path = SCORES_DIR / f"{label}.pkl"
    if path.exists():
        return pickle.loads(path.read_bytes())
    import logging
    logging.disable(logging.CRITICAL)
    from scripts.campaign.run_windows import _apply_overlay
    _apply_overlay(overlay)
    from trader.backtest.engine import run_backtest
    from trader.core.config import config
    from trader.data.store import Store

    watchlist = list(config.watchlist)
    params = config.strategy_config("lr_extrema")
    overrides = config._data.get("per_stock_params") or {}
    per_symbol = {s: config.get_strategy_params(s, "lr_extrema")
                  for s in watchlist if overrides.get(s, {}).get("lr_extrema")} or None
    sink: dict[str, list[dict]] = {}
    run_backtest(None, Store(config.db_path), watchlist, {**{s: 0 for s in watchlist}, "NSE:NIFTY 50": 256265, "NSE:INDIA VIX": 264969}, params,
                 datetime.strptime(SCORE_FROM, "%Y-%m-%d"),
                 datetime.strptime(SCORE_TO, "%Y-%m-%d").replace(hour=23, minute=59),
                 per_symbol_params=per_symbol, model_scores=sink)
    stock_params = {s: config.get_strategy_params(s, "lr_extrema") for s in watchlist}
    out = {"label": label, "overlay": overlay, "scores": sink, "params": stock_params}
    SCORES_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pickle.dumps(out))
    return out


# ---------------------------------------------------------------- truth

# ---------------------------------------------------------------- metrics

def firings(score: np.ndarray, thr: float, exit_idx: np.ndarray, mask: np.ndarray) -> list[int]:
    """Bars where score >= thr inside mask, blocked while a previous firing's simulated
    position is still open."""
    out, blocked_until = [], -1
    for t in np.flatnonzero(mask & (score >= thr)):
        if t <= blocked_until:
            continue
        out.append(int(t))
        blocked_until = exit_idx[t]
    return out


def auc(score: np.ndarray, y: np.ndarray) -> float:
    from sklearn.metrics import roc_auc_score
    ok = ~np.isnan(score)
    if y[ok].all() or not y[ok].any():
        return float("nan")
    return float(roc_auc_score(y[ok], score[ok]))


def event_recall(good: np.ndarray, fired: list[int], mask: np.ndarray) -> float:
    g = good & mask
    if not g.any():
        return float("nan")
    fired_set = np.zeros(len(good), dtype=bool)
    fired_set[fired] = True
    events = hits = 0
    i, n = 0, len(g)
    while i < n:
        if g[i]:
            j = i
            while j + 1 < n and g[j + 1]:
                j += 1
            events += 1
            hits += bool(fired_set[i:j + 1].any())
            i = j + 1
        else:
            i += 1
    return hits / events


def stock_series(run: dict, sym: str):
    rows = run["scores"].get(sym) or []
    if not rows:
        return None
    ts = np.array([r["timestamp"] for r in rows])
    closes = np.array([r["close"] for r in rows], dtype=float)
    pmin = np.array([r["p_min"] for r in rows], dtype=float)
    pmax = np.array([r["p_max"] for r in rows], dtype=float)
    return ts, closes, pmin, pmax


def _match_threshold(score, exit_idx, calib, target: int, default: float) -> float:
    if target <= 0:
        return default
    best, best_err = default, None
    for thr in THR_GRID[::-1]:  # high → low so ties keep the higher threshold
        err = abs(len(firings(score, thr, exit_idx, calib)) - target)
        if best_err is None or err < best_err:
            best, best_err = float(thr), err
    return best


def human_auc(ts, pmin) -> float | None:
    if not HUMAN_LABELS.exists():
        return None
    import pandas as pd
    lab = pd.read_csv(HUMAN_LABELS, parse_dates=["timestamp"])
    dips = set(lab.loc[lab["kind"] == "dip", "timestamp"])
    idx = [i for i, t in enumerate(ts) if t in dips]
    y = np.zeros(len(ts), dtype=bool)
    for i in idx:
        y[max(0, i - 1): i + 2] = True  # ±1 bar tolerance
    m = np.array([t >= datetime(2025, 5, 1) for t in ts])
    return auc(pmin[m], y[m]) if y[m].any() else None


def evaluate(run: dict, base_run: dict | None) -> dict:
    per = {}
    for sym, p in run["params"].items():
        ser = stock_series(run, sym)
        if ser is None:
            continue
        ts, closes, pmin, pmax = ser
        good, ret, exit_idx = simulate_exits(closes, p)
        known = ~np.isnan(ret)
        calib = np.array([t < CALIB_END for t in ts]) & known
        test = np.array([t >= CALIB_END for t in ts]) & known
        if test.sum() < 50:
            continue
        thr = float(p.get("threshold", 0.7))
        if base_run is not None and stock_series(base_run, sym) is not None:
            bts, bcl, bpmin, _ = stock_series(base_run, sym)
            bgood, bret, bexit = simulate_exits(bcl, base_run["params"][sym])
            bcal = np.array([t < CALIB_END for t in bts]) & ~np.isnan(bret)
            target = len(firings(bpmin, float(base_run["params"][sym].get("threshold", 0.7)), bexit, bcal))
        else:
            target = len(firings(pmin, thr, exit_idx, calib))
        mthr = _match_threshold(pmin, exit_idx, calib, target, thr)

        def at(threshold):
            f = firings(pmin, threshold, exit_idx, test)
            prec = float(good[f].mean()) if f else float("nan")
            return {"thr": threshold, "n": len(f), "precision": prec,
                    "ev_pct": float(np.nanmean(ret[f])) if f else float("nan"),
                    "recall": event_recall(good, f, test)}

        base_rate = float(good[test].mean())
        r_raw, r_m = at(thr), at(mthr)
        per[sym] = {
            "tf": p.get("timeframe", "15minute"), "bars_test": int(test.sum()),
            "base_rate": base_rate, "auc": auc(pmin[test], good[test]),
            "auc_pmax_bad": auc(pmax[test], ~good[test]),
            "raw": r_raw, "matched": r_m,
            "lift_matched": (r_m["precision"] / base_rate) if base_rate and r_m["n"] else float("nan"),
            "calib_target_firings": target,
        }
        if sym == "NSE:ATHERENERG":
            per[sym]["human_auc"] = human_auc(ts, pmin)
    return per


def gate(per: dict, base_per: dict) -> dict:
    common = [s for s in per if s in base_per]
    d_auc = np.array([per[s]["auc"] - base_per[s]["auc"] for s in common], dtype=float)
    d_ev = np.array([per[s]["matched"]["ev_pct"] - base_per[s]["matched"]["ev_pct"] for s in common], dtype=float)
    d_auc_ok, d_ev_ok = d_auc[~np.isnan(d_auc)], d_ev[~np.isnan(d_ev)]
    a = bool(len(d_auc_ok) and np.median(d_auc_ok) >= 0.03 and (d_auc_ok < 0).mean() <= 1 / 3)
    e = bool(len(d_ev_ok) and np.median(d_ev_ok) >= 0.25 and (d_ev_ok < 0).mean() <= 1 / 3)
    return {"n_stocks": len(common),
            "median_d_auc": float(np.median(d_auc_ok)) if len(d_auc_ok) else None,
            "frac_auc_worse": float((d_auc_ok < 0).mean()) if len(d_auc_ok) else None,
            "median_d_ev_matched": float(np.median(d_ev_ok)) if len(d_ev_ok) else None,
            "frac_ev_worse": float((d_ev_ok < 0).mean()) if len(d_ev_ok) else None,
            "auc_rule": a, "ev_rule": e, "pass": a or e}


def print_table(per: dict, base_per: dict | None) -> None:
    hdr = f"{'stock':<16}{'tf':<8}{'base%':>6}{'AUC':>7}{'ΔAUC':>7}{'thr*':>7}{'n':>4}{'prec':>6}{'EV%':>7}{'ΔEV':>7}{'rec':>6}"
    print(hdr)
    for s, r in sorted(per.items()):
        b = (base_per or {}).get(s)
        da = r["auc"] - b["auc"] if b else float("nan")
        de = r["matched"]["ev_pct"] - b["matched"]["ev_pct"] if b else float("nan")
        m = r["matched"]
        print(f"{s[4:]:<16}{r['tf'][:7]:<8}{r['base_rate'] * 100:6.1f}{r['auc']:7.3f}{da:+7.3f}{m['thr']:7.3f}"
              f"{m['n']:4d}{m['precision']:6.2f}{m['ev_pct']:7.2f}{de:+7.2f}{m['recall']:6.2f}")
    aucs = [r["auc"] for r in per.values() if not np.isnan(r["auc"])]
    print(f"median AUC {np.median(aucs):.3f}  ({len(aucs)} stocks)")


def emit_overlay(per: dict, path: str) -> None:
    import yaml
    ov = {"per_stock_params": {s: {"lr_extrema": {"threshold": float(r["matched"]["thr"])}} for s, r in per.items()}}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("# generated by scripts/campaign/stage_a.py — matched-budget thresholds\n"
                          + yaml.safe_dump(ov, sort_keys=True))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--overlay", default=None)
    ap.add_argument("--baseline", default=None, help="label of the baseline score run")
    ap.add_argument("--score-only", action="store_true")
    ap.add_argument("--emit-overlay", default=None)
    ap.add_argument("--out", default=None, help="JSON path (default reviews/extrema_campaign/runs/stage_a_<label>.json)")
    args = ap.parse_args()

    run = score_run(args.label, args.overlay)
    if args.score_only:
        print(f"scores cached for {args.label}: {len(run['scores'])} stocks")
        return
    base_run = score_run(args.baseline, None) if args.baseline else None
    per = evaluate(run, base_run)
    base_per = evaluate(base_run, None) if base_run else None
    print_table(per, base_per)
    payload = {"label": args.label, "overlay": args.overlay, "baseline": args.baseline,
               "run_at": datetime.now().isoformat(timespec="seconds"), "per_stock": per}
    if base_per:
        payload["gate"] = gate(per, base_per)
        print("gate:", payload["gate"])
    out = args.out or str(ROOT / "reviews" / "extrema_campaign" / "runs" / f"stage_a_{args.label}.json")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(payload, indent=1, default=float))
    print(f"wrote {out}")
    if args.emit_overlay:
        emit_overlay(per, args.emit_overlay)
        print(f"wrote {args.emit_overlay}")


if __name__ == "__main__":
    main()
