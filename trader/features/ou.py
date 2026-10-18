"""Ornstein-Uhlenbeck s-score helper (Avellaneda & Lee 2010) — pure, no I/O."""

import math

import numpy as np


def ou_score(closes, window: int) -> tuple[float, float]:
    """(s_score, half_life_bars) from an AR(1) fit on log closes over the last window+1 bars:
    x_t = a + b·x_{t-1} + e. If 0 < b < 1: m = a/(1-b), sigma_eq = sqrt(var(e)/(1-b^2)),
    s = (x_last - m)/sigma_eq, half_life = -ln 2 / ln b. Otherwise (no mean reversion) → (0.0, inf).
    s is clipped to [-5, 5]. Needs len(closes) >= window + 1 else (0.0, inf)."""
    if window < 3 or len(closes) < window + 1:
        return 0.0, math.inf
    x = np.log(np.asarray(closes[-(window + 1):], dtype=float))
    if not np.all(np.isfinite(x)):
        return 0.0, math.inf
    x0, x1 = x[:-1], x[1:]
    if np.ptp(x0) == 0.0:
        return 0.0, math.inf
    b, a = np.polyfit(x0, x1, 1)
    if not (0.0 < b < 1.0):
        return 0.0, math.inf
    resid = x1 - (a + b * x0)
    var_e = float(np.var(resid, ddof=2))
    sigma_eq = math.sqrt(var_e / (1.0 - b * b))
    if sigma_eq <= 0.0 or not math.isfinite(sigma_eq):
        return 0.0, math.inf
    m = a / (1.0 - b)
    s = float(np.clip((x[-1] - m) / sigma_eq, -5.0, 5.0))
    return s, -math.log(2.0) / math.log(b)
