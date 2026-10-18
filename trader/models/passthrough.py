"""PassthroughModel — returns the first two feature columns as (p_min, p_max).

Only meaningful with `features.type: rules` (RulesFeaturePipeline emits [entry_score,
top_score]). fit() is a no-op that marks the model trained.
"""

import numpy as np

from trader.models.base import ExtremaModel


class PassthroughModel(ExtremaModel):
    def __init__(self, cfg: dict | None = None):
        self._trained = False

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        self._trained = True

    def predict_proba(self, x: np.ndarray) -> tuple[float, float]:
        return float(x[0]), float(x[1])

    @property
    def is_trained(self) -> bool:
        return self._trained

    def feature_contributions(self, x, feature_names=None):
        return None
