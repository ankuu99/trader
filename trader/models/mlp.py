"""
MLPModel — multi-layer perceptron over the feature vector (Plan 5).

A nonlinear ExtremaModel for use with WindowFeaturePipeline: given the raw
normalized price window, the MLP learns candle-by-candle morphology that the
linear LogisticModel over scalar features cannot. Mirrors LogisticModel's
structure (own scaler, re-fit fresh each retrain) so it drops into the existing
train/predict loop unchanged.

L2 regularization (`alpha`) and a fixed `random_state` are first-class: per-stock
training sets are small, so regularization and determinism matter. No torch/TF
dependency — sklearn only.

Config (nested `model:` block, selected via `model.type: mlp`):
    hidden_layer_sizes : tuple/list of layer widths   (default [32, 16])
    alpha              : L2 penalty                    (default 1e-3)
    max_iter           : optimizer iterations          (default 300)
    random_state       : seed for reproducibility      (default 42)
"""

import numpy as np
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

from trader.models.base import ExtremaModel


class MLPModel(ExtremaModel):
    def __init__(self, cfg: dict | None = None):
        cfg = cfg or {}
        self._hidden = tuple(cfg.get("hidden_layer_sizes", [32, 16]))
        self._alpha: float = float(cfg.get("alpha", 1e-3))
        self._max_iter: int = int(cfg.get("max_iter", 300))
        self._random_state: int = int(cfg.get("random_state", 42))
        self._model: MLPClassifier | None = None
        self._scaler: StandardScaler | None = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        model = MLPClassifier(
            hidden_layer_sizes=self._hidden,
            alpha=self._alpha,
            max_iter=self._max_iter,
            random_state=self._random_state,
        )
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
