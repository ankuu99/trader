"""Walk-forward runner: pooled training pool -> one model per fold -> streamed per-symbol scoring.

    .venv/bin/python -m research.model_lab.runner --run-id r1 --tf 15m --scheme expanding \
        --target t1z_min_k5 --model logistic [--top-n 100] [--n-groups 5] [--workers 8]

Run directory contract (read by score.py): meta.json, folds.parquet, scores/<SYM>.parquet.
Memory-bounded: pass-A frames are never kept for pass B (symbols are recomputed), the pool is capped.
"""
import argparse
import json
import shutil
import time
import zlib
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from research.model_lab import models as models_mod
from research.model_lab import paths, splits, store
from research.model_lab.source import SynthSource, build_xs_table, label_end_ts, symbol_frames

# Debug side channel: tests set this to [] and the runner appends one dict per fitted fold.
_last_fit_rows: list | None = None

_MODELS: dict = {}          # fold_id -> fitted model (set before pass B; worker initializer when workers > 1)


@dataclass
class RunSpec:
    run_id: str
    tf: str
    scheme: str
    target: str
    model: str = "logistic"
    model_params: dict = field(default_factory=dict)
    features: list[str] | None = None
    universe_top_n: int | None = 100
    n_groups: int | None = None
    max_train_rows: int = 2_000_000
    recency_half_life_days: float | None = None
    scheme_kw: dict = field(default_factory=dict)
    seed: int = 7
    workers: int = 1


def _seed_for(seed: int, symbol: str) -> int:
    return seed + zlib.crc32(symbol.encode())


def _range(args):
    source, symbol, tf = args
    b = source.bars(symbol, tf)
    if len(b) == 0:
        return symbol, None
    return symbol, (b["timestamp"].min(), b["timestamp"].max())


def _member_mask(timestamps: pd.Series, years_ok: set[int]) -> np.ndarray:
    return timestamps.dt.year.isin(list(years_ok)).to_numpy()


def _pass_a(args):
    source, symbol, tf, xs, target, feats, years_ok, cap, seed, task = args
    f, t = symbol_frames(source, symbol, tf, xs)
    le = label_end_ts(t, f["timestamp"], target)
    y = t[target].to_numpy(float)
    elig = _member_mask(f["timestamp"], years_ok) & ~np.isnan(y) & le.notna().to_numpy()
    idx = np.flatnonzero(elig)
    seen = int(len(idx))
    rng = np.random.default_rng(_seed_for(seed, symbol))
    if task == "regress":
        keep = np.sort((rng.choice(idx, cap, replace=False) if len(idx) > cap else idx).astype(np.int64))
    else:
        pos = idx[y[idx] == 1]
        neg = idx[y[idx] != 1]
        if len(pos) > cap // 2:
            pos = rng.choice(pos, cap // 2, replace=False)
        room = max(cap - len(pos), 0)
        if len(neg) > room:
            neg = rng.choice(neg, room, replace=False)
        keep = np.sort(np.concatenate([pos, neg]).astype(np.int64))
    return {"symbol": symbol, "seen": seen, "kept": int(len(keep)), "pos": int((y[keep] == 1).sum()),
            "X": f[feats].to_numpy(np.float32)[keep], "y": y[keep].astype(np.float32),
            "avail": f["avail_ts"].to_numpy("datetime64[ns]")[keep],
            "le": le.to_numpy("datetime64[ns]")[keep]}


def _init_models(models):
    global _MODELS
    _MODELS = models


def _pass_b(args):
    source, symbol, tf, xs, feats, years_ok, folds, n_groups, target = args
    f, _ = symbol_frames(source, symbol, tf, xs)
    member = _member_mask(f["timestamp"], years_ok)
    X = f[feats].to_numpy(np.float32)
    av = f["avail_ts"].to_numpy("datetime64[ns]")
    ts = f["timestamp"].to_numpy("datetime64[ns]")
    syms = np.array([symbol] * len(f))
    parts = []
    for fo in folds:
        m = _MODELS.get(fo.fold_id)
        if m is None:
            continue
        sel = splits.test_mask(fo, av, syms, n_groups) & member
        if sel.any():
            sc = m.predict(X[sel]).astype(np.float32)
            d = {"timestamp": ts[sel], "fold_id": np.full(int(sel.sum()), fo.fold_id, dtype=np.int32),
                 "score": sc}
            if m.task == "regress":
                d[f"pred_{target}"] = sc
                if hasattr(m, "predict_multi"):
                    for k, v in m.predict_multi(X[sel]).items():
                        d[f"pred_{target}_{k}"] = np.asarray(v).astype(np.float32)
            parts.append(pd.DataFrame(d))
    if not parts:
        return symbol, None
    return symbol, pd.concat(parts, ignore_index=True)


def _map(fn, jobs, workers, initializer=None, initargs=()):
    if workers > 1:
        with ProcessPoolExecutor(workers, initializer=initializer, initargs=initargs) as ex:
            yield from ex.map(fn, jobs)
    else:
        if initializer:
            initializer(*initargs)
        for j in jobs:
            yield fn(j)


def run(spec: RunSpec, source=None, overwrite: bool = False) -> Path:
    global _last_fit_rows
    t0 = time.time()
    if source is None:
        from research.model_lab.source import LabSource
        source = LabSource()
    run_dir = paths.RUNS_DIR / spec.run_id
    if run_dir.exists():
        if not overwrite:
            raise FileExistsError(f"{run_dir} exists — pick another run id or pass overwrite")
        shutil.rmtree(run_dir)
    tf = spec.tf

    # 1. symbols, PIT membership, data range, folds
    cand = source.symbols(tf)
    ranges = {}
    for sym, r in _map(_range, [(source, s, tf) for s in cand], 1):
        if r is not None:
            ranges[sym] = r
    years = list(range(min(r[0].year for r in ranges.values()), max(r[1].year for r in ranges.values()) + 1))
    member = source.membership(years, spec.universe_top_n, tf=spec.tf)
    sym_years = {s: {y for y in years if s in member[y]} for s in ranges}
    symbols = sorted(s for s in ranges if sym_years[s])
    if not symbols:
        raise RuntimeError("no symbols are universe members in any year")
    data_start = min(ranges[s][0] for s in symbols)
    data_end = max(ranges[s][1] for s in symbols) + pd.Timedelta(1, "ns")
    kw = dict(spec.scheme_kw)
    if spec.n_groups:
        kw["n_groups"] = spec.n_groups
    folds = splits.make_folds(spec.scheme, data_start, data_end, **kw)
    if not folds:
        raise RuntimeError("scheme produced no folds for this data range")
    paths.check_disk()
    run_dir.mkdir(parents=True, exist_ok=True)
    fdf = pd.DataFrame({
        "fold_id": np.array([f.fold_id for f in folds], dtype=np.int32),
        "scheme": [f.scheme for f in folds],
        "train_start": pd.to_datetime([f.train_start for f in folds]).astype("datetime64[ns]"),
        "train_end": pd.to_datetime([f.train_end for f in folds]).astype("datetime64[ns]"),
        "test_start": pd.to_datetime([f.test_start for f in folds]).astype("datetime64[ns]"),
        "test_end": pd.to_datetime([f.test_end for f in folds]).astype("datetime64[ns]"),
        "holdout_group": np.array([f.holdout_group for f in folds], dtype=np.int32)})
    store._atomic_write(run_dir / "folds.parquet", lambda p: fdf.to_parquet(p, compression="zstd", index=False))

    # 2. cross-sectional table
    xs = None
    if not (isinstance(source, SynthSource) and len(symbols) < 10):
        xs = build_xs_table(source, symbols, tf)
    xs_by = {s: g for s, g in xs.groupby("symbol")} if xs is not None and len(xs) else {}

    # feature list (from the first symbol's factor frame when not given)
    feats = spec.features
    if feats is None:
        f0, _ = symbol_frames(source, symbols[0], tf, xs_by.get(symbols[0]))
        feats = [c for c in f0.columns if c not in ("timestamp", "avail_ts")]

    # 3. pass A — training pool
    if spec.model not in models_mod.MODELS:
        raise ValueError(f"unknown model {spec.model!r}; have {sorted(models_mod.MODELS)}")
    task = models_mod.MODELS[spec.model].task
    cap = max(spec.max_train_rows // len(symbols), 2)
    jobs = [(source, s, tf, xs_by.get(s), spec.target, feats, sym_years[s], cap, spec.seed, task)
            for s in symbols]
    pools = [p for p in _map(_pass_a, jobs, spec.workers) if p["kept"] > 0]
    sampling = {"rows_seen": int(sum(p["seen"] for p in pools)), "rows_kept": int(sum(p["kept"] for p in pools)),
                "positives_kept": int(sum(p["pos"] for p in pools)), "cap_per_symbol": int(cap)}
    if not pools:
        raise RuntimeError("empty training pool")
    X = np.concatenate([p["X"] for p in pools])
    y = np.concatenate([p["y"] for p in pools])
    avail = np.concatenate([p["avail"] for p in pools])
    le = np.concatenate([p["le"] for p in pools])
    sym_arr = np.concatenate([np.full(len(p["y"]), p["symbol"], dtype=object) for p in pools])
    del pools
    if task == "classify":
        if not np.isin(np.unique(y), [0.0, 1.0]).all():
            raise ValueError(f"target {spec.target!r} is not binary — classifier models need a binary target")
    elif len(np.unique(y[~np.isnan(y)])) < 2:
        raise ValueError(f"target {spec.target!r} has fewer than 2 distinct values — nothing to regress")

    # 4. fit per fold
    fitted: dict[int, models_mod.LabModel] = {}
    fold_info = []
    if _last_fit_rows is not None:
        _last_fit_rows.clear()
    for fo in folds:
        m = splits.train_mask(fo, avail, le, sym_arr, tf, spec.n_groups)
        info = {"fold_id": fo.fold_id, "train_rows": int(m.sum()), "positives": int((y[m] == 1).sum()) if task == "classify" else None,
                "skipped": None}
        try:
            if not m.any():
                raise ValueError("empty training set")
            w = None
            if spec.recency_half_life_days:
                age = (fo.train_end.to_datetime64() - avail[m]) / np.timedelta64(1, "D")
                w = 0.5 ** (age / spec.recency_half_life_days)
            mp = {"seed": spec.seed, **spec.model_params}
            model = models_mod.make_model(spec.model, **mp)
            model.fit(X[m], y[m], w)
            fitted[fo.fold_id] = model
            if _last_fit_rows is not None:
                _last_fit_rows.append({"fold_id": fo.fold_id, "fold": fo, "n": int(m.sum()),
                                       "avail_max": avail[m].max(), "label_end_max": le[m].max(),
                                       "symbols": sym_arr[m].copy(), "avail": avail[m].copy()})
        except ValueError as e:
            info["skipped"] = str(e)
        fold_info.append(info)
    del X, y, avail, le, sym_arr

    # 5. pass B — scoring
    paths.check_disk()
    sdir = run_dir / "scores"
    sdir.mkdir(exist_ok=True)
    jobs = [(source, s, tf, xs_by.get(s), feats, sym_years[s], folds, spec.n_groups, spec.target) for s in symbols]
    n_scored = 0
    for sym, df in _map(_pass_b, jobs, spec.workers, _init_models, (fitted,)):
        if df is None:
            continue
        store._atomic_write(sdir / f"{paths.sym_file(sym)}.parquet",
                            lambda p, d=df: d.to_parquet(p, compression="zstd", index=False))
        n_scored += len(df)

    # 6. meta
    meta = {"run_id": spec.run_id, "tf": tf, "scheme": spec.scheme, "target": spec.target, "model": spec.model,
            "model_params": spec.model_params, "task": task, "features": feats, "universe_top_n": spec.universe_top_n,
            "symbols": symbols, "train_rows_per_fold": [i["train_rows"] for i in fold_info],
            "seed": spec.seed, "created": datetime.now().isoformat(timespec="seconds"),
            "elapsed_s": round(time.time() - t0, 1),
            "n_groups": spec.n_groups, "max_train_rows": spec.max_train_rows,
            "recency_half_life_days": spec.recency_half_life_days, "scheme_kw": spec.scheme_kw,
            "sampling": sampling, "folds": fold_info, "scores_rows": n_scored}
    if spec.scheme == "loyo":
        meta["diagnostic"] = True
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2, default=str))
    skipped = sum(1 for i in fold_info if i["skipped"])
    print(f"run {spec.run_id}: {len(folds)} folds ({skipped} skipped), {len(symbols)} symbols, "
          f"{n_scored} scored rows, {meta['elapsed_s']}s -> {run_dir}")
    return run_dir


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--tf", required=True)
    ap.add_argument("--scheme", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--model", default="logistic")
    ap.add_argument("--top-n", type=int, default=100)
    ap.add_argument("--n-groups", type=int)
    ap.add_argument("--max-train-rows", type=int, default=2_000_000)
    ap.add_argument("--half-life-days", type=float)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--features", nargs="*")
    ap.add_argument("--step", default="6M")
    ap.add_argument("--min-train", default="2Y")
    ap.add_argument("--anchors", nargs="*")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--overwrite", action="store_true")
    a = ap.parse_args(argv)
    kw = {"step": a.step, "min_train": a.min_train}
    if a.anchors:
        kw["anchors"] = a.anchors
    spec = RunSpec(run_id=a.run_id, tf=a.tf, scheme=a.scheme, target=a.target, model=a.model,
                   features=a.features, universe_top_n=a.top_n, n_groups=a.n_groups,
                   max_train_rows=a.max_train_rows, recency_half_life_days=a.half_life_days,
                   scheme_kw=kw, seed=a.seed, workers=a.workers)
    run(spec, overwrite=a.overwrite)


if __name__ == "__main__":
    main()
