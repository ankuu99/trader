"""Buy-and-hold reference for the campaign windows: ₹ capital split equally across the watchlist names that have
data on the window's first session (held to the end, no costs), plus the Nifty 50. Max drawdown on the daily
equity curve. Same names as the bot — so it carries the same watchlist-selection hindsight.

    .venv/bin/python scripts/campaign/buy_hold_benchmark.py
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.campaign.run_windows import WINDOWS  # noqa: E402
from trader.core.config import config  # noqa: E402
from trader.data.store import Store  # noqa: E402


def daily(store, sym, f, t):
    df = store.read_candles(sym, "15minute", pd.Timestamp(f), pd.Timestamp(t) + pd.Timedelta(days=1))
    if df.empty:
        return pd.Series(dtype=float)
    df["d"] = pd.to_datetime(df["timestamp"]).dt.normalize()
    return df.groupby("d")["close"].last()


def curve_stats(eq: pd.Series, cap: float):
    dd = (eq / eq.cummax() - 1).min() * 100
    return eq.iloc[-1] - cap, dd


def main():
    store, cap = Store(config.db_path), float(config.total_capital)
    for w in ("FULL", "HORIZON", "H1-25", "H2-25", "H1-26", "H2-26"):
        f, t = WINDOWS[w]
        closes = {s: daily(store, s, f, t) for s in config.watchlist}
        first = min(c.index.min() for c in closes.values() if len(c))
        avail = {s: c for s, c in closes.items() if len(c) and c.index.min() <= first + pd.Timedelta(days=5)}
        px = pd.DataFrame(avail).ffill().dropna()
        eq = (px / px.iloc[0] * (cap / len(avail))).sum(axis=1)
        pnl, dd = curve_stats(eq, cap)
        n = daily(store, "NSE:NIFTY 50", f, t)
        npnl, ndd = curve_stats(n / n.iloc[0] * cap, cap)
        print(f"{w:<8} watchlist B&H ({len(avail):2d} names) ₹{pnl / 1e3:8.1f}k DD {dd:6.1f}%  |  "
              f"Nifty 50 B&H ₹{npnl / 1e3:7.1f}k DD {ndd:6.1f}%")


if __name__ == "__main__":
    main()
