"""FIFO trade-matching tests — partial (scale-out) exits must split into
correctly-sized closed-trade records, not one phantom record at entry size."""

from trader.analytics import match_trades


def _o(direction, qty, price, ts, **extra):
    return {"instrument": "NSE:TEST", "direction": direction,
            "quantity": qty, "price": price, "ts": ts, **extra}


def test_partial_exit_splits_into_two_trades():
    """BUY 7 → SELL 4 → SELL 3 yields two trades (4 and 3), each with its own
    P&L — never a single record of quantity 7."""
    orders = [
        _o("BUY", 7, 100.0, "2026-06-24T09:45"),
        _o("SELL", 4, 110.0, "2026-06-25T09:30", exit_reason="PATTERN_TOP_PARTIAL"),
        _o("SELL", 3, 112.0, "2026-06-26T10:00", exit_reason="TRAILING"),
    ]
    trades = match_trades(orders)
    assert [t["quantity"] for t in trades] == [4, 3]
    assert trades[0]["gross_pnl"] == (110.0 - 100.0) * 4
    assert trades[1]["gross_pnl"] == (112.0 - 100.0) * 3
    assert trades[0]["exit_reason"] == "PATTERN_TOP_PARTIAL"
    assert trades[1]["exit_reason"] == "TRAILING"
    # No record claims the full entry size.
    assert all(t["quantity"] != 7 for t in trades)


def test_full_exit_single_trade():
    orders = [
        _o("BUY", 10, 50.0, "2026-01-01T09:15"),
        _o("SELL", 10, 55.0, "2026-01-02T09:15"),
    ]
    trades = match_trades(orders)
    assert len(trades) == 1
    assert trades[0]["quantity"] == 10
    assert trades[0]["gross_pnl"] == 50.0


def test_open_remainder_not_emitted():
    """An unsold remainder produces no closed trade until it is sold."""
    orders = [
        _o("BUY", 7, 100.0, "2026-06-24T09:45"),
        _o("SELL", 4, 110.0, "2026-06-25T09:30"),
    ]
    trades = match_trades(orders)
    assert len(trades) == 1
    assert trades[0]["quantity"] == 4
