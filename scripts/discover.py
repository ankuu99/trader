"""
discover.py — surface new watchlist candidates, ranked by mean-reversion FIT (not backtest P&L).

Two modes:

  --mode screen   (default) Gate the existing NSE-wide screen CSV. Cheap, but the CSV is a stale
                  backtest. Good for mining what was already computed.
  --mode universe Fresh, forward-looking scan of a curated liquid universe (e.g. Nifty 500
                  constituents passed via --universe-file). Ranks by structure + oscillation on
                  daily candles computed today — no stale backtest, no microcap/story-stock trap.

Both modes share the same gates, cheapest-first, so the strategy's fit profile drives selection
— liquid, range-bound / oscillating, structurally sound — never the biggest backtest number or
the hottest momentum name (those are the AQYLON / ELECTHERM traps).

    python scripts/discover.py                                   # screen mode
    python scripts/discover.py --mode universe --universe-file /tmp/nifty500.csv --json

The universe file may be an NSE index CSV (a "Symbol" column) or a plain newline list of tickers.
"""

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")

from trader.core.config import config
from trader.data.store import Store
from trader.data.historical import get_candles
from scripts.trend_guard import _daily_closes, evaluate

_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "config.yaml"
_MIN_TURNOVER = 5_000_000.0   # ₹50L avg daily turnover (CLAUDE.md liquidity floor)
_GUARD_DROP = {"FALLING_KNIFE", "DOWNTREND", "SPIKE"}  # structurally unfit / pump risk
_GUARD_RANK = {"RANGE_BOUND": 0, "WATCH_RECOVERING": 1, "UPTREND": 2}  # best fit first


def _already_considered() -> set[str]:
    """Every NSE:SYMBOL mentioned anywhere in config.yaml — active, parked, removed, or override."""
    return set(re.findall(r"NSE:[A-Z0-9&]+", _CONFIG_PATH.read_text()))


def _f(row: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(row[key])
    except (KeyError, ValueError, TypeError):
        return default


def _efficiency_ratio(daily, n: int = 60):
    """Kaufman efficiency ratio over the last n daily closes: |net move| / total path.
    Low (~<0.3) = choppy / range-bound (good mean-reversion fit); high (~>0.6) = trending."""
    s = daily.tail(n + 1)
    if len(s) < n + 1:
        return None
    net = abs(float(s.iloc[-1]) - float(s.iloc[0]))
    path = float(s.diff().abs().sum())
    return round(net / path, 3) if path > 0 else None


def _candle_metrics(sym: str, token, kite, store):
    """Fetch daily candles and compute liquidity + structural guard + oscillation.
    Returns (metrics_dict, None) on success or (None, reason) when the symbol is dropped."""
    frm = datetime.now() - timedelta(days=550)
    to = datetime.now()
    if token is None:
        return None, "not on NSE"
    try:
        df = get_candles(kite, store, token, sym, "day", frm, to)
    except Exception as e:
        return None, f"fetch error: {e}"
    if df.empty or len(df) < 30:
        return None, "insufficient daily history"
    turnover = float((df["close"] * df["volume"]).tail(60).mean())
    if turnover < _MIN_TURNOVER:
        return None, f"illiquid (₹{turnover/1e5:.1f}L/day)"
    daily = _daily_closes(df)
    guard = evaluate(sym, daily)
    if guard["structural_verdict"] in _GUARD_DROP:
        return None, f"{guard['structural_verdict']} (dd {guard['drawdown_from_peak_pct']}%)"
    return {
        "instrument": sym,
        "turnover_lakh": round(turnover / 1e5, 1),
        "guard_verdict": guard["structural_verdict"],
        "drawdown_pct": guard["drawdown_from_peak_pct"],
        "ret_6m": guard["trailing_returns_pct"].get("6m"),
        "ret_12m": guard["trailing_returns_pct"].get("12m"),
        "efficiency_ratio": _efficiency_ratio(daily),
    }, None


def _load_universe(path: str) -> list[str]:
    """Read NSE symbols from an index CSV (Symbol column) or a plain newline list."""
    text = Path(path).read_text()
    syms = []
    if "," in text.splitlines()[0]:  # CSV with header
        for row in csv.DictReader(text.splitlines()):
            s = (row.get("Symbol") or row.get("symbol") or "").strip()
            if s:
                syms.append(f"NSE:{s}")
    else:
        for line in text.splitlines():
            s = line.strip().upper()
            if s:
                syms.append(s if s.startswith("NSE:") else f"NSE:{s}")
    return syms


def _fit_sort_key(r: dict):
    """RANGE_BOUND first, then choppiest (lowest efficiency ratio), then most liquid."""
    return (_GUARD_RANK.get(r["guard_verdict"], 9),
            r["efficiency_ratio"] if r["efficiency_ratio"] is not None else 1.0,
            -r["turnover_lakh"])


def main():
    ap = argparse.ArgumentParser(description="Surface watchlist candidates ranked by fit")
    ap.add_argument("--mode", choices=["screen", "universe"], default="screen")
    ap.add_argument("--csv", default="results/screen_2024_2026.csv", help="screen mode: screen results CSV")
    ap.add_argument("--universe-file", help="universe mode: NSE index CSV or newline ticker list")
    ap.add_argument("--min-return", type=float, default=5.0, help="screen mode: min screen return_pct")
    ap.add_argument("--min-wr", type=float, default=50.0, help="screen mode: min screen win_rate")
    ap.add_argument("--min-trades", type=int, default=10, help="screen mode: min screen trades")
    ap.add_argument("--max-fetch", type=int, default=60, help="max symbols to fetch/gate")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    considered = _already_considered()

    # Build the candidate symbol list (with optional screen metrics) per mode.
    screen_meta: dict[str, dict] = {}
    if args.mode == "screen":
        rows = list(csv.DictReader(open(args.csv)))
        cand = []
        for r in rows:
            sym = r.get("instrument", "")
            if not sym.startswith("NSE:") or "-" in sym.split(":", 1)[1] or sym in considered:
                continue
            if (_f(r, "trades") >= args.min_trades and _f(r, "return_pct") > args.min_return
                    and _f(r, "win_rate") >= args.min_wr):
                cand.append(sym)
                screen_meta[sym] = {"ret": _f(r, "return_pct"), "wr": _f(r, "win_rate"),
                                    "trades": int(_f(r, "trades"))}
        cand.sort(key=lambda s: -screen_meta[s]["ret"])
        universe_n = len(rows)
    else:
        if not args.universe_file:
            print(json.dumps({"error": "universe mode needs --universe-file"})); return
        all_syms = _load_universe(args.universe_file)
        cand = [s for s in all_syms if s not in considered and "-" not in s.split(":", 1)[1]]
        universe_n = len(all_syms)

    if not args.json:
        print(f"\n  Mode: {args.mode} | universe {universe_n} → {len(cand)} after segment/dedup filters")
        print(f"  Fetching daily candles for up to {min(args.max_fetch, len(cand))} (liquidity + structure)...")

    from trader.auth.session import create_kite
    kite = create_kite()
    s2t = {f"NSE:{i['tradingsymbol']}": i["instrument_token"] for i in kite.instruments("NSE")}
    store = Store(config.db_path)

    kept, dropped = [], []
    for sym in cand[:args.max_fetch]:
        m, reason = _candle_metrics(sym, s2t.get(sym), kite, store)
        if m is None:
            dropped.append((sym, reason))
        else:
            if sym in screen_meta:
                m["screen_return_pct"] = screen_meta[sym]["ret"]
                m["screen_win_rate"] = screen_meta[sym]["wr"]
                m["screen_trades"] = screen_meta[sym]["trades"]
            kept.append(m)
        time.sleep(0.2)  # be polite to the Kite API on cache-miss fetches

    kept.sort(key=_fit_sort_key)

    if args.json:
        print(json.dumps({"mode": args.mode, "candidates": kept, "dropped": dropped}))
        return

    print(f"\n  >>> {len(kept)} candidates passed liquidity + structural guard ({len(dropped)} dropped):\n")
    print(f"  {'symbol':20} {'guard':16} {'ER':>5} {'turnover':>9} {'6m%':>7} {'12m%':>7}  notes")
    for r in kept:
        extra = ""
        if "screen_return_pct" in r:
            extra = f"scr_ret={r['screen_return_pct']:.0f}% wr={r['screen_win_rate']:.0f}%"
        print(f"  {r['instrument']:20} {r['guard_verdict']:16} {str(r['efficiency_ratio']):>5} "
              f"{r['turnover_lakh']:>7.0f}L {str(r['ret_6m']):>7} {str(r['ret_12m']):>7}  {extra}")
    print(f"\n  (ER = efficiency ratio: lower = choppier/range-bound = better fit. RANGE_BOUND first.)")
    print(f"  Next: run the `qualify` skill on the top RANGE_BOUND survivors.\n")


if __name__ == "__main__":
    main()
