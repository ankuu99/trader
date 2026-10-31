"""
LRExtremaStrategy flow tests.

Tests the key behavioural flows — warmup guard, exit conditions, the L2
pending-state fix, and order-update state management. Uses stub model/scaler
so tests are deterministic and fast without requiring real training data.
"""
import pytest
from datetime import datetime, time
from unittest.mock import patch, PropertyMock

from trader.strategies.lr_extrema import LRExtremaStrategy
from trader.strategies.base import Direction, SignalType


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class _AlwaysMinModel:
    """Stub ExtremaModel: always predicts P(local-min)=0.99, P(local-max)=0.01.
    Implements the Stage 2 ExtremaModel interface (predict_proba returns a
    (p_min, p_max) tuple; is_trained is always True)."""

    @property
    def is_trained(self) -> bool:
        return True

    def fit(self, X, y) -> None:  # pragma: no cover - stub never trained
        pass

    def predict_proba(self, x):
        return 0.99, 0.01


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
    strat._model = _AlwaysMinModel()
    # 25 candles satisfies the >= 20 requirement for feature computation
    strat._candles = [_candle(100.0) for _ in range(25)]
    if entry_price is not None:
        strat._entry_price = entry_price
        strat._fill_price = entry_price  # simulate confirmed fill
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

def test_exit_on_trailing_stop():
    """Trailing stop fires once profit floor is hit then price pulls back by trail_pct."""
    strat = _ready_strategy(entry_price=100.0)

    # Tick 1: +5% > profit_pct=4.0 — activates trailing, no exit yet
    signal1 = strat.on_tick({"last_price": 105.0})
    assert signal1 is None
    assert strat._trailing_active

    # Tick 2: drop > trail_pct=1.5% from peak 105 → 105 * 0.985 = 103.425
    signal2 = strat.on_tick({"last_price": 103.4})
    assert signal2 is not None
    assert signal2.signal_type == SignalType.EXIT


def test_exit_on_stop_loss():
    strat = _ready_strategy(entry_price=100.0)

    signal = strat.on_tick({"last_price": 97.5})  # -2.5% < -stop_pct=-2.0

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


def test_in_position_entry_is_stateless():
    """An in-position ENTRY signal is allowed (it is the scale-in add-on
    candidate — RiskManager decides whether to act on it), but emitting it must
    NEVER mutate position state: the entry anchor and staleness clock stay on
    the original entry."""
    strat = _ready_strategy(entry_price=100.0)  # in position
    held_before = strat._held_bars
    entry_before = strat._entry_price

    signal = strat.on_candle(_candle(100.5))

    if signal is not None and signal.signal_type == SignalType.ENTRY:
        # signal emitted stateless — nothing re-anchored
        assert strat._entry_price == entry_before
    # held_bars advanced by exactly the one candle processed
    assert strat._held_bars == held_before + 1
    assert strat.position == Direction.BUY


# ---------------------------------------------------------------------------
# Bug: SL cancel retrigger
# ---------------------------------------------------------------------------

def test_sl_retriggers_after_exit_order_cancelled():
    """
    When an EXIT order (stop-loss) is cancelled or rejected, the strategy must
    re-emit the EXIT signal on the next tick so the position can still be closed.

    Root cause: _reset_position_state() clears _entry_price at signal-emission
    time, so on_tick short-circuits on the next tick and the SL never fires again.
    """
    strat = _ready_strategy(entry_price=100.0)

    # Tick below stop-loss (-2.5% < -stop_pct=-2.0) → EXIT emitted, state reset
    signal1 = strat.on_tick({"last_price": 97.5})
    assert signal1 is not None
    assert signal1.signal_type == SignalType.EXIT

    # Simulate the EXIT order being cancelled (e.g. user cancels on Kite)
    strat.on_order_update({
        "status":      "CANCELLED",
        "signal_type": SignalType.EXIT,
        "direction":   "SELL",
    })

    # Price is still below stop-loss — SL must retrigger
    signal2 = strat.on_tick({"last_price": 97.5})
    assert signal2 is not None, "SL must retrigger after EXIT order is cancelled"
    assert signal2.signal_type == SignalType.EXIT


# ---------------------------------------------------------------------------
# Bug: exit signals bypass trading window
# ---------------------------------------------------------------------------

def test_no_exit_signal_outside_trading_window():
    """
    A candle-based exit (hold_bars timeout) must NOT emit a signal when the
    candle timestamp falls outside the configured trading window.

    The window is enforced via config.trading_start / config.trading_end.
    """
    strat = _ready_strategy(entry_price=100.0)
    strat._held_bars = _PARAMS["hold_bars"] - 1  # one away from hold_bars limit

    # Candle at 09:15 — before trading_start (09:30)
    early_candle = _candle(100.0)
    early_candle["timestamp"] = datetime(2025, 6, 1, 9, 15)

    with patch("trader.strategies.lr_extrema.config") as mock_cfg:
        mock_cfg.trading_start = time(9, 30)
        mock_cfg.trading_end   = time(15, 30)
        signal = strat.on_candle(early_candle)

    assert signal is None, "Hold-bars exit must not fire outside the trading window"
