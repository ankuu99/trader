"""
Screener.in shareholding adapter — historical QUARTERLY shareholding for the FVM
Pillar-4 ownership factors (design §13h, §14 Pillar-4).

Screener.in company pages are PUBLIC for the shareholding table (no login needed):
    https://www.screener.in/company/<NSECODE>/consolidated/
The "Shareholding Pattern" section is a quarterly table with rows:
    Promoters %, FIIs %, DIIs %, Government %, Public %, (Others %), No. of Shareholders.
Promoter "Pledged percentage" appears in the expandable Promoters detail row of the
same page (same quarter columns).

There is no official API. We parse the page HTML. `beautifulsoup4` / `lxml` are NOT
installed in this environment, so parsing uses the stdlib `html.parser` (the parse
functions below are pure and unit-testable without any third-party HTML lib).

Politeness / ToS: a real browser User-Agent, a configurable inter-request delay, and
on-disk caching of raw responses so we never hammer the site.

Normalisation
-------------
- quarter label "Mar 2026" -> period '2026-03'
- knowledge_date = quarter-end + 30 days  (LODR allows ~21 trading days to file the
  shareholding pattern after quarter-end; +30 calendar days is conservative — §13a/§13h)
- value: '%' and thousands separators stripped -> float

Fields emitted (whichever the page exposes):
    'promoter', 'fii', 'dii', 'government', 'public', 'holders', 'pledge'
"""

import os
import time
from calendar import monthrange
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path

import requests
from dotenv import load_dotenv

from trader.core.logger import get_logger

logger = get_logger(__name__)
load_dotenv("config/.env")

_BASE = "https://www.screener.in/company"
# Screener serves a normal browser; python-requests' default UA is sometimes throttled.
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_DEFAULT_CACHE = Path("data/cache/screener")

_MONTHS = {"jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06",
           "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"}


class ScreenerError(RuntimeError):
    pass


# ------------------------------------------------------------------ #
# Pure parse helpers (no network — unit-testable)                    #
# ------------------------------------------------------------------ #

def _norm_period(label: str) -> str | None:
    """'Mar 2026' -> '2026-03'. Returns None for non-period header cells."""
    parts = label.strip().split()
    if len(parts) == 2 and parts[0][:3].lower() in _MONTHS and parts[1].isdigit():
        return f"{parts[1]}-{_MONTHS[parts[0][:3].lower()]}"
    return None


def _knowledge_date_for_period(period: str) -> str:
    """'2026-03' -> quarter-end + 30 days (ISO). Conservative LODR filing-lag PIT stamp."""
    y, m = (int(x) for x in period.split("-"))
    end = date(y, m, monthrange(y, m)[1])
    return (end + timedelta(days=30)).isoformat()


def _label_to_field(label: str) -> str | None:
    """Map a shareholding-table row label to a normalized field name (or None)."""
    l = label.lower()
    if "pledge" in l:
        return "pledge"
    if "promoter" in l:
        return "promoter"
    if "fii" in l or "foreign" in l:
        return "fii"
    if "dii" in l or "domestic" in l:
        return "dii"
    if "government" in l:
        return "government"
    if "public" in l:
        return "public"
    if "shareholder" in l:  # "No. of Shareholders"
        return "holders"
    return None


def _parse_value(text: str) -> float | None:
    """'74.99%' -> 74.99 ; '12,34,567' -> 1234567.0 ; '-'/''/'NA' -> None."""
    raw = (text or "").replace(",", "").replace("%", "").strip()
    if raw in ("", "-", "NA", "N/A"):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


class _TableExtractor(HTMLParser):
    """Flatten every <table> on the page into [[cell-text, ...], ...] rows.

    Screener's shareholding table is not nested, so a single-level model is enough.
    """

    def __init__(self):
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def parse_shareholding_html(html: str) -> dict[str, dict[str, float]]:
    """Parse a Screener.in company page into {field: {period: value}}.

    Scans every table; keeps tables whose header carries 'Mon YYYY' period columns,
    and maps each body row's label to a shareholding field. Pledge (from the expanded
    promoter detail, same period columns) is merged in. Robust to extra/non-shareholding
    tables — rows that don't map to a known field are ignored.
    """
    ex = _TableExtractor()
    ex.feed(html)
    out: dict[str, dict[str, float]] = {}
    for table in ex.tables:
        if not table:
            continue
        header = table[0]
        period_cols = {i: p for i, c in enumerate(header) if (p := _norm_period(c))}
        if not period_cols:
            continue
        for row in table[1:]:
            if not row:
                continue
            field = _label_to_field(row[0])
            if not field:
                continue
            for i, period in period_cols.items():
                if i < len(row):
                    val = _parse_value(row[i])
                    if val is not None:
                        out.setdefault(field, {})[period] = val
    return out


def shareholding_rows(nsecode: str, parsed: dict[str, dict[str, float]],
                      source: str = "screener") -> list[dict]:
    """Flatten parsed {field: {period: value}} into FVMStore.write_shareholding rows."""
    rows: list[dict] = []
    for field, by_period in parsed.items():
        for period, value in by_period.items():
            rows.append({
                "symbol": nsecode.upper(),
                "period": period,
                "field": field,
                "value": value,
                "knowledge_date": _knowledge_date_for_period(period),
                "source": source,
            })
    return rows


# ------------------------------------------------------------------ #
# Networked client (cached, polite)                                  #
# ------------------------------------------------------------------ #

class ShareholdingClient:
    def __init__(self, cache_dir: Path | str | None = None, delay: float = 1.5,
                 session: requests.Session | None = None):
        self.cache_dir = Path(cache_dir or os.getenv("FVM_SCREENER_CACHE") or _DEFAULT_CACHE)
        self.delay = delay
        self.s = session or requests.Session()
        self.s.headers.update({
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def _cache_path(self, nsecode: str, basis: str) -> Path:
        return self.cache_dir / f"{nsecode.upper()}_{basis}.html"

    def fetch_html(self, nsecode: str, basis: str = "consolidated",
                   use_cache: bool = True) -> str:
        """Return the raw company-page HTML, served from disk cache when available."""
        cache = self._cache_path(nsecode, basis)
        if use_cache and cache.exists():
            return cache.read_text(encoding="utf-8")
        seg = "consolidated/" if basis == "consolidated" else ""
        url = f"{_BASE}/{nsecode.upper()}/{seg}"
        if self.delay:
            time.sleep(self.delay)  # polite — never hammer
        r = self.s.get(url, timeout=60)
        if r.status_code == 404 and basis == "consolidated":
            # not every company has a consolidated page; fall back to standalone
            return self.fetch_html(nsecode, basis="standalone", use_cache=use_cache)
        if r.status_code != 200:
            raise ScreenerError(f"{nsecode}: HTTP {r.status_code} from {url}")
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(r.text, encoding="utf-8")
        return r.text


def fetch_shareholding(nsecode: str, client: ShareholdingClient | None = None,
                       basis: str = "consolidated") -> dict[str, dict[str, float]]:
    """Fetch + parse one NSE symbol's shareholding -> {field: {period: value}}."""
    client = client or ShareholdingClient()
    html = client.fetch_html(nsecode, basis=basis)
    return parse_shareholding_html(html)


# ------------------------------------------------------------------ #
# Ingestion                                                          #
# ------------------------------------------------------------------ #

def ingest_shareholding(store, nsecode: str, client: ShareholdingClient | None = None,
                        basis: str = "consolidated") -> int:
    """Fetch one stock's quarterly shareholding and write it to the PIT FVMStore.

    Each period is stamped knowledge_date = quarter-end + 30 days (conservative LODR
    filing lag). Append-only vintage — re-ingesting the same vintage is a no-op.
    """
    parsed = fetch_shareholding(nsecode, client=client, basis=basis)
    rows = shareholding_rows(nsecode, parsed)
    n = store.write_shareholding(rows)
    logger.info("ingest_shareholding | %s | %d rows (%d fields)",
                nsecode, n, len(parsed))
    return n
