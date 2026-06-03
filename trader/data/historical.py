"""
Historical OHLCV data — fetch from Kite and cache locally in SQLite.

Kite API limits:
  - minute data  : max 60 days per request
  - day data     : max 2000 days per request
"""

import time
from datetime import datetime, timedelta

import pandas as pd
from kiteconnect import KiteConnect
from kiteconnect.exceptions import NetworkException

from trader.core.config import config
from trader.core.logger import get_logger
from trader.data.store import Store

logger = get_logger(__name__)

# Kite interval strings
INTERVALS = {
    "minute", "3minute", "5minute", "10minute",
    "15minute", "30minute", "60minute", "4hour", "day",
}

# Kite caps per request for intraday data (in days)
_INTRADAY_MAX_DAYS = 60
_DAY_MAX_DAYS = 2000


def get_candles(
    kite: KiteConnect,
    store: Store,
    instrument_token: int,
    instrument: str,
    timeframe: str,
    from_dt: datetime,
    to_dt: datetime,
) -> pd.DataFrame:
    """
    Return OHLCV candles for the given instrument and date range.

    Serves from local cache where possible; fetches only the missing
    tail from the Kite API and persists it before returning.

    Args:
        kite            : authenticated KiteConnect instance
        store           : Store instance
        instrument_token: Kite numeric token for the instrument
        instrument      : human-readable key used as the cache key (e.g. "NSE:RELIANCE")
        timeframe       : Kite interval string (e.g. "5minute", "day")
        from_dt         : start of requested range (inclusive)
        to_dt           : end of requested range (inclusive)

    Returns:
        DataFrame with columns: timestamp, open, high, low, close, volume
    """
    if timeframe not in INTERVALS:
        raise ValueError(f"Invalid timeframe '{timeframe}'. Must be one of {INTERVALS}")

    # Check what we already have cached
    cached_latest = store.latest_candle_timestamp(instrument, timeframe)

    fetch_from = from_dt
    if cached_latest and cached_latest >= from_dt:
        # We have some cache — only fetch what's missing after the cached range
        fetch_from = cached_latest + timedelta(minutes=1)

    if fetch_from <= to_dt:
        if kite is None:
            logger.debug("kite=None — cache-only mode for %s [%s]", instrument, timeframe)
        else:
            _fetch_and_cache(kite, store, instrument_token, instrument, timeframe, fetch_from, to_dt)

    return store.read_candles(instrument, timeframe, from_dt, to_dt)


def _fetch_with_retry(
    kite: KiteConnect,
    instrument_token: int,
    instrument: str,
    timeframe: str,
    from_dt: datetime,
    to_dt: datetime,
    max_retries: int = 5,
    base_delay: float = 2.0,
) -> list:
    """Call kite.historical_data with exponential backoff on rate-limit errors."""
    for attempt in range(max_retries):
        try:
            return kite.historical_data(
                instrument_token=instrument_token,
                from_date=from_dt,
                to_date=to_dt,
                interval=timeframe,
                continuous=False,
                oi=False,
            )
        except NetworkException as e:
            if "Too many requests" not in str(e) or attempt == max_retries - 1:
                logger.error("Failed to fetch historical data for %s: %s", instrument, e)
                raise
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "Rate limited fetching %s — retrying in %.0fs (attempt %d/%d)",
                instrument, delay, attempt + 1, max_retries,
            )
            time.sleep(delay)
        except Exception as e:
            logger.error("Failed to fetch historical data for %s: %s", instrument, e)
            raise
    return []  # unreachable, but satisfies type checkers


def _fetch_and_cache(
    kite: KiteConnect,
    store: Store,
    instrument_token: int,
    instrument: str,
    timeframe: str,
    from_dt: datetime,
    to_dt: datetime,
):
    """Fetch from Kite in chunks respecting API limits, cache each chunk."""
    is_intraday = timeframe != "day"
    chunk_days = _INTRADAY_MAX_DAYS if is_intraday else _DAY_MAX_DAYS

    chunks = _date_chunks(from_dt, to_dt, chunk_days)
    total_fetched = 0

    for chunk_start, chunk_end in chunks:
        logger.debug(
            "Fetching %s [%s] from %s to %s",
            instrument, timeframe,
            chunk_start.date(), chunk_end.date(),
        )
        records = _fetch_with_retry(kite, instrument_token, instrument, timeframe, chunk_start, chunk_end)
        time.sleep(0.4)  # stay within Kite's ~3 req/sec rate limit

        if not records:
            continue

        df = pd.DataFrame(records)
        df.rename(columns={"date": "timestamp"}, inplace=True)
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]

        store.write_candles(instrument, timeframe, df)
        total_fetched += len(df)

    logger.info(
        "Fetched %d candles for %s [%s]", total_fetched, instrument, timeframe
    )


def _date_chunks(
    from_dt: datetime, to_dt: datetime, max_days: int
) -> list[tuple[datetime, datetime]]:
    """Split a date range into chunks of at most max_days each."""
    chunks = []
    current = from_dt
    while current <= to_dt:
        chunk_end = min(current + timedelta(days=max_days - 1), to_dt)
        chunks.append((current, chunk_end))
        current = chunk_end + timedelta(days=1)
    return chunks


def warm_up(
    kite: KiteConnect,
    store: Store,
    instrument_token: int,
    instrument: str,
    timeframe: str,
    lookback_days: int,
):
    """
    Pre-market warm-up: ensure we have at least `lookback_days` of recent
    candles cached for the given instrument. Called by the scheduler.
    """
    to_dt = datetime.now().replace(hour=23, minute=59, second=59)
    from_dt = to_dt - timedelta(days=lookback_days)
    logger.info("Warming up %s [%s] — %d days", instrument, timeframe, lookback_days)
    get_candles(kite, store, instrument_token, instrument, timeframe, from_dt, to_dt)
