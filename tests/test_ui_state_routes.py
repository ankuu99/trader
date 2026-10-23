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


def test_token_reload_invokes_bot_state_callback(tmp_path):
    from trader.ui.state import BotState

    store = Store(tmp_path / "ui2.db")
    bot_state = BotState()
    calls = []
    bot_state.reload_token = lambda source: calls.append(source)
    app = build_app(bot_state=bot_state, risk=RiskManager(), store=store, config=None)
    app.config.update(TESTING=True)

    resp = app.test_client().post("/token/reload")

    assert resp.status_code == 303
    assert calls == ["ui-reload"]


def test_token_reload_safe_without_callback(ctx):
    client, _, _ = ctx  # bot_state=None in the fixture
    resp = client.post("/token/reload")
    assert resp.status_code == 303


def test_token_reload_survives_callback_exception(tmp_path):
    from trader.ui.state import BotState

    store = Store(tmp_path / "ui3.db")
    bot_state = BotState()
    def boom(source):
        raise RuntimeError("kite down")
    bot_state.reload_token = boom
    app = build_app(bot_state=bot_state, risk=RiskManager(), store=store, config=None)
    app.config.update(TESTING=True)

    resp = app.test_client().post("/token/reload")
    assert resp.status_code == 303  # never 500s the dashboard
