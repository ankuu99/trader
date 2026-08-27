"""Dashboard return stats — cumulative + annualized (total / deployed / MTM)
and the Nifty buy-and-hold benchmark. Pure functions; the 90-day guard is the
load-bearing behaviour (short windows must NOT be annualized)."""

from datetime import datetime

import pytest

from trader.analytics import (
    ANNUALIZE_MIN_DAYS,
    annualize,
    benchmark_return,
    return_stats,
)


def test_annualize_cagr_and_guard():
    # 10% over exactly one year is 10% p.a.
    assert annualize(0.10, 365) == pytest.approx(0.10)
    # 10% over half a year compounds to 21% p.a.
    assert annualize(0.10, 182.5) == pytest.approx(1.1 ** 2 - 1)
    # Below the guard → not annualized at all.
    assert annualize(0.02, 7) is None
    assert annualize(0.02, ANNUALIZE_MIN_DAYS - 1) is None
    assert annualize(0.02, ANNUALIZE_MIN_DAYS) is not None
    # Wiped-out base is undefined, never a complex number.
    assert annualize(-1.0, 365) is None
    assert annualize(0.1, 0) is None


def test_return_stats_headline_on_total_capital():
    start, end = datetime(2026, 4, 28, 9, 15), datetime(2026, 8, 27, 15, 30)
    r = return_stats(3577.30, 400_000.0, start, end)
    assert r["days"] == pytest.approx(121.26, abs=0.01)
    assert r["cum_pct"] == pytest.approx(0.894, abs=0.001)
    assert r["annualized"] is True
    assert r["ann_pct"] == pytest.approx((1.008943 ** (365 / 121.26) - 1) * 100, abs=0.01)
    # No util / unrealised supplied → secondaries stay None
    assert r["deployed_cum_pct"] is None and r["deployed_ann_pct"] is None
    assert r["mtm_cum_pct"] is None and r["mtm_ann_pct"] is None


def test_return_stats_deployed_and_mtm_secondaries():
    start, end = datetime(2026, 1, 1), datetime(2027, 1, 1)
    r = return_stats(10_000.0, 100_000.0, start, end,
                     time_avg_util_pct=50.0, unrealised_pnl=5_000.0)
    assert r["cum_pct"] == pytest.approx(10.0)
    assert r["ann_pct"] == pytest.approx(10.0)
    # Same P&L over half the capital at risk → double the return.
    assert r["deployed_cum_pct"] == pytest.approx(20.0)
    assert r["deployed_ann_pct"] == pytest.approx(20.0)
    # MTM adds open P&L on the total base.
    assert r["mtm_cum_pct"] == pytest.approx(15.0)
    assert r["mtm_ann_pct"] == pytest.approx(15.0)


def test_return_stats_short_window_is_not_annualized():
    start, end = datetime(2026, 8, 20), datetime(2026, 8, 27)
    r = return_stats(8_000.0, 400_000.0, start, end,
                     time_avg_util_pct=60.0, unrealised_pnl=1_000.0)
    assert r["cum_pct"] == pytest.approx(2.0)
    assert r["annualized"] is False
    assert r["ann_pct"] is None
    assert r["deployed_cum_pct"] is not None and r["deployed_ann_pct"] is None
    assert r["mtm_cum_pct"] is not None and r["mtm_ann_pct"] is None


def test_return_stats_degenerate_inputs():
    empty = return_stats(100.0, 0.0, datetime(2026, 1, 1), datetime(2026, 6, 1))
    assert empty["cum_pct"] is None and empty["days"] is None
    assert return_stats(100.0, 1000.0, None, datetime(2026, 6, 1))["cum_pct"] is None
    # end before start → nothing
    assert return_stats(100.0, 1000.0, datetime(2026, 6, 1), datetime(2026, 1, 1))["cum_pct"] is None
    # zero utilisation → deployed variant undefined, headline still fine
    r = return_stats(100.0, 1000.0, datetime(2026, 1, 1), datetime(2026, 7, 1), time_avg_util_pct=0.0)
    assert r["cum_pct"] == pytest.approx(10.0) and r["deployed_cum_pct"] is None


def test_benchmark_return_buy_and_hold_over_series_span():
    closes = [
        {"timestamp": "2026-01-01T00:00:00", "close": 20_000.0},
        {"timestamp": "2026-03-01T00:00:00", "close": 21_000.0},
        {"timestamp": "2027-01-01T00:00:00", "close": 22_000.0},
    ]
    b = benchmark_return(closes)
    assert b["cum_pct"] == pytest.approx(10.0)
    assert b["ann_pct"] == pytest.approx(10.0)
    assert b["first_close"] == 20_000.0 and b["last_close"] == 22_000.0
    assert b["days"] == pytest.approx(365.0)


def test_benchmark_return_short_or_sparse_series():
    # Under the guard: cumulative only.
    short = benchmark_return([
        {"timestamp": "2026-08-01T00:00:00", "close": 100.0},
        {"timestamp": "2026-08-20T00:00:00", "close": 102.0},
    ])
    assert short["cum_pct"] == pytest.approx(2.0) and short["ann_pct"] is None
    # One point / garbage → None-filled, no crash.
    assert benchmark_return([{"timestamp": "2026-08-01T00:00:00", "close": 100.0}])["cum_pct"] is None
    assert benchmark_return([])["cum_pct"] is None
    assert benchmark_return([{"timestamp": "bad", "close": None}] * 3)["cum_pct"] is None


# --------------------------------------------------------------------------- #
# trade-matched benchmark
# --------------------------------------------------------------------------- #

from trader.analytics import trade_matched_benchmark  # noqa: E402


def _closes(*pairs):
    return [{"timestamp": f"{d}T00:00:00", "close": c} for d, c in pairs]


def test_trade_matched_uses_same_notional_on_same_days():
    closes = _closes(("2026-06-01", 100.0), ("2026-06-02", 102.0),
                     ("2026-06-03", 101.0), ("2026-06-05", 110.0))
    trades = [
        # ₹10,000 in from 01-Jun close (100) to 05-Jun close (110) → index +₹1,000
        {"entry_time": "2026-06-01T10:00", "exit_time": "2026-06-05T14:00",
         "entry_price": 100.0, "quantity": 100, "gross_pnl": 1_500.0},
        # ₹5,000 from 02-Jun (102) to 03-Jun (101) → index −₹49.02
        {"entry_time": "2026-06-02T10:00", "exit_time": "2026-06-03T14:00",
         "entry_price": 50.0, "quantity": 100, "gross_pnl": -200.0},
    ]
    r = trade_matched_benchmark(trades, closes)
    assert r["n_trades"] == 2 and r["skipped"] == 0
    assert r["notional"] == pytest.approx(15_000.0)
    assert r["pnl"] == pytest.approx(1_000.0 - 5_000.0 * (1 - 101.0 / 102.0), abs=0.01)
    assert r["pct"] == pytest.approx(r["pnl"] / 15_000.0 * 100)
    assert r["our_gross"] == pytest.approx(1_300.0)
    assert r["our_gross_pct"] == pytest.approx(1_300.0 / 15_000.0 * 100)


def test_trade_matched_weekend_exit_uses_last_close_on_or_before():
    closes = _closes(("2026-06-05", 100.0), ("2026-06-08", 104.0))  # Fri, Mon
    trades = [{"entry_time": "2026-06-05T10:00", "exit_time": "2026-06-07T10:00",  # Sun exit
               "entry_price": 10.0, "quantity": 10, "gross_pnl": 0.0}]
    r = trade_matched_benchmark(trades, closes)
    assert r["n_trades"] == 1 and r["pnl"] == pytest.approx(0.0)   # Fri→Fri close


def test_trade_matched_skips_unpriceable_trades():
    closes = _closes(("2026-06-02", 100.0), ("2026-06-03", 105.0))
    trades = [
        {"entry_time": "2026-06-01T10:00", "exit_time": "2026-06-03T10:00",   # no close ≤ 01-Jun
         "entry_price": 10.0, "quantity": 10, "gross_pnl": 1.0},
        {"entry_time": "2026-06-02T10:00", "exit_time": "2026-06-03T10:00",
         "entry_price": None, "quantity": 10, "gross_pnl": 1.0},                # NULL price (remote DB)
        {"entry_time": "2026-06-02T10:00", "exit_time": "2026-06-03T10:00",
         "entry_price": 10.0, "quantity": 10, "gross_pnl": 7.0},
    ]
    r = trade_matched_benchmark(trades, closes)
    assert r["n_trades"] == 1 and r["skipped"] == 2
    assert r["pnl"] == pytest.approx(5.0) and r["our_gross"] == 7.0


def test_trade_matched_empty():
    assert trade_matched_benchmark([], _closes(("2026-06-02", 100.0)))["pnl"] is None
    r = trade_matched_benchmark([{"entry_time": "2026-06-02T10:00", "exit_time": "2026-06-03T10:00",
                                  "entry_price": 10.0, "quantity": 1, "gross_pnl": 0.0}], [])
    assert r["pnl"] is None and r["skipped"] == 1
