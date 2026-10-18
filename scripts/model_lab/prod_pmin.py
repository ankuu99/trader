"""Production LR-Extrema P(min)/P(max) replayed on the Model Lab's bars (the reference every lab model must beat).

    .venv/bin/python scripts/model_lab/prod_pmin.py --tf 15m [--symbols NSE:X ...] [--params global|per-stock] [--workers N]

The ONLY lab file allowed to import trader.strategies. score_current() is pure and position-independent (it is
what the backtest engine's model_scores sink records) and retraining is not gated by position state, so no
order fills are simulated; returned signals are ignored. Writes refs/<tf>/prod_pmin (score=p_min, p_max) and
refs/<tf>/prod_pmax (score=p_max) in the same layout research.model_lab.references.read_ref() reads.
"""
import argparse
import hashlib
import json
import logging
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("KITE_API_KEY", "lab")
os.environ.setdefault("KITE_API_SECRET", "lab")

import numpy as np
import pandas as pd

from research.model_lab import bars as bars_mod
from research.model_lab import paths, references, store

_TF_TO_CFG = {"15m": "15minute", "4h": "4hour", "dayagg": "day"}


def replay_symbol(bars: pd.DataFrame, symbol: str, params: dict) -> pd.DataFrame:
    """Feed every bar through a fresh LRExtremaStrategy; record score_current() after each. NaN until trained."""
    from trader.strategies.lr_extrema import LRExtremaStrategy
    logging.getLogger("trader").setLevel(logging.WARNING)
    strat = LRExtremaStrategy(symbol, dict(params))
    n = len(bars)
    pmin = np.full(n, np.nan); pmax = np.full(n, np.nan)
    ts = pd.to_datetime(bars["timestamp"]).dt.to_pydatetime()
    o, h, l, c, v = (bars[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume"))
    for i in range(n):
        strat.on_candle({"timestamp": ts[i], "open": o[i], "high": h[i], "low": l[i], "close": c[i],
                         "volume": v[i]})
        s = strat.score_current()
        if s is not None:
            pmin[i], pmax[i] = s
    return pd.DataFrame({"timestamp": bars["timestamp"].astype("datetime64[ns]").to_numpy(),
                         "score": pmin.astype("float32"), "p_max": pmax.astype("float32")})


# Model-side keys of production's standard aggregated-TF blocks (scripts/calibrate_stock.py::TF_TEMPLATES,
# mirrored by the day/4hour blocks in config.yaml). Exits are irrelevant to P(min) and left global.
_TF_TEMPLATE = {
    "4h": {"warmup_bars": 100, "lookback_bars": 400, "extrema_order": 5, "retrain_every": 2},
    "dayagg": {"warmup_bars": 100, "lookback_bars": 400, "extrema_order": 5, "retrain_every": 1},
    "day": {"warmup_bars": 100, "lookback_bars": 400, "extrema_order": 5, "retrain_every": 1},
}


def _resolve_params(symbol: str, tf: str, mode: str) -> tuple[dict, str]:
    from trader.core.config import config
    if mode == "per-stock" and _TF_TO_CFG.get(tf) == config.strategy_timeframe(symbol):
        return config.get_strategy_params(symbol, "lr_extrema"), "per-stock"
    if mode == "template" and tf in _TF_TEMPLATE:
        return {**config.strategy_config("lr_extrema"), **_TF_TEMPLATE[tf]}, "template"
    return config.strategy_config("lr_extrema"), "global"


def _work(args) -> tuple[str, str, str, float, bool]:
    symbol, tf, mode, paths_root = args
    logging.disable(logging.WARNING - 1)
    t0 = time.time()
    b = bars_mod.load(symbol, tf)
    if len(b) == 0:
        return symbol, "none", "", 0.0, False
    params, used = _resolve_params(symbol, tf, mode)
    chash = hashlib.sha1(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()
    df = replay_symbol(b, symbol, params)
    for name, frame in (("prod_pmin", df), ("prod_pmax", df[["timestamp"]].assign(score=df["p_max"]))):
        p = references.ref_path(tf, name, symbol)
        store._atomic_write(p, lambda t, d=frame: d.to_parquet(t, engine="pyarrow", compression="zstd", index=False))
    return symbol, used, chash, time.time() - t0, True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", required=True)
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--params", choices=("global", "per-stock", "template"), default="global",
                    help="template = production's standard 4hour/day block (4h, dayagg, day); else global")
    ap.add_argument("--workers", type=int, default=1)
    a = ap.parse_args()
    paths.check_disk()
    syms = a.symbols or [s for s in store.list_symbols(bars_mod.SOURCE[a.tf]) if s not in references.INDEX_SYMBOLS]
    jobs = [(s, a.tf, a.params, str(paths.REFS_DIR)) for s in syms]
    if a.workers > 1:
        with ProcessPoolExecutor(a.workers) as ex:
            res = list(ex.map(_work, jobs))
    else:
        res = [_work(j) for j in jobs]
    meta = {"tf": a.tf, "params_arg": a.params,
            "symbols": {s: {"params": used, "config_sha1": h, "seconds": round(sec, 2)}
                        for s, used, h, sec, ok in res if ok}}
    d = paths.REFS_DIR / a.tf
    for name in ("prod_pmin", "prod_pmax"):
        (d / name).mkdir(parents=True, exist_ok=True)
        (d / name / "meta.json").write_text(json.dumps(meta, indent=1))
    for s, used, h, sec, ok in res:
        print(f"{s}: {used if ok else 'no bars'} {sec:.1f}s")


if __name__ == "__main__":
    main()
