"""Single-stock study layer — peer comparison + trajectories assembly (no network)."""

import pandas as pd

from trader.fvm import fields as F
from trader.fvm.data.store import FVMStore
from trader.fvm.ui import study

ASOF = "2026-12-31"
A = ["2023-03", "2024-03", "2025-03", "2026-03"]


def _store(tmp_path):
    return FVMStore(str(tmp_path / "fvm.db"))


def _put(store, symbol, spec, by_period, basis="consolidated"):
    statement, field = spec
    store.write_fundamentals([
        {"symbol": symbol, "statement": statement, "basis": basis, "period": p,
         "field": field, "value": v, "knowledge_date": f"{p}-28"}
        for p, v in by_period.items()])


def _put_sh(store, symbol, field, by_period):
    store.write_shareholding([
        {"symbol": symbol, "period": p, "field": field, "value": v,
         "knowledge_date": f"{p}-28"} for p, v in by_period.items()])


def _seed_peer(store, sym, roce, de):
    _put(store, sym, F.ROCE_A, {p: roce for p in A})
    _put(store, sym, F.ROE_A, {p: roce - 2 for p in A})
    _put(store, sym, F.NET_PROFIT_5Y_A, {A[-1]: roce})
    _put(store, sym, F.REVENUE_5Y_A, {A[-1]: roce - 3})
    _put(store, sym, F.DE_A, {p: de for p in A})
    _put(store, sym, F.EV_EBITDA_A, {A[-1]: 18.0})
    _put_sh(store, sym, F.SH_PROMOTER, {p: 55.0 for p in A})


def _board(rows):
    return pd.DataFrame(rows)


def test_peer_table_filters_sector_and_ranks(tmp_path):
    store = _store(tmp_path)
    _seed_peer(store, "AAA", roce=25, de=0.2)
    _seed_peer(store, "BBB", roce=18, de=0.6)
    _seed_peer(store, "CCC", roce=12, de=1.4)
    board = _board([
        {"symbol": "AAA", "sector": "Pharma", "composite": 72.0, "trend": 1.0, "decision": "CANDIDATE"},
        {"symbol": "BBB", "sector": "Pharma", "composite": 65.0, "trend": 0.5, "decision": "NO_TIMING"},
        {"symbol": "CCC", "sector": "Pharma", "composite": 58.0, "trend": 0.0, "decision": "NO_TREND"},
        {"symbol": "ZZZ", "sector": "Metals", "composite": 80.0, "trend": 1.0, "decision": "CANDIDATE"},
    ])
    out = study.peer_table(board, store, "BBB", ASOF)
    assert out["sector"] == "Pharma"
    syms = list(out["df"]["symbol"])
    assert syms == ["AAA", "BBB", "CCC"]      # sorted by composite desc, Metals excluded
    assert "ZZZ" not in syms
    # subject flagged
    assert out["df"].loc[out["df"]["symbol"] == "BBB", "is_subject"].iloc[0]
    # augmented with price-free metrics
    assert out["df"].loc[out["df"]["symbol"] == "AAA", "ROCE %"].iloc[0] == 25
    assert out["df"].loc[out["df"]["symbol"] == "AAA", "Promoter %"].iloc[0] == 55.0


def test_peer_table_missing_subject_is_safe(tmp_path):
    store = _store(tmp_path)
    board = _board([{"symbol": "AAA", "sector": "Pharma", "composite": 72.0}])
    out = study.peer_table(board, store, "NOTHERE", ASOF)
    assert out["df"].empty
    assert out["sector"] is None


def test_trajectories_assembles_annual_series(tmp_path):
    store = _store(tmp_path)
    _put(store, "AAA", F.TOTAL_REVENUE_A, dict(zip(A, [100, 120, 150, 180])))
    _put(store, "AAA", F.NET_PROFIT_A, dict(zip(A, [10, 14, 18, 24])))
    _put(store, "AAA", F.ROCE_A, dict(zip(A, [20, 22, 24, 26])))
    _put_sh(store, "AAA", F.SH_PROMOTER, dict(zip(A, [60, 60, 61, 62])))
    traj = study.trajectories(store, "AAA", ASOF)
    assert traj["Revenue (Annual)"]["2026-03"] == 180
    assert traj["Net Profit (Annual)"]["2023-03"] == 10
    assert traj["ROCE %"]["2025-03"] == 24
    assert traj["_shareholding"]["promoter"]["2026-03"] == 62


def test_has_fundamentals_detects_presence(tmp_path):
    db = str(tmp_path / "fvm.db")
    store = FVMStore(db)
    assert not study.has_fundamentals(db, "AAA", ASOF)
    _put(store, "AAA", F.NET_PROFIT_A, {A[-1]: 100.0})
    assert study.has_fundamentals(db, "AAA", ASOF)
