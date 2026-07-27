"""
ExtremaFeaturePipeline — the LRExtremaStrategy feature vector.

Moved verbatim out of LRExtremaStrategy._compute_features (Stage 1). Behaviour is
byte-identical to the original; the Stage 0 parity golden enforces this.

Config (the nested `features:` block under strategies.lr_extrema):
    volume_ma_bars : rolling window for volume normalisation         (default 20)
    depth:
        enabled      : add drawdown_from_high as a 7th feature        (default false)
        lookback_bars: recent-high window for the drawdown feature    (default 50)
    macd:
        enabled      : add macd_hist_norm + macd_hist_slope features  (default false)
        fast/slow/signal_period/hist_lookback : MACD EMA params       (12/26/9/5)

Base vector (always): [volume_ratio, norm_price, slope3, slope5, slope10, slope20]
Slopes are over % returns (stationary); volume is a ratio to its rolling mean —
both scale-invariant across stocks and price levels.

Optional `smoothing:` block (see trader/features/smoothing.py): the return-slope
features are computed over causally-smoothed closes instead of raw ones.
norm_price and volume_ratio stay raw (they describe the bar itself, not the
trend), as do the optional depth/macd/curvature features (default-off; kept out
of the smoothing blast radius deliberately).
"""

import numpy as np

from trader.features.base import FeaturePipeline
from trader.features.indicators import ema_series, linreg_slope
from trader.features.smoothing import build_smoother

_BASE_NAMES = ["volume_ratio", "norm_price", "slope3", "slope5", "slope10", "slope20"]


class ExtremaFeaturePipeline(FeaturePipeline):
    def __init__(self, cfg: dict | None = None):
        cfg = cfg or {}
        self._volume_ma_bars: int = int(cfg.get("volume_ma_bars", 20))

        _depth = cfg.get("depth") or {}
        self._depth_enabled: bool = bool(_depth.get("enabled", False))
        self._depth_lookback: int = int(_depth.get("lookback_bars", 50))

        _macd = cfg.get("macd") or {}
        self._macd_enabled: bool = bool(_macd.get("enabled", False))
        self._macd_fast: int = int(_macd.get("fast", 12))
        self._macd_slow: int = int(_macd.get("slow", 26))
        self._macd_signal: int = int(_macd.get("signal_period", 9))
        self._macd_hist_lookback: int = int(_macd.get("hist_lookback", 5))

        _curv = cfg.get("curvature") or {}
        self._curv_enabled: bool = bool(_curv.get("enabled", False))
        self._curv_lookback: int = int(_curv.get("lookback_bars", 50))

        self._smoother = build_smoother(cfg)

    @property
    def min_history(self) -> int:
        return 21

    @property
    def feature_names(self) -> list[str]:
        names = list(_BASE_NAMES)
        if self._depth_enabled:
            names.append("drawdown_from_high")
        if self._macd_enabled:
            names.extend(["macd_hist_norm", "macd_hist_slope"])
        if self._curv_enabled:
            names.append("drawdown_curvature")
        return names

    def compute(self, candles: list[dict]) -> "np.ndarray | None":
        """Return feature vector for the last candle in *candles*, or None if not
        enough history."""
        if len(candles) < 21:
            return None
        last = candles[-1]
        closes = [c["close"] for c in candles]
        high, low, close = last["high"], last["low"], last["close"]

        norm_price = (close - low) / (high - low) if high != low else 0.5

        # Volume ratio: current candle volume vs rolling mean
        volumes = [c.get("volume", 0) for c in candles]
        vol_window = volumes[-self._volume_ma_bars:]
        vol_mean = sum(vol_window) / len(vol_window)
        volume_ratio = float(last.get("volume", 0)) / vol_mean if vol_mean > 0 else 1.0

        # % returns over last 21 closes → 20 return values
        slope_closes = (self._smoother.series(candles, 21)
                        if self._smoother else closes[-21:])
        returns = [
            (slope_closes[i] - slope_closes[i - 1]) / slope_closes[i - 1]
            for i in range(1, len(slope_closes))
        ]

        slope3 = linreg_slope(returns[-3:])
        slope5 = linreg_slope(returns[-5:])
        slope10 = linreg_slope(returns[-10:])
        slope20 = linreg_slope(returns[-20:])

        base = [volume_ratio, norm_price, slope3, slope5, slope10, slope20]

        # Depth-of-decline — how far has price fallen from its recent high?
        # Negative value; deeper = more negative. Scale-invariant (ratio).
        if self._depth_enabled:
            n = min(self._depth_lookback, len(closes))
            recent_high = max(closes[-n:])
            drawdown_from_high = (close - recent_high) / recent_high if recent_high > 0 else 0.0
            base.append(drawdown_from_high)

        # MACD features — macd_hist_norm and macd_hist_slope (scale-invariant momentum).
        # Falls back to 0.0/0.0 if not enough bars for the EMA to converge.
        if self._macd_enabled:
            min_bars = self._macd_slow + self._macd_signal + self._macd_hist_lookback
            if len(closes) >= min_bars:
                ema_fast = ema_series(closes, self._macd_fast)
                ema_slow = ema_series(closes, self._macd_slow)
                macd_vals = [ef - es for ef, es in zip(
                    ema_fast[self._macd_slow - self._macd_fast:], ema_slow
                )]
                sig_ema = ema_series(macd_vals, self._macd_signal)
                sig_offset = self._macd_signal - 1
                hist_series = [
                    macd_vals[sig_offset + i] - sig_ema[i]
                    for i in range(len(sig_ema))
                ]
                if len(hist_series) >= self._macd_hist_lookback:
                    hist_norm = hist_series[-1] / close if close != 0 else 0.0
                    lookback_slice = hist_series[-self._macd_hist_lookback:]
                    hist_slope = linreg_slope(
                        [h / close for h in lookback_slice]
                    ) if len(lookback_slice) >= 2 else 0.0
                    base.extend([hist_norm, hist_slope])
                else:
                    base.extend([0.0, 0.0])
            else:
                base.extend([0.0, 0.0])

        # Drawdown curvature — is the decline from the swing high decelerating?
        # Anchor t0 = argmax close within lookback, split the decline t0..now in half,
        # return slope(recent %-returns) - slope(older %-returns). Scale-invariant.
        if self._curv_enabled:
            base.append(self._drawdown_curvature(closes))

        return np.array(base, dtype=float)

    def _drawdown_curvature(self, closes: list[float]) -> float:
        n = min(self._curv_lookback, len(closes))
        window = closes[-n:]
        hi_idx = max(range(len(window)), key=lambda i: window[i])
        seg = window[hi_idx:]  # swing high (t0) .. now (tn), inclusive
        if len(seg) < 5:  # need >=4 returns to split into two halves of >=2
            return 0.0
        returns = [
            (seg[i] - seg[i - 1]) / seg[i - 1]
            for i in range(1, len(seg)) if seg[i - 1] != 0
        ]
        if len(returns) < 4:
            return 0.0
        half = len(returns) // 2
        return linreg_slope(returns[half:]) - linreg_slope(returns[:half])
