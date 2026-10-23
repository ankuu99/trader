"""
MeanReversionStrategy — rule-based z-score dip-buyer (no ML).

A deliberately simple, non-extrema baseline. Same *intent* as LRExtremaStrategy
(buy dips, exit on recovery) but expressed as a 5-line rule instead of a trained
classifier — so it answers a sharp question: does the LR apparatus actually beat a
dumb z-score rule, or is the ML complexity for nothing?

Logic (long-only swing):
  - z = (close - MA(ma_period)) / std(ma_period)
  - ENTRY (BUY) when z <= -z_entry (price z_entry σ below its mean) and flat.
    Hard stop via stop_loss_hint (the engine simulates it intrabar). No fixed target.
  - EXIT when close reverts to/above the mean (close >= MA) or after hold_bars.

Config (strategies.mean_reversion): ma_period, z_entry, stop_pct, hold_bars.
"""

from collections import deque

import numpy as np

from trader.core.logger import get_logger
from trader.strategies.base import Direction, Signal, SignalType, Strategy

logger = get_logger(__name__)


class MeanReversionStrategy(Strategy):
    def __init__(self, instrument: str, params: dict):
        super().__init__(instrument, params)
        self._ma_period: int = int(params.get("ma_period", 50))
        self._z_entry: float = float(params.get("z_entry", 2.0))
        self._stop_pct: float = float(params.get("stop_pct", 5.0))
        self._hold_bars: int = int(params.get("hold_bars", 100))

        self._closes: deque = deque(maxlen=self._ma_period)
        self._entry_price: float | None = None
        self._held_bars: int = 0

    @property
    def name(self) -> str:
        return f"MeanReversion(ma={self._ma_period},z={self._z_entry})"

    def on_candle(self, candle: dict) -> Signal | None:
        close = candle["close"]
        self._closes.append(close)
        ts = candle.get("timestamp")

        # Pending fill guard (entry signalled, awaiting fill).
        if self._entry_price is not None and self.is_flat():
            return None

        if not self.is_flat():
            self._held_bars += 1

        if len(self._closes) < self._ma_period:
            return None

        arr = np.fromiter(self._closes, dtype=float)
        ma = float(arr.mean())
        std = float(arr.std())

        # --- Exit (in position) ---
        if not self.is_flat() and self._entry_price is not None:
            reason = None
            if self._held_bars >= self._hold_bars:
                reason = "TIME"
            elif close >= ma:
                reason = "MEAN_REVERT"
            if reason:
                self._entry_price = None  # clear so we don't re-emit before the fill
                return Signal(
                    instrument=self.instrument, direction=Direction.BUY,
                    signal_type=SignalType.EXIT, price_hint=close, strategy=self.name,
                    exit_reason=reason, timestamp=ts,
                )
            return None

        # --- Entry (flat) ---
        if self.is_flat() and self._entry_price is None and std > 0:
            z = (close - ma) / std
            if z <= -self._z_entry:
                self._entry_price = close
                self._held_bars = 0
                return Signal(
                    instrument=self.instrument, direction=Direction.BUY,
                    signal_type=SignalType.ENTRY, price_hint=close, strategy=self.name,
                    stop_loss_hint=round(close * (1 - self._stop_pct / 100), 2),
                    target_price=None, timestamp=ts,
                )
        return None

    def on_order_update(self, order: dict) -> None:
        super().on_order_update(order)
        status = order.get("status", "")
        signal_type = order.get("signal_type", "")
        if status == "COMPLETE":
            if signal_type == SignalType.ENTRY:
                fill = order.get("price") or order.get("average_price")
                if fill:
                    self._entry_price = float(fill)
                self._held_bars = 0
            elif signal_type == SignalType.EXIT:
                self._entry_price = None
                self._held_bars = 0
        elif status in ("REJECTED", "CANCELLED") and signal_type == SignalType.ENTRY:
            self._entry_price = None
            self._held_bars = 0
