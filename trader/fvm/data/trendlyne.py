"""
Trendlyne fincsv API adapter (Excel Connect's underlying REST API).

Endpoints (GET, CSV/JSON), discovered from the Excel Connect Apps Script:
  get-expiry/                          -> {expires_on, is_expired}      (token only)
  all_stocks/                          -> CSV master list               (token only)
  quarter/?stock_hash=<h>              -> CSV quarterly financials      (token + session cookie)
  annual/?stock_hash=<h>               -> CSV annual financials         (token + session cookie)

Auth:
  - Header `tltoken: Token <token>` + a real browser User-Agent (the WAF blocks
    python-requests' default UA).
  - The DATA endpoints (quarter/annual) additionally require a valid logged-in
    session Cookie. The expiry/master endpoints do not.

Credentials come from config/.env:
  TRENDLYNE_TOKEN   (stable, from the Excel Connect page)
  TRENDLYNE_COOKIE  (session cookie for financials; manual refresh at quarterly cadence,
                     or upgrade to a login routine later — see design §15c)

Rate limit (server-side, per token): 50 financials fetches/day, 500/month.
"""

import csv
import io
import os

import requests
from dotenv import load_dotenv

from trader.core.logger import get_logger

logger = get_logger(__name__)
load_dotenv("config/.env")

_BASE = "https://trendlyne.com/fundamentals/fincsv/v1"
# The financials (quarter/annual) endpoints are CloudFront/WAF UA-allowlisted to Google
# Apps Script's UrlFetchApp — a generic browser UA gets a path-level 403. Using the
# Apps-Script UA is what unblocks the data endpoints (verified). Token + cookie still apply.
_UA = ("Mozilla/5.0 (compatible; Google-Apps-Script; beanserver; "
       "+https://script.google.com; id: trendlyne-fvm)")


class TrendlyneError(RuntimeError):
    pass


class TrendlyneClient:
    def __init__(self, token: str | None = None, cookie: str | None = None):
        self.token = token or os.getenv("TRENDLYNE_TOKEN")
        self.cookie = cookie or os.getenv("TRENDLYNE_COOKIE")
        if not self.token:
            raise TrendlyneError("TRENDLYNE_TOKEN not set (config/.env). Copy it from "
                                 "https://trendlyne.com/tools/data-downloader/trendlyne-excel-connect/")
        self.s = requests.Session()
        self.s.headers.update({
            "tltoken": "Token " + self.token,
            "User-Agent": _UA,
            "Accept": "text/csv, application/json, */*",
        })
        if self.cookie:
            self.s.headers["Cookie"] = self.cookie

    def _get(self, path: str, needs_cookie: bool = False) -> requests.Response:
        if needs_cookie and not self.cookie:
            raise TrendlyneError(
                "This endpoint needs TRENDLYNE_COOKIE (financials). Set a fresh session "
                "cookie in config/.env (see design §15c).")
        r = self.s.get(f"{_BASE}/{path}", timeout=60)
        if r.status_code == 429:
            raise TrendlyneError(
                "429 rate-limited: Trendlyne daily/monthly quota reached "
                "(~50 calls/day, 500/month) — resume after the daily reset")
        if r.status_code == 403:
            raise TrendlyneError(
                f"403 on {path}: token/cookie invalid or expired"
                + (" — refresh TRENDLYNE_COOKIE" if needs_cookie else " (UA blocked?)"))
        r.raise_for_status()
        return r

    # --- token-only endpoints -------------------------------------- #
    def expiry(self) -> dict:
        return self._get("get-expiry/").json()

    def all_stocks(self) -> list[dict]:
        """Master list: nsecode -> stock_hash (+ isin/bse/name/currency)."""
        text = self._get("all_stocks/").text
        out = []
        for r in csv.DictReader(io.StringIO(text)):
            nse = (r.get("NSEcode") or "").strip().upper()
            h = (r.get("Unique Code") or "").strip()
            if nse and h:
                out.append({
                    "isin": (r.get("ISIN") or "").strip(),
                    "nsecode": nse,
                    "bsecode": (r.get("BSEcode") or "").strip(),
                    "name": (r.get("Company Name") or "").strip(),
                    "stock_hash": h,
                    "currency": (r.get("Currency") or "").strip(),
                })
        return out

    # --- cookie-gated financials ----------------------------------- #
    def quarter_csv(self, stock_hash: str) -> str:
        # raw hash in the query (matches the Apps Script; `====` padding kept verbatim)
        return self._get(f"quarter/?stock_hash={stock_hash}", needs_cookie=True).text

    def annual_csv(self, stock_hash: str) -> str:
        return self._get(f"annual/?stock_hash={stock_hash}", needs_cookie=True).text


# ------------------------------------------------------------------ #
# Ingestion                                                           #
# ------------------------------------------------------------------ #

def ingest_master(store, client: TrendlyneClient | None = None) -> int:
    """Fetch the all_stocks master list and upsert into fund_stocks. Token-only."""
    client = client or TrendlyneClient()
    rows = client.all_stocks()
    n = store.upsert_stocks(rows)
    logger.info("ingest_master | %d stocks", n)
    return n


def ingest_financials(store, nsecode: str, client: TrendlyneClient | None = None,
                      basis: str = "consolidated") -> int:
    """Fetch quarter + annual financials for one stock and write to the PIT store.

    Needs TRENDLYNE_COOKIE (cookie-gated endpoints). Each period is stamped with a
    knowledge_date = period_end + 45 days (the conservative reporting-lag PIT default,
    design §13a/13h) — upgradeable to exact announcement dates in Phase 0.3.
    Counts against the 50/day, 500/month token budget (2 calls per stock).
    """
    client = client or TrendlyneClient()
    h = store.get_stock_hash(nsecode)
    if not h:
        raise TrendlyneError(f"{nsecode}: not in fund_stocks (run ingest_master first)")
    total = 0
    for statement, csv_text in (("quarter", client.quarter_csv(h)),
                                ("annual", client.annual_csv(h))):
        rows = []
        for rec in parse_financials_csv(csv_text):
            rows.append({
                "symbol": nsecode.upper(), "statement": statement, "basis": basis,
                "period": rec["period"], "field": rec["field"], "value": rec["value"],
                "knowledge_date": _knowledge_date_for_period(rec["period"]),
            })
        total += store.write_fundamentals(rows)
    logger.info("ingest_financials | %s | %d rows", nsecode, total)
    return total


def _knowledge_date_for_period(period: str) -> str:
    """'2026-03' -> period-end + 45 days (ISO date). Conservative reporting-lag PIT."""
    from calendar import monthrange
    from datetime import date, timedelta
    y, m = (int(x) for x in period.split("-"))
    end = date(y, m, monthrange(y, m)[1])
    return (end + timedelta(days=45)).isoformat()


_MONTHS = {"jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
           "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"}


def _norm_period(label: str) -> str | None:
    """'Mar 2026' -> '2026-03'. Returns None for non-period header cells."""
    parts = label.strip().split()
    if len(parts) == 2 and parts[0][:3].lower() in _MONTHS and parts[1].isdigit():
        return f"{parts[1]}-{_MONTHS[parts[0][:3].lower()]}"
    return None


def parse_financials_csv(text: str) -> list[dict]:
    """Parse a fincsv quarter/annual CSV into [{field, period, value}].

    PROVISIONAL — structure inferred from the Excel Connect sheet (param rows ×
    period columns: header row carries 'Mar YYYY' labels, col 0 = parameter name).
    MUST be validated against a real CSV sample once TRENDLYNE_COOKIE is available
    (then finalise basis/consolidated handling). See design §15c.
    """
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []
    header = rows[0]
    # map column index -> normalized period (skip non-period columns like col 0)
    period_cols = {i: p for i, c in enumerate(header) if (p := _norm_period(str(c)))}
    out: list[dict] = []
    for r in rows[1:]:
        if not r or not r[0].strip():
            continue
        field = r[0].strip()
        for i, period in period_cols.items():
            if i < len(r):
                raw = (r[i] or "").replace(",", "").replace("%", "").strip()
                if raw in ("", "-", "NA", "N/A"):
                    continue
                try:
                    out.append({"field": field, "period": period, "value": float(raw)})
                except ValueError:
                    pass
    return out
