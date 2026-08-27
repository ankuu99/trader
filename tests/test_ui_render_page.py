"""render_page smoke tests — the dashboard is one large f-string, so the only
way to catch a broken brace/undefined name is to render it. Uses the real
Config singleton (reads config/config.yaml), a temp Store and a fresh
RiskManager, exactly what main.py hands the server thread.

Also pins the mobile/return-stats contract: viewport + JS refresh (no meta
refresh outside <noscript>), column-pruning table classes, and the return row
with the Nifty benchmark sourced from `day` candles in the same DB."""

from datetime import datetime, timedelta

import pandas as pd
import pytest

from trader.analytics import BENCHMARK_INSTRUMENT
from trader.core.config import config
from trader.data.store import Store
from trader.risk.manager import RiskManager
from trader.ui.state import BotState
from trader.ui.template import render_page, _render_return_row, _pnl_class


@pytest.fixture
def ctx(tmp_path):
    # db_path is a read-only property over the raw yaml dict (ROOT / data.db_path);
    # point it at the temp DB via the dict, same pattern as test_capital_seeding.
    store = Store(tmp_path / "ui.db")
    orig = config._data["data"]["db_path"]
    config._data["data"]["db_path"] = str(tmp_path / "ui.db")
    try:
        yield BotState(), RiskManager(), store
    finally:
        config._data["data"]["db_path"] = orig


def _order(store, oid, inst, direction, qty, price, ts):
    store.upsert_order({
        "order_id": oid, "instrument": inst, "order_type": "MARKET", "product": "CNC",
        "direction": direction, "quantity": qty, "price": price, "trigger_price": None,
        "status": "COMPLETE", "mode": "live", "placed_at": ts.isoformat(),
        "updated_at": ts.isoformat(),
    })


def test_render_page_empty_db(ctx):
    bot_state, risk, store = ctx
    html = render_page(bot_state, risk, store, config)
    assert "<title>Trader</title>" in html
    # Mobile contract: viewport, JS refresh, meta-refresh only as noscript fallback
    assert 'name="viewport"' in html
    assert "<script>" in html and "visibilitychange" in html
    assert '<noscript><meta http-equiv="refresh" content="30"></noscript>' in html
    assert html.count('http-equiv="refresh"') == 1
    assert "@media (max-width: 720px)" in html
    assert 'id="allcols"' in html
    # No trades → no return row, and no stale inline pane widths
    assert 'class="retrow"' not in html
    assert 'style="flex:1;min-width:280px"' not in html


def test_render_page_with_trades_shows_return_row_and_benchmark(ctx):
    bot_state, risk, store = ctx
    t0 = datetime.now() - timedelta(days=120)
    _order(store, "o1", "NSE:ABC", "BUY", 10, 100.0, t0)
    _order(store, "o2", "NSE:ABC", "SELL", 10, 110.0, t0 + timedelta(days=3))
    _order(store, "o3", "NSE:XYZ", "BUY", 5, 200.0, t0 + timedelta(days=10))
    _order(store, "o4", "NSE:XYZ", "SELL", 5, 190.0, t0 + timedelta(days=12))
    # Nifty daily closes across the window → benchmark tile gets a number
    days = pd.date_range(t0.date(), periods=121, freq="D")
    store.write_candles(BENCHMARK_INSTRUMENT, "day", pd.DataFrame({
        "timestamp": days, "open": 20000.0, "high": 20100.0, "low": 19900.0,
        "close": [20000.0 + i * 10 for i in range(len(days))], "volume": 0,
    }))

    html = render_page(bot_state, risk, store, config)

    assert 'class="retrow"' in html
    assert "Cum return" in html and "Annualized" in html and "p.a." in html
    assert "Nifty 50" in html
    assert "no daily candles cached" not in html      # benchmark found
    assert "trade-matched:" in html and "ours gross" in html   # same-notional counterfactual
    assert 'class="t-trades"' in html and 'class="t-score"' in html
    # 120-day span clears the 90-day guard → annualized headline present, not the "<90 d" note
    assert "&lt;90 d" not in html


def test_render_page_short_window_blanks_annualized(ctx):
    bot_state, risk, store = ctx
    t0 = datetime.now() - timedelta(days=5)
    _order(store, "o1", "NSE:ABC", "BUY", 10, 100.0, t0)
    _order(store, "o2", "NSE:ABC", "SELL", 10, 105.0, t0 + timedelta(days=1))
    html = render_page(bot_state, risk, store, config, range_params={"range": "1w"})
    assert 'class="retrow"' in html
    assert "&lt;90 d" in html                            # guard engaged
    assert "no daily candles cached" in html             # nothing cached for Nifty


def test_render_return_row_handles_missing_pieces():
    ret = {"cum_pct": 1.0, "ann_pct": None, "days": 30.0, "min_days": 90,
           "deployed_cum_pct": None, "deployed_ann_pct": None,
           "mtm_cum_pct": None, "mtm_ann_pct": None, "annualized": False}
    html = _render_return_row(ret, {"cum_pct": None}, 400_000.0, 0.0, _pnl_class)
    assert "+1.0%" in html and "&lt;90 d" in html and "on deployed: —" in html
    assert "Incl. open" not in html
    assert _render_return_row({"cum_pct": None}, {}, 1.0, 0.0, _pnl_class) == ""
