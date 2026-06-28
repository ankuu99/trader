"""Universe builder: sector parsing, financials-exclusion, PIT eligible-universe."""

from trader.fvm.data.store import FVMStore
from trader.fvm.data.universe import (
    eligible_universe,
    is_financial,
    parse_constituents_with_sector,
    prioritized_universe,
)

_CSV = (
    "Company Name,Industry,Symbol,Series,ISIN Code\n"
    "Reliance Industries Ltd.,Oil Gas & Consumable Fuels,RELIANCE,EQ,INE002A01018\n"
    "HDFC Bank Ltd.,Financial Services,HDFCBANK,EQ,INE040A01034\n"
    "Infosys Ltd.,Information Technology,INFY,EQ,INE009A01021\n"
    "ICICI Lombard,Insurance,ICICIGI,EQ,INE765G01017\n"
)


def test_parse_constituents_with_sector():
    rows = parse_constituents_with_sector(_CSV)
    by = {r["symbol"]: r["sector"] for r in rows}
    assert by["RELIANCE"] == "Oil Gas & Consumable Fuels"
    assert by["HDFCBANK"] == "Financial Services"
    assert len(rows) == 4


def test_is_financial():
    assert is_financial("Financial Services")
    assert is_financial("Banks")
    assert is_financial("Insurance")
    assert not is_financial("Information Technology")
    assert not is_financial("Oil Gas & Consumable Fuels")
    assert not is_financial(None)


def test_eligible_universe_excludes_financials_and_respects_pit(tmp_path):
    store = FVMStore(tmp_path / "u.db")
    store.write_sectors(parse_constituents_with_sector(_CSV))
    # RELIANCE+INFY members from 2024; HDFCBANK too; TCS joins only in 2025
    store.write_membership([
        {"index_name": "NIFTY500", "symbol": "RELIANCE", "start_date": "2024-01-01", "end_date": None},
        {"index_name": "NIFTY500", "symbol": "HDFCBANK", "start_date": "2024-01-01", "end_date": None},
        {"index_name": "NIFTY500", "symbol": "INFY", "start_date": "2024-01-01", "end_date": None},
        {"index_name": "NIFTY500", "symbol": "ICICIGI", "start_date": "2024-01-01", "end_date": None},
        {"index_name": "NIFTY500", "symbol": "TCS", "start_date": "2025-06-01", "end_date": None},
    ])
    # 2024: financials (HDFCBANK, ICICIGI) excluded; TCS not yet a member
    u2024 = eligible_universe(store, "2024-06-01")
    assert u2024 == ["INFY", "RELIANCE"]
    # 2025: TCS now in (no sector mapped -> 'Unknown' -> not financial -> kept)
    u2025 = eligible_universe(store, "2025-07-01")
    assert "TCS" in u2025 and "HDFCBANK" not in u2025
    # keeping financials in (toggle off) brings the banks back
    u_all = eligible_universe(store, "2024-06-01", exclude_financials=False)
    assert "HDFCBANK" in u_all


def test_prioritized_universe_orders_mid_small_large(tmp_path):
    store = FVMStore(tmp_path / "u.db")
    # 4 non-financial NIFTY500 names: A (mid), B (small), C (small), D (large-remainder)
    store.write_membership([
        {"index_name": "NIFTY500", "symbol": s, "start_date": "2024-01-01", "end_date": None}
        for s in ("AAA", "BBB", "CCC", "DDD")])
    store.write_membership([
        {"index_name": "NIFTYMIDCAP150", "symbol": "AAA", "start_date": "2024-01-01", "end_date": None}])
    store.write_membership([
        {"index_name": "NIFTYSMALLCAP250", "symbol": s, "start_date": "2024-01-01", "end_date": None}
        for s in ("BBB", "CCC")])
    # mid (AAA) -> small (BBB, CCC alphabetical) -> large-remainder (DDD)
    assert prioritized_universe(store, "2024-06-01") == ["AAA", "BBB", "CCC", "DDD"]


def test_prioritized_universe_falls_back_when_no_size_data(tmp_path):
    store = FVMStore(tmp_path / "u.db")
    store.write_membership([
        {"index_name": "NIFTY500", "symbol": s, "start_date": "2024-01-01", "end_date": None}
        for s in ("ZZZ", "AAA")])
    # no size-band membership -> everything is large-remainder -> plain alphabetical
    assert prioritized_universe(store, "2024-06-01") == ["AAA", "ZZZ"]


def test_liquidity_filter_hook(tmp_path):
    store = FVMStore(tmp_path / "u.db")
    store.write_sectors(parse_constituents_with_sector(_CSV))
    store.write_membership([
        {"index_name": "NIFTY500", "symbol": "RELIANCE", "start_date": "2024-01-01", "end_date": None},
        {"index_name": "NIFTY500", "symbol": "INFY", "start_date": "2024-01-01", "end_date": None},
    ])
    only_reliance = eligible_universe(store, "2024-06-01", liquidity_ok=lambda s: s == "RELIANCE")
    assert only_reliance == ["RELIANCE"]
