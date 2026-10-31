"""EXP-14 probe (docs/02 arm 6): does decline-window volume change whether a dip pays?
Stage-A truth on the baseline score cache, 15m names only (volume read from the candle cache). Dip bars = the
stock's 50-bar depth in its own bottom quintile. Volume ratio = mean volume of the last 5 bars / mean of the last 50.
Capitulation prior: high-volume dips pay; Medhat & Schmeling (2022): high-turnover losers keep losing.

    .venv/bin/python scripts/campaign/exp14_volume_split.py
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


def main():
    run = pickle.loads((ROOT / "lab_data/campaign/scores/baseline.pkl").read_bytes())
    store = Store(config.db_path)
    rows = []
    for sym, p in run["params"].items():
        if p.get("timeframe", "15minute") != "15minute":
            continue
        ts, c, _, _ = stock_series(run, sym)
        good, ret, _ = simulate_exits(c, p)
        cdf = store.read_candles(sym, "15minute", pd.Timestamp("2022-06-01"), pd.Timestamp("2026-10-17"))
        cdf["timestamp"] = pd.to_datetime(cdf["timestamp"])
        v = cdf.set_index("timestamp")["volume"].astype(float)
        vr = (v.rolling(5).mean() / v.rolling(50).mean()).reindex(pd.to_datetime(pd.Series(ts))).values
        depth = c / pd.Series(c).rolling(50, min_periods=50).max().values - 1
        df = pd.DataFrame({"sym": sym, "good": good, "ret": ret, "vr": vr, "depth": depth}).dropna()
        df = df[df["depth"] <= df["depth"].quantile(0.2)]
        df["vol_t"] = pd.qcut(df["vr"], 3, labels=["low", "mid", "high"])
        rows.append(df)
    d = pd.concat(rows)
    t = d.groupby("vol_t", observed=True).agg(n=("good", "size"), p_good=("good", "mean"), ev=("ret", "mean"))
    ps = d.groupby(["sym", "vol_t"], observed=True)["good"].mean().unstack()
    print(t.to_string(float_format=lambda x: f"{x:.3f}"))
    print(f"high-volume tercile beats low on P(good) in {(ps['high'] > ps['low']).mean():.0%} of {len(ps)} stocks")
    print(ps.round(3).to_string())


if __name__ == "__main__":
    main()
