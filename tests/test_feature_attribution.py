"""
Feature attribution (#3 UI explainability): LogisticModel.feature_contributions
and LRExtremaStrategy.last_feature_drivers.

Contributions are signed pushes toward the BUY (local-min / class 0) decision.
A feature whose high value marks the SELL class must contribute negatively when
that feature is high, and the strategy must surface the largest-magnitude
drivers of its most recent prediction.
"""
import numpy as np

from trader.models.base import ExtremaModel
from trader.models.logistic import LogisticModel


def _trained_model():
    # Separable: feature 0 low -> BUY (class 0), high -> SELL (class 1).
    X = np.array([[0.0, 0.1], [0.1, 0.2], [0.2, 0.0],
                  [1.0, 0.1], [0.9, 0.2], [0.8, 0.0]])
    y = np.array([0, 0, 0, 1, 1, 1])
    m = LogisticModel()
    m.fit(X, y)
    return m


def test_contributions_orientation_toward_buy():
    m = _trained_model()
    # High feature-0 marks SELL, so it must push AGAINST buy (negative).
    high = dict(m.feature_contributions(np.array([0.95, 0.1]), ["f0", "f1"]))
    assert high["f0"] < 0


def test_contributions_none_until_trained():
    assert LogisticModel().feature_contributions(np.array([0.0, 0.0])) is None


def test_base_model_default_is_none():
    # A model that doesn't override gets the non-attributing default.
    class Dummy(ExtremaModel):
        def fit(self, X, y): ...
        def predict_proba(self, x): return (0.0, 0.0)
        @property
        def is_trained(self): return True

    assert Dummy().feature_contributions(np.array([1.0])) is None


def test_strategy_drivers_sorted_and_capped():
    from trader.strategies.lr_extrema import LRExtremaStrategy

    strat = LRExtremaStrategy("NSE:TEST", {"warmup_bars": 5})
    strat._model = _trained_model()
    strat._last_features = np.array([0.95, 0.1])

    drivers = strat.last_feature_drivers(top_n=1)
    assert len(drivers) == 1
    assert drivers[0]["kind"] == "contrib"
    # f0 dominates the prediction here.
    assert drivers[0]["name"] == strat.feature_names[0]


def test_strategy_drivers_empty_before_any_prediction():
    from trader.strategies.lr_extrema import LRExtremaStrategy

    strat = LRExtremaStrategy("NSE:TEST", {"warmup_bars": 5})
    assert strat.last_feature_drivers() == []


def test_score_current_none_until_trained():
    from trader.strategies.lr_extrema import LRExtremaStrategy

    strat = LRExtremaStrategy("NSE:TEST", {"warmup_bars": 5})
    assert strat.score_current() is None


def test_score_current_ignores_pending_entry_freeze():
    """score_current must reflect the model on the current buffer regardless of a
    stuck phantom-entry state (the warm-up freeze that flatlined the sparkline)."""
    import numpy as np
    from trader.strategies.lr_extrema import LRExtremaStrategy

    strat = LRExtremaStrategy("NSE:TEST", {"warmup_bars": 5})
    strat._model = _trained_model()

    captured = {}

    class _Pipe:
        feature_names = ["f0", "f1"]
        def compute(self, candles):
            return captured["x"]

    strat._features = _Pipe()
    # Simulate the frozen phantom-entry state that breaks _last_p_min.
    strat._pos.entry_price = 100.0
    strat._last_p_min = 0.97  # stale frozen cache

    captured["x"] = np.array([0.1, 0.1])   # low f0 -> buy-ish
    low = strat.score_current()
    captured["x"] = np.array([0.95, 0.1])  # high f0 -> sell-ish
    high = strat.score_current()

    assert low is not None and high is not None
    assert low[0] != high[0]               # tracks features, not the frozen cache
