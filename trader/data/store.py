"""
SQLite interface — all raw SQL lives here and nowhere else.

Tables
------
candles        : OHLCV data for all instruments and timeframes
orders         : every order action with full lifecycle tracking
trades         : filled trade records linked to orders
open_positions : paper-mode positions that survive restarts
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pandas as pd

from trader.core.logger import get_logger

logger = get_logger(__name__)


class Store:
    _DB_WARN_MB = 500  # warn if DB exceeds this size on startup

    def __init__(self, db_path: Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = str(db_path)
        self._init_schema()
        self._log_db_size()

    def _log_db_size(self):
        try:
            size_bytes = os.path.getsize(self._path)
        except OSError:
            return
        size_mb = size_bytes / (1024 * 1024)
        if size_mb >= self._DB_WARN_MB:
            logger.warning(
                "DB size WARNING | %.1f MB >= %d MB threshold — consider pruning old candles | path=%s",
                size_mb, self._DB_WARN_MB, self._path,
            )
        else:
            logger.info("DB size | %.1f MB | path=%s", size_mb, self._path)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self._path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # Schema                                                               #
    # ------------------------------------------------------------------ #

    def _init_schema(self):
        with self._conn() as conn:
            conn.executescript("""
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=NORMAL;
                CREATE TABLE IF NOT EXISTS candles (
                    instrument  TEXT    NOT NULL,
                    timeframe   TEXT    NOT NULL,
                    timestamp   TEXT    NOT NULL,
                    open        REAL    NOT NULL,
                    high        REAL    NOT NULL,
                    low         REAL    NOT NULL,
                    close       REAL    NOT NULL,
                    volume      INTEGER NOT NULL,
                    PRIMARY KEY (instrument, timeframe, timestamp)
                );

                CREATE TABLE IF NOT EXISTS orders (
                    order_id      TEXT    PRIMARY KEY,
                    instrument    TEXT    NOT NULL,
                    order_type    TEXT    NOT NULL,
                    product       TEXT    NOT NULL,
                    direction     TEXT    NOT NULL,
                    quantity      INTEGER NOT NULL,
                    price         REAL,
                    trigger_price REAL,
                    status        TEXT    NOT NULL,
                    mode          TEXT    NOT NULL,
                    placed_at     TEXT    NOT NULL,
                    updated_at    TEXT    NOT NULL
                );

                CREATE TABLE IF NOT EXISTS trades (
                    trade_id    TEXT    PRIMARY KEY,
                    order_id    TEXT    NOT NULL,
                    instrument  TEXT    NOT NULL,
                    direction   TEXT    NOT NULL,
                    quantity    INTEGER NOT NULL,
                    price       REAL    NOT NULL,
                    traded_at   TEXT    NOT NULL,
                    FOREIGN KEY (order_id) REFERENCES orders(order_id)
                );

                CREATE TABLE IF NOT EXISTS open_positions (
                    instrument  TEXT    PRIMARY KEY,
                    entry_price REAL    NOT NULL,
                    quantity    INTEGER NOT NULL,
                    held_bars   INTEGER NOT NULL DEFAULT 0,
                    entry_time  TEXT    NOT NULL
                );

                CREATE TABLE IF NOT EXISTS signals (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    logged_at     TEXT    NOT NULL,
                    instrument    TEXT    NOT NULL,
                    strategy      TEXT    NOT NULL,
                    direction     TEXT    NOT NULL,
                    signal_type   TEXT    NOT NULL,
                    price_hint    REAL    NOT NULL,
                    accepted      INTEGER NOT NULL,
                    reject_reason TEXT
                );

                CREATE TABLE IF NOT EXISTS state (
                    key   TEXT PRIMARY KEY,
                    value REAL NOT NULL
                );
            """)

    @staticmethod
    def _to_naive(dt: datetime) -> datetime:
        """Strip timezone info, keeping the wall-clock time (IST)."""
        return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt

    def get_state(self, key: str, default: float = 0.0) -> float:
        """Read a named float value from the state table."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM state WHERE key = ?", (key,)
            ).fetchone()
        return float(row[0]) if row else default

    def set_state(self, key: str, value: float) -> None:
        """Persist a named float value to the state table."""
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)",
                (key, value),
            )

    def clear_backtest_data(self):
        """Delete all data from all tables."""
        with self._conn() as conn:
            conn.executescript("DELETE FROM candles; DELETE FROM orders; DELETE FROM trades; DELETE FROM signals;")
        logger.info("Backtest DB cleared (candles, orders, trades, signals)")

    # ------------------------------------------------------------------ #
    # Candles                                                              #
    # ------------------------------------------------------------------ #

    def write_candle(self, instrument: str, timeframe: str, candle: dict):
        """Upsert a single live candle (dict with timestamp, open, high, low, close, volume)."""
        ts = self._to_naive(candle["timestamp"])
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO candles
                    (instrument, timeframe, timestamp, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    instrument, timeframe, ts.isoformat(),
                    candle["open"], candle["high"], candle["low"], candle["close"],
                    int(candle["volume"]),
                ),
            )

    def write_candles(self, instrument: str, timeframe: str, df: pd.DataFrame):
        """
        Upsert candles from a DataFrame with columns:
            timestamp (datetime), open, high, low, close, volume
        """
        if df.empty:
            return

        rows = [
            (
                instrument,
                timeframe,
                self._to_naive(row["timestamp"]).isoformat(),
                row["open"],
                row["high"],
                row["low"],
                row["close"],
                int(row["volume"]),
            )
            for _, row in df.iterrows()
        ]

        with self._conn() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO candles
                    (instrument, timeframe, timestamp, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        logger.debug("Wrote %d candles for %s [%s]", len(rows), instrument, timeframe)

    def read_candles(
        self,
        instrument: str,
        timeframe: str,
        from_dt: datetime,
        to_dt: datetime,
    ) -> pd.DataFrame:
        """Return candles as a DataFrame sorted by timestamp ascending."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT timestamp, open, high, low, close, volume
                FROM candles
                WHERE instrument = ? AND timeframe = ?
                  AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC
                """,
                (instrument, timeframe, from_dt.isoformat(), to_dt.isoformat()),
            ).fetchall()

        if not rows:
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df

    def latest_candle_timestamp(
        self, instrument: str, timeframe: str
    ) -> datetime | None:
        """Return the most recent candle timestamp we have cached, or None."""
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT MAX(timestamp) FROM candles
                WHERE instrument = ? AND timeframe = ?
                """,
                (instrument, timeframe),
            ).fetchone()
        value = row[0] if row else None
        if not value:
            return None
        return self._to_naive(datetime.fromisoformat(value))

    # ------------------------------------------------------------------ #
    # Orders                                                               #
    # ------------------------------------------------------------------ #

    def upsert_order(self, order: dict):
        """Insert or update an order record."""
        now = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO orders
                    (order_id, instrument, order_type, product, direction,
                     quantity, price, trigger_price, status, mode, placed_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(order_id) DO UPDATE SET
                    status     = excluded.status,
                    price      = COALESCE(excluded.price, orders.price),
                    updated_at = excluded.updated_at
                """,
                (
                    order["order_id"],
                    order["instrument"],
                    order["order_type"],
                    order["product"],
                    order["direction"],
                    order["quantity"],
                    order.get("price"),
                    order.get("trigger_price"),
                    order["status"],
                    order.get("mode", "live"),
                    order.get("placed_at", now),
                    now,
                ),
            )

    def log_signal(
        self,
        timestamp: datetime,
        instrument: str,
        strategy: str,
        direction: str,
        signal_type: str,
        price_hint: float,
        accepted: bool,
        reject_reason: str | None = None,
    ):
        """Record a signal validation event (accepted or rejected)."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO signals
                    (logged_at, instrument, strategy, direction, signal_type,
                     price_hint, accepted, reject_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self._to_naive(timestamp).isoformat(),
                    instrument,
                    strategy,
                    direction,
                    signal_type,
                    price_hint,
                    1 if accepted else 0,
                    reject_reason,
                ),
            )

    # ------------------------------------------------------------------ #
    # Open positions (paper mode persistence)                              #
    # ------------------------------------------------------------------ #

    def upsert_open_position(self, instrument: str, entry_price: float,
                             quantity: int, held_bars: int, entry_time: datetime):
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO open_positions (instrument, entry_price, quantity, held_bars, entry_time)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(instrument) DO UPDATE SET
                    entry_price = excluded.entry_price,
                    quantity    = excluded.quantity,
                    held_bars   = excluded.held_bars,
                    entry_time  = excluded.entry_time
                """,
                (instrument, entry_price, quantity, held_bars,
                 self._to_naive(entry_time).isoformat()),
            )

    def delete_open_position(self, instrument: str):
        with self._conn() as conn:
            conn.execute("DELETE FROM open_positions WHERE instrument = ?", (instrument,))

    def read_open_positions(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT instrument, entry_price, quantity, held_bars, entry_time FROM open_positions"
            ).fetchall()
        return [dict(r) for r in rows]

    def read_pending_live_orders(self) -> list[dict]:
        """Return today's live BUY orders still in PENDING state (unfilled on restart)."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT instrument, quantity, price
                FROM orders
                WHERE status = 'PENDING'
                  AND mode   = 'live'
                  AND direction = 'BUY'
                  AND date(placed_at) = date('now', 'localtime')
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def write_trade(self, trade: dict):
        """Record a filled trade."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO trades
                    (trade_id, order_id, instrument, direction, quantity, price, traded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade["trade_id"],
                    trade["order_id"],
                    trade["instrument"],
                    trade["direction"],
                    trade["quantity"],
                    trade["price"],
                    trade.get("traded_at", datetime.now().isoformat()),
                ),
            )
