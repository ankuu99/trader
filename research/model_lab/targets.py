"""Hindsight targets T1w, T1z, T2, T3, T4, T5. Unresolved labels are NaN, never 0.

Every column has a known look-ahead (`lookahead(col)`); zigzag columns (t1z/t3) carry their own
`*_endbars_*` column instead (bars until the pivot that decides the label is CONFIRMED).
"""
import re

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

SCALES = {"15m": [4, 12, 25, 75], "30m": [4, 13, 39], "60m": [3, 7, 21], "4h": [2, 6, 15],
          "dayagg": [3, 5, 10, 20], "day": [3, 5, 10, 20], "week": [2, 4, 8]}
HOLD_H = {"15m": [25, 125, 500], "30m": [13, 65, 260], "60m": [7, 35, 140], "4h": [2, 10, 40],
          "dayagg": [5, 20, 60], "day": [5, 20, 60], "week": [4, 13, 26]}
FWD_H = [1, 2, 4, 8, 16, 32, 64, 128]
ZZ_K = [2, 5, 10]
ZZ_SIGMA_WINDOW = 250
ZZ_CLAMP_PCT = (0.3, 25.0)
BARRIER_X = [3, 5, 7, 10]
BARRIER_Y = [3, 5, 10]          # percent
_CHUNK = 5000


def zigzag_pivots(close: np.ndarray, thr_pct: np.ndarray, start: int = 0) -> list[tuple[int, int, int]]:
    """Close-based zigzag. Returns (pivot_idx, kind in {-1 low, +1 high}, confirm_idx). Sequential: step i
    reads only close[:i+1] and thr at indices <= i."""
    n = len(close)
    piv: list[tuple[int, int, int]] = []
    if start >= n:
        return piv
    mx = mn = start
    state = 0                      # 0 undecided, -1 down leg (cand = low), +1 up leg (cand = high)
    cand = start
    for i in range(start, n):
        c = close[i]
        if state == 0:
            if c > close[mx]:
                mx = i
            if c < close[mn]:
                mn = i
            if c <= close[mx] * (1 - thr_pct[mx] / 100.0):
                piv.append((mx, 1, i)); state = -1; cand = i
            elif c >= close[mn] * (1 + thr_pct[mn] / 100.0):
                piv.append((mn, -1, i)); state = 1; cand = i
        elif state == -1:
            if c < close[cand]:
                cand = i
            elif c >= close[cand] * (1 + thr_pct[cand] / 100.0):
                piv.append((cand, -1, i)); state = 1; cand = i
        else:
            if c > close[cand]:
                cand = i
            elif c <= close[cand] * (1 - thr_pct[cand] / 100.0):
                piv.append((cand, 1, i)); state = -1; cand = i
    return piv


def _first_hit(mask: np.ndarray) -> np.ndarray:
    """First True index per row, or a large sentinel when none."""
    idx = mask.argmax(axis=1)
    return np.where(mask.any(axis=1), idx, 1 << 30)


def _t1w(h: np.ndarray, l: np.ndarray, scales, out: dict) -> None:
    n = len(h)
    for w in scales:
        mn = np.full(n, np.nan)
        mxv = np.full(n, np.nan)
        if n >= 2 * w + 1:
            for name, arr, fn, dst in (("min", l, np.argmin, mn), ("max", h, np.argmax, mxv)):
                win = sliding_window_view(arr, 2 * w + 1)
                for a in range(0, win.shape[0], _CHUNK):
                    am = fn(win[a:a + _CHUNK], axis=1)
                    dst[a + w: a + w + len(am)] = (am == w).astype(float)
        out[f"t1w_min_w{w}"] = mn
        out[f"t1w_max_w{w}"] = mxv


def build_targets(bars: pd.DataFrame, tf: str, **overrides) -> pd.DataFrame:
    scales = overrides.get("scales", SCALES[tf])
    hold_h = overrides.get("hold_h", HOLD_H[tf])
    fwd_h = overrides.get("fwd_h", FWD_H)
    zz_k = overrides.get("zz_k", ZZ_K)
    sw = overrides.get("zz_sigma_window", ZZ_SIGMA_WINDOW)
    clamp = overrides.get("zz_clamp_pct", ZZ_CLAMP_PCT)
    bx = overrides.get("barrier_x", BARRIER_X)
    by = overrides.get("barrier_y", BARRIER_Y)

    o = bars["open"].to_numpy(float)
    h = bars["high"].to_numpy(float)
    l = bars["low"].to_numpy(float)
    c = bars["close"].to_numpy(float)
    n = len(c)
    cs = pd.Series(c)
    simple = cs / cs.shift(1) - 1
    sig_f = simple.rolling(sw).std().to_numpy()          # fraction
    sig_p = 100.0 * sig_f                                # percent
    out: dict[str, np.ndarray] = {}
    t = np.arange(n)

    # T1w
    _t1w(h, l, scales, out)

    # T1z + T3
    valid_sig = ~np.isnan(sig_p)
    start = int(np.argmax(valid_sig)) if valid_sig.any() else n
    for k in zz_k:
        thr = np.clip(k * sig_p, *clamp)
        piv = zigzag_pivots(c, thr, start)
        mn = np.full(n, np.nan); mxx = np.full(n, np.nan); eb = np.full(n, np.nan)
        r3 = np.full(n, np.nan); b3 = np.full(n, np.nan); s3 = np.full(n, np.nan); e3 = np.full(n, np.nan)
        if piv:
            pidx = np.array([p[0] for p in piv]); kind = np.array([p[1] for p in piv])
            conf = np.array([p[2] for p in piv])
            res = (t >= start) & (t <= pidx[-1])
            mn[res] = 0.0; mxx[res] = 0.0
            mn[pidx[kind == -1]] = 1.0
            mxx[pidx[kind == 1]] = 1.0
            first = np.searchsorted(pidx, t, side="left")
            ok = res & (first < len(pidx))
            eb[ok] = conf[first[ok]] - t[ok]
            nxt = np.searchsorted(pidx, t, side="right")
            ok3 = (nxt < len(pidx)) & valid_sig
            ni = pidx[np.minimum(nxt, len(pidx) - 1)]
            ret = c[ni] / c[t] - 1
            r3[ok3] = ret[ok3]
            b3[ok3] = (ni - t)[ok3]
            with np.errstate(divide="ignore", invalid="ignore"):
                sg = np.where(sig_p > 0, 100.0 * ret / sig_p, np.nan)      # σ_t = 0 -> NaN, never inf
            s3[ok3] = sg[ok3]
            e3[ok3] = (conf[np.minimum(nxt, len(pidx) - 1)] - t)[ok3]
        out[f"t1z_min_k{k}"] = mn; out[f"t1z_max_k{k}"] = mxx; out[f"t1z_endbars_k{k}"] = eb
        out[f"t3_ret_k{k}"] = r3; out[f"t3_bars_k{k}"] = b3
        out[f"t3_sig_k{k}"] = s3; out[f"t3_endbars_k{k}"] = e3

    # T2
    for hh in scales:
        up = np.full(n, np.nan); dn = np.full(n, np.nan); fw = np.full(n, np.nan)
        if n > 2 * hh:
            rows = np.arange(hh, n - hh)
            back = c[rows] / c[rows - hh] - 1
            fwd = c[rows + hh] / c[rows] - 1
            delta = 0.5 * sig_f[rows] * np.sqrt(hh)
            ok = ~np.isnan(delta)
            u = ((back < -delta) & (fwd > delta)).astype(float)
            d = ((back > delta) & (fwd < -delta)).astype(float)
            f = np.where(fwd > delta, 1.0, np.where(fwd < -delta, -1.0, 0.0))
            up[rows[ok]] = u[ok]; dn[rows[ok]] = d[ok]; fw[rows[ok]] = f[ok]
        out[f"t2_up_h{hh}"] = up; out[f"t2_dn_h{hh}"] = dn; out[f"t2_fwd_h{hh}"] = fw

    # T4
    for hh in fwd_h:
        r = np.full(n, np.nan)
        if n > hh:
            r[: n - hh] = np.log(c[hh:] / c[: n - hh])
        out[f"t4_ret_h{hh}"] = r

    # T5
    _t5(o, h, l, c, hold_h, bx, by, out)
    _t5_volscaled(c, hold_h, out)

    df = pd.DataFrame(out)
    df.insert(0, "timestamp", bars["timestamp"].values)
    return df


def _t5(o, h, l, c, hold_h, bx, by, out: dict) -> None:
    n = len(c)
    Hmax = max(hold_h)
    nan = np.full(Hmax, np.nan)
    hp = np.concatenate([h[1:], nan]); lp = np.concatenate([l[1:], nan])
    op = np.concatenate([o[1:], [np.nan]])
    cp = np.concatenate([c, nan])
    hw = sliding_window_view(hp, Hmax)          # row t = high[t+1 : t+1+Hmax]
    lw = sliding_window_view(lp, Hmax)
    res = {}
    for H in hold_h:
        for nm in ("mfe", "ttm", "maepre", "mae", "ret"):
            res[f"t5_{nm}_H{H}"] = np.full(n, np.nan)
        for X in bx:
            for Y in by:
                res[f"t5_hit_x{X}_y{Y}_H{H}"] = np.full(n, np.nan)
    for a in range(0, n, _CHUNK):
        b = min(n, a + _CHUNK)
        e = op[a:b]
        hwc = hw[a:b]; lwc = lw[a:b]
        fx = {X: _first_hit(hwc >= (e * (1 + X / 100.0))[:, None]) for X in bx}
        fy = {Y: _first_hit(lwc <= (e * (1 - Y / 100.0))[:, None]) for Y in by}
        tt = np.arange(a, b)
        for H in hold_h:
            ok = tt + H <= n - 1
            if not ok.any():
                continue
            hh = hwc[:, :H]; ll = lwc[:, :H]
            am = np.argmax(hh, axis=1)
            pre = np.minimum.accumulate(ll, axis=1)
            sel = tt[ok]
            mfe = hh.max(axis=1) / e - 1
            ttm = (am + 1).astype(float)
            maepre = np.take_along_axis(pre, am[:, None], axis=1)[:, 0] / e - 1
            mae = pre[:, H - 1] / e - 1
            ret = cp[tt + H] / e - 1
            for nm, v in (("mfe", mfe), ("ttm", ttm), ("maepre", maepre), ("mae", mae), ("ret", ret)):
                res[f"t5_{nm}_H{H}"][sel] = v[ok]
            for X in bx:
                for Y in by:
                    hit = ((fx[X] < H) & (fx[X] < fy[Y])).astype(float)
                    res[f"t5_hit_x{X}_y{Y}_H{H}"][sel] = hit[ok]
    out.update(res)


def _t5_volscaled(c, hold_h, out: dict) -> None:
    """Vol-scaled T5: raw column / (s_t * sqrt(H)), s_t = 16-bar std of 1-bar log returns ending at t (== factors rv_16)."""
    c = np.asarray(c, float)
    r1 = np.full(len(c), np.nan)
    r1[1:] = np.log(c[1:] / c[:-1])
    s = pd.Series(r1).rolling(16).std().to_numpy()
    for H in hold_h:
        SH = s * np.sqrt(H)
        with np.errstate(divide="ignore", invalid="ignore"):
            SH = np.where(SH > 0, SH, np.nan)
            mfe = out[f"t5_mfe_H{H}"]; mp = out[f"t5_maepre_H{H}"]; rt = out[f"t5_ret_H{H}"]
            out[f"t5_mfez_H{H}"] = mfe / SH
            out[f"t5_maepz_H{H}"] = mp / SH
            out[f"t5_retz_H{H}"] = rt / SH
            out[f"t5_edgez_H{H}"] = (mfe + mp) / SH


_LA = [(re.compile(r"^t1w_(min|max)_w(\d+)$"), 2), (re.compile(r"^t2_\w+_h(\d+)$"), 1),
       (re.compile(r"^t4_ret_h(\d+)$"), 1), (re.compile(r"^t5_.*_H(\d+)$"), 1)]


def lookahead(col: str) -> int | None:
    """Fixed look-ahead in bars, or None for the zigzag columns (use *_endbars_* instead)."""
    for rx, g in _LA:
        m = rx.match(col)
        if m:
            return int(m.group(g))
    return None
