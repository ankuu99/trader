"""
Same-day re-entry cooldown tests.

After a position is FULLY closed, ENTRY signals for that instrument are rejected for
the rest of the session (reject reason `reentry_cooldown`). State clears at the day
boundary via reset_day(), which is the only clock — no timestamps are stored, so live
(main.py post_market) and backtest (engine day boundary) share one mechanism.

The feature is config-gated and defaults OFF; the final test guards that inertness.
"""
from contextlib import contextmanager
from unittest.mock import patch, PropertyMock

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


@contextmanager
def _cooldown(enabled=True):
    with patch.object(type(config), "reentry_cooldown_enabled",
                      new_callable=PropertyMock, return_value=enabled):
        yield


def _open_position(risk, instrument="NSE:TEST", price=100.0, qty=10):
    """Take an instrument from flat to held, mirroring the real approve→fill sequence."""
    order = risk.validate(_entry(instrument, price=price))
    assert order is not None
    risk.on_order_filled(instrument, price, qty)
    return order


# ---------------------------------------------------------------------------
# Arming and blocking
# ---------------------------------------------------------------------------

def test_full_exit_blocks_reentry_same_session():
    with _cooldown():
        risk = RiskManager()
        _open_position(risk)
        risk.close_position("NSE:TEST", 104.0)

        blocked = risk.validate(_entry())

        assert blocked is None
        assert risk._last_reject_reason == "reentry_cooldown"


def test_cooldown_is_per_instrument():
    """Closing one stock must not block a different one."""
    with _cooldown():
        risk = RiskManager()
        _open_position(risk, "NSE:AAA", price=100.0)
        risk.close_position("NSE:AAA", 104.0)

        assert risk.validate(_entry("NSE:AAA")) is None
        assert risk.validate(_entry("NSE:BBB", price=100.0)) is not None


def test_reset_day_clears_cooldown():
    with _cooldown():
        risk = RiskManager()
        _open_position(risk)
        risk.close_position("NSE:TEST", 104.0)
        assert risk.validate(_entry()) is None

        risk.reset_day()

        assert risk.validate(_entry()) is not None


# ---------------------------------------------------------------------------
# Exits are never blocked
# ---------------------------------------------------------------------------

def test_exit_signal_not_blocked_by_cooldown():
    """A cooled-down instrument that is somehow re-opened must still be able to exit."""
    with _cooldown():
        risk = RiskManager()
        _open_position(risk)
        risk.close_position("NSE:TEST", 104.0)

        # Re-open out-of-band (as a restart seed would) while the cooldown is armed.
        risk.on_order_filled("NSE:TEST", 100.0, 10)

        order = risk.validate(_exit())

        assert order is not None
        assert order.direction == Direction.SELL


# ---------------------------------------------------------------------------
# Paths that must NOT arm the cooldown
# ---------------------------------------------------------------------------

def test_eviction_with_zero_exit_price_does_not_arm():
    """post_market() evicts stale positions with exit_price=0 — bookkeeping, not an exit."""
    with _cooldown():
        risk = RiskManager()
        _open_position(risk)

        risk.close_position("NSE:TEST", 0.0)

        assert "NSE:TEST" not in risk._reentry_blocked
        assert risk.validate(_entry()) is not None


def test_partial_scale_out_does_not_arm_while_remainder_open():
    with _cooldown():
        risk = RiskManager()
        _open_position(risk, qty=10)

        risk.reduce_position("NSE:TEST", 5, 104.0)

        assert "NSE:TEST" not in risk._reentry_blocked


def test_final_reduction_that_closes_position_does_arm():
    """reduce_position() delegates to close_position() once the remainder hits zero."""
    with _cooldown():
        risk = RiskManager()
        _open_position(risk, qty=10)
        risk.reduce_position("NSE:TEST", 5, 104.0)

        risk.reduce_position("NSE:TEST", 5, 106.0)

        assert "NSE:TEST" in risk._reentry_blocked
        assert risk.validate(_entry()) is None


# ---------------------------------------------------------------------------
# Default-off inertness
# ---------------------------------------------------------------------------

def test_disabled_by_default_allows_reentry():
    with _cooldown(enabled=False):
        risk = RiskManager()
        _open_position(risk)
        risk.close_position("NSE:TEST", 104.0)

        order = risk.validate(_entry())

        assert order is not None
        assert risk._last_reject_reason is None
