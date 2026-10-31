"""Which price-behaviour properties go with names that work under LRExtrema?

Outcome  : standalone backtest 2025-01-01 → 2026-10-14 under three regimes
           (15m global config, 4hour + day standard blocks @ thr 0.85, stale 10/30).
Properties: daily-candle behaviour measured POINT-IN-TIME on calendar 2024 (before the
           outcome window) — so anything that separates winners is usable for discovery.
Usage: python scripts/property_study.py SYMS_FILE OUT_JSON [--workers N] [--skip-bt]
"""
import json, sys, os, math, datetime as dt
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
REPO = "/Users/abhisheksingh/Projects/trader-2"
sys.path.insert(0, REPO); os.chdir(REPO)
from dotenv import load_dotenv; load_dotenv(f"{REPO}/config/.env")
import numpy as np, pandas as pd

BT_FROM, BT_TO = dt.datetime(2025, 1, 1), dt.datetime(2026, 10, 14, 23, 59)
P_FROM, P_TO = "2024-01-01", "2024-12-31"


def agg_block(tf):
    from trader.core.config import config
    b = json.loads(json.dumps(config._data["per_stock_params"]["NSE:CHENNPETRO"]["lr_extrema"]))
    b["timeframe"] = tf; b["threshold"] = 0.85; b["retrain_every"] = 2 if tf == "4hour" else 1
    return b


def bt_one(sym, regime):
    import logging; logging.disable(logging.CRITICAL)
    from trader.notifications import telegram; telegram.disable()
    from trader.core.config import config, flatten_strategy_params
    from trader.data.store import Store
    from trader.backtest.engine import run_backtest
    from scripts.calibrate_stock import _deep_merge
    store = Store(config.db_path)
    if regime == "15minute":
        params = config.strategy_config("lr_extrema")
    else:
        params = flatten_strategy_params(_deep_merge(config._data["strategies"]["lr_extrema"], agg_block(regime)))
    tr = run_backtest(None, store, [sym], {sym: 0}, params, BT_FROM, BT_TO) or []
    pn = [t["pnl"] for t in tr]
    won = sum(p for p in pn if p > 0); lost = -sum(p for p in pn if p <= 0)
    return sym, regime, {"pnl": round(sum(pn)), "trades": len(pn),
                         "win_rate": round(100 * sum(p > 0 for p in pn) / len(pn), 1) if pn else None,
                         "won": round(won), "lost": round(lost)}


def zigzag(c, pct):
    """Swing legs (abs % size) with a pct reversal threshold."""
    legs, piv, ext, up = [], c[0], c[0], None
    for x in c[1:]:
        if up in (None, True) and x > ext: ext = x
        if up in (None, False) and x < ext: ext = x
        if up is None:
            if x >= piv * (1 + pct): up, ext = True, x
            elif x <= piv * (1 - pct): up, ext = False, x
            continue
        if up and x <= ext * (1 - pct):
            legs.append(ext / piv - 1); piv, ext, up = ext, x, False
        elif not up and x >= ext * (1 + pct):
            legs.append(piv / ext - 1); piv, ext, up = ext, x, True
    return legs


def props(df, idx):
    d = df[(df.index >= P_FROM) & (df.index <= P_TO)]
    if len(d) < 150: return None
    c = d["close"].values; r = np.diff(np.log(c))
    ri = idx.reindex(d.index)["close"].pct_change().values[1:]
    rs = d["close"].pct_change().values[1:]
    ok = ~np.isnan(ri)
    beta = np.cov(rs[ok], ri[ok])[0, 1] / np.var(ri[ok]) if ok.sum() > 50 else None
    corr = np.corrcoef(rs[ok], ri[ok])[0, 1] if ok.sum() > 50 else None
    er20 = [abs(c[i] - c[i - 20]) / np.abs(np.diff(c[i - 20:i + 1])).sum() for i in range(20, len(c))]
    legs5 = zigzag(c, 0.05)
    # dip events: close first falls ≥7% under its 20d high; success = +7% from dip close within 30d
    hi20 = pd.Series(c).rolling(20, min_periods=5).max().values
    ev = succ = 0; i = 20
    while i < len(c) - 1:
        if c[i] <= 0.93 * hi20[i]:
            ev += 1; fwd = c[i + 1:i + 31]
            succ += bool((fwd >= c[i] * 1.07).any()); i += 30
        else: i += 1
    rv5 = pd.Series(np.log(c)).diff(5).dropna().var() / (5 * np.var(r)) if np.var(r) else None
    gaps = (d["open"].values[1:] / c[:-1] - 1)
    turn = (d["close"] * d["volume"]).median() / 1e7
    peak = np.maximum.accumulate(c)
    return {
        "vol_d": float(np.std(r) * 100),
        "range_pct": float(((d["high"] - d["low"]) / d["close"]).mean() * 100),
        "er250": float(abs(c[-1] - c[0]) / np.abs(np.diff(c)).sum()),
        "er20_med": float(np.median(er20)),
        "ac1": float(pd.Series(r).autocorr(1)),
        "vr5": float(rv5) if rv5 else None,
        "swing5_med": float(np.median(legs5) * 100) if legs5 else 0.0,
        "swings5_per_m": len(legs5) / (len(c) / 21),
        "dip_events": ev, "dip_recovery": succ / ev if ev else None,
        "ret_2024": float((c[-1] / c[0] - 1) * 100),
        "maxdd_2024": float((c / peak - 1).min() * 100),
        "beta": float(beta) if beta is not None else None,
        "corr_nifty": float(corr) if corr is not None else None,
        "turnover_cr": float(turn),
        "gap2_freq": float((np.abs(gaps) > 0.02).mean() * 100),
        "price": float(c[-1]),
    }


def main():
    syms = [s.strip() for s in open(sys.argv[1]) if s.strip()]
    out = sys.argv[2]; workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 8
    from trader.core.config import config
    from trader.data.store import Store
    from trader.data.historical import get_candles
    from scripts.calibrate_stock import _create_kite, _fetch_missing
    store = Store(config.db_path); kite = _create_kite()
    toks = {f"NSE:{i['tradingsymbol']}": i["instrument_token"] for i in kite.instruments("NSE")}
    res = json.load(open(out)) if Path(out).exists() else {}
    from trader.data.historical import _fetch_and_cache
    def day(s):
        with store._conn() as cn:
            old = cn.execute("SELECT MIN(timestamp) FROM candles WHERE instrument=? AND timeframe='day'", (s,)).fetchone()[0]
        if old is None or old > "2023-12-15":
            _fetch_and_cache(kite, store, toks[s], s, "day", dt.datetime(2023, 6, 1), dt.datetime.now())
        return get_candles(kite, store, toks[s], s, "day", dt.datetime(2023, 6, 1), dt.datetime.now())
    idx = day("NSE:NIFTY 50"); idx.index = pd.to_datetime(idx["timestamp"] if "timestamp" in idx else idx.index)
    for s in syms:
        if s not in toks: print("no token", s); continue
        r = res.setdefault(s, {})
        if "props" not in r:
            df = day(s); df.index = pd.to_datetime(df["timestamp"] if "timestamp" in df else df.index)
            df.index = df.index.tz_localize(None) if df.index.tz is not None else df.index
            idx.index = idx.index.tz_localize(None) if idx.index.tz is not None else idx.index
            r["props"] = props(df, idx)
    json.dump(res, open(out, "w"), indent=1)
    if "--skip-bt" in sys.argv: return
    _fetch_missing(store, [s for s in syms if s in toks], BT_FROM, BT_TO, min_warmup_days=725)
    jobs = [(s, rg) for s in syms if s in toks for rg in ("15minute", "4hour", "day")
            if rg not in res[s].get("bt", {})]
    print(f"{len(jobs)} backtests", flush=True)
    with ProcessPoolExecutor(workers) as ex:
        futs = [ex.submit(bt_one, s, rg) for s, rg in jobs]
        for n, f in enumerate(as_completed(futs), 1):
            try:
                s, rg, m = f.result()
                res[s].setdefault("bt", {})[rg] = m
                print(f"[{n}/{len(jobs)}] {s} {rg} {m}", flush=True)
            except Exception as e:
                print("ERR", e, flush=True)
            if n % 10 == 0: json.dump(res, open(out, "w"), indent=1)
    json.dump(res, open(out, "w"), indent=1)


if __name__ == "__main__":
    main()
