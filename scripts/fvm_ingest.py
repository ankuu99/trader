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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-financials", type=int, default=40,
                    help="stop after N financials fetches (Trendlyne 50/day budget)")
    ap.add_argument("--index", default="NIFTY500")
    ap.add_argument("--db", default="data/fvm.db")
    args = ap.parse_args()

    store = FVMStore(args.db)
    tc = TrendlyneClient()
    asof = datetime.date.today().isoformat()

    # --- one-shot scaffolding (idempotent; guarded so we don't re-pull needlessly) ---
    if store.count_stocks() == 0:
        ingest_master(store, tc)
    nse_client = nse.NseClient()
    if not store.members_asof(args.index, asof):
        nse.ingest_current_membership(store, args.index, "2024-01-01", nse_client)
    if not store.sectors_map():
        universe.ingest_sectors(store, args.index, nse_client)

    syms = universe.eligible_universe(store, asof, args.index)
    print(f"universe: {len(syms)} eligible (non-financial) names")

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
