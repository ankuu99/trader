"""Market-timing stability check (ledger EXP-18 pre-check): is the prior-day India VIX / Nifty-drawdown edge on
the tradeable-trough truth stable across calendar years 2020–2026 (incl. COVID and the 2022 bear)?
Truth needs only prices: every watchlist stock's strategy-TF closes are rebuilt from the 15m cache with the
production CandleAggregator, then run through the shared exit simulator with that stock's own params.

    .venv/bin/python scripts/campaign/vix_by_year.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.campaign.stage_a import auc  # noqa: E402
from trader.core.config import config  # noqa: E402
from trader.data.aggregator import CandleAggregator  # noqa: E402
from trader.data.store import Store  # noqa: E402
from trader.policy.outcome import simulate_exit_outcomes  # noqa: E402


def daily(store, sym):
    df = store.read_candles(sym, "15minute", pd.Timestamp("2019-01-01"), pd.Timestamp("2026-10-17"))
    df["d"] = pd.to_datetime(df["timestamp"]).dt.date
    return df.groupby("d")["close"].last()


def bars(store, sym, tf):
    df = store.read_candles(sym, "15minute", pd.Timestamp("2019-10-01"), pd.Timestamp("2026-10-17"))
    agg = CandleAggregator(tf)
    out = []
    for row in df.itertuples(index=False):
        c = {"timestamp": pd.Timestamp(row.timestamp).to_pydatetime(), "open": row.open, "high": row.high,
             "low": row.low, "close": row.close, "volume": row.volume}
        b = agg.add(c)
        if b is not None:
            out.append((b["timestamp"], b["close"]))
    return out


def main():
    store = Store(config.db_path)
    vd, nd = daily(store, "NSE:INDIA VIX"), daily(store, "NSE:NIFTY 50")
    ctx = pd.DataFrame({"vix": vd, "dd60": nd / nd.rolling(60, 20).max() - 1}).shift(1)
    frames = []
    for sym in config.watchlist:
        p = config.get_strategy_params(sym, "lr_extrema")
        tf = p.get("timeframe", "15minute")
        b = bars(store, sym, tf)
        if len(b) < 300:
            continue
        ts = pd.to_datetime([x[0] for x in b]); closes = np.array([x[1] for x in b], float)
        good, ret, _ = simulate_exit_outcomes(closes, p)
        df = pd.DataFrame({"sym": sym, "ts": ts, "good": good, "ret": ret})
        df["d"] = df["ts"].dt.date
        frames.append(df.join(ctx, on="d").dropna(subset=["ret", "vix", "dd60"]))
    d = pd.concat(frames)
    d = d[d["ts"] >= "2020-01-01"]
    edges = d["vix"].quantile([1 / 3, 2 / 3]).values
    d["vt"] = np.digitize(d["vix"], edges)
    print(f"VIX tercile edges (2020–26 pooled): {np.round(edges, 2)}   stocks={d['sym'].nunique()}  bars={len(d)}")
    print(f"{'year':<6}{'bars':>8}{'stocks':>7}{'AUC vix':>9}{'AUC -dd60':>10}{'P lo':>7}{'P hi':>7}{'EV lo':>7}{'EV hi':>7}"
          f"{'stk hi>lo':>10}")
    for y, g in d.groupby(d["ts"].dt.year):
        lo, hi = g[g["vt"] == 0], g[g["vt"] == 2]
        per = g.groupby(["sym", "vt"])["good"].mean().unstack()
        cons = ((per.get(2) > per.get(0)).sum() / per[[0, 2]].dropna().shape[0]) if {0, 2} <= set(per.columns) and per[[0, 2]].dropna().shape[0] else np.nan
        print(f"{y:<6}{len(g):>8}{g['sym'].nunique():>7}{auc(g['vix'].values, g['good'].values):9.3f}"
              f"{auc(-g['dd60'].values, g['good'].values):10.3f}"
              f"{lo['good'].mean() if len(lo) else np.nan:7.3f}{hi['good'].mean() if len(hi) else np.nan:7.3f}"
              f"{lo['ret'].mean() if len(lo) else np.nan:7.2f}{hi['ret'].mean() if len(hi) else np.nan:7.2f}"
              f"{cons:10.2f}")


if __name__ == "__main__":
    main()
