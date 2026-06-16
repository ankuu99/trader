"""
Persistent-State UI routes (D2): cumulative_pnl reset + clear-stale.

Exercises the Flask routes against a real RiskManager + Store via a test client.
The reset must update BOTH the live risk object and the persisted state so the next
close can't clobber it; clear-stale must drop position-linked rows only for
instruments that aren't currently open.
"""
import pytest

from trader.data.store import Store
from trader.risk.manager import RiskManager
from trader.ui.server import build_app


@pytest.fixture
def ctx(tmp_path):
    store = Store(tmp_path / "ui.db")
    risk = RiskManager()
    app = build_app(bot_state=None, risk=risk, store=store, config=None)
    app.config.update(TESTING=True)
    return app.test_client(), risk, store


def test_reset_pnl_updates_memory_and_persists(ctx):
    client, risk, store = ctx
    risk.seed_cumulative_pnl(-71_473.18)
    store.set_state("cumulative_pnl", -71_473.18)

    resp = client.post("/reset_pnl", data={"value": "0"})

    assert resp.status_code == 303
    assert risk.cumulative_pnl == 0.0                       # live object updated
    assert store.get_state("cumulative_pnl") == 0.0         # persisted (won't be clobbered)


def test_reset_pnl_accepts_explicit_value(ctx):
    client, risk, store = ctx
    client.post("/reset_pnl", data={"value": "1234.50"})
    assert risk.cumulative_pnl == pytest.approx(1234.50)
    assert store.get_state("cumulative_pnl") == pytest.approx(1234.50)


def test_reset_pnl_ignores_garbage(ctx):
    client, risk, store = ctx
    risk.seed_cumulative_pnl(-100.0)
    store.set_state("cumulative_pnl", -100.0)
    resp = client.post("/reset_pnl", data={"value": "abc"})
    assert resp.status_code == 303
    assert risk.cumulative_pnl == -100.0                    # unchanged
    assert store.get_state("cumulative_pnl") == -100.0


def test_clear_stale_state_drops_only_flat_instruments(ctx):
    client, risk, store = ctx
    risk.seed_position("NSE:OPEN", qty=10, avg_price=100.0)  # currently open
    store.set_state("NSE:OPEN.peak_close", 110.0)
    store.set_state("NSE:OPEN.max_gain_pct", 5.0)
    store.set_state("NSE:CLOSED.peak_close", 50.0)          # stale
    store.set_state("BSE:GHOST.max_gain_pct", 1.0)          # stale cruft
    store.set_state("NSE:AQYLON.paused", 1.0)               # control — must survive
    store.set_state("cumulative_pnl", -100.0)               # cumulative — must survive

    resp = client.post("/clear_stale_state")

    assert resp.status_code == 303
    keys = {r["key"] for r in store.read_state()}
    assert "NSE:OPEN.peak_close" in keys                    # open → kept
    assert "NSE:OPEN.max_gain_pct" in keys
    assert "NSE:AQYLON.paused" in keys                      # control → kept
    assert "cumulative_pnl" in keys                         # cumulative → kept
    assert "NSE:CLOSED.peak_close" not in keys              # flat → dropped
    assert "BSE:GHOST.max_gain_pct" not in keys             # cruft → dropped
