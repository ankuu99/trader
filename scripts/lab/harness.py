"""
Walk-forward detection harness for the extrema lab.

Runs the production labeler → feature-pipeline → model loop over a candle list
exactly the way live/backtest does (same warmup, retrain cadence, lookback deque,
train-row construction as LRExtremaStrategy._train / ui._run_signal_probe), but
with NO strategy instance, NO position state, NO exits — pure detection.

Additionally captures a RetrainSnapshot at every model fit: which candles
(GLOBAL indices into the input list) the labeler fed the model as dip/peak
training samples. This powers the lab's "how did it decide during training" view.
"""

from __future__ import annotations

import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from trader.core.config import flatten_strategy_params
from trader.features.labels import MIN_SAMPLES_PER_CLASS, build_labeler
from trader.features.registry import build_feature_pipeline
from trader.models.registry import build_model


@dataclass
class RetrainSnapshot:
    retrain_no: int
    at_bar: int                 # global candle index at which the fit happened
    window_start: int           # global index of buffer[0] at fit time
    sample_indices: list[int]   # GLOBAL candle indices used as training samples
    sample_classes: list[int]   # 0 = min/dip, 1 = max/peak, 2 = neutral
    n_min: int = 0
    n_max: int = 0
    # (name, signed push toward BUY) for the linear model at a probe point; None for MLP
    feature_contribs: list[tuple[str, float]] | None = None


@dataclass
class HarnessResult:
    scores: pd.DataFrame        # timestamp, close, p_min, p_max (NaN pre-warmup)
    retrains: list[RetrainSnapshot] = field(default_factory=list)
    params: dict = field(default_factory=dict)
    feature_names: list[str] = field(default_factory=list)


def run_ml_harness(candles: list[dict], params: dict) -> HarnessResult:
    """Walk-forward over `candles` (list of dicts with timestamp/o/h/l/c/volume).

    `params` is a (possibly nested) lr_extrema-style param dict; relevant keys:
    warmup_bars, lookback_bars, retrain_every, extrema_order, forward_label,
    labels, features, model.
    """
    flat = flatten_strategy_params(params)
    warmup_bars = int(flat.get("warmup_bars", 200))
    lookback_bars = int(flat.get("lookback_bars", 600))
    retrain_every = int(flat.get("retrain_every", 50))

    labeler = build_labeler("LAB", flat)
    features = build_feature_pipeline(flat.get("features", {}))
    model = build_model(flat.get("model"))

    buf: deque = deque(maxlen=lookback_bars)
    since_train = 0
    retrains: list[RetrainSnapshot] = []
    rows_out: list[dict] = []

    for i, candle in enumerate(candles):
        buf.append(candle)
        since_train += 1

        p_min, p_max = float("nan"), float("nan")
        if len(buf) >= warmup_bars:
            if not model.is_trained or since_train >= retrain_every:
                snap = list(buf)
                window_start = i - len(snap) + 1
                indices, classes = labeler.label(snap)
                train_rows, train_labels, kept_local = [], [], []
                for idx, cls in zip(indices, classes):
                    feat = features.compute(snap[: idx + 1])
                    if feat is not None:
                        train_rows.append(feat)
                        train_labels.append(cls)
                        kept_local.append(idx)
                if len(train_rows) >= MIN_SAMPLES_PER_CLASS * 2:
                    model.fit(np.array(train_rows, dtype=float),
                              np.array(train_labels, dtype=int))
                    x_now = features.compute(snap)
                    contribs = (model.feature_contributions(x_now, list(features.feature_names))
                                if x_now is not None else None)
                    retrains.append(RetrainSnapshot(
                        retrain_no=len(retrains),
                        at_bar=i,
                        window_start=window_start,
                        sample_indices=[window_start + k for k in kept_local],
                        sample_classes=train_labels,
                        n_min=train_labels.count(0),
                        n_max=train_labels.count(1),
                        feature_contribs=contribs,
                    ))
                since_train = 0

            if model.is_trained:
                x = features.compute(list(buf))
                if x is not None:
                    p_min, p_max = model.predict_proba(x)

        rows_out.append({
            "timestamp": candle["timestamp"],
            "close": candle["close"],
            "p_min": p_min,
            "p_max": p_max,
        })

    return HarnessResult(
        scores=pd.DataFrame(rows_out),
        retrains=retrains,
        params=dict(params),
        feature_names=list(features.feature_names),
    )


MECHANISMS = ("logistic", "mlp", "gbdt", "rsi_rule")


def run_mechanism(mechanism: str, candles: list[dict], params: dict,
                  rule_params: dict | None = None) -> HarnessResult:
    """Dispatch one of the lab's mechanisms; all return the same HarnessResult shape."""
    if mechanism == "logistic":
        p = dict(params)
        p["model"] = {"type": "logistic"}
        return run_ml_harness(candles, p)
    if mechanism == "mlp":
        p = dict(params)
        p["model"] = {"type": "mlp", **(params.get("mlp_model") or {})}
        return run_ml_harness(candles, p)
    if mechanism == "gbdt":
        p = dict(params)
        p["model"] = {"type": "gbdt"}
        return run_ml_harness(candles, p)
    if mechanism == "rsi_rule":
        from scripts.lab.rules import rsi_reference
        rp = rule_params or {}
        scores = rsi_reference(
            candles,
            period=int(rp.get("period", 14)),
            low=float(rp.get("low", 30.0)),
            high=float(rp.get("high", 70.0)),
            warmup_bars=int(flatten_strategy_params(params).get("warmup_bars", 200)),
        )
        return HarnessResult(scores=scores, retrains=[], params=dict(rp), feature_names=[])
    raise ValueError(f"unknown mechanism {mechanism!r} (choose from {MECHANISMS})")


if __name__ == "__main__":
    # CLI smoke: python scripts/lab/harness.py [scenario] — runs logistic on it.
    import time

    from scripts.lab.generator import load_scenario

    scenario = sys.argv[1] if len(sys.argv) > 1 else "s1_clean_sine"
    df, meta = load_scenario(scenario)
    candles = df.to_dict("records")
    params = {
        "warmup_bars": 300, "lookback_bars": 1200, "retrain_every": 25,
        "extrema_order": 10, "model": {"type": "logistic"},
    }
    t0 = time.time()
    res = run_ml_harness(candles, params)
    dt = time.time() - t0
    s = res.scores
    trained_from = s["p_min"].first_valid_index()
    assert trained_from is not None and trained_from <= 350, trained_from
    assert s["p_min"].iloc[trained_from:].notna().mean() > 0.95
    assert len(res.retrains) > 0
    for snap in res.retrains:
        assert all(snap.window_start <= gi <= snap.at_bar for gi in snap.sample_indices)
    n_cross = int(((s["p_min"] >= 0.9) & (s["p_min"].shift(1) < 0.9)).sum())
    print(f"{scenario}: {len(s)} bars in {dt:.1f}s | retrains={len(res.retrains)} | "
          f"first score at bar {trained_from} | p_min>=0.9 crossings={n_cross} | "
          f"p_min mean={s['p_min'].mean():.3f} max={s['p_min'].max():.3f}")
