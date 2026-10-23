"""
SwingFeaturePipeline — swing-position features (`features.type: swing`).

Motivation (reviews/ather_minima_diagnosis_20260927.md): against 191 hand-labelled
ATHERENERG dips, every "where are we in the swing" feature ranks bars better on its
own (RSI 0.69, distance above the 20-bar low 0.68, 20-bar return 0.68, depth 0.65)
than the whole live 7-feature model (0.54), while the bar-shape features that
dominate the live fit (norm_price, short return slopes) sit at chance (~0.50). The
min-vs-max labels are trivially separated by "did this bar fall", so the logistic
learns bar direction instead of swing position. This pipeline drops the bar-shape
channel and describes only the swing:

    volume_ratio          current volume / rolling mean (kept — 0.61 alone)
    above_low_<N>         (close - min close over N bars) / min close, per N
    depth_<N>             (close - max close over N bars) / max close, per N (<= 0)
    ret_<N>               close / close[-N] - 1, per N
    rsi_<p>               SMA-RSI / 100

All scale-invariant. Config (nested under `features:`):
    swing:
      low_lookbacks:  [20, 50]
      high_lookbacks: [20, 50]
      return_bars:    [5, 20]
      rsi_period:     14
      include_norm_price: false   # opt back in for A/B only
    volume_ma_bars: 20
"""

import numpy as np

from trader.features.base import FeaturePipeline
from trader.features.indicators import rsi_series


class SwingFeaturePipeline(FeaturePipeline):
    def __init__(self, cfg: dict | None = None):
        cfg = cfg or {}
        self._volume_ma_bars: int = int(cfg.get("volume_ma_bars", 20))
        sw = cfg.get("swing") or {}
        self._low_lb: tuple[int, ...] = tuple(int(n) for n in sw.get("low_lookbacks", (20, 50)))
        self._high_lb: tuple[int, ...] = tuple(int(n) for n in sw.get("high_lookbacks", (20, 50)))
        self._ret_bars: tuple[int, ...] = tuple(int(n) for n in sw.get("return_bars", (5, 20)))
        self._rsi_period: int = int(sw.get("rsi_period", 14))
        self._include_norm_price: bool = bool(sw.get("include_norm_price", False))
        self._min_hist = max(
            (*self._low_lb, *self._high_lb, *(n + 1 for n in self._ret_bars),
             self._rsi_period + 1, self._volume_ma_bars)
        )

    @property
    def min_history(self) -> int:
        return self._min_hist

    @property
    def feature_names(self) -> list[str]:
        names = ["volume_ratio"]
        if self._include_norm_price:
            names.append("norm_price")
        names += [f"above_low_{n}" for n in self._low_lb]
        names += [f"depth_{n}" for n in self._high_lb]
        names += [f"ret_{n}" for n in self._ret_bars]
        names.append(f"rsi_{self._rsi_period}")
        return names

    def compute(self, candles: list[dict]) -> "np.ndarray | None":
        candles = list(candles)  # strategy passes its deque; we slice
        if len(candles) < self._min_hist:
            return None
        last = candles[-1]
        close = float(last["close"])
        if close <= 0:
            return None
        closes = [float(c["close"]) for c in candles]

        volumes = [float(c.get("volume", 0)) for c in candles[-self._volume_ma_bars:]]
        vol_mean = sum(volumes) / len(volumes)
        out = [float(last.get("volume", 0)) / vol_mean if vol_mean > 0 else 1.0]

        if self._include_norm_price:
            high, low = float(last["high"]), float(last["low"])
            out.append((close - low) / (high - low) if high != low else 0.5)

        for n in self._low_lb:
            lo = min(closes[-n:])
            out.append((close - lo) / lo if lo > 0 else 0.0)
        for n in self._high_lb:
            hi = max(closes[-n:])
            out.append((close - hi) / hi if hi > 0 else 0.0)
        for n in self._ret_bars:
            ref = closes[-n - 1]
            out.append(close / ref - 1.0 if ref > 0 else 0.0)

        rsi = rsi_series(closes[-(self._rsi_period + 1):], self._rsi_period)
        out.append((rsi[-1] if rsi else 50.0) / 100.0)
        return np.array(out, dtype=float)
