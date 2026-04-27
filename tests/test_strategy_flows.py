"""
LRExtremaStrategy flow tests.

Tests the key behavioural flows — warmup guard, exit conditions, the L2
pending-state fix, and order-update state management. Uses stub model/scaler
so tests are deterministic and fast without requiring real training data.
"""
import numpy as np
import pytest
from datetime import datetime

from trader.strategies.lr_extrema import LRExtremaStrategy
from trader.strategies.base import Direction, SignalType


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class _AlwaysMinModel:
    """Always predicts class 0 (local minimum) with 99% confidence."""
    classes_ = [0, 1]

    def predict_proba(self, X):
        return np.array([[0.99, 0.01]])


class _PassthroughScaler:
    def transform(self, X):
        return X


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PARAMS = {
    "warmup_bars":    5,
    "threshold":      0.70,
    "profit_pct":     4.0,
    "stop_pct":       2.0,
    "hold_bars":      5,
    "retrain_every":  50,
    "extrema_order":  2,
}


def _candle(close, *, open_=None, high=None, low=None, volume=1000):
    return {
        "open":      open_  if open_  is not None else close,
        "high":      high   if high   is not None else close,
        "low":       low    if low    is not None else close,
        "close":     close,
        "volume":    volume,
        "timestamp": datetime(2025, 6, 1, 10, 0),
    }


def _ready_strategy(*, entry_price: float | None = None) -> LRExtremaStrategy:
    """
    Return a strategy that has completed warmup and training.
    If entry_price is given, put the strategy in-position (filled state).
    """
    strat = LRExtremaStrategy("NSE:TEST", _PARAMS)
    strat._trained = True
    strat._model = _AlwaysMinModel()
    strat._scaler = _PassthroughScaler()
    # 25 candles satisfies the >= 20 requirement for feature computation
    strat._candles = [_candle(100.0) for _ in range(25)]
    if entry_price is not None:
        strat._entry_price = entry_price
        strat.position = Direction.BUY
    return strat


# ---------------------------------------------------------------------------
# Warmup guard
# ---------------------------------------------------------------------------

def test_no_signal_before_warmup_bars():
    """Strategy must not emit any signal until it has seen warmup_bars candles."""
    strat = LRExtremaStrategy("NSE:TEST", _PARAMS)  # warmup_bars=5

    signals = [strat.on_candle(_candle(100.0)) for _ in range(4)]

    assert all(s is None for s in signals)


# ---------------------------------------------------------------------------
# L2 fix — no exit while order is pending (filled state not yet confirmed)
# ---------------------------------------------------------------------------

def test_no_exit_while_order_pending():
    """
    When _entry_price is set but position is None (limit order placed, not
    yet filled), a price swing that would normally trigger an exit must NOT
    emit an EXIT signal and must NOT clear _entry_price.
    """
    strat = _ready_strategy()
    strat._entry_price = 100.0
    strat.position = None  # pending: order placed, not confirmed

    # Price moves +5% — exceeds profit_pct=4.0, would normally exit
    signal = strat.on_candle(_candle(105.0, high=106.0))

    assert signal is None
    assert strat._entry_price == 100.0  # guard must remain intact


# ---------------------------------------------------------------------------
# Exit conditions
# ---------------------------------------------------------------------------

def test_exit_on_profit_target():
    strat = _ready_strategy(entry_price=100.0)

    signal = strat.on_candle(_candle(104.5))  # +4.5% > profit_pct=4.0

    assert signal is not None
    assert signal.signal_type == SignalType.EXIT


def test_exit_on_stop_loss():
    strat = _ready_strategy(entry_price=100.0)

    signal = strat.on_candle(_candle(97.5))  # -2.5% < -stop_pct=-2.0

    assert signal is not None
    assert signal.signal_type == SignalType.EXIT


def test_exit_on_max_hold_bars():
    strat = _ready_strategy(entry_price=100.0)
    strat._held_bars = _PARAMS["hold_bars"] - 1  # one candle away from limit

    signal = strat.on_candle(_candle(100.0))  # flat price, hold_bars triggers

    assert signal is not None
    assert signal.signal_type == SignalType.EXIT


# ---------------------------------------------------------------------------
# Order update state management
# ---------------------------------------------------------------------------

def test_entry_guard_cleared_on_rejected_order():
    """A REJECTED entry order must clear _entry_price so the strategy can re-enter."""
    strat = _ready_strategy()
    strat._entry_price = 100.0
    strat.position = None

    strat.on_order_update({
        "status":      "REJECTED",
        "signal_type": SignalType.ENTRY,
        "direction":   "BUY",
    })

    assert strat._entry_price is None
    assert strat._held_bars == 0


def test_fill_sets_entry_price_from_actual_fill():
    """
    on_order_update with COMPLETE+ENTRY overrides _entry_price with the
    real fill price (not the original price_hint).
    """
    strat = _ready_strategy()
    strat._entry_price = 100.0  # price_hint set at signal time

    strat.on_order_update({
        "status":        "COMPLETE",
        "signal_type":   SignalType.ENTRY,
        "direction":     "BUY",
        "average_price": 100.35,  # actual fill price (slippage)
    })

    assert strat._entry_price == pytest.approx(100.35)
    assert strat.position == Direction.BUY


def test_no_new_entry_while_in_position():
    """Strategy must not emit an ENTRY signal when already holding a position."""
    strat = _ready_strategy(entry_price=100.0)  # in position

    # Price is flat — no exit trigger, no entry trigger
    signal = strat.on_candle(_candle(100.5))

    # Either None or an EXIT — never an ENTRY
    if signal is not None:
        assert signal.signal_type == SignalType.EXIT
