"""
MetaModel — binary P(trade wins) classifier for meta-labeling.

The secondary model in meta-labeling: given context features at a candidate entry
(MetaFeaturePipeline), predicts the probability that THIS trade hits its profit barrier
before its stop/time barrier. Unlike ExtremaModel (which returns a (p_min, p_max) pair),
this returns a single P(win).

Per-stock training sets are small (Stage 4 lesson), so models are shallow + regularized.
`logistic` is the conservative leakage canary (if even a linear meta-filter helps, the
signal is real); `xgboost` is the nonlinear option.

Config (nested `meta_label.model` block):
    type           : xgboost | logistic                 (default xgboost)
    # xgboost:
    max_depth        : tree depth                        (default 3)
    n_estimators     : number of trees                   (default 100)
    min_child_weight : min sum hessian per leaf (reg)    (default 5)
    reg_lambda       : L2 penalty                         (default 1.0)
    learning_rate    :                                    (default 0.1)
    random_state     :                                    (default 42)
"""

import numpy as np
from sklearn.preprocessing import StandardScaler


class MetaModel:
    def __init__(self, cfg: dict | None = None):
        cfg = cfg or {}
        self._type: str = str(cfg.get("type", "xgboost"))
        self._cfg = cfg
        self._model = None
        self._scaler: StandardScaler | None = None
        self._pos_label = 1  # the "win" class

    def _build(self):
        if self._type == "logistic":
            from sklearn.linear_model import LogisticRegression
            return LogisticRegression(
                max_iter=int(self._cfg.get("max_iter", 1000)),
                C=float(self._cfg.get("C", 1.0)),
                class_weight="balanced",
            )
        if self._type == "xgboost":
            from xgboost import XGBClassifier
            return XGBClassifier(
                max_depth=int(self._cfg.get("max_depth", 3)),
                n_estimators=int(self._cfg.get("n_estimators", 100)),
                min_child_weight=float(self._cfg.get("min_child_weight", 5)),
                reg_lambda=float(self._cfg.get("reg_lambda", 1.0)),
                learning_rate=float(self._cfg.get("learning_rate", 0.1)),
                random_state=int(self._cfg.get("random_state", 42)),
                n_jobs=1,
                eval_metric="logloss",
            )
        raise ValueError(f"Unknown meta model type {self._type!r}. Available: ['xgboost','logistic']")

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=int)
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        model = self._build()
        # xgboost handles imbalance via scale_pos_weight; set it from class counts.
        if self._type == "xgboost":
            n_pos = int((y == 1).sum()); n_neg = int((y == 0).sum())
            if n_pos > 0:
                model.set_params(scale_pos_weight=max(n_neg / n_pos, 1e-3))
        model.fit(X_scaled, y)
        self._scaler = scaler
        self._model = model

    @property
    def is_trained(self) -> bool:
        return self._model is not None

    def predict_proba(self, x: np.ndarray) -> float:
        """Return P(win) for a single feature vector."""
        x_scaled = self._scaler.transform(np.asarray(x, dtype=float).reshape(1, -1))
        classes = list(self._model.classes_)
        proba = self._model.predict_proba(x_scaled)[0]
        return float(proba[classes.index(1)]) if 1 in classes else 0.0
