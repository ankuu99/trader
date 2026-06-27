"""FVM data layer: Trendlyne financials CSV parser + PIT store correctness."""

from trader.fvm.data.store import FVMStore
from trader.fvm.data.trendlyne import (
    _knowledge_date_for_period,
    _norm_period,
    parse_financials_csv,
)

_CSV = (
    "Parameter,Mar 2026,Mar 2025,Mar 2024\n"
    "Net Profit Annual,8188,6040,7004\n"
    'Total Revenue Annual,"88,512","75,955","70,908"\n'
    "Operating Profit Margin%,19%,17%,18%\n"
    "Some Junk Row,-,NA,\n"
)


def test_norm_period():
    assert _norm_period("Mar 2026") == "2026-03"
    assert _norm_period("Dec 2019") == "2019-12"
    assert _norm_period("Parameter") is None


def test_knowledge_date_is_period_end_plus_45d():
    # Mar 2026 quarter-end = 2026-03-31; +45d = 2026-05-15
    assert _knowledge_date_for_period("2026-03") == "2026-05-15"


def test_parser_normalises_periods_strips_commas_and_pct():
    recs = parse_financials_csv(_CSV)
    np = {r["period"]: r["value"] for r in recs if r["field"] == "Net Profit Annual"}
    assert np == {"2026-03": 8188.0, "2025-03": 6040.0, "2024-03": 7004.0}
    rev = {r["period"]: r["value"] for r in recs if r["field"] == "Total Revenue Annual"}
    assert rev["2026-03"] == 88512.0  # quoted comma stripped
    opm = {r["period"]: r["value"] for r in recs if r["field"].startswith("Operating Profit Margin")}
    assert opm["2026-03"] == 19.0  # percent stripped
    # blank / '-' / 'NA' cells are skipped entirely
    assert not any(r["field"] == "Some Junk Row" for r in recs)


def test_pit_read_hides_future_knowledge(tmp_path):
    """A period must not be visible before its knowledge_date — the core no-lookahead guarantee."""
    store = FVMStore(tmp_path / "fvm_test.db")
    recs = parse_financials_csv(_CSV)
    store.write_fundamentals([
        {"symbol": "TEST", "statement": "annual", "basis": "consolidated",
         "period": r["period"], "field": r["field"], "value": r["value"],
         "knowledge_date": _knowledge_date_for_period(r["period"])}
        for r in recs
    ])
    field = "Net Profit Annual"
    # Mar'26 becomes knowable on 2026-05-15
    early = store.read_fundamental_asof("TEST", "annual", "consolidated", field, "2026-04-01")
    late = store.read_fundamental_asof("TEST", "annual", "consolidated", field, "2026-06-01")
    assert "2026-03" not in early                 # not yet known -> excluded
    assert early == {"2024-03": 7004.0, "2025-03": 6040.0}
    assert late.get("2026-03") == 8188.0          # now known -> included


def test_write_fundamentals_is_append_only_idempotent(tmp_path):
    store = FVMStore(tmp_path / "fvm_test.db")
    row = [{"symbol": "TEST", "statement": "annual", "basis": "consolidated",
            "period": "2026-03", "field": "Net Profit Annual", "value": 8188.0,
            "knowledge_date": "2026-05-15"}]
    store.write_fundamentals(row)
    store.write_fundamentals(row)  # same vintage again -> no duplicate
    got = store.read_fundamental_asof("TEST", "annual", "consolidated", "Net Profit Annual", "2026-06-01")
    assert got == {"2026-03": 8188.0}
