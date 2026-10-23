import sqlite3
from collections import defaultdict, deque
c=sqlite3.connect('file:/opt/trader/data/market.db?mode=ro',uri=True)
rows=c.execute("select placed_at,instrument,direction,quantity,price from orders where status='COMPLETE' and mode='live' and price is not null and placed_at>='2026-05-01' order by placed_at").fetchall()
insts=sorted({r[1] for r in rows})
closes=defaultdict(dict)
for i in insts:
    for d,cl in c.execute("select substr(timestamp,1,10), close from candles where instrument=? and timestamp>='2026-05-01' order by timestamp",(i,)):
        closes[i][d]=cl
days=sorted({d for i in closes for d in closes[i]})
lots=defaultdict(deque); real=0.0; k=0; lastpx={}
print("date,realised,unrealised,equity,deployed,npos")
for d in days:
    while k<len(rows) and rows[k][0][:10]<=d:
        ts,i,side,q,p=rows[k]; k+=1
        if side=='BUY': lots[i].append([q,p])
        else:
            rem=q
            while rem and lots[i]:
                lq,lp=lots[i][0]; t=min(rem,lq); real+=t*(p-lp); rem-=t; lots[i][0][0]-=t
                if lots[i][0][0]==0: lots[i].popleft()
    un=0.0; dep=0.0; n=0
    for i,L in lots.items():
        if not L: continue
        px=closes[i].get(d, lastpx.get(i))
        if px is None: continue
        lastpx[i]=px; n+=1
        for q,p in L: un+=q*(px-p); dep+=q*p
    print(f"{d},{real:.0f},{un:.0f},{real+un:.0f},{dep:.0f},{n}")
import sys
print({i:[(q,round(p,1)) for q,p in L] for i,L in lots.items() if L}, file=sys.stderr)
