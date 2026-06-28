"""
Scoring (Phase 1) — raw factors -> normalized -> pillar -> composite 0-100.

Pipeline (design §3):
  raw factor (factors.py)
   -> winsorize (universe-wide, 1st/99th pct)
   -> normalize: percentile rank (default) | z-score (PEG only, magnitude-preserving)
   -> direction flip so 1.0 ALWAYS = good
   -> sector-relative for valuation factors (coarsened ≥MIN_SECTOR, else universe fallback)
   -> missing -> 0.5 (neutral)
   -> factor -> pillar (weighted) -> composite = 100 × Σ pillar_weight × pillar_score

Pillar 5 (Forward) is down-scoped to a single realized SECTOR-TAILWIND factor (estimates
dropped for v1, §13b): the mean realized YoY profit-growth of each stock's sector.

Output of compute_scores(): {symbol: {"composite", "pillars": {...}, "factors": {...}}}.
"""

import math

from trader.fvm import factors as fac
from trader.fvm.data import universe as uni

MIN_SECTOR = 20            # min members for a sector-relative comparison group
_WINSOR = (0.01, 0.99)

PILLAR_WEIGHTS = {
    "earnings": 0.35, "valuation": 0.25, "forward": 0.15,
    "ownership": 0.15, "balance_sheet": 0.10,
}

# factor -> (pillar, weight-in-pillar, direction 'hi'|'lo', norm 'pct'|'z', scope 'uni'|'sec')
FACTORS = {
    # Pillar 1 — Earnings (acceleration is the crown jewel)
    "growth_acceleration":  ("earnings", 0.30, "hi", "pct", "uni"),
    "yoy_profit_growth":    ("earnings", 0.25, "hi", "pct", "uni"),
    "revenue_growth":       ("earnings", 0.20, "hi", "pct", "uni"),
    "opm_trend":            ("earnings", 0.15, "hi", "pct", "uni"),
    "earnings_consistency": ("earnings", 0.10, "hi", "pct", "uni"),
    # Pillar 2 — Valuation (sector-relative; PEG z-scored)
    "peg":                  ("valuation", 0.50, "lo", "z",   "sec"),
    "ev_ebitda":            ("valuation", 0.30, "lo", "pct", "sec"),
    "pe":                   ("valuation", 0.20, "lo", "pct", "sec"),
    # Pillar 3 — Balance sheet
    "cfo_to_np":            ("balance_sheet", 0.25, "hi", "pct", "uni"),
    "roce":                 ("balance_sheet", 0.20, "hi", "pct", "uni"),
    "debt_to_equity":       ("balance_sheet", 0.20, "lo", "pct", "uni"),
    "interest_coverage":    ("balance_sheet", 0.15, "hi", "pct", "uni"),
    "debt_trend":           ("balance_sheet", 0.10, "lo", "pct", "uni"),
    "roce_trend":           ("balance_sheet", 0.10, "hi", "pct", "uni"),
    # Pillar 4 — Ownership
    "fii_trend":            ("ownership", 0.25, "hi", "pct", "uni"),
    "promoter_holding":     ("ownership", 0.25, "hi", "pct", "uni"),
    "pledge":               ("ownership", 0.20, "lo", "pct", "uni"),
    "dii_trend":            ("ownership", 0.15, "hi", "pct", "uni"),
    "holders_trend":        ("ownership", 0.15, "hi", "pct", "uni"),
    # Pillar 5 — Forward (realized sector tailwind only)
    "sector_tailwind":      ("forward", 1.00, "hi", "pct", "uni"),
}


# ------------------------------------------------------------------ #
# Normalization helpers                                              #
# ------------------------------------------------------------------ #

def _winsorize(values: list[float]) -> list[float]:
    if len(values) < 3:
        return values
    s = sorted(values)
    lo = s[max(0, int(_WINSOR[0] * (len(s) - 1)))]
    hi = s[min(len(s) - 1, int(math.ceil(_WINSOR[1] * (len(s) - 1))))]
    return [max(lo, min(hi, v)) for v in values]


def _percentile_scores(vmap: dict[str, float]) -> dict[str, float]:
    """Mid-rank percentile in [0,1] (higher value -> higher score). Ignores Nones."""
    present = {k: v for k, v in vmap.items() if v is not None}
    if not present:
        return {}
    keys = list(present)
    clipped = dict(zip(keys, _winsorize([present[k] for k in keys])))
    vals = sorted(clipped.values())
    n = len(vals)
    out = {}
    for k, v in clipped.items():
        below = sum(1 for x in vals if x < v)
        equal = sum(1 for x in vals if x == v)
        out[k] = (below + 0.5 * equal) / n if n else 0.5
    return out


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _zscore_scores(vmap: dict[str, float]) -> dict[str, float]:
    """z-score -> normal-CDF in [0,1] (magnitude-preserving; higher value -> higher score)."""
    present = {k: v for k, v in vmap.items() if v is not None}
    if not present:
        return {}
    keys = list(present)
    clipped = dict(zip(keys, _winsorize([present[k] for k in keys])))
    mean = sum(clipped.values()) / len(clipped)
    var = sum((v - mean) ** 2 for v in clipped.values()) / len(clipped)
    sd = math.sqrt(var)
    if sd == 0:
        return {k: 0.5 for k in clipped}
    return {k: _phi((v - mean) / sd) for k, v in clipped.items()}


def _normalize_factor(vmap, norm, direction) -> dict[str, float]:
    scores = _zscore_scores(vmap) if norm == "z" else _percentile_scores(vmap)
    if direction == "lo":                       # flip so 1.0 = good
        scores = {k: 1.0 - v for k, v in scores.items()}
    return scores


def _coarse_groups(symbols, sectors: dict[str, str]) -> dict[str, list[str]]:
    """Group symbols by sector; sectors with < MIN_SECTOR members fall back to a shared
    '_universe' bucket (pragmatic stand-in for AMFI macro-coarsening, §3)."""
    by_sector: dict[str, list[str]] = {}
    for s in symbols:
        by_sector.setdefault(sectors.get(s, "Unknown"), []).append(s)
    groups: dict[str, list[str]] = {}
    for sec, members in by_sector.items():
        key = sec if len(members) >= MIN_SECTOR else "_universe"
        groups.setdefault(key, []).extend(members)
    return groups


# ------------------------------------------------------------------ #
# Composite                                                          #
# ------------------------------------------------------------------ #

def _sector_tailwind(raw, sectors) -> dict[str, float]:
    """Per-stock realized sector tailwind = mean YoY-profit-growth of its sector (§13b)."""
    by_sector: dict[str, list[float]] = {}
    for sym, f in raw.items():
        g = f.get("yoy_profit_growth")
        if g is not None:
            by_sector.setdefault(sectors.get(sym, "Unknown"), []).append(g)
    sec_mean = {sec: sum(v) / len(v) for sec, v in by_sector.items() if v}
    return {sym: sec_mean.get(sectors.get(sym, "Unknown")) for sym in raw}


def compute_scores(store, symbols, asof, price_provider=None) -> dict:
    sectors = store.sectors_map()
    raw = {
        s: fac.all_factors(store, s, asof,
                           price=(price_provider(s) if price_provider else None))
        for s in symbols
    }
    # Pillar 5 derived factor
    tail = _sector_tailwind(raw, sectors)
    for s in symbols:
        raw[s]["sector_tailwind"] = tail.get(s)

    # normalize every factor across the right population
    norm: dict[str, dict[str, float]] = {f: {} for f in FACTORS}
    for fname, (_pillar, _w, direction, ntype, scope) in FACTORS.items():
        if scope == "sec":
            for _key, members in _coarse_groups(symbols, sectors).items():
                vmap = {s: raw[s].get(fname) for s in members}
                norm[fname].update(_normalize_factor(vmap, ntype, direction))
        else:
            vmap = {s: raw[s].get(fname) for s in symbols}
            norm[fname] = _normalize_factor(vmap, ntype, direction)

    # aggregate -> pillar -> composite
    out = {}
    for s in symbols:
        fscores = {f: norm[f].get(s, 0.5) for f in FACTORS}   # missing -> neutral 0.5
        pillars = {}
        for pillar in PILLAR_WEIGHTS:
            items = [(w, fscores[f]) for f, (p, w, *_r) in FACTORS.items() if p == pillar]
            wsum = sum(w for w, _ in items)
            pillars[pillar] = (sum(w * sc for w, sc in items) / wsum) if wsum else 0.5
        composite = 100.0 * sum(PILLAR_WEIGHTS[p] * pillars[p] for p in PILLAR_WEIGHTS)
        out[s] = {"composite": composite, "pillars": pillars, "factors": fscores}
    return out
