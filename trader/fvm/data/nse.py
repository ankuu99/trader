"""
NSE / niftyindices adapter — the GREEN independents (design §13e, §13c, §12b, §14).

Three concerns, all sourced from free NSE / niftyindices files & JSON endpoints:

1. Index membership (survivorship-safe universe, §13e)
   - `ingest_current_membership()` writes the CURRENT Nifty-500 constituents (from the
     published niftyindices constituent CSV) into FVMStore.index_membership.
   - `build_membership_intervals()` / `apply_reconstitution_changes()` scaffold the
     point-in-time reconstruction: given an anchor membership set + a dated change-list
     (additions/removals), they produce membership intervals. Full historical change-list
     files are hard to source — `load_reconstitution_changes()` is left as a TODO loader.

2. Naive-momentum benchmark series (§12b)
   - `fetch_momentum_index()` returns a DataFrame[date, close] for a named momentum index
     (e.g. "NIFTY500 MOMENTUM 50", "NIFTY200 MOMENTUM 30"), cached to CSV under data/.
   - `parse_index_history_csv()` is the pure, testable parser.

3. ASM / GSM compliance lists (live-only veto, §13c)
   - `fetch_compliance_flags()` returns the set of currently-flagged NSE symbols.
   - `parse_compliance_json()` is the pure, testable parser. Current snapshot only.

`requests` is used with a real browser User-Agent (+ referer / cookie bootstrap for the
NSE/niftyindices WAFs). Parsing is stdlib `csv` + `json` + pandas — no scraping libs.
"""

import csv
import io
import json
import os
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

from trader.core.logger import get_logger

logger = get_logger(__name__)
load_dotenv("config/.env")

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_DEFAULT_CACHE = Path("data/cache/nse")

# niftyindices publishes constituent CSVs at stable filenames.
_INDEX_FILES = {
    "NIFTY500": "ind_nifty500list.csv",
    "NIFTY200": "ind_nifty200list.csv",
    "NIFTY100": "ind_nifty100list.csv",
    "NIFTY50": "ind_nifty50list.csv",
}
_CONSTITUENT_BASE = "https://niftyindices.com/IndexConstituent"


class NseError(RuntimeError):
    pass


# ================================================================== #
# 1. Index membership                                                #
# ================================================================== #

def parse_constituents_csv(text: str) -> list[str]:
    """Parse a niftyindices constituent CSV -> list of NSE symbols.

    Columns are typically: Company Name, Industry, Symbol, Series, ISIN Code.
    """
    out: list[str] = []
    for row in csv.DictReader(io.StringIO(text)):
        # tolerate header casing / whitespace
        sym = None
        for k, v in row.items():
            if k and k.strip().lower() == "symbol":
                sym = v
                break
        sym = (sym or "").strip().upper()
        if sym:
            out.append(sym)
    return out


def build_membership_intervals(base_members: list[str], base_date: str,
                               changes: list[dict]) -> list[dict]:
    """Build PIT membership intervals from an anchor set + a dated change-list.

    Pure function (no I/O) — the core of survivorship-safe reconstruction (§13e).

    Args:
        base_members: symbols known to be members as of `base_date` (the anchor).
        base_date: 'YYYY-MM-DD' — the anchor's start_date for those members.
        changes: list of {'date': 'YYYY-MM-DD', 'action': 'ADD'|'DROP', 'symbol': str}.
                 Applied chronologically forward from the anchor.

    Returns:
        list of {'symbol', 'start_date', 'end_date'} (end_date None = still a member).
        A symbol re-added after a drop yields multiple intervals.
    """
    open_start: dict[str, str] = {s.upper(): base_date for s in base_members}
    intervals: list[dict] = []
    for ch in sorted(changes, key=lambda c: c["date"]):
        sym = ch["symbol"].upper()
        action = ch["action"].upper()
        d = ch["date"]
        if action == "ADD":
            if sym not in open_start:          # open a fresh interval
                open_start[sym] = d
        elif action in ("DROP", "REMOVE", "DELETE"):
            if sym in open_start:              # close the open interval
                intervals.append({"symbol": sym, "start_date": open_start.pop(sym),
                                  "end_date": d})
        else:
            raise NseError(f"unknown reconstitution action: {ch['action']!r}")
    for sym, st in open_start.items():
        intervals.append({"symbol": sym, "start_date": st, "end_date": None})
    intervals.sort(key=lambda iv: (iv["symbol"], iv["start_date"]))
    return intervals


def apply_reconstitution_changes(store, index_name: str, base_members: list[str],
                                 base_date: str, changes: list[dict]) -> int:
    """Build intervals from an anchor + change-list and write them to FVMStore."""
    intervals = build_membership_intervals(base_members, base_date, changes)
    rows = [{"index_name": index_name, **iv} for iv in intervals]
    n = store.write_membership(rows)
    logger.info("apply_reconstitution_changes | %s | %d intervals", index_name, n)
    return n


def load_reconstitution_changes(path: Path | str) -> list[dict]:
    """TODO: load a reconstitution change-list file into
    [{'date','action','symbol'}, ...] for `apply_reconstitution_changes()`.

    Full historical Nifty-500 reconstitutions are published by NSE only as periodic
    press releases / index-maintenance PDFs — there is no single machine-readable
    archive. Sourcing strategy (left for a follow-up task):
      - NSE "Index Maintenance" circulars list semi-annual additions/removals (Mar/Sep).
      - Assemble them into a CSV with columns: date, action(ADD|DROP), symbol.
    This loader parses such an assembled CSV; the assembly itself is the open work.
    """
    p = Path(path)
    if not p.exists():
        raise NseError(f"reconstitution change-list not found: {p} "
                       "(assembly of NSE index-maintenance circulars is a TODO)")
    out: list[dict] = []
    for row in csv.DictReader(p.read_text(encoding="utf-8").splitlines()):
        out.append({"date": row["date"].strip(),
                    "action": row["action"].strip().upper(),
                    "symbol": row["symbol"].strip().upper()})
    return out


def ingest_current_membership(store, index_name: str = "NIFTY500",
                              start_date: str = "2024-01-01",
                              client: "NseClient | None" = None) -> int:
    """Fetch the current constituents of `index_name` and write them as open intervals.

    `start_date` is the (approximate) anchor at which we know these names are members;
    end_date is NULL (still members). Use `apply_reconstitution_changes` to layer PIT
    history on top once a change-list is assembled.
    """
    client = client or NseClient()
    text = client.fetch_constituents_csv(index_name)
    symbols = parse_constituents_csv(text)
    rows = [{"index_name": index_name, "symbol": s, "start_date": start_date,
             "end_date": None} for s in symbols]
    n = store.write_membership(rows)
    logger.info("ingest_current_membership | %s | %d constituents", index_name, n)
    return n


# ================================================================== #
# 2. Naive-momentum benchmark series                                 #
# ================================================================== #

def parse_index_history_csv(text: str) -> pd.DataFrame:
    """Parse a niftyindices historical-index CSV -> DataFrame[date, close].

    Tolerant to column naming: picks the column whose name contains 'date' and the one
    containing 'close' (case-insensitive). Dates parsed day-first (e.g. '28 Jun 2026').
    """
    df = pd.read_csv(io.StringIO(text))
    cols = {c.strip().lower(): c for c in df.columns}
    date_col = next((orig for low, orig in cols.items() if "date" in low), None)
    close_col = next((orig for low, orig in cols.items()
                      if "close" in low or low in ("index value", "value")), None)
    if date_col is None or close_col is None:
        raise NseError(f"could not find date/close columns in {list(df.columns)}")
    out = pd.DataFrame({
        "date": pd.to_datetime(df[date_col], dayfirst=True, errors="coerce"),
        "close": pd.to_numeric(
            df[close_col].astype(str).str.replace(",", "", regex=False),
            errors="coerce"),
    }).dropna().sort_values("date").reset_index(drop=True)
    return out


def load_momentum_index(path: Path | str) -> pd.DataFrame:
    """Load a cached momentum-index series CSV -> DataFrame[date, close]."""
    df = pd.read_csv(path, parse_dates=["date"])
    return df[["date", "close"]].sort_values("date").reset_index(drop=True)


def fetch_momentum_index(name: str = "NIFTY500 MOMENTUM 50",
                         client: "NseClient | None" = None,
                         use_cache: bool = True,
                         cache_dir: Path | str | None = None) -> pd.DataFrame:
    """Fetch a momentum-index historical series -> DataFrame[date, close], cached to CSV.

    `name` is the niftyindices display name (e.g. "NIFTY500 MOMENTUM 50",
    "NIFTY200 MOMENTUM 30"). The series is cached under data/cache/nse/<slug>.csv so
    repeat calls (and validation in §12b) never re-hit the network.
    """
    cache_dir = Path(cache_dir or _DEFAULT_CACHE)
    slug = name.lower().replace(" ", "_")
    cache = cache_dir / f"{slug}.csv"
    if use_cache and cache.exists():
        return load_momentum_index(cache)
    client = client or NseClient()
    text = client.fetch_index_history_csv(name)
    df = parse_index_history_csv(text)
    cache.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache, index=False)
    return df


# ================================================================== #
# 3. ASM / GSM compliance lists (live-only)                          #
# ================================================================== #

def parse_compliance_json(data) -> set[str]:
    """Extract the set of NSE symbols from an ASM/GSM JSON payload.

    NSE's surveillance JSONs nest the rows under varying keys ('data', 'longterm',
    'shortterm', ...). Rather than couple to one shape, recursively collect every
    'symbol' value found anywhere in the structure.
    """
    if isinstance(data, (str, bytes)):
        data = json.loads(data)
    found: set[str] = set()

    def _walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.lower() == "symbol" and isinstance(v, str) and v.strip():
                    found.add(v.strip().upper())
                else:
                    _walk(v)
        elif isinstance(obj, list):
            for it in obj:
                _walk(it)

    _walk(data)
    return found


def fetch_compliance_flags(client: "NseClient | None" = None) -> set[str]:
    """Return the union of currently ASM- and GSM-flagged NSE symbols (live veto, §13c)."""
    client = client or NseClient()
    flagged: set[str] = set()
    for fetch in (client.fetch_asm_json, client.fetch_gsm_json):
        try:
            flagged |= parse_compliance_json(fetch())
        except Exception as e:  # one feed failing must not blank the whole veto
            logger.warning("compliance fetch failed: %s", e)
    return flagged


# ================================================================== #
# Networked client (cached, polite, WAF-bootstrapped)                #
# ================================================================== #

class NseClient:
    """Thin session wrapper for niftyindices CSVs + NSE JSON endpoints.

    NSE's API host (www.nseindia.com) requires a cookie obtained by first hitting the
    homepage with a browser UA; `_bootstrap()` handles that lazily.
    """

    _NSE = "https://www.nseindia.com"
    _ASM = "https://www.nseindia.com/api/reportASM"
    _GSM = "https://www.nseindia.com/api/reportGSM"

    def __init__(self, delay: float = 1.0, session: requests.Session | None = None,
                 cache_dir: Path | str | None = None):
        self.delay = delay
        self.cache_dir = Path(cache_dir or _DEFAULT_CACHE)
        self.s = session or requests.Session()
        self.s.headers.update({
            "User-Agent": _UA,
            "Accept-Language": "en-US,en;q=0.9",
        })
        self._bootstrapped = False

    def _bootstrap(self):
        if self._bootstrapped:
            return
        try:
            self.s.get(self._NSE, headers={"Accept": "text/html"}, timeout=30)
            self._bootstrapped = True
        except requests.RequestException as e:
            raise NseError(f"NSE cookie bootstrap failed: {e}") from e

    # --- niftyindices constituent CSVs --------------------------------- #
    def fetch_constituents_csv(self, index_name: str) -> str:
        fn = _INDEX_FILES.get(index_name.upper())
        if not fn:
            raise NseError(f"no constituent file mapped for {index_name!r} "
                           f"(known: {sorted(_INDEX_FILES)})")
        url = f"{_CONSTITUENT_BASE}/{fn}"
        if self.delay:
            time.sleep(self.delay)
        r = self.s.get(url, headers={"Referer": "https://niftyindices.com/"}, timeout=60)
        if r.status_code != 200:
            raise NseError(f"{index_name}: HTTP {r.status_code} from {url}")
        return r.text

    # --- niftyindices historical index CSV ----------------------------- #
    def fetch_index_history_csv(self, name: str) -> str:
        """Best-effort historical-index CSV fetch.

        niftyindices serves history via a POST to its Backpage endpoint (fragile,
        periodically changes). Left as a thin best-effort call; callers normally rely
        on the on-disk cache (`fetch_momentum_index(use_cache=True)`).
        """
        raise NseError(
            "live niftyindices history fetch not wired — provide a cached CSV via "
            "fetch_momentum_index(cache_dir=...) or implement the Backpage POST. "
            f"(requested index: {name!r})")

    # --- NSE surveillance JSON ----------------------------------------- #
    def _api_json(self, url: str):
        self._bootstrap()
        if self.delay:
            time.sleep(self.delay)
        r = self.s.get(url, headers={"Accept": "application/json",
                                     "Referer": self._NSE + "/"}, timeout=60)
        if r.status_code != 200:
            raise NseError(f"HTTP {r.status_code} from {url}")
        return r.json()

    def fetch_asm_json(self):
        return self._api_json(self._ASM)

    def fetch_gsm_json(self):
        return self._api_json(self._GSM)
