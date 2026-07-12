"""
ExtremaRegimeFeaturePipeline — the 6-scalar extrema vector plus multi-horizon
regime context (`features.type: extrema_regime`).

Appends [er_h, vr_h, tanh(t_h/10)] per horizon (default 100/400/1600 bars) to
the base vector so the model can distinguish "dip in an uptrend" from "falling
knife" and "sideways chop" directly, instead of relying on rolling-window
recency for regime adaptation.

Config (nested under `features:`):
    regime:
      horizons: [100, 400, 1600]
Everything else is inherited from ExtremaFeaturePipeline.
"""

import numpy as np

from trader.features.extrema_features import ExtremaFeaturePipeline
from trader.features.regime import (DEFAULT_HORIZONS, regime_feature_names,
                                    regime_vector_at)


class ExtremaRegimeFeaturePipeline(ExtremaFeaturePipeline):
    def __init__(self, cfg: dict | None = None):
        super().__init__(cfg)
        _rg = (cfg or {}).get("regime") or {}
        self._horizons: tuple[int, ...] = tuple(
            int(h) for h in _rg.get("horizons", DEFAULT_HORIZONS))

    @property
    def feature_names(self) -> list[str]:
        return super().feature_names + regime_feature_names(self._horizons)

    def compute(self, candles: list[dict]) -> "np.ndarray | None":
        base = super().compute(candles)
        if base is None:
            return None
        closes = [c["close"] for c in candles]
        return np.concatenate([base, np.asarray(regime_vector_at(closes, self._horizons))])
