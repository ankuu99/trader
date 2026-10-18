"""Reference scores for the Model Lab: coin, RSI, lowest-of-N turn rules (and top-side mirrors).

The production P(min)/P(max) replay lives in scripts/model_lab/prod_pmin.py (it is the only lab file
allowed to import trader.strategies) but writes the same file layout, so read_ref() serves it too.
"""
import argparse
import hashlib

import numpy as np
import pandas as pd

from research.model_lab import bars as bars_mod
from research.model_lab import factors, paths, store

REFS_MIN = ("coin", "rsi", "low10", "low20", "low50", "vol")
REFS_MAX = ("coin", "rsi_hi", "high10", "high20", "high50", "vol")
INDEX_SYMBOLS = ("NSE:NIFTY 50", "NSE:INDIA VIX")


def _rule(close: np.ndarray, n: int, kind: str) -> np.ndarray:
    c = pd.Series(close)
    prev = c.shift(1)
    ext = prev.rolling(n).min() if kind == "low" else prev.rolling(n).max()   # extreme of close[t-n .. t-1]
    turn = (c > prev) if kind == "low" else (c < prev)
    fire = (turn & (prev == ext)).astype("float64").to_numpy().copy()
    fire[:n] = np.nan
    return fire


def ref_scores(bars: pd.DataFrame, name: str, symbol: str, seed: int = 11) -> np.ndarray:
    n = len(bars)
    if name == "coin":
        key = int(hashlib.md5(symbol.encode()).hexdigest()[:8], 16)
        return np.random.default_rng([seed, key]).random(n)
    if name in ("rsi", "rsi_hi"):
        rsi = factors.own_factors(bars)["rsi_14"].to_numpy(float)
        return 100.0 - rsi if name == "rsi" else rsi
    if name == "vol":
        return factors.own_factors(bars)["rv_16"].to_numpy(float)
    for kind in ("low", "high"):
        if name.startswith(kind) and name[len(kind):].isdigit():
            return _rule(bars["close"].to_numpy(float), int(name[len(kind):]), kind)
    raise ValueError(f"unknown reference {name!r}")


def ref_path(tf: str, name: str, symbol: str):
    return paths.REFS_DIR / tf / name / f"{paths.sym_file(symbol)}.parquet"


def write_refs(tf: str, symbols: list[str], names: list[str], seed: int = 11) -> None:
    paths.check_disk()
    for sym in symbols:
        b = bars_mod.load(sym, tf)
        if len(b) == 0:
            continue
        for name in names:
            df = pd.DataFrame({"timestamp": b["timestamp"].astype("datetime64[ns]"),
                               "score": ref_scores(b, name, sym, seed).astype("float32")})
            store._atomic_write(ref_path(tf, name, sym), lambda t, d=df: d.to_parquet(
                t, engine="pyarrow", compression="zstd", index=False))


def read_ref(tf: str, name: str, symbol: str) -> pd.DataFrame | None:
    p = ref_path(tf, name, symbol)
    if not p.exists():
        return None
    return pd.read_parquet(p)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", required=True)
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--refs", nargs="*", default=None)
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args()
    syms = a.symbols or [s for s in store.list_symbols(bars_mod.SOURCE[a.tf]) if s not in INDEX_SYMBOLS]
    names = a.refs or list(dict.fromkeys(REFS_MIN + REFS_MAX))
    write_refs(a.tf, syms, names, a.seed)
    print(f"wrote {len(names)} refs x {len(syms)} symbols -> {paths.REFS_DIR / a.tf}")


if __name__ == "__main__":
    main()
