"""
FVMStore — point-in-time (PIT) fundamentals store for the FVM strategy.

Isolated from the live trading DB (`market.db`): FVM fundamentals live in their own
SQLite file so nothing here can destabilise the live system. Price candles are read
from the existing `trader.data.store.Store` (reused, not duplicated).

Design: append-only, VINTAGED. Fundamentals are stored as an EAV (entity-attribute-value)
table keyed by (symbol, statement, basis, period, field, knowledge_date). A read "as of
date T" returns, per period, the value with the latest knowledge_date <= T — this is what
makes backtests point-in-time correct (no lookahead). We never overwrite a vintage.

Tables
------
fund_stocks     : master list (symbol -> stock_hash) from Trendlyne all_stocks
fundamentals    : EAV vintaged financials (P&L / BS / CF), quarterly + annual
shareholding    : EAV vintaged ownership (promoter/FII/DII/pledge/holders), quarterly
index_membership: PIT index constituents (schema created here; populated in Phase 0.3)
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from trader.core.logger import get_logger

logger = get_logger(__name__)


class FVMStore:
    def __init__(self, db_path: Path | str = "data/fvm.db"):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = str(db_path)
        self._init_schema()

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

    def _init_schema(self):
        with self._conn() as conn:
            conn.executescript("""
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=NORMAL;

                CREATE TABLE IF NOT EXISTS fund_stocks (
                    nsecode    TEXT PRIMARY KEY,
                    isin       TEXT,
                    bsecode    TEXT,
                    name       TEXT,
                    stock_hash TEXT NOT NULL,
                    currency   TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS fundamentals (
                    symbol         TEXT NOT NULL,   -- NSE code
                    statement      TEXT NOT NULL,   -- 'quarter' | 'annual'
                    basis          TEXT NOT NULL,   -- 'consolidated' | 'standalone'
                    period         TEXT NOT NULL,   -- fiscal period end, e.g. '2026-03'
                    field          TEXT NOT NULL,   -- normalized parameter name
                    value          REAL,
                    knowledge_date TEXT NOT NULL,   -- date this became knowable (announce date / lag)
                    ingested_at    TEXT NOT NULL,
                    source         TEXT NOT NULL DEFAULT 'trendlyne',
                    PRIMARY KEY (symbol, statement, basis, period, field, knowledge_date)
                );
                CREATE INDEX IF NOT EXISTS ix_fund_lookup
                    ON fundamentals (symbol, statement, basis, field, period);

                CREATE TABLE IF NOT EXISTS shareholding (
                    symbol         TEXT NOT NULL,
                    period         TEXT NOT NULL,   -- quarter end '2026-03'
                    field          TEXT NOT NULL,   -- promoter|fii|dii|pledge|holders|...
                    value          REAL,
                    knowledge_date TEXT NOT NULL,
                    ingested_at    TEXT NOT NULL,
                    source         TEXT NOT NULL DEFAULT 'screener',
                    PRIMARY KEY (symbol, period, field, knowledge_date)
                );

                CREATE TABLE IF NOT EXISTS index_membership (
                    index_name TEXT NOT NULL,       -- e.g. 'NIFTY500'
                    symbol     TEXT NOT NULL,
                    start_date TEXT NOT NULL,        -- inclusive
                    end_date   TEXT,                 -- NULL = still a member
                    PRIMARY KEY (index_name, symbol, start_date)
                );

                CREATE TABLE IF NOT EXISTS sector_map (
                    symbol     TEXT PRIMARY KEY,
                    sector     TEXT NOT NULL,         -- NSE/AMFI macro industry
                    source     TEXT NOT NULL DEFAULT 'niftyindices',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS journal (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol     TEXT NOT NULL,
                    asof       TEXT NOT NULL,          -- study as-of date
                    verdict    TEXT NOT NULL,          -- the user's call (BUY/WATCH/AVOID/...)
                    thesis     TEXT NOT NULL,          -- one-liner: why
                    price      REAL,                   -- last price when the call was made
                    created_at TEXT NOT NULL
                );
            """)

    # ---------------------------------------------------------------- #
    # Master list (symbol -> stock_hash)                               #
    # ---------------------------------------------------------------- #

    def upsert_stocks(self, rows: list[dict]) -> int:
        """rows: dicts with nsecode, isin, bsecode, name, stock_hash, currency."""
        now = datetime.now().isoformat(timespec="seconds")
        payload = [
            (r["nsecode"], r.get("isin"), r.get("bsecode"), r.get("name"),
             r["stock_hash"], r.get("currency"), now)
            for r in rows if r.get("nsecode") and r.get("stock_hash")
        ]
        with self._conn() as conn:
            conn.executemany(
                """INSERT INTO fund_stocks (nsecode, isin, bsecode, name, stock_hash, currency, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(nsecode) DO UPDATE SET
                     isin=excluded.isin, bsecode=excluded.bsecode, name=excluded.name,
                     stock_hash=excluded.stock_hash, currency=excluded.currency,
                     updated_at=excluded.updated_at""",
                payload,
            )
        logger.info("fund_stocks upserted | %d rows", len(payload))
        return len(payload)

    def get_stock_hash(self, nsecode: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT stock_hash FROM fund_stocks WHERE nsecode = ?", (nsecode.upper(),)
            ).fetchone()
        return row[0] if row else None

    def count_stocks(self) -> int:
        with self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM fund_stocks").fetchone()[0]

    # ---------------------------------------------------------------- #
    # Fundamentals (EAV vintaged)                                      #
    # ---------------------------------------------------------------- #

    def write_fundamentals(self, rows: list[dict]) -> int:
        """rows: dicts with symbol, statement, basis, period, field, value,
        knowledge_date (str). Append-only vintage; re-ingesting same vintage is a no-op."""
        now = datetime.now().isoformat(timespec="seconds")
        payload = [
            (r["symbol"], r["statement"], r["basis"], r["period"], r["field"],
             (None if r.get("value") is None else float(r["value"])),
             r["knowledge_date"], now, r.get("source", "trendlyne"))
            for r in rows
        ]
        with self._conn() as conn:
            conn.executemany(
                """INSERT OR IGNORE INTO fundamentals
                   (symbol, statement, basis, period, field, value, knowledge_date, ingested_at, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                payload,
            )
        return len(payload)

    def read_fundamental_asof(self, symbol: str, statement: str, basis: str,
                              field: str, asof: str) -> dict[str, float]:
        """Per-period value with the latest knowledge_date <= `asof` (PIT). Returns
        {period: value} for the given (symbol, statement, basis, field)."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT period, value FROM fundamentals f
                   WHERE symbol=? AND statement=? AND basis=? AND field=? AND knowledge_date<=?
                     AND knowledge_date = (
                        SELECT MAX(knowledge_date) FROM fundamentals
                        WHERE symbol=f.symbol AND statement=f.statement AND basis=f.basis
                          AND field=f.field AND period=f.period AND knowledge_date<=?)
                   ORDER BY period""",
                (symbol.upper(), statement, basis, field, asof, asof),
            ).fetchall()
        return {r[0]: (None if r[1] is None else float(r[1])) for r in rows}

    # ---------------------------------------------------------------- #
    # Shareholding (EAV vintaged) — used by the Screener adapter        #
    # ---------------------------------------------------------------- #

    def write_shareholding(self, rows: list[dict]) -> int:
        """rows: dicts with symbol, period ('YYYY-MM'), field (promoter|fii|dii|
        pledge|holders|...), value, knowledge_date (str), source (default 'screener').
        Append-only vintage; re-ingesting the same vintage is a no-op."""
        now = datetime.now().isoformat(timespec="seconds")
        payload = [
            (r["symbol"].upper(), r["period"], r["field"],
             (None if r.get("value") is None else float(r["value"])),
             r["knowledge_date"], now, r.get("source", "screener"))
            for r in rows
        ]
        with self._conn() as conn:
            conn.executemany(
                """INSERT OR IGNORE INTO shareholding
                   (symbol, period, field, value, knowledge_date, ingested_at, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                payload,
            )
        return len(payload)

    def read_shareholding_asof(self, symbol: str, field: str, asof: str) -> dict[str, float]:
        """Per-period shareholding value with latest knowledge_date <= `asof` (PIT)."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT period, value FROM shareholding s
                   WHERE symbol=? AND field=? AND knowledge_date<=?
                     AND knowledge_date = (
                        SELECT MAX(knowledge_date) FROM shareholding
                        WHERE symbol=s.symbol AND field=s.field AND period=s.period
                          AND knowledge_date<=?)
                   ORDER BY period""",
                (symbol.upper(), field, asof, asof),
            ).fetchall()
        return {r[0]: (None if r[1] is None else float(r[1])) for r in rows}

    # ---------------------------------------------------------------- #
    # Index membership (PIT) — used by the NSE adapter                  #
    # ---------------------------------------------------------------- #

    def write_membership(self, rows: list[dict]) -> int:
        """rows: dicts with index_name, symbol, start_date ('YYYY-MM-DD'),
        end_date (str|None). Intervals of membership; end_date NULL = current member."""
        payload = [
            (r["index_name"], r["symbol"].upper(), r["start_date"], r.get("end_date"))
            for r in rows
        ]
        with self._conn() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO index_membership
                   (index_name, symbol, start_date, end_date) VALUES (?, ?, ?, ?)""",
                payload,
            )
        return len(payload)

    def members_asof(self, index_name: str, asof: str) -> list[str]:
        """Symbols that were constituents of `index_name` on date `asof` (PIT)."""
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT DISTINCT symbol FROM index_membership
                   WHERE index_name=? AND start_date<=?
                     AND (end_date IS NULL OR end_date> ?)
                   ORDER BY symbol""",
                (index_name, asof, asof),
            ).fetchall()
        return [r[0] for r in rows]

    # ---------------------------------------------------------------- #
    # Thesis journal — record a call, resurface it later                #
    # ---------------------------------------------------------------- #

    def write_journal(self, symbol: str, asof: str, verdict: str, thesis: str,
                      price: float | None = None) -> int:
        """Record a thesis. Returns the new entry id."""
        now = datetime.now().isoformat(timespec="seconds")
        with self._conn() as conn:
            cur = conn.execute(
                """INSERT INTO journal (symbol, asof, verdict, thesis, price, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (symbol.upper(), asof, verdict, thesis,
                 None if price is None else float(price), now))
            return cur.lastrowid

    def read_journal(self, symbol: str | None = None) -> list[dict]:
        """Journal entries, newest first; all symbols when `symbol` is None."""
        q = "SELECT id, symbol, asof, verdict, thesis, price, created_at FROM journal"
        args: tuple = ()
        if symbol:
            q += " WHERE symbol=?"
            args = (symbol.upper(),)
        q += " ORDER BY created_at DESC, id DESC"
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(q, args).fetchall()]

    def delete_journal(self, entry_id: int) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM journal WHERE id=?", (entry_id,))

    # ---------------------------------------------------------------- #
    # Sector map (financials-exclusion + sector-relative normalization) #
    # ---------------------------------------------------------------- #

    def write_sectors(self, rows: list[dict]) -> int:
        """rows: dicts with symbol, sector, source (default 'niftyindices')."""
        now = datetime.now().isoformat(timespec="seconds")
        payload = [(r["symbol"].upper(), r["sector"], r.get("source", "niftyindices"), now)
                   for r in rows if r.get("symbol") and r.get("sector")]
        with self._conn() as conn:
            conn.executemany(
                """INSERT INTO sector_map (symbol, sector, source, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(symbol) DO UPDATE SET
                     sector=excluded.sector, source=excluded.source, updated_at=excluded.updated_at""",
                payload,
            )
        return len(payload)

    def get_sector(self, symbol: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute("SELECT sector FROM sector_map WHERE symbol=?",
                               (symbol.upper(),)).fetchone()
        return row[0] if row else None

    def sectors_map(self) -> dict[str, str]:
        with self._conn() as conn:
            rows = conn.execute("SELECT symbol, sector FROM sector_map").fetchall()
        return {r[0]: r[1] for r in rows}
