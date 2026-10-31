#!/usr/bin/env python
"""
Milestone A — the FVM validation gate (design §12c).

Runs the rules-only FVM backtest against the naive-momentum benchmark over rolling
walk-forward folds on the scored universe (names with both fundamentals in fvm.db and
cached daily prices in market.db). Reports per-fold returns, the edge over the benchmark,
and the gate verdict: beat the benchmark AND be profitable in the majority of folds.

This is a HONEST gate — with a thin universe (few names) the result is indicative, not
decisive. Re-run as fundamentals coverage grows toward the full ~399-name universe.

Usage:
    python scripts/fvm_milestone_a.py [--from 2018-01-01] [--to today]
        [--capital 500000] [--test-len-w 78] [--step-w 39] [--db data/fvm.db]
"""

import argparse
import datetime
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trader.core.logger import get_logger
from trader.data.store import Store
from trader.fvm import scoring, vetoes, walkforward
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_dt", default="2018-01-01")
    ap.add_argument("--to", dest="to_dt", default=datetime.date.today().isoformat())
    ap.add_argument("--capital", type=float, default=500_000.0, help="sleeve capital")
    ap.add_argument("--test-len-w", type=int, default=39, help="fold length in weeks (~9m)")
    ap.add_argument("--step-w", type=int, default=13, help="fold stride in weeks (~3m)")
    ap.add_argument("--warmup-w", type=int, default=52)
    ap.add_argument("--min-scoreable", type=int, default=5,
                    help="min names that must pass vetoes before folds start (data-valid window)")
    ap.add_argument("--db", default="data/fvm.db")
    ap.add_argument("--market-db", default="data/market.db")
    args = ap.parse_args()

    from_dt = datetime.datetime.fromisoformat(args.from_dt)
    to_dt = datetime.datetime.fromisoformat(args.to_dt)

    fvm = FVMStore(args.db)
    candle_store = Store(Path(args.market_db))
    symbols = _scored_symbols(args.db)
    print(f"scored universe: {len(symbols)} names | {args.from_dt} -> {args.to_dt}")

    # cache-only load (run scripts/fvm_prices.py first to populate the candle cache)
    price_data = prices.load_universe_prices(None, candle_store, symbols, from_dt, to_dt,
                                             token_map={}, min_bars=60)
    print(f"price coverage: {len(price_data)}/{len(symbols)} names with >=60 bars")
    if len(price_data) < 2:
        print("not enough priced names — run scripts/fvm_prices.py first")
        return

    sectors = {s: fvm.get_sector(s) or "Unknown" for s in price_data}

    weeks = walkforward.all_weeks(price_data)

    # auto-start folds at the first data-scoreable week — pre-2023 quarterly fundamentals
    # don't exist (Trendlyne depth ~3y), so earlier folds are vacuous `insufficient_data`
    # and would make the gate an artifact of data depth, not strategy behaviour.
    veto_fn = vetoes.check_vetoes
    start_idx = walkforward.first_scoreable_week(
        fvm, weeks, list(price_data), veto_fn, min_names=args.min_scoreable)
    if start_idx is None:
        print(f"no week has >= {args.min_scoreable} scoreable names — fundamentals too sparse")
        return
    print(f"data-valid window starts {weeks[start_idx].date()} "
          f"(first week with >= {args.min_scoreable} scoreable names)")

    folds = walkforward.make_folds(weeks, test_len_w=args.test_len_w,
                                   step_w=args.step_w, warmup_w=args.warmup_w,
                                   start_idx=start_idx)
    print(f"weekly grid: {len(weeks)} weeks -> {len(folds)} folds "
          f"({args.test_len_w}w each, step {args.step_w}w)\n")
    if not folds:
        print("no folds — widen the date range or reduce --test-len-w")
        return

    # valuation factors need price (PEG/PE); pass a price provider as-of each rebalance.
    def score_fn(store, universe, asof):
        return scoring.compute_scores(store, universe, asof,
                                      price_provider=prices.price_provider(price_data, asof))

    res = walkforward.run_walk_forward(fvm, price_data, sectors, args.capital, folds,
                                       score_fn=score_fn)

    hdr = f"{'fold':<26}{'FVM%':>8}{'bench%':>9}{'edge%':>8}{'trades':>8}{'maxDD%':>8}"
    print(hdr)
    print("-" * len(hdr))
    for r in res["folds"]:
        mark = "+" if r["fvm_beats_bench"] else " "
        print(f"{r['fold']:<26}{r['fvm_return_pct']:>8.1f}{r['bench_return_pct']:>9.1f}"
              f"{r['edge_pct']:>7.1f}{mark}{r['fvm_trades']:>8}{r['fvm_maxdd_pct']:>8.1f}")

    s = res["summary"]
    print("\n--- summary ---")
    print(f"folds:                 {s['folds']}")
    print(f"FVM beats benchmark:   {s['fvm_beats_bench']}/{s['folds']} "
          f"({s['fvm_beats_bench_pct']:.0f}%)")
    print(f"FVM profitable:        {s['fvm_profitable']}/{s['folds']} "
          f"({s['fvm_profitable_pct']:.0f}%)")
    print(f"mean edge:             {s['mean_edge_pct']:+.1f}%  "
          f"(FVM {s['mean_fvm_return_pct']:+.1f}% vs bench {s['mean_bench_return_pct']:+.1f}%)")
    print(f"worst FVM fold maxDD:  {s['worst_fvm_maxdd_pct']:.1f}%")
    print(f"\nGATE (§12c): {'PASS' if s['gate_pass'] else 'FAIL'} "
          f"— beat benchmark + profitable in the majority of folds")
    if len(price_data) < 30:
        print("  (caveat: thin universe — indicative only; re-run as coverage grows)")


if __name__ == "__main__":
    main()
