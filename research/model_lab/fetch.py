"""Staged Kite fetcher + cache seeder for the Model Lab.

  .venv/bin/python -m research.model_lab.fetch <seed|market|daily|intraday|qa> [opts]

Resumable through the per-interval manifest (widest requested range per symbol).
"""
import argparse
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from research.model_lab import paths, qa, store, universe
from research.model_lab.paths import REPO_ROOT

# Same limits as trader.data.historical (_INTRADAY_MAX_DAYS / _DAY_MAX_DAYS)
CHUNK_DAYS = {"15minute": 60, "day": 2000}
MARKET_SYMBOLS = ("NSE:NIFTY 50", "NSE:INDIA VIX")


def gap_ranges(entry, req_from: datetime, req_to: datetime) -> list[tuple[datetime, datetime]]:
    """Ranges still to request given a manifest entry (or None)."""
    if not entry:
        return [(req_from, req_to)]
    m_from, m_to = datetime.fromisoformat(entry["from"]), datetime.fromisoformat(entry["to"])
    out = []
    if req_from < m_from and (m_from - req_from) >= timedelta(days=1):
        out.append((req_from, m_from - timedelta(seconds=1)))
    if req_to > m_to and (req_to - m_to) >= timedelta(days=1):
        out.append((m_to + timedelta(seconds=1), req_to))
    return out


def seed(db_path: Path | None = None) -> dict[str, int]:
    """Copy native-interval candles from the main cache (read-only) into the store."""
    db_path = Path(db_path) if db_path else REPO_ROOT / "data" / "market.db"
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    totals: dict[str, int] = {}
    try:
        for interval in (iv for iv in store.NATIVE if iv != "day_nse"):   # day_nse is built by nse_bhav, not Kite-cached
            syms = [r[0] for r in conn.execute(
                "SELECT DISTINCT instrument FROM candles WHERE timeframe=?", (interval,))]
            n = 0
            for sym in sorted(syms):
                rows = conn.execute(
                    "SELECT timestamp, open, high, low, close, volume FROM candles "
                    "WHERE instrument=? AND timeframe=? ORDER BY timestamp", (sym, interval)).fetchall()
                df = store.clean_bars(pd.DataFrame(rows, columns=store.COLS), interval)
                if df.empty:
                    continue
                store.write_bars(sym, interval, df)
                store.update_manifest(interval, sym, df["timestamp"].min().to_pydatetime(),
                                      df["timestamp"].max().to_pydatetime())
                n += len(df)
            totals[interval] = n
            print(f"seed {interval}: {len(syms)} symbols, {n} rows")
    finally:
        conn.close()
    return totals


class _Log:
    def __init__(self, stage: str):
        paths.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        self.f = open(paths.LOGS_DIR / f"fetch_{stage}_{datetime.now():%Y%m%d_%H%M%S}.log", "a")

    def __call__(self, msg: str):
        print(msg)
        self.f.write(msg + "\n")
        self.f.flush()


def _get_kite():
    from trader.auth.session import create_kite
    try:
        return create_kite()
    except Exception as e:
        print(f"Kite auth failed ({e}). Run: .venv/bin/python scripts/kite_totp_refresh.py --no-restart")
        sys.exit(2)


def _plan(interval, symbols, req_from, req_to):
    """[(symbol, [ranges])] for symbols with something left to request."""
    man = store.load_manifest(interval)
    plan = []
    for s in symbols:
        r = gap_ranges(man.get(s), req_from, req_to)
        if r:
            plan.append((s, r))
    return plan


def _n_chunks(interval, ranges) -> int:
    from trader.data.historical import _date_chunks
    return sum(len(_date_chunks(a, b, CHUNK_DAYS[interval])) for a, b in ranges)


def run_fetch(kite, stage, interval, symbols, req_from, req_to, args, tokens) -> None:
    from trader.data.historical import _date_chunks, _fetch_with_retry
    log = _Log(stage)
    plan = _plan(interval, symbols, req_from, req_to)
    if args.max_symbols:
        plan = plan[: args.max_symbols]
    est = sum(_n_chunks(interval, r) for _, r in plan)
    log(f"{stage}/{interval}: {len(plan)} symbols to fetch ({len(symbols) - len(plan)} up to date), ~{est} requests")
    if args.dry_run:
        return
    t0, done, failed, reqs = time.time(), 0, 0, 0
    for sym, ranges in plan:
        try:
            paths.check_disk()
        except RuntimeError as e:
            log(f"STOP disk: {e}")
            break
        tok = tokens.get(sym)
        if tok is None:
            log(f"{sym}: no_token")
            continue
        ts = time.time()
        try:
            frames = []
            for a, b in ranges:
                for cs, ce in _date_chunks(a, b, CHUNK_DAYS[interval]):
                    recs = _fetch_with_retry(kite, int(tok), sym, interval, cs, ce)
                    reqs += 1
                    time.sleep(args.sleep)
                    if recs:
                        frames.append(pd.DataFrame(recs).rename(columns={"date": "timestamp"}))
            added = 0
            if frames:
                raw = pd.concat(frames, ignore_index=True)
                added = len(store.clean_bars(raw, interval))
                store.write_bars(sym, interval, raw)
            for a, b in ranges:
                store.update_manifest(interval, sym, a, b)
            cov = store.coverage(sym, interval)
            log(f"{sym}: +{added} rows, file {cov[0] if cov else None}..{cov[1] if cov else None}, "
                f"{time.time() - ts:.1f}s")
            done += 1
        except Exception as e:
            failed += 1
            log(f"{sym}: FAILED {type(e).__name__}: {e}")
            if args.fail_fast:
                raise
    log(f"summary: done={done} failed={failed} requests={reqs} elapsed={time.time() - t0:.0f}s")


def _tokens(kite) -> dict[str, int]:
    return {"NSE:" + r["tradingsymbol"]: r["instrument_token"]
            for r in kite.instruments("NSE") if r.get("segment") in ("NSE", "INDICES")}


def _d(s: str) -> datetime:
    return datetime.fromisoformat(s)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="research.model_lab.fetch")
    ap.add_argument("stage", choices=["seed", "market", "daily", "intraday", "qa"])
    ap.add_argument("--from", dest="from_", default="2015-01-01")
    ap.add_argument("--day-from", default="2008-01-01")
    ap.add_argument("--to", default=None)
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--years", nargs="*", type=int, default=None)
    ap.add_argument("--top", type=int, default=100)
    ap.add_argument("--snapshot", action="store_true")
    ap.add_argument("--sleep", type=float, default=0.34)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-symbols", type=int, default=None)
    ap.add_argument("--fail-fast", action="store_true")
    ap.add_argument("--interval", default="day", help="qa stage interval")
    args = ap.parse_args(argv)

    if args.stage == "seed":
        seed()
        return 0
    if args.stage == "qa":
        for iv in (store.NATIVE if args.interval == "all" else (args.interval,)):
            df = qa.qa_report(iv)
            paths.LAB_ROOT.mkdir(parents=True, exist_ok=True)
            df.to_csv(paths.LAB_ROOT / f"qa_{iv}.csv", index=False)
            flagged = df[(df["n_jumps_30"] > 0) | (df["dup_ts"] > 0)]
            print(f"qa {iv}: {len(df)} symbols, {len(flagged)} flagged")
            if len(flagged):
                print(flagged.to_string(index=False))
        return 0

    # Default: end of yesterday — never store today's still-forming bars (the manifest would
    # mark them requested and they would never be refreshed).
    to = _d(args.to) if args.to else datetime.combine(date.today(), datetime.min.time()) - timedelta(minutes=1)
    kite = _get_kite()
    tokens = _tokens(kite)

    if args.stage == "market":
        syms = list(MARKET_SYMBOLS)
        run_fetch(kite, "market", "15minute", syms, _d(args.from_), to, args, tokens)
        run_fetch(kite, "market", "day", syms, _d(args.day_from), to, args, tokens)
    elif args.stage == "daily":
        if args.symbols:
            syms = args.symbols
        else:
            try:
                snap = None if args.snapshot else universe.latest_snapshot()
            except FileNotFoundError:
                snap = None
            if snap is None:
                snap = universe.snapshot_instruments(kite)
            syms = snap["symbol"].tolist()
        run_fetch(kite, "daily", "day", syms, _d(args.day_from), to, args, tokens)
    elif args.stage == "intraday":
        if args.symbols:
            syms = list(args.symbols)
        else:
            years = args.years or list(range(2016, date.today().year + 1))
            if not (paths.UNIVERSE_DIR / "liquidity_daily.parquet").exists():
                universe.build_liquidity_panel()
            syms = universe.intraday_fetch_list(years, args.top)
        syms = sorted(set(syms) | set(store.list_symbols("15minute")))
        run_fetch(kite, "intraday", "15minute", syms, _d(args.from_), to, args, tokens)
    return 0


if __name__ == "__main__":
    sys.exit(main())
