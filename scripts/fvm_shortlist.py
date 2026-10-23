#!/usr/bin/env python
"""
FVM shortlist — rank the scored universe as of a date and show what FVM would act on.

Two views:
  1. FVM CANDIDATES — names that clear the full pipeline today (Gate A fundamentals + vetoes,
     Gate B weekly trend, daily timing trigger), ranked exactly as the strategy ranks them
     (within-pool fundamental percentile x technical score).
  2. FULL BOARD — every scored name by composite, with veto status + trend/timing, so you can
     see WHY a name did or didn't make the candidate cut.

Positional horizon: FVM is a multi-week-to-multi-month swing strategy — this is a swing/positional
shortlist, not an intraday one.

Reads cached data only (run scripts/fvm_ingest.py + scripts/fvm_prices.py first).

Usage:
    python scripts/fvm_shortlist.py [--asof YYYY-MM-DD] [--top 20] [--verbose]
"""

import argparse
import datetime
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trader.core.logger import get_logger
from trader.data.store import Store
from trader.fvm import handoff, scoring, technical, vetoes
from trader.fvm.data import prices
from trader.fvm.data.store import FVMStore

logger = get_logger(__name__)


def _scored_symbols(fvm_db):
    con = sqlite3.connect(fvm_db)
    try:
        return [r[0] for r in con.execute(
            "SELECT DISTINCT symbol FROM fundamentals ORDER BY symbol").fetchall()]
    finally:
        con.close()


def _decision(diag):
    """One-word reason a name is / isn't a candidate, from the handoff diagnostics."""
    if not diag.get("veto_passed", True):
        return "VETOED"
    if not diag.get("gate_a", False):
        return "WEAK_FUND"          # below composite pctile/floor
    if not diag.get("gate_b", False):
        return "NO_TREND"           # fundamentals OK but not a weekly uptrend
    if not diag.get("trigger", False):
        return "NO_TIMING"          # trend OK but no entry trigger today
    return "CANDIDATE"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", default=datetime.date.today().isoformat())
    ap.add_argument("--top", type=int, default=25, help="rows to show in the full board")
    ap.add_argument("--verbose", action="store_true", help="show per-pillar breakdown")
    ap.add_argument("--db", default="data/fvm.db")
    ap.add_argument("--market-db", default="data/market.db")
    args = ap.parse_args()

    asof = args.asof
    asof_ts = pd.to_datetime(asof)
    fvm = FVMStore(args.db)
    candle_store = Store(Path(args.market_db))
    symbols = _scored_symbols(args.db)

    price_data = prices.load_universe_prices(
        None, candle_store, symbols, datetime.datetime(2015, 1, 1),
        datetime.datetime.fromisoformat(asof), token_map={}, min_bars=60)
    print(f"FVM shortlist as of {asof} | {len(price_data)}/{len(symbols)} priced names\n")
    if not price_data:
        print("no priced names — run scripts/fvm_prices.py first")
        return

    universe = list(price_data)
    pp = prices.price_provider(price_data, asof)
    scores = scoring.compute_scores(fvm, universe, asof, price_provider=pp)
    vmap = {s: vetoes.check_vetoes(fvm, s, asof) for s in universe}
    tmap = {}
    for s in universe:
        d = price_data[s]
        d = d[pd.to_datetime(d["timestamp"]) <= asof_ts]
        tmap[s] = technical.evaluate(d)

    cands, diag = handoff.select_candidates(scores, vmap, tmap, regime_ok=True)

    # --- view 1: FVM candidates today ---
    print("=== FVM CANDIDATES (would act on today, best first) ===")
    if not cands:
        print("  none — no name clears fundamentals + trend + timing today.\n")
    else:
        print(f"  {'sym':<12}{'rank':>7}{'comp':>7}{'pool%':>7}{'trend':>7}{'timing':>7}")
        for c in cands:
            print(f"  {c['symbol']:<12}{c['final_rank']:>7.3f}{c['composite']:>7.1f}"
                  f"{100*c['pool_pctile']:>7.0f}{c['trend_score']:>7.2f}{c['timing_score']:>7.2f}")
        print()

    # --- view 2: full board by composite ---
    print(f"=== FULL BOARD (top {args.top} by composite) ===")
    ranked = sorted(universe, key=lambda s: -scores[s]["composite"])[:args.top]
    print(f"  {'sym':<12}{'comp':>6}{'trend':>7}{'timing':>7}  {'decision':<11}veto/notes")
    for s in ranked:
        comp = scores[s]["composite"]
        t = tmap[s]
        passed, reasons = vmap[s]
        dec = _decision(diag.get(s, {}))
        note = ""
        if not passed:
            note = ",".join(reasons)
        elif t["extension_vetoed"]:
            note = "parabolic_ext"
        print(f"  {s:<12}{comp:>6.1f}{t['trend_score']:>7.2f}{t['timing_score']:>7.2f}  "
              f"{dec:<11}{note}")
        if args.verbose:
            p = scores[s]["pillars"]
            print(f"    {'':12}earn {p['earnings']:.2f} val {p['valuation']:.2f} "
                  f"fwd {p['forward']:.2f} own {p['ownership']:.2f} bs {p['balance_sheet']:.2f}")

    print(f"\nlegend: CANDIDATE=acts today | NO_TIMING=trend ok, no trigger | "
          f"NO_TREND=fund ok, not an uptrend | WEAK_FUND=below fundamental cut | VETOED=red flag")


if __name__ == "__main__":
    main()
