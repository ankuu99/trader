"""Tests for the Trendlyne Data-Downloader snapshot layer (trader/fvm/data/snapshot.py)."""

import pandas as pd
import pytest

from trader.fvm import conviction as cv
from trader.fvm.data import snapshot as snap
from trader.fvm.data.store import FVMStore


def _make_xlsx(path, rows):
    """Write a minimal Data-Downloader-shaped xlsx. `rows` = list of dicts keyed by the
    real excel column headers (missing columns fine — they read back as None)."""
    df = pd.DataFrame(rows)
    df.to_excel(path, index=False)


GOOD_ROW = {
    "NSEcode": "GOODCO", "Stock Name": "Good Co", "sector_name": "FMCG",
    "Industry Name": "Foods", "DVM_classification_text": "Strong Performer",
    "Current Price": 100.0, "Market Capitalization": 5000.0,
    "Trendlyne Durability Score": 80.0, "Trendlyne Valuation Score": 55.0,
    "Trendlyne Momentum Score": 60.0, "Piotroski Score": 8.0, "ROE Annual %": 20.0,
    "Promoter holding pledge percentage % Qtr": 0.0,
    "Cash from Operating Activity Annual": 400.0,
    "Promoter holding change 4Qtr %": 0.5, "MF holding change QoQ %": 0.4,
    "FII holding change QoQ %": 0.1, "PE TTM Price to Earnings": 20.0,
    "Industry PE TTM": 30.0, "Day SMA200": 90.0,
    "3Month Volume Avg": 200000.0,  # 100 × 200k / 1e5 = ₹200L/day turnover
}

BAD_ROW = {
    "NSEcode": "BADCO", "Stock Name": "Bad Co", "sector_name": "Realty",
    "DVM_classification_text": "Momentum Trap",
    "Current Price": 50.0, "Market Capitalization": 900.0,
    "Trendlyne Durability Score": 35.0, "Trendlyne Momentum Score": 70.0,
    "Piotroski Score": 2.0, "ROE Annual %": 4.0,
    "Promoter holding pledge percentage % Qtr": 40.0,
    "Cash from Operating Activity Annual": -50.0,
    "Promoter holding change 4Qtr %": -6.0, "MF holding change QoQ %": -1.0,
    "FII holding change QoQ %": -1.2, "%Days traded below current PE Price to Earnings": 99.0,
    "Day SMA200": 60.0, "3Month Volume Avg": 500000.0,
    "Forecaster Estimates 1Y forward PE": "Export NA",
}


@pytest.fixture
def store(tmp_path):
    return FVMStore(tmp_path / "fvm.db")


def test_asof_from_filename():
    assert snap.asof_from_filename("Stocks-data-IND-3-Jul-2026.xlsx") == "2026-07-03"
    assert snap.asof_from_filename("Stocks-data-IND-28-Dec-2025.xlsx") == "2025-12-28"
    assert snap.asof_from_filename("random.xlsx") is None


def test_ingest_and_read(store, tmp_path):
    f = tmp_path / "Stocks-data-IND-3-Jul-2026.xlsx"
    _make_xlsx(f, [GOOD_ROW, BAD_ROW])
    as_of, n = snap.ingest_snapshot(store, f)
    assert (as_of, n) == ("2026-07-03", 2)

    row = snap.read_snapshot(store, "NSE:GOODCO")
    assert row["as_of"] == "2026-07-03"
    assert row["durability"] == 80.0
    assert row["dvm_class"] == "Strong Performer"
    # missing column -> None; 'Export NA' -> None
    assert row["rsi_day"] is None
    bad = snap.read_snapshot(store, "BADCO")
    assert bad["pledge"] == 40.0

    # PIT-style read: nothing knowable before the vintage
    assert snap.read_snapshot(store, "GOODCO", asof="2026-07-02") is None
    # idempotent re-ingest
    snap.ingest_snapshot(store, f)
    assert len(snap.read_universe(store)) == 2


def test_snapshots_stack_into_history(store, tmp_path):
    f1 = tmp_path / "Stocks-data-IND-3-Jul-2026.xlsx"
    _make_xlsx(f1, [GOOD_ROW])
    snap.ingest_snapshot(store, f1)
    week2 = dict(GOOD_ROW, **{"Trendlyne Durability Score": 85.0})
    f2 = tmp_path / "Stocks-data-IND-10-Jul-2026.xlsx"
    _make_xlsx(f2, [week2])
    snap.ingest_snapshot(store, f2)

    assert snap.snapshot_dates(store) == ["2026-07-03", "2026-07-10"]
    hist = snap.snapshot_history(store, "GOODCO", ["durability"])
    assert [(h["as_of"], h["durability"]) for h in hist] == \
        [("2026-07-03", 80.0), ("2026-07-10", 85.0)]
    # asof pins the vintage
    assert snap.read_snapshot(store, "GOODCO", asof="2026-07-05")["durability"] == 80.0
    assert snap.read_snapshot(store, "GOODCO")["durability"] == 85.0


def test_quality_screen_funnel(store, tmp_path):
    f = tmp_path / "Stocks-data-IND-3-Jul-2026.xlsx"
    _make_xlsx(f, [GOOD_ROW, BAD_ROW])
    snap.ingest_snapshot(store, f)
    survivors, funnel = snap.quality_screen(snap.read_universe(store))
    assert [r["symbol"] for r in survivors] == ["GOODCO"]
    assert funnel[0][1] == 2       # both pass liquidity
    assert funnel[-1][1] == 1      # only GOODCO survives the full funnel


def test_watchlist_flags():
    good = {"pledge": 0.0, "piotroski": 8, "durability": 80, "mf_chg_qoq": 0.4,
            "fii_chg_qoq": 0.1, "pct_days_below_pe": 50, "dvm_class": "Strong Performer",
            "promoter_chg_4q": 0.5}
    assert snap.watchlist_flags(good) == []
    bad = {"pledge": 40.0, "piotroski": 2, "durability": 35, "mf_chg_qoq": -1.0,
           "fii_chg_qoq": -1.2, "pct_days_below_pe": 99, "dvm_class": "Momentum Trap",
           "promoter_chg_4q": -6.0}
    flags = " | ".join(snap.watchlist_flags(bad))
    for expect in ("HIGH pledge", "promoter −6.0pp", "Piotroski 2", "Durability 35",
                   "institutions exiting", "99th pctile", "Momentum Trap"):
        assert expect in flags


def test_conviction_snapshot_section(store):
    row = {"as_of": "2026-07-03", "piotroski": 8.0, "durability": 80.0,
           "dvm_class": "Strong Performer", "mf_chg_qoq": 0.4, "fii_chg_qoq": 0.1,
           "pledge": 0.0, "pct_days_below_pe": 30.0}
    card = cv.scorecard(store, "GOODCO", "2026-07-03", snapshot=row)
    sec = [s for s in card["sections"] if s["name"].startswith("Market Intelligence")]
    assert len(sec) == 1
    verdicts = {c["label"]: c["verdict"] for c in sec[0]["criteria"]}
    assert verdicts["Piotroski score"] == cv.PASS
    assert verdicts["DVM classification"] == cv.PASS
    assert verdicts["Promoter pledge (snapshot)"] == cv.PASS
    # without snapshot the section is absent (PIT replay path)
    card2 = cv.scorecard(store, "GOODCO", "2026-07-03")
    assert not any(s["name"].startswith("Market Intelligence") for s in card2["sections"])
