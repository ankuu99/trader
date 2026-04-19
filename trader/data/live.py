"""
Live market data via KiteTicker WebSocket.

Responsibilities:
  - Subscribe to tick feed for all watchlist instruments
  - Assemble ticks into completed candles (by timeframe)
  - Call on_tick(tick) and on_candle(candle) on registered strategy instances
  - Reconnect automatically on disconnection
"""

from datetime import datetime, timezone
from threading import Lock
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
        if self._stopping:
            logger.info("KiteTicker closed cleanly")
        else:
            logger.warning("KiteTicker disconnected | code=%s reason=%s", code, reason)

    def _on_error(self, ws, code, reason):
        if self._stopping:
            return  # expected during shutdown — suppress noise
        logger.error("KiteTicker error | code=%s reason=%s", code, reason)

    def _on_reconnect(self, ws, attempts):
        if self._stopping:
            return
        logger.info("KiteTicker reconnecting | attempt=%d", attempts)

    # ------------------------------------------------------------------ #
    # Tick processing & candle assembly                                    #
    # ------------------------------------------------------------------ #

    def _process_tick(self, tick: dict):
        # Dispatch raw tick to all tick handlers
        for handler in self._tick_handlers:
            try:
                handler(tick)
            except Exception:
                logger.exception("Error in tick handler")

        token = tick.get("instrument_token")
        ltp = tick.get("last_price")
        volume = tick.get("volume_traded", 0)
        ts: datetime = tick.get("timestamp") or datetime.now(timezone.utc)

        if token is None or ltp is None:
            return

        candle_start = self._candle_bucket(ts)

        with self._lock:
            partial = self._partials.get(token)

            if partial is None or candle_start > partial["candle_start"]:
                # Emit the completed candle before starting a new one
                if partial is not None:
                    self._emit_candle(token, partial)

                # Baseline for this new candle = cumulative vol at its first tick.
                # Using last seen cumulative (end of previous candle) handles the case
                # where the first tick arrives with a non-zero cumulative.
                # max(0, ...) guards against day-boundary resets (cumulative drops to 0).
                last_cumulative = self._vol_last.get(token, 0)
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
        """Round a timestamp down to the nearest candle boundary."""
        minute = (ts.minute // self._timeframe) * self._timeframe
        return ts.replace(minute=minute, second=0, microsecond=0)
