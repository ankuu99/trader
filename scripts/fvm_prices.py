#!/usr/bin/env python
"""
FVM price ingestion — fetch & cache daily candles for the FVM universe.

Daily OHLCV is the input the technical layer + backtest engine need (weekly is resampled
from daily in `technical.resample_weekly`). Candles are cached in the *generic* market DB
(`trader.data.store.Store`, default `data/market.db`) and reused via `historical.get_candles`
— prices are not FVM-specific, so we share the existing candle cache rather than fvm.db.

Resumable by construction: `get_candles` serves cached bars and fetches only the missing
tail, so re-running extends coverage cheaply.

Universe (default `--scope scored`): the stocks that actually have fundamentals in fvm.db —
i.e. the names we can score today. `--scope eligible` fetches the full non-financial
eligible universe (heavier; for the eventual full-universe backtest).

Usage:
    python scripts/fvm_prices.py [--from 2018-01-01] [--to today]
                                 [--scope scored|eligible] [--db data/fvm.db]
"""

import argparse
import datetime
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trader.auth.session import create_kite
from trader.core.logger import get_logger
from trader.data.store import Store
from trader.fvm.data import prices, universe
from trader.fvm.data.store import FVMStore

logger = get_logger(__name__)


def _scored_symbols(fvm_db: str) -> list[str]:
    """Distinct symbols that have any fundamentals rows (the scoreable set)."""
    con = sqlite3.connect(fvm_db)
    try:
        rows = con.execute("SELECT DISTINCT symbol FROM fundamentals ORDER BY symbol").fetchall()
    finally:
        con.close()
    return [r[0] for r in rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_dt", default="2018-01-01",
                    help="start date (ISO). Default 2018-01-01 — enough for 40w MA + walk-forward.")
    ap.add_argument("--to", dest="to_dt", default=datetime.date.today().isoformat(),
                    help="end date (ISO). Default today.")
    ap.add_argument("--scope", choices=["scored", "eligible"], default="scored",
                    help="'scored' = names with fundamentals (default); 'eligible' = full non-financial universe")
    ap.add_argument("--index", default="NIFTY500")
    ap.add_argument("--db", default="data/fvm.db", help="FVM store (for universe membership)")
    ap.add_argument("--market-db", default="data/market.db", help="candle cache DB")
    ap.add_argument("--min-bars", type=int, default=60)
    args = ap.parse_args()

    from_dt = datetime.datetime.fromisoformat(args.from_dt)
    to_dt = datetime.datetime.fromisoformat(args.to_dt)

    fvm = FVMStore(args.db)
    candle_store = Store(Path(args.market_db))
    asof = args.to_dt

    if args.scope == "scored":
        symbols = _scored_symbols(args.db)
    else:
        symbols = universe.eligible_universe(fvm, asof, args.index)

    print(f"scope={args.scope}: {len(symbols)} symbols | {args.from_dt} -> {args.to_dt}")
    if not symbols:
        print("no symbols — ingest fundamentals first (scripts/fvm_ingest.py)")
        return

    kite = create_kite()
    token_map = prices.resolve_tokens(kite, symbols)
    print(f"resolved {len(token_map)}/{len(symbols)} Kite tokens")

    price_data = prices.load_universe_prices(
        kite, candle_store, symbols, from_dt, to_dt,
        token_map=token_map, min_bars=args.min_bars,
    )

    covered = sorted(price_data)
    missing = sorted(set(s.upper() for s in symbols) - set(covered))
    bar_counts = {s: len(df) for s, df in price_data.items()}
    if bar_counts:
        lo = min(bar_counts.values())
        hi = max(bar_counts.values())
        print(f"\ncovered: {len(covered)}/{len(symbols)} symbols "
              f"(>= {args.min_bars} bars) | bars/symbol {lo}-{hi}")
    if missing:
        print(f"missing/short ({len(missing)}): {missing[:15]}"
              + (" ..." if len(missing) > 15 else ""))


if __name__ == "__main__":
    main()
