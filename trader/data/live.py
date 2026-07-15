"""
Live market data via KiteTicker WebSocket.

Responsibilities:
  - Subscribe to tick feed for all watchlist instruments
  - Assemble ticks into completed candles (by timeframe)
  - Call on_tick(tick) and on_candle(candle) on registered strategy instances
  - Reconnect automatically on disconnection
"""

import time as _sys_time
from datetime import datetime, timedelta, timezone
from threading import Lock

_IST_OFFSET = timedelta(hours=5, minutes=30)
# True when the server's local timezone is UTC (standard EC2 default).
# KiteConnect returns naive datetimes in local time, so on UTC machines
# tick timestamps are UTC and must be shifted to IST for correct bucketing.
_SERVER_IS_UTC = _sys_time.timezone == 0 and not _sys_time.daylight
from typing import Callable

from kiteconnect import KiteTicker

from trader.core.logger import get_logger

logger = get_logger(__name__)

# Type aliases
TickHandler = Callable[[dict], None]
CandleHandler = Callable[[dict], None]
OrderUpdateHandler = Callable[[dict], None]


class LiveFeed:
    def __init__(self, api_key: str, access_token: str, timeframe_minutes: int = 5):
        """
        Args:
            api_key         : Kite API key
            access_token    : valid Kite access token
            timeframe_minutes: candle size in minutes (default 5)
        """
        self._ticker = KiteTicker(api_key, access_token)
        self._timeframe = timeframe_minutes
        self._tokens: list[int] = []

        # Registered callbacks
        self._tick_handlers: list[TickHandler] = []
        self._candle_handlers: list[CandleHandler] = []
        self._order_update_handlers: list[OrderUpdateHandler] = []

        # In-progress candle state per instrument token
        # { token: { open, high, low, close, volume, candle_start } }
        self._partials: dict[int, dict] = {}
        self._lock = Lock()
        # Per-candle volume tracking: Kite sends cumulative day volume per tick.
        # We compute delta = current_cumulative - cumulative_at_candle_start.
        self._vol_baseline: dict[int, int] = {}  # token → cumulative vol at candle start
        self._vol_last: dict[int, int] = {}      # token → last cumulative vol seen

        self._stopping = False
        self._suspended = False  # True between market close disconnect and next-day reconnect

        self._bind_ticker_callbacks()

    def _bind_ticker_callbacks(self):
        self._ticker.on_connect = self._on_connect
        self._ticker.on_ticks = self._on_ticks
        self._ticker.on_order_update = self._on_order_update
        self._ticker.on_close = self._on_close
        self._ticker.on_error = self._on_error
        self._ticker.on_reconnect = self._on_reconnect

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def subscribe(self, tokens: list[int]):
        """Set the instrument tokens to stream."""
        self._tokens = tokens

    def register_tick_handler(self, handler: TickHandler):
        self._tick_handlers.append(handler)

    def register_candle_handler(self, handler: CandleHandler):
        self._candle_handlers.append(handler)

    def register_order_update_handler(self, handler: OrderUpdateHandler):
        self._order_update_handlers.append(handler)

    def start(self, threaded: bool = True):
        """
        Connect and start streaming.
        Set threaded=False to block (useful for simple scripts).
        """
        logger.info("Starting live feed | tokens=%s | timeframe=%dmin",
                    self._tokens, self._timeframe)
        self._ticker.connect(threaded=threaded)

    def stop(self):
        self._stopping = True
        self._ticker.close()
        logger.info("Live feed stopped")

    def disconnect(self):
        """Suspend feed at market close. Clears partial candles and pending volume state.
        Call reconnect() at next market open to resume."""
        self._suspended = True
        with self._lock:
            self._partials.clear()
            self._vol_baseline.clear()
            self._vol_last.clear()
        self._ticker.close()
        logger.info("Live feed disconnected for market close")

    def reconnect(self):
        """Re-establish WebSocket connection at market open. No-op on first startup."""
        if not self._suspended:
            return
        self._suspended = False
        self._connect_ticker()
        logger.info("Live feed reconnecting for market open")

    def _connect_ticker(self):
        """Connect the ticker, safe against an already-running Twisted reactor.

        KiteTicker.connect() issues connectWS() from the calling thread and only
        spawns the reactor `if not reactor.running`. On the first connect of the
        process that's fine. But on a cross-day reconnect (long-lived process:
        15:35 disconnect → next-day 09:00 reconnect) the reactor thread from the
        first connect is still running, so connectWS() runs on the scheduler
        thread against a live reactor — not thread-safe in Twisted, and the
        connection attempt is silently never processed (feed goes dark with no
        error; observed 2026-07-14/15). Hand the call to the reactor thread
        instead."""
        from twisted.internet import reactor
        if reactor.running:
            reactor.callFromThread(self._ticker.connect, threaded=True)
        else:
            self._ticker.connect(threaded=True)

    def update_access_token(self, api_key: str, access_token: str):
        """Adopt a fresh Kite access token by rebuilding the underlying KiteTicker.

        The ws URL embeds the token at construction, so mutation isn't enough — a
        new ticker is built and all callbacks re-bound. Intended for the overnight
        window (between market-close disconnect and pre-market reconnect); if the
        old socket is still up it is closed first. Subscriptions, handlers and
        candle state live on this object and carry over untouched."""
        try:
            if self._ticker.is_connected():
                logger.warning("update_access_token called while connected — closing old socket")
                self._ticker.close()
        except Exception:
            logger.exception("Error closing old ticker during token update")
        self._ticker = KiteTicker(api_key, access_token)
        self._bind_ticker_callbacks()
        logger.info("Live feed access token updated (ticker rebuilt)")

    # ------------------------------------------------------------------ #
    # KiteTicker callbacks                                                 #
    # ------------------------------------------------------------------ #

    def _on_connect(self, ws, response):
        logger.info("KiteTicker connected")
        if self._tokens:
            ws.subscribe(self._tokens)
            ws.set_mode(ws.MODE_FULL, self._tokens)

    def _on_ticks(self, ws, ticks: list[dict]):
        for tick in ticks:
            self._process_tick(tick)

    def _on_order_update(self, ws, update: dict):
        for handler in self._order_update_handlers:
            try:
                handler(update)
            except Exception:
                logger.exception("Error in order update handler")

    def _on_close(self, ws, code, reason):
        if self._stopping or self._suspended:
            logger.info("KiteTicker closed cleanly")
        else:
            logger.warning("KiteTicker disconnected | code=%s reason=%s", code, reason)

    def _on_error(self, ws, code, reason):
        if self._stopping or self._suspended:
            return  # expected during shutdown/suspend — suppress noise
        logger.error("KiteTicker error | code=%s reason=%s", code, reason)

    def _on_reconnect(self, ws, attempts):
        if self._stopping or self._suspended:
            return
        logger.info("KiteTicker reconnecting | attempt=%d", attempts)

    # ------------------------------------------------------------------ #
    # Tick processing & candle assembly                                    #
    # ------------------------------------------------------------------ #

    def _process_tick(self, tick: dict):
        token = tick.get("instrument_token")
        ltp = tick.get("last_price")
        logger.debug("Tick | token=%s ltp=%s", token, ltp)
        volume = tick.get("volume_traded", 0)

        # KiteTicker exposes the trade time as exchange_timestamp / last_trade_time —
        # there is no "timestamp" key on a raw tick. Normalise to a canonical IST
        # "timestamp" here so every downstream consumer (on_tick window gate, exit
        # policy force-close, candle bucketing, signal logging) reads one field, and
        # it matches the key the backtest engine feeds.
        ts_raw: datetime = (
            tick.get("exchange_timestamp")
            or tick.get("last_trade_time")
            or datetime.now()
        )
        if ts_raw.tzinfo is not None:
            # Aware datetime — convert to IST, strip tzinfo
            ts = ts_raw.astimezone(timezone(_IST_OFFSET)).replace(tzinfo=None)
        elif _SERVER_IS_UTC:
            # Naive datetime on a UTC server — shift to IST
            ts = ts_raw + _IST_OFFSET
        else:
            # Naive datetime on a local (IST) machine — use as-is
            ts = ts_raw
        tick["timestamp"] = ts

        # Dispatch the normalised tick to all tick handlers
        for handler in self._tick_handlers:
            try:
                handler(tick)
            except Exception:
                logger.exception("Error in tick handler")

        if token is None or ltp is None:
            return

        candle_start = self._candle_bucket(ts)

        with self._lock:
            partial = self._partials.get(token)

            if partial is None or candle_start > partial["candle_start"]:
                # Emit the completed candle before starting a new one
                if partial is not None:
                    self._emit_candle(token, partial)

                # Baseline for this new candle = cumulative vol at candle start.
                # If volume < last_cumulative, the day has rolled over and Kite has
                # reset the cumulative — zero the baseline so deltas are correct.
                last_cumulative = self._vol_last.get(token, 0)
                if volume < last_cumulative:
                    last_cumulative = 0  # day boundary reset detected
                self._vol_baseline[token] = last_cumulative
                self._partials[token] = {
                    "candle_start": candle_start,
                    "open": ltp,
                    "high": ltp,
                    "low": ltp,
                    "close": ltp,
                    "volume": max(0, volume - last_cumulative),
                }
            else:
                # Update the current partial candle
                partial["high"] = max(partial["high"], ltp)
                partial["low"] = min(partial["low"], ltp)
                partial["close"] = ltp
                partial["volume"] = max(0, volume - self._vol_baseline.get(token, 0))

            self._vol_last[token] = volume

    def _emit_candle(self, token: int, partial: dict):
        candle = {
            "instrument_token": token,
            "timestamp": partial["candle_start"],
            "open": partial["open"],
            "high": partial["high"],
            "low": partial["low"],
            "close": partial["close"],
            "volume": partial["volume"],
        }
        logger.debug("Candle closed | token=%d | %s", token, candle)
        for handler in self._candle_handlers:
            try:
                handler(candle)
            except Exception:
                logger.exception("Error in candle handler")

    def flush_partials(self):
        """Force-emit all in-progress candles. Call at market close (15:30 IST)."""
        with self._lock:
            for token, partial in list(self._partials.items()):
                logger.info("Force-flushing partial candle at market close | token=%d", token)
                self._emit_candle(token, partial)
            self._partials.clear()

    def _candle_bucket(self, ts: datetime) -> datetime:
        """Round a timestamp down to the nearest candle boundary, aligned to 9:15 IST.

        Kite historical API candles are anchored to market open (09:15), so live
        candle boundaries must match — otherwise live OHLCV differs from historical
        OHLCV and the model runs inference on a different distribution than it was
        trained on.
        """
        _MARKET_OPEN_MINUTES = 9 * 60 + 15  # 555
        ts_minutes = ts.hour * 60 + ts.minute
        offset = (ts_minutes - _MARKET_OPEN_MINUTES) // self._timeframe * self._timeframe
        bucket_minutes = _MARKET_OPEN_MINUTES + offset
        return ts.replace(
            hour=bucket_minutes // 60,
            minute=bucket_minutes % 60,
            second=0,
            microsecond=0,
        )
