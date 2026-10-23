"""Tuning-free Stage-A comparison (bias check, 2026-10-18): the baseline's configured thresholds were calibrated on
windows overlapping the 2025+ test window, so EV@matched favours it. Here every arm — baseline included — is scored
at the SAME top-q tail of its own test-window p_min (position-blocked dedupe), plus average precision.

    .venv/bin/python scripts/campaign/tail_compare.py baseline exp01 exp07 ...
"""
import pickle
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.campaign.stage_a import CALIB_END, firings, simulate_exits, stock_series  # noqa: E402

QS = (0.01, 0.03)


def score(label):
    run = pickle.loads((ROOT / f"lab_data/campaign/scores/{label}.pkl").read_bytes())
    from sklearn.metrics import average_precision_score
    out = {}
    for sym, p in run["params"].items():
        ser = stock_series(run, sym)
        if ser is None:
            continue
        ts, c, pmin, _ = ser
        good, ret, ex = simulate_exits(c, p)
        test = np.array([t >= CALIB_END for t in ts]) & ~np.isnan(ret)
        if test.sum() < 50 or not good[test].any():
            continue
        r = {"ap": float(average_precision_score(good[test], pmin[test])), "base": float(good[test].mean())}
        for q in QS:
            thr = np.quantile(pmin[test], 1 - q)
            f = firings(pmin, thr, ex, test)
            r[f"ev{q}"] = float(np.nanmean(ret[f])) if f else np.nan
            r[f"prec{q}"] = float(good[f].mean()) if f else np.nan
        out[sym] = r
    return out


def main():
    labels = sys.argv[1:]
    res = {l: score(l) for l in labels}
    base = res[labels[0]]
    print(f"{'arm':<10}{'AP-base':>9}{'ΔAP':>8}{'w%':>5}" + "".join(f"{'EV@'+str(q):>9}{'ΔEV':>8}{'w%':>5}" for q in QS))
    for l in labels:
        r = res[l]
        common = [s for s in r if s in base]
        d_ap = np.array([r[s]["ap"] - base[s]["ap"] for s in common])
        ap_lift = np.median([r[s]["ap"] - r[s]["base"] for s in common])
        line = f"{l:<10}{ap_lift:9.3f}{np.median(d_ap):+8.3f}{(d_ap < 0).mean() * 100:5.0f}"
        for q in QS:
            ev = np.array([r[s][f"ev{q}"] for s in common]); bev = np.array([base[s][f"ev{q}"] for s in common])
            d = ev - bev; ok = ~np.isnan(d)
            line += f"{np.nanmedian(ev):9.2f}{np.median(d[ok]):+8.2f}{(d[ok] < 0).mean() * 100:5.0f}"
        print(line)


if __name__ == "__main__":
    main()
