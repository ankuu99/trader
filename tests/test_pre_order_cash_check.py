"""TD-001: live ENTRY orders the account can't fund are skipped before placement."""
from datetime import datetime
import sqlite3

import pytest

from trader.data.store import Store
from trader.risk.manager import Order, unfunded_entry
from trader.strategies.base import Direction, SignalType


def _order(signal_type=SignalType.ENTRY, addon=False, qty=10, price=100.0):
    return Order(instrument="NSE:TEST", direction=Direction.BUY, quantity=qty,
                 price_hint=price, stop_loss=90.0, target_price=0.0,
                 strategy="lr_extrema", mode="live", signal_type=signal_type, addon=addon)


def test_funded_entry_goes_ahead():
    assert unfunded_entry(_order(), 2000.0) is None


def test_unfunded_entry_returns_need():
    assert unfunded_entry(_order(), 500.0) == pytest.approx(1010.0)


def test_buffer_edge():
    assert unfunded_entry(_order(), 1000.0) is not None


def test_addon_entry_checked():
    assert unfunded_entry(_order(addon=True), 500.0) == pytest.approx(1010.0)
    assert unfunded_entry(_order(addon=True), 2000.0) is None


def test_exit_never_checked():
    assert unfunded_entry(_order(signal_type=SignalType.EXIT), 0.0) is None


def test_unknown_cash_fails_open():
    assert unfunded_entry(_order(), None) is None


def _log(store):
    store.log_signal(timestamp=datetime(2026, 10, 16, 10, 0), instrument="NSE:TEST",
                     strategy="lr_extrema", direction="BUY", signal_type="ENTRY",
                     price_hint=100.0, accepted=True)


def _row(path):
    with sqlite3.connect(path) as c:
        return c.execute("SELECT accepted, reject_reason FROM signals").fetchone()


def test_mark_signal_rejected_stores_reason_verbatim(tmp_path):
    db = tmp_path / "t.db"
    store = Store(db)
    _log(store)
    reason = "insufficient_cash: need ₹1,010, have ₹500"
    assert store.mark_signal_rejected("NSE:TEST", "BUY", reason)
    assert _row(db) == (0, reason)

    db2 = tmp_path / "t2.db"
    store2 = Store(db2)
    _log(store2)
    assert store2.mark_signal_broker_rejected("NSE:TEST", "BUY", "Insufficient funds")
    assert _row(db2) == (0, "BROKER: Insufficient funds")
