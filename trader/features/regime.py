"""
Multi-horizon regime measures — ATR-free, close-only.

Three measures per horizon (defaults 100/400/1600 bars ≈ 1 week / 1 month /
4 months on 15m candles):

  efficiency ratio (Kaufman): |net move| / path length — ~0 sideways, ~1 clean trend
  variance ratio (Lo-MacKinlay): Var(q-bar returns)/(q·Var(1-bar returns))
                                 >1 trending / <1 mean-reverting
  slope t-stat: OLS t-stat of close vs index — signed trend direction+strength,
                scale-invariant (invariant under y→c·y and level shifts)

Two consumers:
  * `regime_vector_at(closes, horizons)` — last-bar values, O(sum(horizons)) per
    call, safe inside the per-sample feature loop (RegimeFeaturePipeline).
  * `regime_states(closes, horizons)` — vectorised full-series discrete state
    (UP/DOWN/SIDEWAYS/MIXED/NA) for regime-conditioned thresholds.

Dormant in production — nothing imports this on the live path until a
config-gated feature/threshold uses it.
"""

from __future__ import annotations

import math

import numpy as np

DEFAULT_HORIZONS = (100, 400, 1600)

# Discrete state map cutoffs (see regime_states): a trend needs BOTH statistical
# significance (t-stat) and economic significance (fitted move as % of price over
# the window) — OLS end-effects on oscillating series produce |t| ~ 4 with a
# fitted move of ~1%, which must read as SIDEWAYS, not trend.
T_TREND = 2.0
MIN_MOVE_PCT = 2.0


# ---------------------------------------------------------------------------
# Last-bar measures (pure python/numpy on the tail window)
# ---------------------------------------------------------------------------

def efficiency_ratio_at(closes: list[float], window: int) -> float:
    """Kaufman ER over the last `window` bars ending at the last close."""
    if len(closes) < window + 1:
        return 0.5  # neutral
    seg = np.asarray(closes[-(window + 1):], dtype=float)
    net = abs(float(seg[-1] - seg[0]))
    path = float(np.abs(np.diff(seg)).sum())
    return net / path if path > 0 else 0.0


def variance_ratio_at(closes: list[float], window: int, q: int | None = None) -> float:
    """Lo-MacKinlay VR over the last `window` bars; q defaults to window//20."""
    q = q or max(2, window // 20)
    if len(closes) < window + q + 1:
        return 1.0  # neutral (random walk)
    seg = np.asarray(closes[-(window + q + 1):], dtype=float)
    if (seg <= 0).any():
        return 1.0
    logp = np.log(seg)
    r1 = np.diff(logp)[-window:]
    rq = (logp[q:] - logp[:-q])[-window:]
    v1 = r1.var()
    if v1 <= 0:
        return 1.0
    return float(rq.var() / (q * v1))


def slope_tstat_at(closes: list[float], window: int) -> float:
    """OLS t-stat of close vs bar index over the last `window` bars."""
    if len(closes) < window:
        return 0.0
    y = np.asarray(closes[-window:], dtype=float)
    return _tstat(y)


def _tstat(y: np.ndarray) -> float:
    w = len(y)
    if w < 3:
        return 0.0
    x = np.arange(w, dtype=float)
    x_mean = (w - 1) / 2.0
    sxx = float(((x - x_mean) ** 2).sum())
    b = float(((x - x_mean) * (y - y.mean())).sum()) / sxx
    a = float(y.mean()) - b * x_mean
    resid = y - a - b * x
    sse = float((resid ** 2).sum())
    if sse <= 0:
        return math.copysign(1e6, b) if b != 0 else 0.0
    se_b = math.sqrt((sse / (w - 2)) / sxx)
    return b / se_b if se_b > 0 else 0.0


def regime_vector_at(closes: list[float],
                     horizons: tuple[int, ...] = DEFAULT_HORIZONS) -> list[float]:
    """[er_h, vr_h (clipped 0..3), tanh(t_h/10)] per horizon — 3·len(horizons)
    values for the LAST bar. Neutral fallbacks when history is short, so the
    vector is always well-defined."""
    out: list[float] = []
    for h in horizons:
        out.append(efficiency_ratio_at(closes, h))
        out.append(float(np.clip(variance_ratio_at(closes, h), 0.0, 3.0)))
        out.append(math.tanh(slope_tstat_at(closes, h) / 10.0))
    return out


def regime_feature_names(horizons: tuple[int, ...] = DEFAULT_HORIZONS) -> list[str]:
    names = []
    for h in horizons:
        names.extend([f"er{h}", f"vr{h}", f"t{h}"])
    return names


# ---------------------------------------------------------------------------
# Full-series discrete state (vectorised) — for regime-conditioned thresholds
# ---------------------------------------------------------------------------

def _rolling_trend(y: np.ndarray, w: int) -> tuple[np.ndarray, np.ndarray]:
    """Vectorised rolling OLS of y vs index, window w. Returns (t_stat,
    move_pct): the slope t-stat and the fitted move over the window as % of the
    window mean. NaN before w-1."""
    n = len(y)
    out = np.full(n, np.nan)
    move = np.full(n, np.nan)
    if n < w or w < 3:
        return out, move
    x = np.arange(w, dtype=float)
    sx, sxx = x.sum(), (x * x).sum()
    c1 = np.concatenate(([0.0], np.cumsum(y)))
    c2 = np.concatenate(([0.0], np.cumsum(y * y)))
    sy = c1[w:] - c1[:-w]
    syy = c2[w:] - c2[:-w]
    sxy = np.convolve(y, x[::-1], mode="valid")
    denom = w * sxx - sx * sx
    b = (w * sxy - sx * sy) / denom
    a = (sy - b * sx) / w
    sse = np.maximum(syy - a * sy - b * sxy, 0.0)
    var_b = (sse / (w - 2)) / (sxx - sx * sx / w)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = b / np.sqrt(var_b)
    # degenerate/near-perfect fits (sse ~ 0, incl. cumsum cancellation) -> the
    # trend is as significant as it gets, not zero
    bad = ~np.isfinite(t)
    t[bad] = np.sign(b[bad]) * 1e6
    out[w - 1:] = t
    y_mean = sy / w
    with np.errstate(divide="ignore", invalid="ignore"):
        mv = np.where(y_mean != 0, b * w / y_mean * 100.0, 0.0)
    move[w - 1:] = mv
    return out, move


def _rolling_tstat(y: np.ndarray, w: int) -> np.ndarray:
    return _rolling_trend(y, w)[0]


def regime_states(closes: np.ndarray,
                  horizons: tuple[int, ...] | None = None) -> np.ndarray:
    """Discrete per-bar state from the mid-horizon trend, sanity-checked by the
    long horizon:
      UP        t_mid >= +T, fitted move >= +MIN_MOVE_PCT, t_long >= 0
      DOWN      t_mid <= -T, fitted move <= -MIN_MOVE_PCT, t_long <= 0
      MIXED     mid-trend significant (t AND move) but against the long trend
      SIDEWAYS  everything else
      NA        insufficient history
    """
    horizons = tuple(horizons or DEFAULT_HORIZONS)
    mid = horizons[len(horizons) // 2] if len(horizons) < 3 else horizons[1]
    long_ = horizons[-1]
    y = np.asarray(closes, dtype=float)
    t_mid, mv_mid = _rolling_trend(y, mid)
    t_long, _ = _rolling_trend(y, long_)

    states = np.full(len(y), "SIDEWAYS", dtype=object)
    states[np.isnan(t_mid) | np.isnan(t_long)] = "NA"
    valid = ~(np.isnan(t_mid) | np.isnan(t_long))
    trending_up = valid & (t_mid >= T_TREND) & (mv_mid >= MIN_MOVE_PCT)
    trending_dn = valid & (t_mid <= -T_TREND) & (mv_mid <= -MIN_MOVE_PCT)
    up = trending_up & (t_long >= 0)
    down = trending_dn & (t_long <= 0)
    mixed = (trending_up | trending_dn) & ~up & ~down
    states[up] = "UP"
    states[down] = "DOWN"
    states[mixed] = "MIXED"
    return states.astype(str)
