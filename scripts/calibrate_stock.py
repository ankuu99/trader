"""
Per-stock calibration — two-stage, TF-aware, for one or more symbols.

Default flow (per symbol):
  Stage 1 — REGIME: backtest the stock under all three regimes —
            15minute (global config), 4hour and day (standard template blocks,
            threshold swept) — and pick the winner by P&L.
  Stage 2 — PARAMS: calibrate within the winning regime.
            15minute → legacy threshold × forward_label grid.
            4hour/day → the threshold sweep from stage 1 (already done);
            output the full standard override block with the best threshold,
            ready to paste into per_stock_params.

`--no-compare` skips stage 1 and sweeps threshold inside the stock's CURRENT
merged config (global + per_stock_params, including `timeframe`) — the cheap
re-calibration path for stocks whose regime is already settled.

Missing 15m history is fetched from Kite automatically (deep enough to cover
the day-template warm-up before --from), refreshing the token via
kite_totp_refresh.py if it has expired; pass --cache-only to skip fetching.

Usage:
    python scripts/calibrate_stock.py NSE:RVNL [--from 2023-01-01]
    python scripts/calibrate_stock.py NSE:IPCALAB NSE:CUPID NSE:INDHOTEL
    python scripts/calibrate_stock.py NSE:CUPID --no-compare --thresholds 0.80 0.85

Prints JSON to stdout. Single symbol → flat object; multiple symbols →
{"stocks": {sym: {...}}}.
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
from trader.core.config import config, flatten_strategy_params
from trader.data.store import Store
from trader.notifications import telegram
telegram.disable()

THRESHOLDS_15M = [0.88, 0.90, 0.92, 0.95]
THRESHOLDS_AGG = [0.80, 0.82, 0.85, 0.88, 0.90, 0.92]
MIN_RETURNS    = [1.0, 1.5, 2.0, 2.5, 3.0]

# Standard per-stock override blocks for aggregated TFs (config-shaped, nested).
# These mirror the hand-rolled blocks already in config.yaml (ACMESOLAR = 4hour,
# SCHAEFFLER = day); `threshold` is the one knob left to calibration.
_AGG_TEMPLATE_COMMON = {
    "warmup_bars": 100,
    "lookback_bars": 400,
    "extrema_order": 5,
    "exits": {
        "hold_bars": 40,
        "sell_min_pct": 7.0,
        "hard_stop": {"stop_pct": 20},
        "trailing": {"profit_pct": 10, "trail_pct": 4, "force_close_time": None},
        "pattern_top": {"sell_threshold": 0.85, "min_hold_before_exit": 2},
        "stale": {"check_bars": 5, "min_gain_pct": 0.5},
        "stale_2": {"check_bars": 15, "min_gain_pct": -2.0},
    },
}
TF_TEMPLATES = {
    "4hour": {**_AGG_TEMPLATE_COMMON, "timeframe": "4hour", "retrain_every": 2},
    "day":   {**_AGG_TEMPLATE_COMMON, "timeframe": "day",   "retrain_every": 1},
}
# Warm-up depth of the deepest template leg (day: 500 bars ≈ 725 calendar days)
_COMPARE_WARMUP_DAYS = 725


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


def _fetch_missing(store, symbols, from_dt, to_dt, min_warmup_days: int = 0):
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
        warmup_days = max(config.warmup_days_for(sym), min_warmup_days)
        needed_from = from_dt - datetime.timedelta(days=warmup_days)
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


def _cache_bounds(store, symbol):
    with store._conn() as conn:
        return conn.execute(
            "SELECT MIN(timestamp), MAX(timestamp) FROM candles "
            "WHERE instrument=? AND timeframe=?",
            (symbol, config.candle_timeframe),
        ).fetchone()


def _coverage_warning(store, symbol, from_dt, min_warmup_days: int = 0) -> str | None:
    """Aggregated TFs need (warmup+lookback) bars of 15m history BEFORE --from.
    Cache-only mode can't backfill, so warn when warm-up will eat the window."""
    oldest, _ = _cache_bounds(store, symbol)
    if oldest is None:
        return f"No cached candles for {symbol}. Run a live fetch first."
    warmup_days = max(config.warmup_days_for(symbol), min_warmup_days)
    needed_from = from_dt - datetime.timedelta(days=warmup_days)
    oldest_dt = datetime.datetime.fromisoformat(oldest)
    if oldest_dt > needed_from + datetime.timedelta(days=7):
        return (
            f"cache starts {oldest_dt.date()} but warm-up needs ~{needed_from.date()}; "
            f"warm-up will consume the start of the backtest window "
            f"(fewer trades, results skewed). Fetch older 15m history to fix."
        )
    return None


def _current_override(symbol):
    return (
        (config._data.get("per_stock_params") or {})
        .get(symbol, {})
        .get("lr_extrema", {})
    )


def _sweep_15m(store, symbol, base, from_dt, to_dt, thresholds):
    """Legacy 15m param grid: threshold × forward_label."""
    combos = (
        [(False, None, th) for th in thresholds] +
        [(True, mr, th) for mr, th in itertools.product(MIN_RETURNS, thresholds)]
    )
    baseline = _run(store, symbol, base, from_dt, to_dt)
    results = []
    for fl, mr, th in combos:
        override = {"threshold": th}
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
    return baseline, results


def _calibrate_current_regime(store, symbol, from_dt, to_dt, thresholds_arg):
    """--no-compare path: sweep threshold inside the stock's CURRENT merged
    config (its settled regime), 15m stocks get the legacy fl grid."""
    base = config.get_strategy_params(symbol, "lr_extrema")
    tf   = base.get("timeframe", config.candle_timeframe)
    aggregated = tf != config.candle_timeframe

    warning = _coverage_warning(store, symbol, from_dt)
    if warning and warning.startswith("No cached candles"):
        return {"symbol": symbol, "error": warning}

    if aggregated:
        thresholds = thresholds_arg or THRESHOLDS_AGG
        print(f"{symbol} [{tf}]: {len(thresholds)} thresholds...", file=sys.stderr)
        baseline = _run(store, symbol, base, from_dt, to_dt)
        results = []
        for th in thresholds:
            m = _run(store, symbol, _deep_merge(base, {"threshold": th}), from_dt, to_dt)
            results.append({
                "threshold": th, "pnl": m["pnl"], "trades": m["trades"],
                "win_rate": m["win_rate"],
                "delta": round(m["pnl"] - baseline["pnl"], 2),
            })
            print(".", file=sys.stderr, end="", flush=True)
        print(file=sys.stderr)
        results.sort(key=lambda x: x["pnl"], reverse=True)
    else:
        thresholds = thresholds_arg or THRESHOLDS_15M
        print(f"{symbol} [{tf}]: {len(thresholds)} thresholds × fl grid...", file=sys.stderr)
        baseline, results = _sweep_15m(store, symbol, base, from_dt, to_dt, thresholds)

    out = {
        "symbol":            symbol,
        "mode":              "current_regime",
        "timeframe":         tf,
        "current_threshold": base.get("threshold"),
        "baseline":          baseline,   # current merged config, as the stock runs today
        "current_override":  _current_override(symbol),
        "results":           results[:10],
        "best":              results[0],
    }
    if warning:
        out["coverage_warning"] = warning
    return out


def _calibrate_full(store, symbol, from_dt, to_dt, thresholds_arg):
    """Default two-stage flow: pick the regime (15m global vs 4hour/day standard
    templates), then calibrate params within the winner."""
    oldest, _ = _cache_bounds(store, symbol)
    if oldest is None:
        return {"symbol": symbol,
                "error": f"No cached candles for {symbol}. Run a live fetch first."}

    base_raw = config._data["strategies"].get("lr_extrema", {})
    legs = {}

    # ---- Stage 1: regime ----
    base15 = config.strategy_config("lr_extrema")
    print(f"{symbol} [regime] 15minute (global config)...", file=sys.stderr)
    legs["15minute"] = {
        "threshold": base15.get("threshold"),
        **_run(store, symbol, base15, from_dt, to_dt),
    }

    agg_thresholds = thresholds_arg or THRESHOLDS_AGG
    for tf in ("4hour", "day"):
        print(f"{symbol} [regime] {tf}: {len(agg_thresholds)} thresholds...", file=sys.stderr)
        results = []
        for th in agg_thresholds:
            override = _deep_merge(TF_TEMPLATES[tf], {"threshold": th})
            params = flatten_strategy_params(_deep_merge(base_raw, override))
            m = _run(store, symbol, params, from_dt, to_dt)
            results.append({"threshold": th, **m})
            print(".", file=sys.stderr, end="", flush=True)
        print(file=sys.stderr)
        results.sort(key=lambda x: x["pnl"], reverse=True)
        legs[tf] = {"results": results, "best": results[0]}

    # If the stock already runs a hand-tuned override, race it too — a customised
    # block can beat the standard template (e.g. different extrema/stale values),
    # and without this leg the compare would wrongly recommend a regime flip.
    override = _current_override(symbol)
    if override:
        cur = config.get_strategy_params(symbol, "lr_extrema")
        print(f"{symbol} [regime] current override "
              f"({cur.get('timeframe', config.candle_timeframe)})...", file=sys.stderr)
        legs["current"] = {
            "timeframe": cur.get("timeframe", config.candle_timeframe),
            "threshold": cur.get("threshold"),
            **_run(store, symbol, cur, from_dt, to_dt),
        }

    scores = {
        "15minute": legs["15minute"]["pnl"],
        "4hour":    legs["4hour"]["best"]["pnl"],
        "day":      legs["day"]["best"]["pnl"],
    }
    if "current" in legs:
        scores["current"] = legs["current"]["pnl"]
    winner = max(scores, key=scores.get)

    out = {
        "symbol":           symbol,
        "mode":             "full",
        "regime":           winner,
        "legs":             legs,
        "current_override": override,
    }

    # ---- Stage 2: params within the winner ----
    if winner == "current":
        # Existing hand-tuned block already wins — keep it. Threshold fine-tuning
        # within it is the --no-compare path.
        pass
    elif winner == "15minute":
        # Aggregated templates didn't beat the 15m run — calibrate the legacy grid.
        print(f"{symbol} [params] 15minute grid...", file=sys.stderr)
        baseline, results = _sweep_15m(
            store, symbol, base15, from_dt, to_dt, THRESHOLDS_15M)
        out["baseline"] = baseline
        out["results"] = results[:10]
        out["best"] = results[0]
    else:
        # Threshold sweep already ran in stage 1 — emit the paste-ready block.
        out["best"] = legs[winner]["best"]
        out["recommended_override"] = _deep_merge(
            TF_TEMPLATES[winner], {"threshold": legs[winner]["best"]["threshold"]}
        )

    warning = _coverage_warning(store, symbol, from_dt,
                                min_warmup_days=_COMPARE_WARMUP_DAYS)
    if warning:
        out["coverage_warning"] = warning
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("symbols", nargs="+", help="e.g. NSE:RVNL [NSE:CUPID ...]")
    parser.add_argument("--from", dest="from_date", default="2023-01-01")
    parser.add_argument("--thresholds", nargs="+", type=float, default=None,
                        help="Override the aggregated-TF threshold grid "
                             "(e.g. --thresholds 0.80 0.85 0.90)")
    parser.add_argument("--no-compare", action="store_true",
                        help="Skip regime selection — sweep threshold inside the "
                             "stock's current merged config")
    parser.add_argument("--cache-only", action="store_true",
                        help="Skip the Kite fetch — use only already-cached candles")
    args = parser.parse_args()

    symbols = [s if s.startswith("NSE:") else f"NSE:{s}" for s in args.symbols]

    store   = Store(config.db_path)
    from_dt = datetime.datetime.strptime(args.from_date, "%Y-%m-%d")
    to_dt   = datetime.datetime.now()

    if not args.cache_only:
        min_days = 0 if args.no_compare else _COMPARE_WARMUP_DAYS
        _fetch_missing(store, symbols, from_dt, to_dt, min_warmup_days=min_days)

    calibrate = _calibrate_current_regime if args.no_compare else _calibrate_full
    per_symbol = {
        sym: calibrate(store, sym, from_dt, to_dt, args.thresholds)
        for sym in symbols
    }

    if len(symbols) == 1:
        output = {"from_date": args.from_date, **per_symbol[symbols[0]]}
    else:
        output = {"from_date": args.from_date, "stocks": per_symbol}
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
