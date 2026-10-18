"""
RulesFeaturePipeline (`features.type: rules`) — deterministic no-ML baselines.

Emits [entry_score, top_score] in [0, 1]; pair with `model.type: passthrough` so the
strategy's thresholds, veto, pattern-top, exits and risk all run unchanged.

    features:
      type: rules
      rules:
        kind: rsi_bounce_ema | lowest_turn | ou
        ...kind params (rsi_period, rsi_max, rsi_min_top, ema_period | lowest_of | window)
"""

import numpy as np

from trader.features.base import FeaturePipeline
from trader.features.indicators import ema_series, rsi_series
from trader.features.ou import ou_score

_KINDS = ("rsi_bounce_ema", "lowest_turn", "ou")


class RulesFeaturePipeline(FeaturePipeline):
    def __init__(self, cfg: dict | None = None):
        r = (cfg or {}).get("rules") or {}
        self._kind: str = r.get("kind", "lowest_turn")
        if self._kind not in _KINDS:
            raise ValueError(f"Unknown rules kind {self._kind!r}. Available: {list(_KINDS)}")
        self._rsi_period = int(r.get("rsi_period", 14))
        self._rsi_max = float(r.get("rsi_max", 35))
        self._rsi_min_top = float(r.get("rsi_min_top", 70))
        self._ema_period = int(r.get("ema_period", 50))
        self._lowest_of = int(r.get("lowest_of", 20))
        self._window = int(r.get("window", 60))

    @property
    def feature_names(self) -> list[str]:
        return ["entry_score", "top_score"]

    @property
    def min_history(self) -> int:
        if self._kind == "rsi_bounce_ema":
            return max(self._rsi_period + 1, self._ema_period) + 1
        if self._kind == "lowest_turn":
            return self._lowest_of + 2
        return self._window + 1

    def compute(self, candles):
        candles = list(candles)
        if len(candles) < self.min_history:
            return None
        closes = [float(c["close"]) for c in candles]
        close, prev = closes[-1], closes[-2]
        if self._kind == "rsi_bounce_ema":
            rsi = rsi_series(closes, self._rsi_period)[-1]
            ema = ema_series(closes, self._ema_period)[-1]
            entry = 1.0 if (rsi < self._rsi_max and close > prev and close > ema) else 0.0
            top = 1.0 if (rsi > self._rsi_min_top and close < prev) else 0.0
        elif self._kind == "lowest_turn":
            win = closes[-self._lowest_of - 1:-1]
            entry = 1.0 if (prev == min(win) and close > prev) else 0.0
            top = 1.0 if (prev == max(win) and close < prev) else 0.0
        else:
            s, _ = ou_score(closes, self._window)
            entry = float(np.clip(-s / 3.0, 0.0, 1.0))
            top = float(np.clip(s / 3.0, 0.0, 1.0))
        return np.array([entry, top], dtype=float)
