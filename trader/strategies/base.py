"""
Base strategy interface.

All strategies inherit from Strategy and implement on_candle().
Strategies only emit Signal objects — they never place orders directly.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class SignalType(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"


@dataclass
class Signal:
    instrument: str          # e.g. "NSE:RELIANCE"
    direction: Direction
    signal_type: SignalType
    price_hint: float        # indicative price at signal time (LTP)
    strategy: str            # name of the strategy that generated this
    atr: float | None = None              # ATR at signal time; used by RiskManager for SL and sizing
    target_price: float | None = None     # ENTRY only: if set, RiskManager uses this as GTT target instead of computing one
    stop_loss_hint: float | None = None   # ENTRY only: if set, RiskManager uses this as GTT SL price instead of computing one
    exit_reason: str | None = None        # EXIT only: reason code passed to backtest trade record (e.g. "PATTERN_TOP")
    timestamp: object | None = None       # candle/tick timestamp; used by RiskManager for trading-window gate


class Strategy(ABC):
    """
    Base class for all strategies.

    Lifecycle
    ---------
    1. on_candle(candle) is called each time a candle closes.
    2. Internally update state (indicators, position tracking).
    3. Return a Signal or None.

    The live feed calls on_candle; the backtest engine does the same.
    No strategy should import from orders/ or risk/.
    """

    def __init__(self, instrument: str, params: dict):
        self.instrument = instrument
        self.params = params
        self.position: Direction | None = None   # current open direction, None if flat

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this strategy instance."""

    @abstractmethod
    def on_candle(self, candle: dict) -> Signal | None:
        """
        Called on each closed candle.

        Args:
            candle: dict with keys:
                instrument_token, timestamp, open, high, low, close, volume

        Returns:
            Signal if an action is warranted, else None.
        """

    def on_tick(self, tick: dict) -> "Signal | None":
        """
        Called on every raw tick (live) or simulated tick (backtest).
        Override to implement tick-speed exit logic (e.g. trailing stop).
        Entry logic should stay in on_candle.
        Default: no-op.
        """
        return None

    def on_order_update(self, order: dict) -> None:
        """
        Called when an order linked to this strategy changes status.
        Use to update self.position after a fill or rejection.
        """
        status = order.get("status", "")
        if status == "COMPLETE":
            direction = order.get("direction")
            signal_type = order.get("signal_type")
            if signal_type == SignalType.ENTRY:
                self.position = Direction(direction)
            elif signal_type == SignalType.EXIT:
                self.position = None
        elif status in ("REJECTED", "CANCELLED"):
            # Order didn't go through — leave position state unchanged
            pass

    def is_flat(self) -> bool:
        return self.position is None

    def confirm_entry(self, direction: "Direction") -> bool:
        """
        Return True if this strategy's current state supports an entry in the given direction.
        Used by StrategyGroup to gate primary strategy signals.
        Default: always True (strategy does not act as a filter).
        Override in strategies that can serve as confirmation filters.
        """
        return True
