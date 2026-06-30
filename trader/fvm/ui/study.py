"""
Single-stock STUDY data layer — the "study one company in depth, in one place" backend.

Reframing note: the FVM *strategy* (timing entries to beat momentum) is a Milestone-A FAIL.
This module repurposes the same tested fundamental engine for what it's actually good at —
**research for discretionary long-term investing**: a full dossier on one name (the conviction
scorecard from `conviction.py`, multi-year fundamental trajectories, and a head-to-head peer
comparison) plus an on-demand fetch so ANY NSE stock — not just the ingested universe — can be
pulled live (Trendlyne fincsv + Screener + Kite) and studied.

Pure/framework-agnostic (no Streamlit). The Streamlit page wraps these with st.cache_data.
"""

import datetime
from pathlib import Path

import pandas as pd

from trader.fvm import conviction as cv
from trader.fvm import factors as fac
from trader.fvm import fields as F
from trader.fvm.data import prices
from trader.fvm.data.store import FVMStore
from trader.fvm.ui import data as fdata

# Compact peer-comparison metrics — all price-free (read straight from the PIT store) so a
# peer table is cheap and never needs a live quote per peer. "which of these is the better bet".
PEER_METRICS = [
    ("ROCE %", F.ROCE_A),
    ("ROE %", F.ROE_A),
    ("Profit 5y %", F.NET_PROFIT_5Y_A),
    ("Rev 5y %", F.REVENUE_5Y_A),
    ("D/E", F.DE_A),
    ("EV/EBITDA", F.EV_EBITDA_A),
    ("Promoter %", None),  # special: from shareholding table
]

# Multi-year trajectories for the study charts: (label, statement-field spec | "SH:<field>")
TRAJECTORIES = [
    ("Revenue (Annual)", F.TOTAL_REVENUE_A),
    ("Net Profit (Annual)", F.NET_PROFIT_A),
    ("Net margin %", F.NET_PROFIT_MARGIN_A),
    ("ROCE %", F.ROCE_A),
    ("ROE %", F.ROE_A),
    ("D/E", F.DE_A),
    ("CFO (Annual)", F.CFO_A),
    ("Interest coverage", F.INT_COVERAGE_A),
]


def _latest_metric(store, symbol, spec, asof):
    if spec is None:
        return None
    return fac._latest(fac._series(store, symbol, spec, asof))


def _promoter(store, symbol, asof):
    d = store.read_shareholding_asof(symbol, F.SH_PROMOTER, asof)
    vals = [v for _, v in sorted(d.items()) if v is not None]
    return vals[-1] if vals else None


def peer_metrics_row(store, symbol, asof) -> dict:
    """Compact long-term metrics for one name (price-free)."""
    row = {"symbol": symbol}
    for label, spec in PEER_METRICS:
        row[label] = (_promoter(store, symbol, asof) if spec is None
                      else _latest_metric(store, symbol, spec, asof))
    return row


def peer_table(board: pd.DataFrame, store, symbol: str, asof: str,
               max_peers: int = 12) -> dict:
    """Sector peers ranked head-to-head. `board` is build_board()['board'] (has sector +
    composite). Augments each peer with the price-free long-term metrics and flags the subject.
    Returns {sector, df, subject}; df sorted by composite desc."""
    symbol = symbol.upper()
    if board is None or board.empty or symbol not in set(board["symbol"]):
        return {"sector": None, "df": pd.DataFrame(), "subject": symbol}
    sector = board.loc[board["symbol"] == symbol, "sector"].iloc[0]
    peers = board[board["sector"] == sector].copy()
    if len(peers) > max_peers:
        # keep the subject + the top names by composite
        keep = set(peers.nlargest(max_peers, "composite")["symbol"]) | {symbol}
        peers = peers[peers["symbol"].isin(keep)]

    rows = []
    for _, r in peers.iterrows():
        m = peer_metrics_row(store, r["symbol"], asof)
        m.update({"composite": r["composite"], "trend": r.get("trend"),
                  "decision": r.get("decision"), "is_subject": r["symbol"] == symbol})
        rows.append(m)
    df = pd.DataFrame(rows).sort_values("composite", ascending=False).reset_index(drop=True)
    return {"sector": sector, "df": df, "subject": symbol}


def trajectories(store, symbol: str, asof: str) -> dict[str, dict]:
    """Annual (period -> value) series for the long-term trajectory charts. Tries consolidated
    then standalone. Plus CFO-vs-PAT and the shareholding series for the ownership chart."""
    symbol = symbol.upper()
    out = {}
    for label, spec in TRAJECTORIES:
        s = fac._series(store, symbol, spec, asof, "consolidated")
        if not s:
            s = fac._series(store, symbol, spec, asof, "standalone")
        if s:
            out[label] = dict(s)
    # PAT alongside CFO for the earnings-quality chart
    pat = fac._series(store, symbol, F.NET_PROFIT_A, asof, "consolidated") or \
        fac._series(store, symbol, F.NET_PROFIT_A, asof, "standalone")
    if pat:
        out["Net Profit (Annual)"] = dict(pat)
    sh = {}
    for field in ["promoter", "fii", "dii", "pledge"]:
        d = store.read_shareholding_asof(symbol, field, asof)
        if d:
            sh[field] = {p: v for p, v in sorted(d.items()) if v is not None}
    out["_shareholding"] = sh
    return out


def study_stock(db: str, market_db: str, symbol: str, asof: str,
                board: pd.DataFrame | None = None) -> dict:
    """Full single-stock dossier: load_stock detail + conviction scorecard + multi-year
    trajectories + sector peer comparison. `board` (whole-universe scored, for peers) is
    optional — pass the cached build_board()['board'] from the UI to avoid recomputation."""
    symbol = symbol.upper()
    detail = fdata.load_stock(db, market_db, symbol, asof)
    if not detail.get("priced"):
        return {"symbol": symbol, "asof": asof, "priced": False, "detail": detail}

    store = FVMStore(db)
    card = cv.scorecard(
        store, symbol, asof,
        price=detail["last_price"], daily=detail["daily"],
        veto=(detail["veto"]["passed"], detail["veto"]["reasons"]),
        technical=detail["technical"],
    )
    traj = trajectories(store, symbol, asof)
    peers = peer_table(board, symbol=symbol, store=store, asof=asof) if board is not None \
        else {"sector": detail.get("sector"), "df": pd.DataFrame(), "subject": symbol}

    return {"symbol": symbol, "asof": asof, "priced": True,
            "detail": detail, "conviction": card, "trajectories": traj, "peers": peers}


# ------------------------------------------------------------------ #
# On-demand fetch — study ANY NSE name, not just the ingested universe #
# ------------------------------------------------------------------ #

def has_fundamentals(db: str, symbol: str, asof: str) -> bool:
    store = FVMStore(db)
    return bool(store.read_fundamental_asof(
        symbol.upper(), "annual", "consolidated", F.NET_PROFIT_A[1], asof)) or \
        bool(store.read_fundamental_asof(
            symbol.upper(), "annual", "standalone", F.NET_PROFIT_A[1], asof))


def has_prices(market_db: str, symbol: str, asof: str) -> bool:
    pd_ = fdata._load_prices(market_db, [symbol.upper()], asof, min_bars=60)
    return symbol.upper() in pd_


def ensure_stock_data(db: str, market_db: str, symbol: str, asof: str,
                      from_year: int = 2015) -> dict:
    """Fetch financials (Trendlyne fincsv) + shareholding (Screener) + prices (Kite) for a
    name that isn't cached yet, so any NSE stock becomes studyable. Each source is best-effort
    and independently guarded — returns a status dict the UI can surface. Re-running is cheap
    (already-present data is skipped). Needs a fresh TRENDLYNE_COOKIE + a valid Kite token."""
    symbol = symbol.upper()
    status = {"symbol": symbol, "fundamentals": "skipped", "shareholding": "skipped",
              "prices": "skipped", "errors": []}
    store = FVMStore(db)

    if not has_fundamentals(db, symbol, asof):
        try:
            from trader.fvm.data.trendlyne import TrendlyneClient, ingest_financials
            if not store.get_stock_hash(symbol):
                status["fundamentals"] = "not-in-master"
                status["errors"].append(f"{symbol} not in Trendlyne master list")
            else:
                ingest_financials(store, symbol, TrendlyneClient())
                status["fundamentals"] = "fetched"
        except Exception as e:  # cookie stale / quota / network
            status["fundamentals"] = "failed"
            status["errors"].append(f"financials: {type(e).__name__}: {e}")
        try:
            from trader.fvm.data.screener import ingest_shareholding
            ingest_shareholding(store, symbol)
            status["shareholding"] = "fetched"
        except Exception as e:
            status["shareholding"] = "failed"
            status["errors"].append(f"shareholding: {type(e).__name__}: {e}")
    else:
        status["fundamentals"] = "cached"

    if not has_prices(market_db, symbol, asof):
        try:
            from trader.auth.session import create_kite
            from trader.data.store import Store
            kite = create_kite()
            token_map = prices.resolve_tokens(kite, [symbol])
            prices.load_universe_prices(
                kite, Store(Path(market_db)), [symbol],
                datetime.datetime(from_year, 1, 1), datetime.datetime.fromisoformat(asof),
                token_map=token_map, min_bars=60)
            status["prices"] = "fetched" if has_prices(market_db, symbol, asof) else "short"
        except Exception as e:
            status["prices"] = "failed"
            status["errors"].append(f"prices: {type(e).__name__}: {e}")
    else:
        status["prices"] = "cached"

    return status
