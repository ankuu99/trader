"""Lab timeframes derived from native bars, each with `avail_ts` (when the bar's values are known)."""
import pandas as pd

TFS = ("15m", "30m", "60m", "4h", "dayagg", "day", "week", "dayn", "weekn")
SOURCE = {"15m": "15minute", "30m": "15minute", "60m": "15minute", "4h": "15minute",
          "dayagg": "15minute", "day": "day", "week": "day",
          "dayn": "day_nse", "weekn": "day_nse"}

_BASE = pd.Timedelta(minutes=15)
_OPEN_MIN = 9 * 60 + 15
_TAIL_MIN = 15 * 60 + 15
_CLOSE = pd.Timedelta(hours=15, minutes=30)
_OUT = ["timestamp", "open", "high", "low", "close", "volume", "avail_ts", "n_members"]


def _mins(ts: pd.Series) -> pd.Series:
    return ts.dt.hour * 60 + ts.dt.minute


def _agg(src: pd.DataFrame, key: pd.Series, bucket_start: pd.Series) -> pd.DataFrame:
    g = src.groupby(key, sort=True)
    out = g.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                close=("close", "last"), volume=("volume", "sum"),
                last_ts=("timestamp", "max"), n_members=("timestamp", "size"))
    out["timestamp"] = bucket_start.groupby(key, sort=True).first()
    return out.reset_index(drop=True)


def derive(src: pd.DataFrame, tf: str) -> pd.DataFrame:
    if tf not in TFS:
        raise ValueError(f"unknown timeframe {tf!r}")
    src = src.sort_values("timestamp").reset_index(drop=True)
    src["timestamp"] = src["timestamp"].astype("datetime64[ns]")
    if len(src) == 0:
        return pd.DataFrame({c: [] for c in _OUT})

    if tf == "15m":
        out = src[["timestamp", "open", "high", "low", "close", "volume"]].copy()
        out["avail_ts"] = out["timestamp"] + _BASE
        out["n_members"] = 1
        return out[_OUT].reset_index(drop=True)

    if tf in ("day", "dayn"):
        out = src[["timestamp", "open", "high", "low", "close", "volume"]].copy()
        out["avail_ts"] = out["timestamp"].dt.normalize() + _CLOSE
        out["n_members"] = 1
        return out[_OUT].reset_index(drop=True)

    if tf in ("week", "weekn"):
        d = src.copy()
        wk = d["timestamp"].dt.to_period("W-SUN")
        out = _agg(d, wk, d["timestamp"])
        out["avail_ts"] = out["last_ts"].dt.normalize() + _CLOSE
        out = out.iloc[:-1]                        # final week's completeness is unknowable
        return out[_OUT].reset_index(drop=True)

    # intraday-derived from 15m
    s = src
    m = _mins(s["timestamp"])
    day = s["timestamp"].dt.normalize()
    dnum = (day - pd.Timestamp("1970-01-01")).dt.days.astype("int64")      # small ints: no overflow in keys
    if tf in ("4h", "dayagg"):
        keep = m < _TAIL_MIN                       # 15:15 tail dropped
        s, m, day, dnum = s[keep], m[keep], day[keep], dnum[keep]
        if tf == "4h":
            idx = (m >= 13 * 60 + 15).astype(int)
            start_off = pd.to_timedelta(pd.Series(idx).map({0: _OPEN_MIN, 1: 13 * 60 + 15}).values, unit="m")
            key = dnum * 4 + idx.values.astype("int64")
        else:
            idx = pd.Series(0, index=s.index)
            start_off = pd.to_timedelta(_OPEN_MIN, unit="m")
            key = dnum
        bstart = day + start_off
        if tf == "4h":
            exp_last = pd.Series(idx.map({0: 13 * 60, 1: 15 * 60}).values, index=s.index)
        else:
            exp_last = pd.Series(15 * 60, index=s.index)
    else:
        n = 30 if tf == "30m" else 60
        k = (m - _OPEN_MIN) // n
        bstart = day + pd.to_timedelta(_OPEN_MIN + k * n, unit="m")
        key = dnum * 64 + k.astype("int64")
        exp_last = pd.Series((_OPEN_MIN + k * n + n - 15).clip(upper=_TAIL_MIN).values, index=s.index)

    s = s.copy()
    s["_key"] = key.values
    s["_exp"] = exp_last.values
    out = _agg(s, s["_key"], pd.Series(bstart.values, index=s.index))
    exp = s.groupby("_key", sort=True)["_exp"].first().values
    out["avail_ts"] = out["last_ts"] + _BASE
    # drop the LAST bucket if its last member is not the bucket's expected last slot
    last_m = out["last_ts"].dt.hour.iloc[-1] * 60 + out["last_ts"].dt.minute.iloc[-1]
    if last_m != exp[-1]:
        out = out.iloc[:-1]
    return out[_OUT].reset_index(drop=True)


def load(symbol: str, tf: str, start=None, end=None) -> pd.DataFrame:
    from research.model_lab import store          # lazy: store.py is built by the L0a guide
    return derive(store.read_bars(symbol, SOURCE[tf], start, end), tf)
