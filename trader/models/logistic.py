"""
LogisticModel — LogisticRegression + MinMaxScaler.

The default ExtremaModel, moved verbatim out of LRExtremaStrategy._train and the
predict sites (Stage 2). Each fit() re-fits a fresh scaler and model on the latest
training window, matching the original retrain-from-scratch behaviour exactly.
The Stage 0 parity golden enforces byte-identical output.
"""

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import MinMaxScaler

from trader.models.base import ExtremaModel


class LogisticModel(ExtremaModel):
    def __init__(self, cfg: dict | None = None):
        cfg = cfg or {}
        # max_iter / solver were hard-coded in the original; expose them but default
        # to the original values so behaviour is unchanged.
        self._max_iter: int = int(cfg.get("max_iter", 1000))
        self._solver: str = str(cfg.get("solver", "lbfgs"))
        self._model: LogisticRegression | None = None
        self._scaler: MinMaxScaler | None = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        scaler = MinMaxScaler()
        X_scaled = scaler.fit_transform(X)
        model = LogisticRegression(max_iter=self._max_iter, solver=self._solver)
        model.fit(X_scaled, y)
        # Assign only after both succeed, so a failed retrain leaves prior state intact.
        self._scaler = scaler
        self._model = model

    @property
    def is_trained(self) -> bool:
        return self._model is not None

    def predict_proba(self, x: np.ndarray) -> tuple[float, float]:
        x_scaled = self._scaler.transform(x.reshape(1, -1))
        classes = list(self._model.classes_)
        proba = self._model.predict_proba(x_scaled)[0]
        p_min = proba[classes.index(0)] if 0 in classes else 0.0
        p_max = proba[classes.index(1)] if 1 in classes else 0.0
        return float(p_min), float(p_max)

    def feature_contributions(
        self, x: np.ndarray, feature_names: "list[str] | None" = None
    ) -> "list[tuple[str, float]] | None":
        # Binary LogisticRegression stores one coef row oriented toward the higher
        # class (1 = local-max / sell). The signed contribution to that log-odds is
        # coef[j] * x_scaled[j]; negating it gives the push toward BUY (class 0).
        if self._model is None or self._scaler is None:
            return None
        if len(getattr(self._model, "classes_", [])) < 2:
            return None
        x_scaled = self._scaler.transform(x.reshape(1, -1))[0]
        coef = self._model.coef_[0]
        contribs = [-float(c) * float(xs) for c, xs in zip(coef, x_scaled)]
        names = feature_names or [f"f{i}" for i in range(len(contribs))]
        return list(zip(names, contribs))
