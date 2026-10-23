"""
Exit-policy flags survive a restart (MAYURUNIQ 2026-10-12 → 14).

A pattern-top scale-out sets partial_taken and arms the remainder trail
(trailing_active + pattern_top_trailing). Restart restored only peak_close /
max_gain_pct, so the remainder came back with NO trail (13 Oct low 770.45 sat
below the 4% trail at ~779.5 — nothing fired) and the once-per-position
scale-out re-armed (14 Oct 15:15 sold half again). The flags are now persisted
in open_positions — per decision candle and at the scale-out fill — and
seed_position_state restores them.
"""
import sqlite3
from datetime import datetime

from trader.data.store import Store
from trader.strategies.base import Direction, SignalType
from trader.strategies.lr_extrema import LRExtremaStrategy

_FLAGS = ("trailing_active", "pattern_top_trailing", "partial_taken", "breakeven_active")

# MAYURUNIQ's day-TF exit block: trail 4%, arm at +10%, no EOD force-close.
_PARAMS = {
    "warmup_bars": 5, "threshold": 0.82, "retrain_every": 50, "extrema_order": 2,
    "profit_pct": 10.0, "trail_pct": 4.0, "stop_pct": 20.0, "hold_bars": 40,
    "sell_min_pct": 7.0, "force_close_time": None,
    "pattern_top_floor_enabled": False,  # live config (code default is True)
    "pattern_top_scale_out_enabled": True, "pattern_top_scale_out_fraction": 0.5,
}
_ENTRY = 749.12


def _restored_strategy(store: Store, inst: str) -> LRExtremaStrategy:
    """Mirror main.py's live restore: synthetic entry fill, then seed from DB."""
    [pos] = [p for p in store.read_open_positions() if p["instrument"] == inst]
    strat = LRExtremaStrategy(inst, _PARAMS)
    strat.on_order_update({
        "status": "COMPLETE", "signal_type": SignalType.ENTRY, "direction": "BUY",
        "price": pos["entry_price"], "instrument": inst, "_held_bars": 28,
    })
    strat.seed_position_state(store.get_state(f"{inst}.peak_close", 0.0),
                              store.get_state(f"{inst}.max_gain_pct", 0.0),
                              {k: pos[k] for k in _FLAGS if k in pos})
    return strat


def _seed_scaled_out_position(store: Store, inst: str) -> None:
    store.upsert_open_position(inst, _ENTRY, 27, 27, datetime(2026, 9, 1, 15, 15))
    store.set_state(f"{inst}.peak_close", 812.0)
    store.set_state(f"{inst}.max_gain_pct", 7.52)
    # What main.handle_order_update writes at the scale-out fill.
    store.save_exit_flags(inst, trailing_active=True, pattern_top_trailing=True,
                          partial_taken=True, breakeven_active=False)


def test_scaled_out_remainder_keeps_trail_and_scale_out_guard(tmp_path):
    store = Store(tmp_path / "t.db")
    _seed_scaled_out_position(store, "NSE:MAYURUNIQ")

    strat = _restored_strategy(store, "NSE:MAYURUNIQ")
    pos = strat._pos
    assert (pos.trailing_active, pos.pattern_top_trailing, pos.partial_taken) == (True, True, True)
    assert pos.peak_close == 812.0

    # 13 Oct: price drops through peak × 0.96 = 779.52 → the remainder trail fires.
    assert strat.on_tick({"last_price": 785.0, "timestamp": datetime(2026, 10, 13, 11, 0)}) is None
    sig = strat.on_tick({"last_price": 779.0, "timestamp": datetime(2026, 10, 13, 11, 5)})
    assert sig is not None and sig.signal_type == SignalType.EXIT
    assert sig.exit_reason == "TRAILING"


def test_without_flags_restore_is_unprotected_regression_shape(tmp_path):
    """The pre-fix behaviour, pinned so the test above means something: no flags →
    gain 4% < profit_pct 10% leaves the trail off and the drop does not exit."""
    store = Store(tmp_path / "t.db")
    store.upsert_open_position("NSE:X", _ENTRY, 27, 27, datetime(2026, 9, 1, 15, 15))
    store.set_state("NSE:X.peak_close", 812.0)
    strat = _restored_strategy(store, "NSE:X")
    assert not strat._pos.trailing_active and not strat._pos.partial_taken
    assert strat.on_tick({"last_price": 779.0, "timestamp": datetime(2026, 10, 13, 11, 5)}) is None


def test_update_position_metrics_none_keeps_stored_flags(tmp_path):
    store = Store(tmp_path / "t.db")
    _seed_scaled_out_position(store, "NSE:A")
    # Per-candle write from a caller that doesn't know the scale-out flags.
    store.update_position_metrics("NSE:A", 28, 790.0, 5.4, 1100.0, 812.0, True,
                                  780.0, pattern_top_trailing=True)
    [p] = store.read_open_positions()
    assert p["partial_taken"] is True
    store.update_position_metrics("NSE:A", 29, 790.0, 5.4, 1100.0, 812.0, False,
                                  780.0, partial_taken=False, breakeven_active=True)
    [p] = store.read_open_positions()
    assert (p["trailing_active"], p["partial_taken"], p["breakeven_active"]) == (False, False, True)


def test_new_entry_after_close_starts_with_clean_flags(tmp_path):
    store = Store(tmp_path / "t.db")
    _seed_scaled_out_position(store, "NSE:A")
    store.delete_open_position("NSE:A")
    store.upsert_open_position("NSE:A", 700.0, 30, 0, datetime(2026, 10, 20, 10, 0))
    [p] = store.read_open_positions()
    assert not any(p[k] for k in _FLAGS)


def test_migration_adds_flag_columns_to_existing_db(tmp_path):
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.execute("""CREATE TABLE open_positions (
        instrument TEXT PRIMARY KEY, entry_price REAL NOT NULL, quantity INTEGER NOT NULL,
        held_bars INTEGER NOT NULL DEFAULT 0, entry_time TEXT NOT NULL,
        trailing_active INTEGER DEFAULT 0, pattern_top_trailing INTEGER DEFAULT 0)""")
    con.execute("INSERT INTO open_positions VALUES ('NSE:A', 100.0, 5, 3, '2026-10-01T10:00:00', 1, 1)")
    con.commit()
    con.close()
    con = sqlite3.connect(db)
    con.execute("INSERT INTO open_positions VALUES ('NSE:B', 50.0, 5, 3, '2026-10-01T10:00:00', 1, 0)")
    con.commit()
    con.close()
    rows = {p["instrument"]: p for p in Store(db).read_open_positions()}
    a, b = rows["NSE:A"], rows["NSE:B"]
    assert (a["trailing_active"], a["pattern_top_trailing"]) == (True, True)
    # Already-scaled-out position (pattern-top trail armed) keeps its scale-out guard.
    assert (a["partial_taken"], a["breakeven_active"]) == (True, False)
    # A plain profit_pct trail never scaled out.
    assert (b["trailing_active"], b["partial_taken"]) == (True, False)
    # Re-opening the store does not re-run the backfill.
    Store(db).save_exit_flags("NSE:B", True, False, False, False)
    assert not {p["instrument"]: p for p in Store(db).read_open_positions()}["NSE:B"]["partial_taken"]


def test_seed_without_flags_is_backward_compatible():
    strat = LRExtremaStrategy("NSE:T", _PARAMS)
    strat.position = Direction.BUY
    strat._pos.entry_price = 100.0
    strat.seed_position_state(105.0, 5.0)
    assert strat._pos.peak_close == 105.0 and not strat._pos.trailing_active
