"""
Per-stock calibration — TF-aware grid search for one or more symbols.

Base params for each stock are its CURRENT merged config (global strategy block
deep-merged with per_stock_params, including `timeframe`) — so a 4hour/day stock
is calibrated in its own aggregated regime, with all its standard overrides
intact. Baseline = that current config as-is; each result's `delta` is the
improvement over what the stock runs today.

Grid by timeframe:
  - 15minute (base TF):   threshold × forward_label (legacy behaviour)
  - 4hour / day:          threshold-only sweep (forward_label is a 15m-era knob)

Usage:
    python scripts/calibrate_stock.py NSE:RVNL [--from 2023-01-01]
    python scripts/calibrate_stock.py NSE:IPCALAB NSE:CUPID NSE:INDHOTEL
    python scripts/calibrate_stock.py NSE:CUPID --thresholds 0.80 0.85 0.90

Prints JSON to stdout. Single symbol keeps the legacy shape; multiple symbols
are wrapped as {"stocks": {sym: {...}}}. By default it fetches any missing 15m
history from Kite first (deep enough to cover the aggregated-TF warm-up BEFORE
--from), refreshing the token via kite_totp_refresh.py if it has expired; pass
--cache-only to skip fetching. `coverage_warning` in the output flags a cache
that still doesn't reach the warm-up window.
"""

import argparse
import datetime
import itertools
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")

from trader.backtest.engine import compute_metrics, run_backtest
from trader.core.config import config
from trader.data.store import Store
from trader.notifications import telegram
telegram.disable()

THRESHOLDS_15M = [0.88, 0.90, 0.92, 0.95]
THRESHOLDS_AGG = [0.80, 0.82, 0.85, 0.88, 0.90, 0.92]
MIN_RETURNS    = [1.0, 1.5, 2.0, 2.5, 3.0]


def _refresh_token():
    print("Refreshing Kite token...", file=sys.stderr)
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent / "kite_totp_refresh.py")],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Token refresh failed:\n{result.stderr}")
    print("Token refreshed.", file=sys.stderr)


def _create_kite():
    """Kite session with existing token; on auth failure, TOTP-refresh and retry."""
    from trader.auth.session import create_kite
    try:
        return create_kite()
    except Exception as e:
        print(f"Kite auth failed ({e}) — refreshing token...", file=sys.stderr)
        _refresh_token()
        load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env", override=True)
        return create_kite()


def _fetch_missing(store, symbols, from_dt, to_dt):
    """Ensure the 15m cache covers each symbol's warm-up window before --from.
    Full fetch when the cache doesn't reach far enough back (get_candles only
    extends tails, never backfills), tail fetch otherwise."""
    from trader.data.historical import _fetch_and_cache
    kite = _create_kite()
    instruments = kite.instruments("NSE")
    sym_to_tok = {f"NSE:{i['tradingsymbol']}": i["instrument_token"] for i in instruments}
    for sym in symbols:
        token = sym_to_tok.get(sym)
        if token is None:
            print(f"  WARNING: {sym} not in NSE instruments — skipping fetch", file=sys.stderr)
            continue
        needed_from = from_dt - datetime.timedelta(days=config.warmup_days_for(sym))
        with store._conn() as conn:
            oldest, latest = conn.execute(
                "SELECT MIN(timestamp), MAX(timestamp) FROM candles "
                "WHERE instrument=? AND timeframe=?",
                (sym, config.candle_timeframe),
            ).fetchone()
        if oldest is None or datetime.datetime.fromisoformat(oldest) > \
                needed_from + datetime.timedelta(days=7):
            fetch_from = needed_from
        elif latest:
            fetch_from = datetime.datetime.fromisoformat(latest) + datetime.timedelta(minutes=1)
        else:
            fetch_from = needed_from
        if fetch_from >= to_dt:
            continue
        print(f"  Fetching {sym} 15m from {fetch_from.date()}...", file=sys.stderr)
        try:
            _fetch_and_cache(kite, store, token, sym,
                             config.candle_timeframe, fetch_from, to_dt)
        except Exception as e:
            print(f"  WARNING: fetch failed for {sym}: {e}", file=sys.stderr)


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _run(store, symbol, params, from_dt, to_dt):
    trades = run_backtest(
        None, store, [symbol], {symbol: 0},
        params, from_dt, to_dt,
    )
    if not trades:
        return {"pnl": 0, "trades": 0, "win_rate": 0.0}
    wins = [t["pnl"] for t in trades if t["pnl"] > 0]
    return {
        "pnl":      round(sum(t["pnl"] for t in trades), 2),
        "trades":   len(trades),
        "win_rate": round(len(wins) / len(trades) * 100, 1),
    }


def _coverage_warning(store, symbol, from_dt) -> str | None:
    """Aggregated TFs need (warmup+lookback) bars of 15m history BEFORE --from.
    Cache-only mode can't backfill, so warn when warm-up will eat the window."""
    with store._conn() as conn:
        oldest, latest = conn.execute(
            "SELECT MIN(timestamp), MAX(timestamp) FROM candles "
            "WHERE instrument=? AND timeframe=?",
            (symbol, config.candle_timeframe),
        ).fetchone()
    if oldest is None:
        return f"No cached candles for {symbol}. Run a live fetch first."
    needed_from = from_dt - datetime.timedelta(days=config.warmup_days_for(symbol))
    oldest_dt = datetime.datetime.fromisoformat(oldest)
    if oldest_dt > needed_from + datetime.timedelta(days=7):
        return (
            f"cache starts {oldest_dt.date()} but warm-up needs ~{needed_from.date()}; "
            f"warm-up will consume the start of the backtest window "
            f"(fewer trades, results skewed). Fetch older 15m history to fix."
        )
    return None


def _calibrate_symbol(store, symbol, from_dt, to_dt, thresholds_arg):
    base = config.get_strategy_params(symbol, "lr_extrema")
    tf   = base.get("timeframe", config.candle_timeframe)
    aggregated = tf != config.candle_timeframe

    warning = _coverage_warning(store, symbol, from_dt)
    if warning and warning.startswith("No cached candles"):
        return {"symbol": symbol, "error": warning}

    if aggregated:
        thresholds = thresholds_arg or THRESHOLDS_AGG
        combos = [(False, None, th) for th in thresholds]
    else:
        thresholds = thresholds_arg or THRESHOLDS_15M
        combos = (
            [(False, None, th) for th in thresholds] +
            [(True, mr, th) for mr, th in itertools.product(MIN_RETURNS, thresholds)]
        )

    print(f"{symbol} [{tf}]: {len(combos)} combinations...", file=sys.stderr)

    # Baseline = the stock's current merged config, untouched
    baseline = _run(store, symbol, base, from_dt, to_dt)

    results = []
    for fl, mr, th in combos:
        override = {"threshold": th}
        if not aggregated:
            if fl:
                override["forward_label"] = {"enabled": True, "min_return_pct": mr}
            else:
                override["forward_label"] = {"enabled": False}
        params = _deep_merge(base, override)
        m = _run(store, symbol, params, from_dt, to_dt)
        results.append({
            "fl": fl, "min_return_pct": mr, "threshold": th,
            "pnl": m["pnl"], "trades": m["trades"], "win_rate": m["win_rate"],
            "delta": round(m["pnl"] - baseline["pnl"], 2),
        })
        print(".", file=sys.stderr, end="", flush=True)
    print(file=sys.stderr)

    results.sort(key=lambda x: x["pnl"], reverse=True)

    current_override = (
        (config._data.get("per_stock_params") or {})
        .get(symbol, {})
        .get("lr_extrema", {})
    )

    out = {
        "symbol":            symbol,
        "timeframe":         tf,
        "current_threshold": base.get("threshold"),
        "baseline":          baseline,   # current merged config, as the stock runs today
        "current_override":  current_override,
        "results":           results[:10],
        "best":              results[0],
    }
    if warning:
        out["coverage_warning"] = warning
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("symbols", nargs="+", help="e.g. NSE:RVNL [NSE:CUPID ...]")
    parser.add_argument("--from", dest="from_date", default="2023-01-01")
    parser.add_argument("--thresholds", nargs="+", type=float, default=None,
                        help="Override the threshold grid (e.g. --thresholds 0.80 0.85 0.90)")
    parser.add_argument("--cache-only", action="store_true",
                        help="Skip the Kite fetch — use only already-cached candles")
    args = parser.parse_args()

    symbols = [s if s.startswith("NSE:") else f"NSE:{s}" for s in args.symbols]

    store   = Store(config.db_path)
    from_dt = datetime.datetime.strptime(args.from_date, "%Y-%m-%d")
    to_dt   = datetime.datetime.now()

    if not args.cache_only:
        _fetch_missing(store, symbols, from_dt, to_dt)

    per_symbol = {
        sym: _calibrate_symbol(store, sym, from_dt, to_dt, args.thresholds)
        for sym in symbols
    }

    if len(symbols) == 1:
        output = {"from_date": args.from_date, **per_symbol[symbols[0]]}
    else:
        output = {"from_date": args.from_date, "stocks": per_symbol}
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
