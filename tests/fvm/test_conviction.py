"""Long-term conviction scorecard — verdict bands, section assembly, red-flag inversion."""

import pandas as pd

from trader.fvm import conviction as cv
from trader.fvm import fields as F
from trader.fvm.data.store import FVMStore

ASOF = "2026-12-31"
A = ["2022-03", "2023-03", "2024-03", "2025-03", "2026-03"]


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


def _quality_stock(store, sym="GOODCO"):
    """A textbook compounder: high ROCE/ROE, low debt, cash-backed profit, clean ownership."""
    _put(store, sym, F.ROCE_A, {p: 24.0 for p in A})
    _put(store, sym, F.ROE_A, {p: 21.0 for p in A})
    _put(store, sym, F.NET_PROFIT_MARGIN_A, dict(zip(A, [12, 13, 14, 15, 16])))
    _put(store, sym, F.REVENUE_5Y_A, {A[-1]: 18.0})
    _put(store, sym, F.REVENUE_3Y_A, {A[-1]: 20.0})
    _put(store, sym, F.NET_PROFIT_5Y_A, {A[-1]: 22.0})
    _put(store, sym, F.NET_PROFIT_3Y_A, {A[-1]: 26.0})
    _put(store, sym, F.DE_A, {p: 0.2 for p in A})
    _put(store, sym, F.INT_COVERAGE_A, {p: 12.0 for p in A})
    _put(store, sym, F.CFO_A, {A[-1]: 110.0})
    _put(store, sym, F.NET_PROFIT_A, {A[-1]: 100.0})
    _put(store, sym, F.CFI_A, {A[-1]: -40.0})
    _put(store, sym, F.DIV_PAYOUT_A, {A[-1]: 25.0})
    _put_sh(store, sym, F.SH_PROMOTER, {p: 62.0 for p in A})
    _put_sh(store, sym, F.SH_PLEDGE, {p: 0.0 for p in A})
    _put_sh(store, sym, F.SH_FII, dict(zip(A, [8, 9, 10, 11, 12])))
    _put_sh(store, sym, F.SH_DII, dict(zip(A, [5, 5, 6, 6, 7])))
    return sym


def _by_label(section, label):
    return next(c for c in section["criteria"] if c["label"] == label)


def _section(card, name):
    return next(s for s in card["sections"] if s["name"] == name)


def test_quality_compounder_passes_core_criteria(tmp_path):
    store = _store(tmp_path)
    sym = _quality_stock(store)
    card = cv.scorecard(store, sym, ASOF)

    q = _section(card, "Quality & Returns")
    assert _by_label(q, "ROCE (return on capital)")["verdict"] == cv.PASS
    assert _by_label(q, "ROE (return on equity)")["verdict"] == cv.PASS

    b = _section(card, "Balance sheet & Cash")
    assert _by_label(b, "Debt / Equity")["verdict"] == cv.PASS
    assert _by_label(b, "Earnings quality (CFO / PAT)")["verdict"] == cv.PASS  # 110/100 = 1.1

    o = _section(card, "Management & Ownership")
    assert _by_label(o, "Promoter holding")["verdict"] == cv.PASS
    assert _by_label(o, "Promoter pledge")["verdict"] == cv.PASS

    assert card["summary"]["fail"] == 0
    assert card["red_flags"] == []
    assert "Strong long-term" in card["summary"]["headline"]


def test_de_and_earnings_quality_bands(tmp_path):
    store = _store(tmp_path)
    sym = "WEAKCO"
    _put(store, sym, F.DE_A, {A[-1]: 1.8})           # FAIL (>1)
    _put(store, sym, F.INT_COVERAGE_A, {A[-1]: 1.5})  # FAIL (<2)
    _put(store, sym, F.CFO_A, {A[-1]: 30.0})
    _put(store, sym, F.NET_PROFIT_A, {A[-1]: 100.0})  # CFO/PAT = 0.3 -> FAIL
    card = cv.scorecard(store, sym, ASOF)
    b = _section(card, "Balance sheet & Cash")
    assert _by_label(b, "Debt / Equity")["verdict"] == cv.FAIL
    assert _by_label(b, "Interest coverage")["verdict"] == cv.FAIL
    assert _by_label(b, "Earnings quality (CFO / PAT)")["verdict"] == cv.FAIL


def test_red_flags_surface_vetoes_and_pledge(tmp_path):
    store = _store(tmp_path)
    sym = "FLAGCO"
    _put_sh(store, sym, F.SH_PLEDGE, {A[-1]: 35.0})   # high pledge -> red flag
    veto = (False, ["cfo_negative_profit_positive", "manufactured_earnings"])
    technical = {"extension_vetoed": True}
    flags = cv.red_flags(store, sym, ASOF, veto=veto, technical=technical)
    names = {f["flag"] for f in flags}
    assert "cfo_negative_profit_positive" in names
    assert "manufactured_earnings" in names
    assert "parabolic_extension" in names
    assert any("pledge" in f["flag"] for f in flags)
    # every flag carries a human explanation
    assert all(f["note"] for f in flags)


def test_missing_data_is_na_not_crash(tmp_path):
    store = _store(tmp_path)
    card = cv.scorecard(store, "EMPTY", ASOF)
    # nothing ingested -> all NA, no exception, sensible headline
    assert card["summary"]["pass"] == 0
    assert card["summary"]["na"] > 0
    assert "Not enough data" in card["summary"]["headline"]


def test_implied_growth_rate_roundtrip():
    # reverse-DCF must invert the fair-P/E function it's defined against
    for g in (0.0, 0.10, 0.25):
        pe = cv._fair_pe(g, 0.125, 10, 15.0)
        assert abs(cv.implied_growth_rate(pe) - g) < 0.005
    assert cv.implied_growth_rate(None) is None
    assert cv.implied_growth_rate(-5.0) is None
    assert cv.implied_growth_rate(100000.0) == 1.0  # clamped at the hi bound


def test_pe_history_and_own_history_percentile(tmp_path):
    store = _store(tmp_path)
    sym = "HISTCO"
    # constant quarterly EPS 5 (TTM = 20) over 4 years of quarters
    quarters = [f"{y}-{m:02d}" for y in range(2023, 2027) for m in (3, 6, 9, 12)]
    _put(store, sym, F.BASIC_EPS_Q, {q: 5.0 for q in quarters})
    _put(store, sym, F.NET_PROFIT_5Y_A, {"2026-03": 20.0})
    # price grinds 100 -> 200 over 2023-2026, so today's P/E is its richest ever
    n = 1460
    px = [100.0 + 100.0 * i / (n - 1) for i in range(n)]
    daily = pd.DataFrame({
        "timestamp": pd.date_range("2023-01-01", periods=n, freq="D").astype(str),
        "low": px, "high": px, "open": px, "close": px, "volume": [1] * n,
    })

    hist = cv.pe_history(store, sym, ASOF, daily)
    assert len(hist) >= 8
    assert all(pe > 0 for _, pe in hist)
    assert hist == sorted(hist)  # ascending quarter-ends

    card = cv.scorecard(store, sym, ASOF, price=200.0, daily=daily)
    v = _section(card, "Valuation & Margin of Safety")
    own = _by_label(v, "P/E vs own 5-yr history")
    assert own["verdict"] == cv.FAIL          # richest-ever P/E -> top of own band
    assert own["raw"] > 75
    # implied growth: P/E 10 embeds roughly zero growth vs 20% delivered -> PASS
    ig = _by_label(v, "Implied growth (reverse-DCF)")
    assert ig["verdict"] == cv.PASS
    assert "priced vs 20% delivered" in ig["value"]


def test_own_history_percentile_na_when_history_thin(tmp_path):
    store = _store(tmp_path)
    sym = "THINCO"
    # only 5 quarters of EPS -> at most 2 TTM points -> percentile must be NA, not noise
    _put(store, sym, F.BASIC_EPS_Q, {q: 5.0 for q in
                                     ["2025-12", "2026-03", "2026-06", "2026-09", "2026-12"]})
    daily = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=300, freq="D").astype(str),
        "low": [100.0] * 300, "high": [100.0] * 300,
        "open": [100.0] * 300, "close": [100.0] * 300, "volume": [1] * 300,
    })
    card = cv.scorecard(store, sym, ASOF, price=100.0, daily=daily)
    v = _section(card, "Valuation & Margin of Safety")
    assert _by_label(v, "P/E vs own 5-yr history")["verdict"] == cv.NA


def test_ev_ebitda_own_history_percentile(tmp_path):
    store = _store(tmp_path)
    sym = "EVCO"
    # EV/EBITDA fell from 30x to 10x -> today is the cheapest in its own history -> PASS
    _put(store, sym, F.EV_EBITDA_A, dict(zip(A, [30.0, 25.0, 20.0, 15.0, 10.0])))
    card = cv.scorecard(store, sym, ASOF)
    v = _section(card, "Valuation & Margin of Safety")
    own = _by_label(v, "EV/EBITDA vs own history")
    assert own["verdict"] == cv.PASS
    assert own["raw"] == 0.0  # nothing in history below today's multiple


def test_dealbreaker_fail_drives_headline(tmp_path):
    store = _store(tmp_path)
    sym = _quality_stock(store, "PLEDGECO")
    # overwrite: heavy promoter pledge (dealbreaker) on an otherwise clean compounder.
    # The store is append-only vintaged, so this must be a LATER knowledge_date vintage.
    store.write_shareholding([
        {"symbol": sym, "period": p, "field": F.SH_PLEDGE, "value": 40.0,
         "knowledge_date": f"{p}-29"} for p in A])
    card = cv.scorecard(store, sym, "2026-12-31")
    assert "Promoter pledge" in card["summary"]["dealbreaker_fails"]
    assert card["summary"]["headline"].startswith("Dealbreaker risk")


def test_fcf_uses_capex_when_fixed_assets_available(tmp_path):
    store = _store(tmp_path)
    sym = "CAPEXCO"
    _put(store, sym, F.CFO_A, {A[-2]: 25.0, A[-1]: 30.0})
    _put(store, sym, F.FIXED_ASSETS_A, {A[-2]: 100.0, A[-1]: 130.0})
    _put(store, sym, F.DEPRECIATION_A, {A[-1]: 10.0})
    card = cv.scorecard(store, sym, ASOF)
    b = _section(card, "Balance sheet & Cash")
    fcf = _by_label(b, "Free cash flow (≈ CFO−capex)")
    # capex = ΔFA(30) + dep(10) = 40 > CFO 30 -> negative FCF -> WATCH, not the CFI fallback
    assert fcf["verdict"] == cv.WATCH
    assert fcf["value"] == "negative"


def test_working_capital_clean_grower(tmp_path):
    store = _store(tmp_path)
    sym = "CLEANWC"
    # receivables and WC track revenue exactly -> flat debtor days, flat intensity, no flag
    _put(store, sym, F.TOTAL_REVENUE_A, dict(zip(A, [100, 115, 132, 152, 175])))
    _put(store, sym, F.TRADE_RECEIVABLES_A, dict(zip(A, [10, 11.5, 13.2, 15.2, 17.5])))
    _put(store, sym, F.WORKING_CAPITAL_A, dict(zip(A, [20, 23, 26.4, 30.4, 35])))
    _put(store, sym, F.INVENTORY_TURNOVER_A, {p: 6.0 for p in A})
    card = cv.scorecard(store, sym, ASOF)
    w = _section(card, "Working Capital & Accruals")
    assert _by_label(w, "Debtor days trend")["verdict"] == cv.PASS
    assert _by_label(w, "Receivables vs revenue (3yr)")["verdict"] == cv.PASS
    assert _by_label(w, "Inventory turnover trend")["verdict"] == cv.PASS
    assert _by_label(w, "Working-capital intensity trend")["verdict"] == cv.PASS
    assert not any(f["flag"] == "receivables_outrunning_revenue" for f in card["red_flags"])


def test_receivables_outrunning_revenue_is_dealbreaker_and_flag(tmp_path):
    store = _store(tmp_path)
    sym = "STUFFCO"
    # revenue ~10%/yr but receivables ~60%/yr -> classic channel-stuffing signature
    _put(store, sym, F.TOTAL_REVENUE_A, dict(zip(A, [100, 110, 121, 133, 146])))
    _put(store, sym, F.TRADE_RECEIVABLES_A, dict(zip(A, [10, 16, 26, 41, 66])))
    card = cv.scorecard(store, sym, ASOF)
    w = _section(card, "Working Capital & Accruals")
    assert _by_label(w, "Receivables vs revenue (3yr)")["verdict"] == cv.FAIL
    assert _by_label(w, "Debtor days trend")["verdict"] == cv.FAIL  # days exploding too
    assert "Receivables vs revenue (3yr)" in card["summary"]["dealbreaker_fails"]
    assert any(f["flag"] == "receivables_outrunning_revenue" for f in card["red_flags"])


def test_inventory_turnover_deterioration(tmp_path):
    store = _store(tmp_path)
    sym = "PILECO"
    _put(store, sym, F.INVENTORY_TURNOVER_A, dict(zip(A, [9.0, 8.0, 7.0, 5.0, 4.0])))
    card = cv.scorecard(store, sym, ASOF)
    w = _section(card, "Working Capital & Accruals")
    assert _by_label(w, "Inventory turnover trend")["verdict"] == cv.FAIL


def test_valuation_range_position(tmp_path):
    store = _store(tmp_path)
    sym = "VALCO"
    # price near the top of a 100->200 range -> range pos high -> not PASS
    daily = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=252, freq="D").astype(str),
        "low": [100.0] * 252, "high": [200.0] * 252,
        "open": [150.0] * 252, "close": [150.0] * 252, "volume": [1] * 252,
    })
    card = cv.scorecard(store, sym, ASOF, price=190.0, daily=daily)
    v = _section(card, "Valuation & Margin of Safety")
    rp = _by_label(v, "Position in 1yr range")
    assert rp["raw"] == 90.0  # (190-100)/(200-100)
    assert rp["verdict"] == cv.FAIL  # >80
