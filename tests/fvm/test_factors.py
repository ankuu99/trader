"""Factor engine: primitives + Pillar 1 (incl. floored-YoY floor) / 3 / 4."""

import math

import pytest

from trader.fvm.data.store import FVMStore
from trader.fvm import factors as fac
from trader.fvm import fields as F

ASOF = "2026-12-31"
Q = ["2024-03", "2024-06", "2024-09", "2024-12",
     "2025-03", "2025-06", "2025-09", "2025-12", "2026-03"]


def _put(store, symbol, spec, by_period, basis="consolidated"):
    statement, field = spec
    rows = [{"symbol": symbol, "statement": statement, "basis": basis, "period": p,
             "field": field, "value": v, "knowledge_date": f"{p}-28"}
            for p, v in by_period.items()]
    store.write_fundamentals(rows)


def _put_sh(store, symbol, field, by_period):
    store.write_shareholding([
        {"symbol": symbol, "period": p, "field": field, "value": v,
         "knowledge_date": f"{p}-28"} for p, v in by_period.items()])


# ---- primitives ---------------------------------------------------- #

def test_slope_and_winsorize():
    assert fac.slope([1, 2, 3, 4]) == pytest.approx(1.0)
    assert fac.slope([4, 3, 2, 1]) == pytest.approx(-1.0)
    assert fac.slope([5]) is None
    assert fac.winsorize(9.0) == 2.0
    assert fac.winsorize(-9.0) == -2.0
    assert fac.winsorize(0.5) == 0.5


def test_quarter_arithmetic():
    assert fac._q_index("2026-03") - fac._q_index("2025-03") == 4   # one year = 4 quarters
    assert fac._q_index("2026-06") - fac._q_index("2026-03") == 1
    assert fac._year_ago("2026-03") == "2025-03"


def test_floored_yoy_floor_prevents_tiny_base_explosion(tmp_path):
    s = FVMStore(tmp_path / "f.db")
    # tiny base (5) -> without the floor, growth explodes; floor = 1% of TTM revenue
    np_q = {"2025-03": 5, "2025-06": 5, "2025-09": 5, "2025-12": 5, "2026-03": 45}
    rev_q = {p: 1000 for p in np_q}  # TTM at 2026-03 = 4*1000=4000 -> floor=40
    _put(s, "TINY", F.NET_PROFIT_Q, np_q)
    _put(s, "TINY", F.TOTAL_REVENUE_Q, rev_q)
    g = dict(fac.floored_yoy_series(s, "TINY", ASOF))
    # base 2025-03 = 5; denom = max(5, 40) = 40 -> (45-5)/40 = 1.0  (NOT 8.0)
    assert g["2026-03"] == pytest.approx(1.0)


def test_pillar1_acceleration_positive_on_accelerating_profits(tmp_path):
    s = FVMStore(tmp_path / "f.db")
    np_q = {"2024-03": 100, "2024-06": 100, "2024-09": 100, "2024-12": 100,
            "2025-03": 120, "2025-06": 135, "2025-09": 155, "2025-12": 180, "2026-03": 220}
    _put(s, "ACC", F.NET_PROFIT_Q, np_q)
    _put(s, "ACC", F.TOTAL_REVENUE_Q, {p: 1000 for p in np_q})
    _put(s, "ACC", F.OPM_Q, {p: v for p, v in zip(Q, [16, 16, 17, 17, 18, 18, 19, 20, 22])})
    _put(s, "ACC", F.REVENUE_GROWTH_Q, {"2026-03": 12.0})
    f = fac.pillar1_factors(s, "ACC", ASOF)
    assert f["growth_acceleration"] > 0          # YoY growth rate is rising
    assert f["yoy_profit_growth"] == pytest.approx((220 - 120) / 120)   # floor inert (base 120>40)
    assert f["opm_trend"] > 0                     # margins improving
    assert f["revenue_growth"] == pytest.approx(0.12)
    assert f["earnings_consistency"] < 0          # it's -dispersion


def test_pillar1_missing_history_is_neutral_none(tmp_path):
    s = FVMStore(tmp_path / "f.db")
    # only 2 quarters of profit, no year-ago base -> acceleration must be None (neutral later)
    _put(s, "NEW", F.NET_PROFIT_Q, {"2026-03": 50})
    _put(s, "NEW", F.TOTAL_REVENUE_Q, {"2026-03": 500})
    f = fac.pillar1_factors(s, "NEW", ASOF)
    assert f["growth_acceleration"] is None
    assert f["yoy_profit_growth"] is None


def test_pillar3_factors(tmp_path):
    s = FVMStore(tmp_path / "f.db")
    yrs = ["2024-03", "2025-03", "2026-03"]
    _put(s, "BS", F.CFO_A, {"2026-03": 1500})
    _put(s, "BS", F.NET_PROFIT_A, {"2026-03": 1000})
    _put(s, "BS", F.DE_A, dict(zip(yrs, [0.5, 0.45, 0.4])))   # falling D/E (deleveraging)
    _put(s, "BS", F.INT_COVERAGE_A, {"2026-03": 8.0})
    _put(s, "BS", F.ROCE_A, dict(zip(yrs, [12, 13, 14])))
    f = fac.pillar3_factors(s, "BS", ASOF)
    assert f["cfo_to_np"] == pytest.approx(1.5)
    assert f["debt_to_equity"] == pytest.approx(0.4)        # latest
    assert f["interest_coverage"] == pytest.approx(8.0)
    assert f["roce"] == pytest.approx(14)
    assert f["roce_trend"] > 0          # rising ROCE
    assert f["debt_trend"] < 0          # falling D/E (0.5 -> 0.45 -> 0.4)


def test_pillar4_factors(tmp_path):
    s = FVMStore(tmp_path / "f.db")
    qs = ["2025-06", "2025-09", "2025-12", "2026-03"]
    _put_sh(s, "OWN", F.SH_FII, dict(zip(qs, [15, 16, 17, 18])))
    _put_sh(s, "OWN", F.SH_DII, dict(zip(qs, [14, 13, 12, 11])))
    _put_sh(s, "OWN", F.SH_PROMOTER, dict(zip(qs, [60, 60, 60, 60])))
    _put_sh(s, "OWN", F.SH_PLEDGE, dict(zip(qs, [3, 2, 2, 1])))
    _put_sh(s, "OWN", F.SH_HOLDERS, dict(zip(qs, [1000, 1100, 1200, 1300])))
    f = fac.pillar4_factors(s, "OWN", ASOF)
    assert f["fii_trend"] > 0
    assert f["dii_trend"] < 0
    assert f["promoter_holding"] == pytest.approx(60)
    assert f["pledge"] == pytest.approx(1)
    assert f["holders_trend"] > 0
