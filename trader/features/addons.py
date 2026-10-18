"""
Feature add-ons and lag stacking — shared, default-off wrappers around any FeaturePipeline.

Add-ons append extra columns AFTER the inner vector (positional entry gates on x[0], x[1], x[5]
are unaffected). `LagPipeline` appends the inner vector at t-1, t-2, ... Campaign arms register
one FeatureAddon subclass each in ADDONS.
"""

from abc import ABC, abstractmethod

import numpy as np

from trader.features.base import FeaturePipeline


class FeatureAddon(ABC):
    name: str = ""  # config key under `features:` and registry key

    def __init__(self, cfg: dict):
        self.cfg = cfg or {}

    @property
    @abstractmethod
    def feature_names(self) -> list[str]:
        """Column names this add-on appends."""

    @property
    @abstractmethod
    def min_history(self) -> int:
        """Candles needed before compute() is meaningful."""

    @abstractmethod
    def compute(self, candles: list[dict]) -> list[float]:
        """Values for the LAST candle. Must return len(feature_names) finite floats; return neutral
        values (0.0) rather than None when data is short or an input is missing."""


ADDONS: dict[str, type[FeatureAddon]] = {}  # empty here; worktree arms register their own


class AddonPipeline(FeaturePipeline):
    def __init__(self, inner: FeaturePipeline, addons: list[FeatureAddon]):
        self.inner = inner
        self.addons = list(addons)

    @property
    def feature_names(self) -> list[str]:
        names = list(self.inner.feature_names)
        for a in self.addons:
            names += list(a.feature_names)
        return names

    @property
    def min_history(self) -> int:
        return max([self.inner.min_history] + [a.min_history for a in self.addons])

    def compute(self, candles):
        candles = list(candles)
        if len(candles) < self.min_history:
            return None
        base = self.inner.compute(candles)
        if base is None:
            return None
        parts = [np.asarray(base, dtype=float)]
        for a in self.addons:
            parts.append(np.asarray(a.compute(candles), dtype=float))
        return np.concatenate(parts).astype(float)


class LagPipeline(FeaturePipeline):
    def __init__(self, inner: FeaturePipeline, lags: list[int]):
        self.inner = inner
        self.lags = sorted({int(k) for k in lags})
        if not self.lags or self.lags[0] < 1:
            raise ValueError(f"lags must be non-empty integers >= 1, got {lags!r}")

    @property
    def feature_names(self) -> list[str]:
        base = list(self.inner.feature_names)
        return base + [f"{n}_lag{k}" for k in self.lags for n in base]

    @property
    def min_history(self) -> int:
        return self.inner.min_history + max(self.lags)

    def compute(self, candles):
        candles = list(candles)
        if len(candles) < self.min_history:
            return None
        parts = [self.inner.compute(candles)]
        for k in self.lags:
            parts.append(self.inner.compute(candles[:-k]))
        if any(p is None for p in parts):
            return None
        return np.concatenate([np.asarray(p, dtype=float) for p in parts]).astype(float)
