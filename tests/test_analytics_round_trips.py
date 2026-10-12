"""
round_trips() + monthly_round_trip_stats() — the dashboard's monthly card.

Unit = round trip: per instrument, holdings 0 → >0 → 0. Scale-in add-ons and
partial scale-outs fold into ONE trade (a scale-out winner is one win, not
two); a still-open position is excluded until it fully closes. Months bucket
by EXIT, win = net > 0.
"""
from datetime import datetime

from trader.analytics import match_trades, monthly_round_trip_stats, round_trips


def _o(inst, d, q, p, ts):
    return {"instrument": inst, "direction": d, "quantity": q, "price": p, "ts": ts}


def test_scale_out_folds_into_one_round_trip():
    orders = [
        _o("NSE:A", "BUY", 10, 100.0, "2026-09-01T10:00"),
        _o("NSE:A", "SELL", 5, 110.0, "2026-09-03T10:00"),   # 50% scale-out
        _o("NSE:A", "SELL", 5, 104.0, "2026-09-05T10:00"),   # remainder
    ]
    [rt] = round_trips(orders)
    assert rt["gross_pnl"] == 5 * 10 + 5 * 4
    assert (rt["n_slices"], rt["n_buys"], rt["n_sells"]) == (2, 1, 2)
    assert rt["entry_time"] == "2026-09-01T10:00" and rt["exit_time"] == "2026-09-05T10:00"
    assert len(match_trades(orders)) == 2            # slices would have counted 2 trades


def test_addon_folds_in_and_reentry_starts_new_trip():
    orders = [
        _o("NSE:A", "BUY", 10, 100.0, "2026-09-01T10:00"),
        _o("NSE:A", "BUY", 3, 95.0, "2026-09-02T10:00"),     # scale-in add-on
        _o("NSE:A", "SELL", 13, 102.0, "2026-09-04T10:00"),
        _o("NSE:A", "BUY", 8, 101.0, "2026-09-04T11:00"),    # same-day re-entry
        _o("NSE:A", "SELL", 8, 99.0, "2026-09-08T10:00"),
    ]
    a, b = round_trips(orders)
    assert a["gross_pnl"] == 10 * 2 + 3 * 7 and a["n_buys"] == 2
    assert b["gross_pnl"] == -16 and b["entry_time"] == "2026-09-04T11:00"


def test_open_remainder_excluded_and_orphan_sell_ignored():
    orders = [
        _o("NSE:A", "SELL", 5, 90.0, "2026-08-30T10:00"),     # orphan (predates history)
        _o("NSE:A", "BUY", 10, 100.0, "2026-09-01T10:00"),
        _o("NSE:A", "SELL", 5, 110.0, "2026-09-03T10:00"),    # scale-out, rest still open
        _o("NSE:B", "BUY", 4, 50.0, "2026-09-01T10:00"),
        _o("NSE:B", "SELL", 4, 55.0, "2026-09-02T10:00"),
    ]
    trips = round_trips(orders)
    assert [t["instrument"] for t in trips] == ["NSE:B"]


def test_oversell_closes_trip_like_match_trades():
    orders = [_o("NSE:A", "BUY", 5, 100.0, "2026-09-01T10:00"),
              _o("NSE:A", "SELL", 7, 101.0, "2026-09-02T10:00")]
    [rt] = round_trips(orders)
    assert rt["gross_pnl"] == 5.0


def test_cost_fn_applied_per_slice_and_net():
    orders = [_o("NSE:A", "BUY", 10, 100.0, "2026-09-01T10:00"),
              _o("NSE:A", "SELL", 5, 110.0, "2026-09-03T10:00"),
              _o("NSE:A", "SELL", 5, 104.0, "2026-09-05T10:00")]
    [rt] = round_trips(orders, cost_fn=lambda t: 1.5)
    assert rt["costs"] == 3.0 and rt["net_pnl"] == 70 - 3.0


def test_null_price_slice_counts_zero_gross():
    orders = [_o("NSE:A", "BUY", 10, None, "2026-09-01T10:00"),
              _o("NSE:A", "SELL", 10, 104.0, "2026-09-05T10:00")]
    [rt] = round_trips(orders)
    assert rt["gross_pnl"] == 0.0


def _trip(net, exit_dt, costs=0.0):
    return {"net_pnl": net, "costs": costs, "exit_dt": exit_dt}


def test_monthly_buckets_by_exit_month_with_net_win_definition():
    trips = [
        _trip(100.0, datetime(2026, 9, 3), costs=5.0),
        _trip(-5.0, datetime(2026, 9, 20), costs=25.0),   # +₹20 gross, −₹5 net → loss
        _trip(0.0, datetime(2026, 9, 21)),                # break-even net → not a win
        _trip(50.0, datetime(2026, 10, 2)),
    ]
    sep, oct_ = monthly_round_trip_stats(trips)
    assert (sep["month"], sep["label"], sep["trades"], sep["wins"]) == ("2026-09", "Sep", 3, 1)
    assert round(sep["win_rate"], 1) == 33.3
    assert round(sep["money_win_rate"], 2) == round(100 / 105 * 100, 2)
    assert sep["net_pnl"] == 95.0 and sep["costs"] == 30.0
    assert (oct_["trades"], oct_["win_rate"], oct_["money_win_rate"]) == (1, 100.0, 100.0)


def test_monthly_partial_flags_window_edges():
    trips = [_trip(10.0, datetime(2026, 8, 20)), _trip(10.0, datetime(2026, 9, 10)),
             _trip(10.0, datetime(2026, 10, 5))]
    rows = monthly_round_trip_stats(trips, lo=datetime(2026, 8, 12), hi=datetime(2026, 10, 12, 19, 0))
    assert [r["partial"] for r in rows] == [True, False, True]
    full = monthly_round_trip_stats(trips, lo=datetime(2026, 8, 1), hi=datetime(2026, 11, 1))
    assert not any(r["partial"] for r in full)


def test_monthly_all_zero_month_has_no_money_win_rate_and_empty_input():
    [m] = monthly_round_trip_stats([_trip(0.0, datetime(2026, 9, 3))])
    assert m["money_win_rate"] is None and m["win_rate"] == 0.0
    assert monthly_round_trip_stats([]) == []


def test_monthly_card_renders_on_dashboard(tmp_path):
    from trader.core.config import config
    from trader.data.store import Store
    from trader.risk.manager import RiskManager
    from trader.ui.state import BotState
    from trader.ui.template import render_page, _render_monthly_svg

    assert "no closed round trips" in _render_monthly_svg([])

    orig = config._data["data"]["db_path"]
    config._data["data"]["db_path"] = str(tmp_path / "ui.db")
    try:
        store = Store(tmp_path / "ui.db")
        for oid, d, q, p, day in (("1", "BUY", 10, 100.0, 1), ("2", "SELL", 5, 110.0, 3),
                                  ("3", "SELL", 5, 104.0, 5)):
            store.upsert_order({"order_id": oid, "instrument": "NSE:A", "order_type": "MARKET",
                                "product": "CNC", "direction": d, "quantity": q, "price": p,
                                "trigger_price": None, "status": "COMPLETE", "mode": "live",
                                "placed_at": datetime(2026, 9, day, 10, 0)})
        html = render_page(BotState(), RiskManager(), store, config, range_params={"range": "all"})
        assert "Monthly &middot; round trips" in html
        assert "window: 1 round trip " in html            # scale-out folded → ONE trip
        assert "<title>" in html and "round trips · 1 wins" in html
    finally:
        config._data["data"]["db_path"] = orig
