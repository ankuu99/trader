"""
Pure technical-indicator functions.

Extracted verbatim from LRExtremaStrategy so both the feature pipeline and the
entry-gate checks share one implementation. All functions are pure (no state) and
operate on plain lists of floats — callers pass `[c["close"] for c in candles]`.

Behaviour MUST match the original LRExtremaStrategy staticmethods exactly — the
Stage 0 parity golden depends on it.
"""


def linreg_slope(prices: list[float]) -> float:
    """Ordinary least-squares slope of prices vs index."""
    n = len(prices)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(prices) / n
    num = sum((i - x_mean) * (prices[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return num / den if den != 0.0 else 0.0


def find_local_extrema(closes: list[float], order: int) -> tuple[list[int], list[int]]:
    """Return (minima_indices, maxima_indices) without scipy."""
    minima, maxima = [], []
    n = len(closes)
    for i in range(order, n - order):
        window = closes[i - order: i + order + 1]
        if closes[i] == min(window):
            minima.append(i)
        if closes[i] == max(window):
            maxima.append(i)
    return minima, maxima


def rsi_series(closes: list[float], period: int) -> list[float]:
    """SMA-based RSI series. Each value uses the preceding `period` deltas."""
    if len(closes) < period + 1:
        return []
    result = []
    for i in range(period, len(closes)):
        deltas = [closes[j] - closes[j - 1] for j in range(i - period + 1, i + 1)]
        avg_gain = sum(max(d, 0.0) for d in deltas) / period
        avg_loss = sum(abs(min(d, 0.0)) for d in deltas) / period
        if avg_loss == 0:
            result.append(100.0)
        else:
            result.append(100.0 - 100.0 / (1.0 + avg_gain / avg_loss))
    return result


def ema_series(values: list[float], period: int) -> list[float]:
    """Standard EMA series seeded with the first-period SMA."""
    if len(values) < period:
        return []
    k = 2.0 / (period + 1)
    result = [sum(values[:period]) / period]
    for v in values[period:]:
        result.append(v * k + result[-1] * (1 - k))
    return result


def stoch_rsi_k(closes: list[float], period: int, smooth_k: int) -> float | None:
    """Stochastic RSI K line. Uses `period` for both RSI and stochastic lookback.
    Returns None if there is insufficient data."""
    rsi_vals = rsi_series(closes, period)
    if len(rsi_vals) < period + smooth_k - 1:
        return None
    stoch_vals = []
    for i in range(period - 1, len(rsi_vals)):
        window = rsi_vals[i - period + 1: i + 1]
        lo, hi = min(window), max(window)
        if hi == lo:
            stoch_vals.append(0.0)
        else:
            stoch_vals.append((window[-1] - lo) / (hi - lo) * 100.0)
    if len(stoch_vals) < smooth_k:
        return None
    return sum(stoch_vals[-smooth_k:]) / smooth_k


def htf_trend_regime(
    closes: list[float],
    rsi_period: int,
    macd_fast: int,
    macd_slow: int,
    macd_signal_period: int,
    macd_slope_ma_period: int,
    rsi_downtrend_max: float,
    rsi_oversold: float,
    oversold_lookback: int,
) -> dict | None:
    """Classify the higher-timeframe trend regime from a list of CLOSED HTF closes.

    Returns None if there is insufficient data for either indicator — callers
    treat None as "neutral / gate inactive".

    Returns a dict with:
        rsi        : latest RSI value
        macd_hist  : latest MACD histogram value
        macd_slope : avg slope of the last `macd_slope_ma_period` histogram diffs
        downtrend  : MACD histogram < 0 AND RSI < rsi_downtrend_max AND macd_slope <= 0
        inversion  : RSI was < rsi_oversold within the last `oversold_lookback`
                      closed bars and has since risen, OR MACD histogram is
                      negative but its slope has turned positive
    """
    rsi_vals = rsi_series(closes, rsi_period)
    macd_st = macd_state(closes, macd_fast, macd_slow, macd_signal_period, macd_slope_ma_period)
    if not rsi_vals or macd_st is None:
        return None

    rsi = rsi_vals[-1]
    macd_hist, macd_slope = macd_st

    downtrend = macd_hist < 0 and rsi < rsi_downtrend_max and macd_slope <= 0

    recent_rsi = rsi_vals[-oversold_lookback:] if len(rsi_vals) >= oversold_lookback else rsi_vals
    was_oversold_and_rising = any(
        recent_rsi[i] < rsi_oversold and rsi > recent_rsi[i]
        for i in range(len(recent_rsi) - 1)
    )
    macd_turning_up = macd_hist < 0 and macd_slope > 0
    inversion = was_oversold_and_rising or macd_turning_up

    return {
        "rsi": rsi,
        "macd_hist": macd_hist,
        "macd_slope": macd_slope,
        "downtrend": downtrend,
        "inversion": inversion,
    }


def macd_state(
    closes: list[float],
    fast: int,
    slow: int,
    signal_period: int,
    slope_ma_period: int,
) -> tuple[float, float] | None:
    """Returns (current_histogram, avg_slope) or None if insufficient data.

    avg_slope is the mean of the last `slope_ma_period` bar-to-bar histogram
    differences (y2-y1 with x spacing=1). A positive avg_slope means the
    histogram is consistently rising (converging toward 0 from negative).
    """
    if len(closes) < slow + signal_period + slope_ma_period:
        return None
    ema_fast = ema_series(closes, fast)
    ema_slow = ema_series(closes, slow)
    if not ema_fast or not ema_slow:
        return None
    # Align fast EMA to match slow EMA length
    macd_vals = [ef - es for ef, es in zip(ema_fast[slow - fast:], ema_slow)]
    signal_ema = ema_series(macd_vals, signal_period)
    # signal_ema[i] corresponds to macd_vals[signal_period - 1 + i]
    sig_offset = signal_period - 1
    hist_series = [
        macd_vals[sig_offset + i] - signal_ema[i]
        for i in range(len(signal_ema))
    ]
    if len(hist_series) < slope_ma_period + 1:
        return None
    current_hist = hist_series[-1]
    slopes = [hist_series[i] - hist_series[i - 1] for i in range(-slope_ma_period, 0)]
    avg_slope = sum(slopes) / slope_ma_period
    return current_hist, avg_slope
