"""
diag_firings.py — Outcome-based firing-precision diagnostic for LRExtremaStrategy.

Measures the model's REAL false-positive rate: for every candle where the model's
P(local-min) crosses a threshold (a would-be BUY firing), grade the firing by what
price actually did next (triple-barrier race), independent of geometric extrema
labels. Symmetrically for P(local-max) (would-be top calls).

This is the number the #8 training diagnostic cannot see: its holdout contains only
labelled extrema candles, so it measures "min vs max on extrema", never "firing vs
ordinary candle" — which is where live FPs live.

Grading (fixed, definition-stable across model A/Bs):
  dip firing  CORRECT  if high hits entry*(1+up_pct) before low hits entry*(1-down_pct)
              within horizon bars (tie -> incorrect, conservative);
              time-barrier fallback: close > entry at horizon.
  top firing  CORRECT  if the mirrored race resolves down first.
  Firings whose horizon extends past the cached candles are dropped (unresolved).

Also reports "episodes" — consecutive above-threshold candles collapsed to one —
approximating actual entries (live, one entry consumes the whole cluster).

Usage:
    python scripts/diag_firings.py --from 2026-01-01 --to 2026-07-01
    python scripts/diag_firings.py --from 2026-01-01 --symbols NSE:CUPID NSE:QUESS
    python scripts/diag_firings.py --from 2026-01-01 --up-pct 3 --down-pct 3 --horizon 200

Read-only: uses cached candles only; never writes to the DB or touches trading state.
"""

import argparse
import csv
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")

from trader.core.config import config
from trader.core.logger import setup
from trader.data.store import Store
from trader.features.labels import triple_barrier_label
from trader.strategies.lr_extrema import LRExtremaStrategy

setup(log_dir=config.log_dir, level="CRITICAL")

GRID = [0.80, 0.85, 0.88, 0.90, 0.92, 0.95, 0.98]
# Neutral-class scores live on a lower scale (mass shared with class 2) — sweep wider.
GRID_WIDE = [0.40, 0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.95]


def _grade_dip(candles, idx, up_pct, down_pct, horizon):
    """1 = dip correct (up barrier first), 0 = wrong, None = unresolved."""
    return triple_barrier_label(candles, idx, profit_pct=up_pct, stop_pct=down_pct,
                                max_bars=horizon)


def _grade_top(candles, idx, up_pct, down_pct, horizon):
    """1 = top correct (down barrier first), 0 = wrong, None = unresolved.
    Mirror of the dip race: triple_barrier_label returns 0 when the down side
    resolves first (incl. the below-entry time-barrier fallback)."""
    lbl = triple_barrier_label(candles, idx, profit_pct=up_pct, stop_pct=down_pct,
                               max_bars=horizon)
    if lbl is None:
        return None
    return 1 - lbl


def _fwd_extremes(candles, idx, horizon):
    """(peak_gain_pct, trough_pct) over the next `horizon` bars, or (None, None)."""
    end = min(idx + horizon, len(candles) - 1)
    if end <= idx:
        return None, None
    entry = candles[idx]["close"]
    if entry <= 0:
        return None, None
    highs = max(c["high"] for c in candles[idx + 1: end + 1])
    lows = min(c["low"] for c in candles[idx + 1: end + 1])
    return (highs - entry) / entry * 100.0, (lows - entry) / entry * 100.0


def _episodes(flags: list[bool]) -> int:
    """Count runs of consecutive True values."""
    runs, prev = 0, False
    for f in flags:
        if f and not prev:
            runs += 1
        prev = f
    return runs


def _replay_scores(symbol: str, candles: list[dict], force_neutral: bool = False):
    """Feed candles through the strategy (real retrain cadence) and return the
    per-candle (p_min, p_max) once trained. Position state is cleared each candle
    so scoring is never blocked by phantom entries (same trick as replay_strategy)."""
    import copy
    params = copy.deepcopy(config.get_strategy_params(symbol, "lr_extrema"))
    if force_neutral:
        params.setdefault("labels", {})["neutral"] = {
            "enabled": True, "ratio": 1.0, "margin_bars": None}
    strategy = LRExtremaStrategy(symbol, params)
    scores: list[tuple[float, float] | None] = []
    for candle in candles:
        strategy.on_candle(candle)
        strategy._pos.reset()
        strategy.position = None
        scores.append(strategy.score_current())
    return params, scores


def main():
    parser = argparse.ArgumentParser(description="Outcome-based firing-precision diagnostic")
    parser.add_argument("--from", dest="from_date", required=True)
    parser.add_argument("--to", dest="to_date", default=datetime.datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--symbols", nargs="+", default=None)
    parser.add_argument("--up-pct", type=float, default=3.0,
                        help="Up barrier %% for grading (default 3 = sell_min_pct)")
    parser.add_argument("--down-pct", type=float, default=3.0,
                        help="Down barrier %% for grading (default 3, symmetric race)")
    parser.add_argument("--horizon", type=int, default=200,
                        help="Bars for the race / time barrier (default 200 = hold_bars)")
    parser.add_argument("--csv", default=None, help="Optional per-firing CSV dump path")
    parser.add_argument("--neutral", action="store_true",
                        help="Force labels.neutral.enabled=true (A/B without editing config)")
    parser.add_argument("--wide-grid", action="store_true",
                        help="Sweep the lower/wider threshold grid (for neutral-scale scores)")
    args = parser.parse_args()

    from_dt = datetime.datetime.strptime(args.from_date, "%Y-%m-%d")
    to_dt = datetime.datetime.strptime(args.to_date, "%Y-%m-%d").replace(hour=23, minute=59)
    symbols = args.symbols or list(config.watchlist)

    store = Store(config.db_path)
    grid = GRID_WIDE if args.wide_grid else GRID
    rows_csv: list[dict] = []
    portfolio: dict[float, dict] = {t: {"dip_n": 0, "dip_ok": 0, "top_n": 0, "top_ok": 0}
                                    for t in grid}

    print(f"\nFiring diagnostic {args.from_date} → {args.to_date} | "
          f"race: +{args.up_pct}% vs -{args.down_pct}% within {args.horizon} bars "
          f"(tie/time-barrier resolved conservatively)\n")

    for symbol in symbols:
        # Load the full cache so the strategy warms up exactly like live/backtest;
        # only candles inside [from, to] are recorded.
        df = store.read_candles(symbol, config.candle_timeframe,
                                datetime.datetime(2000, 1, 1), to_dt)
        if df.empty:
            print(f"  {symbol:<16} no cached candles — skipped")
            continue
        candles = df.to_dict("records")
        params, scores = _replay_scores(symbol, candles, force_neutral=args.neutral)
        live_thr = params.get("threshold", 0.90)
        sell_thr = params.get("sell_threshold",
                              (params.get("exits", {}).get("pattern_top", {})
                               .get("sell_threshold", 0.85)))

        # Collect scored candles inside the window, with grades computed lazily.
        window: list[dict] = []
        for i, sc in enumerate(scores):
            if sc is None:
                continue
            ts = candles[i]["timestamp"]
            ts_dt = datetime.datetime.fromisoformat(str(ts)[:19])
            if not (from_dt <= ts_dt <= to_dt):
                continue
            p_min, p_max = sc
            entry = {"idx": i, "ts": ts, "p_min": p_min, "p_max": p_max,
                     "dip_grade": None, "top_grade": None}
            if p_min >= grid[0]:
                entry["dip_grade"] = _grade_dip(candles, i, args.up_pct, args.down_pct,
                                                args.horizon)
            if p_max >= grid[0]:
                entry["top_grade"] = _grade_top(candles, i, args.up_pct, args.down_pct,
                                                args.horizon)
            window.append(entry)

        if not window:
            print(f"  {symbol:<16} no scored candles in window — skipped")
            continue

        sym_short = symbol.replace("NSE:", "")
        print(f"  {sym_short}  (threshold={live_thr}  sell_threshold={sell_thr}  "
              f"scored candles={len(window)})")
        print(f"    {'thr':>5}  {'dipN':>5} {'ep':>4} {'prec':>6} {'avgPk':>7} {'avgTr':>7}"
              f"   {'topN':>5} {'ep':>4} {'prec':>6}")

        for thr in grid:
            dip = [w for w in window if w["p_min"] >= thr and w["dip_grade"] is not None]
            top = [w for w in window if w["p_max"] >= thr and w["top_grade"] is not None]
            dip_ok = sum(w["dip_grade"] for w in dip)
            top_ok = sum(w["top_grade"] for w in top)
            dip_ep = _episodes([w["p_min"] >= thr for w in window])
            top_ep = _episodes([w["p_max"] >= thr for w in window])
            dip_prec = dip_ok / len(dip) if dip else float("nan")
            top_prec = top_ok / len(top) if top else float("nan")
            pks, trs = [], []
            for w in dip:
                pk, tr = _fwd_extremes(candles, w["idx"], args.horizon)
                if pk is not None:
                    pks.append(pk)
                    trs.append(tr)
            avg_pk = sum(pks) / len(pks) if pks else float("nan")
            avg_tr = sum(trs) / len(trs) if trs else float("nan")
            marker = " <- live thr" if abs(thr - live_thr) < 1e-9 else ""
            print(f"    {thr:>5.2f}  {len(dip):>5} {dip_ep:>4} {dip_prec:>6.2f} "
                  f"{avg_pk:>+6.1f}% {avg_tr:>+6.1f}%   {len(top):>5} {top_ep:>4} "
                  f"{top_prec:>6.2f}{marker}")
            portfolio[thr]["dip_n"] += len(dip)
            portfolio[thr]["dip_ok"] += dip_ok
            portfolio[thr]["top_n"] += len(top)
            portfolio[thr]["top_ok"] += top_ok

        if args.csv:
            for w in window:
                if w["dip_grade"] is None and w["top_grade"] is None:
                    continue
                rows_csv.append({"symbol": symbol, "timestamp": w["ts"],
                                 "p_min": round(w["p_min"], 4), "p_max": round(w["p_max"], 4),
                                 "dip_grade": w["dip_grade"], "top_grade": w["top_grade"]})
        print()

    print("  PORTFOLIO (all symbols pooled, graded firings only)")
    print(f"    {'thr':>5}  {'dipN':>6} {'dip_prec':>9}   {'topN':>6} {'top_prec':>9}")
    for thr in grid:
        p = portfolio[thr]
        dp = p["dip_ok"] / p["dip_n"] if p["dip_n"] else float("nan")
        tp = p["top_ok"] / p["top_n"] if p["top_n"] else float("nan")
        print(f"    {thr:>5.2f}  {p['dip_n']:>6} {dp:>9.2f}   {p['top_n']:>6} {tp:>9.2f}")
    print()

    if args.csv and rows_csv:
        out = Path(args.csv)
        with open(out, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows_csv[0].keys()))
            writer.writeheader()
            writer.writerows(rows_csv)
        print(f"  Per-firing CSV saved: {out}")


if __name__ == "__main__":
    main()
