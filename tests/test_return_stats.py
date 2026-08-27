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
