"""Lab model wrappers: pooled, fit on training rows only, 1-D score out (higher = more likely positive)."""
import warnings
from abc import ABC, abstractmethod

import numpy as np


def _check(y: np.ndarray) -> None:
    if len(np.unique(y)) < 2:
        raise ValueError("one-class training set")


class LabModel(ABC):
    name: str = "base"
    task: str = "classify"

    def __init__(self, **params):
        self.params = params

    @abstractmethod
    def fit(self, X: np.ndarray, y: np.ndarray, w: np.ndarray | None = None) -> None: ...

    @abstractmethod
    def predict(self, X: np.ndarray) -> np.ndarray: ...


class PooledLogistic(LabModel):
    name = "logistic"
    task = "classify"

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
    task = "classify"

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


class _Regressor(LabModel):
    """Continuous-target base: y is winsorised to the training [0.5, 99.5] percentiles before fitting."""
    task = "regress"

    def _winsorise(self, X, y, w):
        y = np.asarray(y, dtype=np.float64)
        ok = ~np.isnan(y)
        if not ok.all():
            X, y = np.asarray(X)[ok], y[ok]
            w = None if w is None else np.asarray(w)[ok]
        if len(y) < 100 or len(np.unique(y)) < 2:
            raise ValueError("degenerate training set")
        self._ylo, self._yhi = (float(v) for v in np.percentile(y, [0.5, 99.5]))
        return X, np.clip(y, self._ylo, self._yhi), w


class PooledRidge(_Regressor):
    name = "ridge"

    def fit(self, X, y, w=None):
        from sklearn.linear_model import Ridge
        from sklearn.preprocessing import StandardScaler
        X, y, w = self._winsorise(X, y, w)
        X = np.asarray(X, dtype=np.float64)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            med = np.nanmedian(X, axis=0)
        self._med = np.where(np.isnan(med), 0.0, med)
        Xi = np.where(np.isnan(X), self._med, X)
        self._sc = StandardScaler().fit(Xi)
        self._reg = Ridge(alpha=self.params.get("alpha", 1.0))
        self._reg.fit(self._sc.transform(Xi), y, sample_weight=w)

    def predict(self, X):
        X = np.asarray(X, dtype=np.float64)
        Xi = np.where(np.isnan(X), self._med, X)
        return self._reg.predict(self._sc.transform(Xi))


class PooledHGBReg(_Regressor):
    name = "hgb_reg"

    def _make(self, **kw):
        from sklearn.ensemble import HistGradientBoostingRegressor
        return HistGradientBoostingRegressor(
            max_depth=self.params.get("max_depth", 3), learning_rate=0.05,
            max_iter=self.params.get("max_iter", 300), early_stopping=False,
            random_state=self.params.get("seed", 7), **kw)

    def fit(self, X, y, w=None):
        X, y, w = self._winsorise(X, y, w)
        self._reg = self._make()
        self._reg.fit(np.asarray(X, dtype=np.float32), y, sample_weight=w)

    def predict(self, X):
        return self._reg.predict(np.asarray(X, dtype=np.float32))


class PooledHGBQuantile(PooledHGBReg):
    name = "hgb_q"

    def fit(self, X, y, w=None):
        X, y, w = self._winsorise(X, y, w)
        X = np.asarray(X, dtype=np.float32)
        qs = list(self.params.get("quantiles", [0.1, 0.5, 0.9]))
        self._q = {}
        for q in qs:
            m = self._make(loss="quantile", quantile=q)
            m.fit(X, y, sample_weight=w)
            self._q[f"q{round(q * 100):02d}"] = (q, m)
        self._mid = min(self._q, key=lambda k: abs(self._q[k][0] - 0.5))

    def predict(self, X):
        return self._q[self._mid][1].predict(np.asarray(X, dtype=np.float32))

    def predict_multi(self, X) -> dict[str, np.ndarray]:
        X = np.asarray(X, dtype=np.float32)
        return {k: m.predict(X) for k, (_, m) in self._q.items()}


MODELS: dict[str, type[LabModel]] = {"logistic": PooledLogistic, "hgb": PooledHGB, "ridge": PooledRidge,
                                     "hgb_reg": PooledHGBReg, "hgb_q": PooledHGBQuantile}


def make_model(name: str, **params) -> LabModel:
    if name not in MODELS:
        raise ValueError(f"unknown model {name!r}; have {sorted(MODELS)}")
    return MODELS[name](**params)
