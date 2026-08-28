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
    assert "vs Nifty" in html and " pp</span>" in html   # per-stock trade-matched column
    # Rolling windows row: inception (120 d) annualized, 1M under the guard
    assert 'class="t-roll"' in html and "Inception" in html
    assert "under the 90-day guard" in html
    assert "at our exit dates" in html and 'stroke="#58a6ff" stroke-width="1.1"' in html   # Nifty overlay
    # 120-day span clears the 90-day guard → annualized headline present, not the "<90 d" note
    assert "&lt;90 d" not in html


def test_render_page_open_positions_show_stop_risk(ctx):
    bot_state, risk, store = ctx
    e = datetime.now() - timedelta(days=2)
    _order(store, "ob", "NSE:ABC", "BUY", 10, 100.0, e)
    store.upsert_open_position("NSE:ABC", 100.0, 10, 5, e, low_since_entry=99.0)
    # current 104, trailing OFF → effective stop = hard stop (100 × (1 − stop_pct))
    store.update_position_metrics("NSE:ABC", 5, 104.0, 4.0, 40.0, 104.0, False)
    html = render_page(bot_state, risk, store, config)
    assert "If every stop hits:" in html
    assert "at risk &#8377;" in html          # per-row exposure to the effective stop
    assert "locked in" in html               # portfolio summary line present


def test_render_page_health_strip_all_clear_and_flags(ctx):
    bot_state, risk, store = ctx
    html = render_page(bot_state, risk, store, config)
    assert "Health:" in html and "ALL CLEAR" in html

    # A broker reject today + an accepted signal with no order → both flagged.
    now = datetime.now()
    store.upsert_order({
        "order_id": "r1", "instrument": "NSE:REDTAPE", "order_type": "MARKET", "product": "CNC",
        "direction": "BUY", "quantity": 0, "price": 0.0, "trigger_price": None,
        "status": "REJECTED", "mode": "live", "placed_at": now.isoformat(), "updated_at": now.isoformat(),
    })
    store.log_signal(timestamp=now, instrument="NSE:CGPOWER", strategy="lr_extrema",
                     direction="BUY", signal_type="EXIT", price_hint=897.9, accepted=True,
                     reject_reason=None, exit_reason="PATTERN_TOP_PARTIAL")
    bot_state.model_scores["NSE:KPL"] = {"p_min": 1.0, "p_max": 0.0, "drivers": []}
    html = render_page(bot_state, risk, store, config)
    assert "ALL CLEAR" not in html
    assert "1 broker reject today (REDTAPE)" in html
    assert "1 accepted signal never placed (CGPOWER)" in html
    assert "model saturated P(buy)=1.0: KPL" in html


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


# --------------------------------------------------------------------------- #
# /stock/<sym> drilldown
# --------------------------------------------------------------------------- #

def test_render_stock_page_empty(ctx):
    from trader.ui.template import render_stock_page
    bot_state, risk, store = ctx
    html = render_stock_page("NSE:ABC", bot_state, risk, store, config)
    assert "<title>ABC — Trader</title>" in html
    assert "NO SCORE" in html and "Not enough" in html
    assert "none yet" in html and "none logged" in html
    assert 'href="/chart/ABC"' in html and "visibilitychange" in html


def test_render_stock_page_full(ctx):
    from trader.ui.template import render_stock_page
    bot_state, risk, store = ctx
    t0 = datetime.now() - timedelta(days=30)
    _order(store, "o1", "NSE:ABC", "BUY", 10, 100.0, t0)
    _order(store, "o2", "NSE:ABC", "SELL", 10, 110.0, t0 + timedelta(days=3))
    store.log_signal(timestamp=t0 + timedelta(days=3), instrument="NSE:ABC", strategy="lr_extrema",
                     direction="BUY", signal_type="EXIT", price_hint=110.0, accepted=True,
                     reject_reason=None, exit_reason="TRAILING")
    store.log_signal(timestamp=t0 + timedelta(days=5), instrument="NSE:ABC", strategy="lr_extrema",
                     direction="BUY", signal_type="ENTRY", price_hint=105.0, accepted=False,
                     reject_reason="FILTER: ht_trend", exit_reason=None)
    # candles (base TF) + model scores + Nifty + open position + live reading
    days = pd.date_range(t0.date(), periods=31, freq="D")
    store.write_candles("NSE:ABC", config.candle_timeframe, pd.DataFrame({
        "timestamp": days, "open": 100.0, "high": 101.0, "low": 99.0,
        "close": [100.0 + i * 0.5 for i in range(len(days))], "volume": 1000}))
    store.write_candles(BENCHMARK_INSTRUMENT, "day", pd.DataFrame({
        "timestamp": days, "open": 20000.0, "high": 20100.0, "low": 19900.0,
        "close": [20000.0 + i * 10 for i in range(len(days))], "volume": 0}))
    for i, d in enumerate(days):
        store.write_model_score("NSE:ABC", d.to_pydatetime(), 0.3 + i * 0.01, 0.2)
    e = datetime.now() - timedelta(days=2)
    store.upsert_open_position("NSE:ABC", 112.0, 10, 4, e, low_since_entry=111.0)
    store.update_position_metrics("NSE:ABC", 4, 115.0, 2.7, 30.0, 116.0, True)
    bot_state.model_scores["NSE:ABC"] = {"p_min": 0.42, "p_max": 0.2,
                                         "drivers": [{"name": "slope_5", "value": 0.31, "kind": "contrib"}]}

    html = render_stock_page("NSE:ABC", bot_state, risk, store, config)

    assert "IN POSITION" in html and "P(buy) <span" in html and "drivers:" in html
    assert "Open Position" in html and "Stop risk" in html and "TRAIL(" in html
    assert "Closed Trades (1)" in html and "TRAILING" in html
    assert "vs Nifty trade-matched" in html
    assert "FILTER: ht_trend" in html and "incl. gate filters" in html
    assert "Effective Params" in html and "threshold = " in html
    assert "<svg" in html                      # price chart rendered
    assert "last 31 scores" in html            # conviction history


def test_stock_route_serves_page(ctx):
    from trader.ui.server import build_app
    bot_state, risk, store = ctx
    app = build_app(bot_state, risk, store, config)
    app.config.update(TESTING=True)
    resp = app.test_client().get("/stock/ABC")
    assert resp.status_code == 200 and b"ABC" in resp.data


def test_dashboard_links_point_to_drilldown(ctx):
    bot_state, risk, store = ctx
    e = datetime.now() - timedelta(days=1)
    _order(store, "ob", "NSE:ABC", "BUY", 10, 100.0, e)
    store.upsert_open_position("NSE:ABC", 100.0, 10, 1, e)
    html = render_page(bot_state, risk, store, config)
    assert "href='/stock/ABC'" in html and "href='/chart/ABC'" not in html


def test_render_page_giveback_pane_is_plain_english(ctx):
    bot_state, risk, store = ctx
    t0 = datetime.now() - timedelta(days=40)
    # win, loss (giveback), bigger win (recovered), then a loss still open → "underwater"
    legs = [("NSE:ABC", 10, 100.0, 120.0, 0), ("NSE:ABC", 10, 120.0, 110.0, 5),
            ("NSE:XYZ", 10, 100.0, 130.0, 10), ("NSE:XYZ", 10, 130.0, 125.0, 20)]
    for i, (inst, q, bp, sp, d) in enumerate(legs):
        _order(store, f"b{i}", inst, "BUY", q, bp, t0 + timedelta(days=d))
        _order(store, f"s{i}", inst, "SELL", q, sp, t0 + timedelta(days=d + 2))
    html = render_page(bot_state, risk, store, config)
    assert "Giveback from peak" in html and "Drawdown</h3>" not in html
    assert "days and counting" in html                  # underwater state sentence
    assert 'class="t-giveback"' in html and "ongoing" in html
    assert "high-water mark" in html and 'stroke="#d29922"' in html   # HWM step line drawn
    assert "not a loss against starting capital" in html
    assert "· net of costs" in html
