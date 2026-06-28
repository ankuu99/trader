"""
Factor computation (Phase 1) — raw per-stock factor values from the PIT store.

Each pillar function returns {factor_name: value | None} for a (symbol, asof). `None`
means "missing" (-> neutral 0.5 at scoring); raw values are NOT yet normalized or
direction-flipped — that happens centrally in scoring.py (design §3). All reads are
point-in-time via FVMStore.read_fundamental_asof / read_shareholding_asof.

Pillars implemented here: 1 (Earnings), 3 (Balance sheet), 4 (Ownership). Pillar 2
(Valuation) needs live price (Kite) and Pillar 5 (sector tailwind) is a cross-sectional
aggregate — both wired in later layers.
"""

from statistics import pstdev

from trader.fvm import fields as F

_WINSOR = 2.0  # ±200% growth cap (design §2/§3)


# ------------------------------------------------------------------ #
# Primitives                                                          #
# ------------------------------------------------------------------ #

def _series(store, symbol, spec, asof, basis="consolidated") -> list[tuple[str, float]]:
    """PIT (period, value) pairs for a (statement, field) spec, period-ascending,
    Nones dropped."""
    statement, field = spec
    d = store.read_fundamental_asof(symbol, statement, basis, field, asof)
    return [(p, v) for p, v in sorted(d.items()) if v is not None]


def _latest(series):
    return series[-1][1] if series else None


def slope(ys: list[float]) -> float | None:
    """OLS slope of ys against x = 0..n-1 (per-step change). None if < 2 points."""
    n = len(ys)
    if n < 2:
        return None
    xbar = (n - 1) / 2.0
    ybar = sum(ys) / n
    num = sum((i - xbar) * (y - ybar) for i, y in enumerate(ys))
    den = sum((i - xbar) ** 2 for i in range(n))
    return None if den == 0 else num / den


def winsorize(x: float, lo: float = -_WINSOR, hi: float = _WINSOR) -> float:
    return max(lo, min(hi, x))


def _q_index(period: str) -> int:
    """'YYYY-MM' (MM in 03/06/09/12) -> absolute quarter index (year*4 + q-1)."""
    y, m = (int(x) for x in period.split("-"))
    return y * 4 + (m // 3 - 1)


def _year_ago(period: str) -> str:
    """Same fiscal quarter one year earlier ('2026-03' -> '2025-03')."""
    y, m = period.split("-")
    return f"{int(y) - 1}-{m}"


def floored_yoy_series(store, symbol, asof, basis="consolidated") -> list[tuple[str, float]]:
    """Per-quarter floored YoY profit growth (the crown-jewel input, design §2):

        g_t = (NP_t - NP_{t-4q}) / max(|NP_{t-4q}|, F_t),  F_t = 1% of TTM revenue at t

    Numerator carries the Δ₹ turnaround signal; the floor stabilises tiny/negative
    bases (keeps it unit-coherent). Each g winsorized to ±200%. Returns period-ascending
    (period, g) pairs (only quarters with a year-ago base AND a positive TTM-revenue floor).
    """
    np_d = dict(_series(store, symbol, F.NET_PROFIT_Q, asof, basis))
    rev_d = dict(_series(store, symbol, F.TOTAL_REVENUE_Q, asof, basis))
    out = []
    for period in sorted(np_d):
        base_p = _year_ago(period)
        if base_p not in np_d:
            continue
        # TTM revenue at `period` = sum of the 4 quarters ending at `period`
        qi = _q_index(period)
        ttm_rev = sum(v for p, v in rev_d.items() if 0 <= qi - _q_index(p) <= 3)
        floor = 0.01 * abs(ttm_rev)
        denom = max(abs(np_d[base_p]), floor)
        if denom <= 0:
            continue
        g = winsorize((np_d[period] - np_d[base_p]) / denom)
        out.append((period, g))
    return out


# ------------------------------------------------------------------ #
# Pillar 1 — Earnings                                                 #
# ------------------------------------------------------------------ #

def pillar1_factors(store, symbol, asof, basis="consolidated") -> dict:
    g = floored_yoy_series(store, symbol, asof, basis)
    gvals = [v for _, v in g]

    yoy = gvals[-1] if gvals else None
    # acceleration: slope of last 4 YoY-growth points (needs >=4 -> ~8 quarters), else None
    acceleration = slope(gvals[-4:]) if len(gvals) >= 4 else None
    # consistency: -dispersion of recent YoY-growth (steady compounding scores high)
    consistency = -pstdev(gvals[-6:]) if len(gvals) >= 3 else None

    rev_growth_series = _series(store, symbol, F.REVENUE_GROWTH_Q, asof, basis)
    revenue_growth = winsorize(_latest(rev_growth_series) / 100.0) if rev_growth_series else None

    opm_series = [v for _, v in _series(store, symbol, F.OPM_Q, asof, basis)]
    opm_trend = slope(opm_series[-6:]) if len(opm_series) >= 3 else None

    return {
        "growth_acceleration": acceleration,
        "yoy_profit_growth": yoy,
        "revenue_growth": revenue_growth,
        "opm_trend": opm_trend,
        "earnings_consistency": consistency,
    }


# ------------------------------------------------------------------ #
# Pillar 3 — Balance sheet                                            #
# ------------------------------------------------------------------ #

def pillar3_factors(store, symbol, asof, basis="consolidated") -> dict:
    cfo = _latest(_series(store, symbol, F.CFO_A, asof, basis))
    npa = _latest(_series(store, symbol, F.NET_PROFIT_A, asof, basis))
    cfo_to_np = (cfo / npa) if (cfo is not None and npa not in (None, 0)) else None

    # debt trend uses the D/E RATIO series (scale-free, cross-sectionally comparable) —
    # NOT absolute-₹ debt, which would be dominated by company size. Falling D/E = good.
    de_vals = [v for _, v in _series(store, symbol, F.DE_A, asof, basis)]
    roce_series = [v for _, v in _series(store, symbol, F.ROCE_A, asof, basis)]

    return {
        "cfo_to_np": cfo_to_np,
        "debt_to_equity": de_vals[-1] if de_vals else None,        # lower=better
        "interest_coverage": _latest(_series(store, symbol, F.INT_COVERAGE_A, asof, basis)),
        "debt_trend": slope(de_vals[-4:]) if len(de_vals) >= 2 else None,  # lower(falling)=better
        "roce": roce_series[-1] if roce_series else None,
        "roce_trend": slope(roce_series[-4:]) if len(roce_series) >= 2 else None,
    }


# ------------------------------------------------------------------ #
# Pillar 4 — Ownership (from the shareholding table)                  #
# ------------------------------------------------------------------ #

def _sh_series(store, symbol, field, asof) -> list[float]:
    d = store.read_shareholding_asof(symbol, field, asof)
    return [v for _, v in sorted(d.items()) if v is not None]


def pillar4_factors(store, symbol, asof) -> dict:
    fii = _sh_series(store, symbol, F.SH_FII, asof)
    dii = _sh_series(store, symbol, F.SH_DII, asof)
    promoter = _sh_series(store, symbol, F.SH_PROMOTER, asof)
    pledge = _sh_series(store, symbol, F.SH_PLEDGE, asof)
    holders = _sh_series(store, symbol, F.SH_HOLDERS, asof)
    return {
        "fii_trend": slope(fii[-4:]) if len(fii) >= 2 else None,
        "dii_trend": slope(dii[-4:]) if len(dii) >= 2 else None,
        "promoter_holding": promoter[-1] if promoter else None,   # penalty side handled in scoring
        "pledge": pledge[-1] if pledge else None,                 # lower=better
        "holders_trend": slope(holders[-4:]) if len(holders) >= 2 else None,
    }


# ------------------------------------------------------------------ #
# Pillar 2 — Valuation                                                #
# ------------------------------------------------------------------ #

PEG_CAP = 5.0  # winsor cap; also the "bad" sentinel for negative-earnings / no-runway


def ttm_eps(store, symbol, asof, basis="consolidated") -> float | None:
    """Trailing-twelve-month EPS = sum of the last 4 quarterly Basic EPS (PIT). None if <4q."""
    series = _series(store, symbol, F.BASIC_EPS_Q, asof, basis)
    vals = [v for _, v in series]
    return sum(vals[-4:]) if len(vals) >= 4 else None


def pillar2_factors(store, symbol, asof, price: float | None = None,
                    basis="consolidated") -> dict:
    """Valuation factors. `ev_ebitda` is pure-Trendlyne; `peg`/`pe` need a current price
    (Kite, threaded from the strategy/engine). PEG uses TRAILING growth only (forward
    estimates dropped for v1, §13b) — degrades gracefully.

    PEG degenerate handling (design §2): negative earnings or non-positive growth ⇒ NOT
    "cheap" — set PEG to the worst sentinel (PEG_CAP), never None/neutral. PEG is winsorized
    to [0, PEG_CAP]; lower = better (direction flipped in scoring; z-scored there).
    """
    ev_ebitda = _latest(_series(store, symbol, F.EV_EBITDA_A, asof, basis))  # lower=better

    pe = peg = None
    if price is not None:
        eps = ttm_eps(store, symbol, asof, basis)
        if eps is not None and eps > 0:
            pe = price / eps
            g = pillar1_factors(store, symbol, asof, basis)["yoy_profit_growth"]  # fraction
            if g is not None and g > 0:
                peg = min(PEG_CAP, max(0.0, pe / (g * 100.0)))
            else:
                peg = PEG_CAP        # no runway / declining → worst, never "cheap"
        else:
            pe = None
            peg = PEG_CAP            # negative earnings → worst, never "cheap"

    return {
        "ev_ebitda": ev_ebitda,     # lower=better, sector-relative
        "pe": pe,                   # lower=better, sector-relative
        "peg": peg,                 # lower=better, z-scored, sector-relative
    }


def all_factors(store, symbol, asof, basis="consolidated", price: float | None = None) -> dict:
    """Convenience: merge the implemented pillars' raw factors for one (symbol, asof)."""
    return {
        **pillar1_factors(store, symbol, asof, basis),
        **pillar2_factors(store, symbol, asof, price, basis),
        **pillar3_factors(store, symbol, asof, basis),
        **pillar4_factors(store, symbol, asof),
    }
