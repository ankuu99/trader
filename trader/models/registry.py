"""
Model factory — builds an ExtremaModel from the nested `model:` config block.

    model:
      type: logistic     # logistic (default) | knn | gbm | mlp (future)
      ...type-specific params...

kNN/GBM/MLP are intentionally not registered yet: on per-stock training data they
overfit (see todo_revamp.md Stage 4). They become viable once pooled cross-sectional
training lands.
"""

from trader.models.base import ExtremaModel
from trader.models.logistic import LogisticModel

_REGISTRY = {
    "logistic": LogisticModel,
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
