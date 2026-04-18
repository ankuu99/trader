"""
Strategy registry — builds strategy instances from config.
"""

from trader.strategies.lr_extrema import LRExtremaStrategy
from trader.strategies.macd import MACDStrategy
from trader.strategies.rsi import RSIStrategy
from trader.strategies.zlmtf_macd import ZeroLagMTFMACDStrategy


def build_strategies(instrument: str, config) -> list:
    strategies = []

    rsi_cfg = config.strategy_config("rsi")
    if rsi_cfg.get("enabled", False):
        strategies.append(RSIStrategy(instrument, rsi_cfg))

    macd_cfg = config.strategy_config("macd")
    if macd_cfg.get("enabled", False):
        strategies.append(MACDStrategy(instrument, macd_cfg))

    zlmtf_cfg = config.strategy_config("zlmtf_macd")
    if zlmtf_cfg.get("enabled", False):
        strategies.append(ZeroLagMTFMACDStrategy(instrument, zlmtf_cfg))

    lr_cfg = config.strategy_config("lr_extrema")
    if lr_cfg.get("enabled", False):
        strategies.append(LRExtremaStrategy(instrument, lr_cfg))

    return strategies
