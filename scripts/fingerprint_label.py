#!/usr/bin/env python
"""
Fundamental-fingerprint discovery — Step 1: winner / loser / baseline labelling.

Pools the names LRExtrema trades *well* (winners) and *poorly* (losers) from the
NSE-wide screen CSV, unioned with the calibrated `per_stock_params` names (de-facto
winners someone bothered to tune and keep). Emits an explicit, conservative,
segment-clean label set that Step 2 fingerprints on PIT fundamentals.

This step is deliberately dumb and auditable — no fundamentals are touched here. It
just answers "which names trade well / badly, and how many of each do we actually
have?" so the small-N risk is visible *before* any fingerprint is built.

Usage:
    python scripts/fingerprint_label.py [--screen results/screen_2024_2026.csv]
                                        [--min-return 5] [--min-wr 50] [--min-trades 3]
                                        [--json] [--out reviews/fingerprint_labels.json]

Winner  : return_pct >= min_return AND win_rate >= min_wr AND trades >= min_trades
          ∪ calibrated per_stock_params names (excluding ones explicitly removed)
Loser   : trades >= min_trades AND (return_pct < 0 OR win_rate < 35)
Baseline: the rest of the clean-equity screen universe (for "winner trait vs
          any-stock trait" contrast in Step 3).
"""

import argparse
import csv
import json
import re

import yaml

# Segments / instrument codes that are not ordinary EQ series — drop them. The screen
# CSV is the full NSE master, so it is full of bonds, SGBs, ETFs, InvITs, rights, etc.
_BAD_SUFFIX = re.compile(r"-(BE|BZ|N\d+|GB|GS|IV|RR|RE|RT|PP|E\d|W\d|Y\d)$", re.I)
# names with a leading digit (e.g. 0IRFC35, 7NTPC26) are bond/SGB ISINs in disguise
_LEADS_DIGIT = re.compile(r"^NSE:\d")
# config names removed for cause should not count as winners even if calibrated
_REMOVED = {"NSE:AQYLON", "NSE:TARAPUR", "NSE:RECLTD", "NSE:RMDRIP"}


def _clean_equity(sym: str) -> bool:
    """True if `sym` looks like an ordinary NSE equity (not a bond/ETF/segment series)."""
    if _LEADS_DIGIT.match(sym):
        return False
    if _BAD_SUFFIX.search(sym):
        return False
    return True


def _norm(sym: str) -> str:
    """Strip series suffix so screen names line up with config / fundamentals keys."""
    return _BAD_SUFFIX.sub("", sym)


def load_screen(path):
    rows = []
    with open(path) as fh:
        for r in csv.DictReader(fh):
            try:
                rows.append({
                    "instrument": r["instrument"],
                    "trades": int(r["trades"]),
                    "win_rate": float(r["win_rate"]),
                    "return_pct": float(r["return_pct"]),
                    "total_pnl": float(r["total_pnl"]),
                })
            except (ValueError, KeyError):
                continue
    return rows


def calibrated_names(config_path="config/config.yaml"):
    c = yaml.safe_load(open(config_path))
    psp = set((c.get("per_stock_params") or {}).keys())
    wl = {_norm(s) for s in (c.get("watchlist") or [])}
    # calibrated ∪ currently-traded, minus explicitly-removed
    return ({_norm(s) for s in psp} | wl) - _REMOVED


def label(rows, min_return, min_wr, min_trades, calibrated):
    """Return four buckets:

    curated  : the TRUSTED winners — calibrated `per_stock_params` ∪ vetted watchlist,
               minus explicitly-removed. These survived human + `qualify` review, so the
               Step-2 fingerprint is learned ONLY on these.
    screen   : names passing the raw screen bar but NOT curated. UNTRUSTED — the raw screen
               is heavily contaminated with pumps / story-stocks / falling knives that print
               fake mean-reversion wins (ELECTHERM, AQYLON, RMDRIP, microcaps). These are
               candidates to *score* in Step 4, never to *train* the fingerprint on.
    losers   : adequate trades but poor metrics — the contrast pool for Step 3.
    baseline : the rest of the clean-equity universe — "any-stock trait" contrast.
    """
    screen, losers, baseline = {}, {}, {}
    seen = set()
    for r in rows:
        sym = r["instrument"]
        if not _clean_equity(sym):
            continue
        key = _norm(sym)
        if key in seen:                       # screen has no dups, but be safe
            continue
        seen.add(key)
        is_winner = (r["return_pct"] >= min_return and r["win_rate"] >= min_wr
                     and r["trades"] >= min_trades)
        is_loser = (r["trades"] >= min_trades and (r["return_pct"] < 0 or r["win_rate"] < 35))
        if is_winner:
            screen[key] = r
        elif is_loser:
            losers[key] = r
        else:
            baseline[key] = r

    # Curated winners are the trusted training set. Pull their screen metrics in if present;
    # ensure they never sit in loser/baseline/screen-untrusted.
    curated = {}
    for sym in sorted(calibrated):
        curated[sym] = (screen.pop(sym, None) or losers.pop(sym, None)
                        or baseline.pop(sym, None)
                        or {"instrument": sym, "trades": None, "win_rate": None,
                            "return_pct": None, "total_pnl": None, "source": "calibrated"})
    # never let a known-removed/toxic name leak into the untrusted screen-winner pool either
    for bad in _REMOVED:
        screen.pop(bad, None)
    return curated, screen, losers, baseline


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--screen", default="results/screen_2024_2026.csv")
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--min-return", type=float, default=5.0)
    ap.add_argument("--min-wr", type=float, default=50.0)
    ap.add_argument("--min-trades", type=int, default=3)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", default=None, help="write label JSON to this path")
    args = ap.parse_args()

    rows = load_screen(args.screen)
    calibrated = calibrated_names(args.config)
    curated, screen, losers, baseline = label(rows, args.min_return, args.min_wr,
                                              args.min_trades, calibrated)

    low_power = len(curated) < 25
    result = {
        "screen": args.screen,
        "bar": {"min_return": args.min_return, "min_wr": args.min_wr,
                "min_trades": args.min_trades},
        "counts": {"curated_winners": len(curated), "screen_winners": len(screen),
                   "losers": len(losers), "baseline": len(baseline)},
        # the TRUSTED training set for the fingerprint (Step 2/3)
        "curated_winners": sorted(curated),
        # passed the raw bar but UNTRUSTED — score these in Step 4, never train on them
        "screen_winners": sorted(screen),
        "losers": sorted(losers),
        "baseline": sorted(baseline),
        "low_power": low_power,
    }

    if args.out:
        json.dump(result, open(args.out, "w"), indent=2)
    if args.json:
        print(json.dumps({k: v for k, v in result.items() if k != "baseline"}, indent=2))
        return

    print(f"screen: {args.screen}  ({len(rows)} rows)")
    print(f"bar: return>={args.min_return}%  WR>={args.min_wr}%  trades>={args.min_trades}")
    print(f"clean-equity universe: {len(curated)+len(screen)+len(losers)+len(baseline)}")
    print(f"  curated winners (TRUSTED, train fingerprint) : {len(curated):4}"
          f"{'   <-- LOW STATISTICAL POWER (<25)' if low_power else ''}")
    print(f"  screen winners  (UNTRUSTED, score only)      : {len(screen):4}")
    print(f"  losers                                       : {len(losers):4}")
    print(f"  baseline                                     : {len(baseline):4}")
    print("\ncurated (fingerprint training set):\n  " + ", ".join(sorted(curated)))
    print("\nscreen-only winners (UNTRUSTED — contaminated with pumps/microcaps):\n  "
          + ", ".join(sorted(screen)))
    if args.out:
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
