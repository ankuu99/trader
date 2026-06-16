"""
Feature-pipeline factory — builds a FeaturePipeline from the nested `features:`
config block, keyed by `features.type`.

    features:
      type: extrema   # extrema (default) | window
      ...type-specific params...

Default is `extrema` (the hand-engineered 6-scalar ExtremaFeaturePipeline) so
existing configs and the parity golden are unaffected. `window` selects the raw
multi-channel price window (WindowFeaturePipeline, Plan 5) for use with model.type: mlp.
"""

from trader.features.base import FeaturePipeline
from trader.features.extrema_features import ExtremaFeaturePipeline
from trader.features.window_features import WindowFeaturePipeline

_REGISTRY = {
    "extrema": ExtremaFeaturePipeline,
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
    return cls(cfg)
