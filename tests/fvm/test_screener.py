"""Screener.in shareholding adapter — offline parse + PIT-store tests.

All tests run with NO network: a synthetic company-page HTML fragment drives the
stdlib-html.parser parser. Live tests would be guarded by FVM_LIVE_TESTS (none here).
"""

from trader.fvm.data.screener import (
    _knowledge_date_for_period,
    _label_to_field,
    _norm_period,
    _parse_value,
    fetch_shareholding,
    ingest_shareholding,
    parse_shareholding_html,
    shareholding_rows,
)
from trader.fvm.data.store import FVMStore

# Minimal stand-in for Screener's shareholding section: a period-headed table whose
# rows cover every field, plus an expanded promoter-detail table carrying the pledge
# row over the SAME quarter columns. A decoy quarterly-results table (Sales/Net Profit)
# must NOT pollute the shareholding fields.
_HTML = """
<html><body>
<section id="quarters"><table>
  <thead><tr><th></th><th>Mar 2025</th><th>Jun 2025</th></tr></thead>
  <tbody>
    <tr><td class="text">Sales</td><td>1,000</td><td>1,100</td></tr>
    <tr><td class="text">Net Profit</td><td>120</td><td>140</td></tr>
  </tbody>
</table></section>

<section id="shareholding"><table class="data-table">
  <thead><tr><th></th><th>Mar 2025</th><th>Jun 2025</th><th>Sep 2025</th></tr></thead>
  <tbody>
    <tr><td class="text"><button>Promoters <span>+</span></button></td>
        <td>74.99%</td><td>74.99%</td><td>75.01%</td></tr>
    <tr><td class="text">FIIs</td><td>10.20%</td><td>11.05%</td><td>11.80%</td></tr>
    <tr><td class="text">DIIs</td><td>6.50%</td><td>6.10%</td><td>5.90%</td></tr>
    <tr><td class="text">Government</td><td>0.00%</td><td>0.00%</td><td>0.00%</td></tr>
    <tr><td class="text">Public</td><td>8.31%</td><td>7.86%</td><td>7.29%</td></tr>
    <tr><td class="text">No. of Shareholders</td><td>2,50,000</td><td>2,61,000</td><td>2,72,500</td></tr>
  </tbody>
</table>
<table class="data-table">
  <thead><tr><th></th><th>Mar 2025</th><th>Jun 2025</th><th>Sep 2025</th></tr></thead>
  <tbody>
    <tr><td class="text">Pledged percentage</td><td>1.20%</td><td>0.90%</td><td>-</td></tr>
  </tbody>
</table></section>
</body></html>
"""


# --- pure helpers ---------------------------------------------------- #

def test_norm_period():
    assert _norm_period("Mar 2026") == "2026-03"
    assert _norm_period("Sep 2025") == "2025-09"
    assert _norm_period("") is None
    assert _norm_period("Promoters") is None


def test_knowledge_date_is_quarter_end_plus_30d():
    # Mar 2025 quarter-end = 2025-03-31; +30d = 2025-04-30
    assert _knowledge_date_for_period("2025-03") == "2025-04-30"
    # Dec end of a leap year still resolves correctly
    assert _knowledge_date_for_period("2025-12") == "2026-01-30"


def test_label_to_field():
    assert _label_to_field("Promoters +") == "promoter"
    assert _label_to_field("Pledged percentage") == "pledge"
    assert _label_to_field("FIIs") == "fii"
    assert _label_to_field("DIIs") == "dii"
    assert _label_to_field("Government") == "government"
    assert _label_to_field("Public") == "public"
    assert _label_to_field("No. of Shareholders") == "holders"
    assert _label_to_field("Sales") is None


def test_parse_value_strips_pct_and_commas():
    assert _parse_value("74.99%") == 74.99
    assert _parse_value("2,50,000") == 250000.0
    assert _parse_value("-") is None
    assert _parse_value("") is None
    assert _parse_value("NA") is None


# --- table parsing --------------------------------------------------- #

def test_parse_shareholding_html_extracts_all_fields():
    parsed = parse_shareholding_html(_HTML)
    assert set(parsed) == {"promoter", "fii", "dii", "government", "public",
                           "holders", "pledge"}
    assert parsed["promoter"] == {"2025-03": 74.99, "2025-06": 74.99, "2025-09": 75.01}
    assert parsed["fii"]["2025-09"] == 11.80
    assert parsed["holders"]["2025-06"] == 261000.0     # commas stripped
    # pledge merged from the second (promoter-detail) table; '-' cell dropped
    assert parsed["pledge"] == {"2025-03": 1.20, "2025-06": 0.90}


def test_decoy_results_table_does_not_pollute_fields():
    parsed = parse_shareholding_html(_HTML)
    # 'Sales'/'Net Profit' rows map to no shareholding field
    for field in parsed:
        assert field in {"promoter", "fii", "dii", "government", "public",
                         "holders", "pledge"}


def test_shareholding_rows_shape_and_knowledge_date():
    parsed = parse_shareholding_html(_HTML)
    rows = shareholding_rows("ULTRACEMCO", parsed)
    one = next(r for r in rows if r["field"] == "promoter" and r["period"] == "2025-03")
    assert one == {"symbol": "ULTRACEMCO", "period": "2025-03", "field": "promoter",
                   "value": 74.99, "knowledge_date": "2025-04-30", "source": "screener"}


# --- client + ingest (no network: monkeypatch fetch_html) ------------ #

def test_fetch_shareholding_uses_client(monkeypatch):
    class FakeClient:
        def fetch_html(self, nsecode, basis="consolidated"):
            return _HTML
    parsed = fetch_shareholding("ANY", client=FakeClient())
    assert parsed["dii"]["2025-03"] == 6.50


def test_ingest_writes_pit_shareholding(tmp_path, monkeypatch):
    store = FVMStore(tmp_path / "fvm.db")

    import trader.fvm.data.screener as screener

    class FakeClient:
        def fetch_html(self, nsecode, basis="consolidated"):
            return _HTML
    # also patch the default-client constructor so no real ShareholdingClient is built
    monkeypatch.setattr(screener, "ShareholdingClient", lambda *a, **k: FakeClient())

    n = ingest_shareholding(store, "ULTRACEMCO")
    assert n == len(shareholding_rows("ULTRACEMCO", parse_shareholding_html(_HTML)))

    # PIT read: promoter % becomes knowable 30d after quarter-end
    early = store.read_shareholding_asof("ULTRACEMCO", "promoter", "2025-04-15")
    late = store.read_shareholding_asof("ULTRACEMCO", "promoter", "2025-05-15")
    assert "2025-03" not in early          # not yet filed -> hidden (no lookahead)
    assert late.get("2025-03") == 74.99    # now knowable

    # idempotent re-ingest writes the same vintage (no duplicates / no error)
    ingest_shareholding(store, "ULTRACEMCO")
    again = store.read_shareholding_asof("ULTRACEMCO", "promoter", "2025-12-31")
    assert again == {"2025-03": 74.99, "2025-06": 74.99, "2025-09": 75.01}
