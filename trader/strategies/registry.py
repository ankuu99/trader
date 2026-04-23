"""
Strategy registry — builds strategy instances from config.
"""

from trader.strategies.lr_extrema import LRExtremaStrategy


def build_strategies(instrument: str, config) -> list:
    strategies = []

    lr_cfg = config.strategy_config("lr_extrema")
    if lr_cfg.get("enabled", False):
        strategies.append(LRExtremaStrategy(instrument, lr_cfg))

    return strategies
