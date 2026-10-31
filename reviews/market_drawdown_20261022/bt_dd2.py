import pandas as pd, numpy as np, sys
J=sys.argv[1]
eq=pd.read_csv(f"{J}/bt_eq.csv",index_col=0,parse_dates=True).iloc[:,0]
acct=6e5+eq; pk=acct.cummax(); ddp=100*(acct/pk-1)
idx=pd.read_csv(f"{J}/idx.csv",index_col=0,parse_dates=True)["NIFTY SMLCAP 250"]
EPS=[("2020-01-24","2020-03-24","COVID crash"),("2020-09-16","2020-09-24","Sep-2020 dip"),("2021-08-02","2021-08-23","Aug-2021"),("2021-10-18","2021-11-29","Nov-2021"),
("2022-01-17","2022-02-24","Jan–Feb 2022"),("2022-04-11","2022-06-20","Apr–Jun 2022"),("2022-12-14","2023-03-28","Dec22–Mar23"),("2024-02-07","2024-03-13","Feb–Mar 2024 SME/smallcap"),
("2024-09-23","2024-11-13","Oct–Nov 2024"),("2024-12-11","2025-03-03","Dec24–Mar25"),("2025-07-17","2026-03-23","Jul25–Mar26 grind")]
r7=100*(acct/acct.shift(7)-1)
print("episode | SC250 | worst acct DD inside | worst 7-sess % | days pk->trough | recovered by")
for a,b,n in EPS:
    w=ddp[a:pd.Timestamp(b)+pd.Timedelta(days=21)]; i=w.idxmin()
    p=acct[:i].idxmax()
    rec=acct[i:][acct[i:]>=acct[p]]; rd=rec.index[0].date() if len(rec) else None
    print(f"{n:26s} | {100*(idx[b]/idx[a]-1):6.1f}% | {w.min():6.1f}% ({p.date()}→{i.date()}) | {r7[a:b].min():6.1f}% | {(i-p).days:3d} | {rd} ({(rec.index[0]-i).days if len(rec) else '-'}d after trough)")
print("\nall-time worst acct DD", round(ddp.min(),1), ddp.idxmin().date())
print("DD by year:", {k:round(v,1) for k,v in ddp.groupby(ddp.index.year).min().items()})
print("7-session drops <= -6.3%:", round(100*(r7<=-6.3).mean(),2), "% of all 7-session windows")
s=r7.copy(); out=[]
while len(out)<10:
    i=s.idxmin(); out.append((i.date(),round(s[i],1))); s[i-pd.Timedelta(days=20):i+pd.Timedelta(days=20)]=np.nan
print("worst 7-session drops:", out)
# drawdown episode depth distribution (peak→trough episodes ≥3%)
eps=[];inn=False
for t,v in ddp.items():
    if not inn and v<=-3: inn=True; st=t
    if inn and v==0: eps.append(ddp[st:t].min()); inn=False
print("DD episodes ≥3%:", len(eps), "depths sorted:", sorted(round(x,1) for x in eps))
