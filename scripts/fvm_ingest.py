#!/usr/bin/env python
"""
FVM data ingestion — rate-budgeted, resumable.

One-shot (cheap, token-only): master list, current index membership, sector map.
Per-universe-stock (rate-limited): Trendlyne financials (2 calls/stock, 50/day budget) +
Screener shareholding (polite scrape).

Resumable: stocks that already have financials in the store are skipped, so re-running on
subsequent days fills the rest of the universe within the daily budget.

Usage:
    python scripts/fvm_ingest.py [--max-financials 40] [--index NIFTY500] [--db data/fvm.db]

Requires TRENDLYNE_TOKEN and a fresh TRENDLYNE_COOKIE in config/.env (financials are
cookie-gated; see docs/FVM_Design_Decisions.md §15c).
"""

import argparse
import datetime

from trader.core.logger import get_logger
from trader.fvm.data import nse, universe
from trader.fvm.data.screener import ingest_shareholding
from trader.fvm.data.store import FVMStore
from trader.fvm.data.trendlyne import (
    TrendlyneClient,
    TrendlyneError,
    ingest_financials,
    ingest_master,
)

logger = get_logger(__name__)


def _has_financials(store, sym, asof) -> bool:
    return bool(store.read_fundamental_asof(sym, "annual", "consolidated", "Net Profit Annual", asof))


def _ingest_symbols(store, tc, symbols, asof) -> None:
    """On-demand fetch for an explicit symbol list (used for watchlist names outside the
    Nifty500 universe, e.g. CUPID). Reuses the same financials + shareholding ingest as the
    universe loop, so the rows written are identical (same PIT knowledge_date, fields, tables).
    Already-present symbols are skipped (resumable). Counts against the Trendlyne daily budget."""
    done = skipped = sh_ok = errors = 0
    for sym in symbols:
        if not store.get_stock_hash(sym):
            print(f"  {sym}: not in fund_stocks master — cannot fetch via fincsv "
                  f"(use the Trendlyne browser fallback)")
            errors += 1
            continue
        if _has_financials(store, sym, asof):
            print(f"  {sym}: already present — skipped")
            skipped += 1
            continue
        try:
            ingest_financials(store, sym, tc)
            done += 1
            print(f"  {sym}: financials ✓")
        except TrendlyneError as e:
            errors += 1
            print(f"  financials {sym}: {e}")
            if any(t in str(e) for t in ("429", "quota", "rate-limit")):
                print("  -> daily Trendlyne quota reached; stopping.")
                break
            if "403" in str(e) or "cookie" in str(e).lower():
                print("  -> likely a stale TRENDLYNE_COOKIE; refresh it in config/.env and re-run")
                break
        try:
            ingest_shareholding(store, sym)
            sh_ok += 1
        except Exception as e:                       # screener is best-effort
            print(f"  shareholding {sym}: {type(e).__name__}: {e}")
    print(f"\non-demand done: {done} financials, {sh_ok} shareholding, "
          f"{skipped} already-present, {errors} errors")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-financials", type=int, default=40,
                    help="stop after N financials fetches (Trendlyne 50/day budget)")
    ap.add_argument("--index", default="NIFTY500")
    ap.add_argument("--db", default="data/fvm.db")
    ap.add_argument("--symbols", default=None,
                    help="comma-separated NSE codes (e.g. CUPID,RADICO or NSE:CUPID) to fetch "
                         "ON DEMAND, bypassing the universe ordering. Use for watchlist names "
                         "outside the Nifty500 universe. Still counts against the daily budget.")
    args = ap.parse_args()

    store = FVMStore(args.db)
    tc = TrendlyneClient()
    asof = datetime.date.today().isoformat()

    # --- one-shot scaffolding (idempotent; guarded so we don't re-pull needlessly) ---
    if store.count_stocks() == 0:
        ingest_master(store, tc)

    # --- on-demand mode: fetch exactly the named symbols, skip the universe loop ---
    if args.symbols:
        wanted = [s.strip().upper().replace("NSE:", "") for s in args.symbols.split(",") if s.strip()]
        _ingest_symbols(store, tc, wanted, asof)
        return

    nse_client = nse.NseClient()
    if not store.members_asof(args.index, asof):
        nse.ingest_current_membership(store, args.index, "2024-01-01", nse_client)
    if not store.sectors_map():
        universe.ingest_sectors(store, args.index, nse_client)
    # size-band memberships order the ingest mid-cap-first (one-shot; idempotent)
    if not store.members_asof("NIFTYMIDCAP150", asof):
        universe.ingest_size_memberships(store, client=nse_client)

    syms = universe.prioritized_universe(store, asof, args.index)
    n_mid = len(set(store.members_asof("NIFTYMIDCAP150", asof)) & set(syms))
    n_small = len(set(store.members_asof("NIFTYSMALLCAP250", asof)) & set(syms))
    print(f"universe: {len(syms)} eligible (non-financial) names "
          f"[ordered mid-cap-first: {n_mid} mid, {n_small} small, "
          f"{len(syms) - n_mid - n_small} large-remainder]")

    done = skipped = sh_ok = errors = 0
    for sym in syms:
        if _has_financials(store, sym, asof):
            skipped += 1
            continue
        if done >= args.max_financials:
            print(f"daily financials budget ({args.max_financials}) reached — "
                  f"re-run tomorrow to continue")
            break
        try:
            ingest_financials(store, sym, tc)
            done += 1
        except TrendlyneError as e:
            errors += 1
            msg = str(e)
            print(f"  financials {sym}: {msg}")
            if "429" in msg or "quota" in msg.lower() or "rate-limit" in msg.lower():
                print("  -> daily Trendlyne quota reached; stopping. Re-run after the daily reset.")
                break
            if "403" in msg or "cookie" in msg.lower():
                print("  -> likely a stale TRENDLYNE_COOKIE; refresh it in config/.env and re-run")
                break
        try:
            ingest_shareholding(store, sym)
            sh_ok += 1
        except Exception as e:                       # screener is best-effort
            print(f"  shareholding {sym}: {type(e).__name__}: {e}")

    print(f"\ndone: {done} financials, {sh_ok} shareholding, {skipped} already-present, "
          f"{errors} errors | total with financials now ~{skipped + done}/{len(syms)}")


if __name__ == "__main__":
    main()
