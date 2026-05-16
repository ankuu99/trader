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


class _AlwaysMaxModel:
    """Always predicts class 1 (local maximum) with high confidence."""
    classes_ = [0, 1]

    def predict_proba(self, X):
        return np.array([[0.10, 0.90]])  # p_max=0.90 >= sell_threshold=0.65, p_min=0.10 < threshold=0.70


class _BelowThresholdModel:
    """Predicts p_min below the entry threshold — model is not confident."""
    classes_ = [0, 1]

    def predict_proba(self, X):
        return np.array([[0.50, 0.50]])  # p_min=0.50 < threshold=0.70


class _OnlyMinClassModel:
    """Training produced only class 0 (all extrema were minima)."""
    classes_ = [0]

    def predict_proba(self, X):
        return np.array([[1.0]])


class _OnlyMaxClassModel:
    """Training produced only class 1 (all extrema were maxima)."""
    classes_ = [1]

    def predict_proba(self, X):
        return np.array([[1.0]])


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


def _candle(close, *, open_=None, high=None, low=None, volume=1000, ts=None):
    return {
        "open":      open_  if open_  is not None else close,
        "high":      high   if high   is not None else close,
        "low":       low    if low    is not None else close,
        "close":     close,
        "volume":    volume,
        "timestamp": ts if ts is not None else datetime(2025, 6, 1, 10, 0),
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
    strat._candles = list([_candle(100.0) for _ in range(25)])
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

def test_exit_on_stop_loss_via_tick():
    """Hard stop fires in on_tick when price drops below entry * (1 - stop_pct)."""
    strat = _ready_strategy(entry_price=100.0)

    signal = strat.on_tick({"last_price": 97.5})  # -2.5% < -stop_pct=-2.0

    assert signal is not None
    assert signal.signal_type == SignalType.EXIT


def test_trailing_stop_activates_and_exits_via_tick():
    """Trailing stop activates once profit_pct floor is hit, then exits on drawdown."""
    strat = _ready_strategy(entry_price=100.0)

    # Step 1: price rises to activate trailing (profit_pct=4.0)
    strat.on_tick({"last_price": 105.0})  # +5% → trailing activates, peak=105.0
    assert strat._trailing_active

    # Step 2: price drops trail_pct=1.5% from peak → exit
    # 105.0 * (1 - 0.015) = 103.425; use 103.0 to be clearly below
    signal = strat.on_tick({"last_price": 103.0})

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


# ---------------------------------------------------------------------------
# Entry filter flows
# ---------------------------------------------------------------------------

def test_entry_emitted_when_model_confident_and_no_gates():
    """ENTRY signal fires when p_min >= threshold, p_max < veto, and no filter gates."""
    strat = _ready_strategy()  # flat, no entry gates set

    signal = strat.on_candle(_candle(100.0))

    assert signal is not None
    assert signal.signal_type == SignalType.ENTRY
    assert signal.stop_loss_hint is not None
    assert strat.last_filter_block is None


def test_filter_block_reset_at_start_of_each_candle():
    """last_filter_block is cleared to None at the start of every candle."""
    strat = _ready_strategy()
    strat.last_filter_block = "stale reason from last candle"

    strat.on_candle(_candle(100.0))  # emits entry, which clears last_filter_block

    assert strat.last_filter_block is None


def test_volume_gate_blocks_entry_and_sets_filter_block():
    """entry_min_volume_ratio gate: low-volume candle sets last_filter_block, no ENTRY emitted."""
    params = {**_PARAMS, "entry_min_volume_ratio": 0.8}
    strat = LRExtremaStrategy("NSE:TEST", params)
    strat._trained = True
    strat._model = _AlwaysMinModel()
    strat._scaler = _PassthroughScaler()
    # 25 base candles at volume=1000; new candle at volume=400 → ratio ≈ 0.42 < 0.8
    strat._candles = list([_candle(100.0, volume=1000) for _ in range(25)])

    signal = strat.on_candle(_candle(100.0, volume=400))

    assert signal is None
    assert strat.last_filter_block is not None
    assert "vol_ratio" in strat.last_filter_block


def test_below_threshold_no_signal_no_filter_block():
    """When p_min < threshold the model simply isn't confident — no signal and no
    filter_block (a filter_block implies the model WOULD have entered but was gated)."""
    strat = _ready_strategy()
    strat._model = _BelowThresholdModel()  # p_min=0.50 < threshold=0.70

    signal = strat.on_candle(_candle(100.0))

    assert signal is None
    assert strat.last_filter_block is None


def test_norm_price_gate_blocks_entry_and_sets_filter_block():
    """entry_min_norm_price gate: candle that closes at its low (norm_price=0) is blocked."""
    params = {**_PARAMS, "entry_min_norm_price": 0.3}
    strat = LRExtremaStrategy("NSE:TEST", params)
    strat._trained = True
    strat._model = _AlwaysMinModel()
    strat._scaler = _PassthroughScaler()
    strat._candles = list([_candle(100.0) for _ in range(25)])

    # close == low → norm_price = 0.0 < 0.3
    signal = strat.on_candle(_candle(100.0, low=100.0, high=105.0))

    assert signal is None
    assert strat.last_filter_block is not None
    assert "norm_price" in strat.last_filter_block


def test_prior_decline_gate_blocks_entry_and_sets_filter_block():
    """entry_require_prior_decline gate: flat candles produce slope20=0 which is not negative."""
    params = {**_PARAMS, "entry_require_prior_decline": True}
    strat = LRExtremaStrategy("NSE:TEST", params)
    strat._trained = True
    strat._model = _AlwaysMinModel()
    strat._scaler = _PassthroughScaler()
    # All closes identical → returns all zero → slope20 = 0.0 >= 0 → blocked
    strat._candles = list([_candle(100.0) for _ in range(25)])

    signal = strat.on_candle(_candle(100.0))

    assert signal is None
    assert strat.last_filter_block is not None
    assert "slope20" in strat.last_filter_block


def test_multiple_gates_all_appear_in_filter_block():
    """When multiple gates fail, every reason is included in last_filter_block."""
    params = {**_PARAMS, "entry_min_volume_ratio": 0.8, "entry_min_norm_price": 0.3}
    strat = LRExtremaStrategy("NSE:TEST", params)
    strat._trained = True
    strat._model = _AlwaysMinModel()
    strat._scaler = _PassthroughScaler()
    strat._candles = list([_candle(100.0, volume=1000) for _ in range(25)])

    # Low volume (ratio ≈ 0.42 < 0.8) AND close at low (norm_price=0.0 < 0.3)
    signal = strat.on_candle(_candle(100.0, volume=400, low=100.0, high=105.0))

    assert signal is None
    assert "vol_ratio" in strat.last_filter_block
    assert "norm_price" in strat.last_filter_block


def test_features_insufficient_candles_no_signal():
    """When the candle buffer has fewer than 21 candles, _compute_features returns None
    and the strategy silently skips both the exit check and the entry prediction."""
    strat = _ready_strategy()
    # Override with only 10 candles — warmup (5) passes but features need 21
    strat._candles = list([_candle(100.0) for _ in range(10)])

    signal = strat.on_candle(_candle(100.0))

    assert signal is None
    assert strat.last_filter_block is None


def test_single_class_min_only_model_no_entry_due_to_veto():
    """A model trained on only local minima (classes_=[0]) has no class 1.
    p_max defaults to 1.0 (defensive) which fails the veto gate — no entry."""
    strat = _ready_strategy()
    strat._model = _OnlyMinClassModel()  # classes_=[0], p_max defaults to 1.0

    signal = strat.on_candle(_candle(100.0))

    # veto: p_max=1.0 >= veto_threshold=0.50 → entry blocked
    assert signal is None
    assert strat.last_filter_block is None  # veto is not a filter_block (model threshold)


def test_single_class_max_only_model_no_entry():
    """A model trained on only local maxima (classes_=[1]) has no class 0.
    p_min defaults to 0.0 which never meets the threshold — no entry, no filter_block."""
    strat = _ready_strategy()
    strat._model = _OnlyMaxClassModel()  # classes_=[1], p_min defaults to 0.0

    signal = strat.on_candle(_candle(100.0))

    assert signal is None
    assert strat.last_filter_block is None


# ---------------------------------------------------------------------------
# Trading window gate
# ---------------------------------------------------------------------------

def test_entry_blocked_outside_trading_window():
    """No ENTRY signal is emitted when the candle timestamp is outside the trading window."""
    strat = _ready_strategy()  # default window 09:30–15:30 (from config)

    signal = strat.on_candle(_candle(100.0, ts=datetime(2025, 6, 1, 8, 0)))  # 08:00

    assert signal is None


def test_hold_bars_exit_suppressed_outside_trading_window():
    """In release_branch, the trading window gates ALL signals (including hold-bars exits).
    Exits fire on the next in-window candle, not immediately when outside the window."""
    strat = _ready_strategy(entry_price=100.0)
    strat._held_bars = _PARAMS["hold_bars"] - 1  # one candle from limit

    signal = strat.on_candle(_candle(100.0, ts=datetime(2025, 6, 1, 8, 0)))  # 08:00, outside window

    # Release gates all signals outside the window — exit fires on next in-window candle
    assert signal is None


# ---------------------------------------------------------------------------
# Pattern-top exit
# ---------------------------------------------------------------------------

def _in_position_strategy(entry_price: float, held_bars: int) -> LRExtremaStrategy:
    """Strategy in position with AlwaysMaxModel (p_max=0.90 >= sell_threshold=0.65)."""
    strat = LRExtremaStrategy("NSE:TEST", _PARAMS)
    strat._trained = True
    strat._model = _AlwaysMaxModel()
    strat._scaler = _PassthroughScaler()
    strat._candles = list([_candle(100.0) for _ in range(25)])
    strat._entry_price = entry_price
    strat._fill_price = entry_price
    strat.position = Direction.BUY
    strat._held_bars = held_bars
    return strat


def test_pattern_top_exit_fires_when_all_conditions_met():
    """Pattern-top exit fires when: in position, held_bars >= min_hold_before_exit (3),
    gain >= sell_min_pct (2%), and P(max) >= sell_threshold (0.65)."""
    # _held_bars=2 → increments to 3 = min_hold_before_exit; gain=3% >= sell_min_pct=2%
    strat = _in_position_strategy(entry_price=100.0, held_bars=2)

    signal = strat.on_candle(_candle(103.0))

    assert signal is not None
    assert signal.signal_type == SignalType.EXIT
    assert signal.exit_reason == "PATTERN_TOP"


def test_pattern_top_exit_blocked_when_gain_below_sell_min_pct():
    """Pattern-top exit must NOT fire when gain is below sell_min_pct (2%) — stop_pct
    handles those underwater/flat exits."""
    strat = _in_position_strategy(entry_price=100.0, held_bars=2)

    signal = strat.on_candle(_candle(100.5))  # only +0.5% < sell_min_pct=2%

    assert signal is None or signal.signal_type != SignalType.EXIT or signal.exit_reason != "PATTERN_TOP"


def test_pattern_top_exit_blocked_when_held_bars_below_minimum():
    """Pattern-top exit must NOT fire in the first few bars — prevents an immediate
    U-turn right after entry."""
    # _held_bars=0 → increments to 1 < min_hold_before_exit=3
    strat = _in_position_strategy(entry_price=100.0, held_bars=0)

    signal = strat.on_candle(_candle(103.0))  # gain ok, but too early

    assert signal is None or signal.exit_reason != "PATTERN_TOP"


def test_pattern_top_exit_blocked_when_p_max_below_sell_threshold():
    """Pattern-top exit must NOT fire when the model is not confident a top is forming."""
    strat = _ready_strategy(entry_price=100.0)  # AlwaysMinModel: p_max=0.01 < 0.65
    strat._held_bars = 2

    signal = strat.on_candle(_candle(103.0))

    assert signal is None or signal.exit_reason != "PATTERN_TOP"


# ---------------------------------------------------------------------------
# on_tick edge cases
# ---------------------------------------------------------------------------

def test_on_tick_no_signal_when_flat():
    """on_tick must be a no-op when the strategy has no open position."""
    strat = _ready_strategy()  # flat

    signal = strat.on_tick({"last_price": 50.0})  # extreme drop — irrelevant when flat

    assert signal is None


def test_on_tick_no_signal_when_last_price_missing():
    """on_tick must not crash or emit a signal when last_price is absent from the tick."""
    strat = _ready_strategy(entry_price=100.0)

    signal = strat.on_tick({})  # no last_price key

    assert signal is None


def test_on_tick_no_exit_before_trailing_activation():
    """A drawdown that would trigger the trailing stop must NOT exit if profit_pct
    floor has never been reached (trailing not yet active)."""
    strat = _ready_strategy(entry_price=100.0)
    # Peak at 103 (only +3%, below profit_pct=4% → trailing stays inactive)
    strat.on_tick({"last_price": 103.0})
    assert not strat._trailing_active

    # Price drops from peak by more than trail_pct=1.5% (103 * 0.985 = 101.455)
    # but trailing is not active, so no exit; price is above entry, so no hard stop either
    signal = strat.on_tick({"last_price": 101.0})

    assert signal is None


def test_on_tick_trailing_active_but_drawdown_not_enough():
    """Once trailing is active, a small pullback that doesn't reach trail_pct must
    not trigger an exit."""
    strat = _ready_strategy(entry_price=100.0)
    strat.on_tick({"last_price": 105.0})  # activates trailing, peak=105.0
    assert strat._trailing_active

    # Drawdown = (104.0 - 105.0) / 105.0 = -0.95% — less than trail_pct=1.5%
    signal = strat.on_tick({"last_price": 104.0})

    assert signal is None


# ---------------------------------------------------------------------------
# on_order_update — additional coverage
# ---------------------------------------------------------------------------

def test_exit_order_complete_clears_all_position_state():
    """A COMPLETE EXIT order must clear entry_price, held_bars, peak_close, and
    trailing_active so the strategy is fully reset and ready for the next entry."""
    strat = _ready_strategy(entry_price=100.0)
    strat._held_bars = 10
    strat._peak_close = 108.0
    strat._trailing_active = True

    strat.on_order_update({
        "status":      "COMPLETE",
        "signal_type": SignalType.EXIT,
        "direction":   "SELL",
    })

    assert strat._entry_price is None
    assert strat._held_bars == 0
    assert strat._peak_close is None
    assert strat._trailing_active is False
    assert strat.position is None


def test_cancelled_entry_clears_state():
    """A CANCELLED entry order must clear _entry_price just like a REJECTED one,
    allowing the strategy to attempt re-entry on the next candle."""
    strat = _ready_strategy()
    strat._entry_price = 100.0
    strat.position = None

    strat.on_order_update({
        "status":      "CANCELLED",
        "signal_type": SignalType.ENTRY,
        "direction":   "BUY",
    })

    assert strat._entry_price is None
    assert strat._held_bars == 0


# ---------------------------------------------------------------------------
# held_bars management
# ---------------------------------------------------------------------------

def test_held_bars_increments_each_candle_while_in_position():
    """held_bars must grow by exactly 1 per candle while the strategy holds a position."""
    strat = _ready_strategy(entry_price=100.0)
    strat._held_bars = 0

    strat.on_candle(_candle(100.0))
    assert strat._held_bars == 1

    strat.on_candle(_candle(100.0))
    assert strat._held_bars == 2


def test_held_bars_not_incremented_when_flat():
    """held_bars must stay at zero when the strategy is flat (no open position)."""
    strat = _ready_strategy()  # flat
    strat._held_bars = 0

    # Suppress entry by swapping to a below-threshold model
    strat._model = _BelowThresholdModel()
    strat.on_candle(_candle(100.0))

    assert strat._held_bars == 0
