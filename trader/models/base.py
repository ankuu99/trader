"""
ExtremaModel interface — binary classifier over extrema features.

The model is trained on labelled local extrema (class 0 = local minimum / buy
candidate, class 1 = local maximum / sell candidate) and predicts, for a single
feature vector, the pair (P(local-min), P(local-max)).

Contract:
  - fit(X, y): X is (n_samples, n_features); y holds class labels 0 and 1.
  - predict_proba(x): x is a single 1-D feature vector; returns (p_min, p_max).
    A class absent from the training labels yields probability 0.0 for that class.
  - is_trained: False until fit() has succeeded at least once.

The model owns any preprocessing it needs (scaling, etc.) — callers pass raw
feature vectors from the FeaturePipeline.
"""

from abc import ABC, abstractmethod

import numpy as np


class ExtremaModel(ABC):
    @abstractmethod
    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        """Train (or retrain) on labelled feature rows."""

    @abstractmethod
    def predict_proba(self, x: np.ndarray) -> tuple[float, float]:
        """Return (p_min, p_max) for a single feature vector."""

    @property
    @abstractmethod
    def is_trained(self) -> bool:
        """True once the model has been successfully fit at least once."""

    def feature_contributions(
        self, x: np.ndarray, feature_names: "list[str] | None" = None
    ) -> "list[tuple[str, float]] | None":
        """Per-feature signed contribution toward the BUY (local-min / class 0)
        prediction for a single feature vector. Positive pushes toward BUY.

        Returns None when the model cannot attribute its output linearly (e.g.
        MLP) — callers fall back to showing raw feature values. The default is
        None; linear models override.
        """
        return None
