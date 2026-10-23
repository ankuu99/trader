"""
BreakoutStrategy — Donchian channel breakout (trend-following, non-extrema).

Orthogonal alpha to the dip-buying extrema/mean-reversion family: it buys strength,
not weakness. Directly targets the case flagged in config (e.g. NSE:SOLARINDS) where
a strong uptrend produces *zero* LRExtrema signals — a dip-buyer is silent in a trend.

Logic (long-only swing, turtle-style):
  - ENTRY (BUY) when close breaks above the highest high of the prior
    `entry_period` bars (a new N-bar high) and flat. Stop via stop_loss_hint
    (engine simulates intrabar): the lower channel, or stop_pct, whichever is set.
  - EXIT when close breaks below the lowest low of the prior `exit_period` bars
    (channel breakdown) or after hold_bars.

Config (strategies.breakout): entry_period, exit_period, stop_pct, hold_bars.
"""

from collections import deque

from trader.core.logger import get_logger
from trader.strategies.base import Direction, Signal, SignalType, Strategy

logger = get_logger(__name__)


class BreakoutStrategy(Strategy):
    def __init__(self, instrument: str, params: dict):
        super().__init__(instrument, params)
        self._entry_period: int = int(params.get("entry_period", 55))
        self._exit_period: int = int(params.get("exit_period", 20))
        self._stop_pct: float = float(params.get("stop_pct", 5.0))
        self._hold_bars: int = int(params.get("hold_bars", 200))

        # Keep enough history for the larger of the two channels (+1 for "prior" bars).
        maxlen = max(self._entry_period, self._exit_period) + 1
        self._highs: deque = deque(maxlen=maxlen)
        self._lows: deque = deque(maxlen=maxlen)
        self._entry_price: float | None = None
        self._held_bars: int = 0

    @property
    def name(self) -> str:
        return f"Breakout(in={self._entry_period},out={self._exit_period})"

    def on_candle(self, candle: dict) -> Signal | None:
        high, low, close = candle["high"], candle["low"], candle["close"]
        ts = candle.get("timestamp")

        # Channels over the PRIOR bars (exclude the current candle) — snapshot before append.
        prior_high = max(self._highs) if len(self._highs) >= self._entry_period else None
        prior_low = min(list(self._lows)[-self._exit_period:]) if len(self._lows) >= self._exit_period else None

        self._highs.append(high)
        self._lows.append(low)

        # Pending fill guard.
        if self._entry_price is not None and self.is_flat():
            return None

        if not self.is_flat():
            self._held_bars += 1

        # --- Exit (in position) ---
        if not self.is_flat() and self._entry_price is not None:
            reason = None
            if self._held_bars >= self._hold_bars:
                reason = "TIME"
            elif prior_low is not None and close < prior_low:
                reason = "CHANNEL_EXIT"
            if reason:
                self._entry_price = None
                return Signal(
                    instrument=self.instrument, direction=Direction.BUY,
                    signal_type=SignalType.EXIT, price_hint=close, strategy=self.name,
                    exit_reason=reason, timestamp=ts,
                )
            return None

        # --- Entry (flat): break above prior N-bar high ---
        if self.is_flat() and self._entry_price is None and prior_high is not None:
            if close > prior_high:
                self._entry_price = close
                self._held_bars = 0
                # Stop: the wider of the channel low and stop_pct floor.
                pct_stop = close * (1 - self._stop_pct / 100)
                stop = max(prior_low, pct_stop) if prior_low is not None else pct_stop
                return Signal(
                    instrument=self.instrument, direction=Direction.BUY,
                    signal_type=SignalType.ENTRY, price_hint=close, strategy=self.name,
                    stop_loss_hint=round(stop, 2), target_price=None, timestamp=ts,
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
