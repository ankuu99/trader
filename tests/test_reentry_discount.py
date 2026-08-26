"""
Same-day re-entry discount gate tests.

After exiting an instrument, an ENTRY signal the same session is rejected
(`reentry_discount`) unless it is priced at least `min_discount_pct` BELOW the
*blended* exit price of the round trip just closed (partial scale-outs included).

One-sided by design: the live sweep (2026-08-26) showed the expensive same-day
re-entries were the ones that bought back HIGHER, which a symmetric band misses.

Config-gated, defaults OFF; the last test guards that inertness.
"""
from contextlib import contextmanager
from unittest.mock import patch, PropertyMock

from trader.core.config import config
from trader.risk.manager import RiskManager
from trader.strategies.base import Direction, Signal, SignalType


def _entry(instrument="NSE:TEST", price=100.0, sl=98.0) -> Signal:
    return Signal(
        instrument=instrument,
        direction=Direction.BUY,
        signal_type=SignalType.ENTRY,
        price_hint=price,
        strategy="test",
        stop_loss_hint=sl,
    )


@contextmanager
def _gate(enabled=True, pct=1.5):
    with patch.object(type(config), "reentry_discount_enabled",
                      new_callable=PropertyMock, return_value=enabled), \
         patch.object(type(config), "reentry_discount_pct",
                      new_callable=PropertyMock, return_value=pct):
        yield


def _open(risk, instrument="NSE:TEST", price=100.0, qty=100):
    order = risk.validate(_entry(instrument, price=price))
    assert order is not None
    risk.on_order_filled(instrument, price, qty)


# --------------------------------------------------------------- blocking

def test_flat_reentry_blocked():
    """Re-entry at the same price as the exit is pure churn — rejected."""
    risk = RiskManager()
    with _gate():
        _open(risk, price=100.0)
        risk.close_position("NSE:TEST", 110.0)
        assert risk.validate(_entry(price=110.0)) is None
        assert risk._last_reject_reason == "reentry_discount"


def test_higher_reentry_blocked():
    """Sold, price ran, buying back dearer — the case a symmetric band misses."""
    risk = RiskManager()
    with _gate():
        _open(risk, price=100.0)
        risk.close_position("NSE:TEST", 110.0)
        assert risk.validate(_entry(price=113.5)) is None
        assert risk._last_reject_reason == "reentry_discount"


def test_marginal_discount_blocked():
    """1.0% below a 1.5% gate is still a reject."""
    risk = RiskManager()
    with _gate(pct=1.5):
        _open(risk, price=100.0)
        risk.close_position("NSE:TEST", 110.0)
        assert risk.validate(_entry(price=108.9)) is None


# --------------------------------------------------------------- allowing

def test_genuine_dip_reentry_allowed():
    """A re-entry comfortably below the exit is the value-adding case — allowed."""
    risk = RiskManager()
    with _gate(pct=1.5):
        _open(risk, price=100.0)
        risk.close_position("NSE:TEST", 110.0)
        order = risk.validate(_entry(price=107.0))   # -2.7%
        assert order is not None
        assert risk._last_reject_reason is None


def test_boundary_exactly_at_limit_allowed():
    risk = RiskManager()
    with _gate(pct=1.5):
        _open(risk, price=100.0)
        risk.close_position("NSE:TEST", 100.0)
        assert risk.validate(_entry(price=98.5)) is not None


def test_other_instruments_unaffected():
    risk = RiskManager()
    with _gate():
        _open(risk, price=100.0)
        risk.close_position("NSE:TEST", 110.0)
        assert risk.validate(_entry("NSE:OTHER", price=110.0)) is not None


def test_exit_signals_never_blocked():
    """The gate sits below the EXIT early-return — an open position always closes."""
    risk = RiskManager()
    with _gate():
        _open(risk, price=100.0)
        risk.close_position("NSE:TEST", 110.0)
        _open(risk, price=105.0)     # seeded directly; entry path is gated, exits are not
        ex = Signal(instrument="NSE:TEST", direction=Direction.BUY,
                    signal_type=SignalType.EXIT, price_hint=106.0, strategy="test")
        assert risk.validate(ex) is not None


# --------------------------------------------------------------- blended exit price

def test_blended_across_partial_scale_out():
    """Reference price is the qty-weighted avg of every exit since the last entry.

    Mirrors QUESS 2026-08-26: 62 @ 357.65 scale-out + 63 @ 367.10 trail exit
    → blended 362.41; the live re-entry at 365.45 must be rejected, while a
    re-entry below 362.41 * 0.985 = 356.98 must pass.
    """
    risk = RiskManager()
    with _gate(pct=1.5):
        _open(risk, "NSE:QUESS", price=350.0, qty=125)
        risk.reduce_position("NSE:QUESS", 62, 357.64838710)
        risk.close_position("NSE:QUESS", 367.10)
        blended = risk._exit_today["NSE:QUESS"][0] / risk._exit_today["NSE:QUESS"][1]
        assert abs(blended - 362.41) < 0.01
        assert risk.validate(_entry("NSE:QUESS", price=365.45, sl=350.0)) is None
        assert risk.validate(_entry("NSE:QUESS", price=356.00, sl=340.0)) is not None


def test_accumulator_resets_on_new_entry_fill():
    """A new round trip's exits replace the old ones as the reference price."""
    risk = RiskManager()
    with _gate(pct=1.5):
        _open(risk, price=100.0)
        risk.close_position("NSE:TEST", 110.0)
        _open(risk, price=105.0)                 # fill clears the old exit record
        assert "NSE:TEST" not in risk._exit_today
        risk.close_position("NSE:TEST", 100.0)
        assert risk.validate(_entry(price=99.0, sl=97.0)) is None   # vs 100, not 110
        assert risk.validate(_entry(price=98.0, sl=96.0)) is not None


# --------------------------------------------------------------- lifecycle

def test_reset_day_clears_gate():
    risk = RiskManager()
    with _gate():
        _open(risk, price=100.0)
        risk.close_position("NSE:TEST", 110.0)
        assert risk.validate(_entry(price=110.0)) is None
        risk.reset_day()
        assert risk.validate(_entry(price=110.0)) is not None


def test_eviction_with_zero_exit_price_does_not_arm():
    """post_market() evicts stale positions with exit_price=0 — bookkeeping, not an exit."""
    risk = RiskManager()
    with _gate():
        _open(risk, price=100.0)
        risk.close_position("NSE:TEST", 0.0)
        assert "NSE:TEST" not in risk._exit_today
        assert risk.validate(_entry(price=100.0)) is not None


def test_disabled_by_default_is_inert():
    risk = RiskManager()
    with _gate(enabled=False):
        _open(risk, price=100.0)
        risk.close_position("NSE:TEST", 110.0)
        assert risk.validate(_entry(price=110.0)) is not None
