"""
Rule-based reference detector for the extrema lab.

A deliberately simple non-ML yardstick: RSI mapped to pseudo-probabilities so it
plugs into the same scores/metrics pipeline as the ML mechanisms. These are NOT
calibrated probabilities — 0.5 corresponds to RSI exactly at the band edge
(low for dips, high for peaks), 1.0 to RSI at its extreme. Evaluate it at its
own detection threshold (default 0.75), not the ML threshold.

If a dumb RSI rule matches or beats the trained model on synthetic data, that is
a loud finding about the model — which is the point of including it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from trader.features.indicators import rsi_series


def rsi_reference(candles: list[dict], period: int = 14, low: float = 30.0,
                  high: float = 70.0, warmup_bars: int = 200) -> pd.DataFrame:
    """Return scores df (timestamp, close, p_min, p_max) — same shape as the
    ML harness. NaN before warmup_bars for a fair comparison window.

    p_min ramp: rsi >= 2*low -> 0.0, rsi == low -> 0.5, rsi == 0 -> 1.0
    p_max ramp: rsi <= 2*high-100 -> 0.0, rsi == high -> 0.5, rsi == 100 -> 1.0
    """
    closes = [c["close"] for c in candles]
    rsi = rsi_series(closes, period)  # aligned: rsi[k] belongs to candle k+period

    rows = []
    for i, c in enumerate(candles):
        p_min, p_max = float("nan"), float("nan")
        k = i - period
        if i >= warmup_bars and k >= 0:
            r = rsi[k]
            p_min = min(max(1.0 - r / (2.0 * low), 0.0), 1.0)
            span = 2.0 * (100.0 - high)
            p_max = min(max((r - (2.0 * high - 100.0)) / span, 0.0), 1.0)
        rows.append({
            "timestamp": c["timestamp"],
            "close": c["close"],
            "p_min": p_min,
            "p_max": p_max,
        })
    return pd.DataFrame(rows)
