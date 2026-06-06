"""
Per-stock calibration — grid search over threshold × forward_label for a single symbol.

Usage:
    python scripts/calibrate_stock.py NSE:RVNL [--from 2023-01-01]

Prints JSON to stdout with ranked results + current override info.
Runs in cache-only mode (assumes candles already fetched).
"""

import argparse
import datetime
import itertools
import json
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol", help="e.g. NSE:RVNL")
    parser.add_argument("--from", dest="from_date", default="2023-01-01")
    args = parser.parse_args()

    symbol = args.symbol if args.symbol.startswith("NSE:") else f"NSE:{args.symbol}"

    store   = Store(config.db_path)
    base    = config.strategy_config("lr_extrema")
    from_dt = datetime.datetime.strptime(args.from_date, "%Y-%m-%d")
    to_dt   = datetime.datetime.now()

    # Check candle availability
    with store._conn() as conn:
        cnt = conn.execute(
            "SELECT COUNT(*) FROM candles WHERE instrument=? AND timeframe=?",
            (symbol, config.candle_timeframe),
        ).fetchone()[0]
    if cnt == 0:
        print(json.dumps({"error": f"No cached candles for {symbol}. Run a live fetch first."}))
        sys.exit(1)

    # Grid
    thresholds  = [0.88, 0.90, 0.92, 0.95]
    min_returns = [1.0, 1.5, 2.0, 2.5, 3.0]
    combos = (
        [(False, None, th) for th in thresholds] +
        [(True, mr, th) for mr, th in itertools.product(min_returns, thresholds)]
    )

    print(f"Running {len(combos)} combinations for {symbol}...", file=sys.stderr)

    # Baseline (global params, no override)
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

    # Current override (if any)
    current_override = (
        (config._data.get("per_stock_params") or {})
        .get(symbol, {})
        .get("lr_extrema", {})
    )

    output = {
        "symbol":           symbol,
        "from_date":        args.from_date,
        "baseline":         baseline,
        "current_override": current_override,
        "results":          results[:10],  # top 10
        "best":             results[0],
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
