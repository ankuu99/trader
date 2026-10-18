"""Model Lab L0a: parquet bar store, PIT universe, fetch helpers, QA. No network, no real market.db."""
import sqlite3
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from research.model_lab import fetch, paths, qa, store, universe


@pytest.fixture(autouse=True)
def lab_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "BARS_DIR", tmp_path / "bars")
    monkeypatch.setattr(paths, "UNIVERSE_DIR", tmp_path / "universe")
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(paths, "LAB_ROOT", tmp_path)
    return tmp_path


def _bars(stamps, price=100.0, vol=10):
    return pd.DataFrame({"timestamp": stamps, "open": price, "high": price + 1, "low": price - 1,
                         "close": price, "volume": vol})


def test_clean_bars_drops_offgrid_15m():
    stamps = ["2025-01-01 09:15", "2025-01-01 09:20", "2025-01-01 12:45", "2025-01-01 15:15",
              "2025-01-01 15:16", "2025-01-01 15:25", "2025-01-01 15:30", "2025-01-01 09:00",
              "2025-01-01 12:45"]
    df = _bars(stamps)
    df.loc[8, "close"] = 105.0
    out = store.clean_bars(df, "15minute")
    assert [t.strftime("%H:%M") for t in out["timestamp"]] == ["09:15", "12:45", "15:15"]
    assert out.loc[out["timestamp"].dt.strftime("%H:%M") == "12:45", "close"].iloc[0] == 105.0


def test_clean_bars_tz_aware_to_naive_ist():
    df = _bars(["2025-01-01 09:15:00+05:30"])
    out = store.clean_bars(df, "15minute")
    assert out["timestamp"].iloc[0] == pd.Timestamp("2025-01-01 09:15")
    assert out["timestamp"].dt.tz is None


def test_write_read_roundtrip_and_merge():
    a = _bars(pd.date_range("2025-01-01", periods=5, freq="D"))
    b = _bars(pd.date_range("2025-01-04", periods=5, freq="D"), price=200.0)
    store.write_bars("NSE:AAA", "day", a)
    n = store.write_bars("NSE:AAA", "day", b)
    got = store.read_bars("NSE:AAA", "day")
    assert n == len(got) == 8
    assert got["timestamp"].is_monotonic_increasing and not got["timestamp"].duplicated().any()
    assert got.loc[got["timestamp"] == "2025-01-04", "close"].iloc[0] == 200.0
    assert store.coverage("NSE:AAA", "day") == (pd.Timestamp("2025-01-01"), pd.Timestamp("2025-01-08"))
    assert store.list_symbols("day") == ["NSE:AAA"]
    assert len(store.read_bars("NSE:AAA", "day", start="2025-01-03", end="2025-01-05")) == 3
    assert store.read_bars("NSE:NOPE", "day").empty


def test_write_is_atomic_temp_cleanup():
    store.write_bars("NSE:AAA", "day", _bars(pd.date_range("2025-01-01", periods=3)))
    store.update_manifest("day", "NSE:AAA", datetime(2025, 1, 1), datetime(2025, 1, 3))
    names = [p.name for p in (paths.BARS_DIR / "day").iterdir()]
    assert sorted(names) == ["AAA.parquet", "_manifest.json"]


def test_manifest_widens_only():
    store.update_manifest("day", "NSE:A", datetime(2020, 1, 1), datetime(2024, 1, 1))
    store.update_manifest("day", "NSE:A", datetime(2021, 1, 1), datetime(2023, 1, 1))
    m = store.load_manifest("day")["NSE:A"]
    assert (m["from"], m["to"]) == ("2020-01-01T00:00:00", "2024-01-01T00:00:00")
    store.update_manifest("day", "NSE:A", datetime(2019, 1, 1), datetime(2025, 1, 1))
    m = store.load_manifest("day")["NSE:A"]
    assert (m["from"], m["to"]) == ("2019-01-01T00:00:00", "2025-01-01T00:00:00")
    assert store.load_manifest("15minute") == {}


def test_gap_ranges():
    f, t = datetime(2020, 1, 1), datetime(2024, 1, 1)
    assert fetch.gap_ranges(None, f, t) == [(f, t)]
    e = {"from": "2020-01-01T00:00:00", "to": "2024-01-01T00:00:00"}
    assert fetch.gap_ranges(e, f, t) == []
    e2 = {"from": "2022-01-01T00:00:00", "to": "2024-01-01T00:00:00"}
    r = fetch.gap_ranges(e2, f, t)
    assert len(r) == 1 and r[0][0] == f and r[0][1] < datetime(2022, 1, 1)
    e3 = {"from": "2020-01-01T00:00:00", "to": "2022-01-01T00:00:00"}
    r = fetch.gap_ranges(e3, f, t)
    assert len(r) == 1 and r[0][1] == t and r[0][0] > datetime(2022, 1, 1)
    e4 = {"from": "2021-01-01T00:00:00", "to": "2022-01-01T00:00:00"}
    assert len(fetch.gap_ranges(e4, f, t)) == 2
    e5 = {"from": "2020-01-01T12:00:00", "to": "2023-12-31T12:00:00"}
    assert fetch.gap_ranges(e5, f, t) == []


def _days(n=300, vol=100):
    return _bars(pd.bdate_range("2023-01-02", periods=n), vol=vol)


def test_liquidity_panel_is_pit():
    d = _days()
    store.write_bars("NSE:AAA", "day", d)
    p1 = universe.build_liquidity_panel().set_index("date")
    d2 = d.copy()
    D = d2["timestamp"].iloc[250]
    d2.loc[250, "volume"] = 10 ** 9
    store.write_bars("NSE:AAA", "day", d2)
    p2 = universe.build_liquidity_panel().set_index("date")
    assert p1.loc[D, "med_tv_252"] == p2.loc[D, "med_tv_252"]
    nxt = d2["timestamp"].iloc[251]
    assert p1.loc[nxt, "n_sessions"] == 251
    assert (paths.UNIVERSE_DIR / "liquidity_daily.parquet").exists()


def test_liquid_universe_strictly_before_asof():
    dates = pd.bdate_range("2023-01-02", periods=300)
    asof = dates[-1]

    def mk(sym, med, upto=None):
        ds = dates if upto is None else dates[dates <= upto]
        return pd.DataFrame({"date": ds, "symbol": sym, "med_tv_252": med, "n_sessions": 250})
    spike = mk("NSE:SPIKE", 1.0)
    spike.loc[spike["date"] == asof, "med_tv_252"] = 1e12
    panel = pd.concat([
        mk("NSE:BIG", 100.0), mk("NSE:MID", 50.0), spike,
        mk("NSE:STALE", 1000.0, upto=asof - pd.Timedelta(days=20)),
        mk("NSE:NIFTY 50", 1e9), mk("NSE:INDIA VIX", 1e9),
    ], ignore_index=True)
    assert universe.liquid_universe(asof, 3, panel) == ["NSE:BIG", "NSE:MID", "NSE:SPIKE"]
    assert universe.liquid_universe(asof, 1, panel) == ["NSE:BIG"]
    assert universe.intraday_fetch_list([2024], 2, panel) == ["NSE:BIG", "NSE:STALE"]  # STALE still trading on 2024-01-01


class _FakeKite:
    def instruments(self, ex):
        def r(ts, name="X CO", seg="NSE", typ="EQ"):
            return {"tradingsymbol": ts, "name": name, "segment": seg, "instrument_type": typ,
                    "instrument_token": 1, "lot_size": 1, "tick_size": 0.05}
        return [r("AAA"), r("BBB-BE"), r("NIFTYBEES"), r("CCC", name="Foo Nifty ETF"),
                r("DDD", seg="INDICES", typ="INDEX"), r("EEE", typ="BE"), r("GOLDIETF"),
                r("FFF", name="Bar Ltd")]


def test_snapshot_filters():
    df = universe.snapshot_instruments(_FakeKite())
    assert df["symbol"].tolist() == ["NSE:AAA", "NSE:FFF"]
    assert list(df.columns) == ["symbol", "tradingsymbol", "instrument_token", "name", "lot_size", "tick_size"]
    assert not universe.latest_snapshot().empty


def test_seed_reads_market_db_readonly(tmp_path):
    db = tmp_path / "src.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE candles (instrument TEXT, timeframe TEXT, timestamp TEXT, open REAL,
        high REAL, low REAL, close REAL, volume INTEGER, PRIMARY KEY (instrument, timeframe, timestamp))""")
    rows = [("NSE:AAA", "15minute", ts, 10, 11, 9, 10, 5) for ts in
            ("2025-01-01T09:15:00", "2025-01-01T09:30:00", "2025-01-01T15:16:00")]
    rows += [("NSE:AAA", "day", "2025-01-01T00:00:00", 10, 11, 9, 10, 5),
             ("NSE:AAA", "5minute", "2025-01-01T09:15:00", 10, 11, 9, 10, 5)]
    conn.executemany("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()
    before = db.read_bytes()
    totals = fetch.seed(db)
    assert db.read_bytes() == before
    assert totals == {"15minute": 2, "day": 1}
    assert len(store.read_bars("NSE:AAA", "15minute")) == 2
    assert store.list_symbols("5minute") == []
    m = store.load_manifest("15minute")["NSE:AAA"]
    assert m["from"].startswith("2025-01-01T09:15") and m["to"].startswith("2025-01-01T09:30")


def test_qa_flags_jump():
    ds = pd.bdate_range("2024-01-01", periods=10)
    df = _bars(ds)
    df.loc[5:, ["open", "high", "low", "close"]] = [150.0, 151, 149, 150]
    store.write_bars("NSE:JMP", "day", df)
    store.write_bars("NSE:OK", "day", _bars(ds))
    rep = qa.qa_report("day")
    top = rep.iloc[0]
    assert top["symbol"] == "NSE:JMP" and top["max_jump_ts"] == ds[5]
    assert abs(top["max_jump_pct"] - 50.0) < 1e-6 and top["n_jumps_30"] == 1
    assert rep.set_index("symbol").loc["NSE:OK", "n_jumps_30"] == 0
