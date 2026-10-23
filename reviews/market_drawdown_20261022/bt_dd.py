import pickle, sqlite3, sys, pandas as pd, numpy as np
from collections import defaultdict
J=sys.argv[1]
tr=pickle.load(open(f"{J}/bt_trades.pkl","rb"))
insts=sorted({t["instrument"] for t in tr})
c=sqlite3.connect("data/market.db")
closes={}
for i in insts:
    df=pd.read_sql("select timestamp, close from candles where instrument=? and timestamp>='2019-12-01' order by timestamp",c,params=(i,))
    df["d"]=pd.to_datetime(df.timestamp.str[:10]); closes[i]=df.groupby("d").close.last()
C=pd.DataFrame(closes).sort_index().ffill()
days=C.loc["2020-01-01":].index
ed=lambda x: pd.Timestamp(str(x)[:10])
real=pd.Series(0.0,index=days); un=pd.Series(0.0,index=days); dep=pd.Series(0.0,index=days)
for t in tr:
    e,x=ed(t["entry_date"]),ed(t["exit_date"])
    real[days>=x]+=t["pnl"]
    m=(days>=e)&(days<x)
    if m.any():
        un[m]+=t["qty"]*(C.loc[days[m],t["instrument"]].values-t["entry"]); dep[m]+=t["qty"]*t["entry"]
eq=real+un
dd=eq-eq.cummax()
print("full max MTM DD", round(dd.min()), dd.idxmin().date(), "peak", eq[:dd.idxmin()].idxmax().date())
rdd=real-real.cummax(); print("full max realised DD", round(rdd.min()), rdd.idxmin().date())
idx=pd.read_csv(f"{J}/idx.csv",index_col=0,parse_dates=True)["NIFTY SMLCAP 250"]
EPS=[("2020-01-24","2020-03-24"),("2020-09-16","2020-09-24"),("2021-08-02","2021-08-23"),("2021-10-18","2021-11-29"),
("2022-01-17","2022-02-24"),("2022-04-11","2022-06-20"),("2022-12-14","2023-03-28"),("2024-02-07","2024-03-13"),
("2024-09-23","2024-11-13"),("2024-12-11","2025-03-03"),("2025-07-17","2026-03-23")]
print("\nepisode | SC250 | eq chg over episode | worst MTM DD inside (pk->tr) | % of 6L | worst 7-session drop inside")
r7=eq.diff(7)
for a,b in EPS:
    w=eq[a:pd.Timestamp(b)+pd.Timedelta(days=21)]
    d_=w-w.cummax(); i=d_.idxmin()
    print(f"{a}→{b} | {100*(idx[b]/idx[a]-1):6.1f}% | {eq[:b].iloc[-1]-eq[:a].iloc[-1]:+9.0f} | {d_.min():9.0f} ({w[:i].idxmax().date()}→{i.date()}) | {100*d_.min()/6e5:5.1f}% | {r7[a:b].min():8.0f} ({r7[a:b].idxmin().date()})")
print("\nworst 7-session equity drops (non-overlapping):")
s=r7.copy(); out=[]
while len(out)<12:
    i=s.idxmin(); out.append((i.date(),round(s[i]))); s[i-pd.Timedelta(days=20):i+pd.Timedelta(days=20)]=np.nan
for o in out: print(o)
print("live -41,422 in 7 sessions percentile among all 7-session windows:", round(100*(r7<=-41422).mean(),2),"%")
print("count of distinct 7-sess drops worse than -41k:", sum(1 for o in out if o[1]<=-41422), "(of top 12)")
yr=eq.groupby(eq.index.year).apply(lambda w:(w-w.cummax()).min())
print("\nmax MTM DD by year:", {k:round(v) for k,v in yr.items()})
eq.to_csv(f"{J}/bt_eq.csv")
