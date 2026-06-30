"""
Long-term conviction scorecard — a structured evidence panel for studying a stock as a
multi-year buy-and-hold candidate (NOT the FVM trading strategy, which is a separate,
timing-oriented engine and a Milestone-A FAIL).

This is decision support for discretionary long-term investing. It maps the criteria that
serious long-term investors actually use — Buffett/Munger's "four M's" (Meaning, Moat,
Management, Margin of safety), the quant quality screen (ROCE/ROE, low debt, earnings backed
by cash, consistent through-cycle growth), and Munger's inversion ("what would guarantee
failure?") — onto the point-in-time fundamentals we already hold (Trendlyne fincsv + Screener
shareholding). Each criterion gets a PASS / WATCH / FAIL / NA verdict, the underlying value,
and a plain-English note saying why it matters. The output is evidence to reason over, not a
buy/sell call — the qualitative parts (does the moat last? is management honest?) are yours.

Pure and testable: takes a store + symbol + asof (+ optional pre-computed price / veto /
technical so the study aggregator doesn't recompute them). No Streamlit, no I/O beyond the store.

References (how long-term investors frame it):
- Rule One "4 M's": Meaning, Moat, Management, Margin of safety.
- Buffett quality: high ROE/ROCE, low debt, consistent earnings through a full cycle, wise
  capital allocation.
- Munger inversion red flags: overleverage, aggressive accounting (profit not backed by cash),
  customer concentration, promoter pledging/selling, promotional management.
- India quant screen: ROCE>15%, ROE>15%, D/E<1, positive & growing cash flow, promoter
  holding high & unpledged, steady revenue+profit growth.
"""

from trader.fvm import fields as F
from trader.fvm.factors import _latest, _series, slope

PASS, WATCH, FAIL, NA = "PASS", "WATCH", "FAIL", "NA"


def _verdict(value, good, ok, higher_better=True) -> str:
    """Three-band verdict. `good` clears PASS, `ok` clears WATCH, else FAIL."""
    if value is None:
        return NA
    if higher_better:
        if value >= good:
            return PASS
        if value >= ok:
            return WATCH
        return FAIL
    else:  # lower is better
        if value <= good:
            return PASS
        if value <= ok:
            return WATCH
        return FAIL


def _fmt(value, suffix="", nd=1) -> str:
    return "—" if value is None else f"{value:.{nd}f}{suffix}"


def _crit(label, raw, verdict, note, value=None) -> dict:
    return {"label": label, "raw": raw, "verdict": verdict,
            "note": note, "value": value if value is not None else _fmt(raw)}


def _annual_latest(store, symbol, spec, asof, basis):
    return _latest(_series(store, symbol, spec, asof, basis))


def _annual_vals(store, symbol, spec, asof, basis):
    return [v for _, v in _series(store, symbol, spec, asof, basis)]


# ------------------------------------------------------------------ #
# Section builders                                                    #
# ------------------------------------------------------------------ #

def _quality_section(store, symbol, asof, basis) -> dict:
    """Moat proxy — does the business earn high returns on capital, durably?"""
    roce = _annual_latest(store, symbol, F.ROCE_A, asof, basis)
    roe = _annual_latest(store, symbol, F.ROE_A, asof, basis)
    roce_hist = _annual_vals(store, symbol, F.ROCE_A, asof, basis)
    opm_vals = _annual_vals(store, symbol, F.NET_PROFIT_MARGIN_A, asof, basis)
    roce_trend = slope(roce_hist[-4:]) if len(roce_hist) >= 2 else None
    margin_trend = slope(opm_vals[-4:]) if len(opm_vals) >= 2 else None

    crits = [
        _crit("ROCE (return on capital)", roce, _verdict(roce, 15, 10),
              "Capital efficiency. >15% = a genuinely high-quality business; the clearest "
              "single quant proxy for a moat.", _fmt(roce, "%")),
        _crit("ROE (return on equity)", roe, _verdict(roe, 15, 10),
              ">15% means shareholder capital compounds well. Cross-check vs ROCE — a big "
              "ROE>ROCE gap is usually leverage, not quality.", _fmt(roe, "%")),
        _crit("ROCE trend", roce_trend,
              PASS if (roce_trend is not None and roce_trend >= -0.5) else (NA if roce_trend is None else FAIL),
              "Stable-or-rising returns = a widening or holding moat. Steadily falling ROCE "
              "is an early erosion signal.", "rising" if (roce_trend or 0) > 0.5 else ("stable" if roce_trend is not None and roce_trend >= -0.5 else ("falling" if roce_trend is not None else "—"))),
        _crit("Net-margin trend", margin_trend,
              PASS if (margin_trend is not None and margin_trend >= -0.3) else (NA if margin_trend is None else WATCH),
              "Expanding margins = pricing power / operating leverage. Contracting margins "
              "warrant a 'why?'.", "expanding" if (margin_trend or 0) > 0.3 else ("stable" if margin_trend is not None and margin_trend >= -0.3 else ("contracting" if margin_trend is not None else "—"))),
    ]
    return {"name": "Quality & Returns", "tag": "Moat", "criteria": crits}


def _growth_section(store, symbol, asof, basis) -> dict:
    """Is the business actually getting bigger, consistently?"""
    rev5 = _annual_latest(store, symbol, F.REVENUE_5Y_A, asof, basis)
    rev3 = _annual_latest(store, symbol, F.REVENUE_3Y_A, asof, basis)
    np5 = _annual_latest(store, symbol, F.NET_PROFIT_5Y_A, asof, basis)
    np3 = _annual_latest(store, symbol, F.NET_PROFIT_3Y_A, asof, basis)
    accel = None if (np3 is None or np5 is None) else np3 - np5  # 3yr hotter than 5yr = accelerating

    crits = [
        _crit("Revenue CAGR (5yr)", rev5, _verdict(rev5, 12, 6),
              "Topline durability. >12% is strong, 6-12% steady, <6% a slow grower (fine if "
              "high-ROCE + cheap, but know it).", _fmt(rev5, "%")),
        _crit("Profit CAGR (5yr)", np5, _verdict(np5, 12, 6),
              "The number that compounds your capital. Should roughly track or beat revenue "
              "growth over time.", _fmt(np5, "%")),
        _crit("Growth momentum (3yr vs 5yr)", accel,
              PASS if (accel is not None and accel >= 0) else (NA if accel is None else WATCH),
              "3yr profit CAGR above the 5yr = accelerating; below = decelerating. Direction "
              "matters more than the level.", "accelerating" if (accel or 0) >= 0 else ("decelerating" if accel is not None else "—")),
        _crit("Profit CAGR (3yr)", np3, _verdict(np3, 12, 6),
              "Recent compounding — confirms the 5yr number isn't living off an old boom.",
              _fmt(np3, "%")),
    ]
    return {"name": "Growth", "tag": "Meaning", "criteria": crits}


def _balance_section(store, symbol, asof, basis) -> dict:
    """Financial strength — can it survive a downturn and is profit real cash?"""
    de = _annual_latest(store, symbol, F.DE_A, asof, basis)
    icov = _annual_latest(store, symbol, F.INT_COVERAGE_A, asof, basis)
    cfo = _annual_latest(store, symbol, F.CFO_A, asof, basis)
    npa = _annual_latest(store, symbol, F.NET_PROFIT_A, asof, basis)
    cfo_np = (cfo / npa) if (cfo is not None and npa not in (None, 0)) else None
    cfi = _annual_latest(store, symbol, F.CFI_A, asof, basis)
    fcf = (cfo + cfi) if (cfo is not None and cfi is not None) else None  # rough: CFO + investing

    crits = [
        _crit("Debt / Equity", de, _verdict(de, 0.5, 1.0, higher_better=False),
              "<0.5 = conservatively financed, survives downturns. >1 means leverage can sink "
              "it in a bad year — Munger's #1 'guaranteed failure'.", _fmt(de, "x", 2)),
        _crit("Interest coverage", icov, _verdict(icov, 4, 2),
              "EBIT / interest. >4x = debt is comfortably serviced; <2x is fragile.",
              _fmt(icov, "x")),
        _crit("Earnings quality (CFO / PAT)", cfo_np, _verdict(cfo_np, 0.8, 0.5),
              "Is reported profit backed by real operating cash? >0.8 is healthy; persistently "
              "low is the classic aggressive-accounting red flag (Munger inversion).",
              _fmt(cfo_np, "x", 2)),
        _crit("Free cash flow (≈ CFO+investing)", fcf,
              PASS if (fcf is not None and fcf > 0) else (NA if fcf is None else WATCH),
              "Rough FCF. Positive = self-funding (can pay dividends / cut debt / reinvest "
              "without dilution). Negative can be fine for a heavy-capex grower — check why.",
              "positive" if (fcf or 0) > 0 else ("negative" if fcf is not None else "—")),
    ]
    return {"name": "Balance sheet & Cash", "tag": "Survival", "criteria": crits}


def _ownership_section(store, symbol, asof) -> dict:
    """Management & governance — skin in the game, no looting, institutions buying."""
    prom = store.read_shareholding_asof(symbol, F.SH_PROMOTER, asof)
    pledge = store.read_shareholding_asof(symbol, F.SH_PLEDGE, asof)
    fii = store.read_shareholding_asof(symbol, F.SH_FII, asof)
    dii = store.read_shareholding_asof(symbol, F.SH_DII, asof)
    div_payout = _annual_latest(store, symbol, F.DIV_PAYOUT_A, asof, "consolidated")

    def _last(d):
        vals = [v for _, v in sorted(d.items()) if v is not None]
        return vals[-1] if vals else None

    def _trend(d):
        vals = [v for _, v in sorted(d.items()) if v is not None]
        return slope(vals[-4:]) if len(vals) >= 2 else None

    prom_now, prom_tr = _last(prom), _trend(prom)
    pledge_now = _last(pledge)
    inst_tr = None
    if _trend(fii) is not None or _trend(dii) is not None:
        inst_tr = (_trend(fii) or 0) + (_trend(dii) or 0)

    crits = [
        _crit("Promoter holding", prom_now, _verdict(prom_now, 50, 35),
              "High promoter ownership = aligned skin in the game. >50% strong; very low "
              "holdings raise pump/governance risk.", _fmt(prom_now, "%")),
        _crit("Promoter holding trend", prom_tr,
              PASS if (prom_tr is not None and prom_tr >= -0.3) else (NA if prom_tr is None else FAIL),
              "Promoters STEADILY SELLING is a serious negative — they know the business best. "
              "Rising/stable is reassuring.", "buying/stable" if (prom_tr is not None and prom_tr >= -0.3) else ("selling" if prom_tr is not None else "—")),
        _crit("Promoter pledge", pledge_now, _verdict(pledge_now, 0.5, 10, higher_better=False),
              "Pledged promoter shares = leverage at the owner level; a forced-sale time bomb. "
              "Zero is what you want (Munger inversion).", _fmt(pledge_now, "%")),
        _crit("Institutional trend (FII+DII)", inst_tr,
              PASS if (inst_tr is not None and inst_tr > 0) else (NA if inst_tr is None else WATCH),
              "Smart money accumulating is a soft positive; steady selling is worth a look.",
              "accumulating" if (inst_tr or 0) > 0 else ("reducing" if inst_tr is not None else "—")),
        _crit("Dividend payout", div_payout,
              PASS if (div_payout is not None and div_payout > 5) else (NA if div_payout is None else WATCH),
              "A consistent dividend signals real cash and capital-return discipline. Zero is "
              "fine for a high-ROCE reinvester, a worry for a mature low-growth one.",
              _fmt(div_payout, "%")),
    ]
    return {"name": "Management & Ownership", "tag": "Management", "criteria": crits}


def _valuation_section(store, symbol, asof, price, daily, basis) -> dict:
    """Margin of safety — am I paying a sane price? (bands are deliberately soft / sector-blind)."""
    from trader.fvm.factors import pillar2_factors, ttm_eps
    p2 = pillar2_factors(store, symbol, asof, price=price, basis=basis)
    eps = ttm_eps(store, symbol, asof, basis)
    pe = (price / eps) if (price and eps and eps > 0) else None
    ev_ebitda = p2.get("ev_ebitda")
    peg = p2.get("peg")

    # where in the trailing 1yr price range (margin-of-safety proxy)
    range_pos = None
    if daily is not None and not daily.empty and price:
        recent = daily.tail(252)
        lo, hi = recent["low"].min(), recent["high"].max()
        if hi > lo:
            range_pos = 100 * (price - lo) / (hi - lo)

    crits = [
        _crit("P/E (TTM)", pe, _verdict(pe, 25, 50, higher_better=False),
              "Soft, sector-blind band. Pair with growth (a 30 P/E on 25% growth ≠ a 30 P/E on "
              "5%). Compare to the stock's OWN history and its peers.", _fmt(pe, "x")),
        _crit("EV / EBITDA", ev_ebitda, _verdict(ev_ebitda, 15, 25, higher_better=False),
              "Capital-structure-neutral valuation. Lower = cheaper; very high needs exceptional "
              "growth to justify.", _fmt(ev_ebitda, "x")),
        _crit("PEG (trailing)", peg, _verdict(peg, 1.0, 2.0, higher_better=False),
              "Price/earnings-to-growth. <1 classically attractive, >2 pricey. Trailing growth "
              "only — forward estimates sharpen this.", _fmt(peg, "x", 2)),
        _crit("Position in 1yr range", range_pos, _verdict(range_pos, 50, 80, higher_better=False),
              "Near 52w lows = more margin of safety (if the thesis holds); buying at the top of "
              "the range leaves less room for error.", _fmt(range_pos, "%", 0)),
    ]
    return {"name": "Valuation & Margin of Safety", "tag": "Margin of safety", "criteria": crits}


# ------------------------------------------------------------------ #
# Red flags (Munger inversion) — pulls vetoes + ownership/technical   #
# ------------------------------------------------------------------ #

_FLAG_EXPLAIN = {
    "cfo_negative_profit_positive": "Profit positive but operating cash flow negative — classic "
                                    "aggressive-accounting / non-cash-profit red flag.",
    "manufactured_earnings": "Revenue fell while profit jumped — earnings may be manufactured "
                             "(one-offs, accounting), not operational.",
    "promoter_dumping": "Promoters reduced their stake sharply — owners cashing out.",
    "high_pledge": "High promoter pledge — owner-level leverage, forced-sale risk.",
    "insufficient_data": "Too little fundamental history to judge — study manually.",
}


def red_flags(store, symbol, asof, veto=None, technical=None) -> list[dict]:
    """Inversion view — the things that 'guarantee failure'. Pulls the FVM vetoes plus a few
    ownership/technical checks, each with a plain-English explanation."""
    flags = []
    if veto is not None:
        passed, reasons = veto
        for r in reasons:
            flags.append({"flag": r, "note": _FLAG_EXPLAIN.get(r, r)})
    if technical is not None and technical.get("extension_vetoed"):
        flags.append({"flag": "parabolic_extension",
                      "note": "Price is parabolically extended above trend — poor entry, high "
                              "mean-reversion risk even on a good business."})
    pledge = store.read_shareholding_asof(symbol, F.SH_PLEDGE, asof)
    pv = [v for _, v in sorted(pledge.items()) if v is not None]
    if pv and pv[-1] is not None and pv[-1] > 10 and not any(f["flag"] == "high_pledge" for f in flags):
        flags.append({"flag": "promoter_pledge",
                      "note": f"Promoter pledge at {pv[-1]:.0f}% — owner-level leverage / forced-sale risk."})
    return flags


# ------------------------------------------------------------------ #
# Top-level                                                           #
# ------------------------------------------------------------------ #

def scorecard(store, symbol, asof, price=None, daily=None, veto=None, technical=None,
              basis="consolidated") -> dict:
    """The full long-term conviction scorecard for one name as of `asof`.

    Returns {symbol, asof, sections[], red_flags[], summary{pass/watch/fail/na, headline}}.
    Evidence, not a recommendation — the qualitative moat/management judgment is the user's.
    """
    symbol = symbol.upper()
    sections = [
        _quality_section(store, symbol, asof, basis),
        _growth_section(store, symbol, asof, basis),
        _balance_section(store, symbol, asof, basis),
        _ownership_section(store, symbol, asof),
        _valuation_section(store, symbol, asof, price, daily, basis),
    ]
    flags = red_flags(store, symbol, asof, veto=veto, technical=technical)

    tally = {PASS: 0, WATCH: 0, FAIL: 0, NA: 0}
    for sec in sections:
        for c in sec["criteria"]:
            tally[c["verdict"]] += 1

    scored = tally[PASS] + tally[WATCH] + tally[FAIL]
    pass_rate = (tally[PASS] / scored) if scored else 0.0
    if not scored:
        headline = "Not enough data to judge — study manually."
    elif tally[FAIL] == 0 and pass_rate >= 0.6:
        headline = "Strong long-term profile — quality, balance sheet and ownership mostly clear."
    elif pass_rate >= 0.5 and tally[FAIL] <= 2:
        headline = "Solid but mixed — real strengths, a few things to dig into before conviction."
    elif tally[FAIL] >= scored * 0.4:
        headline = "Weak on the fundamentals that matter for a multi-year hold — high bar to clear."
    else:
        headline = "Mixed — strengths offset by clear concerns; the flagged items decide it."
    if flags:
        headline += f"  ⚠ {len(flags)} red flag(s) — read the inversion panel."

    return {
        "symbol": symbol, "asof": asof,
        "sections": sections, "red_flags": flags,
        "summary": {"pass": tally[PASS], "watch": tally[WATCH], "fail": tally[FAIL],
                    "na": tally[NA], "pass_rate": round(pass_rate, 2), "headline": headline},
    }
