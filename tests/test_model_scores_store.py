"""
model_scores persistence (#1 UI conviction trajectory).

write_model_score upserts per (instrument, timestamp), trims to the most recent
`keep` rows per instrument, and get_model_scores returns them oldest-first so the
UI can plot left-to-right.
"""
from datetime import datetime

from trader.data.store import Store


def test_write_and_read_chronological(tmp_path):
    store = Store(tmp_path / "ms.db")
    for i in range(5):
        store.write_model_score("NSE:TEST", f"2026-01-0{i + 1}T09:15:00", 0.1 * i, 0.9 - 0.1 * i)

    rows = store.get_model_scores("NSE:TEST")
    assert [r["timestamp"] for r in rows] == [
        "2026-01-01T09:15:00", "2026-01-02T09:15:00", "2026-01-03T09:15:00",
        "2026-01-04T09:15:00", "2026-01-05T09:15:00",
    ]
    assert rows[0]["p_min"] == 0.0
    assert rows[-1]["p_max"] == 0.5


def test_upsert_same_timestamp(tmp_path):
    store = Store(tmp_path / "ms.db")
    store.write_model_score("NSE:TEST", "2026-01-01T09:15:00", 0.2, 0.8)
    store.write_model_score("NSE:TEST", "2026-01-01T09:15:00", 0.7, 0.3)
    rows = store.get_model_scores("NSE:TEST")
    assert len(rows) == 1
    assert rows[0]["p_min"] == 0.7


def test_retention_trim(tmp_path):
    store = Store(tmp_path / "ms.db")
    for i in range(10):
        store.write_model_score("NSE:TEST", f"2026-01-{i + 1:02d}T09:15:00", 0.5, 0.5, keep=3)
    rows = store.get_model_scores("NSE:TEST", limit=100)
    assert len(rows) == 3
    # The three most-recent timestamps survive.
    assert rows[0]["timestamp"] == "2026-01-08T09:15:00"
    assert rows[-1]["timestamp"] == "2026-01-10T09:15:00"


def test_accepts_datetime_timestamp(tmp_path):
    store = Store(tmp_path / "ms.db")
    store.write_model_score("NSE:TEST", datetime(2026, 1, 1, 9, 15), 0.4, 0.6)
    rows = store.get_model_scores("NSE:TEST")
    assert len(rows) == 1


def test_per_instrument_isolation(tmp_path):
    store = Store(tmp_path / "ms.db")
    store.write_model_score("NSE:AAA", "2026-01-01T09:15:00", 0.4, 0.6)
    store.write_model_score("NSE:BBB", "2026-01-01T09:15:00", 0.1, 0.9)
    assert len(store.get_model_scores("NSE:AAA")) == 1
    assert store.get_model_scores("NSE:AAA")[0]["p_min"] == 0.4
