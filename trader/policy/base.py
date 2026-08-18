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
    partial_taken: bool = False  # Step 2: a pattern-top scale-out has already fired
    # Full-state capture taken at FULL-exit signal emission (survives reset(), like
    # fill_price) so a REJECTED/CANCELLED exit order can restore the position's
    # clocks and trail state — e.g. a last-candle exit dying in Zerodha's Closing
    # Auction Session. One-shot: consumed by restore_snapshot(), discarded on a
    # COMPLETE exit fill or a new entry.
    _snapshot: dict | None = None

    def reset(self) -> None:
        """Clear all position-tracking fields (except fill_price and _snapshot).
        Matches the original LRExtremaStrategy._reset_position_state exactly."""
        self.entry_price = None
        self.held_bars = 0
        self.peak_close = None
        self.trailing_active = False
        self.pattern_top_trailing = False
        self.max_gain_pct = 0.0
        self.breakeven_active = False
        self.partial_taken = False

    def snapshot_and_reset(self) -> None:
        """Capture every position-tracking field, then reset(). Called wherever a
        FULL exit is emitted, so the whole position (not just entry_price) can be
        restored if the exit order is later rejected."""
        self._snapshot = {
            "entry_price": self.entry_price,
            "held_bars": self.held_bars,
            "peak_close": self.peak_close,
            "trailing_active": self.trailing_active,
            "pattern_top_trailing": self.pattern_top_trailing,
            "max_gain_pct": self.max_gain_pct,
            "breakeven_active": self.breakeven_active,
            "partial_taken": self.partial_taken,
        }
        self.reset()

    def restore_snapshot(self) -> bool:
        """Restore the state captured at exit emission (one-shot). Returns True
        if a snapshot existed and was applied."""
        snap = self._snapshot
        if snap is None:
            return False
        self._snapshot = None
        for key, value in snap.items():
            setattr(self, key, value)
        return True

    def clear_snapshot(self) -> None:
        self._snapshot = None


@dataclass
class ExitDecision:
    """An exit the policy wants to emit. The strategy turns it into a Signal."""
    price_hint: float
    exit_reason: str | None = None
    timestamp: object | None = None
    exit_fraction: float | None = None  # Step 2: <1.0 = partial (scale-out); None/1.0 = full
