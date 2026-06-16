"""
Model factory — builds an ExtremaModel from the nested `model:` config block.

    model:
      type: logistic     # logistic (default) | mlp
      ...type-specific params...

`mlp` (Plan 5) is a nonlinear net intended for use with WindowFeaturePipeline —
it learns price-window morphology the linear logistic model cannot. On per-stock
data it is overfit-prone, so it carries L2 regularization; judge it on walk-forward.
kNN/GBM remain unregistered (overfit on per-stock data — see todo_revamp.md Stage 4).
"""

from trader.models.base import ExtremaModel
from trader.models.logistic import LogisticModel
from trader.models.mlp import MLPModel

_REGISTRY = {
    "logistic": LogisticModel,
    "mlp": MLPModel,
}


def build_model(cfg: dict | None) -> ExtremaModel:
    cfg = cfg or {}
    mtype = cfg.get("type", "logistic")
    cls = _REGISTRY.get(mtype)
    if cls is None:
        raise ValueError(
            f"Unknown model type {mtype!r}. Available: {sorted(_REGISTRY)}"
        )
    return cls(cfg)
