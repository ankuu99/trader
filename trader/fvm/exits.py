"""
Exit stack (design Piece 9) — pure exit decision for an open position.

Precedence (any clock ringing = act; first match wins):
  1. Hard veto (Clock 1, thesis break)          -> EXIT 'thesis_break'
  2. Price break / trailing (Clock 2):           -> EXIT 'price_break' | 'trailing'
       active stop = 40-week MA early, tightened to 10-week MA once meaningfully in profit (R4)
  3. Valuation exhaustion (PEG ran to exhaustion)-> TRIM 'valuation_exhaustion' (ride the rest)
  4. Recycle (no new high in N weeks)            -> EXIT 'recycle'
  5. else                                         -> HOLD

The veto register reused at exit time IS Clock 1 (§4a). Thresholds are tunable constants.
"""

import pandas as pd

from trader.fvm import technical as tech

HOLD, EXIT, TRIM = "HOLD", "EXIT", "TRIM"

PROFIT_ACTIVATE = 0.15      # +15% from entry -> "meaningfully in profit" (tighten trail)
PEG_EXHAUSTION = 4.0        # PEG at/above this -> trim
RECYCLE_WEEKS = 12          # no new weekly-close high in N weeks -> recycle capital
TRIM_FRACTION = 0.5


def update_tracking(state: dict, weekly_close: float) -> dict:
    """Maintain the high-water mark + weeks-since-new-high each week. Returns state."""
    peak = state.get("peak_close", state["entry_price"])
    if weekly_close > peak:
        state["peak_close"] = weekly_close
        state["weeks_since_new_high"] = 0
    else:
        state["weeks_since_new_high"] = state.get("weeks_since_new_high", 0) + 1
    return state


def decide_exit(weekly: pd.DataFrame, state: dict, veto_passed: bool,
                peg: float | None = None) -> tuple[str, str | None]:
    """Return (action, reason). state: {entry_price, peak_close, weeks_since_new_high, trimmed}."""
    # 1. thesis break (Clock 1)
    if not veto_passed:
        return EXIT, "thesis_break"

    closes = weekly["close"].astype(float).tolist()
    close = closes[-1]
    entry = state["entry_price"]
    in_profit = close >= entry * (1 + PROFIT_ACTIVATE)

    ma40 = tech._sma_last(closes, tech.MA_LONG_W)
    ma10 = tech._sma_last(closes, tech.MA_SHORT_W)

    # 2. price break / trailing (Clock 2). Active stop tightens once in profit.
    if ma40 is not None:
        active_stop = ma10 if (in_profit and ma10 is not None) else ma40
        if close < active_stop:
            return EXIT, ("trailing" if in_profit else "price_break")

    # 3. valuation exhaustion -> trim (once)
    if peg is not None and peg >= PEG_EXHAUSTION and not state.get("trimmed"):
        return TRIM, "valuation_exhaustion"

    # 4. opportunity-cost recycle
    if state.get("weeks_since_new_high", 0) >= RECYCLE_WEEKS:
        return EXIT, "recycle"

    return HOLD, None
