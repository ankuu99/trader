"""
Backtest metrics + utilisation correctness.

Permanent guards for the numbers the backtest reports:
  - compute_metrics aggregates reconcile with the raw trade list
    (total_pnl == Σpnl, wins+losses == total, Σ monthly == total).
  - compute_utilisation reconstructs deployed capital / open-position counts.
  - the engine's per-trade invariant: pnl == (exit-entry)*qty - cost, on a real
    run over the committed candle fixture.
"""

import csv
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from trader.backtest.engine import compute_metrics, compute_utilisation, run_backtest

FIXTURE = Path(__file__).parent / "fixtures" / "integration" / "candles.csv"


def _trade(entry, exit_, qty, cost, edate, xdate):
    return {
        "instrument": "NSE:T", "entry": entry, "exit": exit_, "qty": qty,
        "cost": cost, "pnl": (exit_ - entry) * qty - cost,
        "entry_date": edate, "exit_date": xdate,
        "product": "CNC", "reason": "X", "held_candles": 1,
    }


_TRADES = [
    _trade(100, 110, 10, 5, datetime(2025, 1, 6), datetime(2025, 1, 13)),   # +95
    _trade(50, 45, 20, 4, datetime(2025, 1, 8), datetime(2025, 1, 20)),     # -104
    _trade(200, 220, 5, 3, datetime(2025, 2, 3), datetime(2025, 2, 6)),     # +97
]
_CAPITAL = 10_000.0


# ---------------------------------------------------------------------------
# compute_metrics reconciliation
# ---------------------------------------------------------------------------

def test_compute_metrics_reconciles_with_trades():
    m = compute_metrics(_TRADES, _CAPITAL)
    raw = sum(t["pnl"] for t in _TRADES)
    assert m["total_pnl"] == pytest.approx(raw)               # 88
    assert m["return_pct"] == pytest.approx(raw / _CAPITAL * 100)
    assert m["wins"] == 2 and m["losses"] == 1
    assert m["wins"] + m["losses"] == m["total_trades"] == 3
    assert sum(v["pnl"] for v in m["monthly_returns"].values()) == pytest.approx(raw)


def test_compute_metrics_empty():
    m = compute_metrics([], _CAPITAL)
    assert m["total_trades"] == 0 and m["total_pnl"] == 0.0


# ---------------------------------------------------------------------------
# compute_utilisation
# ---------------------------------------------------------------------------

def test_compute_utilisation_reconstruction():
    u = compute_utilisation(_TRADES, _CAPITAL)
    o = u["overall"]
    # A (100x10=1000) and B (50x20=1000) overlap Jan 8–12 → 2 positions, ₹2000.
    assert o["peak_positions"] == 2
    assert o["peak_deployed"] == pytest.approx(2000.0)
    # Peak overlap precedes any exit → avail = capital → util = 2000/10000 = 20%.
    assert o["peak_util_pct"] == pytest.approx(20.0, abs=0.1)

    months = {r["month"]: r for r in u["monthly"]}
    assert set(months) == {"2025-01", "2025-02"}
    assert months["2025-01"]["entries"] == 2
    assert months["2025-02"]["entries"] == 1
    assert months["2025-01"]["peak_positions"] == 2


def test_compute_utilisation_empty():
    u = compute_utilisation([], _CAPITAL)
    assert u["monthly"] == []
    assert u["overall"]["peak_positions"] == 0


def test_compute_utilisation_daily_bucket():
    """bucket='day' keys rows by YYYY-MM-DD (used by the live dashboard); overall
    stats are identical to the monthly bucketing (same daily grid underneath)."""
    u_day = compute_utilisation(_TRADES, _CAPITAL, bucket="day")
    u_mon = compute_utilisation(_TRADES, _CAPITAL, bucket="month")
    keys = [r["month"] for r in u_day["monthly"]]
    assert all(len(k) == 10 and k.count("-") == 2 for k in keys)  # YYYY-MM-DD
    assert "2025-01-06" in keys  # trade A entry day
    assert len(keys) > len(u_mon["monthly"])  # more granular than monthly
    assert u_day["overall"] == u_mon["overall"]  # bucketing doesn't change overall peaks


# ---------------------------------------------------------------------------
# Engine per-trade invariant on the real candle fixture
# ---------------------------------------------------------------------------

def test_engine_trades_pnl_reconcile(tmp_path):
    """Real run_backtest over the committed fixture: every trade's pnl must equal
    (exit-entry)*qty - cost, and the aggregate must equal Σpnl."""
    from trader.core.config import config
    from trader.data.store import Store

    rows = []
    with open(FIXTURE, newline="") as f:
        for r in csv.DictReader(f):
            rows.append({
                "timestamp": datetime.fromisoformat(r["timestamp"]),
                "open": float(r["open"]), "high": float(r["high"]),
                "low": float(r["low"]), "close": float(r["close"]),
                "volume": int(r["volume"]),
            })
    df = pd.DataFrame(rows)

    store = Store(tmp_path / "t.db")
    store.write_candles("NSE:T", "15minute", df)

    saved_tf = config._data.get("candle_timeframe")
    config._data["candle_timeframe"] = "15minute"
    try:
        params = {
            "warmup_bars": 10, "lookback_bars": 50, "threshold": 0.6,
            "profit_pct": 2.0, "trail_pct": 1.0, "stop_pct": 2.0, "hold_bars": 20,
            "retrain_every": 10, "extrema_order": 2, "sell_threshold": 0.6,
            "sell_min_pct": 1.0, "features": {"volume_ma_bars": 5},
        }
        trades = run_backtest(
            None, store, ["NSE:T"], {"NSE:T": 0}, params,
            datetime(2025, 2, 1), datetime(2025, 3, 28), pre_warmup_days=30,
        )
    finally:
        config._data["candle_timeframe"] = saved_tf

    assert trades, "fixture run produced no trades — can't verify invariant"
    for t in trades:
        recon = (t["exit"] - t["entry"]) * t["qty"] - t["cost"]
        assert recon == pytest.approx(t["pnl"], abs=0.01), f"pnl mismatch: {t}"
    m = compute_metrics(trades, 100_000)
    assert m["total_pnl"] == pytest.approx(sum(t["pnl"] for t in trades))
