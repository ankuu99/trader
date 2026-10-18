"""Causal factor library: every column at bar t uses only data available at bar t's avail_ts.

No full-sample statistics, no centred windows. Joins to other series are exact on timestamp
(same-TF Nifty) or strictly earlier on avail_ts (VIX, higher timeframes).
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

HIGHER_TF = {"15m": ["60m", "day"], "30m": ["day"], "60m": ["day"], "4h": ["day", "week"],
             "dayagg": ["week"], "day": ["week"], "week": []}
HIGHER_SUBSET = ["ret_4", "ret_16", "dmin_20", "dmax_20", "dmin_100", "dmax_100", "rsi_14", "rv_16",
                 "atr_pct", "relvol_20", "bsl_20"]

_EXT_N = (20, 50, 100, 250, 500, 1000)
_RET_K = (1, 4, 16, 64, 256)
_BARS_PER_SESSION = {"15m": 25, "30m": 13, "60m": 7, "4h": 2}
_CLOSE = pd.Timedelta(hours=15, minutes=30)
_CHUNK = 4000


def _bars_since_extreme(x: np.ndarray, n: int, kind: str) -> np.ndarray:
    """Bars since the lowest (kind='min') / highest value of the last n bars incl. the current one.
    0 = this bar; ties -> the MOST RECENT occurrence. NaN until n bars exist."""
    L = len(x)
    out = np.full(L, np.nan)
    if L < n:
        return out
    win = sliding_window_view(x, n)                       # row j = x[j : j+n]  -> bar t = j + n - 1
    for a in range(0, win.shape[0], _CHUNK):
        w = win[a:a + _CHUNK, ::-1]                       # reversed: first occurrence == most recent
        idx = np.argmin(w, axis=1) if kind == "min" else np.argmax(w, axis=1)
        bad = np.isnan(w).any(axis=1)
        res = idx.astype(float)
        res[bad] = np.nan
        out[a + n - 1: a + n - 1 + len(idx)] = res
    return out


def own_factors(bars: pd.DataFrame) -> pd.DataFrame:
    o, h, l, c, v = (bars[k].astype("float64") for k in ("open", "high", "low", "close", "volume"))
    f: dict[str, pd.Series | np.ndarray] = {}
    cp = c.shift(1)
    f["gap_1"] = o / cp - 1
    f["body"] = (c - o) / o
    f["uwick"] = (h - np.maximum(o, c)) / o
    f["lwick"] = (np.minimum(o, c) - l) / o
    rng = h - l
    f["clv"] = ((c - l) / rng).where(rng != 0, 0.5)
    tr = pd.concat([h - l, (h - cp).abs(), (l - cp).abs()], axis=1).max(axis=1, skipna=True)
    tr.iloc[0] = (h - l).iloc[0]
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    atr.iloc[:13] = np.nan
    f["atr_14"] = atr
    f["atr_pct"] = atr / c
    f["range_atr"] = rng / atr
    r1 = np.log(c / cp)
    f["r1"] = r1
    sd = r1.rolling(256).std()
    f["sd_256"] = sd
    for k in _RET_K:
        rk = np.log(c / c.shift(k))
        f[f"ret_{k}"] = rk
        f[f"retz_{k}"] = rk / (sd * np.sqrt(k))
    bsl20 = None
    for n in _EXT_N:
        lmin = l.rolling(n).min()
        hmax = h.rolling(n).max()
        f[f"dmin_{n}"] = c / lmin - 1
        f[f"dmax_{n}"] = c / hmax - 1
        bsl = pd.Series(_bars_since_extreme(l.to_numpy(), n, "min"), index=bars.index)
        f[f"bsl_{n}"] = bsl
        f[f"bsh_{n}"] = pd.Series(_bars_since_extreme(h.to_numpy(), n, "max"), index=bars.index)
        if n == 20:
            bsl20 = bsl
    # RSI (Wilder)
    d = c.diff()
    ag = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    al = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = ag / al
    rsi = 100 - 100 / (1 + rs)
    rsi = rsi.where(~((ag == 0) & (al == 0)), 50.0)
    rsi.iloc[:14] = np.nan
    f["rsi_14"] = rsi
    lo14, hi14 = l.rolling(14).min(), h.rolling(14).max()
    f["stoch_14"] = ((c - lo14) / (hi14 - lo14)).where(hi14 != lo14, 0.5).where(lo14.notna())
    for k in (16, 64, 256):
        f[f"rv_{k}"] = r1.rolling(k).std()
    rv16 = f["rv_16"]
    f["vov_64"] = rv16.rolling(64).std() / rv16.rolling(64).mean()
    f["rngexp_20"] = rng / rng.rolling(20).mean()
    vm = v.shift(1).rolling(20).mean()
    f["relvol_20"] = (v / vm).where(vm != 0)
    lv = np.log1p(v)
    vs = lv.rolling(64).std()
    f["volz_64"] = ((lv - lv.rolling(64).mean()) / vs).where(vs != 0)
    sv = v.rolling(20).sum()
    f["upvol_20"] = ((v * (c > o)).rolling(20).sum() / sv).where(sv != 0, 0.5).where(sv.notna())
    pos = np.arange(len(bars)) - bsl20.to_numpy()
    vals = np.full(len(bars), np.nan)
    ok = ~np.isnan(pos)
    vals[ok] = v.to_numpy()[pos[ok].astype(int)]
    vm20 = v.rolling(20).mean()
    f["lowbar_relvol_20"] = pd.Series(vals, index=bars.index) / vm20
    out = pd.DataFrame(f, index=bars.index)
    return out.replace([np.inf, -np.inf], np.nan)


def monthly_expiry(d: date) -> date:
    """Next monthly F&O expiry on or after d. Last Thursday of the month before 2025-09, last Tuesday from
    2025-09 (NSE/SEBI change). Holidays ignored (documented approximation)."""
    def last_wd(y: int, m: int) -> date:
        wd = 3 if (y, m) < (2025, 9) else 1
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        last = nxt - timedelta(days=1)
        return last - timedelta(days=(last.weekday() - wd) % 7)
    e = last_wd(d.year, d.month)
    if d > e:
        y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
        e = last_wd(y, m)
    return e


def calendar_factors(bars: pd.DataFrame, tf: str) -> pd.DataFrame:
    ts = bars["timestamp"]
    dates = ts.dt.normalize()
    out = pd.DataFrame(index=bars.index)
    if tf in ("day", "week"):
        out["tod"] = 0.0
    else:
        out["tod"] = (ts.dt.hour * 60 + ts.dt.minute - (9 * 60 + 15)).astype(float)
    out["dow"] = ts.dt.weekday.astype(float)
    eom = dates + pd.offsets.MonthEnd(0)
    out["dtme"] = (eom - dates).dt.days.astype(float)
    uniq = dates.drop_duplicates()
    exp = {u: monthly_expiry(u.date()) for u in uniq}
    out["dtexp"] = np.array([(exp[u] - u.date()).days for u in dates], dtype=float)
    bps = _BARS_PER_SESSION.get(tf)
    out["sesspos"] = (dates.groupby(dates).cumcount() / bps).astype(float) if bps else 0.0
    return out


def _vix_cols(vix_day: pd.DataFrame) -> pd.DataFrame:
    v = vix_day.sort_values("timestamp").reset_index(drop=True)
    c = v["close"].astype("float64")
    return pd.DataFrame({
        "avail_ts": (v["timestamp"].dt.normalize() + _CLOSE).astype("datetime64[ns]"),
        "vix_close_d1": c,
        "vix_pct_252_d1": c.rolling(252, min_periods=200).rank(pct=True),
        "vix_ret_5_d1": np.log(c / c.shift(5)),
    })


_MARKET_COLS = ["nifty_ret_1", "nifty_ret_16", "nifty_ret_64", "nifty_dmax_250", "beta_250", "resid_16",
                "rs_64", "vix_close_d1", "vix_pct_252_d1", "vix_ret_5_d1"]


def market_factors(bars: pd.DataFrame, own: pd.DataFrame, nifty: pd.DataFrame | None,
                   vix_day: pd.DataFrame | None) -> pd.DataFrame:
    out = pd.DataFrame(np.nan, index=bars.index, columns=_MARKET_COLS)
    if nifty is not None and len(nifty):
        nf = own_factors(nifty)
        nf.index = pd.DatetimeIndex(nifty["timestamp"].astype("datetime64[ns]"))
        nf = nf[~nf.index.duplicated()]
        al = nf.reindex(pd.DatetimeIndex(bars["timestamp"].astype("datetime64[ns]")))
        al.index = bars.index
        out["nifty_ret_1"] = al["ret_1"]
        out["nifty_ret_16"] = al["ret_16"]
        out["nifty_ret_64"] = al["ret_64"]
        out["nifty_dmax_250"] = al["dmax_250"]
        nr1 = al["r1"]
        r1 = own["r1"]
        cov = r1.rolling(250, min_periods=200).cov(nr1)
        var = nr1.rolling(250, min_periods=200).var()
        beta = cov / var
        out["beta_250"] = beta
        out["resid_16"] = own["ret_16"] - beta * out["nifty_ret_16"]
        out["rs_64"] = own["ret_64"] - out["nifty_ret_64"]
    if vix_day is not None and len(vix_day):
        vx = _vix_cols(vix_day)
        left = pd.DataFrame({"avail_ts": bars["avail_ts"].astype("datetime64[ns]").values})
        m = pd.merge_asof(left, vx, on="avail_ts", direction="backward", allow_exact_matches=False)
        for c in ("vix_close_d1", "vix_pct_252_d1", "vix_ret_5_d1"):
            out[c] = m[c].values
    return out.replace([np.inf, -np.inf], np.nan)


def higher_tf_factors(bars: pd.DataFrame, higher: dict[str, pd.DataFrame | None]) -> pd.DataFrame:
    parts = []
    left = pd.DataFrame({"avail_ts": bars["avail_ts"].astype("datetime64[ns]").values})
    for htf, hb in higher.items():
        cols = [f"h{htf}_{c}" for c in HIGHER_SUBSET]
        if hb is None or len(hb) == 0:
            parts.append(pd.DataFrame(np.nan, index=bars.index, columns=cols))
            continue
        hf = own_factors(hb)[HIGHER_SUBSET]
        hf.columns = cols
        hf.insert(0, "avail_ts", hb["avail_ts"].astype("datetime64[ns]").values)
        hf = hf.sort_values("avail_ts")
        m = pd.merge_asof(left, hf, on="avail_ts", direction="backward", allow_exact_matches=False)
        p = m[cols]
        p.index = bars.index
        parts.append(p)
    if not parts:
        return pd.DataFrame(index=bars.index)
    return pd.concat(parts, axis=1)


def compute_factors(bars: pd.DataFrame, tf: str, nifty=None, vix_day=None, higher=None) -> pd.DataFrame:
    bars = bars.reset_index(drop=True)
    own = own_factors(bars)
    cal = calendar_factors(bars, tf)
    mkt = market_factors(bars, own, nifty, vix_day)
    hmap = {htf: (higher or {}).get(htf) for htf in HIGHER_TF[tf]}
    hi = higher_tf_factors(bars, hmap)
    head = pd.DataFrame({"timestamp": bars["timestamp"].values, "avail_ts": bars["avail_ts"].values})
    return pd.concat([head, own, cal, mkt, hi], axis=1)


def cross_section(inputs: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """inputs[sym] = frame with timestamp, ret_16, ret_64, close (one TF). Per timestamp across symbols."""
    syms = list(inputs)
    frames = []
    for s in syms:
        d = inputs[s]
        c = d["close"].astype("float64")
        ma = c.rolling(100).mean()
        ab = (c > ma).astype("float64").where(ma.notna())
        frames.append(pd.DataFrame({"timestamp": d["timestamp"].values, "ret_16": d["ret_16"].values,
                                    "ret_64": d["ret_64"].values, "above_100": ab.values}))
    big = pd.concat(frames, ignore_index=True)
    g = big.groupby("timestamp")
    big["xs_n"] = g["ret_16"].transform("count").astype(float)
    big["xs_rank_ret16"] = g["ret_16"].rank(pct=True)
    big["xs_rank_ret64"] = g["ret_64"].rank(pct=True)
    big["xs_breadth_100"] = g["above_100"].transform("mean")
    thin = big["xs_n"] < 10
    for c in ("xs_rank_ret16", "xs_rank_ret64", "xs_breadth_100"):
        big.loc[thin, c] = np.nan
    res, a = {}, 0
    cols = ["xs_n", "xs_rank_ret16", "xs_rank_ret64", "xs_breadth_100"]
    for s in syms:
        n = len(inputs[s])
        res[s] = big.iloc[a:a + n][cols].reset_index(drop=True)
        a += n
    return res
