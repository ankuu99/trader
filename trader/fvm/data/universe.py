"""
Universe builder (Phase 0.3) — the tradeable FVM universe for any as-of date.

eligible_universe(asof) = PIT index members  ∩  non-financial  ∩  (optional liquidity)

- Membership: FVMStore.members_asof (populated by nse.py; PIT-correct).
- Sector / financials-exclusion: the niftyindices constituent CSV carries an "Industry"
  column = NSE macro sector. We persist it (sector_map) and exclude financials (design:
  "financials excluded for v1", §1b). The same sector_map feeds sector-relative
  normalization in scoring (§3).
- Liquidity: a pluggable predicate (needs price data, wired in a later phase). Nifty-500
  membership already implies decent liquidity, so it's an optional refinement for v1.
"""

import csv
import io

from trader.core.logger import get_logger
from trader.fvm.data.nse import NseClient, parse_constituents_csv  # noqa: F401 (re-export)

logger = get_logger(__name__)

# NSE macro-industry labels treated as financials (excluded for v1, §1b). Matched
# case-insensitively as substrings so "Financial Services", "Banks", etc. all hit.
FINANCIAL_SECTORS = (
    "financial services", "bank", "insurance", "nbfc", "finance",
    "capital markets", "asset management", "financial",
)


def is_financial(sector: str | None) -> bool:
    if not sector:
        return False
    s = sector.strip().lower()
    return any(key in s for key in FINANCIAL_SECTORS)


def parse_constituents_with_sector(text: str) -> list[dict]:
    """Parse a niftyindices constituent CSV -> [{symbol, sector}].

    Columns are typically: Company Name, Industry, Symbol, Series, ISIN Code.
    """
    out: list[dict] = []
    for row in csv.DictReader(io.StringIO(text)):
        sym = sector = None
        for k, v in row.items():
            if not k:
                continue
            kl = k.strip().lower()
            if kl == "symbol":
                sym = (v or "").strip().upper()
            elif kl in ("industry", "sector"):
                sector = (v or "").strip()
        if sym:
            out.append({"symbol": sym, "sector": sector or "Unknown"})
    return out


def ingest_sectors(store, index_name: str = "NIFTY500", client: NseClient | None = None) -> int:
    """Fetch the constituent CSV and persist each symbol's sector to sector_map."""
    client = client or NseClient()
    text = client.fetch_constituents_csv(index_name)
    rows = parse_constituents_with_sector(text)
    n = store.write_sectors(rows)
    logger.info("ingest_sectors | %s | %d symbols", index_name, n)
    return n


def eligible_universe(store, asof: str, index_name: str = "NIFTY500",
                      exclude_financials: bool = True,
                      liquidity_ok=None) -> list[str]:
    """The tradeable universe on date `asof`.

    Args:
        store: FVMStore.
        asof: 'YYYY-MM-DD'.
        index_name: PIT membership index (default NIFTY500).
        exclude_financials: drop financial-sector names (§1b).
        liquidity_ok: optional callable(symbol) -> bool (needs price data; default None
            = no liquidity gate). Wired in a later phase.

    Returns sorted list of NSE symbols.
    """
    members = store.members_asof(index_name, asof)
    sectors = store.sectors_map()
    out = []
    for sym in members:
        if exclude_financials and is_financial(sectors.get(sym)):
            continue
        if liquidity_ok is not None and not liquidity_ok(sym):
            continue
        out.append(sym)
    return sorted(out)
