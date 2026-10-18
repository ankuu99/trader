"""Headroom probe (ledger EXP-00b): AUC of univariate swing measures vs the Stage-A
tradeable-trough truth on the baseline score cache. Run from the repo root:
    .venv/bin/python scripts/campaign/headroom_probe.py
"""
import sys, pickle, numpy as np
sys.path.insert(0, ".")
from scripts.campaign.stage_a import simulate_exits, auc, stock_series, CALIB_END
run = pickle.load(open("lab_data/campaign/scores/baseline.pkl","rb"))
def rsi(c, p=14):
    d = np.diff(c, prepend=c[0]); up = np.where(d>0,d,0); dn = np.where(d<0,-d,0)
    k = np.ones(p)/p; au = np.convolve(up,k,"full")[:len(c)]; ad = np.convolve(dn,k,"full")[:len(c)]
    return 100 - 100/(1+au/np.maximum(ad,1e-12))
def roll(f, c, n):
    out = np.full(len(c), np.nan)
    for i in range(n, len(c)): out[i] = f(c[i-n+1:i+1])
    return out


def main():
    rows = {}
    for sym, p in run["params"].items():
        ser = stock_series(run, sym)
        if ser is None: continue
        ts, c, pmin, pmax = ser
        good, ret, ex = simulate_exits(c, p)
        test = np.array([t >= CALIB_END for t in ts]) & ~np.isnan(ret)
        feats = {
          "p_min": pmin,
          "-depth50": -(c/roll(np.max,c,50)-1),
          "-above_low20": -(c/roll(np.min,c,20)-1),
          "-ret20": -(c/np.concatenate([np.full(20,np.nan),c[:-20]])-1),
          "-rsi14": -rsi(c),
          "-ret5": -(c/np.concatenate([np.full(5,np.nan),c[:-5]])-1),
        }
        rows[sym] = {k: auc(v[test], good[test]) for k, v in feats.items()}
    keys = list(next(iter(rows.values())))
    print(f"{'stock':<14}" + "".join(f"{k:>13}" for k in keys))
    for s, r in sorted(rows.items()):
        print(f"{s[4:]:<14}" + "".join(f"{r[k]:13.3f}" for k in keys))
    print(f"{'MEDIAN':<14}" + "".join(f"{np.nanmedian([r[k] for r in rows.values()]):13.3f}" for k in keys))


if __name__ == "__main__":
    main()
