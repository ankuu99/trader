"""
GBDTModel — small gradient-boosted trees (`model.type: gbdt`).

Registered for lab benchmarking (Stage 4 of the beat-the-benchmark plan).
Deliberately shallow/regularised: per-stock training windows hold only tens of
clean samples, so anything deeper memorises them. Deterministic (fixed
random_state) so benchmark caching is safe.

Config (nested `model:` block):
    max_depth:      tree depth                       (default 3)
    max_iter:       boosting rounds                  (default 100)
    learning_rate:                                    (default 0.1)
    min_samples_leaf:                                 (default 5)
"""

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

from trader.models.base import ExtremaModel


class GBDTModel(ExtremaModel):
    def __init__(self, cfg: dict | None = None):
        cfg = cfg or {}
        self._max_depth = int(cfg.get("max_depth", 3))
        self._max_iter = int(cfg.get("max_iter", 100))
        self._learning_rate = float(cfg.get("learning_rate", 0.1))
        self._min_samples_leaf = int(cfg.get("min_samples_leaf", 5))
        self._model: HistGradientBoostingClassifier | None = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        model = HistGradientBoostingClassifier(
            max_depth=self._max_depth,
            max_iter=self._max_iter,
            learning_rate=self._learning_rate,
            min_samples_leaf=self._min_samples_leaf,
            random_state=42,
        )
        model.fit(X, y)
        self._model = model

    @property
    def is_trained(self) -> bool:
        return self._model is not None

    def predict_proba(self, x: np.ndarray) -> tuple[float, float]:
        classes = list(self._model.classes_)
        proba = self._model.predict_proba(x.reshape(1, -1))[0]
        p_min = proba[classes.index(0)] if 0 in classes else 0.0
        p_max = proba[classes.index(1)] if 1 in classes else 0.0
        return float(p_min), float(p_max)

    def feature_contributions(self, x, feature_names=None):
        # Non-linear model — no per-prediction linear attribution; mirror MLP's
        # fallback (None -> UI shows raw feature values).
        return None
