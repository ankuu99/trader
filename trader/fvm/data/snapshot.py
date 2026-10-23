"""
Trendlyne Data-Downloader snapshot layer — the weekly full-market excel export.

Trendlyne's "Data Downloader" xlsx (Stocks-data-IND-<d>-<Mon>-<YYYY>.xlsx) is a one-day
snapshot of ~5,700 NSE names × 163 columns, several of which the FVM API stack has no
other source for: Piotroski score, DVM (Durability/Valuation/Momentum) scores, promoter
pledge (fills the 0%-coverage gap in the scoring lab), monthly MF/FII holding deltas,
and valuation-vs-own-history percentiles.

Storage: wide table `tl_snapshot` in fvm.db keyed (symbol, as_of). Each weekly download
appends a new vintage — snapshots STACK into our own history of fields whose past
Trendlyne never exposes (pledge, holdings flow, DVM). A snapshot is knowable only from
its as_of date, so reads take `asof` and return the latest snapshot on/before it.

NOT for backtests: a single snapshot has no depth, and the fields (DVM, Piotroski) are
Trendlyne-computed with unknown revision behaviour. Live cockpit / discretionary use only.

Ingest:  python scripts/tl_snapshot.py            (auto-finds newest xlsx in data/)
"""

import re
from datetime import datetime
from pathlib import Path

from trader.core.logger import get_logger

logger = get_logger(__name__)

# short field name -> excel column header (curated subset of the 163 columns)
NUMERIC_FIELDS: dict[str, str] = {
    # identity / size
    "price": "Current Price",
    "mcap_cr": "Market Capitalization",
    # Trendlyne DVM
    "durability": "Trendlyne Durability Score",
    "valuation": "Trendlyne Valuation Score",
    "momentum": "Trendlyne Momentum Score",
    # quality
    "piotroski": "Piotroski Score",
    "roe": "ROE Annual %",
    "roa": "RoA Annual %",
    "opm_qtr": "Operating Profit Margin Qtr %",
    "opm_qtr_4qago": "Operating Profit Margin Qtr 4Qtr ago %",
    # growth
    "rev_yoy_qtr": "Revenue Growth Qtr YoY %",
    "np_yoy_qtr": "Net Profit Qtr Growth YoY %",
    "rev_qoq": "Revenue QoQ Growth %",
    "np_qoq": "Net Profit QoQ Growth %",
    "rev_yoy_annual": "Revenue Growth Annual YoY %",
    "np_yoy_annual": "Net Profit Annual YoY Growth %",
    "eps_ttm_growth": "EPS TTM Growth %",
    # cash
    "cfo_annual": "Cash from Operating Activity Annual",
    "net_cash_flow_annual": "Net Cash Flow Annual",
    # valuation
    "pe_ttm": "PE TTM Price to Earnings",
    "pe_3y_avg": "PE 3Yr Average",
    "pe_5y_avg": "PE 5Yr Average",
    "pct_days_below_pe": "%Days traded below current PE Price to Earnings",
    "sector_pe": "Sector PE TTM",
    "industry_pe": "Industry PE TTM",
    "peg_ttm": "PEG TTM PE to Growth",
    "pb": "Price to Book Value Adjusted",
    "pct_days_below_pb": "%Days traded below current Price to Book Value",
    "eps_ttm": "Basic EPS TTM",
    # technicals / risk
    "sma50": "Day SMA50",
    "sma200": "Day SMA200",
    "rsi_day": "Day RSI",
    "adx_day": "Day ADX",
    "beta_1y": "Beta 1Year",
    "chg_1m_pct": "Month Change %",
    "chg_qtr_pct": "Qtr Change %",
    "chg_1y_pct": "1Yr change %",
    "yr1_low": "1Yr Low",
    "yr1_high": "1Yr High",
    # liquidity
    "vol_3m_avg": "3Month Volume Avg",
    # ownership & flows
    "promoter": "Promoter holding latest %",
    "promoter_chg_qoq": "Promoter holding change QoQ %",
    "promoter_chg_4q": "Promoter holding change 4Qtr %",
    "pledge": "Promoter holding pledge percentage % Qtr",
    "pledge_chg_qoq": "Promoter pledge change QoQ %",
    "mf": "MF holding current Qtr %",
    "mf_chg_qoq": "MF holding change QoQ %",
    "mf_chg_1m": "MF holding change 1Month %",
    "mf_chg_3m": "MF holding change 3Month%",
    "fii": "FII holding current Qtr %",
    "fii_chg_qoq": "FII holding change QoQ %",
    "fii_chg_4q": "FII holding change 4Qtr %",
    "inst": "Institutional holding current Qtr %",
    "inst_chg_qoq": "Institutional holding change QoQ %",
}

TEXT_FIELDS: dict[str, str] = {
    "name": "Stock Name",
    "sector": "sector_name",
    "industry": "Industry Name",
    "dvm_class": "DVM_classification_text",
    "result_date": "Result Announced Date",
}

ALL_FIELDS = list(TEXT_FIELDS) + list(NUMERIC_FIELDS)

_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def asof_from_filename(path: str | Path) -> str | None:
    """'Stocks-data-IND-3-Jul-2026.xlsx' -> '2026-07-03'."""
    m = re.search(r"(\d{1,2})-([A-Za-z]{3})-(\d{4})", Path(path).name)
    if not m or m.group(2).capitalize() not in _MONTHS:
        return None
    return f"{int(m.group(3)):04d}-{_MONTHS[m.group(2).capitalize()]:02d}-{int(m.group(1)):02d}"


# ------------------------------------------------------------------ #
# Schema + write                                                      #
# ------------------------------------------------------------------ #

def _ensure_schema(store) -> None:
    cols = ",\n".join(f"    {f} TEXT" for f in TEXT_FIELDS) + ",\n" + \
           ",\n".join(f"    {f} REAL" for f in NUMERIC_FIELDS)
    with store._conn() as conn:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS tl_snapshot (
                symbol TEXT NOT NULL,
                as_of  TEXT NOT NULL,
{cols},
                ingested_at TEXT NOT NULL,
                PRIMARY KEY (symbol, as_of)
            )""")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_tl_snap_asof ON tl_snapshot (as_of)")


def parse_snapshot_xlsx(path: str | Path):
    """Parse the Data-Downloader xlsx → (as_of, rows). Each row is a dict keyed by the
    short field names, plus 'symbol'. Plan-gated 'Export NA' cells and non-numeric
    junk coerce to None. Rows without an NSE code are dropped."""
    import pandas as pd
    path = Path(path)
    as_of = asof_from_filename(path) or datetime.fromtimestamp(
        path.stat().st_mtime).date().isoformat()
    df = pd.read_excel(path)
    if "NSEcode" not in df.columns:
        raise ValueError(f"{path.name}: no NSEcode column — not a Data-Downloader export?")
    rows = []
    for rec in df.to_dict("records"):
        sym = rec.get("NSEcode")
        if not isinstance(sym, str) or not sym.strip():
            continue
        row: dict = {"symbol": sym.strip().upper()}
        for f, col in TEXT_FIELDS.items():
            v = rec.get(col)
            row[f] = str(v) if isinstance(v, str) and v not in ("", "Export NA") else None
        for f, col in NUMERIC_FIELDS.items():
            v = pd.to_numeric(rec.get(col), errors="coerce")
            row[f] = None if pd.isna(v) else float(v)
        rows.append(row)
    return as_of, rows


def ingest_snapshot(store, path: str | Path) -> tuple[str, int]:
    """Ingest one xlsx into tl_snapshot. Idempotent per (symbol, as_of) — re-ingesting
    the same file replaces that vintage in place. Returns (as_of, row_count)."""
    _ensure_schema(store)
    as_of, rows = parse_snapshot_xlsx(path)
    now = datetime.now().isoformat(timespec="seconds")
    cols = ["symbol", "as_of", *ALL_FIELDS, "ingested_at"]
    sql = (f"INSERT OR REPLACE INTO tl_snapshot ({', '.join(cols)}) "
           f"VALUES ({', '.join('?' * len(cols))})")
    payload = [tuple([r["symbol"], as_of, *[r[f] for f in ALL_FIELDS], now]) for r in rows]
    with store._conn() as conn:
        conn.executemany(sql, payload)
    logger.info("tl_snapshot ingested | as_of=%s rows=%d file=%s", as_of, len(rows), Path(path).name)
    return as_of, len(rows)


# ------------------------------------------------------------------ #
# Reads                                                                #
# ------------------------------------------------------------------ #

def snapshot_dates(store) -> list[str]:
    """All ingested snapshot vintages, ascending. Empty if the table doesn't exist yet."""
    with store._conn() as conn:
        try:
            rows = conn.execute("SELECT DISTINCT as_of FROM tl_snapshot ORDER BY as_of").fetchall()
        except Exception:
            return []
    return [r[0] for r in rows]


def _latest_asof(store, asof: str | None) -> str | None:
    dates = snapshot_dates(store)
    if asof is not None:
        dates = [d for d in dates if d <= asof]
    return dates[-1] if dates else None


def read_snapshot(store, symbol: str, asof: str | None = None) -> dict | None:
    """One name's row from the latest snapshot on/before `asof` (or latest overall).
    Returns None if no snapshot covers it. Result includes 'as_of'."""
    target = _latest_asof(store, asof)
    if target is None:
        return None
    with store._conn() as conn:
        row = conn.execute(
            "SELECT * FROM tl_snapshot WHERE symbol=? AND as_of=?",
            (symbol.upper().replace("NSE:", ""), target)).fetchone()
    return dict(row) if row else None


def read_universe(store, asof: str | None = None) -> list[dict]:
    """All rows of the latest snapshot on/before `asof` (or latest overall)."""
    target = _latest_asof(store, asof)
    if target is None:
        return []
    with store._conn() as conn:
        rows = conn.execute("SELECT * FROM tl_snapshot WHERE as_of=?", (target,)).fetchall()
    return [dict(r) for r in rows]


def snapshot_history(store, symbol: str, fields: list[str]) -> list[dict]:
    """One name's requested fields across ALL vintages, ascending — how things evolve
    week over week as downloads stack."""
    sel = ", ".join(["as_of", *fields])
    with store._conn() as conn:
        try:
            rows = conn.execute(
                f"SELECT {sel} FROM tl_snapshot WHERE symbol=? ORDER BY as_of",
                (symbol.upper().replace("NSE:", ""),)).fetchall()
        except Exception:
            return []
    return [dict(r) for r in rows]


# ------------------------------------------------------------------ #
# Quality screen — the "good stocks" funnel                            #
# ------------------------------------------------------------------ #

MIN_TURNOVER_LAKH = 50.0  # ₹50L/day, same liquidity floor as stock-selection guidance

SCREEN_GATES: list[tuple[str, str]] = [
    # (gate key, human description) — order defines the funnel
    ("liquidity", f"mcap known + turnover ≥ ₹{MIN_TURNOVER_LAKH:.0f}L/day"),
    ("durability", "Trendlyne Durability ≥ 55"),
    ("piotroski", "Piotroski ≥ 6"),
    ("roe", "ROE ≥ 15%"),
    ("pledge", "zero promoter pledge"),
    ("cfo", "positive operating cash flow"),
    ("promoter", "promoter not dumping (4Q change ≥ −1pp)"),
    ("inst_flow", "institutions accumulating (MF+FII QoQ > 0)"),
    ("valuation", "valuation sane (V-score ≥ 40 or PE < industry PE)"),
    ("momentum", "Momentum score ≥ 55"),
    ("trend", "price above 200DMA"),
]


def _passes(row: dict, gate: str) -> bool:
    g = lambda k: row.get(k)  # noqa: E731
    turnover_l = ((g("price") or 0) * (g("vol_3m_avg") or 0)) / 1e5
    checks = {
        "liquidity": g("mcap_cr") is not None and g("price") is not None
                     and turnover_l >= MIN_TURNOVER_LAKH,
        "durability": (g("durability") or 0) >= 55,
        "piotroski": (g("piotroski") or 0) >= 6,
        "roe": (g("roe") or 0) >= 15,
        "pledge": (g("pledge") or 0) <= 0,
        "cfo": (g("cfo_annual") or 0) > 0,
        "promoter": (g("promoter_chg_4q") or 0) >= -1.0,
        "inst_flow": ((g("mf_chg_qoq") or 0) + (g("fii_chg_qoq") or 0)) > 0,
        "valuation": (g("valuation") or 0) >= 40
                     or (g("pe_ttm") is not None and g("industry_pe") is not None
                         and g("pe_ttm") < g("industry_pe")),
        "momentum": (g("momentum") or 0) >= 55,
        "trend": g("price") is not None and g("sma200") is not None
                 and g("price") > g("sma200"),
    }
    return checks[gate]


def quality_screen(rows: list[dict]) -> tuple[list[dict], list[tuple[str, int]]]:
    """Run the funnel over snapshot rows → (survivors sorted by durability desc,
    funnel [(description, count-after-gate), ...])."""
    funnel = []
    survivors = rows
    for gate, desc in SCREEN_GATES:
        survivors = [r for r in survivors if _passes(r, gate)]
        funnel.append((desc, len(survivors)))
    survivors = sorted(survivors, key=lambda r: (r.get("durability") or 0), reverse=True)
    return survivors, funnel


# ------------------------------------------------------------------ #
# Watchlist red-flag read                                              #
# ------------------------------------------------------------------ #

def watchlist_flags(row: dict) -> list[str]:
    """Snapshot-derived cautions for one held/watched name. Advisory strings only."""
    flags = []
    g = lambda k: row.get(k)  # noqa: E731
    if (g("pledge") or 0) > 25:
        flags.append(f"HIGH pledge {g('pledge'):.1f}%")
    elif (g("pledge") or 0) > 10:
        flags.append(f"pledge {g('pledge'):.1f}%")
    if g("promoter_chg_4q") is not None and g("promoter_chg_4q") < -2.0:
        flags.append(f"promoter −{abs(g('promoter_chg_4q')):.1f}pp/4Q")
    if g("piotroski") is not None and g("piotroski") <= 3:
        flags.append(f"Piotroski {g('piotroski'):.0f}")
    if g("durability") is not None and g("durability") < 50:
        flags.append(f"Durability {g('durability'):.0f}")
    inst = (g("mf_chg_qoq") or 0) + (g("fii_chg_qoq") or 0)
    if (g("mf_chg_qoq") is not None or g("fii_chg_qoq") is not None) and inst < -1.5:
        flags.append(f"institutions exiting {inst:+.1f}pp QoQ")
    if g("pct_days_below_pe") is not None and g("pct_days_below_pe") >= 95:
        flags.append(f"PE at {g('pct_days_below_pe'):.0f}th pctile of own history")
    if g("dvm_class") and any(w in g("dvm_class") for w in ("Trap", "Falling", "Weak")):
        flags.append(f"DVM: {g('dvm_class')}")
    return flags
