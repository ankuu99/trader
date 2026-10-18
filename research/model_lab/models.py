"""Lab model wrappers: pooled, fit on training rows only, 1-D score out (higher = more likely positive)."""
import warnings
from abc import ABC, abstractmethod

import numpy as np


def _check(y: np.ndarray) -> None:
    if len(np.unique(y)) < 2:
        raise ValueError("one-class training set")


class LabModel(ABC):
    name: str = "base"

    def __init__(self, **params):
        self.params = params

    @abstractmethod
    def fit(self, X: np.ndarray, y: np.ndarray, w: np.ndarray | None = None) -> None: ...

    @abstractmethod
    def predict(self, X: np.ndarray) -> np.ndarray: ...


class PooledLogistic(LabModel):
    name = "logistic"

    def fit(self, X, y, w=None):
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
        _check(y)
        X = np.asarray(X, dtype=np.float64)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            med = np.nanmedian(X, axis=0)
        self._med = np.where(np.isnan(med), 0.0, med)
        Xi = np.where(np.isnan(X), self._med, X)
        self._sc = StandardScaler().fit(Xi)
        self._clf = LogisticRegression(C=self.params.get("C", 1.0), max_iter=1000, class_weight="balanced")
        self._clf.fit(self._sc.transform(Xi), y, sample_weight=w)

    def predict(self, X):
        X = np.asarray(X, dtype=np.float64)
        Xi = np.where(np.isnan(X), self._med, X)
        return self._clf.predict_proba(self._sc.transform(Xi))[:, 1]


class PooledHGB(LabModel):
    name = "hgb"

    def fit(self, X, y, w=None):
        from sklearn.ensemble import HistGradientBoostingClassifier
        _check(y)
        self._clf = HistGradientBoostingClassifier(
            max_depth=self.params.get("max_depth", 3), learning_rate=0.05,
            max_iter=self.params.get("max_iter", 300), early_stopping=False,
            class_weight="balanced", random_state=self.params.get("seed", 7))
        self._clf.fit(np.asarray(X, dtype=np.float32), y, sample_weight=w)

    def predict(self, X):
        return self._clf.predict_proba(np.asarray(X, dtype=np.float32))[:, 1]


MODELS: dict[str, type[LabModel]] = {"logistic": PooledLogistic, "hgb": PooledHGB}


def make_model(name: str, **params) -> LabModel:
    if name not in MODELS:
        raise ValueError(f"unknown model {name!r}; have {sorted(MODELS)}")
    return MODELS[name](**params)
