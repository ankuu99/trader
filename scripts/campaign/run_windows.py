"""
Campaign window runner — the fixed Stage-B protocol of docs/01_Extrema_Model_Campaign.md.

Runs the portfolio backtest (cache-only, never wipes the candle cache) over the
campaign's fixed windows, optionally with a YAML overlay deep-merged onto
config/config.yaml, and writes one JSON of metrics per run.

    python scripts/campaign/run_windows.py --label baseline --out reviews/extrema_campaign/runs/baseline.json
    python scripts/campaign/run_windows.py --label exp01 --overlay config/experiments/exp01.yaml \
        --out reviews/extrema_campaign/runs/exp01.json --compare reviews/extrema_campaign/runs/baseline.json
    python scripts/campaign/run_windows.py --windows H1-25 H2-25 --workers 4 ...

Windows (fixed up front — do not edit without a DECISIONS row):
    H1-25 2025-01-01→2025-06-30 · H2-25 2025-07-01→2025-12-31 · H1-26 2026-01-01→2026-06-30 ·
    H2-26 2026-07-01→2026-10-16 · FULL 2025-01-01→2026-10-16 · HORIZON 2020-01-01→2026-10-16
Each window is an independent run starting from config capital.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

WINDOWS = {
    "H1-25": ("2025-01-01", "2025-06-30"),
    "H2-25": ("2025-07-01", "2025-12-31"),
    "H1-26": ("2026-01-01", "2026-06-30"),
    "H2-26": ("2026-07-01", "2026-10-16"),
    "FULL": ("2025-01-01", "2026-10-16"),
    "HORIZON": ("2020-01-01", "2026-10-16"),
}
HALF_YEARS = ["H1-25", "H2-25", "H1-26", "H2-26"]


def _apply_overlay(overlay_path: str | None) -> None:
    from trader.core.config import _deep_merge, config
    if not overlay_path:
        return
    import yaml
    with open(overlay_path) as f:
        overlay = yaml.safe_load(f) or {}
    config._data = _deep_merge(config._data, overlay)


def _run_window(name: str, overlay_path: str | None, symbols: list[str] | None) -> dict:
    import logging
    logging.disable(logging.CRITICAL)
    _apply_overlay(overlay_path)

    from trader.analytics import compute_utilisation
    from trader.backtest.engine import compute_metrics, run_backtest
    from trader.core.config import config
    from trader.data.store import Store

    f, t = WINDOWS[name]
    from_dt = datetime.strptime(f, "%Y-%m-%d")
    to_dt = datetime.strptime(t, "%Y-%m-%d").replace(hour=23, minute=59)
    watchlist = symbols or list(config.watchlist)
    params = config.strategy_config("lr_extrema")
    overrides = config._data.get("per_stock_params") or {}
    per_symbol = {s: config.get_strategy_params(s, "lr_extrema")
                  for s in watchlist if overrides.get(s, {}).get("lr_extrema")} or None

    t0 = time.perf_counter()
    trades = run_backtest(None, Store(config.db_path), watchlist, {s: 0 for s in watchlist},
                          params, from_dt, to_dt, per_symbol_params=per_symbol)
    elapsed = time.perf_counter() - t0
    m = compute_metrics(trades, config.total_capital)
    util = compute_utilisation(trades, config.total_capital, from_dt, to_dt)["overall"]
    by_inst: dict[str, float] = {}
    for tr in trades:
        by_inst[tr["instrument"]] = by_inst.get(tr["instrument"], 0.0) + tr["pnl"]
    return {
        "window": name, "from": f, "to": t, "elapsed_s": round(elapsed, 1),
        "trades": m["total_trades"], "pnl": round(m["total_pnl"], 2),
        "return_pct": round(m["return_pct"], 3),
        "max_dd_pct": round(m["max_drawdown_pct"], 3), "calmar": round(m["calmar_ratio"], 3),
        "sharpe_proxy": round(m["sharpe_proxy"], 3), "profit_factor": round(m["profit_factor"], 3),
        "util_pct": round(util.get("time_avg_util_pct", 0.0), 2),
        "exit_counts": dict(Counter(tr["reason"] for tr in trades)),
        "pnl_by_instrument": {k: round(v, 2) for k, v in sorted(by_inst.items())},
    }


def _fmt(r: dict, base: dict | None) -> str:
    s = (f"{r['window']:<8} ₹{r['pnl'] / 1e3:8.1f}k  DD {r['max_dd_pct']:5.1f}%  Cal {r['calmar']:6.2f}  "
         f"trades {r['trades']:4d}  util {r['util_pct']:5.1f}%")
    if base:
        s += (f"  | Δ ₹{(r['pnl'] - base['pnl']) / 1e3:+7.1f}k  ΔDD {r['max_dd_pct'] - base['max_dd_pct']:+5.1f}pp"
              f"  ΔCal {r['calmar'] - base['calmar']:+6.2f}")
    return s


def verdict(results: dict, base: dict) -> dict:
    """Stage-B pass rule (pre-registered): Calmar >= baseline in >= 3/4 half-years,
    FULL P&L >= baseline, FULL DD no worse than baseline + 1pp."""
    hy = [w for w in HALF_YEARS if w in results and w in base]
    cal_wins = sum(results[w]["calmar"] >= base[w]["calmar"] for w in hy)
    out = {"calmar_wins": f"{cal_wins}/{len(hy)}"}
    if "FULL" in results and "FULL" in base:
        out["full_pnl_ok"] = results["FULL"]["pnl"] >= base["FULL"]["pnl"]
        out["full_dd_ok"] = results["FULL"]["max_dd_pct"] <= base["FULL"]["max_dd_pct"] + 1.0
        out["pass"] = bool(len(hy) == 4 and cal_wins >= 3 and out["full_pnl_ok"] and out["full_dd_ok"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--overlay", default=None, help="YAML deep-merged onto config/config.yaml")
    ap.add_argument("--windows", nargs="+", default=list(WINDOWS))
    ap.add_argument("--symbols", nargs="+", default=None)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--out", required=True)
    ap.add_argument("--compare", default=None, help="baseline JSON to diff against")
    args = ap.parse_args()

    base = None
    if args.compare:
        base = json.loads(Path(args.compare).read_text())["results"]

    results: dict[str, dict] = {}
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_run_window, w, args.overlay, args.symbols): w for w in args.windows}
        for fut in as_completed(futs):
            r = fut.result()
            results[r["window"]] = r
            print(_fmt(r, base.get(r["window"]) if base else None), flush=True)

    import subprocess
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--", "trader", "config"],
                                capture_output=True, text=True).stdout.strip())
    payload = {"label": args.label, "overlay": args.overlay, "git_head": head, "dirty_tree": dirty,
               "run_at": datetime.now().isoformat(timespec="seconds"),
               "results": {w: results[w] for w in args.windows if w in results}}
    if base:
        payload["verdict"] = verdict(results, base)
        print("verdict:", payload["verdict"])
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, indent=1))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
