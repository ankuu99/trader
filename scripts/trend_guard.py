"""
trend_guard.py — deterministic structural-trend / falling-knife guard for stock selection.

LRExtremaStrategy is mean-reversion: it works on range-bound / oscillating stocks and
FAILS on stocks in a sustained one-way trend (every dip in a secular decline looks like a
local minimum — the RMDRIP failure mode). This script computes a purely price-based,
reproducible verdict on whether a stock is structurally tradeable by the strategy, so the
qualitative `qualify` skill can pair it with news/filings checks.

It resamples cached intraday candles to daily closes and reports trailing returns over
1/3/6/12-month windows, drawdown from the period peak, and distance above the period low.

    python scripts/trend_guard.py --symbol NSE:RMDRIP                # cache-only by default
    python scripts/trend_guard.py --symbol NSE:RMDRIP --fetch        # refresh candles from Kite first
    python scripts/trend_guard.py --symbol NSE:RMDRIP --json         # machine-readable output

Verdicts:
    FALLING_KNIFE — sustained decline AND price still near the period low (do not trade)
    DOWNTREND     — meaningful multi-month decline, but off the lows
    UPTREND       — strong sustained rally (few local minima; weak fit, not a loss risk)
    RANGE_BOUND   — oscillating without a strong directional trend (good fit)
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")

import pandas as pd

from trader.core.config import config
from trader.data.store import Store
from trader.data.historical import get_candles

# Trailing-return windows in trading days (~21 trading days per month)
_WINDOWS = {"1m": 21, "3m": 63, "6m": 126, "12m": 252}

# Verdict thresholds (tunable)
_KNIFE_DRAWDOWN = -40.0     # peak-to-now drawdown below this => deep decline territory
_KNIFE_RECENT_RET = -10.0   # ...and recent return below this => still falling (falling knife)
_DOWNTREND_RET_6M = -15.0   # structural-window return below this => downtrend
_UPTREND_RET_6M = 40.0      # structural-window return above this => strong uptrend (weak fit)


def _daily_closes(df: pd.DataFrame) -> pd.Series:
    """Resample intraday candles to one close per trading day."""
    s = df.set_index("timestamp")["close"]
    s.index = pd.to_datetime(s.index)
    daily = s.resample("1D").last().dropna()
    return daily


def _trailing_return(daily: pd.Series, ndays: int) -> float | None:
    if len(daily) <= ndays:
        return None
    ref = daily.iloc[-1 - ndays]
    cur = daily.iloc[-1]
    return round((cur - ref) / ref * 100.0, 1) if ref > 0 else None


def evaluate(symbol: str, daily: pd.Series) -> dict:
    last = float(daily.iloc[-1])
    peak = float(daily.max())
    low = float(daily.min())
    returns = {k: _trailing_return(daily, n) for k, n in _WINDOWS.items()}
    dd_from_peak = round((last - peak) / peak * 100.0, 1) if peak > 0 else 0.0
    above_low = round((last - low) / low * 100.0, 1) if low > 0 else 0.0
    n_days = int(len(daily))

    # Structural-trend proxy: prefer the longest available window; recent-momentum
    # proxy: the shortest. Falling back keeps the verdict working on short histories
    # (the cache may only hold a few months) rather than silently returning None.
    ret_struct = next((returns[k] for k in ("12m", "6m", "3m") if returns.get(k) is not None), None)
    struct_win = next((k for k in ("12m", "6m", "3m") if returns.get(k) is not None), None)
    ret_recent = next((returns[k] for k in ("3m", "1m") if returns.get(k) is not None), None)
    confidence = "high" if n_days >= 180 else "medium" if n_days >= 90 else "low"

    reasons: list[str] = []
    verdict = "RANGE_BOUND"

    # Falling knife: deep peak-to-now drawdown AND still declining recently. Drawdown is
    # the primary tell — it survives short histories where trailing returns are missing.
    if dd_from_peak <= _KNIFE_DRAWDOWN and (ret_recent is not None and ret_recent <= _KNIFE_RECENT_RET):
        verdict = "FALLING_KNIFE"
        reasons.append(f"drawdown {dd_from_peak}% from peak and recent ({'3m' if returns.get('3m') is not None else '1m'}) "
                       f"return {ret_recent}% <= -10% — still declining")
    elif ret_struct is not None and ret_struct <= _DOWNTREND_RET_6M:
        verdict = "DOWNTREND"
        reasons.append(f"{struct_win} return {ret_struct}% <= {_DOWNTREND_RET_6M}% "
                       f"(drawdown {dd_from_peak}%, {above_low}% above period low)")
    elif dd_from_peak <= _KNIFE_DRAWDOWN:
        verdict = "WATCH_RECOVERING"
        reasons.append(f"deep drawdown {dd_from_peak}% from peak but recent return {ret_recent}% — "
                       f"beaten down, may be basing or still rolling over; treat with caution")
    elif ret_struct is not None and ret_struct >= _UPTREND_RET_6M:
        verdict = "UPTREND"
        reasons.append(f"{struct_win} return {ret_struct}% >= {_UPTREND_RET_6M}% — strong trend, "
                       f"few local minima (weak fit for mean-reversion, not a loss risk)")
    else:
        reasons.append(f"{struct_win or '1m'} return {ret_struct if ret_struct is not None else returns.get('1m')}%, "
                       f"drawdown {dd_from_peak}% from peak — no strong directional trend")

    if confidence == "low":
        reasons.append(f"LOW CONFIDENCE: only {n_days} trading days of history "
                       f"— run with --fetch for a fuller structural view")

    return {
        "symbol": symbol,
        "as_of": str(daily.index[-1].date()),
        "days_of_history": n_days,
        "confidence": confidence,
        "last_close": round(last, 2),
        "peak_close": round(peak, 2),
        "low_close": round(low, 2),
        "drawdown_from_peak_pct": dd_from_peak,
        "pct_above_period_low": above_low,
        "trailing_returns_pct": returns,
        "structural_verdict": verdict,
        "reasons": reasons,
    }


def main():
    ap = argparse.ArgumentParser(description="Structural falling-knife guard for stock selection")
    ap.add_argument("--symbol", required=True, help="e.g. NSE:RMDRIP")
    ap.add_argument("--fetch", action="store_true", help="Refresh candles from Kite before evaluating")
    ap.add_argument("--from", dest="from_date", default=None, help="History start (default: 18 months back)")
    ap.add_argument("--json", action="store_true", help="Emit JSON only")
    args = ap.parse_args()

    store = Store(config.db_path)
    from_dt = (datetime.strptime(args.from_date, "%Y-%m-%d") if args.from_date
               else datetime.now() - timedelta(days=550))
    to_dt = datetime.now()

    kite = None
    token = 0
    if args.fetch:
        from trader.auth.session import create_kite
        kite = create_kite()
        instruments = kite.instruments("NSE")
        s2t = {f"NSE:{i['tradingsymbol']}": i["instrument_token"] for i in instruments}
        token = s2t.get(args.symbol)
        if token is None:
            print(json.dumps({"symbol": args.symbol, "error": "symbol not found on NSE"}))
            return

    # Use DAILY candles, not the 15-min trading timeframe. A structural multi-month/year
    # guard needs long history; Kite serves years of `day` candles but only a few months of
    # intraday, so 15-min data caps history at ~3-4 months and leaves 6m/12m windows empty.
    df = get_candles(kite, store, token, args.symbol, "day", from_dt, to_dt)
    if df.empty:
        print(json.dumps({"symbol": args.symbol,
                          "error": "no cached daily candles — run with --fetch to pull them"}))
        return

    daily = _daily_closes(df)
    if len(daily) < _WINDOWS["1m"] + 1:
        print(json.dumps({"symbol": args.symbol, "error": f"insufficient history ({len(daily)} days)"}))
        return

    result = evaluate(args.symbol, daily)

    if args.json:
        print(json.dumps(result))
        return

    r = result
    print(f"\n  Trend guard — {r['symbol']}  (as of {r['as_of']}, {r['days_of_history']} trading days, "
          f"confidence={r['confidence']})")
    print(f"  {'-'*60}")
    print(f"  Last close       : {r['last_close']}")
    print(f"  Peak / low        : {r['peak_close']} / {r['low_close']}")
    print(f"  Drawdown from peak: {r['drawdown_from_peak_pct']}%")
    print(f"  Above period low  : {r['pct_above_period_low']}%")
    print(f"  Trailing returns  : " + "  ".join(f"{k}={v}%" for k, v in r['trailing_returns_pct'].items()))
    print(f"\n  >>> {r['structural_verdict']}")
    for reason in r["reasons"]:
        print(f"      - {reason}")
    print()


if __name__ == "__main__":
    main()
