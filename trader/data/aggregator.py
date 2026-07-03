"""
CandleAggregator — build higher-timeframe bars from 15-minute base candles.

Shared by the live path (main.py) and the backtest engine so aggregated bars
are identical in both. Only 15m candles are ever persisted; aggregated bars
exist in memory only (see docs/Aggregated_Timeframes_Design.md).

Bar boundaries (FROZEN — changing them changes every model's training data):

    day     09:15–15:15                 (15:15–15:30 tail dropped)
    4hour   09:15–13:15, 13:15–15:15    (15:15–15:30 tail dropped)

Emission is *completion-based*: the bar is emitted the moment its last member
candle is added (the 15m candle whose end touches the bucket end — e.g. the
15:00 candle completes the day bar). This matters live: LiveFeed only emits a
base candle when the next bucket's first tick arrives, so waiting for a
"trigger" candle past the boundary would delay every decision by a full base
candle (the 15:15 candle doesn't complete until 15:30). Fallbacks for missing
data: a base candle stamped >= 15:15 acts as a trigger-only candle (completes
any in-progress bar, own OHLCV discarded), a candle from a later bucket/date
closes out a stale partial, and flush() serves the scheduler's clock-based
end-of-day job.

Aggregated bar shape: timestamp = bucket start, OHLC composed, volume summed.
All non-OHLCV keys (_symbol, instrument_token, regime/_htf_* injections, …)
are inherited from the LAST member candle — the values as of decision time.
"""

from datetime import datetime, time, timedelta

TIMEFRAMES = {"15minute", "4hour", "day"}

# Strategy-TF bars per trading day — used to derive warm-up fetch depth.
BARS_PER_DAY = {"15minute": 25, "4hour": 2, "day": 1}

_MARKET_OPEN = time(9, 15)
_SECOND_4H_START = time(13, 15)
_TAIL_START = time(15, 15)
_BASE_MINUTES = 15

_OHLCV_KEYS = ("open", "high", "low", "close", "volume", "timestamp")


class CandleAggregator:
    def __init__(self, timeframe: str):
        if timeframe not in TIMEFRAMES:
            raise ValueError(
                f"Invalid aggregation timeframe '{timeframe}'. Must be one of {sorted(TIMEFRAMES)}"
            )
        self._tf = timeframe
        self._partial: dict | None = None       # accumulated OHLCV + bucket_start
        self._meta: dict | None = None          # last member candle (metadata source)
        self._bucket: tuple | None = None       # (date, bucket_index)

    @property
    def timeframe(self) -> str:
        return self._tf

    def add(self, candle: dict) -> dict | None:
        """Feed one base 15m candle. Returns a completed aggregated bar or None.
        Passthrough on 15minute: returns the candle itself, untouched.

        A bar is emitted the moment its last member arrives (candle end touches
        the bucket end) — the timely path. A candle from a later bucket/date, or
        a tail candle (>= 15:15, trigger-only, OHLCV discarded), closes out a
        stale partial left by missing data."""
        if self._tf == "15minute":
            return candle

        ts: datetime = candle["timestamp"]

        if ts.time() >= _TAIL_START:
            return self._emit()

        bucket = self._bucket_key(ts)
        emitted = None
        if self._partial is not None and bucket != self._bucket:
            emitted = self._emit()

        if self._partial is None:
            self._bucket = bucket
            self._partial = {
                "bucket_start": self._bucket_start(ts),
                "open": candle["open"],
                "high": candle["high"],
                "low": candle["low"],
                "close": candle["close"],
                "volume": candle.get("volume", 0),
            }
        else:
            p = self._partial
            p["high"] = max(p["high"], candle["high"])
            p["low"] = min(p["low"], candle["low"])
            p["close"] = candle["close"]
            p["volume"] += candle.get("volume", 0)
        self._meta = candle

        # Completion check: this candle is the bucket's last member. Only one
        # bar can be returned per add() — if a stale partial was already emitted
        # above (pathological gap), the fresh bar waits for the next
        # trigger/flush instead.
        candle_end = ts + timedelta(minutes=_BASE_MINUTES)
        if emitted is None and candle_end.time() >= self._bucket_end_time():
            return self._emit()
        return emitted

    def flush(self) -> dict | None:
        """Force-emit the in-progress bar (clock-based end-of-day flush, or day
        boundary in backtest when no trigger candle arrived). None when empty."""
        return self._emit()

    # ------------------------------------------------------------------ #

    def _bucket_key(self, ts: datetime) -> tuple:
        if self._tf == "day":
            return (ts.date(), 0)
        # 4hour — candles before 09:15 (defensive) fold into the first bucket
        return (ts.date(), 1 if ts.time() >= _SECOND_4H_START else 0)

    def _bucket_end_time(self) -> time:
        if self._tf == "4hour" and self._bucket and self._bucket[1] == 0:
            return _SECOND_4H_START
        return _TAIL_START

    def _bucket_start(self, ts: datetime) -> datetime:
        start = _SECOND_4H_START if self._bucket_key(ts)[1] == 1 else _MARKET_OPEN
        return ts.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)

    def _emit(self) -> dict | None:
        if self._partial is None:
            return None
        p, meta = self._partial, self._meta
        self._partial = None
        self._meta = None
        self._bucket = None
        out = {k: v for k, v in meta.items() if k not in _OHLCV_KEYS}
        out.update({
            "timestamp": p["bucket_start"],
            "open": p["open"],
            "high": p["high"],
            "low": p["low"],
            "close": p["close"],
            "volume": p["volume"],
        })
        return out
