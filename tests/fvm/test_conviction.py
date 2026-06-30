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
