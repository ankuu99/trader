"""
52-Week High Breakout Strategy (interday / daily candles)
----------------------------------------------------------
Buys when price makes a new N-period high — a classic momentum breakout.
Institutions and trend followers pile in on new highs, creating follow-through.

Entry  (BUY) : today's close exceeds the highest close of the previous `lookback` candles
Exit (SELL)  : close drops below a trailing stop (entry price - stop_pct %)

Works on daily candles. Requires at least `lookback` candles of history to warm up.

Config keys (under strategies.breakout in config.yaml):
    lookback : number of periods to look back for the high (default 52, ≈ 1 year weekly)
    stop_pct : trailing stop as % below the highest close seen since entry (default 8.0)
"""

from collections import deque

from trader.strategies.base import Direction, Signal, SignalType, Strategy


class BreakoutStrategy(Strategy):
    def __init__(self, instrument: str, params: dict):
        super().__init__(instrument, params)
        self._lookback: int = params.get("lookback", 52)
        self._stop_pct: float = float(params.get("stop_pct", 8.0)) / 100

        # Keep lookback + 1 so we can compare today vs previous N
        self._closes: deque[float] = deque(maxlen=self._lookback + 1)
        self._peak_since_entry: float | None = None   # highest close since entry

    @property
    def name(self) -> str:
        return f"Breakout({self._lookback})"

    def on_candle(self, candle: dict) -> Signal | None:
        close = candle["close"]
        self._closes.append(close)

        if len(self._closes) <= self._lookback:
            return None  # not enough history yet

        # Track highest close since entry for trailing stop
        if self.position == Direction.BUY:
            if self._peak_since_entry is None or close > self._peak_since_entry:
                self._peak_since_entry = close

        return self._evaluate(close)

    def _evaluate(self, close: float) -> Signal | None:
        closes = list(self._closes)
        # Previous N closes (excluding today)
        prev_closes = closes[:-1]
        prev_high = max(prev_closes)

        # Entry: new high breakout
        if self.is_flat() and close > prev_high:
            return Signal(
                instrument=self.instrument,
                direction=Direction.BUY,
                signal_type=SignalType.ENTRY,
                price_hint=close,
                strategy=self.name,
            )

        # Exit: trailing stop triggered
        if self.position == Direction.BUY and self._peak_since_entry is not None:
            trailing_stop = self._peak_since_entry * (1 - self._stop_pct)
            if close < trailing_stop:
                self._peak_since_entry = None
                return Signal(
                    instrument=self.instrument,
                    direction=Direction.SELL,
                    signal_type=SignalType.EXIT,
                    price_hint=close,
                    strategy=self.name,
                )

        return None

    def on_order_update(self, order: dict) -> None:
        super().on_order_update(order)
        if order.get("status") == "COMPLETE" and order.get("signal_type") == SignalType.EXIT:
            self._peak_since_entry = None
