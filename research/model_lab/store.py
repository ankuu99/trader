"""Parquet bar store for the Model Lab (pure file IO, no Kite).

One file per (native interval, symbol): BARS_DIR/<interval>/<SYMBOL>.parquet.
Native intervals are 15minute and day; every other timeframe is derived in L0b.
Timestamps are naive IST (same convention as trader.data.store.Store._to_naive).
"""
import json
import os
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from research.model_lab import paths
from research.model_lab.paths import check_disk, file_sym, sym_file

NATIVE = ("15minute", "day", "day_nse")
COLS = ["timestamp", "open", "high", "low", "close", "volume"]
_PRICE = ["open", "high", "low", "close"]
_MAX_VOL = 2 ** 62


def _dir(interval: str) -> Path:
    return paths.BARS_DIR / interval


def bar_path(symbol: str, interval: str) -> Path:
    return _dir(interval) / f"{sym_file(symbol)}.parquet"


def _empty() -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp": pd.Series(dtype="datetime64[ns]"),
        **{c: pd.Series(dtype="float64") for c in _PRICE},
        "volume": pd.Series(dtype="int64"),
    })


def clean_bars(df: pd.DataFrame, interval: str) -> pd.DataFrame:
    if df is None or len(df) == 0:
        return _empty()
    out = df[COLS].copy()
    ts = pd.to_datetime(out["timestamp"])
    if ts.dt.tz is not None:
        ts = ts.dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    out["timestamp"] = ts.astype("datetime64[ns]")
    for c in _PRICE:
        out[c] = pd.to_numeric(out[c], errors="coerce").astype("float64")
    out = out.dropna(subset=_PRICE)
    out = out[(out[_PRICE] > 0).all(axis=1)]
    vol = pd.to_numeric(out["volume"], errors="coerce").fillna(0)
    vol = vol.where((vol >= 0) & (vol <= _MAX_VOL), 0)
    out["volume"] = vol.astype("int64")
    if interval == "15minute":
        t = out["timestamp"]
        mins = t.dt.hour * 60 + t.dt.minute
        keep = (t.dt.minute % 15 == 0) & (mins >= 9 * 60 + 15) & (mins <= 15 * 60 + 15)
        out = out[keep]
    elif interval in ("day", "day_nse"):
        out["timestamp"] = out["timestamp"].dt.normalize()
    out = out.drop_duplicates("timestamp", keep="last").sort_values("timestamp")
    return out.reset_index(drop=True)


def _bound(x):
    if x is None:
        return None
    if isinstance(x, str):
        return pd.Timestamp(x)
    if isinstance(x, datetime):
        return pd.Timestamp(x)
    if isinstance(x, date):
        return pd.Timestamp(x)
    return pd.Timestamp(x)


def read_bars(symbol: str, interval: str, start=None, end=None) -> pd.DataFrame:
    p = bar_path(symbol, interval)
    if not p.exists():
        return _empty()
    df = clean_bars(pd.read_parquet(p), interval)
    s, e = _bound(start), _bound(end)
    if s is not None:
        df = df[df["timestamp"] >= s]
    if e is not None:
        df = df[df["timestamp"] <= e]
    return df.reset_index(drop=True)


def _atomic_write(path: Path, writer) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    try:
        writer(tmp)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def write_bars(symbol: str, interval: str, df: pd.DataFrame) -> int:
    check_disk()
    p = bar_path(symbol, interval)
    parts = [clean_bars(df, interval)]
    if p.exists():
        parts.insert(0, pd.read_parquet(p))
    parts = [x for x in parts if len(x)]
    merged = clean_bars(pd.concat(parts, ignore_index=True), interval) if parts else _empty()
    _atomic_write(p, lambda t: merged.to_parquet(
        t, engine="pyarrow", compression="zstd", index=False))
    return len(merged)


def list_symbols(interval: str) -> list[str]:
    d = _dir(interval)
    if not d.exists():
        return []
    return sorted(file_sym(f.stem) for f in d.glob("*.parquet"))


def coverage(symbol: str, interval: str):
    p = bar_path(symbol, interval)
    if not p.exists():
        return None
    ts = pd.read_parquet(p, columns=["timestamp"])["timestamp"]
    if ts.empty:
        return None
    return ts.min(), ts.max()


def _manifest_path(interval: str) -> Path:
    return _dir(interval) / "_manifest.json"


def load_manifest(interval: str) -> dict[str, dict]:
    p = _manifest_path(interval)
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def update_manifest(interval: str, symbol: str, req_from: datetime, req_to: datetime) -> None:
    man = load_manifest(interval)
    f, t = pd.Timestamp(req_from).isoformat(), pd.Timestamp(req_to).isoformat()
    cur = man.get(symbol)
    if cur:
        f, t = min(f, cur["from"]), max(t, cur["to"])
    man[symbol] = {"from": f, "to": t}
    _atomic_write(_manifest_path(interval), lambda tmp: tmp.write_text(json.dumps(man, indent=0)))
