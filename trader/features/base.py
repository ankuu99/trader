"""
FeaturePipeline interface — model-agnostic feature computation.

A pipeline turns a list of candles into a single feature vector for the *last*
candle (or None if there isn't enough history). Models (Stage 2) consume the
vector; they never compute features themselves.
"""

from abc import ABC, abstractmethod

import numpy as np


class FeaturePipeline(ABC):
    """Base class for all feature pipelines."""

    #: Stable, introspectable feature ordering — index i names column i of compute().
    feature_names: list[str] = []

    @property
    @abstractmethod
    def min_history(self) -> int:
        """Minimum number of candles required before compute() returns a vector."""

    @abstractmethod
    def compute(self, candles: list[dict]) -> "np.ndarray | None":
        """Return the feature vector for the last candle in *candles*, or None if
        there is insufficient history."""
