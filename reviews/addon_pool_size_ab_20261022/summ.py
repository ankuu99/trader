import json, sys
R = json.load(open(sys.argv[1]))
order = ["2020-01→2026-10","2020","2021","2022","2023","2024","2025","2026 YTD"]
by = {(r["window"], r["budget"]): r for r in R if "error" not in r}
for e in [r for r in R if "error" in r]: print("ERROR", e)
name = {10:"₹60k (now)",20:"₹1.2L",40:"₹2.4L",1000:"unlimited"}
for w in order:
    b0 = by.get((w,10))
    if not b0: continue
    print(f"\n{w}")
    print(f"  {'pool':<12}{'P&L':>10}{'Δ vs now':>10}{'addon P&L':>11}{'DD ₹':>9}{'DD%':>6}{'Calmar':>8}{'MWWR%':>7}{'peak add-on cash':>18}{'Δ₹ per ₹ extra cash':>21}")
    for b in (10,20,40,1000):
        r = by.get((w,b))
        if not r: continue
        d = r["pnl"]-b0["pnl"]; extra = r["peak_addon"]-b0["peak_addon"]
        eff = f"{d/extra:+.3f}" if b != 10 and extra > 0 else ""
        print(f"  {name[b]:<12}{r['pnl']/1e3:>9.1f}k{d/1e3:>+9.1f}k{r['addon_pnl']/1e3:>10.1f}k{r['dd']/1e3:>8.1f}k{r['dd_pct']:>6.1f}{r['calmar']:>8.2f}{r['mwwr']:>7.1f}{r['peak_addon']/1e3:>17.0f}k{eff:>21}")
