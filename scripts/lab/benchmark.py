"""
Reproducible benchmark runner for the extrema lab.

Runs named ARMS (labeler/features/model/threshold-rule combinations) across the
synthetic scenarios and scores dip/peak detections against the generator's
noise-free truth. Every stage of the improvement plan is one more arm here.

    python scripts/lab/benchmark.py                          # all arms, all scenarios
    python scripts/lab/benchmark.py --arms base zigzag_lab   # subset
    python scripts/lab/benchmark.py --scenarios s2_sine_trend s7_trend_noise
    python scripts/lab/benchmark.py --labels-only            # stage-1 label quality

Outputs the metric table to stdout and CSV under lab_data/benchmark_runs/
(git-ignored). Walk-forward score series are cached per (scenario, arm-params)
hash so re-running with new arms only computes what changed.

Success criteria (fixed up front — see plan):
  trend scenarios (s2/s5/s7): dip P@10 >= 2x chance AND R@10 >= 0.30
                              AND median-%-above-trough <= 0.5
  oscillation (s1/s3/s6):     dip P@10 >= 0.50 (no regression)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.lab.generator import (LAB_DATA_DIR, SCENARIOS, load_scenario,
                                   save_scenario, scenario_exists)
from scripts.lab.harness import run_ml_harness
from scripts.lab.metrics import label_quality, match_events

RUNS_DIR = LAB_DATA_DIR / "benchmark_runs"
SCORES_DIR = RUNS_DIR / "scores"

LIVE_PARAMS = {
    "warmup_bars": 300, "lookback_bars": 1200, "retrain_every": 25,
    "extrema_order": 10, "model": {"type": "logistic"},
}
WARMUP = 300
TOLS = (5, 10)

# Hard set: trend/noise/regime — criteria are relative to chance.
# Easy set: clean oscillation — absolute precision floor (no regression).
TREND_SCENARIOS = {"s2_sine_trend", "s4_noise_ladder", "s5_regime_switch",
                   "s7_trend_noise"}
OSC_SCENARIOS = {"s1_clean_sine", "s3_multi_freq", "s6_falling_knife"}


# ---------------------------------------------------------------------------
# Arms — each is {"params": <nested overrides on LIVE_PARAMS>,
#                 "thr": <threshold rule>}
# Threshold rules:
#   {"type": "fixed", "min": 0.90, "max": 0.85}
#   {"type": "quantile", "window": 1000, "q": 0.98, "floor": 0.5}
# (stage 2 adds {"type": "regime", ...})
# ---------------------------------------------------------------------------

ARMS: dict[str, dict] = {
    # Production baseline — must reproduce the 2026-07-11 matrix rows.
    "base": {
        "params": {},
        "thr": {"type": "fixed", "min": 0.90, "max": 0.85},
    },
    # Known-partial control from the adaptive-variants run: new arms must beat it.
    "quantile_ctrl": {
        "params": {},
        "thr": {"type": "quantile", "window": 1000, "q": 0.995, "floor": 0.5},
    },
    # --- Stage 1: labelers ---
    "ties_fix": {
        "params": {"labels": {"collapse_ties": True}},
        "thr": {"type": "fixed", "min": 0.90, "max": 0.85},
    },
    "zigzag_r1.5": {
        "params": {"labels": {"type": "zigzag", "zigzag": {"reversal_pct": 1.5}}},
        "thr": {"type": "fixed", "min": 0.90, "max": 0.85},
    },
    "zigzag_r2.5": {
        "params": {"labels": {"type": "zigzag", "zigzag": {"reversal_pct": 2.5}}},
        "thr": {"type": "fixed", "min": 0.90, "max": 0.85},
    },
    "zigzag_r4": {
        "params": {"labels": {"type": "zigzag", "zigzag": {"reversal_pct": 4.0}}},
        "thr": {"type": "fixed", "min": 0.90, "max": 0.85},
    },
    "trend_scan": {
        "params": {"labels": {"type": "trend_scan"}},
        "thr": {"type": "fixed", "min": 0.90, "max": 0.85},
    },
    # --- Stage 1b: clean labels starve a 1200-bar window (~10 samples) — pair
    # zigzag with a long lookback so the model actually has data to learn from.
    "zz15_lb6k": {
        "params": {"labels": {"type": "zigzag", "zigzag": {"reversal_pct": 1.5}},
                   "lookback_bars": 6000, "warmup_bars": 1000},
        "thr": {"type": "fixed", "min": 0.90, "max": 0.85},
    },
    "zz15_lb6k_t80": {
        "params": {"labels": {"type": "zigzag", "zigzag": {"reversal_pct": 1.5}},
                   "lookback_bars": 6000, "warmup_bars": 1000},
        "thr": {"type": "fixed", "min": 0.80, "max": 0.75},
    },
    "zz15_lb12k": {
        "params": {"labels": {"type": "zigzag", "zigzag": {"reversal_pct": 1.5}},
                   "lookback_bars": 12000, "warmup_bars": 1500},
        "thr": {"type": "fixed", "min": 0.90, "max": 0.85},
    },
    # --- Stage 2: regime context ---
    # 2a: regime features on the production labeler/window
    "base_regime": {
        "params": {"features": {"type": "extrema_regime"}},
        "thr": {"type": "fixed", "min": 0.90, "max": 0.85},
    },
    # 2a: regime features on clean labels + long window
    "zz15_lb6k_regime": {
        "params": {"labels": {"type": "zigzag", "zigzag": {"reversal_pct": 1.5}},
                   "lookback_bars": 6000, "warmup_bars": 1000,
                   "features": {"type": "extrema_regime"}},
        "thr": {"type": "fixed", "min": 0.90, "max": 0.85},
    },
    # 2b: regime-conditioned threshold on the production pipeline
    "base_regime_thr": {
        "params": {},
        "thr": {"type": "regime", "min": 0.90, "max": 0.85,
                "offsets": {"UP": -0.15, "DOWN": 0.10}},
    },
    # 2a+2b combo
    "zz15_lb6k_regime_thr": {
        "params": {"labels": {"type": "zigzag", "zigzag": {"reversal_pct": 1.5}},
                   "lookback_bars": 6000, "warmup_bars": 1000,
                   "features": {"type": "extrema_regime"}},
        "thr": {"type": "regime", "min": 0.90, "max": 0.85,
                "offsets": {"UP": -0.15, "DOWN": 0.10}},
    },
    # --- Stage 3: neutral class on the stage-2 winner (mid-descent bars get a
    # class of their own instead of leaking into P(min)) ---
    "winner_neutral": {
        "params": {"labels": {"type": "zigzag", "zigzag": {"reversal_pct": 1.5},
                              "neutral": {"enabled": True, "ratio": 1.0}},
                   "lookback_bars": 6000, "warmup_bars": 1000,
                   "features": {"type": "extrema_regime"}},
        "thr": {"type": "fixed", "min": 0.90, "max": 0.85},
    },
    "winner_neutral_t70": {
        "params": {"labels": {"type": "zigzag", "zigzag": {"reversal_pct": 1.5},
                              "neutral": {"enabled": True, "ratio": 1.0}},
                   "lookback_bars": 6000, "warmup_bars": 1000,
                   "features": {"type": "extrema_regime"}},
        "thr": {"type": "fixed", "min": 0.70, "max": 0.65},
    },
    "winner_neutral2": {
        "params": {"labels": {"type": "zigzag", "zigzag": {"reversal_pct": 1.5},
                              "neutral": {"enabled": True, "ratio": 2.0}},
                   "lookback_bars": 6000, "warmup_bars": 1000,
                   "features": {"type": "extrema_regime"}},
        "thr": {"type": "fixed", "min": 0.70, "max": 0.65},
    },
    # Threshold operating points for the stage-3 winner
    "winner_neutral2_t65": {
        "params": {"labels": {"type": "zigzag", "zigzag": {"reversal_pct": 1.5},
                              "neutral": {"enabled": True, "ratio": 2.0}},
                   "lookback_bars": 6000, "warmup_bars": 1000,
                   "features": {"type": "extrema_regime"}},
        "thr": {"type": "fixed", "min": 0.65, "max": 0.60},
    },
    "winner_neutral2_t45": {
        "params": {"labels": {"type": "zigzag", "zigzag": {"reversal_pct": 1.5},
                              "neutral": {"enabled": True, "ratio": 2.0}},
                   "lookback_bars": 6000, "warmup_bars": 1000,
                   "features": {"type": "extrema_regime"}},
        "thr": {"type": "fixed", "min": 0.45, "max": 0.45},
    },
    "winner_neutral2_q": {
        "params": {"labels": {"type": "zigzag", "zigzag": {"reversal_pct": 1.5},
                              "neutral": {"enabled": True, "ratio": 2.0}},
                   "lookback_bars": 6000, "warmup_bars": 1000,
                   "features": {"type": "extrema_regime"}},
        "thr": {"type": "quantile", "window": 1000, "q": 0.99, "floor": 0.45},
    },
    # --- Stage 4: model class, one shot on the winning labels+features ---
    "winner_gbdt": {
        "params": {"labels": {"type": "zigzag", "zigzag": {"reversal_pct": 1.5},
                              "neutral": {"enabled": True, "ratio": 2.0}},
                   "lookback_bars": 6000, "warmup_bars": 1000,
                   "features": {"type": "extrema_regime"},
                   "model": {"type": "gbdt"}},
        "thr": {"type": "fixed", "min": 0.65, "max": 0.60},
    },
}


def deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def arm_params(arm: dict) -> dict:
    return deep_merge(LIVE_PARAMS, arm.get("params") or {})


# ---------------------------------------------------------------------------
# Truth / metric helpers
# ---------------------------------------------------------------------------

def truth_pos(meta: dict, index: pd.Series) -> dict[str, list[int]]:
    lookup = {ts: i for i, ts in enumerate(pd.to_datetime(index))}
    return {k: [lookup[pd.Timestamp(t)] for t in meta["true_extrema"][src]
                if pd.Timestamp(t) in lookup]
            for k, src in (("dip", "minima"), ("peak", "maxima"))}


def rising_edges(fire: np.ndarray) -> list[int]:
    prev = np.roll(fire, 1)
    prev[0] = False
    return [int(i) for i in np.nonzero(fire & ~prev)[0]]


def threshold_series(rule: dict, p: np.ndarray, candles: pd.DataFrame,
                     side: str) -> np.ndarray:
    """Per-bar threshold array for one side ('min' entry / 'max' exit)."""
    rtype = rule.get("type", "fixed")
    if rtype == "fixed":
        return np.full(len(p), float(rule[side]))
    if rtype == "quantile":
        s = pd.Series(p)
        w = int(rule["window"])
        rq = s.rolling(w, min_periods=w // 2).quantile(float(rule["q"])).shift(1)
        return np.maximum(rq.to_numpy(), float(rule.get("floor", 0.5)))
    if rtype == "regime":
        # base fixed threshold plus a per-bar offset from the discrete regime state
        from trader.features.regime import regime_states
        base = float(rule[side])
        offsets = rule.get("offsets", {})  # e.g. {"UP": -0.10, "DOWN": 0.05}
        states = regime_states(candles["close"].to_numpy(),
                               horizons=rule.get("horizons"))
        thr = np.full(len(p), base)
        for state, off in offsets.items():
            thr[states == state] += float(off)
        return thr
    raise ValueError(f"unknown threshold rule {rtype!r}")


# Trade-realistic dedupe: a live position blocks re-entry, so only the FIRST
# threshold crossing in a cluster matters. 25 bars = one trading day.
DEDUPE_GAP = 25


def dedupe_crossings(preds: list[int], gap: int = DEDUPE_GAP) -> list[int]:
    out: list[int] = []
    for p in preds:
        if not out or p - out[-1] > gap:
            out.append(p)
    return out


def crossings(rule: dict, p: np.ndarray, candles: pd.DataFrame, side: str) -> list[int]:
    thr = threshold_series(rule, p, candles, side)
    with np.errstate(invalid="ignore"):
        raw = [i for i in rising_edges(p >= thr) if i >= WARMUP]
    return dedupe_crossings(raw)


def chance_precision(truth_idx: list[int], n_bars: int, tol: int) -> float:
    band = np.zeros(n_bars, dtype=bool)
    for t in truth_idx:
        band[max(0, t - tol):min(n_bars, t + tol + 1)] = True
    band = band[WARMUP:]
    return float(band.mean()) if len(band) else float("nan")


def price_above_trough(pred_idx: list[int], truth_idx: list[int],
                       close: np.ndarray) -> float:
    if not pred_idx or not truth_idx:
        return float("nan")
    t = np.asarray(sorted(truth_idx))
    return float(np.median([(close[p] / close[t[np.argmin(np.abs(t - p))]] - 1) * 100
                            for p in pred_idx]))


# ---------------------------------------------------------------------------
# Score computation with caching
# ---------------------------------------------------------------------------

def _cache_key(scenario: str, params: dict) -> Path:
    h = hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()[:12]
    return SCORES_DIR / f"{scenario}__{h}.csv"


def compute_scores(scenario: str, params: dict) -> pd.DataFrame:
    path = _cache_key(scenario, params)
    if path.exists():
        return pd.read_csv(path)
    df, _ = load_scenario(scenario)
    res = run_ml_harness(df.to_dict("records"), params)
    SCORES_DIR.mkdir(parents=True, exist_ok=True)
    res.scores.to_csv(path, index=False)
    return res.scores


def _worker(scenario: str, arm_name: str, params: dict) -> tuple[str, str, float]:
    t0 = time.time()
    compute_scores(scenario, params)  # populates the cache
    return scenario, arm_name, time.time() - t0


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate_arm(scenario: str, arm_name: str, arm: dict) -> list[dict]:
    df, meta = load_scenario(scenario)
    close = df["close"].to_numpy()
    tpos = truth_pos(meta, df["timestamp"])
    scores = compute_scores(scenario, arm_params(arm))
    rule = arm["thr"]

    rows = []
    for kind, col, side in (("dip", "p_min", "min"), ("peak", "p_max", "max")):
        p = scores[col].to_numpy(dtype=float)
        preds = crossings(rule, p, df, side)
        row = {"scenario": scenario, "arm": arm_name, "kind": kind,
               "n_truth": len(tpos[kind]), "n_fired": len(preds)}
        for tol in TOLS:
            r = match_events(preds, tpos[kind], tol_bars=tol)
            row[f"P@{tol}"] = round(r.precision, 3)
            row[f"R@{tol}"] = round(r.recall, 3)
            row[f"lag@{tol}"] = r.median_lag
            row[f"Pchance@{tol}"] = round(chance_precision(tpos[kind], len(close), tol), 3)
        if kind == "dip":
            row["med_%_above_trough"] = round(
                price_above_trough(preds, tpos[kind], close), 3)
            row["PASS"] = passes(scenario, row)
        rows.append(row)
    return rows


def passes(scenario: str, dip_row: dict) -> str:
    p, r = dip_row.get("P@10"), dip_row.get("R@10")
    ch, med = dip_row.get("Pchance@10"), dip_row.get("med_%_above_trough")
    if any(x is None or (isinstance(x, float) and np.isnan(x)) for x in (p, r, ch)):
        return "FAIL"
    if scenario in TREND_SCENARIOS:
        ok = p >= 2 * ch and r >= 0.30 and (med is not None and med <= 0.5)
    elif scenario in OSC_SCENARIOS:
        ok = p >= 0.50
    else:
        return "-"
    return "PASS" if ok else "FAIL"


def evaluate_labels(scenario: str, arm_name: str, arm: dict, tol: int = 10) -> list[dict]:
    """Stage-1 mode: labeler-vs-truth only (bounds any model)."""
    df, meta = load_scenario(scenario)
    candles = df.to_dict("records")
    truth = pd.DataFrame(
        [{"timestamp": pd.Timestamp(t), "kind": k}
         for k, src in (("dip", "minima"), ("peak", "maxima"))
         for t in meta["true_extrema"][src]])
    lq = label_quality(candles, arm_params(arm), truth, mask=None, tol_bars=tol)
    rows = []
    for kind in ("dips", "peaks"):
        r = lq[kind]
        rows.append({"scenario": scenario, "arm": arm_name, "kind": kind,
                     "n_labeled": r.tp + r.fp,
                     f"P@{tol}": round(r.precision, 3),
                     f"R@{tol}": round(r.recall, 3),
                     f"F1@{tol}": round(r.f1, 3),
                     f"lag@{tol}": r.median_lag})
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arms", nargs="+", default=None, help="arm names (default: all)")
    ap.add_argument("--scenarios", nargs="+", default=None)
    ap.add_argument("--labels-only", action="store_true",
                    help="evaluate labeler-vs-truth instead of model detections")
    ap.add_argument("--tol", type=int, default=10, help="tolerance for --labels-only")
    ap.add_argument("--out", default=None, help="output CSV name")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    arm_names = args.arms or list(ARMS)
    unknown = [a for a in arm_names if a not in ARMS]
    if unknown:
        sys.exit(f"unknown arms {unknown}; available: {sorted(ARMS)}")
    scenarios = args.scenarios or list(SCENARIOS)

    for s in scenarios:
        if not scenario_exists(s):
            save_scenario(SCENARIOS[s])
            print(f"generated {s}", flush=True)

    rows: list[dict] = []
    if args.labels_only:
        for s in scenarios:
            for a in arm_names:
                rows.extend(evaluate_labels(s, a, ARMS[a], tol=args.tol))
    else:
        # warm the score cache in parallel, then evaluate serially (cheap)
        jobs = [(s, a) for s in scenarios for a in arm_names
                if not _cache_key(s, arm_params(ARMS[a])).exists()]
        if jobs and args.workers <= 1:
            # serial, in-process — robust when the spawn-based pool is unreliable
            for s, a in jobs:
                _, _, dt = _worker(s, a, arm_params(ARMS[a]))
                print(f"scored {s}/{a} in {dt:.0f}s", flush=True)
        elif jobs:
            with ProcessPoolExecutor(max_workers=args.workers) as ex:
                futs = [ex.submit(_worker, s, a, arm_params(ARMS[a])) for s, a in jobs]
                for fut in as_completed(futs):
                    s, a, dt = fut.result()
                    print(f"scored {s}/{a} in {dt:.0f}s", flush=True)
        for s in scenarios:
            for a in arm_names:
                rows.extend(evaluate_arm(s, a, ARMS[a]))

    out = pd.DataFrame(rows).sort_values(["kind", "scenario", "arm"])
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    name = args.out or f"{'labels' if args.labels_only else 'bench'}_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    out.to_csv(RUNS_DIR / name, index=False)

    with pd.option_context("display.width", 260, "display.max_columns", 30):
        for kind in out["kind"].unique():
            print(f"\n=== {kind.upper()} ===")
            sub = out[out["kind"] == kind].drop(columns="kind")
            if kind == "peak" and "med_%_above_trough" in sub:
                sub = sub.drop(columns=["med_%_above_trough", "PASS"], errors="ignore")
            print(sub.to_string(index=False))
    print(f"\nsaved -> {RUNS_DIR / name}")


if __name__ == "__main__":
    main()
