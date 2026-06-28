"""
FVM Cockpit — framework-agnostic data layer.

The UI never reimplements engine logic: every number here comes from the tested
`scoring` / `vetoes` / `technical` / `handoff` functions. This module is pure
(no Streamlit import) so it stays testable; the Streamlit app wraps these with
`st.cache_data`. Reads cached data only (run fvm_ingest + fvm_prices first).
"""

import datetime
import sqlite3
from pathlib import Path

import pandas as pd

from trader.data.store import Store
from trader.fvm import factors, handoff, scoring, technical, vetoes
from trader.fvm.data import prices, universe
from trader.fvm.data.store import FVMStore
from trader.fvm.fields import (
    BASIC_EPS_Q, CFO_A, DE_A, INT_COVERAGE_A, NET_PROFIT_A, NET_PROFIT_Q,
    OPM_Q, REVENUE_GROWTH_Q, ROCE_A, TOTAL_REVENUE_Q,
)
from trader.fvm.scoring import FACTORS, PILLAR_WEIGHTS

PILLARS = list(PILLAR_WEIGHTS)

# Fundamentals history rows for the Stock Detail page: (label, statement, field)
FUNDAMENTAL_HISTORY = [
    ("Revenue (Qtr)",      *TOTAL_REVENUE_Q),
    ("Net Profit (Qtr)",   *NET_PROFIT_Q),
    ("OPM % (Qtr)",        *OPM_Q),
    ("Rev growth YoY %",   *REVENUE_GROWTH_Q),
    ("Basic EPS (Qtr)",    *BASIC_EPS_Q),
    ("CFO (Annual)",       *CFO_A),
    ("Net Profit (Annual)", *NET_PROFIT_A),
    ("D/E (Annual)",       *DE_A),
    ("Int coverage (Annual)", *INT_COVERAGE_A),
    ("ROCE % (Annual)",    *ROCE_A),
]

SHAREHOLDING_FIELDS = ["promoter", "fii", "dii", "pledge", "holders"]


def scored_symbols(db_path: str) -> list[str]:
    con = sqlite3.connect(db_path)
    try:
        return [r[0] for r in con.execute(
            "SELECT DISTINCT symbol FROM fundamentals ORDER BY symbol").fetchall()]
    finally:
        con.close()


def _decision(diag: dict) -> str:
    """One-word reason a name is / isn't a candidate (same taxonomy as the CLI)."""
    if not diag.get("veto_passed", True):
        return "VETOED"
    if not diag.get("gate_a", False):
        return "WEAK_FUND"
    if not diag.get("gate_b", False):
        return "NO_TREND"
    if not diag.get("trigger", False):
        return "NO_TIMING"
    return "CANDIDATE"


def _load_prices(market_db: str, symbols: list[str], asof: str,
                 from_year: int = 2015, min_bars: int = 60) -> dict[str, pd.DataFrame]:
    store = Store(Path(market_db))
    return prices.load_universe_prices(
        None, store, symbols, datetime.datetime(from_year, 1, 1),
        datetime.datetime.fromisoformat(asof), token_map={}, min_bars=min_bars)


def build_board(db: str, market_db: str, asof: str) -> dict:
    """Score the whole ingested universe as of `asof`. Returns a serializable dict:
       {asof, priced, total, board (DataFrame), candidates (list), diag (dict)}."""
    fvm = FVMStore(db)
    symbols = scored_symbols(db)
    asof_ts = pd.to_datetime(asof)
    price_data = _load_prices(market_db, symbols, asof)
    universe = list(price_data)

    if not universe:
        return {"asof": asof, "priced": 0, "total": len(symbols),
                "board": pd.DataFrame(), "candidates": [], "diag": {}}

    pp = prices.price_provider(price_data, asof)
    scores = scoring.compute_scores(fvm, universe, asof, price_provider=pp)
    vmap = {s: vetoes.check_vetoes(fvm, s, asof) for s in universe}
    tmap = {}
    for s in universe:
        d = price_data[s]
        d = d[pd.to_datetime(d["timestamp"]) <= asof_ts]
        tmap[s] = technical.evaluate(d)

    cands, diag = handoff.select_candidates(scores, vmap, tmap, regime_ok=True)
    sectors = fvm.sectors_map()

    rows = []
    for s in universe:
        sc = scores[s]
        t = tmap[s]
        passed, reasons = vmap[s]
        dec = _decision(diag.get(s, {}))
        note = ",".join(reasons) if not passed else ("parabolic_ext" if t["extension_vetoed"] else "")
        row = {
            "symbol": s, "sector": sectors.get(s, "Unknown"),
            "composite": round(sc["composite"], 1),
            "trend": round(t["trend_score"], 2), "timing": round(t["timing_score"], 2),
            "technical": round(t["technical_score"], 3),
            "decision": dec, "note": note,
        }
        for p in PILLARS:
            row[p] = round(sc["pillars"][p], 2)
        rows.append(row)

    board = pd.DataFrame(rows).sort_values("composite", ascending=False).reset_index(drop=True)
    return {"asof": asof, "priced": len(universe), "total": len(symbols),
            "board": board, "candidates": cands, "diag": diag}


def load_stock(db: str, market_db: str, symbol: str, asof: str) -> dict:
    """Everything the Stock Detail page needs for one name, as of `asof`."""
    symbol = symbol.upper()
    fvm = FVMStore(db)
    asof_ts = pd.to_datetime(asof)
    price_data = _load_prices(market_db, [symbol], asof)
    daily = price_data.get(symbol)
    if daily is None or daily.empty:
        return {"symbol": symbol, "asof": asof, "priced": False}

    daily = daily[pd.to_datetime(daily["timestamp"]) <= asof_ts].reset_index(drop=True)
    weekly = technical.resample_weekly(daily)

    pp = prices.price_provider(price_data, asof)
    scores = scoring.compute_scores(fvm, [symbol], asof, price_provider=pp)[symbol]
    passed, reasons = vetoes.check_vetoes(fvm, symbol, asof)
    tech = technical.evaluate(daily, weekly)
    last_price = pp(symbol)
    raw = factors.all_factors(fvm, symbol, asof, price=last_price)

    factor_rows = []
    for fname, (pillar, w, direction, ntype, scope) in FACTORS.items():
        factor_rows.append({
            "factor": fname, "pillar": pillar, "weight": w, "direction": direction,
            "normalized": round(scores["factors"].get(fname, 0.5), 3),
            "raw": raw.get(fname),
        })

    fundamentals = {}
    for label, statement, field in FUNDAMENTAL_HISTORY:
        series = fvm.read_fundamental_asof(symbol, statement, "consolidated", field, asof)
        if not series:
            series = fvm.read_fundamental_asof(symbol, statement, "standalone", field, asof)
        if series:
            fundamentals[label] = series

    shareholding = {}
    for field in SHAREHOLDING_FIELDS:
        series = fvm.read_shareholding_asof(symbol, field, asof)
        if series:
            shareholding[field] = series

    return {
        "symbol": symbol, "asof": asof, "priced": True,
        "daily": daily, "weekly": weekly,
        "scores": scores, "veto": {"passed": passed, "reasons": reasons},
        "technical": tech, "last_price": last_price,
        "factors": pd.DataFrame(factor_rows),
        "fundamentals": fundamentals, "shareholding": shareholding,
        "sector": fvm.sectors_map().get(symbol, "Unknown"),
    }


# ------------------------------------------------------------------ #
# Coverage / ops (U2) — cheap SQL aggregates, no scoring sweep        #
# ------------------------------------------------------------------ #
def _fundamentals_coverage(db: str) -> dict[str, dict]:
    """Per ingested symbol: quarter/annual period depth, latest quarter, last ingest."""
    con = sqlite3.connect(db)
    try:
        rows = con.execute(
            """SELECT symbol,
                      SUM(statement='quarter') AS q_rows,
                      SUM(statement='annual')  AS a_rows,
                      MAX(CASE WHEN statement='quarter' THEN period END) AS last_q,
                      MAX(CASE WHEN statement='annual'  THEN period END) AS last_a,
                      MAX(ingested_at) AS ingested
               FROM fundamentals GROUP BY symbol""").fetchall()
        depth = {}
        for sym, *_ in rows:
            q = con.execute("SELECT COUNT(DISTINCT period) FROM fundamentals "
                            "WHERE symbol=? AND statement='quarter'", (sym,)).fetchone()[0]
            a = con.execute("SELECT COUNT(DISTINCT period) FROM fundamentals "
                            "WHERE symbol=? AND statement='annual'", (sym,)).fetchone()[0]
            depth[sym] = (q, a)
        sh = {r[0] for r in con.execute("SELECT DISTINCT symbol FROM shareholding").fetchall()}
    finally:
        con.close()
    out = {}
    for sym, q_rows, a_rows, last_q, last_a, ingested in rows:
        q_depth, a_depth = depth[sym]
        out[sym] = {"q_depth": q_depth, "a_depth": a_depth, "last_q": last_q,
                    "last_a": last_a, "ingested": ingested, "has_shareholding": sym in sh}
    return out


def _price_coverage(market_db: str) -> dict[str, dict]:
    con = sqlite3.connect(market_db)
    try:
        rows = con.execute(
            "SELECT instrument, COUNT(*), MIN(timestamp), MAX(timestamp) "
            "FROM candles WHERE timeframe='day' GROUP BY instrument").fetchall()
    finally:
        con.close()
    out = {}
    for inst, n, lo, hi in rows:
        sym = inst.split(":", 1)[1] if ":" in inst else inst
        out[sym.upper()] = {"bars": n, "first": (lo or "")[:10], "last": (hi or "")[:10]}
    return out


def coverage(db: str, market_db: str, asof: str, index_name: str = "NIFTY500") -> dict:
    """Universe ingest/price coverage for the ops page. Cheap aggregates only."""
    fvm = FVMStore(db)
    target = universe.eligible_universe(fvm, asof, index_name=index_name)
    funda = _fundamentals_coverage(db)
    px = _price_coverage(market_db)
    sectors = fvm.sectors_map()
    ingested = set(funda)

    rows = []
    for sym in sorted(set(target) | ingested):
        f = funda.get(sym, {})
        p = px.get(sym, {})
        rows.append({
            "symbol": sym, "sector": sectors.get(sym, "Unknown"),
            "in_universe": sym in target, "ingested": sym in ingested,
            "q_depth": f.get("q_depth", 0), "a_depth": f.get("a_depth", 0),
            "last_q": f.get("last_q", ""), "shareholding": bool(f.get("has_shareholding")),
            "price_bars": p.get("bars", 0), "price_last": p.get("last", ""),
            "last_ingest": (f.get("ingested") or "")[:10],
        })
    df = pd.DataFrame(rows)

    missing = sorted(set(target) - ingested)
    not_priced = sorted(s for s in ingested if not px.get(s, {}).get("bars"))
    return {
        "asof": asof, "df": df,
        "target": len(target), "ingested": len(ingested),
        "priced": sum(1 for s in ingested if px.get(s, {}).get("bars")),
        "missing": missing, "not_priced": not_priced,
        "last_ingest": max((f.get("ingested") or "" for f in funda.values()), default=""),
        "min_q_depth": min((f["q_depth"] for f in funda.values()), default=0),
        "max_q_depth": max((f["q_depth"] for f in funda.values()), default=0),
    }
