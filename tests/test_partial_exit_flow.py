"""
Partial (scale-out) exit flow tests.

Regression for the live-orphaning bug (2026-06-25, TVS): the pattern-top
scale-out works end-to-end in the backtest engine, but the LIVE path never
carried the `partial` flag, so a partial SELL was treated as a full close —
risk freed the whole position, the open_positions row was deleted, and the
strategy reset. The remaining shares were orphaned and never trailed/exited.

These tests pin the contract that makes scale-out work live:
  1. RiskManager._validate_exit marks the SELL Order as partial.
  2. OrderManager propagates `partial` into the dispatched fill record
     (both paper and live paths).
  3. End-to-end: a partial SELL keeps the remainder open in risk + strategy
     and in the open_positions row; a subsequent full SELL closes it.
"""
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from trader.core.config import config
from trader.data.store import Store
from trader.orders.manager import OrderManager
from trader.risk.manager import Order, RiskManager
from trader.strategies.base import Direction, Signal, SignalType
from trader.strategies.lr_extrema import LRExtremaStrategy


INSTRUMENT = "NSE:TEST"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _make_kite(order_id="ORD1"):
    kite = MagicMock()
    kite.place_order.return_value = order_id
    kite.VARIETY_REGULAR = "regular"
    return kite


@contextmanager
def _live_config(gtt_enabled=False, order_type="MARKET"):
    with patch.object(type(config), "gtt_enabled", new_callable=PropertyMock, return_value=gtt_enabled), \
         patch.object(type(config), "order_type", new_callable=PropertyMock, return_value=order_type), \
         patch.object(type(config), "market_protection_pct", new_callable=PropertyMock, return_value=1.0), \
         patch.object(type(config), "product", new_callable=PropertyMock, return_value="CNC"), \
         patch.object(type(config), "env", new_callable=PropertyMock, return_value="live"):
        yield


def _sell_kite_update(order_id, qty, fill_price, status="COMPLETE"):
    return {
        "order_id": order_id,
        "tradingsymbol": INSTRUMENT.split(":")[-1],
        "exchange": "NSE",
        "transaction_type": "SELL",
        "status": status,
        "average_price": fill_price,
        "filled_quantity": qty,
        "trigger_price": 0,
        "order_type": "MARKET",
        "product": "CNC",
    }


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "test.db")


# --------------------------------------------------------------------------- #
# 1. RiskManager marks the partial SELL Order
# --------------------------------------------------------------------------- #

def test_validate_exit_marks_scaleout_order_partial():
    """A scale-out EXIT (0 < exit_fraction < 1) yields a SELL Order with the
    reduced quantity AND partial=True; a full exit is partial=False."""
    risk = RiskManager()
    risk.on_order_filled(INSTRUMENT, fill_price=100.0, quantity=7)

    scale_out = Signal(
        instrument=INSTRUMENT, direction=Direction.BUY, signal_type=SignalType.EXIT,
        price_hint=110.0, strategy="lr_extrema", exit_fraction=0.7,
    )
    order = risk.validate(scale_out)
    assert order is not None
    assert order.quantity == 4                       # int(7 * 0.7)
    assert getattr(order, "partial", False) is True  # <-- the unwired contract

    full = Signal(
        instrument=INSTRUMENT, direction=Direction.BUY, signal_type=SignalType.EXIT,
        price_hint=110.0, strategy="lr_extrema", exit_fraction=None,
    )
    order2 = risk.validate(full)
    assert order2.quantity == 7
    assert getattr(order2, "partial", False) is False


# --------------------------------------------------------------------------- #
# 2. OrderManager propagates `partial` into the dispatched record
# --------------------------------------------------------------------------- #

def _partial_sell_order(qty=4):
    o = Order(
        instrument=INSTRUMENT, direction=Direction.SELL, quantity=qty,
        price_hint=110.0, stop_loss=0.0, target_price=0.0,
        strategy="lr_extrema", mode="live", signal_type=SignalType.EXIT,
    )
    o.partial = True
    return o


def test_partial_flag_propagated_paper(store):
    """Paper fill of a partial SELL dispatches a record with partial=True."""
    received = []
    with patch.object(type(config), "order_type", new_callable=PropertyMock, return_value="MARKET"), \
         patch.object(type(config), "product", new_callable=PropertyMock, return_value="CNC"), \
         patch.object(type(config), "env", new_callable=PropertyMock, return_value="paper"):
        mgr = OrderManager(kite=None, store=store, mode="paper")
        mgr.register_update_callback(received.append)
        mgr.place(_partial_sell_order())
        mgr.on_candle({"_symbol": INSTRUMENT, "open": 110.0, "high": 111.0,
                       "low": 109.0, "close": 110.0, "volume": 100})

    fills = [r for r in received if r.get("status") == "COMPLETE"]
    assert len(fills) == 1
    assert fills[0].get("partial") is True


def test_partial_flag_propagated_live(store):
    """Live fill of a partial SELL dispatches a record with partial=True."""
    received = []
    kite = _make_kite("SELL-PART")
    with _live_config():
        mgr = OrderManager(kite=kite, store=store, mode="live")
        mgr.register_update_callback(received.append)
        mgr.place(_partial_sell_order())
        mgr.on_kite_order_update(_sell_kite_update("SELL-PART", qty=4, fill_price=110.0))

    fills = [r for r in received if r.get("status") == "COMPLETE" and r["direction"] == "SELL"]
    assert len(fills) == 1
    assert fills[0].get("partial") is True


def test_full_sell_not_marked_partial_live(store):
    """A normal (full) SELL must NOT be tagged partial."""
    received = []
    kite = _make_kite("SELL-FULL")
    full = Order(
        instrument=INSTRUMENT, direction=Direction.SELL, quantity=7,
        price_hint=110.0, stop_loss=0.0, target_price=0.0,
        strategy="lr_extrema", mode="live", signal_type=SignalType.EXIT,
    )
    with _live_config():
        mgr = OrderManager(kite=kite, store=store, mode="live")
        mgr.register_update_callback(received.append)
        mgr.place(full)
        mgr.on_kite_order_update(_sell_kite_update("SELL-FULL", qty=7, fill_price=110.0))

    fills = [r for r in received if r.get("status") == "COMPLETE" and r["direction"] == "SELL"]
    assert fills[0].get("partial") in (False, None)


# --------------------------------------------------------------------------- #
# 3. End-to-end: partial keeps the remainder; full close finishes it
# --------------------------------------------------------------------------- #

def _wire_handler(risk, store, strat):
    """Order-update handler mirroring main.py.handle_order_update (SELL branch
    is what this regression pins). Returns the callback."""
    def handle(update):
        status = update.get("status", "")
        st = update.get("signal_type")
        inst = update["instrument"]
        fill_price = float(update.get("fill_price") or update.get("price") or 0)
        qty = int(update.get("quantity") or 0)
        if status == "COMPLETE":
            if st == SignalType.ENTRY:
                risk.on_order_filled(inst, fill_price, qty)
                store.upsert_open_position(inst, fill_price, qty, 0, datetime.now())
            else:
                if update.get("partial"):
                    risk.reduce_position(inst, qty, fill_price)
                    store.update_position_quantity(inst, risk._open_positions.get(inst, 0))
                else:
                    risk.close_position(inst, fill_price)
                    store.delete_open_position(inst)
        if strat.instrument == inst:
            strat.on_order_update(update)
    return handle


def test_partial_exit_keeps_remainder_then_full_close(store):
    """Entry 7 → partial SELL 4 leaves 3 open in risk + strategy + DB;
    a follow-up full SELL 3 closes everything."""
    risk = RiskManager()
    strat = LRExtremaStrategy(INSTRUMENT, {"warmup_bars": 10})
    kite = _make_kite()

    with _live_config():
        mgr = OrderManager(kite=kite, store=store, mode="live")
        mgr.register_update_callback(_wire_handler(risk, store, strat))

        # --- Entry: BUY 7 @ 100 ---
        buy = Order(instrument=INSTRUMENT, direction=Direction.BUY, quantity=7,
                    price_hint=100.0, stop_loss=98.0, target_price=0.0,
                    strategy="lr_extrema", mode="live", signal_type=SignalType.ENTRY)
        kite.place_order.return_value = "BUY1"
        mgr.place(buy)
        mgr.on_kite_order_update({
            "order_id": "BUY1", "tradingsymbol": "TEST", "exchange": "NSE",
            "transaction_type": "BUY", "status": "COMPLETE", "average_price": 100.0,
            "filled_quantity": 7, "trigger_price": 0, "order_type": "MARKET", "product": "CNC",
        })
        assert risk._open_positions[INSTRUMENT] == 7
        assert not strat.is_flat()

        # --- Partial scale-out: SELL 4 @ 110 ---
        sell_part = risk.validate(Signal(
            instrument=INSTRUMENT, direction=Direction.BUY, signal_type=SignalType.EXIT,
            price_hint=110.0, strategy="lr_extrema", exit_fraction=0.7,
        ))
        kite.place_order.return_value = "SELL-PART"
        mgr.place(sell_part)
        mgr.on_kite_order_update(_sell_kite_update("SELL-PART", qty=4, fill_price=110.0))

        # Remainder must stay open everywhere.
        assert risk._open_positions.get(INSTRUMENT) == 3
        assert not strat.is_flat()                       # strategy keeps trailing the rest
        rows = {r["instrument"]: r for r in store.read_open_positions()}
        assert rows[INSTRUMENT]["quantity"] == 3

        # --- Full close of the remainder: SELL 3 @ 112 ---
        sell_full = risk.validate(Signal(
            instrument=INSTRUMENT, direction=Direction.BUY, signal_type=SignalType.EXIT,
            price_hint=112.0, strategy="lr_extrema", exit_fraction=None,
        ))
        kite.place_order.return_value = "SELL-FULL"
        mgr.place(sell_full)
        mgr.on_kite_order_update(_sell_kite_update("SELL-FULL", qty=3, fill_price=112.0))

        assert INSTRUMENT not in risk._open_positions
        assert strat.is_flat()
        assert all(r["instrument"] != INSTRUMENT for r in store.read_open_positions())
