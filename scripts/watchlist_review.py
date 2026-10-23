"""
Watchlist review — quantitative analysis for /watchlist-review skill.

Outputs a JSON report with per-stock metrics for two periods:
  - full  : --from date to today
  - recent: last 6 months

Usage:
    python scripts/watchlist_review.py [--from 2023-01-01] [--skip-refresh]
    python scripts/watchlist_review.py --symbol NSE:MARICO [--from 2023-01-01]

Flags:
    --from       Full-period start date (default: 2023-01-01)
    --skip-refresh  Skip kite_totp_refresh (use existing token)
    --symbol     Single-stock detailed review mode — emits richer JSON for one
                 stock (yearly breakdown, exit-reason breakdown, full trade list)
                 instead of the watchlist-wide report. Symbol need not be in the
                 watchlist.

Prints JSON to stdout; also writes to reviews/quant_<timestamp>.json
(or reviews/stock_<SYMBOL>_<timestamp>.json in --symbol mode).
"""

import argparse
import datetime
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")

from trader.backtest.engine import compute_metrics, run_backtest
from trader.core.config import config
from trader.data.store import Store
from trader.notifications import telegram
telegram.disable()


def _refresh_token():
    print("Refreshing Kite token...", file=sys.stderr)
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "kite_totp_refresh.py")],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Token refresh failed:\n{result.stderr}")
    print("Token refreshed.", file=sys.stderr)


def _fetch_candles(kite, store, symbols, full_from_date: str):
    from trader.data.historical import _fetch_and_cache
    print(f"Fetching candles for {len(symbols)} symbols from {full_from_date}...", file=sys.stderr)
    instruments = kite.instruments("NSE")
    sym_to_tok = {f"NSE:{i['tradingsymbol']}": i["instrument_token"] for i in instruments}
    valid = [s for s in symbols if s in sym_to_tok]
    from_dt = datetime.datetime.strptime(full_from_date, "%Y-%m-%d")
    to_dt   = datetime.datetime.now()
    for i, sym in enumerate(valid, 1):
        print(f"  [{i}/{len(valid)}] {sym}   ", file=sys.stderr, end="\r")
        try:
            # Check oldest cached candle for this symbol
            with store._conn() as conn:
                oldest = conn.execute(
                    "SELECT MIN(timestamp) FROM candles WHERE instrument=? AND timeframe=?",
                    (sym, config.candle_timeframe),
                ).fetchone()[0]
            need_from = from_dt
            if oldest:
                oldest_dt = datetime.datetime.fromisoformat(oldest)
                if oldest_dt <= from_dt + datetime.timedelta(days=5):
                    # Cache covers the full period — only fetch the tail
                    with store._conn() as conn:
                        latest = conn.execute(
                            "SELECT MAX(timestamp) FROM candles WHERE instrument=? AND timeframe=?",
                            (sym, config.candle_timeframe),
                        ).fetchone()[0]
                    if latest:
                        need_from = datetime.datetime.fromisoformat(latest) + datetime.timedelta(minutes=1)
            if need_from <= to_dt:
                _fetch_and_cache(
                    kite, store, sym_to_tok[sym], sym,
                    config.candle_timeframe, need_from, to_dt,
                )
        except Exception as e:
            print(f"\n  Warning: could not fetch {sym}: {e}", file=sys.stderr)
    print(file=sys.stderr)
    return {s: 0 for s in valid}, valid


def _run_period(store, symbols, sym_to_tok, from_dt, to_dt, per_symbol_params):
    trades = run_backtest(
        None, store, symbols, sym_to_tok, config.strategy_config("lr_extrema"),
        from_dt, to_dt, per_symbol_params=per_symbol_params,
    )
    by_sym = defaultdict(list)
    for t in trades:
        by_sym[t["instrument"]].append(t)
    return by_sym


def _stock_metrics(trades: list) -> dict:
    if not trades:
        return {"pnl": 0, "trades": 0, "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0}
    wins   = [t["pnl"] for t in trades if t["pnl"] > 0]
    losses = [t["pnl"] for t in trades if t["pnl"] <= 0]
    return {
        "pnl":      round(sum(t["pnl"] for t in trades), 2),
        "trades":   len(trades),
        "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0.0,
        "avg_win":  round(sum(wins)   / len(wins),   2) if wins   else 0.0,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
    }


def _period_breakdown(trades: list, span: int) -> dict:
    """Group trades by the first `span` chars of exit_date (4 = year, 7 = month)."""
    buckets = defaultdict(list)
    for t in trades:
        key = str(t.get("exit_date") or "?")[:span]
        buckets[key].append(t)
    return {k: _stock_metrics(v) for k, v in sorted(buckets.items())}


def _reason_breakdown(trades: list) -> dict:
    """Group trades by exit reason — count + total/avg P&L per reason."""
    buckets = defaultdict(list)
    for t in trades:
        buckets[t.get("reason", "?")].append(t)
    out = {}
    for reason, ts in buckets.items():
        out[reason] = {
            "count": len(ts),
            "pnl":   round(sum(t["pnl"] for t in ts), 2),
            "avg":   round(sum(t["pnl"] for t in ts) / len(ts), 2),
        }
    # Sort by total P&L descending so the dominant exit path is first.
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["pnl"]))


def _trade_rows(trades: list) -> list:
    """Compact, chronological trade list for the report."""
    rows = []
    for t in sorted(trades, key=lambda x: str(x.get("entry_date") or "")):
        rows.append({
            "entry_date": str(t.get("entry_date") or "")[:10],
            "exit_date":  str(t.get("exit_date") or "")[:10],
            "entry":      round(t.get("entry", 0), 2),
            "exit":       round(t.get("exit", 0), 2),
            "qty":        t.get("qty", 0),
            "pnl":        round(t.get("pnl", 0), 2),
            "reason":     t.get("reason", "?"),
            "held_candles": t.get("held_candles", 0),
        })
    return rows


def _run_single_stock(store, sym_to_tok, symbol, full_from, recent_from, now, per_symbol_params):
    """Detailed single-stock review — richer breakdowns than the watchlist row."""
    full_trades   = _run_period(store, [symbol], sym_to_tok, full_from, now, per_symbol_params).get(symbol, [])
    recent_trades = _run_period(store, [symbol], sym_to_tok, recent_from, now, per_symbol_params).get(symbol, [])

    override = (config._data.get("per_stock_params") or {}).get(symbol, {}).get("lr_extrema")

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "symbol":       symbol,
        "full_from":    full_from.strftime("%Y-%m-%d"),
        "recent_from":  recent_from.strftime("%Y-%m-%d"),
        "in_watchlist": symbol in config.watchlist,
        "override":     override,
        "params_used":  config.get_strategy_params(symbol, "lr_extrema"),
        "full":         _stock_metrics(full_trades),
        "recent":       _stock_metrics(recent_trades),
        "yearly":       _period_breakdown(full_trades, 4),
        "monthly_recent": _period_breakdown(recent_trades, 7),
        "reasons":      _reason_breakdown(full_trades),
        "trades":       _trade_rows(full_trades),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="from_date", default="2023-01-01")
    parser.add_argument("--skip-refresh", action="store_true")
    parser.add_argument("--symbol", default=None,
                        help="Single-stock detailed review (e.g. NSE:MARICO)")
    args = parser.parse_args()

    if not args.skip_refresh:
        _refresh_token()

    from trader.auth.session import create_kite
    kite  = create_kite()
    store = Store(config.db_path)
    # Do NOT clear candles — warm_up upserts so existing history is preserved.
    # Only clear orders/trades/signals from any prior backtest run.
    with store._conn() as conn:
        conn.executescript("DELETE FROM orders; DELETE FROM trades; DELETE FROM signals;")

    single = args.symbol
    if single:
        single = single.upper()
        if not single.startswith("NSE:"):
            single = f"NSE:{single}"
        symbols = [single]
    else:
        symbols = list(config.watchlist)

    sym_to_tok, valid = _fetch_candles(kite, store, symbols, args.from_date)

    if single and single not in valid:
        print(json.dumps({"error": f"{single} not found on NSE or has no candles"}))
        sys.exit(1)

    # Build per_symbol_params
    _overrides = config._data.get("per_stock_params") or {}
    per_symbol_params = {
        sym: config.get_strategy_params(sym, "lr_extrema")
        for sym in valid if _overrides.get(sym, {}).get("lr_extrema")
    } or None

    now     = datetime.datetime.now()
    full_from  = datetime.datetime.strptime(args.from_date, "%Y-%m-%d")
    recent_from = now - datetime.timedelta(days=180)

    if single:
        print(f"Running detailed single-stock review for {single}...", file=sys.stderr)
        output = _run_single_stock(
            store, sym_to_tok, single, full_from, recent_from, now, per_symbol_params,
        )
        reviews_dir = Path(__file__).resolve().parents[1] / "reviews"
        reviews_dir.mkdir(exist_ok=True)
        ts = now.strftime("%Y%m%d_%H%M%S")
        safe_sym = single.replace("NSE:", "").replace(":", "_")
        out_path = reviews_dir / f"stock_{safe_sym}_{ts}.json"
        out_path.write_text(json.dumps(output, indent=2))
        print(f"Stock data saved: {out_path}", file=sys.stderr)
        print(json.dumps(output, indent=2))
        return

    print("Running full-period backtest...", file=sys.stderr)
    full_by_sym = _run_period(store, valid, sym_to_tok, full_from, now, per_symbol_params)

    print("Running recent 6-month backtest...", file=sys.stderr)
    recent_by_sym = _run_period(store, valid, sym_to_tok, recent_from, now, per_symbol_params)

    results = {}
    for sym in valid:
        full   = _stock_metrics(full_by_sym.get(sym, []))
        recent = _stock_metrics(recent_by_sym.get(sym, []))

        # Trend: is recent P&L proportionally better or worse than full-period average?
        full_monthly   = full["pnl"]   / max(1, (now - full_from).days / 30)
        recent_monthly = recent["pnl"] / 6
        if full_monthly == 0:
            trend = "flat"
        elif recent_monthly >= full_monthly * 1.1:
            trend = "improving"
        elif recent_monthly <= full_monthly * 0.5:
            trend = "declining"
        else:
            trend = "stable"

        results[sym] = {"full": full, "recent": recent, "trend": trend}

    # Portfolio totals
    all_full_trades = [t for trades in full_by_sym.values() for t in trades]
    portfolio = compute_metrics(all_full_trades, config.total_capital)

    output = {
        "generated_at": now.isoformat(timespec="seconds"),
        "full_from":    args.from_date,
        "recent_from":  recent_from.strftime("%Y-%m-%d"),
        "portfolio": {
            "total_pnl":  round(portfolio["total_pnl"], 2),
            "return_pct": round(portfolio["return_pct"], 2),
            "win_rate":   round(portfolio["win_rate"], 1),
            "total_trades": portfolio["total_trades"],
            "max_dd":     round(portfolio["max_drawdown"], 2),
            "sortino":    round(portfolio.get("sortino", 0), 3),
        },
        "stocks": results,
    }

    # Save to reviews/
    reviews_dir = Path(__file__).resolve().parents[1] / "reviews"
    reviews_dir.mkdir(exist_ok=True)
    ts = now.strftime("%Y%m%d_%H%M%S")
    out_path = reviews_dir / f"quant_{ts}.json"
    out_path.write_text(json.dumps(output, indent=2))
    print(f"Quant data saved: {out_path}", file=sys.stderr)

    # Print JSON to stdout for the skill to consume
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
