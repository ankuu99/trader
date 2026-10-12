"""
NSE Closing Auction Session (CAS) handling — F&O-eligible stocks stop
continuous trading at 15:15 and NSE blocks fresh orders 15:15–15:20, so Kite
refuses every order placed then ("Your order could not be converted to a After
Market Order (AMO)"). 12 such rejects Aug 31–Oct 12 2026, all at 15:15:00–02,
all on CAS names (CUMMINSIND day-TF entries four sessions running, ATHERENERG
pattern-top scale-out 2026-10-12).

Covers:
  - LiveFeed.flush_auction_partials_early (15:14:15): CAS names decide on their
    15:00 candle before the block; non-CAS names untouched; unknown set → all.
  - CAS names' 15:15 bucket is persist-only (pre_close skips it, its final
    emission is tagged _early_final); non-CAS names keep the 15:29:15 flush.
  - Store.mark_signal_broker_rejected: the signals table stops showing a
    broker-refused order as accepted.
  - OrderManager passes the broker's reason through on async rejects.
  - Scheduler registers pre_auction at 15:14:15 IST.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from trader.core.config import config
from trader.data.live import LiveFeed
from trader.data.store import Store
from trader.orders.manager import OrderManager
from trader.risk.manager import Order
from trader.scheduler.jobs import Scheduler
from trader.strategies.base import Direction, SignalType

_IST = timezone(timedelta(hours=5, minutes=30))
CAS, PLAIN = 111, 222          # CAS-eligible token, ordinary cash-only token
DAY = datetime(2026, 10, 12)


def _feed(auction=frozenset({CAS})):
    feed = LiveFeed(api_key="x", access_token="y", timeframe_minutes=15)
    if auction is not None:
        feed.set_auction_tokens(set(auction))
    emitted = []
    feed.register_candle_handler(emitted.append)
    return feed, emitted


def _tick(feed, token, hh, mm, ss, price, vol):
    # Aware IST timestamps → bucketing is independent of the host timezone.
    feed._process_tick({
        "instrument_token": token, "last_price": price, "volume_traded": vol,
        "exchange_timestamp": DAY.replace(hour=hh, minute=mm, second=ss, tzinfo=_IST),
    })


def _keys(emitted):
    return [(c["instrument_token"], c["timestamp"].strftime("%H:%M"), bool(c.get("_early_final")))
            for c in emitted]


# --------------------------------------------------------------------------- #
# Feed: pre-auction early emission                                            #
# --------------------------------------------------------------------------- #

def test_pre_auction_emits_only_cas_15_00_candle():
    feed, emitted = _feed()
    for tok in (CAS, PLAIN):
        _tick(feed, tok, 15, 0, 5, 100.0, 1000)
        _tick(feed, tok, 15, 13, 50, 101.0, 1500)

    feed.flush_auction_partials_early()

    # CAS 15:00 candle delivered as a normal decision candle; PLAIN untouched.
    assert _keys(emitted) == [(CAS, "15:00", False)]
    assert emitted[0]["close"] == 101.0
    assert feed._partials[CAS]["early_emitted"] is True
    assert "early_emitted" not in feed._partials[PLAIN]

    feed.flush_auction_partials_early()      # idempotent
    assert len(emitted) == 1


def test_full_session_tail_cas_vs_plain():
    """Tick-driven 15:00 → 15:30 walk through every scheduler hook."""
    feed, emitted = _feed()
    for tok in (CAS, PLAIN):
        _tick(feed, tok, 15, 0, 5, 100.0, 1000)
        _tick(feed, tok, 15, 13, 50, 101.0, 1500)

    feed.flush_auction_partials_early()                # 15:14:15
    _tick(feed, CAS, 15, 14, 40, 101.5, 1600)          # late tick, same bucket
    for tok in (CAS, PLAIN):                           # 15:15:00 rollover
        _tick(feed, tok, 15, 15, 0, 102.0, 1700)
    _tick(feed, PLAIN, 15, 22, 0, 103.0, 1900)
    feed.flush_closed_partials(DAY.replace(hour=15, minute=15).time())   # 15:16 eod_flush (no-op now)
    feed.flush_open_partials_early()                   # 15:29:15 pre_close
    feed.flush_partials()                              # 15:30 market close

    assert _keys(emitted) == [
        (CAS, "15:00", False),     # 15:14:15 — decided before the CAS block
        (CAS, "15:00", True),      # 15:15:00 — real completion, persist-only
        (PLAIN, "15:00", False),   # 15:15:00 — non-CAS decides at candle close as before
        (PLAIN, "15:15", False),   # 15:29:15 — pre_close still serves non-CAS
        (CAS, "15:15", True),      # 15:30 — auction bucket: persist, never decide
        (PLAIN, "15:15", True),    # 15:30 — final of the early-emitted bucket
    ]
    # The persisted CAS 15:00 candle carries the late tick.
    assert emitted[1]["close"] == 101.5


def test_unknown_auction_set_falls_back_to_all_tokens_and_old_pre_close():
    feed, emitted = _feed(auction=None)
    for tok in (CAS, PLAIN):
        _tick(feed, tok, 15, 0, 5, 100.0, 1000)
    feed.flush_auction_partials_early()
    assert sorted(_keys(emitted)) == [(CAS, "15:00", False), (PLAIN, "15:00", False)]

    emitted.clear()
    for tok in (CAS, PLAIN):
        _tick(feed, tok, 15, 15, 30, 102.0, 1700)      # rollover → finals, persist-only
    feed.flush_open_partials_early()
    # With no CAS knowledge pre_close behaves exactly as before (decides on all).
    assert [k for k in _keys(emitted) if k[1] == "15:15"] == [(CAS, "15:15", False), (PLAIN, "15:15", False)]


def test_pre_auction_ignores_already_open_15_15_bucket():
    """A restart/clock skew that runs the hook after 15:15 must not decide on the
    auction bucket."""
    feed, emitted = _feed()
    _tick(feed, CAS, 15, 16, 0, 100.0, 1000)
    feed.flush_auction_partials_early()
    assert emitted == []


def test_set_auction_tokens_none_clears():
    feed, _ = _feed()
    feed.set_auction_tokens(None)
    assert feed._auction_tokens is None
    assert not feed._in_auction(CAS, DAY.replace(hour=15, minute=15))


# --------------------------------------------------------------------------- #
# Store: signal row reflects broker refusal                                   #
# --------------------------------------------------------------------------- #

def _log(store, inst, direction, accepted, signal_type="EXIT", reason=None, exit_reason=None):
    store.log_signal(timestamp=DAY.replace(hour=15), instrument=inst, strategy="s",
                     direction=direction, signal_type=signal_type, price_hint=1470.0,
                     accepted=accepted, reject_reason=reason, exit_reason=exit_reason)


def _rows(store):
    with store._conn() as c:
        return [tuple(r) for r in c.execute(
            "SELECT instrument, accepted, reject_reason, exit_reason FROM signals ORDER BY id")]


def test_mark_signal_broker_rejected_flips_latest_accepted(tmp_path):
    store = Store(tmp_path / "t.db")
    _log(store, "NSE:ATHERENERG", "BUY", True, exit_reason="PATTERN_TOP_PARTIAL")
    _log(store, "NSE:KPL", "BUY", True, signal_type="ENTRY")

    assert store.mark_signal_broker_rejected(
        "NSE:ATHERENERG", "BUY", "Your order could not be converted to a After Market Order (AMO).")
    assert _rows(store) == [
        ("NSE:ATHERENERG", 0,
         "BROKER: Your order could not be converted to a After Market Order (AMO).",
         "PATTERN_TOP_PARTIAL"),
        ("NSE:KPL", 1, None, None),           # other instruments untouched
    ]
    # Second reject for the same instrument finds no accepted row → no-op.
    assert not store.mark_signal_broker_rejected("NSE:ATHERENERG", "BUY", "again")


def test_mark_signal_broker_rejected_guards(tmp_path):
    store = Store(tmp_path / "t.db")
    assert not store.mark_signal_broker_rejected("NSE:X", "BUY", "r")       # no rows
    _log(store, "NSE:X", "BUY", False, reason="max_positions")
    assert not store.mark_signal_broker_rejected("NSE:X", "BUY", "r")       # latest not accepted
    _log(store, "NSE:X", "SELL", True)
    assert not store.mark_signal_broker_rejected("NSE:X", "BUY", "r")       # direction mismatch
    assert [r[1] for r in _rows(store)] == [0, 1]


# --------------------------------------------------------------------------- #
# OrderManager: broker reason survives async rejects                          #
# --------------------------------------------------------------------------- #

def test_async_reject_dispatch_carries_status_message(tmp_path):
    kite = MagicMock()
    kite.place_order.return_value = "ORD1"
    kite.VARIETY_REGULAR = "regular"
    seen = []
    with patch.object(type(config), "gtt_enabled", new_callable=PropertyMock, return_value=False), \
         patch.object(type(config), "order_type", new_callable=PropertyMock, return_value="MARKET"), \
         patch.object(type(config), "product", new_callable=PropertyMock, return_value="CNC"), \
         patch.object(type(config), "env", new_callable=PropertyMock, return_value="live"):
        mgr = OrderManager(kite=kite, store=Store(tmp_path / "t.db"), mode="live")
        mgr.register_update_callback(seen.append)
        mgr.place(Order(instrument="NSE:TVSMOTOR", direction=Direction.BUY, quantity=10,
                        price_hint=3839.4, stop_loss=3000.0, target_price=0.0,
                        strategy="s", mode="live", signal_type=SignalType.ENTRY))
        mgr.on_kite_order_update({
            "order_id": "ORD1", "tradingsymbol": "TVSMOTOR", "exchange": "NSE",
            "transaction_type": "BUY", "status": "REJECTED", "average_price": 0,
            "filled_quantity": 0, "trigger_price": 0, "order_type": "MARKET", "product": "CNC",
            "status_message": "The Closing Auction Session has ended.",
        })
    assert seen[-1]["status"] == "REJECTED"
    assert seen[-1]["status_message"] == "The Closing Auction Session has ended."


def test_sync_placement_failure_dispatches_reject_then_raises(tmp_path):
    """Contract main._place_order relies on: the REJECTED dispatch (strategy
    restore, signal stamp, Telegram) happens BEFORE the re-raise."""
    kite = MagicMock()
    kite.place_order.side_effect = Exception(
        "Your order could not be converted to a After Market Order (AMO).")
    kite.VARIETY_REGULAR = "regular"
    seen = []
    with patch.object(type(config), "gtt_enabled", new_callable=PropertyMock, return_value=False), \
         patch.object(type(config), "order_type", new_callable=PropertyMock, return_value="MARKET"), \
         patch.object(type(config), "product", new_callable=PropertyMock, return_value="CNC"), \
         patch.object(type(config), "env", new_callable=PropertyMock, return_value="live"):
        mgr = OrderManager(kite=kite, store=Store(tmp_path / "t.db"), mode="live")
        mgr.register_update_callback(seen.append)
        with pytest.raises(Exception):
            mgr.place(Order(instrument="NSE:ATHERENERG", direction=Direction.SELL, quantity=14,
                            price_hint=1470.0, stop_loss=0.0, target_price=0.0,
                            strategy="s", mode="live", signal_type=SignalType.EXIT))
    assert seen and seen[-1]["status"] == "REJECTED"
    assert "AMO" in seen[-1]["status_message"]


# --------------------------------------------------------------------------- #
# Scheduler                                                                   #
# --------------------------------------------------------------------------- #

def test_scheduler_registers_pre_auction_at_15_14_15():
    sched = Scheduler()
    calls = []
    sched.on_pre_auction(lambda: calls.append(1))
    sched.start()
    try:
        job = sched._scheduler.get_job("pre_auction")
        fields = {f.name: str(f) for f in job.trigger.fields}
        assert (fields["hour"], fields["minute"], fields["second"]) == ("15", "14", "15")
        assert fields["day_of_week"] == "mon-fri"
        job.func()                      # runs the registered hooks
        assert calls == [1]
    finally:
        sched.stop()


# --------------------------------------------------------------------------- #
# UI: broker refusal is visible on the dashboard and the stock page           #
# --------------------------------------------------------------------------- #

def test_ui_shows_broker_rejected_signal(tmp_path):
    from trader.risk.manager import RiskManager
    from trader.ui.state import BotState
    from trader.ui.template import render_page, render_stock_page

    orig = config._data["data"]["db_path"]
    config._data["data"]["db_path"] = str(tmp_path / "ui.db")
    try:
        store = Store(tmp_path / "ui.db")
        store.log_signal(timestamp=datetime.now(), instrument="NSE:ATHERENERG", strategy="s",
                         direction="BUY", signal_type="EXIT", price_hint=1470.0,
                         accepted=True, exit_reason="PATTERN_TOP_PARTIAL")
        store.mark_signal_broker_rejected(
            "NSE:ATHERENERG", "BUY", "Your order could not be converted to a After Market Order (AMO).")
        want = "PATTERN_TOP_PARTIAL — BROKER: Your order could not be converted"
        page = render_page(BotState(), RiskManager(), store, config)
        assert want in page
        assert "never placed (ATHERENERG)" in page          # health strip
        assert want in render_stock_page("NSE:ATHERENERG", BotState(), RiskManager(), store, config)
    finally:
        config._data["data"]["db_path"] = orig
