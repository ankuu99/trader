"""Stratify a saved backtest trade list by the market state at entry (prior session — no look-ahead):
India VIX trailing-250-day percentile tercile and Nifty drawdown from its 60-day high. One row per position
(add-on lots and scale-out records merged on instrument + entry_date).

    .venv/bin/python scripts/campaign/trades_by_market.py lab_data/campaign/trades/baseline_HORIZON.pkl
"""
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from trader.core.config import config  # noqa: E402
from trader.data.store import Store  # noqa: E402


def daily(store, sym):
    df = store.read_candles(sym, "15minute", pd.Timestamp("2018-01-01"), pd.Timestamp("2026-10-17"))
    df["d"] = pd.to_datetime(df["timestamp"]).dt.date
    return df.groupby("d")["close"].last()


def market_context(store) -> pd.DataFrame:
    vd, nd = daily(store, "NSE:INDIA VIX"), daily(store, "NSE:NIFTY 50")
    pct = vd.rolling(250, min_periods=60).apply(lambda w: (w[:-1] < w[-1]).mean(), raw=True)
    return pd.DataFrame({"vix": vd, "vix_pct": pct, "dd60": nd / nd.rolling(60, 20).max() - 1}).shift(1)


def main():
    trades = pickle.loads(Path(sys.argv[1]).read_bytes())
    ctx = market_context(Store(config.db_path))
    t = pd.DataFrame(trades)
    t["entry_date"] = pd.to_datetime(t["entry_date"])
    t["notional"] = t["entry"] * t["qty"]
    pos = t.groupby(["instrument", "entry_date"], as_index=False).agg(pnl=("pnl", "sum"), notional=("notional", "sum"))
    pos["ret_pct"] = pos["pnl"] / pos["notional"] * 100
    pos["d"] = pos["entry_date"].dt.date
    pos = pos.join(ctx, on="d").dropna(subset=["vix_pct", "dd60"])
    pos["vix_t"] = pd.cut(pos["vix_pct"], [-0.01, 1 / 3, 2 / 3, 1.01], labels=["calm", "mid", "stress"])
    pos["dd_b"] = pd.cut(pos["dd60"], [-1, -0.08, -0.03, 0.01], labels=["dd>8%", "3-8%", "<3%"])
    for col in ("vix_t", "dd_b"):
        g = pos.groupby(col, observed=True).agg(n=("pnl", "size"), pnl_k=("pnl", lambda x: x.sum() / 1e3),
                                                avg_ret=("ret_pct", "mean"), med_ret=("ret_pct", "median"),
                                                win=("pnl", lambda x: (x > 0).mean()))
        print(f"\nby {col}\n" + g.to_string(float_format=lambda v: f"{v:.2f}"))
    pos["year"] = pos["entry_date"].dt.year
    yr = pos.pivot_table(index="year", columns="vix_t", values="ret_pct", aggfunc="mean", observed=True)
    cnt = pos.pivot_table(index="year", columns="vix_t", values="ret_pct", aggfunc="size", observed=True)
    print("\navg position return % by year × VIX tercile (count in brackets)")
    for y in yr.index:
        print(y, "  ".join(f"{c}: {yr.loc[y, c]:6.2f} ({int(cnt.loc[y, c]) if not np.isnan(cnt.loc[y, c]) else 0})"
                           for c in yr.columns))


if __name__ == "__main__":
    main()
