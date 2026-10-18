"""Synthetic OHLCV for tests and smoke runs (no store, no network)."""
import numpy as np
import pandas as pd

_BARS = 25  # 09:15 … 15:15 on a 15m grid


def _ohlcv(rng: np.random.Generator, n: int, sigma: float, drift: float, gap_sigma: float,
           first_gap_sigma: float, first_mask: np.ndarray, base: float = 100.0) -> pd.DataFrame:
    close = np.empty(n)
    open_ = np.empty(n)
    prev = base
    rets = rng.normal(drift, sigma, n)
    gaps = rng.normal(0.0, gap_sigma, n)
    gaps = np.where(first_mask, rng.normal(0.0, first_gap_sigma, n), gaps)
    for i in range(n):
        open_[i] = prev * (1.0 + gaps[i])
        close[i] = open_[i] * np.exp(rets[i])
        prev = close[i]
    up = np.abs(rng.normal(0.0, sigma * 0.5, n))
    dn = np.abs(rng.normal(0.0, sigma * 0.5, n))
    high = np.maximum(open_, close) * (1.0 + up)
    low = np.minimum(open_, close) * (1.0 - dn)
    vol = np.round(np.exp(rng.normal(9.0, 0.6, n))).astype("int64")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol})


def synthetic_15m(n_sessions: int, seed: int, start: str = "2020-01-06", missing_frac: float = 0.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(start, periods=n_sessions)
    offs = pd.to_timedelta(9 * 60 + 15 + 15 * np.arange(_BARS), unit="m")
    ts = (days.values[:, None] + offs.values[None, :]).ravel().astype("datetime64[ns]")
    n = len(ts)
    first = np.tile(np.arange(_BARS) == 0, n_sessions)
    df = _ohlcv(rng, n, 0.004, 0.00002, 0.0003, 0.003, first)
    df.insert(0, "timestamp", ts)
    if missing_frac > 0:
        drop = rng.random(n) < missing_frac
        sess = np.repeat(np.arange(n_sessions), _BARS)
        for s in range(n_sessions):          # never drop a whole session
            m = sess == s
            if drop[m].all():
                drop[np.flatnonzero(m)[0]] = False
        df = df[~drop]
    return df.reset_index(drop=True)


def synthetic_day(n_days: int, seed: int, start: str = "2019-01-01") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(start, periods=n_days)
    df = _ohlcv(rng, n_days, 0.018, 0.0003, 0.002, 0.002, np.zeros(n_days, dtype=bool))
    df.insert(0, "timestamp", days.values.astype("datetime64[ns]"))
    return df
