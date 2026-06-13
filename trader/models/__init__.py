"""
Model layer — swappable classifiers behind a uniform interface.

Extracted from LRExtremaStrategy (Stage 2 of the rearchitecture, see todo_revamp.md)
so any model family (LR today; kNN / GBM / MLP later) is a config choice, not a
strategy rewrite. The model owns its own preprocessing (e.g. the MinMaxScaler) —
features are model-agnostic, scaling is a model-fitting artifact.

  - base.py     : ExtremaModel ABC
  - logistic.py : LogisticModel (LogisticRegression + MinMaxScaler) — the default
  - registry.py : build_model(cfg) factory driven by `model.type`
"""

from trader.models.base import ExtremaModel
from trader.models.logistic import LogisticModel
from trader.models.registry import build_model

__all__ = ["ExtremaModel", "LogisticModel", "build_model"]
