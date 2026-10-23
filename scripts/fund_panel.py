#!/usr/bin/env python
"""
fund_panel.py — two-sided fundamental panel for LRExtrema stock selection.

LRExtrema is mean-reversion: it buys local-minima dips. The fundamental question is
NOT "is this a great business" in the abstract, but "when this stock dips, will the dip
RECOVER or keep falling?" Fundamentals answer that two ways:

  • RED FLAGS (disqualifier)  — distress that makes a dip a trap: thin interest cover,
    leverage spike, profit collapse, negative operating cash, promoter pledge/selling.
    These escalate a name toward AVOID/REMOVE regardless of how it backtested
    (backtests are regime-blind — the RMDRIP / falling-knife failure).

  • QUALITY (positive picker) — durable growth + expanding margins + low leverage +
    clean ownership mean the business compounds underneath, so pullbacks mean-revert.
    This is why a quality stock in an UPTREND (e.g. CUPID) is a *good* LRExtrema fit,
    not a bad one — every dip is buyable. So fundamentals are not merely a veto.

Source resolution (per symbol):
  1. fvm.db if the name is already ingested (fast path).
  2. else fetch on demand via the Trendlyne fincsv API (token+cookie) — works for ANY
     NSE name in the master list, including small-caps outside the Nifty500 universe
     (CUPID etc.). The fetched rows are cached into fvm.db (same PIT schema as the daily
     ingest), so subsequent runs are instant.
  3. if the name isn't in the master list or the cookie is stale → source="none",
     verdict INSUFFICIENT; fall back to the Trendlyne *browser* session manually.

IMPORTANT: quality_score here is an ABSOLUTE threshold heuristic, deliberately NOT the
FVM cross-sectional composite (percentile-vs-Nifty500-peers). Absolute thresholds need no
peer pool, so this works for out-of-universe names too. For in-universe ranking use
scripts/fvm_shortlist.py.

Usage:
    python scripts/fund_panel.py --symbol NSE:CUPID [--asof YYYY-MM-DD] [--json] [--no-fetch]
"""

import argparse
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")

from trader.fvm import factors
from trader.fvm.data.store import FVMStore
from trader.fvm.data.universe import is_financial


# ------------------------------------------------------------------ #
# Source resolution                                                   #
# ------------------------------------------------------------------ #

def _has_financials(store, sym, asof) -> bool:
    return bool(store.read_fundamental_asof(sym, "annual", "consolidated", "Net Profit Annual", asof))


def _ensure_data(store, sym, asof, allow_fetch) -> str:
    """Return the data source for `sym`: 'fvm.db' (already present), 'fetched' (pulled on
    demand and cached), or 'none' (unavailable). Never raises — network/cookie failures
    degrade to 'none' so the panel can still report INSUFFICIENT."""
    if _has_financials(store, sym, asof):
        return "fvm.db"
    if not allow_fetch:
        return "none"
    try:
        from trader.fvm.data.screener import ingest_shareholding
        from trader.fvm.data.trendlyne import TrendlyneClient, ingest_financials
        tc = TrendlyneClient()
        if not store.get_stock_hash(sym):
            return "none"          # not in master list — needs the browser fallback
        ingest_financials(store, sym, tc)
        try:
            ingest_shareholding(store, sym)
        except Exception:
            pass                   # shareholding is best-effort; financials are enough
        return "fetched" if _has_financials(store, sym, asof) else "none"
    except Exception:
        return "none"


def _promoter_trend(store, sym, asof):
    """Slope (pp/quarter) of promoter holding over the last 4 quarters; None if <2 points."""
    d = store.read_shareholding_asof(sym, "promoter", asof)
    vals = [v for _, v in sorted(d.items()) if v is not None]
    return factors.slope(vals[-4:]) if len(vals) >= 2 else None


# ------------------------------------------------------------------ #
# Panel logic — absolute thresholds (NOT cross-sectional)            #
# ------------------------------------------------------------------ #

def build_panel(f: dict, promoter_trend, financial: bool = False) -> dict:
    """From raw factor values, produce red_flags, positives, quality_score and a verdict.

    `financial=True` (banks/NBFCs/insurers) suppresses the leverage / interest-cover /
    operating-cash checks — for a lender, high D/E, thin coverage and negative CFO are
    structural, not distress. Growth, returns and ownership signals still apply. (FVM's
    own universe excludes financials entirely; here we still want a usable read on
    watchlist financials like M&MFIN / LTF.)"""
    red, pos = [], []

    def flag(cond, sev, key, detail):
        if cond:
            red.append({"severity": sev, "flag": key, "detail": detail})

    def good(cond, key, detail):
        if cond:
            pos.append({"factor": key, "detail": detail})

    ic, de, dt = f.get("interest_coverage"), f.get("debt_to_equity"), f.get("debt_trend")
    yoy, cfo = f.get("yoy_profit_growth"), f.get("cfo_to_np")
    pledge = f.get("pledge")
    roce, opm = f.get("roce"), f.get("opm_trend")
    rev = f.get("revenue_growth")

    # --- red flags (distress: a dip here may not recover) ---
    # leverage / coverage / operating-cash are meaningless for lenders → skip for financials
    if not financial:
        flag(ic is not None and ic < 1.5, "high", "thin_interest_cover",
             f"interest coverage {ic:.1f}× (<1.5 = struggles to service debt)" if ic is not None else "")
        flag(de is not None and de > 2.0, "high", "high_leverage", f"D/E {de:.2f} (>2.0)")
        flag(de is not None and 1.0 < de <= 2.0 and (dt or 0) > 0, "med", "rising_leverage",
             f"D/E {de:.2f} and rising")
        # Negative operating cash: deeply negative (cfo < -0.3) is real cash bleed → high.
        # A *mildly* negative single year (-0.3..0) is routinely working-capital build in
        # inventory-heavy growers (gold/jewellery, cables) — only high if returns/growth are
        # ALSO weak; otherwise med with a working-capital note. Mirrors the financial-sector
        # suppression: don't let one soft CFO year force DISTRESS on a 30%-ROCE doubler.
        _cfo_weak_context = (roce is None or roce < 15) or (yoy is None or yoy < 0.15)
        flag(cfo is not None and (cfo < -0.3 or (cfo < 0 and _cfo_weak_context)),
             "high", "negative_operating_cash",
             f"CFO/NP {cfo:.2f} (operating cash negative vs reported profit)" if cfo is not None else "")
        flag(cfo is not None and -0.3 <= cfo < 0 and not _cfo_weak_context,
             "med", "negative_operating_cash_wc",
             f"CFO/NP {cfo:.2f} — single-year negative but ROCE/growth strong (likely working capital)"
             if cfo is not None else "")
        flag(cfo is not None and 0 <= cfo < 0.3, "med", "weak_cash_conversion", f"CFO/NP {cfo:.2f}")
    flag(yoy is not None and yoy < -0.5, "high", "profit_collapse",
         f"YoY profit growth {yoy:+.0%} (PAT down >50%)" if yoy is not None else "")
    flag(yoy is not None and -0.5 <= yoy < -0.2, "med", "profit_decline",
         f"YoY profit growth {yoy:+.0%}")
    _pl = f"pledge {pledge:.1f}%" if pledge is not None else ""
    flag(pledge is not None and pledge > 25, "high", "high_promoter_pledge", _pl)
    flag(pledge is not None and 10 < pledge <= 25, "med", "promoter_pledge", _pl)
    flag(promoter_trend is not None and promoter_trend < -1.0, "med", "promoter_selling",
         f"promoter holding falling {promoter_trend:.2f} pp/qtr")

    # --- positives (quality: business compounds, so dips mean-revert) ---
    good(yoy is not None and yoy > 0.15, "profit_growth", f"YoY profit growth {yoy:+.0%}")
    good(f.get("growth_acceleration") is not None and f["growth_acceleration"] > 0,
         "accelerating", "profit growth accelerating")
    good(rev is not None and rev > 0.10, "revenue_growth", f"revenue +{rev:.0%} YoY")
    good(opm is not None and opm > 0, "margin_expansion", "operating margin trending up")
    good(roce is not None and roce > 15, "high_roce", f"ROCE {roce:.1f}%")
    good(f.get("roce_trend") is not None and f["roce_trend"] > 0, "improving_returns", "ROCE rising")
    good(de is not None and de < 0.5, "low_leverage", f"D/E {de:.2f}")
    good(cfo is not None and cfo > 0.6, "good_cash_conversion", f"CFO/NP {cfo:.2f}")
    good(pledge in (None, 0) or (pledge is not None and pledge == 0), "no_pledge", "no promoter pledge")

    # --- quality_score: mean of present component scores in [0,1] (None components skipped) ---
    def bucket(v, hi, mid, higher_better=True):
        if v is None:
            return None
        if higher_better:
            return 1.0 if v >= hi else 0.5 if v >= mid else 0.0
        return 1.0 if v <= hi else 0.5 if v <= mid else 0.0

    comps = [
        bucket(yoy, 0.15, 0.0),
        bucket(opm, 0.0001, -0.0001),          # margin trend up / flat / down
        bucket(roce, 18, 12),
        bucket(0.0 if pledge in (None, 0) else pledge, 0.0, 10.0, higher_better=False),
    ]
    if not financial:                          # leverage/coverage/cash not comparable for lenders
        comps += [
            bucket(de, 0.5, 1.0, higher_better=False),
            bucket(ic, 5, 2),
            bucket(cfo, 0.6, 0.3),
        ]
    present = [c for c in comps if c is not None]
    quality_score = round(sum(present) / len(present), 3) if present else None

    has_high = any(r["severity"] == "high" for r in red)
    if quality_score is None:
        verdict = "INSUFFICIENT"
    elif has_high:
        verdict = "DISTRESS"
    elif quality_score >= 0.70 and not red:
        verdict = "STRONG"
    elif quality_score >= 0.45:
        verdict = "OK"
    else:
        verdict = "WEAK"

    return {
        "fund_verdict": verdict,
        "quality_score": quality_score,
        "red_flags": red,
        "positives": pos,
    }


def analyze(symbol: str, asof: str, db: str, allow_fetch: bool) -> dict:
    sym = symbol.upper().replace("NSE:", "")
    store = FVMStore(db)
    source = _ensure_data(store, sym, asof, allow_fetch)
    if source == "none":
        return {
            "symbol": f"NSE:{sym}", "asof": asof, "source": "none",
            "fund_verdict": "INSUFFICIENT", "quality_score": None,
            "red_flags": [], "positives": [],
            "note": "Not in fvm.db and could not fetch (not in Trendlyne master, or stale "
                    "TRENDLYNE_COOKIE). Use the logged-in Trendlyne browser session as fallback.",
        }
    f = factors.all_factors(store, sym, asof)
    promoter_trend = _promoter_trend(store, sym, asof)

    # Weekly Trendlyne snapshot overlay (tl_snapshot, if ingested): fills the pledge /
    # promoter-trend coverage gaps and adds fields the API stack has no source for.
    from trader.fvm.data import snapshot as snap_mod
    snap = snap_mod.read_snapshot(store, sym, asof)
    if snap:
        if f.get("pledge") is None and snap.get("pledge") is not None:
            f["pledge"] = snap["pledge"]
        if promoter_trend is None and snap.get("promoter_chg_4q") is not None:
            promoter_trend = snap["promoter_chg_4q"] / 4.0  # pp/quarter
    sector = store.sectors_map().get(sym)
    financial = is_financial(sector)
    panel = build_panel(f, promoter_trend, financial=financial)
    metrics = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in f.items()}
    metrics["promoter_trend_pp_per_qtr"] = (
        round(promoter_trend, 3) if promoter_trend is not None else None)
    notes = []
    if financial:
        notes.append(f"financial-sector ({sector}) — leverage / interest-cover / operating-cash "
                     f"flags suppressed (structural for lenders); judged on growth, returns, ownership")
    if f.get("ev_ebitda") is not None and f["ev_ebitda"] > 30:
        notes.append(f"richly valued (EV/EBITDA {f['ev_ebitda']:.0f}) — less critical for "
                     f"dip-buying than for buy-and-hold, but caps upside")
    snapshot_read = None
    if snap:
        snapshot_read = {k: snap.get(k) for k in
                         ("as_of", "durability", "valuation", "momentum", "dvm_class",
                          "piotroski", "pledge", "mf_chg_qoq", "fii_chg_qoq",
                          "pct_days_below_pe")}
        for fl in snap_mod.watchlist_flags(snap):
            notes.append(f"snapshot ({snap['as_of']}): {fl}")
    return {
        "symbol": f"NSE:{sym}", "asof": asof, "source": source,
        "sector": sector, "financial": financial,
        **panel, "snapshot": snapshot_read, "metrics": metrics, "notes": notes,
    }


def _print_human(r: dict) -> None:
    print(f"\n=== Fundamental panel — {r['symbol']}  (asof {r['asof']}, source: {r['source']}) ===")
    qs = r["quality_score"]
    print(f"VERDICT: {r['fund_verdict']}   quality_score: {qs if qs is not None else 'n/a'}")
    if r.get("note"):
        print(f"  {r['note']}")
        return
    if r["red_flags"]:
        print("\n  RED FLAGS:")
        for x in r["red_flags"]:
            mark = "🔴" if x["severity"] == "high" else "🟡"
            print(f"    {mark} {x['flag']}: {x['detail']}")
    else:
        print("\n  RED FLAGS: none")
    if r["positives"]:
        print("\n  POSITIVES:")
        for x in r["positives"]:
            print(f"    🟢 {x['factor']}: {x['detail']}")
    s = r.get("snapshot")
    if s:
        def _n(v, nd=0):
            return "—" if v is None else f"{v:.{nd}f}"
        print(f"\n  SNAPSHOT ({s['as_of']}): D={_n(s['durability'])} V={_n(s['valuation'])} "
              f"M={_n(s['momentum'])}  Piotroski={_n(s['piotroski'])}/9  "
              f"pledge={_n(s['pledge'], 1)}%  MF+FII QoQ="
              f"{_n((s['mf_chg_qoq'] or 0) + (s['fii_chg_qoq'] or 0), 2)}pp  "
              f"[{s['dvm_class'] or '—'}]")
    for n in r.get("notes", []):
        print(f"\n  note: {n}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", required=True, help="NSE:SYMBOL or bare ticker")
    ap.add_argument("--asof", default=datetime.date.today().isoformat())
    ap.add_argument("--db", default="data/fvm.db")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--no-fetch", action="store_true",
                    help="cache-only: do not fetch from Trendlyne if absent")
    args = ap.parse_args()

    r = analyze(args.symbol, args.asof, args.db, allow_fetch=not args.no_fetch)
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        _print_human(r)


if __name__ == "__main__":
    main()
