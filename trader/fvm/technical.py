"""
Technical layer (Phase 2) — the TIMER. Pure functions over OHLCV (price wiring via Kite
is separate). Produces Technical_Score = Trend_Score × Timing_Score (design Piece 5).

- Trend_Score (WEEKLY, the governing TF): multiplicative soft-gates on a Stage-2 uptrend —
  price above a rising 40-week MA with 10-week > 40-week. Any leg failing -> ~0 (= "not a
  confirmed uptrend"). Doubles as the Gate-B floor and (its negation) the Clock-2 exit.
- Timing_Score (DAILY trigger): max(Pullback, Breakout), each a two-component product.
  Per stress-test R2 the extension guard is NOT a graded multiplier — it's a hard
  parabolic-entry VETO (price too far above the 50-day -> block).
- Initial stop (R4): a WIDE catastrophe level (weekly swing low) beyond daily noise — the
  sizing denominator + black-swan breaker, never a tight daily stop.

All thresholds are module constants (tunable; design `OPEN`).
"""

import pandas as pd

# --- weekly trend ---
MA_LONG_W, MA_SHORT_W = 40, 10
TREND_SLOPE_LOOKBACK_W = 8          # weeks to measure 40w-MA slope over
ABOVE_EPS, SLOPE_EPS, ALIGN_EPS = 0.02, 0.0015, 0.03   # smoothstep saturation edges
# --- daily timing ---
MA_DAILY = 50
ATR_N = 14
BASE_LOOKBACK_D = 20               # consolidation window for breakout high
VOL_MA_D = 20
VOL_LO, VOL_HI = 1.2, 2.0          # volume-expansion ramp (× avg)
EXT_HI_ATR = 4.0                   # price > 50dMA + 4×ATR -> parabolic veto
SWING_LOW_W = 8                    # weeks for the wide catastrophe stop


# ------------------------------------------------------------------ #
# helpers                                                            #
# ------------------------------------------------------------------ #

def smoothstep(x: float, e0: float, e1: float) -> float:
    if e1 == e0:
        return 1.0 if x >= e1 else 0.0
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def _closes(df):
    return df["close"].astype(float).tolist()


def resample_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    """Daily OHLCV -> weekly (W-FRI). Expects a 'timestamp' column + OHLCV."""
    d = daily.copy()
    d["timestamp"] = pd.to_datetime(d["timestamp"])
    w = d.set_index("timestamp").resample("W-FRI").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"),
        close=("close", "last"), volume=("volume", "sum")).dropna()
    return w.reset_index()


def _sma_last(values, n):
    return sum(values[-n:]) / n if len(values) >= n else None


def atr(df: pd.DataFrame, n: int = ATR_N) -> float | None:
    """Average true range over the last n bars (simple mean of TR)."""
    h = df["high"].astype(float).tolist()
    low = df["low"].astype(float).tolist()
    c = df["close"].astype(float).tolist()
    if len(c) < n + 1:
        return None
    trs = [max(h[i] - low[i], abs(h[i] - c[i - 1]), abs(low[i] - c[i - 1]))
           for i in range(1, len(c))]
    return sum(trs[-n:]) / n


# ------------------------------------------------------------------ #
# Trend (weekly)                                                     #
# ------------------------------------------------------------------ #

def trend_score(weekly: pd.DataFrame) -> float:
    """Stage-2 confirmation in [0,1] = g_above × g_slope × g_align. 0.0 if too little history."""
    closes = _closes(weekly)
    if len(closes) < MA_LONG_W + 1:
        return 0.0
    ma40 = _sma_last(closes, MA_LONG_W)
    ma10 = _sma_last(closes, MA_SHORT_W)
    price = closes[-1]
    # 40w-MA slope as %/week over the lookback
    prev_ma40 = sum(closes[-MA_LONG_W - TREND_SLOPE_LOOKBACK_W:-TREND_SLOPE_LOOKBACK_W]) / MA_LONG_W
    slope_pw = (ma40 - prev_ma40) / prev_ma40 / TREND_SLOPE_LOOKBACK_W if prev_ma40 else 0.0

    g_above = smoothstep(price / ma40 - 1.0, 0.0, ABOVE_EPS)
    g_slope = smoothstep(slope_pw, 0.0, SLOPE_EPS)
    g_align = smoothstep((ma10 - ma40) / ma40, 0.0, ALIGN_EPS)
    return g_above * g_slope * g_align


# ------------------------------------------------------------------ #
# Timing (daily)                                                     #
# ------------------------------------------------------------------ #

def pullback_score(daily: pd.DataFrame) -> float:
    """proximity-to-rising-50d-MA × bullish-reversal (buy the dip in an uptrend)."""
    closes = _closes(daily)
    if len(closes) < MA_DAILY + 5:
        return 0.0
    ma50 = _sma_last(closes, MA_DAILY)
    ma50_prev = _sma_last(closes[:-5], MA_DAILY)
    if ma50_prev is None or ma50 <= ma50_prev:    # MA must be rising
        return 0.0
    dist = (closes[-1] - ma50) / ma50
    # proximity: peaks in the support zone just around/above the rising MA
    proximity = smoothstep(dist, -0.03, -0.005) * (1 - smoothstep(dist, 0.02, 0.08))
    row = daily.iloc[-1]
    rng = float(row["high"]) - float(row["low"])
    norm_close = (float(row["close"]) - float(row["low"])) / rng if rng > 0 else 0.5
    reversal = smoothstep(norm_close, 0.5, 0.85) * (1.0 if closes[-1] > closes[-2] else 0.4)
    return proximity * reversal


def breakout_score(daily: pd.DataFrame) -> float:
    """breakout-magnitude × volume-expansion (continuation from a base)."""
    if len(daily) < BASE_LOOKBACK_D + 2:
        return 0.0
    highs = daily["high"].astype(float).tolist()
    closes = _closes(daily)
    base_high = max(highs[-BASE_LOOKBACK_D - 1:-1])      # base excludes today
    magnitude = smoothstep((closes[-1] - base_high) / base_high, -0.005, 0.01)
    vols = daily["volume"].astype(float).tolist()
    vol_ma = _sma_last(vols, VOL_MA_D)
    volume = smoothstep(vols[-1] / vol_ma, VOL_LO, VOL_HI) if vol_ma else 0.0
    return magnitude * volume


def extension_vetoed(daily: pd.DataFrame) -> bool:
    """Parabolic-entry veto (R2): price more than EXT_HI_ATR×ATR above the 50-day MA."""
    closes = _closes(daily)
    ma50 = _sma_last(closes, MA_DAILY)
    a = atr(daily)
    if ma50 is None or a is None:
        return False
    return closes[-1] > ma50 + EXT_HI_ATR * a


def timing_score(daily: pd.DataFrame) -> float:
    """max(pullback, breakout); 0 if parabolically extended (hard veto)."""
    if extension_vetoed(daily):
        return 0.0
    return max(pullback_score(daily), breakout_score(daily))


# ------------------------------------------------------------------ #
# Combine + stop                                                     #
# ------------------------------------------------------------------ #

def initial_stop(weekly: pd.DataFrame) -> float | None:
    """Wide catastrophe stop (R4) = lowest weekly low over the last SWING_LOW_W weeks."""
    if len(weekly) < SWING_LOW_W:
        return None
    return min(weekly["low"].astype(float).tolist()[-SWING_LOW_W:])


def evaluate(daily: pd.DataFrame, weekly: pd.DataFrame | None = None) -> dict:
    """Full technical read for one stock. Technical_Score = Trend × Timing."""
    weekly = weekly if weekly is not None else resample_weekly(daily)
    trend = trend_score(weekly)
    timing = timing_score(daily)
    return {
        "trend_score": trend,
        "timing_score": timing,
        "technical_score": trend * timing,
        "extension_vetoed": extension_vetoed(daily),
        "pullback": pullback_score(daily),
        "breakout": breakout_score(daily),
        "initial_stop": initial_stop(weekly),
    }
