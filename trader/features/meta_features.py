"""
MetaFeaturePipeline — context features for the meta-labeling filter (Plan: meta).

Deliberately DISJOINT from the primary ExtremaFeaturePipeline: re-using the primary's
6 scalars would just relearn the primary. These features describe the *context* of a
candidate entry so the meta-model can judge whether this particular firing is likely to
win: volatility regime, dip depth, oscillator state, mean-reversion vs trend, and the
primary's own confidence.

Unlike FeaturePipeline.compute(candles), compute() here also takes the primary's
prediction (p_min, p_max) for the current candle, so it is a standalone class (not a
FeaturePipeline subclass).

Config (nested `meta_label.features` block):
    vol_bars   : window for realized-volatility + autocorrelation   (default 20)
    rsi_period : RSI lookback                                       (default 14)
    depth_bars : recent-high window for drawdown_from_high          (default 50)
    include_primary_scores : add p_min, p_max, (p_min - threshold)  (default True)
"""

import numpy as np

from trader.features.indicators import rsi_series


class MetaFeaturePipeline:
    def __init__(self, cfg: dict | None = None):
        cfg = cfg or {}
        self._vol_bars: int = int(cfg.get("vol_bars", 20))
        self._rsi_period: int = int(cfg.get("rsi_period", 14))
        self._depth_bars: int = int(cfg.get("depth_bars", 50))
        self._include_primary: bool = bool(cfg.get("include_primary_scores", True))

    @property
    def min_history(self) -> int:
        # Need enough for returns/vol, RSI, and depth windows.
        return max(self._vol_bars + 1, self._rsi_period + 1, self._depth_bars)

    @property
    def feature_names(self) -> list[str]:
        names = [
            "realized_vol", "ret_autocorr1", "drawdown_from_high",
            "rsi", "ret_5", "ret_10",
        ]
        if self._include_primary:
            names += ["p_min", "p_max", "p_min_margin"]
        return names

    def compute(
        self, candles, p_min: float = 0.0, p_max: float = 0.0, threshold: float = 0.0
    ) -> "np.ndarray | None":
        candles = list(candles)
        if len(candles) < self.min_history:
            return None
        closes = [c["close"] for c in candles]
        close = closes[-1]

        # --- Realized volatility: std of last vol_bars % returns ---
        rets = [
            (closes[i] - closes[i - 1]) / closes[i - 1]
            for i in range(len(closes) - self._vol_bars, len(closes))
            if closes[i - 1] != 0
        ]
        realized_vol = float(np.std(rets)) if rets else 0.0

        # --- Lag-1 autocorrelation of returns (regime: mean-revert < 0, trend > 0) ---
        if len(rets) >= 3 and np.std(rets) > 0:
            a = np.array(rets[:-1]); b = np.array(rets[1:])
            denom = (np.std(a) * np.std(b))
            ret_autocorr1 = float(np.mean((a - a.mean()) * (b - b.mean())) / denom) if denom > 0 else 0.0
        else:
            ret_autocorr1 = 0.0

        # --- Dip depth: how far below the recent high ---
        n = min(self._depth_bars, len(closes))
        recent_high = max(closes[-n:])
        drawdown_from_high = (close - recent_high) / recent_high if recent_high > 0 else 0.0

        # --- RSI ---
        rsi_vals = rsi_series(closes, self._rsi_period)
        rsi = (rsi_vals[-1] / 100.0) if rsi_vals else 0.5  # scaled to [0,1]

        # --- Short-horizon momentum (scale-invariant % returns) ---
        ret_5 = (close - closes[-6]) / closes[-6] if len(closes) >= 6 and closes[-6] else 0.0
        ret_10 = (close - closes[-11]) / closes[-11] if len(closes) >= 11 and closes[-11] else 0.0

        feats = [realized_vol, ret_autocorr1, drawdown_from_high, rsi, ret_5, ret_10]
        if self._include_primary:
            feats += [float(p_min), float(p_max), float(p_min - threshold)]
        return np.array(feats, dtype=float)
