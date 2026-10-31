"""Scoring layer: normalization helpers + composite ordering + direction flips."""

import pytest

from trader.fvm.data.store import FVMStore
from trader.fvm import scoring


# ---- normalization helpers ---------------------------------------- #

def test_percentile_scores_rank_ascending():
    sc = scoring._percentile_scores({"a": 1.0, "b": 2.0, "c": 3.0})
    assert sc["c"] > sc["b"] > sc["a"]
    assert 0.0 <= sc["a"] <= 1.0 and 0.0 <= sc["c"] <= 1.0


def test_direction_flip_lower_is_better():
    # raw debt-to-equity: lower should score higher after the 'lo' flip
    sc = scoring._normalize_factor({"low": 0.2, "high": 2.0}, "pct", "lo")
    assert sc["low"] > sc["high"]


def test_zscore_scores_monotonic_and_bounded():
    sc = scoring._zscore_scores({"a": 1.0, "b": 2.0, "c": 3.0, "d": 10.0})
    assert sc["d"] > sc["a"]
    assert all(0.0 <= v <= 1.0 for v in sc.values())


def test_missing_values_ignored_in_normalization():
    sc = scoring._percentile_scores({"a": 1.0, "b": None, "c": 3.0})
    assert "b" not in sc and set(sc) == {"a", "c"}


# ---- composite ----------------------------------------------------- #

def _full(**over):
    base = {
        "growth_acceleration": 0.0, "yoy_profit_growth": 0.0, "revenue_growth": 0.0,
        "opm_trend": 0.0, "earnings_consistency": -0.3,
        "peg": 2.5, "ev_ebitda": 20.0, "pe": 40.0,
        "cfo_to_np": 1.0, "roce": 12.0, "debt_to_equity": 0.8,
        "interest_coverage": 5.0, "debt_trend": 0.0, "roce_trend": 0.0,
        "fii_trend": 0.0, "promoter_holding": 50.0, "pledge": 5.0,
        "dii_trend": 0.0, "holders_trend": 0.0,
    }
    base.update(over)
    return base


GOOD = _full(growth_acceleration=0.5, yoy_profit_growth=0.4, revenue_growth=0.3, opm_trend=1.0,
             earnings_consistency=-0.05, peg=0.8, ev_ebitda=8, pe=15, cfo_to_np=1.8, roce=25,
             debt_to_equity=0.2, interest_coverage=12, debt_trend=-0.05, roce_trend=1.0,
             fii_trend=1.0, promoter_holding=70, pledge=0, dii_trend=0.5, holders_trend=1.0)
BAD = _full(growth_acceleration=-0.3, yoy_profit_growth=-0.2, revenue_growth=-0.1, opm_trend=-1.0,
            earnings_consistency=-0.5, peg=4.5, ev_ebitda=40, pe=80, cfo_to_np=0.3, roce=5,
            debt_to_equity=2.0, interest_coverage=1.2, debt_trend=0.2, roce_trend=-1.0,
            fii_trend=-1.0, promoter_holding=30, pledge=25, dii_trend=-0.5, holders_trend=-1.0)
MID = _full()


def test_composite_orders_good_mid_bad(tmp_path, monkeypatch):
    store = FVMStore(tmp_path / "s.db")
    store.write_sectors([{"symbol": s, "sector": "Information Technology"}
                         for s in ("GOOD", "MID", "BAD")])
    raw = {"GOOD": GOOD, "MID": MID, "BAD": BAD}
    monkeypatch.setattr(scoring.fac, "all_factors",
                        lambda store, sym, asof, price=None: dict(raw[sym]))
    res = scoring.compute_scores(store, ["GOOD", "MID", "BAD"], "2026-06-30")
    assert res["GOOD"]["composite"] > res["MID"]["composite"] > res["BAD"]["composite"]
    for r in res.values():
        assert 0.0 <= r["composite"] <= 100.0
        assert set(r["pillars"]) == set(scoring.PILLAR_WEIGHTS)
        assert all(0.0 <= v <= 1.0 for v in r["pillars"].values())
    # GOOD should dominate the earnings pillar
    assert res["GOOD"]["pillars"]["earnings"] > res["BAD"]["pillars"]["earnings"]


def test_missing_factor_scores_neutral(tmp_path, monkeypatch):
    store = FVMStore(tmp_path / "s.db")
    store.write_sectors([{"symbol": s, "sector": "IT"} for s in ("A", "B")])
    a = _full(); b = _full()
    a["pledge"] = None  # missing -> should be 0.5 for A
    monkeypatch.setattr(scoring.fac, "all_factors",
                        lambda store, sym, asof, price=None: {"A": a, "B": b}[sym])
    res = scoring.compute_scores(store, ["A", "B"], "2026-06-30")
    assert res["A"]["factors"]["pledge"] == 0.5


def test_sector_tailwind_higher_for_higher_growth_sector():
    raw = {
        "T1": {"yoy_profit_growth": 0.5}, "T2": {"yoy_profit_growth": 0.3},  # tech sector
        "P1": {"yoy_profit_growth": -0.1},                                   # pharma sector
    }
    sectors = {"T1": "Tech", "T2": "Tech", "P1": "Pharma"}
    tail = scoring._sector_tailwind(raw, sectors)
    assert tail["T1"] == tail["T2"] == pytest.approx(0.4)   # mean of 0.5, 0.3
    assert tail["P1"] == pytest.approx(-0.1)
    assert tail["T1"] > tail["P1"]
