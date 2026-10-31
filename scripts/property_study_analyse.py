"""Analyse property_study.py outputs: Spearman of 2024 properties vs 2025-26 backtest P&L,
per group (A = traded/watchlist names, B = random scan survivors). Args: the JSON files
(file name containing "groupA" marks group A)."""
import json, sys
import numpy as np
from scipy import stats

files = sys.argv[1:] or ["/tmp/claude-mo/groupA.json", "/tmp/claude-mo/groupB.json"]
rows = []
for f in files:
    try:
        d = json.load(open(f))
    except FileNotFoundError:
        continue
    grp = "A" if "groupA" in f else "B"
    for s, r in d.items():
        bt, p = r.get("bt", {}), r.get("props")
        if len(bt) < 3 or not p or p["turnover_cr"] < 0.5:   # discovery liquidity floor ₹50L/day
            continue
        pn = {k: v["pnl"] for k, v in bt.items()}
        rows.append({"sym": s[4:], "grp": grp, **p,
                     "pnl15": pn["15minute"], "pnl4h": pn["4hour"], "pnlD": pn["day"],
                     "pnl_agg": max(pn["4hour"], pn["day"]), "pnl_best": max(pn.values()),
                     "pnl_mean": np.mean(list(pn.values())),
                     "best_tf": max(pn, key=pn.get)})
print(f"n = {len(rows)} names with 2024 properties + 3 regimes "
      f"(A {sum(r['grp']=='A' for r in rows)}, B {sum(r['grp']=='B' for r in rows)})\n")
PROPS = ["vol_d", "range_pct", "er250", "er20_med", "ac1", "vr5", "swing5_med", "swings5_per_m",
         "dip_recovery", "ret_2024", "maxdd_2024", "beta", "corr_nifty", "turnover_cr", "gap2_freq", "price"]
OUTS = ["pnl_mean", "pnl_best", "pnl_agg", "pnl15"]
print(f"{'property':<14}" + "".join(f"{o:>16}" for o in OUTS) + "   top-third vs bottom-third median (pnl_mean)")
order = sorted(rows, key=lambda r: r["pnl_mean"])
k = len(rows) // 3
bot, top = order[:k], order[-k:]
for pr in PROPS:
    line = f"{pr:<14}"
    for o in OUTS:
        x = [(r[pr], r[o]) for r in rows if r.get(pr) is not None]
        rho, pv = stats.spearmanr([a for a, _ in x], [b for _, b in x])
        star = "**" if pv < 0.01 else "* " if pv < 0.05 else "  "
        line += f"  {rho:+.2f} p{pv:.2f}{star}"
    for g in "AB":
        x = [(r[pr], r["pnl_mean"]) for r in rows if r["grp"] == g and r.get(pr) is not None]
        if len(x) > 8:
            rho, pv = stats.spearmanr([a for a, _ in x], [b for _, b in x])
            line += f"  {g}:{rho:+.2f}"
    tm = np.median([r[pr] for r in top if r.get(pr) is not None])
    bm = np.median([r[pr] for r in bot if r.get(pr) is not None])
    print(line + f"   {tm:9.2f} vs {bm:9.2f}")
print("\nnames by pnl_mean:")
for r in sorted(rows, key=lambda r: -r["pnl_mean"]):
    print(f"{r['sym']:<12} {r['grp']} 15m {r['pnl15']:>7,} 4h {r['pnl4h']:>7,} D {r['pnlD']:>7,}  best {r['best_tf']:<8} "
          f"vol {r['vol_d']:.1f} sw {r['swing5_med']:.0f}% swm {r['swings5_per_m']:.1f} dip {r['dip_recovery'] if r['dip_recovery'] is None else round(r['dip_recovery'],2)} "
          f"ret24 {r['ret_2024']:+.0f} dd {r['maxdd_2024']:.0f} beta {r['beta']:.2f} turn {r['turnover_cr']:.0f}")
json.dump(rows, open("/tmp/claude-mo/rows.json", "w"))
