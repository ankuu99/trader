"""NSE / niftyindices adapter — offline parse + PIT-membership tests.

All tests run with NO network: synthetic CSV / JSON fixtures drive the pure parsers and
the membership-interval builder. Live fetches (NseClient) are never exercised here; a
live smoke test would be guarded by FVM_LIVE_TESTS.
"""

import pandas as pd

from trader.fvm.data.nse import (
    apply_reconstitution_changes,
    build_membership_intervals,
    fetch_compliance_flags,
    parse_compliance_json,
    parse_constituents_csv,
    parse_index_history_csv,
)
from trader.fvm.data.store import FVMStore

_CONSTITUENTS_CSV = (
    "Company Name,Industry,Symbol,Series,ISIN Code\n"
    "Reliance Industries Ltd.,Energy,RELIANCE,EQ,INE002A01018\n"
    "Tata Consultancy Services Ltd.,IT,TCS,EQ,INE467B01029\n"
    "UltraTech Cement Ltd.,Construction,ULTRACEMCO,EQ,INE481G01011\n"
)

_INDEX_CSV = (
    "Date,Open,High,Low,Close\n"
    '01 Jan 2025,"10,000.00","10,100.00","9,950.00","10,080.50"\n'
    '02 Jan 2025,"10,080.50","10,200.00","10,050.00","10,175.25"\n'
    '03 Jan 2025,"10,175.25","10,180.00","10,000.00","10,020.00"\n'
)

_ASM_JSON = {
    "longterm": {"data": [{"symbol": "FOO", "series": "EQ"},
                          {"symbol": "BAR", "series": "EQ"}]},
    "shortterm": {"data": [{"symbol": "baz"}]},
}
_GSM_JSON = {"data": [{"symbol": "QUX"}, {"symbol": "FOO"}]}  # FOO overlaps ASM


# --- constituents ---------------------------------------------------- #

def test_parse_constituents_csv():
    syms = parse_constituents_csv(_CONSTITUENTS_CSV)
    assert syms == ["RELIANCE", "TCS", "ULTRACEMCO"]


# --- index history --------------------------------------------------- #

def test_parse_index_history_csv():
    df = parse_index_history_csv(_INDEX_CSV)
    assert list(df.columns) == ["date", "close"]
    assert len(df) == 3
    assert df["date"].iloc[0] == pd.Timestamp("2025-01-01")
    assert df["close"].iloc[0] == 10080.50          # commas stripped
    assert df["close"].iloc[-1] == 10020.00
    # sorted ascending by date
    assert df["date"].is_monotonic_increasing


# --- compliance (ASM/GSM) -------------------------------------------- #

def test_parse_compliance_json_recursive():
    asm = parse_compliance_json(_ASM_JSON)
    assert asm == {"FOO", "BAR", "BAZ"}             # nested + uppercased
    gsm = parse_compliance_json(_GSM_JSON)
    assert gsm == {"QUX", "FOO"}


def test_parse_compliance_json_accepts_raw_string():
    import json
    assert parse_compliance_json(json.dumps(_GSM_JSON)) == {"QUX", "FOO"}


def test_fetch_compliance_flags_unions_and_tolerates_failure():
    class FakeClient:
        def fetch_asm_json(self):
            return _ASM_JSON

        def fetch_gsm_json(self):
            raise RuntimeError("GSM endpoint down")   # one feed failing is tolerated

    flags = fetch_compliance_flags(client=FakeClient())
    assert flags == {"FOO", "BAR", "BAZ"}             # ASM survives, GSM skipped


# --- PIT membership intervals ---------------------------------------- #

def test_build_membership_intervals_basic():
    intervals = build_membership_intervals(
        base_members=["AAA", "BBB"],
        base_date="2024-01-01",
        changes=[
            {"date": "2024-06-01", "action": "ADD", "symbol": "CCC"},
            {"date": "2024-09-01", "action": "DROP", "symbol": "BBB"},
        ],
    )
    by_sym = {iv["symbol"]: iv for iv in intervals}
    assert by_sym["AAA"] == {"symbol": "AAA", "start_date": "2024-01-01", "end_date": None}
    assert by_sym["BBB"] == {"symbol": "BBB", "start_date": "2024-01-01",
                             "end_date": "2024-09-01"}
    assert by_sym["CCC"] == {"symbol": "CCC", "start_date": "2024-06-01", "end_date": None}


def test_build_membership_intervals_readd_creates_two_intervals():
    intervals = build_membership_intervals(
        base_members=["AAA"],
        base_date="2024-01-01",
        changes=[
            {"date": "2024-03-01", "action": "DROP", "symbol": "AAA"},
            {"date": "2024-08-01", "action": "ADD", "symbol": "AAA"},
        ],
    )
    aaa = sorted((iv for iv in intervals if iv["symbol"] == "AAA"),
                 key=lambda iv: iv["start_date"])
    assert aaa == [
        {"symbol": "AAA", "start_date": "2024-01-01", "end_date": "2024-03-01"},
        {"symbol": "AAA", "start_date": "2024-08-01", "end_date": None},
    ]


def test_apply_reconstitution_then_pit_read(tmp_path):
    store = FVMStore(tmp_path / "fvm.db")
    apply_reconstitution_changes(
        store, "NIFTY500",
        base_members=["AAA", "BBB"],
        base_date="2024-01-01",
        changes=[
            {"date": "2024-06-01", "action": "ADD", "symbol": "CCC"},
            {"date": "2024-09-01", "action": "DROP", "symbol": "BBB"},
        ],
    )
    # PIT membership queries through the store
    assert store.members_asof("NIFTY500", "2024-02-01") == ["AAA", "BBB"]
    assert store.members_asof("NIFTY500", "2024-07-01") == ["AAA", "BBB", "CCC"]
    # BBB dropped on 2024-09-01 -> gone the day of the drop
    assert store.members_asof("NIFTY500", "2024-10-01") == ["AAA", "CCC"]
