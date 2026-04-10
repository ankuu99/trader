"""
Parameter search spaces for each intraday strategy.

No trader.* imports — this module is pure data so it can be imported
before the config singleton is loaded.
"""

# Maps strategy name → {param_name: [candidate values]}
PARAM_SPACES: dict[str, dict[str, list]] = {
    # ------------------------------------------------------------------ #
    # Intraday strategies (5-minute candles, MIS)                         #
    # ------------------------------------------------------------------ #
    "rsi": {
        "period":     [7, 10, 14, 21],
        "oversold":   [20, 25, 30, 35],
        "overbought": [65, 70, 75, 80, 85],
        "midpoint":   [45, 50, 55],
    },
    "orb": {
        "range_minutes": [5, 10, 15, 20, 30, 45],
    },
    "vwap": {
        "min_deviation_pct": [0.1, 0.2, 0.3, 0.5, 0.75, 1.0],
    },
    "supertrend": {
        "period": [5, 7, 10, 14],
        "factor": [2.0, 2.5, 3.0, 3.5, 4.0],
    },
    "bollinger": {
        "period": [10, 15, 20, 25, 30],
        "std":    [1.5, 2.0, 2.5, 3.0],
    },
    "ema_pullback": {
        "fast": [9, 12, 20, 26],
        "slow": [26, 50, 100, 200],
    },

    # ------------------------------------------------------------------ #
    # Interday strategies (daily candles, CNC)                            #
    # ------------------------------------------------------------------ #
    "ema_crossover": {
        "fast": [5, 9, 12, 20],
        "slow": [21, 26, 50, 100],
    },
    "rsi_ema": {
        "rsi_period": [7, 10, 14, 21],
        "ema_period": [20, 50, 100, 200],
        "oversold":   [25, 30, 35, 40],
        "midpoint":   [45, 50, 55],
    },
    "breakout": {
        "lookback":  [20, 30, 52, 63],
        "stop_pct":  [3.0, 5.0, 8.0, 10.0],
    },
    "adx": {
        "period":    [10, 14, 20],
        "threshold": [20, 25, 30],
    },
}

# Maps group name → (primary_strategy_name, [filter_strategy_names])
GROUP_COMPOSITIONS: dict[str, tuple[str, list[str]]] = {
    # Intraday groups
    "orb_supertrend": ("orb",          ["supertrend"]),
    "rsi_bollinger":  ("rsi",          ["bollinger"]),
    # Interday groups
    "ema_adx":        ("ema_crossover", ["adx"]),
}

ALL_STRATEGIES = set(PARAM_SPACES) | set(GROUP_COMPOSITIONS)
