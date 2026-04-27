"""
Risk manager flow tests.

Tests the key safety flows — pending capital locking (L1 fix), halt behaviour,
and exit pass-through. Not testing each method individually; testing the
sequences that matter in live trading.
"""
from unittest.mock import patch, PropertyMock

import pytest

from trader.core.config import config
from trader.risk.manager import RiskManager
from trader.strategies.base import Direction, Signal, SignalType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry(instrument="NSE:TEST", price=100.0, sl=98.0) -> Signal:
    return Signal(
        instrument=instrument,
        direction=Direction.BUY,
        signal_type=SignalType.ENTRY,
        price_hint=price,
        strategy="test",
        stop_loss_hint=sl,
    )


def _exit(instrument="NSE:TEST", price=104.0) -> Signal:
    return Signal(
        instrument=instrument,
        direction=Direction.BUY,
        signal_type=SignalType.EXIT,
        price_hint=price,
        strategy="test",
    )


# ---------------------------------------------------------------------------
# L1 — Pending capital locking
# ---------------------------------------------------------------------------

def test_capital_locked_on_signal_approval():
    """Approving a signal immediately reduces available capital and records the pending order."""
    risk = RiskManager()
    available_before = risk.capital_available

    order = risk.validate(_entry())

    assert order is not None
    assert risk.capital_available < available_before
    assert "NSE:TEST" in risk._pending_orders


def test_duplicate_signal_blocked_while_order_pending():
    """A second signal for the same instrument is rejected while the first order is pending."""
    risk = RiskManager()
    risk.validate(_entry())

    second = risk.validate(_entry())

    assert second is None


def test_pending_order_counts_toward_max_positions():
    """A pending order (unfilled) prevents a new order from exceeding max_open_positions."""
    with patch.object(type(config), "max_open_positions",
                      new_callable=PropertyMock, return_value=1):
        risk = RiskManager()
        risk.validate(_entry("NSE:A", price=100.0, sl=98.0))

        blocked = risk.validate(_entry("NSE:B", price=200.0, sl=196.0))

        assert blocked is None


def test_capital_released_when_order_cancelled():
    """Cancelling a pending order restores available capital and removes the pending lock."""
    risk = RiskManager()
    risk.validate(_entry())
    available_locked = risk.capital_available

    risk.on_order_cancelled("NSE:TEST")

    assert risk.capital_available > available_locked
    assert "NSE:TEST" not in risk._pending_orders


def test_capital_moves_from_pending_to_deployed_on_fill():
    """Filling an order clears the pending lock and records deployed capital correctly."""
    risk = RiskManager()
    order = risk.validate(_entry(price=100.0, sl=98.0))
    assert "NSE:TEST" in risk._pending_orders

    risk.on_order_filled("NSE:TEST", 100.0, order.quantity)

    assert "NSE:TEST" not in risk._pending_orders
    assert "NSE:TEST" in risk._open_positions
    assert risk._capital_deployed > 0
    # capital_available should reflect deployed, not pending
    assert risk.capital_available == pytest.approx(
        config.total_capital - risk._capital_deployed, abs=1.0
    )


# ---------------------------------------------------------------------------
# Halt behaviour
# ---------------------------------------------------------------------------

def test_entry_blocked_when_halted():
    risk = RiskManager()
    risk._halted = True

    assert risk.validate(_entry()) is None


def test_exit_passes_through_when_halted():
    """Exits must always be allowed even after the daily halt is triggered."""
    risk = RiskManager()
    risk.on_order_filled("NSE:TEST", 100.0, 10)
    risk._halted = True

    order = risk.validate(_exit())

    assert order is not None
    assert order.direction == Direction.SELL
    assert order.quantity == 10
