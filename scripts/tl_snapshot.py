#!/usr/bin/env python
"""
tl_snapshot.py — weekly Trendlyne Data-Downloader snapshot: ingest → screen → evolve.

Workflow (weekly):
  1. Download the "Data Downloader" xlsx from Trendlyne into data/
     (filename like Stocks-data-IND-3-Jul-2026.xlsx — the date is parsed from it).
  2. Run this script with no args. It:
       • ingests the newest not-yet-ingested export into fvm.db (tl_snapshot table),
       • runs the quality screen (funnel printed; survivors → data/screens/tl_screen_<asof>.csv,
         a ready feed for /discover / /qualify),
       • prints a watchlist red-flag panel,
       • if an older snapshot exists, shows week-over-week evolution: names that entered/
         left the screen and per-watchlist-name drift of the key fields.

Snapshots STACK — every weekly ingest becomes a new vintage, building our own history of
pledge / holdings-flow / DVM that Trendlyne's API never exposes retrospectively.

Usage:
    python scripts/tl_snapshot.py                    # auto-find newest xlsx in data/
    python scripts/tl_snapshot.py --file <path.xlsx>
    python scripts/tl_snapshot.py --screen-only      # no ingest, latest stored snapshot
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml

from trader.fvm.data import snapshot as snap
from trader.fvm.data.store import FVMStore

ROOT = Path(__file__).resolve().parents[1]

SCREEN_CSV_FIELDS = [
    "symbol", "name", "sector", "mcap_cr", "price", "durability", "valuation", "momentum",
    "dvm_class", "piotroski", "roe", "pe_ttm", "industry_pe", "np_yoy_qtr", "rev_yoy_qtr",
    "mf_chg_qoq", "fii_chg_qoq", "pct_days_below_pe",
]

WATCH_EVOLVE_FIELDS = ["durability", "valuation", "momentum", "piotroski", "pledge",
                       "promoter", "mf", "fii", "pe_ttm"]


def _watchlist(override: str | None) -> list[str]:
    if override:
        return [s.strip().upper().replace("NSE:", "") for s in override.split(",") if s.strip()]
    cfg = yaml.safe_load(open(ROOT / "config" / "config.yaml"))
    return [s.replace("NSE:", "") for s in (cfg.get("watchlist") or [])]


def _find_latest_xlsx() -> Path | None:
    files = [(snap.asof_from_filename(p), p)
             for p in (ROOT / "data").glob("Stocks-data-IND-*.xlsx")]
    files = [(d, p) for d, p in files if d]
    return max(files)[1] if files else None


def _fmt(v, nd=1):
    return "—" if v is None else f"{v:.{nd}f}"


def cmd_run(args) -> None:
    store = FVMStore(args.db)

    if not args.screen_only:
        path = Path(args.file) if args.file else _find_latest_xlsx()
        if path is None:
            sys.exit("No data/Stocks-data-IND-*.xlsx found — download the Data Downloader "
                     "export from Trendlyne first.")
        as_of = snap.asof_from_filename(path)
        already = as_of in snap.snapshot_dates(store)
        if already and not args.force:
            print(f"snapshot {as_of} already ingested ({path.name}) — skipping ingest "
                  f"(--force to re-ingest)")
        else:
            as_of, n = snap.ingest_snapshot(store, path)
            print(f"ingested {path.name}: {n} rows as vintage {as_of}")

    dates = snap.snapshot_dates(store)
    if not dates:
        sys.exit("No snapshots in the store.")
    latest = dates[-1]
    prev = dates[-2] if len(dates) > 1 else None
    rows = snap.read_universe(store, latest)

    # ---- quality screen ----
    survivors, funnel = snap.quality_screen(rows)
    print(f"\n=== Quality screen @ {latest}  ({len(rows)} names) ===")
    for desc, count in funnel:
        print(f"  {desc:55s} -> {count}")
    out_dir = ROOT / "data" / "screens"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / f"tl_screen_{latest}.csv"
    with open(out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=SCREEN_CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(survivors)
    print(f"\n{len(survivors)} survivors -> {out_csv.relative_to(ROOT)}")
    for r in survivors[:15]:
        print(f"  {r['symbol']:12s} D={_fmt(r['durability'], 0):>3} P={_fmt(r['piotroski'], 0)} "
              f"ROE={_fmt(r['roe'])}%  {r.get('dvm_class') or '—'}  [{r.get('sector') or '—'}]")
    if len(survivors) > 15:
        print(f"  … +{len(survivors) - 15} more in the CSV")

    # ---- watchlist panel ----
    wl = _watchlist(args.symbols)
    print(f"\n=== Watchlist read @ {latest} ===")
    if not wl:
        print("  (config watchlist is empty — pass --symbols NSE:X,NSE:Y for an ad-hoc panel)")
    for sym in wl:
        row = next((r for r in rows if r["symbol"] == sym), None)
        if row is None:
            print(f"  {sym:12s} — not in snapshot")
            continue
        flags = snap.watchlist_flags(row)
        dvm = (f"D={_fmt(row['durability'], 0):>3} V={_fmt(row['valuation'], 0):>3} "
               f"M={_fmt(row['momentum'], 0):>3} P={_fmt(row['piotroski'], 0)}")
        mark = "⚠️ " if flags else "   "
        print(f"  {mark}{sym:12s} {dvm}  {'; '.join(flags) if flags else 'clean'}")

    # ---- evolution vs previous snapshot ----
    if prev is None:
        print("\n(no earlier snapshot yet — evolution view starts next week)")
        return
    prev_rows = snap.read_universe(store, prev)
    prev_surv, _ = snap.quality_screen(prev_rows)
    cur_set = {r["symbol"] for r in survivors}
    prev_set = {r["symbol"] for r in prev_surv}
    print(f"\n=== Evolution {prev} -> {latest} ===")
    entered, left = sorted(cur_set - prev_set), sorted(prev_set - cur_set)
    print(f"  screen entries : {', '.join(entered) or '—'}")
    print(f"  screen exits   : {', '.join(left) or '—'}")

    prev_by = {r["symbol"]: r for r in prev_rows}
    print("\n  watchlist drift (Δ vs previous snapshot):")
    for sym in wl:
        cur = next((r for r in rows if r["symbol"] == sym), None)
        old = prev_by.get(sym)
        if cur is None or old is None:
            continue
        deltas = []
        for f in WATCH_EVOLVE_FIELDS:
            a, b = old.get(f), cur.get(f)
            if a is not None and b is not None and abs(b - a) >= 0.05:
                deltas.append(f"{f} {a:.1f}->{b:.1f}")
        print(f"    {sym:12s} {'; '.join(deltas) if deltas else 'no material change'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", help="explicit xlsx path (default: newest in data/)")
    ap.add_argument("--db", default="data/fvm.db")
    ap.add_argument("--force", action="store_true", help="re-ingest an existing vintage")
    ap.add_argument("--screen-only", action="store_true",
                    help="skip ingest; screen the latest stored snapshot")
    ap.add_argument("--symbols", help="comma-separated NSE:SYMBOLs for the watchlist panel "
                                      "(default: config watchlist)")
    cmd_run(ap.parse_args())


if __name__ == "__main__":
    main()
