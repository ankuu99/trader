"""
Strategy registry — single source of truth for all strategy classes and groups.

Adding a new strategy:
  1. Create trader/strategies/my_strategy.py
  2. Import and add to STRATEGY_CLASSES below
  3. If it's a group, add to GROUP_COMPOSITIONS
  4. Add config section in the relevant config yaml
  5. Add param space to trader/calibration/param_space.py
  That's it — main.py, main_interday.py, backtest.py, calibrate.py need no changes.
"""

from trader.strategies.adx import ADXFilter
from trader.strategies.base import Strategy
from trader.strategies.bollinger import BollingerBandStrategy
from trader.strategies.breakout import BreakoutStrategy
from trader.strategies.ema_crossover import EMACrossoverStrategy
from trader.strategies.ema_pullback import EMAPullbackStrategy
from trader.strategies.group import StrategyGroup
from trader.strategies.orb import ORBStrategy
from trader.strategies.rsi import RSIStrategy
from trader.strategies.rsi_ema import RSIEMAStrategy
from trader.strategies.supertrend import SupertrendStrategy
from trader.strategies.vwap import VWAPReversionStrategy

# Maps config key → strategy class
# Order matters: strategies are instantiated in this order per symbol.
STRATEGY_CLASSES: dict[str, type[Strategy]] = {
    # Intraday (5-minute candles, MIS)
    "rsi":          RSIStrategy,
    "orb":          ORBStrategy,
    "vwap":         VWAPReversionStrategy,
    "supertrend":   SupertrendStrategy,
    "bollinger":    BollingerBandStrategy,
    "ema_pullback": EMAPullbackStrategy,
    # Interday (daily candles, CNC)
    "ema_crossover": EMACrossoverStrategy,
    "rsi_ema":       RSIEMAStrategy,
    "breakout":      BreakoutStrategy,
    # Filters (never emit signals — only usable inside groups)
    "adx":           ADXFilter,
}

# Strategies that only implement confirm_entry() and never emit signals.
# They are excluded from standalone registration and calibration.
FILTER_ONLY: set[str] = {"adx"}

# Maps group config key → (primary strategy key, [filter strategy keys])
GROUP_COMPOSITIONS: dict[str, tuple[str, list[str]]] = {
    # Intraday groups
    "orb_supertrend": ("orb",          ["supertrend"]),
    "rsi_bollinger":  ("rsi",          ["bollinger"]),
    # Interday groups
    "ema_adx":        ("ema_crossover", ["adx"]),
}


def build_strategies(symbol: str, config) -> list[Strategy]:
    """
    Instantiate all enabled strategies and groups for a single symbol,
    driven entirely by the active config.

    Args:
        symbol : instrument string, e.g. "NSE:RELIANCE"
        config : the config singleton (trader.core.config.config)

    Returns:
        List of Strategy instances ready to receive candles.
    """
    strategies: list[Strategy] = []

    # Solo strategies
    for name, cls in STRATEGY_CLASSES.items():
        if name in FILTER_ONLY:
            continue
        cfg = config.strategy_config(name)
        if cfg.get("enabled"):
            strategies.append(cls(symbol, cfg))

    # Strategy groups
    for group_name, (primary_name, filter_names) in GROUP_COMPOSITIONS.items():
        if not config.strategy_config(group_name).get("enabled"):
            continue
        primary = STRATEGY_CLASSES[primary_name](
            symbol, config.strategy_config(primary_name)
        )
        filters = [
            STRATEGY_CLASSES[fn](symbol, config.strategy_config(fn))
            for fn in filter_names
        ]
        strategies.append(StrategyGroup(primary=primary, filters=filters))

    return strategies
