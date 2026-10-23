"""
Triple-barrier labels (design Piece 7) — for evaluation + the future ML challenger.

From an entry bar, whichever barrier is hit first decides the label:
  upper = entry + k·ATR   (gain)
  lower = entry − k·ATR   (stop)
  time  = max_bars        (horizon)
Returns the signed net return at first touch (path-aware, vol-scaled). Pure; independent of
the live exit stack so exit tuning never invalidates labels.
"""


def triple_barrier_label(daily, entry_idx: int, atr_val: float,
                         k: float = 2.0, max_bars: int = 40) -> float:
    highs = daily["high"].astype(float).tolist()
    lows = daily["low"].astype(float).tolist()
    closes = daily["close"].astype(float).tolist()
    entry = closes[entry_idx]
    upper, lower = entry + k * atr_val, entry - k * atr_val
    end = min(len(closes) - 1, entry_idx + max_bars)
    for j in range(entry_idx + 1, end + 1):
        if highs[j] >= upper:
            return (upper - entry) / entry
        if lows[j] <= lower:
            return (lower - entry) / entry
    return (closes[end] - entry) / entry      # time barrier
