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

# Criterion tiers — a FAIL on promoter pledge is not the same as a WATCH on dividend payout.
# DEALBREAKER = survival / fraud-risk items (Munger's "guaranteed failure" list); CORE = the
# quality/growth/valuation spine; SOFT = supporting colour. The headline weighs these.
DEALBREAKER, CORE, SOFT = "dealbreaker", "core", "soft"
_TIER_W = {DEALBREAKER: 3, CORE: 2, SOFT: 1}


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


def _crit(label, raw, verdict, note, value=None, tier=CORE) -> dict:
    return {"label": label, "raw": raw, "verdict": verdict, "tier": tier,
            "note": note, "value": value if value is not None else _fmt(raw)}


def _annual_latest(store, symbol, spec, asof, basis):
    return _latest(_series(store, symbol, spec, asof, basis))


# ------------------------------------------------------------------ #
# Valuation-context helpers (own-history percentile, reverse-DCF)      #
# ------------------------------------------------------------------ #

def _quarter_ends(asof: str, n: int) -> list[str]:
    """Last `n` calendar quarter-end dates on/before `asof`, ascending ISO dates."""
    import calendar
    y, m = int(asof[:4]), int(asof[5:7])
    qm = (m // 3) * 3
    if qm == 0:
        y, qm = y - 1, 12
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{qm:02d}-{calendar.monthrange(y, qm)[1]:02d}")
        qm -= 3
        if qm == 0:
            y, qm = y - 1, 12
    return out[::-1]


def pe_history(store, symbol, asof, daily, years: int = 5,
               basis="consolidated") -> list[tuple[str, float]]:
    """PIT P/E at each quarter-end over the trailing `years`: close on/before the
    quarter-end (from `daily`) over TTM EPS as knowable then. Only positive-EPS points.
    This is what makes "cheap/expensive vs its OWN history" computable with zero new data."""
    if daily is None or getattr(daily, "empty", True):
        return []
    from trader.fvm.factors import ttm_eps
    import pandas as pd
    ts = pd.to_datetime(daily["timestamp"])
    closes = daily["close"].astype(float)
    out = []
    for qe in _quarter_ends(asof, years * 4):
        mask = ts <= pd.Timestamp(qe)
        if not mask.any():
            continue
        price = closes[mask].iloc[-1]
        eps = ttm_eps(store, symbol, qe, basis)
        if eps is not None and eps > 0 and price > 0:
            out.append((qe, price / eps))
    return out


def percentile_rank(value: float, values: list[float]) -> float | None:
    """Percentile of `value` within `values` (0 = cheapest ever, 100 = richest ever)."""
    if value is None or not values:
        return None
    return 100.0 * sum(1 for v in values if v < value) / len(values)


def _fair_pe(g: float, r: float, years: int, terminal_pe: float) -> float:
    pv = sum((1 + g) ** t / (1 + r) ** t for t in range(1, years + 1))
    return pv + terminal_pe * (1 + g) ** years / (1 + r) ** years


def implied_growth_rate(pe: float | None, r: float = 0.125, years: int = 10,
                        terminal_pe: float = 15.0) -> float | None:
    """Reverse-DCF: the constant earnings CAGR over `years` that justifies the current
    P/E at discount rate `r` with a `terminal_pe` exit. Bisection; returns a fraction
    clamped to [-0.5, 1.0]. The teaching number: "what growth is priced in?"."""
    if pe is None or pe <= 0:
        return None
    lo, hi = -0.5, 1.0
    if _fair_pe(lo, r, years, terminal_pe) >= pe:
        return lo
    if _fair_pe(hi, r, years, terminal_pe) <= pe:
        return hi
    for _ in range(60):
        mid = (lo + hi) / 2
        if _fair_pe(mid, r, years, terminal_pe) < pe:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


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
              "warrant a 'why?'.", "expanding" if (margin_trend or 0) > 0.3 else ("stable" if margin_trend is not None and margin_trend >= -0.3 else ("contracting" if margin_trend is not None else "—")),
              tier=SOFT),
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
              "matters more than the level.", "accelerating" if (accel or 0) >= 0 else ("decelerating" if accel is not None else "—"),
              tier=SOFT),
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

    # FCF ≈ CFO − capex, capex ≈ ΔFixedAssets + depreciation (net-block delta understates
    # capex by the year's D&A). Falls back to the cruder CFO + CFI when the fixed-asset
    # history is missing — CFI also nets out treasury/MF purchases, so it's noisier.
    fa_vals = _annual_vals(store, symbol, F.FIXED_ASSETS_A, asof, basis)
    dep = _annual_latest(store, symbol, F.DEPRECIATION_A, asof, basis)
    fcf, fcf_label = None, "Free cash flow (≈ CFO−capex)"
    if cfo is not None and len(fa_vals) >= 2:
        capex = max(fa_vals[-1] - fa_vals[-2] + (dep or 0.0), 0.0)
        fcf = cfo - capex
    else:
        cfi = _annual_latest(store, symbol, F.CFI_A, asof, basis)
        fcf_label = "Free cash flow (≈ CFO+investing)"
        fcf = (cfo + cfi) if (cfo is not None and cfi is not None) else None

    crits = [
        _crit("Debt / Equity", de, _verdict(de, 0.5, 1.0, higher_better=False),
              "<0.5 = conservatively financed, survives downturns. >1 means leverage can sink "
              "it in a bad year — Munger's #1 'guaranteed failure'.", _fmt(de, "x", 2),
              tier=DEALBREAKER),
        _crit("Interest coverage", icov, _verdict(icov, 4, 2),
              "EBIT / interest. >4x = debt is comfortably serviced; <2x is fragile.",
              _fmt(icov, "x")),
        _crit("Earnings quality (CFO / PAT)", cfo_np, _verdict(cfo_np, 0.8, 0.5),
              "Is reported profit backed by real operating cash? >0.8 is healthy; persistently "
              "low is the classic aggressive-accounting red flag (Munger inversion).",
              _fmt(cfo_np, "x", 2), tier=DEALBREAKER),
        _crit(fcf_label, fcf,
              PASS if (fcf is not None and fcf > 0) else (NA if fcf is None else WATCH),
              "Rough FCF. Positive = self-funding (can pay dividends / cut debt / reinvest "
              "without dilution). Negative can be fine for a heavy-capex grower — check why.",
              "positive" if (fcf or 0) > 0 else ("negative" if fcf is not None else "—"),
              tier=SOFT),
    ]
    return {"name": "Balance sheet & Cash", "tag": "Survival", "criteria": crits}


def _cagr3(vals: list[float]) -> float | None:
    """3-yr CAGR from the last 4 annual values (needs positive endpoints)."""
    if len(vals) >= 4 and vals[-4] > 0 and vals[-1] > 0:
        return (vals[-1] / vals[-4]) ** (1 / 3) - 1
    return None


def _working_capital_section(store, symbol, asof, basis) -> dict:
    """Accrual quality — is growth turning into cash, or piling up as receivables and
    inventory? The classic early-warning metrics for channel stuffing and stress."""
    recv = dict(_series(store, symbol, F.TRADE_RECEIVABLES_A, asof, basis))
    rev = dict(_series(store, symbol, F.TOTAL_REVENUE_A, asof, basis))

    dd_vals = [365.0 * recv[p] / rev[p] for p in sorted(recv) if rev.get(p)]
    dd_now = dd_vals[-1] if dd_vals else None
    dd_tr = slope(dd_vals[-4:]) if len(dd_vals) >= 2 else None

    inv_vals = [v for _, v in _series(store, symbol, F.INVENTORY_TURNOVER_A, asof, basis)]
    inv_rel = None
    if len(inv_vals) >= 2:
        recent = inv_vals[-4:]
        mean = sum(recent) / len(recent)
        if mean:
            inv_rel = slope(recent) / abs(mean)  # fraction/yr; falling = inventory piling up

    wc = dict(_series(store, symbol, F.WORKING_CAPITAL_A, asof, basis))
    wcr_vals = [100.0 * wc[p] / rev[p] for p in sorted(wc) if rev.get(p)]
    wcr_now = wcr_vals[-1] if wcr_vals else None
    wcr_tr = slope(wcr_vals[-4:]) if len(wcr_vals) >= 2 else None

    recv_g = _cagr3([recv[p] for p in sorted(recv)])
    rev_g = _cagr3([rev[p] for p in sorted(rev)])
    outrun = None
    if recv_g is not None and rev_g is not None:
        outrun = rev_g > 0 and recv_g > 1.5 * rev_g

    crits = [
        _crit("Debtor days trend", dd_tr, _verdict(dd_tr, 5, 15, higher_better=False),
              "Receivables ÷ revenue × 365, per year. The LEVEL is industry-specific; the "
              "TREND isn't — steadily rising debtor days means sales are being booked faster "
              "than customers pay (channel stuffing / weakening bargaining power).",
              "—" if dd_tr is None else f"{dd_now:.0f} days ({dd_tr:+.0f}/yr)"),
        _crit("Receivables vs revenue (3yr)", None if outrun is None else (1.0 if outrun else 0.0),
              NA if outrun is None else (FAIL if outrun else PASS),
              "Receivables compounding much faster than revenue is the single most reliable "
              "accrual red flag — reported growth that customers haven't paid for.",
              "—" if outrun is None else
              f"recv {recv_g * 100:+.0f}%/yr vs rev {rev_g * 100:+.0f}%/yr",
              tier=DEALBREAKER),
        _crit("Inventory turnover trend", inv_rel,
              _verdict(inv_rel, -0.05, -0.15),
              "Falling turnover = inventory piling up faster than it sells — demand fading "
              "or obsolescence building. Stable/rising is what you want.",
              "—" if inv_rel is None else f"{inv_rel * 100:+.0f}%/yr", tier=SOFT),
        _crit("Working-capital intensity trend", wcr_tr,
              _verdict(wcr_tr, 2, 6, higher_better=False),
              "Working capital as % of revenue, per year. Rising intensity means each rupee "
              "of growth traps more cash — the gap between profit and FCF widens.",
              "—" if wcr_tr is None else f"{wcr_now:.0f}% of revenue ({wcr_tr:+.1f}pp/yr)"),
    ]
    return {"name": "Working Capital & Accruals", "tag": "Cash conversion", "criteria": crits}


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
              "Zero is what you want (Munger inversion).", _fmt(pledge_now, "%"),
              tier=DEALBREAKER),
        _crit("Institutional trend (FII+DII)", inst_tr,
              PASS if (inst_tr is not None and inst_tr > 0) else (NA if inst_tr is None else WATCH),
              "Smart money accumulating is a soft positive; steady selling is worth a look.",
              "accumulating" if (inst_tr or 0) > 0 else ("reducing" if inst_tr is not None else "—"),
              tier=SOFT),
        _crit("Dividend payout", div_payout,
              PASS if (div_payout is not None and div_payout > 5) else (NA if div_payout is None else WATCH),
              "A consistent dividend signals real cash and capital-return discipline. Zero is "
              "fine for a high-ROCE reinvester, a worry for a mature low-growth one.",
              _fmt(div_payout, "%"), tier=SOFT),
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

    # --- context rows: vs OWN history + what the price implies ---
    pe_hist = pe_history(store, symbol, asof, daily, basis=basis)
    pe_pctile = None
    if pe is not None and len(pe_hist) >= 8:  # need a real history to rank against
        pe_pctile = percentile_rank(pe, [v for _, v in pe_hist])

    ev_hist = _annual_vals(store, symbol, F.EV_EBITDA_A, asof, basis)
    ev_pctile = None
    if ev_ebitda is not None and len(ev_hist) >= 4:
        ev_pctile = percentile_rank(ev_ebitda, ev_hist)

    ig = implied_growth_rate(pe)
    np5 = _annual_latest(store, symbol, F.NET_PROFIT_5Y_A, asof, basis)
    ig_pct = None if ig is None else ig * 100.0
    if ig_pct is None or np5 is None:
        ig_verdict, ig_value = NA, "—"
    else:
        if ig_pct <= np5:
            ig_verdict = PASS
        elif ig_pct <= max(np5 * 1.5, np5 + 3):
            ig_verdict = WATCH
        else:
            ig_verdict = FAIL
        ig_value = f"{ig_pct:.0f}% priced vs {np5:.0f}% delivered"

    crits = [
        _crit("P/E vs own 5-yr history", pe_pctile,
              _verdict(pe_pctile, 40, 75, higher_better=False),
              "Percentile of today's P/E within the stock's OWN trailing 5-yr quarterly P/E "
              "band — the band that actually means something (sector-blind absolutes don't). "
              "Low percentile = cheap for THIS stock; high = priced for perfection.",
              "—" if pe_pctile is None else f"{pe_pctile:.0f}th pctile (n={len(pe_hist)})",
              tier=CORE),
        _crit("EV/EBITDA vs own history", ev_pctile,
              _verdict(ev_pctile, 40, 75, higher_better=False),
              "Same idea, capital-structure-neutral: where today's EV/EBITDA sits in the "
              "stock's own annual history.",
              "—" if ev_pctile is None else f"{ev_pctile:.0f}th pctile (n={len(ev_hist)})",
              tier=CORE),
        _crit("Implied growth (reverse-DCF)", ig_pct, ig_verdict,
              "The earnings CAGR the current P/E is quietly assuming (10 yrs, 12.5% discount, "
              "15x exit multiple), next to what the business actually delivered over 5 yrs. "
              "Paying for growth far above the delivered rate means the thesis needs "
              "acceleration that hasn't happened yet.", ig_value, tier=CORE),
        _crit("P/E (TTM)", pe, _verdict(pe, 25, 50, higher_better=False),
              "Soft, sector-blind band. Pair with growth (a 30 P/E on 25% growth ≠ a 30 P/E on "
              "5%). The own-history percentile above is the sharper read.", _fmt(pe, "x"),
              tier=SOFT),
        _crit("EV / EBITDA", ev_ebitda, _verdict(ev_ebitda, 15, 25, higher_better=False),
              "Capital-structure-neutral valuation. Lower = cheaper; very high needs exceptional "
              "growth to justify.", _fmt(ev_ebitda, "x"), tier=SOFT),
        _crit("PEG (trailing)", peg, _verdict(peg, 1.0, 2.0, higher_better=False),
              "Price/earnings-to-growth. <1 classically attractive, >2 pricey. Trailing growth "
              "only — forward estimates sharpen this.", _fmt(peg, "x", 2), tier=SOFT),
        _crit("Position in 1yr range", range_pos, _verdict(range_pos, 50, 80, higher_better=False),
              "Near 52w lows = more margin of safety (if the thesis holds); buying at the top of "
              "the range leaves less room for error.", _fmt(range_pos, "%", 0), tier=SOFT),
    ]
    return {"name": "Valuation & Margin of Safety", "tag": "Margin of safety", "criteria": crits}


def _snapshot_section(snap: dict) -> dict:
    """Market intelligence from the weekly Trendlyne Data-Downloader snapshot — fields the
    PIT store has no other source for (Piotroski, DVM, monthly institutional flow, pledge
    with full-market coverage). Snapshot-dated, not PIT-deep: colour, not history."""
    g = snap.get
    dvm_class = g("dvm_class")
    if dvm_class is None:
        dvm_v = NA
    elif "Strong Performer" in dvm_class:
        dvm_v = PASS
    elif any(w in dvm_class for w in ("Trap", "Falling", "Weak", "Underperformer")):
        dvm_v = FAIL
    else:
        dvm_v = WATCH
    inst_flow = None
    if g("mf_chg_qoq") is not None or g("fii_chg_qoq") is not None:
        inst_flow = (g("mf_chg_qoq") or 0) + (g("fii_chg_qoq") or 0)

    crits = [
        _crit("Piotroski score", g("piotroski"), _verdict(g("piotroski"), 7, 5),
              "9-point accounting-quality checklist (profitability, leverage, efficiency). "
              "≥7 = clean; ≤3 has historically flagged deteriorating financials.",
              _fmt(g("piotroski"), "/9", 0)),
        _crit("Trendlyne Durability", g("durability"), _verdict(g("durability"), 65, 50),
              "Trendlyne's long-horizon quality composite — an independent second opinion "
              "on the moat/balance-sheet read above.", _fmt(g("durability"), "", 0)),
        _crit("DVM classification", None if dvm_class is None else 1.0, dvm_v,
              "Trendlyne's combined Durability-Valuation-Momentum bucket. 'Momentum Trap' / "
              "'Falling Comet' style labels are the caution ones.", dvm_class or "—",
              tier=SOFT),
        _crit("Institutional flow (MF+FII QoQ)", inst_flow,
              PASS if (inst_flow is not None and inst_flow > 0) else
              (NA if inst_flow is None else (FAIL if inst_flow < -1.5 else WATCH)),
              "Combined mutual-fund + FII holding change last quarter. Sustained exit "
              "(<−1.5pp) is worth understanding before buying.",
              "—" if inst_flow is None else f"{inst_flow:+.2f}pp", tier=SOFT),
        _crit("Promoter pledge (snapshot)", g("pledge"),
              _verdict(g("pledge"), 0.5, 10, higher_better=False),
              "Full-market pledge coverage from the weekly export — catches names whose "
              "Screener shareholding history is missing.", _fmt(g("pledge"), "%"),
              tier=DEALBREAKER),
        _crit("PE vs own history (Trendlyne)", g("pct_days_below_pe"),
              _verdict(g("pct_days_below_pe"), 40, 75, higher_better=False),
              "% of trading days the stock closed below today's PE — Trendlyne's version of "
              "the own-history percentile, computed on daily data (sharper than our "
              "quarter-end series).", _fmt(g("pct_days_below_pe"), "%", 0), tier=SOFT),
    ]
    return {"name": "Market Intelligence (Trendlyne snapshot)",
            "tag": f"Snapshot {snap.get('as_of', '')}", "criteria": crits}


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
    "receivables_outrunning_revenue": "Receivables compounding much faster than revenue — "
                                      "reported growth customers haven't paid for (classic "
                                      "channel-stuffing signature).",
}


def red_flags(store, symbol, asof, veto=None, technical=None,
              basis="consolidated") -> list[dict]:
    """Inversion view — the things that 'guarantee failure'. Pulls the FVM vetoes plus a few
    ownership/accrual/technical checks, each with a plain-English explanation."""
    flags = []
    recv_vals = [v for _, v in _series(store, symbol, F.TRADE_RECEIVABLES_A, asof, basis)]
    rev_vals = [v for _, v in _series(store, symbol, F.TOTAL_REVENUE_A, asof, basis)]
    recv_g, rev_g = _cagr3(recv_vals), _cagr3(rev_vals)
    if recv_g is not None and rev_g is not None and rev_g > 0 and recv_g > 1.5 * rev_g:
        flags.append({"flag": "receivables_outrunning_revenue",
                      "note": _FLAG_EXPLAIN["receivables_outrunning_revenue"] +
                      f" (recv {recv_g * 100:+.0f}%/yr vs rev {rev_g * 100:+.0f}%/yr)"})
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
              basis="consolidated", snapshot=None) -> dict:
    """The full long-term conviction scorecard for one name as of `asof`.

    `snapshot` (optional) is a tl_snapshot row (trader.fvm.data.snapshot.read_snapshot) —
    adds a Market-Intelligence section (Piotroski/DVM/pledge/inst-flow). Pass it only for
    current-date studies; the PIT replay must not see it.

    Returns {symbol, asof, sections[], red_flags[], summary{pass/watch/fail/na, headline}}.
    Evidence, not a recommendation — the qualitative moat/management judgment is the user's.
    """
    symbol = symbol.upper()
    sections = [
        _quality_section(store, symbol, asof, basis),
        _growth_section(store, symbol, asof, basis),
        _balance_section(store, symbol, asof, basis),
        _working_capital_section(store, symbol, asof, basis),
        _ownership_section(store, symbol, asof),
        _valuation_section(store, symbol, asof, price, daily, basis),
    ]
    if snapshot:
        sections.append(_snapshot_section(snapshot))
    flags = red_flags(store, symbol, asof, veto=veto, technical=technical, basis=basis)

    tally = {PASS: 0, WATCH: 0, FAIL: 0, NA: 0}
    scored_w = pass_w = fail_w = 0
    db_fails = []
    for sec in sections:
        for c in sec["criteria"]:
            tally[c["verdict"]] += 1
            if c["verdict"] == NA:
                continue
            w = _TIER_W.get(c.get("tier", CORE), _TIER_W[CORE])
            scored_w += w
            if c["verdict"] == PASS:
                pass_w += w
            elif c["verdict"] == FAIL:
                fail_w += w
                if c.get("tier") == DEALBREAKER:
                    db_fails.append(c["label"])

    scored = tally[PASS] + tally[WATCH] + tally[FAIL]
    pass_rate = (pass_w / scored_w) if scored_w else 0.0
    fail_rate = (fail_w / scored_w) if scored_w else 0.0
    if not scored:
        headline = "Not enough data to judge — study manually."
    elif db_fails:
        headline = (f"Dealbreaker risk — {', '.join(db_fails)} FAIL. Survival/integrity items "
                    "outweigh everything else here; clear these before anything else matters.")
    elif tally[FAIL] == 0 and pass_rate >= 0.6:
        headline = "Strong long-term profile — quality, balance sheet and ownership mostly clear."
    elif pass_rate >= 0.5 and fail_rate < 0.2:
        headline = "Solid but mixed — real strengths, a few things to dig into before conviction."
    elif fail_rate >= 0.4:
        headline = "Weak on the fundamentals that matter for a multi-year hold — high bar to clear."
    else:
        headline = "Mixed — strengths offset by clear concerns; the flagged items decide it."
    if flags:
        headline += f"  ⚠ {len(flags)} red flag(s) — read the inversion panel."

    return {
        "symbol": symbol, "asof": asof,
        "sections": sections, "red_flags": flags,
        "summary": {"pass": tally[PASS], "watch": tally[WATCH], "fail": tally[FAIL],
                    "na": tally[NA], "pass_rate": round(pass_rate, 2),
                    "dealbreaker_fails": db_fails, "headline": headline},
    }
