"""Data sources for the lab runner (real lab data or synthetic), PIT membership, label end times.

LabSource reads the L0 store / bars / universe; SynthSource generates stocks from synth.py for tests.
`symbol_frames` is the one place factors + targets are produced for a symbol, so the runner's two
passes (training pool, scoring) see identical rows.
"""
from datetime import date
import zlib

import numpy as np
import pandas as pd

from research.model_lab import bars as bars_mod
from research.model_lab import factors as fx
from research.model_lab import synth, targets as tg

NIFTY, VIX = "NSE:NIFTY 50", "NSE:INDIA VIX"
XS_COLS = ["xs_n", "xs_rank_ret16", "xs_rank_ret64", "xs_breadth_100"]


class LabSource:
    """Real lab data: L0 bars store + liquidity universe."""

    def symbols(self, tf: str = "15m") -> list[str]:
        from research.model_lab import store
        return [s for s in store.list_symbols(bars_mod.SOURCE[tf]) if s not in (NIFTY, VIX)]

    def bars(self, symbol: str, tf: str) -> pd.DataFrame:
        return bars_mod.load(symbol, tf)

    def nifty(self, tf: str) -> pd.DataFrame | None:
        try:
            b = bars_mod.load(NIFTY, tf)
        except Exception:
            return None
        return b if len(b) else None

    def vix_day(self) -> pd.DataFrame | None:
        from research.model_lab import store
        try:
            v = store.read_bars(VIX, "day")
        except Exception:
            return None
        return v if len(v) else None

    def membership(self, years: list[int], top_n: int | None, tf: str = "15m") -> dict[int, set[str]]:
        if top_n is None:
            from research.model_lab import store
            out: dict[int, set[str]] = {y: set() for y in years}
            for s in self.symbols(tf):
                cov = store.coverage(s, bars_mod.SOURCE[tf])
                if cov is None:
                    continue
                for y in years:
                    if cov[0].year <= y <= cov[1].year:
                        out[y].add(s)
            return out
        from research.model_lab import universe
        panel = universe._load_panel()
        return {y: set(universe.liquid_universe(date(y, 1, 1), top_n, panel)) for y in years}


class SynthSource:
    """Synthetic stocks for tests. `plant="ret_4"` adds factor `plant_signal` = target t1w_min_w4 + N(0, 0.3)."""

    def __init__(self, n_symbols: int, n_sessions: int, seed: int, plant: str | None = None,
                 start: str = "2020-01-06"):
        self.n_symbols, self.n_sessions, self.seed, self.plant, self.start = n_symbols, n_sessions, seed, plant, start
        self._syms = [f"NSE:SYN{i}" for i in range(n_symbols)]

    def symbols(self, tf: str = "15m") -> list[str]:
        return list(self._syms)

    def _src(self, seed: int, tf: str) -> pd.DataFrame:
        if bars_mod.SOURCE[tf] == "15minute":
            raw = synth.synthetic_15m(self.n_sessions, seed, start=self.start)
        else:
            raw = synth.synthetic_day(self.n_sessions, seed, start=self.start)
        return raw

    def bars(self, symbol: str, tf: str) -> pd.DataFrame:
        i = self._syms.index(symbol)
        return bars_mod.derive(self._src(self.seed * 1000 + i + 1, tf), tf)

    def nifty(self, tf: str) -> pd.DataFrame | None:
        return bars_mod.derive(self._src(self.seed * 1000 + 999, tf), tf)

    def vix_day(self) -> pd.DataFrame | None:
        d = synth.synthetic_day(self.n_sessions + 400, self.seed * 1000 + 998, start="2019-01-01")
        return d

    def membership(self, years: list[int], top_n: int | None, tf: str = "15m") -> dict[int, set[str]]:
        return {y: set(self._syms) for y in years}

    def postprocess(self, symbol: str, factors: pd.DataFrame, targets: pd.DataFrame):
        if self.plant:
            rng = np.random.default_rng(self.seed + zlib.crc32(symbol.encode()))
            tgt = targets["t1w_min_w4"].to_numpy(float)
            factors = factors.copy()
            factors["plant_signal"] = tgt + rng.normal(0.0, 0.3, len(tgt))
        return factors, targets


def symbol_frames(source, symbol: str, tf: str, xs_table: pd.DataFrame | None = None):
    """(factors, targets), row-aligned with the symbol's bars."""
    b = source.bars(symbol, tf)
    higher = {htf: source.bars(symbol, htf) for htf in fx.HIGHER_TF[tf]}
    f = fx.compute_factors(b, tf, nifty=source.nifty(tf), vix_day=source.vix_day(), higher=higher)
    t = tg.build_targets(b, tf)
    sub = None
    if xs_table is not None and len(xs_table):
        sub = xs_table[xs_table["symbol"] == symbol] if "symbol" in xs_table.columns else xs_table
    if sub is not None and len(sub):
        sub = sub[["timestamp"] + XS_COLS].drop_duplicates("timestamp")
        f = f.merge(sub, on="timestamp", how="left")
    else:
        for c in XS_COLS:
            f[c] = np.nan
    post = getattr(source, "postprocess", None)
    if post is not None:
        f, t = post(symbol, f, t)
    return f, t


def build_xs_table(source, symbols: list[str], tf: str) -> pd.DataFrame:
    inputs = {}
    for s in symbols:
        b = source.bars(s, tf)
        if len(b) == 0:
            continue
        o = fx.own_factors(b)
        inputs[s] = pd.DataFrame({"timestamp": b["timestamp"].values, "ret_16": o["ret_16"].values,
                                  "ret_64": o["ret_64"].values, "close": b["close"].values})
    if not inputs:
        return pd.DataFrame(columns=["symbol", "timestamp"] + XS_COLS)
    res = fx.cross_section(inputs)
    parts = []
    for s, x in res.items():
        d = x[XS_COLS].copy()
        d.insert(0, "timestamp", inputs[s]["timestamp"].values)
        d.insert(0, "symbol", s)
        parts.append(d)
    return pd.concat(parts, ignore_index=True)


def label_end_ts(targets: pd.DataFrame, timestamps: pd.Series, col: str) -> pd.Series:
    """Timestamp at which the label of each row is fully resolved (NaT = undefined)."""
    ts = pd.Series(pd.to_datetime(timestamps.to_numpy()), index=range(len(timestamps)))
    L = tg.lookahead(col)
    if L is not None:
        return ts.shift(-L)
    if col.startswith("t1z_"):
        k = col.rsplit("_k", 1)[1]
        eb = targets[f"t1z_endbars_k{k}"].to_numpy(float)
    elif col.startswith("t3_"):
        k = col.rsplit("_k", 1)[1]
        eb = targets[f"t3_endbars_k{k}"].to_numpy(float)
    else:
        raise ValueError(f"no label-end rule for target {col!r}")
    n = len(ts)
    pos = np.arange(n) + np.where(np.isnan(eb), 0, eb).astype(np.int64)
    ok = ~np.isnan(eb) & (pos < n)
    vals = ts.to_numpy()
    out = np.full(n, np.datetime64("NaT"), dtype="datetime64[ns]")
    out[ok] = vals[pos[ok]]
    return pd.Series(out)
