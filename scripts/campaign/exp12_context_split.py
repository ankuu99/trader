"""EXP-12 (docs/02 literature review): does market context carry headroom for the tradeable-trough truth?
Splits the Stage-A truth (baseline score cache, all bars 2023-01 → 2026-10) by PRIOR-DAY India VIX tercile and
by prior-day Nifty drawdown from its 50-day high — no model change. Also for "dip bars" (stock 50-bar depth in
its own bottom quintile). No look-ahead: context is the previous session's close.

    .venv/bin/python scripts/campaign/exp12_context_split.py
"""
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.campaign.stage_a import simulate_exits, stock_series  # noqa: E402
from trader.core.config import config  # noqa: E402
from trader.data.store import Store  # noqa: E402


def daily_close(store, sym):
    df = store.read_candles(sym, "15minute", pd.Timestamp("2019-06-01"), pd.Timestamp("2026-10-17"))
    df["date"] = pd.to_datetime(df["timestamp"]).dt.date
    return df.groupby("date")["close"].last()


def main():
    run = pickle.loads((ROOT / "lab_data/campaign/scores/baseline.pkl").read_bytes())
    store = Store(config.db_path)
    vix = daily_close(store, "NSE:INDIA VIX")
    nifty = daily_close(store, "NSE:NIFTY 50")
    ctx = pd.DataFrame({"vix": vix, "nifty_dd": nifty / nifty.rolling(50, min_periods=20).max() - 1})
    ctx = ctx.shift(1)  # prior session only
    rows = []
    for sym, p in run["params"].items():
        ser = stock_series(run, sym)
        if ser is None:
            continue
        ts, c, _, _ = ser
        good, ret, _ = simulate_exits(c, p)
        dates = pd.to_datetime(pd.Series(ts)).dt.date
        depth = pd.Series(c / pd.Series(c).rolling(50, min_periods=50).max().values - 1)
        df = pd.DataFrame({"sym": sym, "date": dates, "good": good, "ret": ret, "depth": depth})
        df = df.join(ctx, on="date").dropna(subset=["ret", "vix", "nifty_dd", "depth"])
        df["dip"] = df["depth"] <= df["depth"].quantile(0.2)
        rows.append(df)
    d = pd.concat(rows)
    d["vix_t"] = pd.qcut(d["vix"], 3, labels=["low", "mid", "high"])
    d["dd_b"] = pd.cut(d["nifty_dd"], [-1, -0.08, -0.03, 0.001], labels=["dd>8%", "3-8%", "<3%"])
    out = []
    for name, grp in (("all bars", d), ("dip bars", d[d["dip"]])):
        for col in ("vix_t", "dd_b"):
            t = grp.groupby(col, observed=True).agg(n=("good", "size"), p_good=("good", "mean"), ev=("ret", "mean"))
            # per-stock consistency: share of stocks where the top bucket beats the bottom bucket on p_good
            ps = grp.groupby(["sym", col], observed=True)["good"].mean().unstack()
            hi, lo = (ps.columns[-1], ps.columns[0]) if col == "vix_t" else (ps.columns[0], ps.columns[-1])
            cons = float((ps[hi] > ps[lo]).mean())
            out.append(f"\n[{name}] by {col}  (stress bucket beats calm bucket on P(good) in {cons:.0%} of stocks)\n"
                       + t.to_string(float_format=lambda v: f"{v:.3f}"))
    print("\n".join(out))
    print(f"\nvix tercile edges: {d['vix'].quantile([1/3, 2/3]).round(2).tolist()}  n={len(d)}")


if __name__ == "__main__":
    main()
