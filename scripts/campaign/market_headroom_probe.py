"""Market-information headroom probe (ledger EXP-13 pre-check): univariate AUC vs the Stage-A truth for
measures that use Nifty/VIX — prior-session context (no look-ahead) and the stock's residual vs Nifty.
Baseline score cache; Nifty/VIX from the 15m cache (as-of join on bar timestamps).

    .venv/bin/python scripts/campaign/market_headroom_probe.py
"""
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.campaign.stage_a import CALIB_END, auc, simulate_exits, stock_series  # noqa: E402
from trader.core.config import config  # noqa: E402
from trader.data.store import Store  # noqa: E402
from trader.features.ou import ou_score  # noqa: E402  (exp/rules worktree)


def series(store, sym):
    df = store.read_candles(sym, "15minute", pd.Timestamp("2019-06-01"), pd.Timestamp("2026-10-17"))
    return df.assign(timestamp=pd.to_datetime(df["timestamp"])).set_index("timestamp")["close"].astype(float)


def main():
    run = pickle.loads((ROOT / "lab_data/campaign/scores/baseline.pkl").read_bytes())
    store = Store(config.db_path)
    nifty, vix = series(store, "NSE:NIFTY 50"), series(store, "NSE:INDIA VIX")
    nd, vd = nifty.groupby(nifty.index.date).last(), vix.groupby(vix.index.date).last()
    ctx = pd.DataFrame({"vix_prev": vd, "vix_z250": (vd - vd.rolling(250, 60).mean()) / vd.rolling(250, 60).std(),
                        "nifty_dd20": nd / nd.rolling(20, 10).max() - 1, "nifty_dd60": nd / nd.rolling(60, 20).max() - 1,
                        "nifty_ret5": nd / nd.shift(5) - 1}).shift(1)
    rows = {}
    for sym, p in run["params"].items():
        ser = stock_series(run, sym)
        if ser is None:
            continue
        ts, c, pmin, _ = ser
        good, ret, _ = simulate_exits(c, p)
        tsi = pd.to_datetime(pd.Series(ts))
        test = (tsi >= CALIB_END).values & ~np.isnan(ret)
        nb = nifty.reindex(tsi, method="ffill").values  # nifty at the bar's own timestamp (bar close known)
        lc, ln = np.log(c), np.log(nb)
        r_s, r_n = np.diff(lc, prepend=np.nan), np.diff(ln, prepend=np.nan)
        resid_cum = np.full(len(c), np.nan)
        res20 = np.full(len(c), np.nan)
        rs_ou = np.full(len(c), np.nan)
        W = 60
        for i in range(W + 1, len(c)):
            ys, xs = r_s[i - W + 1:i + 1], r_n[i - W + 1:i + 1]
            ok = ~(np.isnan(ys) | np.isnan(xs))
            if ok.sum() < 30 or np.var(xs[ok]) == 0:
                continue
            beta = np.cov(ys[ok], xs[ok])[0, 1] / np.var(xs[ok])
            e = np.where(ok, ys - beta * xs, 0.0)
            res20[i] = e[-20:].sum()
            s, _ = ou_score(np.exp(np.cumsum(e)), W - 1)
            rs_ou[i] = s
        day = tsi.dt.date
        cx = ctx.reindex(day).values
        feats = {"p_min": pmin, "-resid_ret20": -res20, "-resid_ou_s": -rs_ou,
                 "vix_prev": cx[:, 0], "vix_z250": cx[:, 1], "-nifty_dd20": -cx[:, 2], "-nifty_dd60": -cx[:, 3],
                 "-nifty_ret5": -cx[:, 4]}
        rows[sym] = {k: auc(v[test], good[test]) for k, v in feats.items()}
        rows[sym]["tf"] = p.get("timeframe", "15minute")[:6]
    keys = [k for k in next(iter(rows.values())) if k != "tf"]
    print(f"{'stock':<13}{'tf':<7}" + "".join(f"{k:>13}" for k in keys))
    for s, r in sorted(rows.items()):
        print(f"{s[4:]:<13}{r['tf']:<7}" + "".join(f"{r[k]:13.3f}" for k in keys))
    print(f"{'MEDIAN':<20}" + "".join(f"{np.nanmedian([r[k] for r in rows.values()]):13.3f}" for k in keys))
    print(f"{'frac>0.5':<20}" + "".join(f"{np.nanmean([r[k] > 0.5 for r in rows.values()]):13.2f}" for k in keys))


if __name__ == "__main__":
    main()
