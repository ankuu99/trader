"""
StrategyGroup — combines a primary strategy with confirmation filters.

How it works
------------
- On each candle, ALL strategies (primary + filters) receive on_candle() so their
  internal state (indicators, position tracking) stays current.
- If the primary emits an ENTRY signal, every filter must return True from
  confirm_entry(direction) for the signal to be forwarded.
- EXIT signals from the primary always pass through — you never want to block an exit.

Example
-------
    from trader.strategies.group import StrategyGroup
    from trader.strategies.orb import ORBStrategy
    from trader.strategies.supertrend import SupertrendStrategy

    primary = ORBStrategy("NSE:RELIANCE", config.strategy_config("orb"))
    trend_filter = SupertrendStrategy("NSE:RELIANCE", config.strategy_config("supertrend"))
    strategy = StrategyGroup(primary, filters=[trend_filter])
"""

from trader.strategies.base import Direction, Signal, SignalType, Strategy


class StrategyGroup(Strategy):
    """
    Wraps one primary strategy and zero or more filter strategies.
    Presents itself as a single Strategy with a composite name.
    """

    def __init__(self, primary: Strategy, filters: list[Strategy]):
        # Initialise base with primary's instrument; params unused here
        super().__init__(primary.instrument, {})
        self._primary = primary
        self._filters = filters

    # ------------------------------------------------------------------ #
    # Identity                                                             #
    # ------------------------------------------------------------------ #

    @property
    def name(self) -> str:
        if self._filters:
            filter_names = "+".join(f.name for f in self._filters)
            return f"{self._primary.name}[{filter_names}]"
        return self._primary.name

    # ------------------------------------------------------------------ #
    # Position — proxied from primary                                      #
    # ------------------------------------------------------------------ #

    @property
    def position(self):
        return self._primary.position

    @position.setter
    def position(self, value):
        # base __init__ sets self.position = None; redirect to primary
        if hasattr(self, "_primary"):
            self._primary.position = value

    def is_flat(self) -> bool:
        return self._primary.is_flat()

    # ------------------------------------------------------------------ #
    # Core lifecycle                                                        #
    # ------------------------------------------------------------------ #

    def on_candle(self, candle: dict) -> Signal | None:
        # Always update all filter states regardless of primary signal
        for f in self._filters:
            f.on_candle(candle)

        signal = self._primary.on_candle(candle)

        if signal is None:
            return None

        # EXIT signals always pass through — never block an exit
        if signal.signal_type == SignalType.EXIT:
            return signal

        # ENTRY: every filter must confirm
        if all(f.confirm_entry(signal.direction) for f in self._filters):
            return signal

        return None

    def on_order_update(self, update: dict) -> None:
        self._primary.on_order_update(update)
        for f in self._filters:
            f.on_order_update(update)

    def confirm_entry(self, direction: Direction) -> bool:
        """Delegate to primary — allows nesting StrategyGroups."""
        return self._primary.confirm_entry(direction)
