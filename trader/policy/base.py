"""
Policy primitives: PositionState and ExitDecision.

The nested→flat config resolver lives in trader.core.config.flatten_strategy_params
(centralised there so the live UI, which reads config.strategy_config, gets flat keys
too). Policies receive already-flattened params.
"""

from dataclasses import dataclass


@dataclass
class PositionState:
    """In-position tracking state. Single source of truth for the exit policy,
    restart recovery (seed_position_state) and reset. `fill_price` deliberately
    survives reset() — it is needed to restore entry state if an EXIT order is
    later cancelled/rejected."""
    entry_price: float | None = None
    fill_price: float | None = None
    held_bars: int = 0
    peak_close: float | None = None
    trailing_active: bool = False
    pattern_top_trailing: bool = False
    max_gain_pct: float = 0.0
    breakeven_active: bool = False

    def reset(self) -> None:
        """Clear all position-tracking fields (except fill_price). Matches the
        original LRExtremaStrategy._reset_position_state exactly."""
        self.entry_price = None
        self.held_bars = 0
        self.peak_close = None
        self.trailing_active = False
        self.pattern_top_trailing = False
        self.max_gain_pct = 0.0
        self.breakeven_active = False


@dataclass
class ExitDecision:
    """An exit the policy wants to emit. The strategy turns it into a Signal."""
    price_hint: float
    exit_reason: str | None = None
    timestamp: object | None = None
