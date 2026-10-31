"""TD-016: every stock name on the dashboard links to its /stock/<sym> drilldown."""

from datetime import datetime, timedelta

from tests.test_ui_render_page import ctx, _order  # noqa: F401  (ctx is a pytest fixture)
from trader.core.config import config
from trader.ui.template import render_page, _stock_link


def test_stock_link_encodes_and_escapes():
    s = _stock_link("M&MFIN")
    assert "href='/stock/M%26MFIN'" in s and ">M&amp;MFIN</a>" in s
    assert "href='/stock/QUESS'" in _stock_link("QUESS")


def test_rendered_tables_link_symbols(ctx):  # noqa: F811
    bot_state, risk, store = ctx
    t0 = datetime.now() - timedelta(days=10)
    _order(store, "o1", "NSE:ABC", "BUY", 10, 100.0, t0)
    _order(store, "o2", "NSE:ABC", "SELL", 10, 110.0, t0 + timedelta(days=3))
    store.log_signal(timestamp=t0, instrument="NSE:ABC", strategy="lr_extrema", direction="BUY",
                     signal_type="ENTRY", price_hint=100.0, accepted=True)
    store.log_signal(timestamp=t0 + timedelta(days=1), instrument="NSE:ABC", strategy="lr_extrema",
                     direction="BUY", signal_type="ENTRY", price_hint=101.0, accepted=False,
                     reject_reason="FILTER: ht_trend")
    html = render_page(bot_state, risk, store, config, range_params={"range": "all"})
    assert "<td>ABC</td>" not in html
    assert "href='/stock/ABC'" in html
    # orders, closed trades, recent + filtered signals: at least one link each
    assert html.count("href='/stock/ABC'") >= 4
