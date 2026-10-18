"""Stage-A exit sensitivity (owner question 2026-10-18: "did we try changing the targets/stops?").
Re-scores every cached arm against the tradeable-trough truth rebuilt under ALTERNATIVE exit parameters:
profit_pct × {0.5, 1, 1.5} and stale check_bars × {1, 2} (stale_2 / hold unchanged). Reports, per truth variant,
the median AUC of the baseline and the median ΔAUC (with % of stocks worse) of each arm vs the baseline under the
SAME truth. Test window 2025-01-01 → 2026-10-16. Read-only on the score caches.

    .venv/bin/python scripts/campaign/exit_sensitivity.py
"""
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.campaign.stage_a import CALIB_END, auc, simulate_exits, stock_series  # noqa: E402

ARMS = ["baseline", "exp01", "exp02", "exp03", "exp04", "exp05", "exp06", "exp07", "exp08",
        "exp09a", "exp09b", "exp10a", "exp10b"]
VARIANTS = [(pm, sm) for pm in (0.5, 1.0, 1.5) for sm in (1, 2)]


def _variant_params(p, pm, sm):
    q = dict(p)
    q["profit_pct"] = float(p.get("profit_pct", 7.0)) * pm
    q["stale_check_bars"] = int(p.get("stale_check_bars", 40)) * sm
    return q


def score_arm(label):
    run = pickle.loads((ROOT / f"lab_data/campaign/scores/{label}.pkl").read_bytes())
    out = {}
    for sym, p in run["params"].items():
        ser = stock_series(run, sym)
        if ser is None:
            continue
        ts, c, pmin, _ = ser
        test = np.array([t >= CALIB_END for t in ts])
        for v in VARIANTS:
            good, ret, _ = simulate_exits(c, _variant_params(p, *v))
            m = test & ~np.isnan(ret)
            if m.sum() >= 50:
                out[(sym, v)] = (auc(pmin[m], good[m]), float(good[m].mean()))
    return label, out


def main():
    with ProcessPoolExecutor(max_workers=7) as ex:
        res = dict(ex.map(score_arm, ARMS))
    base = res["baseline"]
    hdr = f"{'arm':<10}" + "".join(f"{f'T×{pm} S×{sm}':>16}" for pm, sm in VARIANTS)
    print("baseline median AUC (and median base rate of good bars) per truth variant")
    line = f"{'baseline':<10}"
    for v in VARIANTS:
        a = [base[k][0] for k in base if k[1] == v]; b = [base[k][1] for k in base if k[1] == v]
        line += f"{np.nanmedian(a):9.3f} ({np.nanmedian(b) * 100:3.0f}%)"
    print(hdr); print(line)
    print("\nmedian ΔAUC vs baseline under the same truth  [% of stocks worse]")
    print(hdr)
    for arm in ARMS[1:]:
        r = res[arm]; line = f"{arm:<10}"
        for v in VARIANTS:
            d = np.array([r[k][0] - base[k][0] for k in r if k[1] == v and k in base], float)
            d = d[~np.isnan(d)]
            line += f"{np.median(d):+9.3f} [{(d < 0).mean() * 100:3.0f}%]"
        print(line)


if __name__ == "__main__":
    main()
