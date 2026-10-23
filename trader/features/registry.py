"""
Feature-pipeline factory — builds a FeaturePipeline from the nested `features:`
config block, keyed by `features.type`.

    features:
      type: extrema   # extrema (default) | extrema_regime | swing | window
      ...type-specific params...

Default is `extrema` (the hand-engineered 6-scalar ExtremaFeaturePipeline) so
existing configs and the parity golden are unaffected. `window` selects the raw
multi-channel price window (WindowFeaturePipeline, Plan 5) for use with model.type: mlp.

Default-off wrappers (trader/features/addons.py), applied in this order and always APPENDED
after the base vector: `features.<addon>.enabled` for each registered add-on (ADDONS order),
then `features.lags: [1, 2, ...]` (the whole inner vector again at t-1, t-2, ...).
"""

from trader.features.addons import ADDONS, AddonPipeline, LagPipeline
from trader.features.base import FeaturePipeline
from trader.features.extrema_features import ExtremaFeaturePipeline
from trader.features.regime_features import ExtremaRegimeFeaturePipeline
from trader.features.swing_features import SwingFeaturePipeline
from trader.features.window_features import WindowFeaturePipeline

_REGISTRY = {
    "extrema": ExtremaFeaturePipeline,
    "extrema_regime": ExtremaRegimeFeaturePipeline,
    "swing": SwingFeaturePipeline,
    "window": WindowFeaturePipeline,
}


def build_feature_pipeline(cfg: dict | None) -> FeaturePipeline:
    cfg = cfg or {}
    ftype = cfg.get("type", "extrema")
    cls = _REGISTRY.get(ftype)
    if cls is None:
        raise ValueError(
            f"Unknown feature pipeline type {ftype!r}. Available: {sorted(_REGISTRY)}"
        )
    base = cls(cfg)
    enabled = [ADDONS[k]((cfg.get(k) or {})) for k in ADDONS if (cfg.get(k) or {}).get("enabled")]
    pipe = AddonPipeline(base, enabled) if enabled else base
    lags = cfg.get("lags") or []
    if lags:
        pipe = LagPipeline(pipe, [int(k) for k in lags])
    return pipe
