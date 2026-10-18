"""Survivorship-free daily bars from NSE bhavcopy archives (TD-022, lab interval `day_nse`, timeframes dayn/weekn).

  .venv/bin/python -m research.model_lab.nse_bhav <fetch|ca|parse|build|validate> [--from 2008-01-01] [--to YYYY-MM-DD]

fetch    every calendar day's cm bhavcopy zip -> nse_bhav/raw/<YYYY>/<YYYYMMDD>.zip (resumable, <= 2 req/s;
         dates logged holiday_or_missing are not re-requested unless --retry-missing)
ca       NSE corporate-actions API, one request per year -> nse_bhav/ca/<YYYY>.json -> ca_events.parquet
parse    zips -> nse_bhav/panel/<YYYY>.parquet (EQ/BE/BZ rows, normalised columns)
build    panel -> securities (chained across renames / ISIN changes), split/bonus adjustment from the
         corporate-actions events, per-security bars in bars/day_nse/, Kite index copies, PIT liquidity panel
validate adjusted closes vs Kite's adjusted daily bars for overlapping names -> nse_bhav/validation.csv

Bhavcopy PREVCLOSE is NOT adjusted on an ex-date (verified on RELIANCE bonuses), so it is QA-only
(prevclose_gaps.csv). No imports from trader.* (lab rule).
"""
import argparse
import csv
import io
import re
import sys
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from research.model_lab import paths, store, universe
from research.model_lab.paths import sym_file

OLD_LAST = date(2024, 7, 5)                 # last file in the legacy format
SERIES = ("EQ", "BE", "BZ")
_PRI = {"EQ": 0, "BE": 1, "BZ": 2}
LINK_DAYS = 30                              # symbol continuity gap that still joins a security
PREVCLOSE_QA = 0.02                         # |prevclose / prev close - 1| above this is listed in prevclose_gaps.csv
GAP_SUSPECT = 0.25                          # |gap_ratio - 1| above this counts as a suspect corporate action
CA_WINDOW_DAYS = 5                          # attach an event to the first row within this many days of ex_date
CA_INTERVAL = 1.0                           # seconds between corporate-actions requests (<= 1 req/s)
CA_URL = "https://www.nseindia.com/api/corporates-corporateActions"
CA_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-actions",
}
REQ_INTERVAL = 0.5                          # seconds between requests (<= 2 req/s)
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
    "Referer": "https://www.nseindia.com/",
    "Accept": "*/*",
}
PANEL_COLS = ["date", "symbol", "series", "isin", "open", "high", "low", "close", "prevclose",
              "volume", "value", "trades"]
INDICES = ("NSE:NIFTY 50", "NSE:INDIA VIX")
_MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


# ---------------------------------------------------------------- paths / urls

def raw_path(d: date) -> Path:
    return paths.NSE_BHAV_DIR / "raw" / f"{d.year}" / f"{d:%Y%m%d}.zip"


def url_for(d: date, fmt: str) -> str:
    if fmt == "old":
        mon = _MON[d.month - 1]
        return (f"https://nsearchives.nseindia.com/content/historical/EQUITIES/{d.year}/{mon}/"
                f"cm{d.day:02d}{mon}{d.year}bhav.csv.zip")
    return f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"


def formats_for(d: date) -> list[str]:
    return ["old", "udiff"] if d <= OLD_LAST else ["udiff", "old"]


# ---------------------------------------------------------------- fetch

def _http_get(url: str) -> tuple[int, bytes]:
    """(status, body). Retries network errors / 5xx 3 times with backoff; status 0 = gave up on network."""
    import requests
    status, body = 0, b""
    for attempt in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            status, body = r.status_code, r.content
            if status < 500:
                return status, body
        except requests.RequestException:
            status, body = 0, b""
        time.sleep(2 ** attempt)
    return status, body


def _log_fetch(rows: list[tuple]) -> None:
    p = paths.NSE_BHAV_DIR / "fetch_log.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    new = not p.exists()
    with open(p, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "url", "status", "bytes"])
        w.writerows(rows)


def calendar_days(start: date, end: date) -> list[date]:
    """Every calendar day (weekend special sessions exist)."""
    out, d = [], start
    while d <= end:
        out.append(d)
        d += timedelta(days=1)
    return out


def _logged_missing() -> set[str]:
    """ISO dates whose latest fetch_log row is holiday_or_missing."""
    p = paths.NSE_BHAV_DIR / "fetch_log.csv"
    if not p.exists():
        return set()
    log = pd.read_csv(p, dtype=str)
    if log.empty:
        return set()
    last = log.groupby("date", sort=False)["status"].last()
    return set(last.index[last == "holiday_or_missing"])


def fetch_date(d: date) -> str:
    """Fetch one date. Returns 'exists' | 'ok' | 'holiday_or_missing' | 'error'. Never raises."""
    rp = raw_path(d)
    if rp.exists():
        return "exists"
    log, result = [], "holiday_or_missing"
    try:
        for fmt in formats_for(d):
            url = url_for(d, fmt)
            status, body = _http_get(url)
            time.sleep(REQ_INTERVAL)
            if status == 200 and body[:2] == b"PK":
                rp.parent.mkdir(parents=True, exist_ok=True)
                tmp = rp.with_name(rp.name + ".tmp")
                tmp.write_bytes(body)
                tmp.replace(rp)
                log.append((d.isoformat(), url, status, len(body)))
                result = "ok"
                break
            if status == 404:
                log.append((d.isoformat(), url, 404, 0))
                continue
            log.append((d.isoformat(), url, status, len(body)))
            result = "error"
            break
        if result == "holiday_or_missing":
            log.append((d.isoformat(), "", "holiday_or_missing", 0))
    except Exception as e:                                  # one bad date never stops the run
        log.append((d.isoformat(), "", f"error:{type(e).__name__}", 0))
        result = "error"
    _log_fetch(log)
    return result


def fetch_range(start: date, end: date, retry_missing: bool = False) -> dict[str, int]:
    paths.check_disk()
    counts: dict[str, int] = {}
    missing = set() if retry_missing else _logged_missing()
    for d in calendar_days(start, end):
        if d.isoformat() in missing and not raw_path(d).exists():
            counts["skipped_missing"] = counts.get("skipped_missing", 0) + 1
            continue
        r = fetch_date(d)
        counts[r] = counts.get(r, 0) + 1
    return counts


# ---------------------------------------------------------------- parse

def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def parse_zip(path_or_bytes, d: date) -> tuple[pd.DataFrame, int]:
    """One bhavcopy zip -> (normalised EQ/BE/BZ rows, rows dropped as bad OHLC)."""
    zf = zipfile.ZipFile(io.BytesIO(path_or_bytes) if isinstance(path_or_bytes, bytes) else path_or_bytes)
    name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
    raw = pd.read_csv(zf.open(name), dtype=str, skipinitialspace=True, index_col=False)
    raw.columns = [c.strip() for c in raw.columns]
    if "TckrSymb" in raw.columns:                                       # UDiFF
        if "FinInstrmTp" in raw.columns:
            raw = raw[raw["FinInstrmTp"].str.strip() == "STK"]
        m = {"symbol": "TckrSymb", "series": "SctySrs", "isin": "ISIN", "open": "OpnPric", "high": "HghPric",
             "low": "LwPric", "close": "ClsPric", "prevclose": "PrvsClsgPric", "volume": "TtlTradgVol",
             "value": "TtlTrfVal", "trades": "TtlNbOfTxsExctd"}
    else:                                                               # legacy
        m = {"symbol": "SYMBOL", "series": "SERIES", "isin": "ISIN", "open": "OPEN", "high": "HIGH",
             "low": "LOW", "close": "CLOSE", "prevclose": "PREVCLOSE", "volume": "TOTTRDQTY",
             "value": "TOTTRDVAL", "trades": "TOTALTRADES"}
    out = pd.DataFrame({k: (raw[v] if v in raw.columns else pd.Series(np.nan, index=raw.index))
                        for k, v in m.items()})
    out["series"] = out["series"].astype("string").str.strip().str.upper()
    out = out[out["series"].isin(SERIES)].copy()
    out["symbol"] = out["symbol"].astype("string").str.strip()
    isin = out["isin"].astype("string").str.strip()
    out["isin"] = isin.where(isin.str.len() > 0)
    for c in ("open", "high", "low", "close", "prevclose", "value", "trades"):
        out[c] = _num(out[c]).astype("float64")
    out["volume"] = _num(out["volume"]).fillna(0).astype("int64")
    ok = ((out[["open", "high", "low", "close"]] > 0).all(axis=1)
          & (out["close"] >= out["low"]) & (out["close"] <= out["high"]))
    dropped = int((~ok).sum())
    out = out[ok]
    out.insert(0, "date", pd.Timestamp(d))
    out["date"] = out["date"].astype("datetime64[ns]")
    out["symbol"] = out["symbol"].astype(object)
    out["series"] = out["series"].astype(object)
    out["isin"] = out["isin"].astype(object).where(out["isin"].notna(), None)
    return out[PANEL_COLS].reset_index(drop=True), dropped


def _panel_path(year: int) -> Path:
    return paths.NSE_BHAV_DIR / "panel" / f"{year}.parquet"


def parse_range(start: date, end: date) -> pd.DataFrame:
    paths.check_disk()
    log = []
    for year in range(start.year, end.year + 1):
        files = sorted((paths.NSE_BHAV_DIR / "raw" / f"{year}").glob("*.zip"))
        files = [f for f in files if start <= datetime.strptime(f.stem, "%Y%m%d").date() <= end]
        if not files:
            continue
        parts, dropped, bad = [], 0, 0
        for f in files:
            d = datetime.strptime(f.stem, "%Y%m%d").date()
            try:
                df, n = parse_zip(f, d)
            except Exception:
                bad += 1
                continue
            parts.append(df)
            dropped += n
        panel = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=PANEL_COLS)
        if len(panel):
            store._atomic_write(_panel_path(year), lambda t, p=panel: p.to_parquet(
                t, engine="pyarrow", compression="zstd", index=False))
        log.append({"year": year, "files": len(files), "unreadable": bad, "rows": len(panel),
                    "dropped_bad_ohlc": dropped})
    out = pd.DataFrame(log, columns=["year", "files", "unreadable", "rows", "dropped_bad_ohlc"])
    if len(out):
        paths.NSE_BHAV_DIR.mkdir(parents=True, exist_ok=True)
        out.to_csv(paths.NSE_BHAV_DIR / "parse_log.csv", index=False)
    return out


def load_panel() -> pd.DataFrame:
    files = sorted((paths.NSE_BHAV_DIR / "panel").glob("*.parquet"))
    if not files:
        raise FileNotFoundError("no bhavcopy panel — run the parse stage")
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


# ---------------------------------------------------------------- securities

def assign_securities(panel: pd.DataFrame) -> pd.DataFrame:
    """Add integer `sec` to each row, chaining by ISIN or by symbol continuity (<= LINK_DAYS).
    Rows are sorted by date (EQ before BE/BZ); a second row of one security on one date is dropped."""
    p = panel.copy()
    p["_pri"] = p["series"].map(_PRI).fillna(3)
    p = p.sort_values(["date", "_pri", "symbol"], kind="stable").reset_index(drop=True)
    dn = p["date"].values.astype("datetime64[D]").astype("int64")
    syms, isins = p["symbol"].tolist(), p["isin"].tolist()
    isin_sec: dict[str, int] = {}
    sym_cur: dict[str, tuple[int, int]] = {}
    sec_last: dict[int, int] = {}
    sec = np.empty(len(p), dtype="int64")
    keep = np.ones(len(p), dtype=bool)
    nsec = 0
    for i in range(len(p)):
        s, isn, d = syms[i], isins[i], int(dn[i])
        has = isinstance(isn, str) and len(isn) > 0
        if has and isn in isin_sec:
            k = isin_sec[isn]
        else:
            cur = sym_cur.get(s)
            if cur is not None and d - cur[1] <= LINK_DAYS:
                k = cur[0]
            else:
                k = nsec
                nsec += 1
        if has and isn not in isin_sec:
            isin_sec[isn] = k
        sym_cur[s] = (k, d)
        if sec_last.get(k) == d:
            keep[i] = False
        else:
            sec_last[k] = d
        sec[i] = k
    p["sec"] = sec
    return p[keep].drop(columns="_pri").reset_index(drop=True)


def security_table(p: pd.DataFrame, last_panel_date: pd.Timestamp) -> pd.DataFrame:
    """One row per security. `p` is the output of assign_securities."""
    rows = []
    for k, g in p.groupby("sec", sort=True):
        g = g.sort_values("date")
        isn = g["isin"].dropna()
        runs = g.groupby("symbol", sort=False)["date"].agg(["min", "max"]).sort_values("min")
        rows.append({
            "sec": int(k),
            "sec_id": isn.iloc[0] if len(isn) else "SYM:" + g["symbol"].iloc[0],
            "symbols": ";".join(f"{s}:{r['min']:%Y-%m-%d}:{r['max']:%Y-%m-%d}" for s, r in runs.iterrows()),
            "isins": ";".join(dict.fromkeys(isn.tolist())),
            "first_date": g["date"].iloc[0],
            "last_date": g["date"].iloc[-1],
            "last_symbol": g["symbol"].iloc[-1],
            "n_rows": len(g),
        })
    t = pd.DataFrame(rows)
    t["delisted"] = t["last_date"] < (last_panel_date - pd.Timedelta(days=LINK_DAYS))
    return t


# ---------------------------------------------------------------- corporate actions

_RS = r"\br[se]\.?\s*(\d+(?:\.\d+)?)"
_SPLIT_KW = re.compile(r"split|sub-?\s*division", re.I)
_BONUS_RE = re.compile(r"\bbonus\W*(?:shares\s+in\s+the\s+ratio\s+of\W*)?(\d+)\s*:\s*(\d+)", re.I)
_NON_EQUITY = re.compile(r"deb|ncrps|preference|dvr", re.I)
EVENT_COLS = ["symbol", "isin", "series", "ex_date", "subject", "kind", "factor"]


def _parse_ca(subject: str) -> tuple[float, str] | None:
    """(price factor applied BEFORE the ex-date, kind) or None when not a price-adjusting event."""
    f, kinds = 1.0, []
    m = _BONUS_RE.search(subject)
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        if a + b > 0:
            f *= b / (a + b)
            kinds.append("bonus")
    k = _SPLIT_KW.search(subject)
    if k:
        rs = re.findall(_RS, subject[k.end():], re.I)
        if len(rs) >= 2 and float(rs[1]) > 0 and float(rs[0]) > 0:
            f *= float(rs[1]) / float(rs[0])
            kinds.append("split")
    if not kinds:
        return None
    return f, "+".join(kinds)


def parse_ca_subject(subject) -> float | None:
    """Price factor for a corporate-action subject (None = not a price-adjusting event)."""
    if not isinstance(subject, str):
        return None
    r = _parse_ca(subject)
    return None if r is None else r[0]


def _ca_json_path(year: int) -> Path:
    return paths.NSE_BHAV_DIR / "ca" / f"{year}.json"


def _new_session():
    import requests
    return requests.Session()


def _warm(session) -> None:
    session.get("https://www.nseindia.com/", headers=CA_HEADERS, timeout=30)


def _ca_get(session, year: int) -> list:
    """One year's rows. 3 attempts with backoff; re-warms the session once on 401/403."""
    params = {"index": "equities", "from_date": f"01-01-{year}", "to_date": f"31-12-{year}"}
    rewarmed, last = False, "no response"
    for attempt in range(3):
        try:
            r = session.get(CA_URL, params=params, headers=CA_HEADERS, timeout=30)
            if r.status_code == 200:
                data = r.json()
                return data["data"] if isinstance(data, dict) and "data" in data else data
            last = f"status {r.status_code}"
            if r.status_code in (401, 403) and not rewarmed:
                rewarmed = True
                _warm(session)
        except Exception as e:
            last = type(e).__name__
        time.sleep(CA_INTERVAL * (2 ** attempt))
    raise RuntimeError(f"corporate actions {year}: {last}")


def fetch_ca(start_year: int, end_year: int, session=None) -> dict[str, int]:
    import json
    paths.check_disk()
    counts = {"fetched": 0, "skipped": 0}
    this_year = date.today().year
    session = session or _new_session()
    warmed = False
    for y in range(start_year, end_year + 1):
        p = _ca_json_path(y)
        if p.exists() and y != this_year:
            counts["skipped"] += 1
            continue
        if not warmed:
            _warm(session)
            warmed = True
        rows = _ca_get(session, y)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(rows))
        tmp.replace(p)
        counts["fetched"] += 1
        time.sleep(CA_INTERVAL)
    return counts


def parse_ca(start_year: int | None = None, end_year: int | None = None) -> pd.DataFrame:
    """All saved ca/*.json -> ca_events.parquet (+ ca_unparsed.csv)."""
    import json
    events, unparsed = [], []
    for f in sorted((paths.NSE_BHAV_DIR / "ca").glob("*.json")):
        rows = json.loads(f.read_text())
        for r in rows:
            subj = r.get("subject") or ""
            if not re.search(r"bonus|split|sub-?\s*division", subj, re.I):
                continue
            ex = pd.to_datetime(r.get("exDate"), format="%d-%b-%Y", errors="coerce")
            if pd.isna(ex):
                continue
            res = _parse_ca(subj)
            if res is None:
                if not _NON_EQUITY.search(subj):
                    unparsed.append({"symbol": r.get("symbol"), "ex_date": ex.date().isoformat(), "subject": subj})
                continue
            events.append({"symbol": (r.get("symbol") or "").strip(), "isin": (r.get("isin") or "").strip() or None,
                           "series": r.get("series"), "ex_date": ex, "subject": subj,
                           "kind": res[1], "factor": res[0]})
    ev = pd.DataFrame(events, columns=EVENT_COLS)
    ev["ex_date"] = pd.to_datetime(ev["ex_date"]).astype("datetime64[ns]")
    ev["factor"] = ev["factor"].astype("float64")
    paths.NSE_BHAV_DIR.mkdir(parents=True, exist_ok=True)
    store._atomic_write(paths.NSE_BHAV_DIR / "ca_events.parquet", lambda t: ev.to_parquet(
        t, engine="pyarrow", compression="zstd", index=False))
    pd.DataFrame(unparsed, columns=["symbol", "ex_date", "subject"]).to_csv(
        paths.NSE_BHAV_DIR / "ca_unparsed.csv", index=False)
    return ev


# ---------------------------------------------------------------- adjustment

def adjust(p: pd.DataFrame, events: pd.DataFrame | None = None):
    """Backward-adjust per security from corporate-action events.
    Returns (adjusted rows, corporate actions, unmatched events, prevclose QA gaps)."""
    p = p.sort_values(["sec", "date"], kind="stable").reset_index(drop=True)
    n = len(p)
    sec = p["sec"].to_numpy()
    dates = p["date"].to_numpy()
    pos_by_sec: dict[int, np.ndarray] = {}
    bounds = np.flatnonzero(np.r_[True, sec[1:] != sec[:-1], True]) if n else np.array([0])
    for a, b in zip(bounds[:-1], bounds[1:]):
        pos_by_sec[int(sec[a])] = np.arange(a, b)
    isn_col, sym_col = p["isin"].tolist(), p["symbol"].tolist()
    ev = events if events is not None else pd.DataFrame(columns=EVENT_COLS)
    win = np.timedelta64(CA_WINDOW_DAYS, "D")

    def _attach(cands, ex):
        best = None
        for k in cands:
            idx = pos_by_sec[k]
            dd = dates[idx]
            j = int(np.searchsorted(dd, ex))
            if j < len(idx) and dd[j] - ex <= win and (best is None or dd[j] < dates[best]):
                best = int(idx[j])
        return best

    # per-row (isin/symbol) -> security candidates, restricted to the event window
    isin_rows: dict[str, list] = {}
    sym_rows: dict[str, list] = {}
    for i in range(n):
        if isinstance(isn_col[i], str):
            isin_rows.setdefault(isn_col[i], []).append(i)
        sym_rows.setdefault(sym_col[i], []).append(i)

    def _near(rows, ex):
        return {int(sec[i]) for i in rows if 0 <= (dates[i] - ex) / np.timedelta64(1, "D") <= CA_WINDOW_DAYS}

    f = np.ones(n)
    seen, kept, unmatched = set(), [], []
    for e in ev.itertuples(index=False):
        ex = np.datetime64(e.ex_date, "ns")
        row = None
        if isinstance(e.isin, str) and e.isin in isin_rows:
            row = _attach(_near(isin_rows[e.isin], ex), ex)
        if row is None and e.symbol in sym_rows:
            row = _attach(_near(sym_rows[e.symbol], ex), ex)
        if row is None:
            unmatched.append({"symbol": e.symbol, "isin": e.isin, "ex_date": e.ex_date, "subject": e.subject,
                              "factor": e.factor})
            continue
        key = (int(sec[row]), row, round(float(e.factor), 9))
        if key in seen:
            continue
        seen.add(key)
        f[row] *= float(e.factor)
        kept.append({"row": row, "kind": e.kind, "subject": e.subject})
    p["f"] = f

    prev_close = p.groupby("sec")["close"].shift(1)
    # QA only: NSE's PREVCLOSE is not adjusted on ex-dates; never used for adjustment
    ratio = p["prevclose"] / prev_close
    qa = ((ratio - 1).abs() > PREVCLOSE_QA) & (p["f"] == 1.0)
    gaps = pd.DataFrame({"sec": p.loc[qa, "sec"], "date": p.loc[qa, "date"], "prevclose": p.loc[qa, "prevclose"],
                         "prev_close": prev_close[qa], "ratio": ratio[qa]}).reset_index(drop=True)

    gap_ratio = (p["open"] / prev_close) / p["f"]
    A = np.ones(n)
    for a, b in zip(bounds[:-1], bounds[1:]):
        seg = f[a:b]
        if (seg != 1.0).any():
            rev = np.cumprod(seg[::-1])[::-1]               # prod_{s>=t}
            A[a:b - 1] = rev[1:]
    p["adj"] = A
    ca_rows = []
    for k in kept:
        i = k["row"]
        ca_rows.append({"sec": int(sec[i]), "date": p["date"].iloc[i], "f": float(p["f"].iloc[i]), "kind": k["kind"],
                        "subject": k["subject"], "gap_ratio": float(gap_ratio.iloc[i])})
    ca = pd.DataFrame(ca_rows, columns=["sec", "date", "f", "kind", "subject", "gap_ratio"])
    ca["gap_ratio"] = ca["gap_ratio"].astype("float64")
    ca = ca.sort_values(["sec", "date"], kind="stable").reset_index(drop=True)
    for c in ("open", "high", "low", "close"):
        p[c] = p[c] * A
    p["volume"] = np.rint(p["volume"].to_numpy(float) / A).astype("int64")
    um = pd.DataFrame(unmatched, columns=["symbol", "isin", "ex_date", "subject", "factor"])
    return p, ca, um, gaps


# ---------------------------------------------------------------- build

def _bar_name(table: pd.DataFrame) -> pd.Series:
    """Unique file stem per security: last symbol; on collision the earlier-ending one gets ~sec_id."""
    names = table["last_symbol"].map(sym_file)
    out = names.copy()
    for nm, idx in table.groupby(names).groups.items():
        if len(idx) > 1:
            order = table.loc[idx].sort_values("last_date")
            for j in order.index[:-1]:
                out[j] = nm + "~" + str(table.loc[j, "sec_id"]).replace(":", "-")
    return out


def build(liquidity: bool = True) -> dict:
    paths.check_disk()
    panel = load_panel()
    last_panel_date = panel["date"].max()
    p = assign_securities(panel)
    table = security_table(p, last_panel_date)
    table["file_name"] = _bar_name(table)
    ev_path = paths.NSE_BHAV_DIR / "ca_events.parquet"
    events = pd.read_parquet(ev_path) if ev_path.exists() else pd.DataFrame(columns=EVENT_COLS)
    if not ev_path.exists():
        print("build: WARNING no ca_events.parquet — run the ca stage; no adjustment applied")
    adj, ca, unmatched, gaps = adjust(p, events)
    sec_to_id = dict(zip(table["sec"], table["sec_id"]))
    ca.insert(0, "sec_id", ca["sec"].map(sec_to_id))
    ca = ca.drop(columns="sec")
    paths.NSE_BHAV_DIR.mkdir(parents=True, exist_ok=True)
    gaps.insert(0, "sec_id", gaps["sec"].map(sec_to_id))
    gaps.drop(columns="sec").to_csv(paths.NSE_BHAV_DIR / "prevclose_gaps.csv", index=False)
    unmatched.to_csv(paths.NSE_BHAV_DIR / "ca_unmatched.csv", index=False)

    paths.NSE_BHAV_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in (("securities.parquet", table.drop(columns="sec")), ("corporate_actions.parquet", ca)):
        store._atomic_write(paths.NSE_BHAV_DIR / name, lambda t, d=df: d.to_parquet(
            t, engine="pyarrow", compression="zstd", index=False))

    names = dict(zip(table["sec"], table["file_name"]))
    for k, g in adj.groupby("sec", sort=False):
        bars = pd.DataFrame({"timestamp": g["date"].values, "open": g["open"].values, "high": g["high"].values,
                             "low": g["low"].values, "close": g["close"].values, "volume": g["volume"].values})
        clean = store.clean_bars(bars, "day_nse")
        if clean.empty:
            continue
        sym = "NSE:" + names[k]
        store._atomic_write(store.bar_path(sym, "day_nse"), lambda t, d=clean: d.to_parquet(
            t, engine="pyarrow", compression="zstd", index=False))
    n_idx = 0
    for sym in INDICES:                                     # not in bhavcopy; market factors need them here
        b = store.read_bars(sym, "day")
        if len(b):
            store._atomic_write(store.bar_path(sym, "day_nse"), lambda t, d=b: d.to_parquet(
                t, engine="pyarrow", compression="zstd", index=False))
            n_idx += 1
    if liquidity:
        universe.build_liquidity_panel(interval="day_nse")
    return {"securities": len(table), "delisted": int(table["delisted"].sum()),
            "corporate_actions": len(ca), "indices": n_idx, "n_ca_matched": len(ca),
            "n_ca_unmatched": len(unmatched),
            "n_gap_suspect": int(((ca["gap_ratio"] - 1).abs() > GAP_SUSPECT).sum())}


# ---------------------------------------------------------------- validate

def validate() -> pd.DataFrame:
    table = pd.read_parquet(paths.NSE_BHAV_DIR / "securities.parquet")
    kite_syms = set(store.list_symbols("day"))
    rows = []
    for _, r in table.iterrows():
        sym = "NSE:" + r["last_symbol"]
        if sym not in kite_syms:
            continue
        a = store.read_bars("NSE:" + r["file_name"], "day_nse")
        k = store.read_bars(sym, "day")
        m = a[["timestamp", "close"]].merge(k[["timestamp", "close"]], on="timestamp", suffixes=("_nse", "_kite"))
        if m.empty:
            continue
        diff = (m["close_nse"] / m["close_kite"] - 1).abs()
        rows.append({"symbol": r["last_symbol"], "sec_id": r["sec_id"], "n_days": len(m),
                     "median_abs_diff": float(diff.median()), "share_within_0p5pct": float((diff <= 0.005).mean())})
    out = pd.DataFrame(rows, columns=["symbol", "sec_id", "n_days", "median_abs_diff", "share_within_0p5pct"])
    paths.NSE_BHAV_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(paths.NSE_BHAV_DIR / "validation.csv", index=False)
    if len(out):
        print(f"validate: {len(out)} symbols; median of median |diff| {out['median_abs_diff'].median():.5f}; "
              f"mean share within 0.5%: {out['share_within_0p5pct'].mean():.4f}; "
              f"{int((out['share_within_0p5pct'] < 0.9).sum())} symbols < 90% within 0.5%")
        print("validate: 20 worst by share within 0.5%:")
        print(out.nsmallest(20, "share_within_0p5pct")[["symbol", "sec_id", "n_days", "median_abs_diff",
                                                         "share_within_0p5pct"]].to_string(index=False))
    else:
        print("validate: no overlapping symbols")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="research.model_lab.nse_bhav")
    ap.add_argument("stage", choices=["fetch", "ca", "parse", "build", "validate"])
    ap.add_argument("--from", dest="from_", default="2008-01-01")
    ap.add_argument("--to", default=None)
    ap.add_argument("--no-liquidity", action="store_true", help="build: skip the day_nse liquidity panel")
    ap.add_argument("--retry-missing", action="store_true", help="fetch: re-request dates logged holiday_or_missing")
    args = ap.parse_args(argv)
    if args.stage == "ca":
        y0 = int(args.from_[:4])
        y1 = int(args.to[:4]) if args.to else date.today().year
        print(fetch_ca(y0, y1))
        print(f"ca_events: {len(parse_ca())} rows")
        return 0
    start = date.fromisoformat(args.from_)
    end = date.fromisoformat(args.to) if args.to else date.today()
    if args.stage == "fetch":
        print(fetch_range(start, end, retry_missing=args.retry_missing))
    elif args.stage == "parse":
        print(parse_range(start, end).to_string(index=False))
    elif args.stage == "build":
        print(build(liquidity=not args.no_liquidity))
    else:
        validate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
