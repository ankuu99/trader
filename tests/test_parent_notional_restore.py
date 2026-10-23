"""TD-015: the parent lot's ORIGINAL notional is persisted so the first add-on is sized
the same after a scale-out + reboot as it would be without the reboot."""
import sqlite3
from datetime import datetime

from tests.test_scale_in import _scale_in_config
from trader.data.store import Store
from trader.risk.manager import RiskManager

INST = "NSE:TEST"
TS = datetime(2026, 6, 1, 10, 0)


def _store(tmp_path):
    s = Store(tmp_path / "t.db")
    s.upsert_open_position(INST, 500.0, 100, 0, TS)
    return s


def test_upsert_stores_parent_notional(tmp_path):
    s = _store(tmp_path)
    assert s.read_open_positions()[0]["parent_notional"] == 50_000


def test_scaleout_does_not_shrink_parent_notional(tmp_path):
    s = _store(tmp_path)
    s.consume_position_lots(INST, 50)
    pos = s.read_open_positions()[0]
    assert pos["quantity"] == 50
    assert pos["parent_notional"] == 50_000


def test_reboot_after_scaleout_sizes_addon_like_memory(tmp_path):
    with _scale_in_config():
        a = RiskManager()
        a.on_order_filled(INST, 500.0, 100)
        a.reduce_position(INST, 50, 520.0)

        s = _store(tmp_path)
        s.consume_position_lots(INST, 50)
        pos = s.read_open_positions()[0]
        b = RiskManager()
        b.seed_position(INST, pos["quantity"], pos["entry_price"], entry_ts=TS)
        b.restore_parent_notional(INST, pos["parent_notional"])

        assert a._scale_in[INST]["last_lot_notional"] == 50_000
        assert b._scale_in[INST]["last_lot_notional"] == 50_000


def test_legacy_row_keeps_old_behaviour():
    with _scale_in_config():
        r = RiskManager()
        r.seed_position(INST, 50, 500.0)
        r.restore_parent_notional(INST, 0.0)
        assert r._scale_in[INST]["last_lot_notional"] == 25_000


def test_addon_lot_notional_still_wins():
    with _scale_in_config():
        r = RiskManager()
        r.seed_position(INST, 50, 500.0)
        r.restore_parent_notional(INST, 50_000)
        r.seed_scale_in(INST, [{"price": 480.0, "qty": 0, "notional": 24_000.0,
                                "date": "2026-06-02T10:00:00"}])
        assert r._scale_in[INST]["last_lot_notional"] == 24_000


def test_migration_adds_column(tmp_path):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE open_positions (
        instrument TEXT PRIMARY KEY, entry_price REAL NOT NULL, quantity INTEGER NOT NULL,
        held_bars INTEGER NOT NULL DEFAULT 0, entry_time TEXT NOT NULL,
        current_price REAL DEFAULT 0, pct_change REAL DEFAULT 0, unrealised_pnl REAL DEFAULT 0,
        peak_close REAL DEFAULT 0, trailing_active INTEGER DEFAULT 0, low_since_entry REAL DEFAULT 0,
        pattern_top_trailing INTEGER DEFAULT 0, addon_lots TEXT, partial_taken INTEGER DEFAULT 0,
        breakeven_active INTEGER DEFAULT 0)""")
    conn.execute("INSERT INTO open_positions (instrument, entry_price, quantity, entry_time) "
                 "VALUES (?, 500.0, 100, ?)", (INST, TS.isoformat()))
    conn.commit()
    conn.close()
    s = Store(db)
    assert s.read_open_positions()[0]["parent_notional"] == 0.0
