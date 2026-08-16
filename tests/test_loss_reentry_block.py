"""
Loss re-entry block tests.

After a FULL close that realises a LOSS, ENTRY signals for that instrument are
rejected (`loss_reentry_block`) until N sessions have elapsed — reset_day() is the
only clock, decrementing the per-instrument counter, so live (main.py post_market)
and backtest (engine day boundary) share one mechanism. Winning exits never arm it.

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
def _block(enabled=True, sessions=3):
    with patch.object(type(config), "loss_reentry_block_enabled",
                      new_callable=PropertyMock, return_value=enabled), \
         patch.object(type(config), "loss_reentry_block_sessions",
                      new_callable=PropertyMock, return_value=sessions):
        yield


def _open_position(risk, instrument="NSE:TEST", price=100.0, qty=10):
    order = risk.validate(_entry(instrument, price=price))
    assert order is not None
    risk.on_order_filled(instrument, price, qty)
    return order


# ---------------------------------------------------------------------------
# Arming and expiry
# ---------------------------------------------------------------------------

def test_losing_exit_blocks_reentry():
    with _block():
        risk = RiskManager()
        _open_position(risk)
        risk.close_position("NSE:TEST", 95.0)   # loss

        assert risk.validate(_entry()) is None
        assert risk._last_reject_reason == "loss_reentry_block"


def test_winning_exit_does_not_arm():
    with _block():
        risk = RiskManager()
        _open_position(risk)
        risk.close_position("NSE:TEST", 104.0)  # profit

        assert risk.validate(_entry()) is not None


def test_block_expires_after_configured_sessions():
    with _block(sessions=3):
        risk = RiskManager()
        _open_position(risk)
        risk.close_position("NSE:TEST", 95.0)

        risk.reset_day()                         # session 1 after exit
        assert risk.validate(_entry()) is None
        risk.reset_day()                         # session 2
        assert risk.validate(_entry()) is None
        risk.reset_day()                         # session 3 — earliest re-entry
        assert risk.validate(_entry()) is not None


def test_block_is_per_instrument():
    with _block():
        risk = RiskManager()
        _open_position(risk, "NSE:AAA", price=100.0)
        risk.close_position("NSE:AAA", 95.0)

        assert risk.validate(_entry("NSE:AAA")) is None
        assert risk.validate(_entry("NSE:BBB", price=100.0)) is not None


# ---------------------------------------------------------------------------
# Paths that must NOT arm / must not be blocked
# ---------------------------------------------------------------------------

def test_eviction_with_zero_exit_price_does_not_arm():
    """post_market() evicts stale positions with exit_price=0 — bookkeeping, not a loss."""
    with _block():
        risk = RiskManager()
        _open_position(risk)

        risk.close_position("NSE:TEST", 0.0)

        assert risk.validate(_entry()) is not None


def test_exit_signal_not_blocked():
    """A blocked instrument that is somehow re-opened must still be able to exit."""
    with _block():
        risk = RiskManager()
        _open_position(risk)
        risk.close_position("NSE:TEST", 95.0)

        risk.on_order_filled("NSE:TEST", 100.0, 10)   # out-of-band re-open (restart seed)

        order = risk.validate(_exit())
        assert order is not None
        assert order.direction == Direction.SELL


def test_profitable_scale_out_then_losing_remainder_arms():
    """The block keys off the FINAL lot's realised P&L: a profitable partial
    scale-out followed by a losing remainder close is exactly the pattern-top
    scale-out shape that precedes a toxic rebuy — it must arm."""
    with _block():
        risk = RiskManager()
        _open_position(risk, qty=10)
        risk.reduce_position("NSE:TEST", 5, 110.0)    # partial at a profit
        risk.close_position("NSE:TEST", 95.0)         # remainder closes at a loss

        assert risk.validate(_entry()) is None
        assert risk._last_reject_reason == "loss_reentry_block"


# ---------------------------------------------------------------------------
# Seeding (live restart)
# ---------------------------------------------------------------------------

def test_seed_and_state_roundtrip():
    with _block():
        risk = RiskManager()
        _open_position(risk)
        risk.close_position("NSE:TEST", 95.0)
        state = risk.loss_reentry_state

        fresh = RiskManager()
        fresh.seed_loss_reentry(state)

        assert fresh.validate(_entry()) is None


def test_seed_drops_expired_entries():
    risk = RiskManager()
    risk.seed_loss_reentry({"NSE:AAA": 0, "NSE:BBB": 2})
    assert risk.loss_reentry_state == {"NSE:BBB": 2}


# ---------------------------------------------------------------------------
# Default-off inertness
# ---------------------------------------------------------------------------

def test_disabled_flag_is_inert():
    with _block(enabled=False):
        risk = RiskManager()
        _open_position(risk)
        risk.close_position("NSE:TEST", 95.0)

        assert risk.validate(_entry()) is not None
