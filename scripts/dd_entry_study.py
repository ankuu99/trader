"""Is the portfolio's own drawdown state at entry predictive of that entry's outcome?"""
import sys, numpy as np, pandas as pd
from scipy.stats import spearmanr, mannwhitneyu
rng = np.random.default_rng(7)

def rounds_from_csv(path):
    df = pd.read_csv(path, parse_dates=["entry_date", "exit_date"])
    df["notional"] = df["entry"] * df["qty"]
    g = df.groupby(["instrument", "entry_date"], as_index=False).agg(
        exit_date=("exit_date", "max"), notional=("notional", "sum"), pnl=("pnl", "sum"))
    return g

def study(rounds, cap, label, fwd_days=(10, 20, 40)):
    rounds = rounds.sort_values("entry_date").reset_index(drop=True)
    rounds["pct"] = rounds["pnl"] / rounds["notional"] * 100
    # equity curve by exit time (net pnl already)
    ex = rounds.sort_values("exit_date")[["exit_date", "pnl"]].reset_index(drop=True)
    ex["cum"] = ex["pnl"].cumsum(); ex["hwm"] = ex["cum"].cummax()
    ex["dd"] = ex["hwm"] - ex["cum"]
    hwm_time = []
    pk_t = ex["exit_date"].iloc[0]; pk = -1e18
    for _, r in ex.iterrows():
        if r["cum"] > pk: pk = r["cum"]; pk_t = r["exit_date"]
        hwm_time.append(pk_t)
    ex["hwm_time"] = hwm_time
    # state at each entry = last exit strictly before entry
    idx = np.searchsorted(ex["exit_date"].values, rounds["entry_date"].values, side="left") - 1
    dd = np.where(idx >= 0, ex["dd"].values[np.clip(idx, 0, None)], 0.0)
    ddpct = dd / cap * 100
    days = np.where(idx >= 0, (rounds["entry_date"].values - ex["hwm_time"].values[np.clip(idx, 0, None)]) / np.timedelta64(1, "D"), 0.0)
    rounds["dd_pct"] = ddpct; rounds["days_uw"] = np.where(ddpct > 0, days, 0)
    edges = [(-1, 1e-9, "at new high"), (1e-9, 1, "0–1%"), (1, 2, "1–2%"), (2, 4, "2–4%"), (4, 8, "4–8%"), (8, 99, ">8%")]
    print(f"\n=== {label}: {len(rounds)} rounds, capital ₹{cap:,.0f}, total net ₹{rounds['pnl'].sum():,.0f}, maxDD {ex['dd'].max()/cap*100:.1f}% ===")
    print(f"{'dd at entry':<14}{'n':>5}{'avg ₹':>9}{'med ₹':>8}{'avg %':>8}{'win%':>7}{'total ₹':>11}{'avg days uw':>12}")
    for lo, hi, name in edges:
        b = rounds[(rounds.dd_pct > lo) & (rounds.dd_pct <= hi)]
        if len(b) == 0: continue
        print(f"{name:<14}{len(b):>5}{b.pnl.mean():>9,.0f}{b.pnl.median():>8,.0f}{b.pct.mean():>8.2f}{(b.pnl>0).mean()*100:>7.1f}{b.pnl.sum():>11,.0f}{b.days_uw.mean():>12.1f}")
    rho, p = spearmanr(rounds.dd_pct, rounds.pct)
    print(f"Spearman(dd_pct at entry, round % return) = {rho:+.3f} (p={p:.3f})")
    hi_ = rounds[rounds.dd_pct > 2]; lo_ = rounds[rounds.dd_pct <= 1e-9]; mid = rounds[(rounds.dd_pct > 1e-9) & (rounds.dd_pct <= 2)]
    for nm, a in (("in drawdown >2%", hi_), ("shallow 0–2%", mid)):
        if len(a) and len(lo_):
            u, pu = mannwhitneyu(a.pct, lo_.pct, alternative="two-sided")
            print(f"  {nm} vs at-high: avg% {a.pct.mean():+.2f} vs {lo_.pct.mean():+.2f}, Mann-Whitney p={pu:.3f}")
    # permutation null on 'in drawdown' minus 'at high' avg pct
    if len(hi_) and len(lo_):
        obs = hi_.pct.mean() - lo_.pct.mean()
        v = rounds.pct.values; m = (rounds.dd_pct > 2).values; k = (rounds.dd_pct <= 1e-9).values
        null = []
        for _ in range(4000):
            s = rng.permutation(v); null.append(s[m].mean() - s[k].mean())
        null = np.array(null)
        print(f"  permutation: obs diff {obs:+.2f}pp, null sd {null.std():.2f}, two-sided p={np.mean(np.abs(null) >= abs(obs)):.3f}")
    # days under water buckets
    print("by days under water at entry:")
    for lo, hi, name in ((-1, 0, "0 (at high)"), (0, 7, "1–7d"), (7, 21, "8–21d"), (21, 60, "22–60d"), (60, 9999, ">60d")):
        b = rounds[(rounds.days_uw > lo) & (rounds.days_uw <= hi)]
        if len(b): print(f"  {name:<12} n={len(b):>4} avg ₹{b.pnl.mean():>7,.0f} avg% {b.pct.mean():+.2f} win% {(b.pnl>0).mean()*100:.1f}")
    # forward portfolio P&L by daily drawdown state (mechanical in-sample recovery bias — see note)
    daily = ex.groupby(ex.exit_date.dt.normalize())["pnl"].sum()
    days_idx = pd.bdate_range(daily.index.min(), daily.index.max())
    daily = daily.reindex(days_idx, fill_value=0.0)
    cum = daily.cumsum(); ddd = (cum.cummax() - cum) / cap * 100
    print("forward portfolio net P&L (₹) from days in each drawdown state:")
    hdr = f"{'state':<14}{'n days':>7}" + "".join(f"{f'+{f}d':>10}" for f in fwd_days)
    print(hdr)
    for lo, hi, name in edges:
        sel = (ddd > lo) & (ddd <= hi)
        if sel.sum() == 0: continue
        row = f"{name:<14}{int(sel.sum()):>7}"
        for f in fwd_days:
            fw = cum.shift(-f) - cum
            row += f"{fw[sel].mean():>10,.0f}"
        print(row)
    row = f"{'ALL':<14}{len(ddd):>7}"
    for f in fwd_days:
        fw = cum.shift(-f) - cum; row += f"{fw.mean():>10,.0f}"
    print(row)
    return rounds

if __name__ == "__main__":
    r = rounds_from_csv(sys.argv[1]); study(r, float(sys.argv[2]), sys.argv[3])
