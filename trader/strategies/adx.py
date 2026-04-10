"""
ADX Trend Strength Filter (interday + intraday)
------------------------------------------------
The Average Directional Index (ADX) measures trend STRENGTH, not direction.
ADX > threshold means a strong trend is in place; below means choppy/ranging.

This strategy never generates signals by itself — it is designed purely as a
confirmation filter inside a StrategyGroup.

  confirm_entry(BUY)  : ADX > threshold AND +DI > -DI  (strong uptrend)
  confirm_entry(SELL) : ADX > threshold AND -DI > +DI  (strong downtrend)

Config keys (under strategies.adx in config.yaml):
    period    : smoothing period for ATR, +DM, -DM (default 14)
    threshold : minimum ADX to confirm a trend (default 25)
"""

from collections import deque

from trader.strategies.base import Direction, Signal, SignalType, Strategy


class ADXFilter(Strategy):
    def __init__(self, instrument: str, params: dict):
        super().__init__(instrument, params)
        self._period: int = params.get("period", 14)
        self._threshold: float = float(params.get("threshold", 25))

        self._highs: deque[float] = deque(maxlen=self._period + 1)
        self._lows: deque[float] = deque(maxlen=self._period + 1)
        self._closes: deque[float] = deque(maxlen=self._period + 1)

        self._adx: float | None = None
        self._plus_di: float | None = None
        self._minus_di: float | None = None

        # Smoothed values (Wilder's smoothing)
        self._smooth_tr: float | None = None
        self._smooth_plus_dm: float | None = None
        self._smooth_minus_dm: float | None = None
        self._smooth_dx: float | None = None

    @property
    def name(self) -> str:
        return f"ADX({self._period})"

    def on_candle(self, candle: dict) -> Signal | None:
        """Update ADX state. Never generates a trade signal."""
        self._highs.append(candle["high"])
        self._lows.append(candle["low"])
        self._closes.append(candle["close"])

        if len(self._closes) < 2:
            return None

        highs = list(self._highs)
        lows = list(self._lows)
        closes = list(self._closes)

        h, prev_h = highs[-1], highs[-2]
        l, prev_l = lows[-1], lows[-2]
        prev_c = closes[-2]

        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        plus_dm = max(h - prev_h, 0) if (h - prev_h) > (prev_l - l) else 0
        minus_dm = max(prev_l - l, 0) if (prev_l - l) > (h - prev_h) else 0

        # Wilder's smoothing (equivalent to EMA with alpha=1/period)
        k = 1 / self._period
        if self._smooth_tr is None:
            self._smooth_tr = tr
            self._smooth_plus_dm = plus_dm
            self._smooth_minus_dm = minus_dm
        else:
            self._smooth_tr = self._smooth_tr * (1 - k) + tr * k
            self._smooth_plus_dm = self._smooth_plus_dm * (1 - k) + plus_dm * k
            self._smooth_minus_dm = self._smooth_minus_dm * (1 - k) + minus_dm * k

        if self._smooth_tr == 0:
            return None

        self._plus_di = 100 * self._smooth_plus_dm / self._smooth_tr
        self._minus_di = 100 * self._smooth_minus_dm / self._smooth_tr

        di_sum = self._plus_di + self._minus_di
        if di_sum == 0:
            return None

        dx = 100 * abs(self._plus_di - self._minus_di) / di_sum

        if self._smooth_dx is None:
            self._smooth_dx = dx
        else:
            self._smooth_dx = self._smooth_dx * (1 - k) + dx * k

        self._adx = self._smooth_dx
        return None  # ADX filter never generates its own signals

    def confirm_entry(self, direction: Direction) -> bool:
        """
        Returns True when:
        - ADX exceeds the threshold (trend is strong enough), AND
        - the directional indicators align with the requested direction
        """
        if self._adx is None or self._plus_di is None or self._minus_di is None:
            return False
        if self._adx < self._threshold:
            return False
        if direction == Direction.BUY:
            return self._plus_di > self._minus_di
        return self._minus_di > self._plus_di
