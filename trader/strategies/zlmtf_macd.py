"""
Zero Lag Multi-Timeframe MACD Strategy
----------------------------------------
Pine Script reference: https://www.tradingview.com/script/chlgDc8f-Zero-Lag-Multi-Timeframe-MACD/
Author: CoffeeshopCrypto

"Zero Lag" here means the HTF MACD is approximated on the current timeframe candles
WITHOUT waiting for an HTF bar to close. It does this by scaling the MACD period:

    htf_period = round(htf_minutes / current_tf_minutes * period)

e.g. current=5min, htf=15min, fast=12 → htf_fast = round(15/5*12) = 36

LTF MACD: standard EMA-based (ta.ema)
HTF MACD: SMA-based with scaled periods (ta.sma) — SMA only, per the original script

Entry (BUY, CNC):
    1. LTF MACD line crosses above LTF signal line
    2. HTF MACD line has been rising for `lookback_bars` consecutive bars

Config keys (under strategies.zlmtf_macd in config.yaml):
    fast              : fast MA period (default 12)
    slow              : slow MA period (default 26)
    signal            : signal line period (default 9)
    current_tf_minutes: current chart timeframe in minutes (default 5)
    htf_minutes       : higher timeframe in minutes (default 15)
    lookback_bars     : bars to check for HTF rising (default 5)
"""

from collections import deque

from trader.core.logger import get_logger
from trader.strategies.base import Direction, Signal, SignalType, Strategy

logger = get_logger(__name__)


class ZeroLagMTFMACDStrategy(Strategy):
    def __init__(self, instrument: str, params: dict):
        super().__init__(instrument, params)

        fast: int = params.get("fast", 12)
        slow: int = params.get("slow", 26)
        sig: int = params.get("signal", 9)
        current_tf: int = params.get("current_tf_minutes", 5)
        htf: int = params.get("htf_minutes", 15)
        self._lookback: int = params.get("lookback_bars", 5)

        ratio = htf / current_tf

        # LTF periods (EMA-based)
        self._ltf_fast = fast
        self._ltf_slow = slow
        self._ltf_sig = sig

        # HTF periods (SMA-based, scaled to approximate HTF on LTF candles)
        self._htf_fast = round(ratio * fast)
        self._htf_slow = round(ratio * slow)
        self._htf_sig = round(ratio * sig)

        # LTF running EMA state
        self._kf = 2 / (fast + 1)
        self._ks = 2 / (slow + 1)
        self._kg = 2 / (sig + 1)
        self._ltf_ema_fast: float | None = None
        self._ltf_ema_slow: float | None = None
        self._ltf_sig_ema: float | None = None
        self._ltf_count = 0
        self._prev_ltf_macd: float | None = None
        self._prev_ltf_sig: float | None = None

        # HTF SMA state — keep enough closes for the largest SMA window
        htf_max = max(self._htf_slow, self._htf_sig + self._htf_slow)
        self._htf_closes: deque[float] = deque(maxlen=htf_max)
        self._htf_macd_vals: deque[float] = deque(maxlen=self._htf_sig + self._lookback + 1)
        # History of htf_macd_line for rising detection (need lookback+1 values)
        self._htf_macd_line_hist: deque[float] = deque(maxlen=self._lookback + 1)

    @property
    def name(self) -> str:
        return (
            f"ZL-MTF-MACD({self._ltf_fast},{self._ltf_slow},{self._ltf_sig}"
            f"|HTF-{self._htf_fast},{self._htf_slow},{self._htf_sig})"
        )

    def on_candle(self, candle: dict) -> Signal | None:
        close = candle["close"]
        self._ltf_count += 1

        # ---- LTF MACD (EMA-based) ----
        self._ltf_ema_fast = _ema_step(self._ltf_ema_fast, close, self._kf)
        self._ltf_ema_slow = _ema_step(self._ltf_ema_slow, close, self._ks)

        if self._ltf_count < self._ltf_slow:
            return None  # LTF EMAs warming up

        ltf_macd = self._ltf_ema_fast - self._ltf_ema_slow
        self._ltf_sig_ema = _ema_step(self._ltf_sig_ema, ltf_macd, self._kg)

        if self._ltf_count < self._ltf_slow + self._ltf_sig:
            self._prev_ltf_macd = ltf_macd
            self._prev_ltf_sig = self._ltf_sig_ema
            return None  # LTF signal line warming up

        # ---- HTF MACD (SMA-based with scaled periods) ----
        self._htf_closes.append(close)

        htf_macd_line: float | None = None
        if len(self._htf_closes) >= self._htf_slow:
            htf_fast_ma = _sma(self._htf_closes, self._htf_fast)
            htf_slow_ma = _sma(self._htf_closes, self._htf_slow)
            htf_macd_line = htf_fast_ma - htf_slow_ma
            self._htf_macd_vals.append(htf_macd_line)
            self._htf_macd_line_hist.append(htf_macd_line)

        # ---- Evaluate ----
        signal = None
        if (self._prev_ltf_macd is not None
                and self._prev_ltf_sig is not None
                and htf_macd_line is not None):
            signal = self._evaluate(close, ltf_macd, self._ltf_sig_ema, htf_macd_line)

        self._prev_ltf_macd = ltf_macd
        self._prev_ltf_sig = self._ltf_sig_ema
        return signal

    def _evaluate(
        self,
        close: float,
        ltf_macd: float,
        ltf_sig: float,
        htf_macd: float,
    ) -> Signal | None:
        if not self.is_flat():
            return None

        # LTF bullish crossover
        if not (self._prev_ltf_macd <= self._prev_ltf_sig and ltf_macd > ltf_sig):
            return None

        # HTF rising over lookback_bars (ta.rising equivalent)
        if not _is_rising(self._htf_macd_line_hist, self._lookback):
            logger.debug(
                "ZL-MTF-MACD | %s | LTF crossover but HTF not rising over %d bars",
                self.instrument, self._lookback,
            )
            return None

        logger.info(
            "ZL-MTF-MACD BUY | %s | LTF MACD=%.4f > Signal=%.4f | HTF rising (%.4f)",
            self.instrument, ltf_macd, ltf_sig, htf_macd,
        )
        return Signal(
            instrument=self.instrument,
            direction=Direction.BUY,
            signal_type=SignalType.ENTRY,
            price_hint=close,
            strategy=self.name,
        )


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def _ema_step(prev: float | None, value: float, k: float) -> float:
    """Incremental EMA. Initialises to value on first call."""
    return value if prev is None else value * k + prev * (1 - k)


def _sma(values: deque, period: int) -> float:
    """SMA of the last `period` values."""
    data = list(values)[-period:]
    return sum(data) / len(data)


def _is_rising(hist: deque, n: int) -> bool:
    """
    Equivalent to ta.rising(source, n): returns True if the series has been
    strictly rising for n consecutive bars (needs n+1 values).
    """
    vals = list(hist)
    if len(vals) < n + 1:
        return False
    # Check vals[-1] > vals[-2] > ... > vals[-(n+1)]
    tail = vals[-(n + 1):]
    return all(tail[i] > tail[i - 1] for i in range(1, len(tail)))
