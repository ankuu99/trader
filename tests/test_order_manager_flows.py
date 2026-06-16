"""
OrderManager flow tests.

Tests GTT lifecycle (L5 fix, R6-4, R6-5), instrument_orders cleanup,
and Telegram notification coverage. Uses a stubbed KiteConnect so no
real API calls are made.
"""
import pytest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch, PropertyMock

from trader.orders.manager import OrderManager
from trader.risk.manager import Order
from trader.strategies.base import Direction, SignalType
from trader.data.store import Store
from trader.core.config import config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_kite(order_id="ORDER123", gtt_trigger_id=42):
    kite = MagicMock()
    kite.place_order.return_value = order_id
    kite.place_gtt.return_value = {"trigger_id": gtt_trigger_id}
    kite.VARIETY_REGULAR = "regular"
    return kite


def _buy_order(instrument="NSE:TEST", price=100.0, sl=98.0, target=104.0, qty=10):
    return Order(
        instrument=instrument,
        direction=Direction.BUY,
        quantity=qty,
        price_hint=price,
        stop_loss=sl,
        target_price=target,
        strategy="test",
        mode="live",
        signal_type=SignalType.ENTRY,
    )


def _kite_update(order_id, instrument, direction, status, fill_price, qty=10):
    symbol = instrument.split(":")[-1]
    return {
        "order_id": order_id,
        "tradingsymbol": symbol,
        "exchange": "NSE",
        "transaction_type": direction,
        "status": status,
        "average_price": fill_price,
        "filled_quantity": qty,
        "trigger_price": 0,
        "order_type": "MARKET",
        "product": "CNC",
    }


@contextmanager
def _live_config(gtt_enabled=True, order_type="MARKET", market_protection_pct=1.0):
    """Patch all config properties needed for live order placement."""
    with patch.object(type(config), "gtt_enabled", new_callable=PropertyMock, return_value=gtt_enabled), \
         patch.object(type(config), "order_type", new_callable=PropertyMock, return_value=order_type), \
         patch.object(type(config), "market_protection_pct", new_callable=PropertyMock, return_value=market_protection_pct), \
         patch.object(type(config), "product", new_callable=PropertyMock, return_value="CNC"), \
         patch.object(type(config), "env", new_callable=PropertyMock, return_value="live"):
        yield


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "test.db")


# ---------------------------------------------------------------------------
# L5: GTT placed only after fill, not at order submission
# ---------------------------------------------------------------------------

def test_gtt_not_placed_at_order_submission(store):
    """GTT must NOT be placed when the live order is submitted."""
    kite = _make_kite()
    with _live_config(gtt_enabled=True):
        mgr = OrderManager(kite=kite, store=store, mode="live")
        mgr.place(_buy_order())

    kite.place_gtt.assert_not_called()


def test_gtt_placed_after_buy_fill_confirmed(store):
    """GTT must be placed exactly once, after COMPLETE BUY fill arrives."""
    kite = _make_kite(order_id="ORD1")
    with _live_config(gtt_enabled=True):
        mgr = OrderManager(kite=kite, store=store, mode="live")
        mgr.place(_buy_order())
        mgr.on_kite_order_update(_kite_update("ORD1", "NSE:TEST", "BUY", "COMPLETE", 100.0))

    kite.place_gtt.assert_called_once()


def test_gtt_not_placed_when_buy_rejected(store):
    """GTT must NOT be placed if the BUY order is rejected."""
    kite = _make_kite(order_id="ORD1")
    with _live_config(gtt_enabled=True):
        mgr = OrderManager(kite=kite, store=store, mode="live")
        mgr.place(_buy_order())
        mgr.on_kite_order_update(_kite_update("ORD1", "NSE:TEST", "BUY", "REJECTED", 0.0, qty=0))

    kite.place_gtt.assert_not_called()


def test_gtt_not_placed_when_buy_cancelled(store):
    """GTT must NOT be placed if the BUY order is cancelled (e.g. unfilled limit at EOD)."""
    kite = _make_kite(order_id="ORD1")
    with _live_config(gtt_enabled=True):
        mgr = OrderManager(kite=kite, store=store, mode="live")
        mgr.place(_buy_order())
        mgr.on_kite_order_update(_kite_update("ORD1", "NSE:TEST", "BUY", "CANCELLED", 0.0, qty=0))

    kite.place_gtt.assert_not_called()


def test_gtt_not_placed_when_gtt_disabled(store):
    """GTT must not be placed even after fill when gtt_enabled=False."""
    kite = _make_kite(order_id="ORD1")
    with _live_config(gtt_enabled=False):
        mgr = OrderManager(kite=kite, store=store, mode="live")
        mgr.place(_buy_order())
        mgr.on_kite_order_update(_kite_update("ORD1", "NSE:TEST", "BUY", "COMPLETE", 100.0))

    kite.place_gtt.assert_not_called()


# ---------------------------------------------------------------------------
# R6-5: GTT last_price uses actual fill price, not signal price_hint
# ---------------------------------------------------------------------------

def test_gtt_uses_fill_price_as_last_price(store):
    """GTT last_price must be the actual fill price, not the signal's price_hint."""
    kite = _make_kite(order_id="ORD1")
    order = _buy_order(price=100.0)   # price_hint = 100.0
    fill_price = 101.5                # market order filled with slippage

    with _live_config(gtt_enabled=True):
        mgr = OrderManager(kite=kite, store=store, mode="live")
        mgr.place(order)
        mgr.on_kite_order_update(_kite_update("ORD1", "NSE:TEST", "BUY", "COMPLETE", fill_price))

    _, kwargs = kite.place_gtt.call_args
    assert kwargs["last_price"] == pytest.approx(fill_price)


def test_gtt_uses_price_hint_when_fill_price_zero(store):
    """If fill_price is somehow 0, GTT falls back to price_hint (defensive)."""
    kite = _make_kite(order_id="ORD1")
    order = _buy_order(price=100.0)

    with _live_config(gtt_enabled=True):
        mgr = OrderManager(kite=kite, store=store, mode="live")
        mgr.place(order)
        # Simulate edge case: fill_price=0 in update — GTT should not be placed
        # (on_order_filled guard in risk manager will handle this, but GTT is placed
        # independently in on_kite_order_update — verify fallback to price_hint)
        mgr.on_kite_order_update(_kite_update("ORD1", "NSE:TEST", "BUY", "COMPLETE", 0.0))

    if kite.place_gtt.called:
        _, kwargs = kite.place_gtt.call_args
        # Should fall back to price_hint (100.0), not use 0.0
        assert kwargs["last_price"] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# R6-4: _instrument_orders cleaned up on CANCELLED BUY
# ---------------------------------------------------------------------------

def test_instrument_orders_cleared_on_cancelled_buy(store):
    """Cancelled BUY must remove instrument from _instrument_orders to prevent stale GTT context."""
    kite = _make_kite(order_id="ORD1")
    with _live_config(gtt_enabled=False, order_type="LIMIT"):
        mgr = OrderManager(kite=kite, store=store, mode="live")
        mgr.place(_buy_order())
        assert "NSE:TEST" in mgr._instrument_orders

        mgr.on_kite_order_update(_kite_update("ORD1", "NSE:TEST", "BUY", "CANCELLED", 0.0, qty=0))

    assert "NSE:TEST" not in mgr._instrument_orders


def test_instrument_orders_cleared_on_rejected_buy(store):
    """Rejected BUY must also remove instrument from _instrument_orders."""
    kite = _make_kite(order_id="ORD1")
    with _live_config(gtt_enabled=False):
        mgr = OrderManager(kite=kite, store=store, mode="live")
        mgr.place(_buy_order())
        assert "NSE:TEST" in mgr._instrument_orders

        mgr.on_kite_order_update(_kite_update("ORD1", "NSE:TEST", "BUY", "REJECTED", 0.0, qty=0))

    assert "NSE:TEST" not in mgr._instrument_orders


def test_instrument_orders_retained_after_buy_fill(store):
    """After BUY fills, _instrument_orders must stay populated for GTT context recovery."""
    kite = _make_kite(order_id="ORD1")
    with _live_config(gtt_enabled=False):
        mgr = OrderManager(kite=kite, store=store, mode="live")
        mgr.place(_buy_order())
        mgr.on_kite_order_update(_kite_update("ORD1", "NSE:TEST", "BUY", "COMPLETE", 100.0))

    # Must stay — needed for GTT-triggered SELL recovery
    assert "NSE:TEST" in mgr._instrument_orders


def test_instrument_orders_cleared_on_sell_complete(store):
    """After SELL fills, _instrument_orders must be cleared."""
    kite = _make_kite(order_id="ORD1")
    with _live_config(gtt_enabled=False):
        mgr = OrderManager(kite=kite, store=store, mode="live")
        mgr.place(_buy_order())
        mgr.on_kite_order_update(_kite_update("ORD1", "NSE:TEST", "BUY", "COMPLETE", 100.0))
        mgr.on_kite_order_update(_kite_update("GTT-SELL", "NSE:TEST", "SELL", "COMPLETE", 104.0))

    assert "NSE:TEST" not in mgr._instrument_orders


def test_stale_instrument_orders_after_cancel_does_not_affect_new_entry(store):
    """After a cancelled BUY, a new BUY for the same instrument overwrites _instrument_orders cleanly."""
    kite = _make_kite()
    kite.place_order.side_effect = ["ORD1", "ORD2"]

    with _live_config(gtt_enabled=False, order_type="LIMIT"):
        mgr = OrderManager(kite=kite, store=store, mode="live")
        mgr.place(_buy_order())
        mgr.on_kite_order_update(_kite_update("ORD1", "NSE:TEST", "BUY", "CANCELLED", 0.0, qty=0))

        assert "NSE:TEST" not in mgr._instrument_orders

        mgr.place(_buy_order())
        assert mgr._instrument_orders["NSE:TEST"] is not None


# ---------------------------------------------------------------------------
# GTT cancellation on strategy-driven SELL
# ---------------------------------------------------------------------------

def test_gtt_cancelled_on_strategy_sell(store):
    """When a SELL order is placed (strategy exit), existing GTT must be cancelled first."""
    kite = _make_kite(order_id="ORD1", gtt_trigger_id=99)
    sell_order = Order(
        instrument="NSE:TEST",
        direction=Direction.SELL,
        quantity=10,
        price_hint=104.0,
        stop_loss=0.0,
        target_price=0.0,
        strategy="test",
        mode="live",
        signal_type=SignalType.EXIT,
    )
    with _live_config(gtt_enabled=True):
        mgr = OrderManager(kite=kite, store=store, mode="live")
        mgr._gtt_ids["NSE:TEST"] = 99
        mgr.place(sell_order)

    kite.delete_gtt.assert_called_once_with(99)


def test_gtt_not_cancelled_on_sell_when_no_gtt_exists(store):
    """SELL with no prior GTT must not call delete_gtt."""
    kite = _make_kite()
    sell_order = Order(
        instrument="NSE:TEST",
        direction=Direction.SELL,
        quantity=10,
        price_hint=104.0,
        stop_loss=0.0,
        target_price=0.0,
        strategy="test",
        mode="live",
        signal_type=SignalType.EXIT,
    )
    with _live_config(gtt_enabled=True):
        mgr = OrderManager(kite=kite, store=store, mode="live")
        mgr.place(sell_order)

    kite.delete_gtt.assert_not_called()


# ---------------------------------------------------------------------------
# GTT fill dispatch — signal_type recovery
# ---------------------------------------------------------------------------

def test_gtt_fill_dispatched_as_exit(store):
    """A GTT-triggered SELL must be dispatched with signal_type=EXIT, not ENTRY."""
    kite = _make_kite(order_id="ORD1")
    received = []

    with _live_config(gtt_enabled=False):
        mgr = OrderManager(kite=kite, store=store, mode="live")
        mgr.register_update_callback(received.append)
        mgr.place(_buy_order())
        mgr.on_kite_order_update(_kite_update("ORD1", "NSE:TEST", "BUY", "COMPLETE", 100.0))
        # GTT-triggered SELL — new order_id not in _live_orders
        mgr.on_kite_order_update(_kite_update("GTT-999", "NSE:TEST", "SELL", "COMPLETE", 104.0))

    sell_records = [r for r in received if r["direction"] == "SELL" and r["status"] == "COMPLETE"]
    assert len(sell_records) == 1
    assert sell_records[0]["signal_type"] == SignalType.EXIT


def test_unknown_instrument_sell_dispatched_as_exit(store):
    """SELL for unknown instrument (no _instrument_orders entry) defaults to EXIT signal_type."""
    kite = _make_kite()
    received = []

    with _live_config(gtt_enabled=False):
        mgr = OrderManager(kite=kite, store=store, mode="live")
        mgr.register_update_callback(received.append)
        mgr.on_kite_order_update(_kite_update("UNKNOWN", "NSE:MYSTERY", "SELL", "COMPLETE", 50.0))

    assert received[0]["signal_type"] == SignalType.EXIT


# ---------------------------------------------------------------------------
# Market protection price (Zerodha API requirement for MARKET orders)
# ---------------------------------------------------------------------------

def test_market_order_passes_market_protection_flag(store):
    """MARKET orders must pass market_protection=-1 (auto) — not a price field."""
    kite = _make_kite(order_id="ORD1")
    order = _buy_order(price=100.0)

    with _live_config(gtt_enabled=False, order_type="MARKET"):
        mgr = OrderManager(kite=kite, store=store, mode="live")
        mgr.place(order)

    _, kwargs = kite.place_order.call_args
    assert kwargs["order_type"] == "MARKET"
    assert kwargs.get("market_protection") == -1
    assert "price" not in kwargs  # price must NOT be sent for MARKET orders


def test_market_sell_passes_market_protection_flag(store):
    """MARKET SELL must also pass market_protection=-1."""
    kite = _make_kite(order_id="ORD1")
    sell_order = Order(
        instrument="NSE:TEST",
        direction=Direction.SELL,
        quantity=10,
        price_hint=100.0,
        stop_loss=0.0,
        target_price=0.0,
        strategy="test",
        mode="live",
        signal_type=SignalType.EXIT,
    )

    with _live_config(gtt_enabled=False, order_type="MARKET"):
        mgr = OrderManager(kite=kite, store=store, mode="live")
        mgr.place(sell_order)

    _, kwargs = kite.place_order.call_args
    assert kwargs["order_type"] == "MARKET"
    assert kwargs.get("market_protection") == -1
    assert "price" not in kwargs


def test_limit_order_uses_price_hint_exactly(store):
    """LIMIT orders must pass price = price_hint with no buffer, no market_protection."""
    kite = _make_kite(order_id="ORD1")
    order = _buy_order(price=100.0)

    with _live_config(gtt_enabled=False, order_type="LIMIT"):
        mgr = OrderManager(kite=kite, store=store, mode="live")
        mgr.place(order)

    _, kwargs = kite.place_order.call_args
    assert kwargs["order_type"] == "LIMIT"
    assert kwargs["price"] == pytest.approx(100.0)
    assert "market_protection" not in kwargs


# ---------------------------------------------------------------------------
# Layer 1: cross-exchange / external SELL reconciliation
# ---------------------------------------------------------------------------

def _bse_sell_update(order_id, symbol, fill_price, qty=4):
    """An external SELL that filled on BSE for a symbol the bot holds on NSE."""
    return {
        "order_id": order_id,
        "tradingsymbol": symbol,
        "exchange": "BSE",
        "transaction_type": "SELL",
        "status": "COMPLETE",
        "average_price": fill_price,
        "filled_quantity": qty,
        "trigger_price": 0,
        "order_type": "MARKET",
        "product": "CNC",
    }


def test_cross_exchange_sell_remapped_to_held_position(store):
    """A BSE sell of an NSE-held position must reconcile against NSE:SYMBOL."""
    kite = _make_kite()
    dispatched = []
    with _live_config(gtt_enabled=False):
        mgr = OrderManager(kite=kite, store=store, mode="live",
                           position_lookup=lambda: ["NSE:GAIL", "NSE:RELIANCE"])
        mgr.register_update_callback(dispatched.append)
        mgr.on_kite_order_update(_bse_sell_update("EXT1", "GAIL", 175.15))

    assert len(dispatched) == 1
    assert dispatched[0]["instrument"] == "NSE:GAIL"
    assert dispatched[0]["direction"] == "SELL"
    assert dispatched[0]["signal_type"] == SignalType.EXIT
    # Stored order must also carry the remapped instrument so trade history pairs.
    import sqlite3
    conn = sqlite3.connect(store._path)
    instruments = [r[0] for r in conn.execute(
        "SELECT instrument FROM orders WHERE direction='SELL'")]
    conn.close()
    assert instruments == ["NSE:GAIL"]


def test_cross_exchange_sell_no_remap_when_ambiguous(store):
    """No remap if the symbol isn't uniquely held (safety: leave as-is)."""
    kite = _make_kite()
    dispatched = []
    with _live_config(gtt_enabled=False):
        mgr = OrderManager(kite=kite, store=store, mode="live",
                           position_lookup=lambda: ["NSE:RELIANCE"])
        mgr.register_update_callback(dispatched.append)
        mgr.on_kite_order_update(_bse_sell_update("EXT2", "GAIL", 175.15))

    assert dispatched[0]["instrument"] == "BSE:GAIL"  # unchanged


def test_cross_exchange_remap_skipped_without_position_lookup(store):
    """Backward-compat: no position_lookup => behaviour unchanged (BSE:GAIL)."""
    kite = _make_kite()
    dispatched = []
    with _live_config(gtt_enabled=False):
        mgr = OrderManager(kite=kite, store=store, mode="live")
        mgr.register_update_callback(dispatched.append)
        mgr.on_kite_order_update(_bse_sell_update("EXT3", "GAIL", 175.15))

    assert dispatched[0]["instrument"] == "BSE:GAIL"
