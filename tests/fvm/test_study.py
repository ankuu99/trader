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


def _daily(start, periods, closes):
    ts = pd.date_range(start, periods=periods, freq="D").astype(str)
    return pd.DataFrame({"timestamp": ts, "open": closes, "high": closes,
                         "low": closes, "close": closes, "volume": [1] * periods})


def test_scorecard_replay_flips_verdict_before_asof(tmp_path):
    store = _store(tmp_path)
    sym = "REPLAYCO"
    # D/E deteriorates over the years: early vintages read healthy, later ones read broken.
    # Each FY value becomes knowable at its own period-end, so the PIT replay must show
    # the flip in the quarter it became knowable — not before, not smeared.
    _put(store, sym, F.DE_A, {"2023-03": 0.2, "2024-03": 0.3, "2025-03": 1.6, "2026-03": 1.8})
    _put(store, sym, F.ROCE_A, {p: 20.0 for p in A})
    n = 1500
    daily = _daily("2023-01-01", n, [100.0] * n)

    rp = study.replay_from_daily(store, sym, "2026-12-31", daily, years=4)
    crit, summ = rp["criteria"], rp["summary"]
    assert not crit.empty and not summ.empty
    assert rp["quarters"] == sorted(rp["quarters"])

    de = crit[crit["label"] == "Debt / Equity"].set_index("quarter")["verdict"]
    assert de.loc["2024-06-30"] == "PASS"   # knows only FY24 (D/E 0.3)
    assert de.loc["2026-06-30"] == "FAIL"   # knows FY26 (D/E 1.8)
    # dealbreaker column populated in the summary once the flip happens
    assert "Debt / Equity" in summ.set_index("quarter").loc["2026-06-30", "dealbreaker_fails"]
    # price track is PIT (flat 100 series)
    assert (summ["price"] == 100.0).all()


def test_scorecard_replay_empty_without_prices(tmp_path):
    store = _store(tmp_path)
    rp = study.replay_from_daily(store, "NOPX", ASOF, None)
    assert rp["criteria"].empty and rp["summary"].empty and rp["quarters"] == []


def test_has_fundamentals_detects_presence(tmp_path):
    db = str(tmp_path / "fvm.db")
    store = FVMStore(db)
    assert not study.has_fundamentals(db, "AAA", ASOF)
    _put(store, "AAA", F.NET_PROFIT_A, {A[-1]: 100.0})
    assert study.has_fundamentals(db, "AAA", ASOF)


def test_journal_roundtrip_with_price_change(tmp_path):
    db = str(tmp_path / "fvm.db")
    store = FVMStore(db)
    eid = study.add_journal_entry(db, "aaa", "2026-06-30", "BUY",
                                  "moat + cheapest own-history P/E", price=100.0)
    assert eid > 0
    study.add_journal_entry(db, "AAA", "2026-09-30", "WATCH", "margins wobbling", price=None)

    entries = study.journal_entries(db, "AAA", last_price=120.0)
    assert len(entries) == 2
    assert entries[0]["verdict"] == "WATCH"            # newest first
    assert entries[0]["change_pct"] is None            # no entry price recorded
    assert abs(entries[1]["change_pct"] - 20.0) < 1e-9  # +20% since the BUY call
    assert study.journal_entries(db, "OTHER", 50.0) == []

    store.delete_journal(eid)
    assert len(study.journal_entries(db, "AAA", 120.0)) == 1


def _sectors(store, pharma, metals=()):
    store.write_sectors([{"symbol": s, "sector": "Pharma"} for s in pharma] +
                        [{"symbol": s, "sector": "Metals"} for s in metals])


def test_peer_fetch_plan_tops_up_uncached_peers(tmp_path):
    db = str(tmp_path / "fvm.db")
    store = FVMStore(db)
    _sectors(store, ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG"], metals=["ZZZ"])
    _put(store, "BBB", F.NET_PROFIT_A, {A[-1]: 10.0})  # one peer already cached
    plan = study.peer_fetch_plan(db, "AAA", ASOF)
    assert plan["sector"] == "Pharma"
    assert plan["cached"] == ["BBB"]
    assert len(plan["to_fetch"]) == 4          # tops up to max_peers=5
    assert "AAA" not in plan["to_fetch"]       # never the subject
    assert "ZZZ" not in plan["to_fetch"]       # never cross-sector
    assert "BBB" not in plan["to_fetch"]


def test_peer_fetch_plan_enough_cached_fetches_nothing(tmp_path):
    db = str(tmp_path / "fvm.db")
    store = FVMStore(db)
    _sectors(store, ["AAA", "BBB", "CCC", "DDD", "EEE"])
    for p in ("BBB", "CCC", "DDD"):
        _put(store, p, F.NET_PROFIT_A, {A[-1]: 10.0})
    plan = study.peer_fetch_plan(db, "AAA", ASOF)
    assert plan["cached"] == ["BBB", "CCC", "DDD"]
    assert plan["to_fetch"] == []              # 3 cached peers is a usable table


def test_peer_fetch_plan_unknown_sector_is_empty(tmp_path):
    db = str(tmp_path / "fvm.db")
    FVMStore(db)  # empty sector_map
    plan = study.peer_fetch_plan(db, "NOSECTOR", ASOF)
    assert plan["sector"] is None and plan["to_fetch"] == []


def test_fetch_peers_stops_on_quota_exhaustion(tmp_path, monkeypatch):
    db = str(tmp_path / "fvm.db")
    store = FVMStore(db)
    _sectors(store, ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"])
    calls = []

    def fake_ensure(db_, market_db_, symbol, asof, **kw):
        calls.append(symbol)
        # first fetch works, second hits the fincsv quota
        return {"symbol": symbol, "fundamentals": "fetched" if len(calls) == 1 else "empty",
                "shareholding": "fetched", "prices": "fetched", "errors": []}

    monkeypatch.setattr(study, "ensure_stock_data", fake_ensure)
    res = study.fetch_peers(db, str(tmp_path / "market.db"), "AAA", ASOF)
    assert len(res["statuses"]) == 2           # stopped right after the quota signal
    assert calls == res["to_fetch"][:2]
