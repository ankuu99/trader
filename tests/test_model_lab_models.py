"""Model Lab L2a — regressors / quantile model (synthetic)."""
import numpy as np
import pytest

from research.model_lab import models


def _data(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, 4))
    y = 2 * X[:, 0] + rng.normal(0, 0.5, n)
    y[:5] = 1e6                                   # outliers
    return X, y


def _rank_corr(a, b):
    import pandas as pd
    return float(np.corrcoef(pd.Series(a).rank(), pd.Series(b).rank())[0, 1])


@pytest.mark.parametrize("name", ["ridge", "hgb_reg", "hgb_q"])
def test_regressors_fit_predict_and_winsorise(name):
    X, y = _data()
    m = models.make_model(name)
    assert m.task == "regress"
    m.fit(X, y)
    Xt, yt = _data(1000, seed=1)
    p = m.predict(Xt)
    assert np.isfinite(p).all()
    assert _rank_corr(p, 2 * Xt[:, 0]) > 0.8
    assert m._yhi < 1e5 and m._ylo < m._yhi            # outliers clipped (bounds from training y only)
    if name == "hgb_q":
        mm = m.predict_multi(Xt)
        assert set(mm) == {"q10", "q50", "q90"}
        ok = (mm["q10"] <= mm["q50"]) & (mm["q50"] <= mm["q90"])
        assert ok.mean() >= 0.95
        assert np.array_equal(p, mm["q50"])
    with pytest.raises(ValueError, match="degenerate"):
        models.make_model(name).fit(X, np.ones(len(X)))
    with pytest.raises(ValueError, match="degenerate"):
        models.make_model(name).fit(X[:50], y[:50])


def test_classifiers_keep_classify_task():
    assert models.MODELS["logistic"].task == "classify" and models.MODELS["hgb"].task == "classify"
