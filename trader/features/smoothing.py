"""
CausalGaussianSmoother — noise-suppressed close series for feature pipelines
(`features.smoothing`, Bruni et al. 2026).

Gaussian smoothing of the close channel with the paper's acceleration-gated
right-edge extension, made strictly causal: the smoothed value at bar j is
computed from closes[..j] only, by extending the series W/2 bars past j
(constant or linear continuation, selected by the local acceleration of the
already-smoothed signal) and applying a centered Gaussian kernel at j. Because
each bar's value depends only on its past, it is computed once and cached by
timestamp — train and inference see the identical representation, which the
paper's ablation identifies as the thing that actually matters (train/test
representation mismatch degraded to raw-data performance).

This deliberately deviates from the paper's *training* procedure (they smooth
training segments with real future bars); centered smoothing here would put
future closes inside training features — leakage the live path can't reproduce.

Config (nested under `features:`):
    smoothing:
      enabled: true
      window: 21        # W — Gaussian kernel width in bars (σ = W/6)
      edge: accel       # accel | constant | linear (constant/linear force one mode)
      slope_bars: 10    # γ — regression window for the linear extension
      accel_lookback: 250  # trailing accelerations used to estimate a_low = μ − σ

Extension rule (paper §3.2.2): with a = second difference of the smoothed signal
at the edge and a_low = μ − σ of trailing accelerations, extend constant when
a >= 0 (don't inject upward bias) or a <= a_low (protective: don't extrapolate a
crash), else linear with the γ-bar regression slope.
"""

from collections import deque

import numpy as np

from trader.features.indicators import linreg_slope


def gaussian_kernel(window: int) -> np.ndarray:
    """Symmetric Gaussian weights of odd length `window`, σ = window/6, sum 1."""
    m = window // 2
    sigma = window / 6.0
    j = np.arange(-m, m + 1, dtype=float)
    w = np.exp(-(j ** 2) / (2 * sigma ** 2))
    return w / w.sum()


class CausalGaussianSmoother:
    def __init__(self, cfg: dict | None = None):
        cfg = cfg or {}
        window = int(cfg.get("window", 21))
        if window % 2 == 0:
            window += 1  # kernel must be symmetric around the current bar
        self._window = window
        self._half = window // 2
        self._kernel = gaussian_kernel(window)
        self._edge: str = str(cfg.get("edge", "accel"))
        self._slope_bars: int = int(cfg.get("slope_bars", 10))
        self._accels: deque = deque(maxlen=int(cfg.get("accel_lookback", 250)))
        # timestamp -> smoothed close; causal values never change once computed
        self._cache: dict = {}

    def series(self, candles: list[dict], k: int) -> list[float]:
        """Smoothed closes for the last `k` bars of `candles`, each value causal
        (computed from closes up to that bar only). Cache misses are computed in
        chronological order so the acceleration state stays consistent."""
        n = len(candles)
        k = min(k, n)
        out: list[float] = []
        for pos in range(n - k, n):
            ts = candles[pos]["timestamp"]
            val = self._cache.get(ts)
            if val is None:
                val = self._smooth_at(candles, pos)
                self._cache[ts] = val
            out.append(val)
        return out

    def _smooth_at(self, candles: list[dict], pos: int) -> float:
        closes = [c["close"] for c in candles[max(0, pos - self._half): pos + 1]]
        ext = self._extension(candles, pos)
        seg = np.asarray(closes + ext, dtype=float)
        kern = self._kernel[self._window - len(seg):]  # left-truncate early bars
        kern = kern / kern.sum()
        return float(np.dot(kern, seg))

    def _extension(self, candles: list[dict], pos: int) -> list[float]:
        last = float(candles[pos]["close"])
        mode = self._edge
        if mode == "accel":
            a = self._edge_accel(candles, pos)
            a_low = self._a_low()
            mode = "constant" if (a >= 0 or a <= a_low) else "linear"
        if mode == "linear":
            g = self._slope_bars
            tail = [c["close"] for c in candles[max(0, pos - g + 1): pos + 1]]
            slope = linreg_slope(tail) if len(tail) >= 2 else 0.0
            return [last + slope * i for i in range(1, self._half + 1)]
        return [last] * self._half

    def _edge_accel(self, candles: list[dict], pos: int) -> float:
        """Second difference of the smoothed signal just before `pos`, from the
        cached causal values. Falls back to 0 (=> constant extension) until three
        prior smoothed values exist."""
        prev = [self._cache.get(candles[pos - d]["timestamp"]) for d in (3, 2, 1)]
        if pos < 3 or any(v is None for v in prev):
            return 0.0
        a = prev[2] - 2 * prev[1] + prev[0]
        self._accels.append(a)
        return a

    def _a_low(self) -> float:
        if len(self._accels) < 20:
            return float("-inf")  # too little history to call an extreme tail
        arr = np.asarray(self._accels, dtype=float)
        return float(arr.mean() - arr.std())


def build_smoother(cfg: dict | None) -> "CausalGaussianSmoother | None":
    """Return a smoother when `features.smoothing.enabled`, else None."""
    sm = (cfg or {}).get("smoothing") or {}
    return CausalGaussianSmoother(sm) if sm.get("enabled", False) else None
