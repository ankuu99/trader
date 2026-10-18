"""Model Lab L0c: NSE bhavcopy day source (TD-022). Synthetic zips only — no network, no real lab_data."""
import io
import zipfile
from datetime import date

import numpy as np
import pandas as pd
import pytest

from research.model_lab import bars, factors, nse_bhav as nb, paths, score, source, splits, store, synth, targets, universe

OLD_HDR = "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN,"
OLD_HDR_2008 = "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,"
UD_HDR = ("TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,"
          "StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,"
          "SttlmPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd")


@pytest.fixture(autouse=True)
def lab_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "BARS_DIR", tmp_path / "bars")
    monkeypatch.setattr(paths, "UNIVERSE_DIR", tmp_path / "universe")
    monkeypatch.setattr(paths, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(paths, "LAB_ROOT", tmp_path)
    monkeypatch.setattr(paths, "NSE_BHAV_DIR", tmp_path / "nse_bhav")
    monkeypatch.setattr(nb, "REQ_INTERVAL", 0.0)
    return tmp_path


def _zip(text: str, name="x.csv") -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr(name, text)
    return b.getvalue()


def _old(rows, hdr=OLD_HDR):
    return _zip(hdr + "\n" + "\n".join(rows) + "\n")


def _ud(rows):
    return _zip(UD_HDR + "\n" + "\n".join(rows) + "\n")


def _udrow(tp, isin, sym, ser, o, h, l, c, pc, vol=100, val=1000, n=5):
    return (f"2024-07-08,2024-07-08,CM,NSE,{tp},1,{isin},{sym},{ser},,,,,{sym} LTD,{o},{h},{l},{c},{c},{pc},,,,,"
            f"{vol},{val},{n}")


def test_parse_old_and_udiff_formats():
    z = _old(["AAA,EQ,10,11,9,10.5,10.5,10,100,1000,02-JAN-2012,7,INE001A01010,",
              "BBB,BE,20,21,19,20,20,20,50,500,02-JAN-2012,3,INE002A01010,",
              "CCC,BZ,5,6,4,5,5,5,10,50,02-JAN-2012,1,INE003A01010,",
              "DDD,SM,5,6,4,5,5,5,10,50,02-JAN-2012,1,INE004A01010,",
              "BAD,EQ,5,6,4,9,5,5,10,50,02-JAN-2012,1,INE005A01010,",       # close above high
              "ZER,EQ,0,6,4,5,5,5,10,50,02-JAN-2012,1,INE006A01010,"])      # non-positive open
    df, dropped = nb.parse_zip(z, date(2012, 1, 2))
    assert list(df.columns) == nb.PANEL_COLS
    assert df["symbol"].tolist() == ["AAA", "BBB", "CCC"] and df["series"].tolist() == ["EQ", "BE", "BZ"]
    assert dropped == 2
    r = df.iloc[0]
    assert r["date"] == pd.Timestamp("2012-01-02") and r["isin"] == "INE001A01010"
    assert (r["open"], r["high"], r["low"], r["close"], r["prevclose"]) == (10, 11, 9, 10.5, 10)
    assert r["volume"] == 100 and r["value"] == 1000 and r["trades"] == 7

    z08 = _old(["AAA,EQ,10,11,9,10.5,10.5,10,100,1000,02-JAN-2008"], OLD_HDR_2008)
    df8, _ = nb.parse_zip(z08, date(2008, 1, 2))
    assert len(df8) == 1 and df8["isin"].iloc[0] is None and np.isnan(df8["trades"].iloc[0])

    zu = _ud([_udrow("STK", "INE001A01010", "AAA", "EQ", 10, 11, 9, 10.5, 10),
              _udrow("ETF", "INE777A01010", "ETFX", "EQ", 10, 11, 9, 10.5, 10),
              _udrow("STK", "INE002A01010", "BBB", "N1", 10, 11, 9, 10.5, 10),
              _udrow("STK", "INE003A01010", "CCC", "BE", 10, 11, 9, 10.5, 10)])
    du, _ = nb.parse_zip(zu, date(2024, 7, 8))
    assert du["symbol"].tolist() == ["AAA", "CCC"]
    assert du["volume"].iloc[0] == 100 and du["value"].iloc[0] == 1000 and du["trades"].iloc[0] == 5


def test_url_for_date_and_fallback(monkeypatch):
    assert nb.url_for(date(2012, 1, 2), "old") == (
        "https://nsearchives.nseindia.com/content/historical/EQUITIES/2012/JAN/cm02JAN2012bhav.csv.zip")
    assert nb.url_for(date(2024, 7, 8), "udiff").endswith("BhavCopy_NSE_CM_0_0_0_20240708_F_0000.csv.zip")
    assert nb.formats_for(date(2024, 7, 5)) == ["old", "udiff"]
    assert nb.formats_for(date(2024, 7, 8)) == ["udiff", "old"]

    calls = []
    zbytes = _zip("a")

    def get(url):
        calls.append(url)
        return (200, zbytes) if "bhav.csv.zip" in url else (404, b"")
    monkeypatch.setattr(nb, "_http_get", get)
    assert nb.fetch_date(date(2024, 7, 8)) == "ok"          # udiff 404 -> old tried once
    assert len(calls) == 2 and nb.raw_path(date(2024, 7, 8)).exists()

    calls.clear()
    assert nb.fetch_date(date(2024, 7, 8)) == "exists" and calls == []     # resumable

    monkeypatch.setattr(nb, "_http_get", lambda url: (calls.append(url) or (404, b"")))
    assert nb.fetch_date(date(2012, 1, 26)) == "holiday_or_missing"
    assert len(calls) == 2 and not nb.raw_path(date(2012, 1, 26)).exists()
    log = pd.read_csv(paths.NSE_BHAV_DIR / "fetch_log.csv", dtype=str)
    assert "holiday_or_missing" in log["status"].tolist()

    monkeypatch.setattr(nb, "_http_get", lambda url: (_ for _ in ()).throw(RuntimeError("boom")))
    assert nb.fetch_date(date(2012, 1, 27)) == "error"      # never raises
    assert nb.weekdays(date(2024, 7, 5), date(2024, 7, 9)) == [date(2024, 7, 5), date(2024, 7, 8), date(2024, 7, 9)]


def _row(d, sym, isin, close, prevclose=None, series="EQ", volume=100):
    return {"date": pd.Timestamp(d), "symbol": sym, "series": series, "isin": isin, "open": close,
            "high": close + 0.5, "low": close - 0.5, "close": close,
            "prevclose": close if prevclose is None else prevclose, "volume": volume, "value": 1.0, "trades": np.nan}


def test_security_chain_rename_isin_change_and_pre_isin():
    rows = []
    # rename with same ISIN
    rows += [_row("2020-01-01", "OLDN", "INE1", 100), _row("2020-01-02", "NEWN", "INE1", 101)]
    # ISIN change same symbol next day
    rows += [_row("2020-01-01", "CHG", "INE2A", 50), _row("2020-01-02", "CHG", "INE2B", 51)]
    # pre-ISIN 2008-style rows joined to later ISIN
    rows += [_row("2008-01-02", "OLDY", None, 10), _row("2008-01-03", "OLDY", None, 11),
             _row("2008-01-04", "OLDY", "INE3", 12)]
    # symbol reused after a 60-day gap by a different ISIN
    rows += [_row("2015-01-01", "REU", "INE4A", 20), _row("2015-03-10", "REU", "INE4B", 30)]
    # EQ + BE same day -> EQ kept
    rows += [_row("2021-05-03", "DUP", "INE5", 70, series="BE"), _row("2021-05-03", "DUP", "INE5", 71, series="EQ")]
    p = nb.assign_securities(pd.DataFrame(rows))
    sec = lambda sym, d: p[(p["symbol"] == sym) & (p["date"] == d)]["sec"].iloc[0]       # noqa: E731
    assert sec("OLDN", pd.Timestamp("2020-01-01")) == sec("NEWN", pd.Timestamp("2020-01-02"))
    assert sec("CHG", pd.Timestamp("2020-01-01")) == sec("CHG", pd.Timestamp("2020-01-02"))
    assert p[p["symbol"] == "OLDY"]["sec"].nunique() == 1
    assert sec("REU", pd.Timestamp("2015-01-01")) != sec("REU", pd.Timestamp("2015-03-10"))
    dup = p[p["symbol"] == "DUP"]
    assert len(dup) == 1 and dup["series"].iloc[0] == "EQ" and dup["close"].iloc[0] == 71
    t = nb.security_table(p, pd.Timestamp("2021-05-03"))
    oldy = t[t["last_symbol"] == "OLDY"].iloc[0]
    assert oldy["sec_id"] == "INE3" and oldy["first_date"] == pd.Timestamp("2008-01-02")
    assert t[t["last_symbol"] == "NEWN"].iloc[0]["symbols"].startswith("OLDN:2020-01-01:2020-01-01;NEWN")
    assert len(t) == 6 and t["delisted"].sum() == 5          # only DUP is within 30d of the panel end


def _series(sec_rows):
    return pd.DataFrame(sec_rows)


def _adj_input():
    days = pd.bdate_range("2022-01-03", periods=8)
    closes = [100, 101, 102, 20.4, 20.5, 10.25, 10.3, 10.2]          # 1:5 split at idx3, 1:1 bonus at idx5
    prevs = [100, 100, 101, 102 / 5, 20.4, 20.5 / 2, 10.25, 10.3]    # idx1 prev=100 -> tiny ignored move
    prevs[1] = 100.0
    rows = []
    for i, (d, c, pc) in enumerate(zip(days, closes, prevs)):
        r = _row(d, "AAA", "INE9", c, pc, volume=1000)
        r["sec"] = 0
        rows.append(r)
    # small moves: idx 6 prevclose 10.25 vs close 10.25 same; add 1.5% mismatch
    rows[7]["prevclose"] = 10.3 * 1.015
    return pd.DataFrame(rows)


def test_adjustment_split_and_bonus():
    adj, ca = nb.adjust(_adj_input())
    assert len(ca) == 2 and ca["f"].round(6).tolist() == [0.2, 0.5]
    c = adj["close"].to_numpy()
    assert c[-1] == pytest.approx(10.2)                              # last row unadjusted
    assert c[2] == pytest.approx(102 / 10) and c[3] == pytest.approx(20.4 / 2)   # continuous across ex-dates
    assert c[4] == pytest.approx(20.5 / 2) and c[5] == pytest.approx(10.25)
    assert adj["volume"].tolist()[:3] == [10000] * 3 and adj["volume"].tolist()[3:5] == [2000] * 2
    assert adj["volume"].tolist()[5:] == [1000] * 3
    assert adj["adj"].iloc[-1] == 1.0                                # 1.5% prevclose gap ignored


def test_build_writes_bars_and_indices(monkeypatch):
    # two securities sharing a last symbol (earlier one delisted), one live; kite index bars present
    days1 = pd.bdate_range("2020-01-01", periods=40)
    days2 = pd.bdate_range("2021-06-01", periods=40)
    rows = [_row(d, "SAME", "INEOLD", 10 + i * 0.01) for i, d in enumerate(days1)]
    rows += [_row(d, "SAME", "INENEW", 20 + i * 0.01) for i, d in enumerate(days2)]
    rows += [_row(d, "LIVE", "INELIVE", 30) for d in days2]
    panel = pd.DataFrame(rows)
    # same symbol reused >30d later by different ISIN => two securities with last symbol SAME
    (paths.NSE_BHAV_DIR / "panel").mkdir(parents=True)
    panel.to_parquet(paths.NSE_BHAV_DIR / "panel" / "all.parquet")
    for ix in ("NSE:NIFTY 50", "NSE:INDIA VIX"):
        store.write_bars(ix, "day", pd.DataFrame({"timestamp": days2, "open": 100.0, "high": 101.0,
                                                  "low": 99.0, "close": 100.0, "volume": 0}))
    res = nb.build()
    assert res["securities"] == 3 and res["delisted"] == 1
    syms = store.list_symbols("day_nse")
    assert "NSE:LIVE" in syms and "NSE:SAME" in syms and "NSE:NIFTY 50" in syms and "NSE:INDIA VIX" in syms
    assert any(s.startswith("NSE:SAME~INEOLD") for s in syms)
    t = pd.read_parquet(paths.NSE_BHAV_DIR / "securities.parquet")
    assert t.set_index("sec_id").loc["INEOLD", "delisted"] and not t.set_index("sec_id").loc["INENEW", "delisted"]
    assert len(store.read_bars("NSE:SAME", "day_nse")) == 40
    assert store.read_bars("NSE:SAME", "day_nse")["close"].iloc[0] == pytest.approx(20.0)
    assert (paths.UNIVERSE_DIR / "liquidity_day_nse.parquet").exists()
    assert not (paths.UNIVERSE_DIR / "liquidity_daily.parquet").exists()
    assert (paths.NSE_BHAV_DIR / "corporate_actions.parquet").exists()


def test_validate_against_kite():
    days = pd.bdate_range("2022-01-03", periods=60)
    rows = [_row(d, "VAL", "INEV", 100 + i) for i, d in enumerate(days)]
    (paths.NSE_BHAV_DIR / "panel").mkdir(parents=True)
    pd.DataFrame(rows).to_parquet(paths.NSE_BHAV_DIR / "panel" / "all.parquet")
    nb.build(liquidity=False)
    adj = store.read_bars("NSE:VAL", "day_nse")
    store.write_bars("NSE:VAL", "day", adj)
    out = nb.validate()
    assert len(out) == 1 and out["median_abs_diff"].iloc[0] == 0 and out["share_within_0p5pct"].iloc[0] == 1.0
    assert (paths.NSE_BHAV_DIR / "validation.csv").exists()


def test_dayn_wiring(monkeypatch):
    raw = synth.synthetic_day(300, 3)
    store.write_bars("NSE:AAA", "day_nse", raw)
    d_ref, w_ref = bars.derive(raw.copy(), "day"), bars.derive(raw.copy(), "week")
    pd.testing.assert_frame_equal(bars.load("NSE:AAA", "dayn"), d_ref)
    pd.testing.assert_frame_equal(bars.load("NSE:AAA", "weekn"), w_ref)
    t = targets.build_targets(bars.load("NSE:AAA", "dayn"), "dayn")
    t_ref = targets.build_targets(d_ref, "day")
    assert list(t.columns) == list(t_ref.columns)
    for d in (splits.EMBARGO, factors.HIGHER_TF, score.BARS_PER_YEAR, targets.SCALES, targets.HOLD_H, score.TOL):
        assert "dayn" in d and "weekn" in d
    assert splits.EMBARGO["dayn"] == "5D" and splits.EMBARGO["weekn"] == "21D"
    assert factors.HIGHER_TF["dayn"] == ["weekn"] and factors.HIGHER_TF["weekn"] == []
    cal = factors.calendar_factors(bars.load("NSE:AAA", "dayn"), "dayn")
    assert (cal["tod"] == 0).all()

    # membership reads the day_nse panel for dayn/weekn, the day panel for day
    p = pd.DataFrame({"date": pd.to_datetime(["2019-12-30"] * 2), "symbol": ["NSE:NSEONLY", "NSE:BIG"],
                      "med_tv_252": [5.0, 9.0], "n_sessions": [300, 300]})
    pd_day = p.assign(symbol=["NSE:DAYONLY", "NSE:BIG"])
    paths.UNIVERSE_DIR.mkdir(parents=True, exist_ok=True)
    p.to_parquet(paths.UNIVERSE_DIR / "liquidity_day_nse.parquet")
    pd_day.to_parquet(paths.UNIVERSE_DIR / "liquidity_daily.parquet")
    src = source.LabSource()
    assert src.membership([2020], 2, tf="dayn")[2020] == {"NSE:NSEONLY", "NSE:BIG"}
    assert src.membership([2020], 2, tf="weekn")[2020] == {"NSE:NSEONLY", "NSE:BIG"}
    assert src.membership([2020], 2, tf="day")[2020] == {"NSE:DAYONLY", "NSE:BIG"}
    assert universe._load_panel("day_nse")["symbol"].tolist() == ["NSE:NSEONLY", "NSE:BIG"]
