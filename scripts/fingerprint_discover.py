#!/usr/bin/env python
"""
Fundamental-fingerprint discovery — Steps 2 & 3.

Step 2 — fingerprint: for every labelled name with fundamentals, compute a small,
interpretable PIT factor vector (reuses `trader/fvm/factors.py`; no reimplementation).

Step 3 — the honest core: per factor, test whether the TRUSTED curated winners differ
from the contrast pool (losers ∪ baseline). Robust effect size (median gap in MAD units)
+ Mann-Whitney U. If no factor separates after multiple-testing discipline, print the
NULL result and STOP — do not proceed to similarity scoring on a fingerprint that does
not exist (the meta-labeling lesson: a secondary filter once *worsened* outcomes).

PIT caveat (loud): this first pass uses a single `--asof` snapshot for every name, not
each winner's actual trade-period fundamentals (the screen CSV records no per-trade dates).
That is a cross-sectional "do current winners look different from current losers" test and
carries look-ahead. True trade-period PIT and an out-of-sample check are Step 5 — a positive
here is necessary, not sufficient.

Usage:
    python scripts/fingerprint_discover.py [--labels reviews/fingerprint_labels.json]
        [--asof 2026-06-30] [--db data/fvm.db] [--json] [--out reviews/fingerprint_step3.json]
"""

import argparse
import datetime
import json

import numpy as np
from scipy import stats

from trader.fvm import factors
from trader.fvm.data.store import FVMStore
from trader.fvm.data.universe import is_financial

# the ≤10 interpretable factors (plan Step 2). leverage/coverage/cash are structurally
# different for lenders → blanked for financials so they don't poison those distributions.
FACTORS = [
    "yoy_profit_growth", "growth_acceleration", "earnings_consistency",
    "opm_trend", "roce", "roce_trend",
    "debt_to_equity", "cfo_to_np", "interest_coverage",
    "pledge", "promoter_trend_pp_per_qtr",
]
_FINANCIAL_BLANK = {"debt_to_equity", "cfo_to_np", "interest_coverage"}


def _promoter_trend(store, sym, asof):
    """Slope (pp/qtr) of the last 4 quarters of promoter holding; None if too few points."""
    from trader.fvm import fields as F
    d = store.read_shareholding_asof(sym, F.SH_PROMOTER, asof)
    if not d:
        return None
    pts = sorted(d.items())[-4:]
    if len(pts) < 2:
        return None
    y = np.array([v for _, v in pts], float)
    x = np.arange(len(y), dtype=float)
    return float(np.polyfit(x, y, 1)[0])


def fingerprint(store, sym, asof, financial):
    f = factors.all_factors(store, sym, asof)
    f["promoter_trend_pp_per_qtr"] = _promoter_trend(store, sym, asof)
    vec = {}
    for k in FACTORS:
        v = f.get(k)
        if financial and k in _FINANCIAL_BLANK:
            v = None
        vec[k] = float(v) if isinstance(v, (int, float)) and np.isfinite(v) else None
    return vec


def _vectors(store, names, asof, sectors):
    out = {}
    for sym in names:
        bare = sym.replace("NSE:", "")
        # only names that actually have financials (Net Profit annual present)
        if not store.read_fundamental_asof(bare, "annual", "consolidated", "Net Profit Annual", asof):
            continue
        fin = is_financial(sectors.get(bare) or "")
        out[bare] = fingerprint(store, bare, asof, fin)
    return out


def _winsorize(a, lo=5, hi=95):
    a = np.asarray(a, float)
    if a.size == 0:
        return a
    return np.clip(a, np.percentile(a, lo), np.percentile(a, hi))


def discriminate(win_vecs, con_vecs):
    """Per factor: robust effect size + Mann-Whitney U between winners and contrast."""
    rows = []
    n_tests = 0
    for fac in FACTORS:
        w = [v[fac] for v in win_vecs.values() if v.get(fac) is not None]
        c = [v[fac] for v in con_vecs.values() if v.get(fac) is not None]
        if len(w) < 5 or len(c) < 10:
            rows.append({"factor": fac, "n_win": len(w), "n_con": len(c),
                         "status": "insufficient"})
            continue
        n_tests += 1
        wv, cv = _winsorize(w), _winsorize(c)
        med_w, med_c = float(np.median(wv)), float(np.median(cv))
        # robust scale: pooled median absolute deviation
        mad = float(np.median(np.abs(np.concatenate([wv, cv]) -
                                     np.median(np.concatenate([wv, cv]))))) or 1e-9
        effect = (med_w - med_c) / mad                       # median gap in MAD units
        try:
            u, p = stats.mannwhitneyu(wv, cv, alternative="two-sided")
        except ValueError:
            p = 1.0
        rows.append({"factor": fac, "n_win": len(w), "n_con": len(c),
                     "median_win": round(med_w, 4), "median_con": round(med_c, 4),
                     "effect_mad": round(effect, 3), "p": round(float(p), 5),
                     "status": "tested"})
    # Bonferroni threshold over the actually-tested factors
    alpha = 0.05 / max(n_tests, 1)
    for r in rows:
        if r.get("status") == "tested":
            r["discriminating"] = bool(r["p"] < alpha and abs(r["effect_mad"]) >= 0.5)
    return rows, alpha, n_tests


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default="reviews/fingerprint_labels.json")
    ap.add_argument("--asof", default=datetime.date.today().isoformat())
    ap.add_argument("--db", default="data/fvm.db")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    store = FVMStore(args.db)
    sectors = store.sectors_map()
    labels = json.load(open(args.labels))

    win = _vectors(store, labels["curated_winners"], args.asof, sectors)
    con = _vectors(store, labels["losers"] + labels["baseline"], args.asof, sectors)

    rows, alpha, n_tests = discriminate(win, con)
    disc = [r for r in rows if r.get("discriminating")]

    result = {
        "asof": args.asof,
        "n_winners_with_fund": len(win),
        "n_contrast_with_fund": len(con),
        "bonferroni_alpha": round(alpha, 5),
        "n_factors_tested": n_tests,
        "factors": rows,
        "discriminating_factors": [r["factor"] for r in disc],
        "null_result": len(disc) == 0,
        "low_power": len(win) < 25,
        "pit_caveat": "single-asof snapshot, not trade-period PIT — look-ahead; OOS validation (Step 5) is required before trusting.",
    }

    if args.out:
        json.dump(result, open(args.out, "w"), indent=2)
    if args.json:
        print(json.dumps(result, indent=2))
        return

    print(f"asof: {args.asof}   winners w/ fund: {len(win)}   contrast w/ fund: {len(con)}")
    if result["low_power"]:
        print("  ** LOW STATISTICAL POWER (winners < 25) — treat any signal as tentative **")
    print(f"  Bonferroni alpha = 0.05/{n_tests} = {alpha:.5f}\n")
    hdr = f"{'factor':28} {'n_w':>4} {'n_c':>4} {'med_win':>10} {'med_con':>10} {'effect':>8} {'p':>9}  disc"
    print(hdr); print("-" * len(hdr))
    for r in rows:
        if r.get("status") != "tested":
            print(f"{r['factor']:28} {r['n_win']:>4} {r['n_con']:>4}   (insufficient sample)")
            continue
        mark = " <==" if r.get("discriminating") else ""
        print(f"{r['factor']:28} {r['n_win']:>4} {r['n_con']:>4} {r['median_win']:>10.4f} "
              f"{r['median_con']:>10.4f} {r['effect_mad']:>8.3f} {r['p']:>9.5f}{mark}")
    print()
    if result["null_result"]:
        print("NULL RESULT: no factor separates winners from the contrast pool after "
              "multiple-testing discipline.")
        print("=> Do NOT build a similarity fingerprint. Keep fund_panel as a per-name gate. STOP.")
    else:
        print(f"DISCRIMINATING factors: {', '.join(result['discriminating_factors'])}")
        print("=> Candidate fingerprint. Still must pass out-of-sample validation (Step 5) "
              "before any wiring into discover.")
    if args.out:
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
