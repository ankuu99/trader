"""
Feature engineering layer — model-agnostic.

Extracted from LRExtremaStrategy (Stage 1 of the rearchitecture, see todo_revamp.md)
so any model family (LR, kNN, GBM, MLP) can consume the same features and so feature
math lives in one place.

  - base.py            : FeaturePipeline ABC
  - indicators.py      : pure technical-indicator functions (shared by features + gates)
  - extrema_features.py: ExtremaFeaturePipeline (the LRExtremaStrategy feature vector)
"""

from trader.features.base import FeaturePipeline
from trader.features.extrema_features import ExtremaFeaturePipeline

__all__ = ["FeaturePipeline", "ExtremaFeaturePipeline"]
