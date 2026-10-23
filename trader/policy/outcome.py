"""
Canonical "what would our non-model exits do to a long entered at bar t" simulator.

Shared by the tradeable-trough labeler and scripts/campaign/stage_a.py so truth is defined once.
"""

from __future__ import annotations

import numpy as np


def simulate_exit_outcomes(closes, params: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """For every bar t: (good, outcome_ret_pct, exit_index) of a long entered at closes[t]
    under the stock's NON-MODEL exits on the close path. good = reached +profit_pct (trail arming) first.
    outcome_ret_pct = profit_pct on success, else the return at the exit bar; NaN when the outcome is
    unresolved because the data ends first (truncation guard — never guess)."""
    closes = np.asarray(closes, dtype=float)
    p = params
    up = float(p.get("profit_pct", 7.0))
    stop = float(p.get("stop_pct", 20.0))
    hold = int(p.get("hold_bars", 200))
    st_on = bool(p.get("stale_exit_enabled", False))
    st_k = int(p.get("stale_check_bars", 40))
    st_g = float(p.get("stale_min_gain_pct", 0.5))
    ra_on = st_on and bool(p.get("stale_rearm_enabled", False))
    ra_floor = float(p.get("stale_rearm_cur_floor_pct", -2.0))
    s2_on = bool(p.get("stale_exit_2_enabled", False))
    s2_k = int(p.get("stale_check_bars_2", 200))
    s2_g = float(p.get("stale_min_gain_pct_2", -2.0))

    n = len(closes)
    good = np.zeros(n, dtype=bool)
    ret = np.full(n, np.nan)
    exit_idx = np.full(n, n - 1, dtype=int)
    for t in range(n):
        e = closes[t]
        best = -1e9
        end = min(n - 1, t + hold)
        if end <= t:
            continue
        res = None
        for j in range(t + 1, end + 1):
            k = j - t
            g = (closes[j] - e) / e * 100.0
            if g > best:
                best = g
            if g >= up:
                res = (True, up, j)
                break
            if g <= -stop:
                res = (False, g, j)
                break
            if st_on and k >= st_k and best < st_g:
                res = (False, g, j)
                break
            if ra_on and k >= 2 * st_k and k % st_k == 0 and g < ra_floor:
                rb = (closes[j - st_k + 1: j + 1].max() - e) / e * 100.0
                if rb < st_g:
                    res = (False, g, j)
                    break
            if s2_on and k == s2_k and g < s2_g:
                res = (False, g, j)
                break
        if res is None:
            if t + hold > n - 1:
                continue  # truncated at the end of data — unknown outcome
            g = (closes[end] - e) / e * 100.0
            res = (False, g, end)
        good[t], ret[t], exit_idx[t] = res
    return good, ret, exit_idx
