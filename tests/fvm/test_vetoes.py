"""Veto register: each gate fires on its trigger and a clean stock passes."""

from trader.fvm.data.store import FVMStore
from trader.fvm import fields as F
from trader.fvm import vetoes

ASOF = "2026-12-31"


def build_store(tmp_path, **ov):
    """A clean, veto-passing stock; pass kwargs to override individual field-dicts."""
    d = dict(
        np_qtr={"2025-03": 100, "2026-03": 120},
        rev_qtr={"2026-03": 1000},
        ev={"2026-03": 15},
        cfo={"2026-03": 500},
        npa={"2025-03": 100, "2026-03": 120},
        de={"2026-03": 0.4},
        cov={"2026-03": 8},
        rev_growth={"2026-03": 10},
        pledge={"2026-03": 0},
    )
    d.update(ov)
    s = FVMStore(tmp_path / "v.db")

    def put(spec, by):
        s.write_fundamentals([
            {"symbol": "X", "statement": spec[0], "basis": "consolidated", "period": p,
             "field": spec[1], "value": v, "knowledge_date": f"{p}-28"} for p, v in by.items()])

    put(F.NET_PROFIT_Q, d["np_qtr"]); put(F.TOTAL_REVENUE_Q, d["rev_qtr"])
    put(F.EV_EBITDA_A, d["ev"]); put(F.CFO_A, d["cfo"]); put(F.NET_PROFIT_A, d["npa"])
    put(F.DE_A, d["de"]); put(F.INT_COVERAGE_A, d["cov"]); put(F.REVENUE_GROWTH_A, d["rev_growth"])
    s.write_shareholding([
        {"symbol": "X", "period": p, "field": F.SH_PLEDGE, "value": v, "knowledge_date": f"{p}-28"}
        for p, v in d["pledge"].items()])
    return s


def test_clean_stock_passes(tmp_path):
    passed, reasons = vetoes.check_vetoes(build_store(tmp_path), "X", ASOF)
    assert passed and reasons == []


def test_cfo_negative_profit_positive(tmp_path):
    s = build_store(tmp_path, cfo={"2026-03": -50})
    passed, reasons = vetoes.check_vetoes(s, "X", ASOF)
    assert not passed and "cfo_negative_profit_positive" in reasons


def test_high_leverage_low_coverage(tmp_path):
    s = build_store(tmp_path, de={"2026-03": 2.5}, cov={"2026-03": 1.0})
    passed, reasons = vetoes.check_vetoes(s, "X", ASOF)
    assert not passed and "high_leverage_low_coverage" in reasons


def test_pledge_high_and_rising(tmp_path):
    s = build_store(tmp_path, pledge={"2025-03": 10, "2025-06": 15, "2025-09": 22, "2026-03": 25})
    passed, reasons = vetoes.check_vetoes(s, "X", ASOF)
    assert not passed and "pledge_high_and_rising" in reasons


def test_manufactured_earnings_fires_when_revenue_falls(tmp_path):
    s = build_store(tmp_path, rev_growth={"2026-03": -10},
                    npa={"2025-03": 100, "2026-03": 160})  # profit +60% while revenue -10%
    passed, reasons = vetoes.check_vetoes(s, "X", ASOF)
    assert not passed and "manufactured_earnings" in reasons


def test_margin_expansion_does_not_trip_manufactured(tmp_path):
    # revenue RISING + profit rising faster = best case, must NOT veto (§4b)
    s = build_store(tmp_path, rev_growth={"2026-03": 8},
                    npa={"2025-03": 100, "2026-03": 160})
    passed, reasons = vetoes.check_vetoes(s, "X", ASOF)
    assert "manufactured_earnings" not in reasons


def test_min_scoreability_blocks_missing_valuation(tmp_path):
    s = build_store(tmp_path, ev={})  # no EV/EBITDA -> insufficient_data
    passed, reasons = vetoes.check_vetoes(s, "X", ASOF)
    assert not passed and "insufficient_data" in reasons


def test_compliance_flag_live_only():
    assert vetoes.is_compliance_flagged("RELIANCE", {"RELIANCE", "INFY"})
    assert not vetoes.is_compliance_flagged("TCS", {"RELIANCE"})
