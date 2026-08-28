"""Dashboard analytics helpers — exit-reason breakdown (#3), per-stock
scorecard (#6), drawdown stats (#7), and partial-exit legs (#14).

All pure functions over plain dicts; must tolerate None prices/pnl/timestamps
(remote DB carries NULL order prices). No win-rate-by-exit-reason anywhere —
that metric is circular for this strategy."""

from datetime import datetime

from trader.analytics import (
    exit_reason_breakdown,
    per_stock_scorecard,
    drawdown_stats,
    position_exit_legs,
)


def _trade(inst, pnl, reason, entry, exit, qty=10, entry_p=100.0, exit_p=110.0):
    return {"instrument": inst, "gross_pnl": pnl, "exit_reason": reason,
            "entry_time": entry, "exit_time": exit, "quantity": qty,
            "entry_price": entry_p, "exit_price": exit_p}


# --------------------------------------------------------------------------- #
# #3 exit_reason_breakdown
# --------------------------------------------------------------------------- #

def test_exit_reason_breakdown_groups_and_labels_none():
    trades = [
        _trade("NSE:A", 100.0, "TRAILING", "2026-06-01T09:15", "2026-06-01T11:15"),
        _trade("NSE:B", -40.0, "STALE",    "2026-06-02T09:15", "2026-06-02T10:15"),
        _trade("NSE:C", 60.0,  "TRAILING", "2026-06-03T09:15", "2026-06-03T10:15"),
        _trade("NSE:D", None,  None,       "2026-06-04T09:15", "2026-06-04T10:15"),
    ]
    rows = exit_reason_breakdown(trades)
    by = {r["reason"]: r for r in rows}
    assert by["TRAILING"]["count"] == 2
    assert by["TRAILING"]["total_pnl"] == 160.0
    assert by["TRAILING"]["avg_hold_hours"] == 1.5   # (2h + 1h) / 2
    assert by["STALE"]["count"] == 1 and by["STALE"]["total_pnl"] == -40.0
    assert "MANUAL/EXTERNAL" in by                    # None reason relabelled
    assert by["MANUAL/EXTERNAL"]["total_pnl"] == 0.0  # None pnl treated as 0
    # No win-rate leakage.
    assert all("win" not in k.lower() for r in rows for k in r)
    # Sorted by count desc → TRAILING first.
    assert rows[0]["reason"] == "TRAILING"


# --------------------------------------------------------------------------- #
# #6 per_stock_scorecard
# --------------------------------------------------------------------------- #

def test_per_stock_scorecard_aggregates_and_joins_open():
    trades = [
        _trade("NSE:A", 100.0, "TRAILING", "2026-06-01T09:15", "2026-06-01T11:15"),
        _trade("NSE:A", -30.0, "STALE",    "2026-06-05T09:15", "2026-06-05T10:15"),
        _trade("NSE:B", 50.0,  "TRAILING", "2026-06-02T09:15", "2026-06-02T10:15"),
    ]
    open_positions = [{"instrument": "NSE:A", "quantity": 3},   # still partly open
                      {"instrument": "NSE:C", "quantity": 7}]   # open, never closed a trade
    rows = per_stock_scorecard(trades, open_positions)
    by = {r["instrument"]: r for r in rows}
    assert by["NSE:A"]["n_trades"] == 2
    assert by["NSE:A"]["gross_pnl"] == 70.0
    assert by["NSE:A"]["open_qty"] == 3
    assert by["NSE:A"]["last_exit_reason"] == "STALE"          # latest exit_time wins
    assert by["NSE:C"]["n_trades"] == 0 and by["NSE:C"]["open_qty"] == 7
    # Sorted by gross_pnl desc → A (70) before B (50) before C (0).
    assert [r["instrument"] for r in rows] == ["NSE:A", "NSE:B", "NSE:C"]


# --------------------------------------------------------------------------- #
# #7 drawdown_stats
# --------------------------------------------------------------------------- #

def test_drawdown_stats_peak_trough():
    # equity path: +100, +60(=160 peak), -80(=80), +20(=100)
    trades = [
        _trade("NSE:A", 100.0, "T", "2026-06-01T09:15", "2026-06-01T10:00"),
        _trade("NSE:A", 60.0,  "T", "2026-06-02T09:15", "2026-06-02T10:00"),
        _trade("NSE:A", -80.0, "T", "2026-06-03T09:15", "2026-06-03T10:00"),
        _trade("NSE:A", 20.0,  "T", "2026-06-05T09:15", "2026-06-05T10:00"),
    ]
    s = drawdown_stats(trades, capital=10_000.0)
    assert s["peak"] == 160.0
    assert s["max_dd"] == 80.0                       # 160 -> 80
    assert s["current_dd"] == 60.0                   # 160 -> 100 now
    assert round(s["max_dd_pct"], 2) == 0.80
    assert all(u <= 0 for u in s["underwater"])
    assert s["days_in_drawdown"] >= 1                # peak on 06-02, now 06-05


def test_drawdown_stats_empty():
    s = drawdown_stats([], capital=10_000.0)
    assert s["max_dd"] == 0.0 and s["current_dd"] == 0.0 and s["underwater"] == []


# --------------------------------------------------------------------------- #
# #14 position_exit_legs
# --------------------------------------------------------------------------- #

def _o(direction, qty, price, ts, **extra):
    return {"instrument": "NSE:TVSMOTOR", "direction": direction,
            "quantity": qty, "price": price, "ts": ts, **extra}


def test_position_exit_legs_partial():
    orders = [
        _o("BUY", 7, 3390.4, "2026-06-24T09:45"),
        _o("SELL", 4, 3536.7, "2026-06-25T09:30", exit_reason="PATTERN_TOP_PARTIAL"),
    ]
    open_positions = [{"instrument": "NSE:TVSMOTOR", "quantity": 3,
                       "entry_time": "2026-06-24T09:45:01"}]
    legs = position_exit_legs(orders, open_positions)
    assert "NSE:TVSMOTOR" in legs
    info = legs["NSE:TVSMOTOR"]
    assert info["sold_qty"] == 4
    assert info["open_qty"] == 3
    assert info["original_qty"] == 7
    assert len(info["legs"]) == 1
    assert info["legs"][0]["reason"] == "PATTERN_TOP_PARTIAL"
    assert info["legs"][0]["qty"] == 4


def test_position_exit_legs_none_when_no_partial():
    orders = [_o("BUY", 7, 3390.4, "2026-06-24T09:45")]
    open_positions = [{"instrument": "NSE:TVSMOTOR", "quantity": 7,
                       "entry_time": "2026-06-24T09:45:01"}]
    assert position_exit_legs(orders, open_positions) == {}


def test_drawdown_stats_episodes_and_state():
    # +100, +60 (=160 peak), -80 (=80 trough), +100 (=180 recovered+new peak), -30 (ongoing)
    trades = [
        _trade("NSE:A", 100.0, "T", "2026-06-01T09:15", "2026-06-01T10:00"),
        _trade("NSE:A", 60.0,  "T", "2026-06-02T09:15", "2026-06-02T10:00"),
        _trade("NSE:A", -80.0, "T", "2026-06-03T09:15", "2026-06-03T10:00"),
        _trade("NSE:A", 100.0, "T", "2026-06-05T09:15", "2026-06-05T10:00"),
        _trade("NSE:A", -30.0, "T", "2026-06-08T09:15", "2026-06-08T10:00"),
    ]
    now = datetime(2026, 6, 15, 12, 0)
    s = drawdown_stats(trades, capital=10_000.0, now=now)
    assert s["hwm"] == [100.0, 160.0, 160.0, 180.0, 180.0]
    assert s["state"] == "underwater"
    assert s["current_dd"] == 30.0
    assert s["days_in_drawdown"] == 10            # peak 06-05 → now 06-15, not → last exit
    assert len(s["episodes"]) == 2
    worst, cur = s["episodes"]                    # deepest first
    assert worst["depth"] == 80.0 and not worst["ongoing"]
    assert worst["peak_time"].startswith("2026-06-02") and worst["trough_time"].startswith("2026-06-03")
    assert worst["recovery_time"].startswith("2026-06-05") and worst["days_underwater"] == 3
    assert cur["ongoing"] and cur["recovery_time"] is None and cur["days_underwater"] == 10
    assert s["last_episode"] is cur
    # net-of-costs selection: a net_pnl key shrinks every leg
    for t in trades:
        t["net_pnl"] = t["gross_pnl"] - 1.0
    sn = drawdown_stats(trades, capital=10_000.0, now=now, pnl_key="net_pnl")
    assert sn["peak"] == 176.0 and sn["current_dd"] == 31.0


def test_drawdown_stats_new_high_reports_last_recovered_episode():
    trades = [
        _trade("NSE:A", 50.0,  "T", "2026-06-01T09:15", "2026-06-01T10:00"),
        _trade("NSE:A", -20.0, "T", "2026-06-02T09:15", "2026-06-02T10:00"),
        _trade("NSE:A", 40.0,  "T", "2026-06-04T09:15", "2026-06-04T10:00"),
    ]
    s = drawdown_stats(trades, capital=10_000.0)
    assert s["state"] == "new_high" and s["current_dd"] == 0.0 and s["days_in_drawdown"] == 0
    assert s["last_episode"]["depth"] == 20.0 and not s["last_episode"]["ongoing"]
    assert s["last_episode"]["recovery_time"].startswith("2026-06-04")
    # a monotone curve has no episodes at all
    s2 = drawdown_stats(trades[:1], capital=10_000.0)
    assert s2["state"] == "new_high" and s2["episodes"] == [] and s2["last_episode"] is None
