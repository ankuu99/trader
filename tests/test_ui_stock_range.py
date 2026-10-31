"""TD-017: date-range filter on /stock/<sym> and /chart/<sym>, plus a pin that
the dashboard's own range bar is unchanged by the _range_bar extraction."""

from datetime import datetime, timedelta

import pandas as pd

from tests.test_ui_render_page import ctx, _order  # noqa: F401  (ctx is a pytest fixture)
from trader.core.config import config
from trader.ui.template import (
    _now_ist, render_chart_page, render_page, render_stock_page,
)

INST = "NSE:ABC"


def _seed(store):
    """Old round trip (~40d ago, 111.11 exit) and a recent one (~2d ago, 222.22 exit), one signal each."""
    old, new = datetime.now() - timedelta(days=40), datetime.now() - timedelta(days=2)
    _order(store, "o1", INST, "BUY", 10, 100.0, old)
    _order(store, "o2", INST, "SELL", 10, 111.11, old + timedelta(hours=5))
    _order(store, "o3", INST, "BUY", 10, 200.0, new)
    _order(store, "o4", INST, "SELL", 10, 222.22, new + timedelta(hours=5))
    store.log_signal(timestamp=old, instrument=INST, strategy="lr_extrema", direction="BUY",
                     signal_type="ENTRY", price_hint=101.01, accepted=True)
    store.log_signal(timestamp=new, instrument=INST, strategy="lr_extrema", direction="BUY",
                     signal_type="ENTRY", price_hint=202.02, accepted=True)
    start = (datetime.now() - timedelta(days=45)).replace(hour=9, minute=15, second=0, microsecond=0)
    ts = pd.date_range(start, periods=400, freq="1D")
    store.write_candles(INST, config.candle_timeframe, pd.DataFrame({
        "timestamp": ts, "open": 100.0, "high": 101.0, "low": 99.0,
        "close": [100.0 + i * 0.1 for i in range(len(ts))], "volume": 1000,
    }))


def _stock(ctx, **kw):
    bot_state, risk, store = ctx
    return render_stock_page(INST, bot_state, risk, store, config, **kw)


def test_stock_page_has_range_bar_auto_active(ctx):  # noqa: F811
    html = _stock(ctx)
    assert 'class="rangebar"' in html
    assert '<a href="/stock/ABC" class="rbtn active">Auto</a>' in html
    assert 'href="/stock/ABC?range=1m"' in html
    assert 'action="/stock/ABC"' in html


def test_stock_page_window_filters_trades_and_signals(ctx):  # noqa: F811
    _seed(ctx[2])
    week = _stock(ctx, range_params={"range": "1w"})
    assert "222.22" in week and "111.11" not in week
    assert "202.02" in week and "101.01" not in week
    assert '<a href="/stock/ABC?range=1w" class="rbtn active">1W</a>' in week
    allr = _stock(ctx, range_params={"range": "all"})
    assert "222.22" in allr and "111.11" in allr
    assert "202.02" in allr and "101.01" in allr
    auto = _stock(ctx)
    assert "111.11" in auto and "101.01" in auto      # auto = today's behaviour


def test_custom_from_to(ctx):  # noqa: F811
    _seed(ctx[2])
    d0 = (datetime.now() - timedelta(days=42)).strftime("%Y-%m-%d")
    d1 = (datetime.now() - timedelta(days=38)).strftime("%Y-%m-%d")
    html = _stock(ctx, range_params={"from": d0, "to": d1})
    assert "111.11" in html and "222.22" not in html
    assert "101.01" in html and "202.02" not in html
    assert f'name="from" value="{d0}"' in html and f'name="to" value="{d1}"' in html
    assert 'class="rbtn active">Apply</button>' in html


def test_bench_preserved(ctx):  # noqa: F811
    html = _stock(ctx, bench="gold", range_params={"range": "1m", "bench": "gold"})
    assert 'href="/stock/ABC?range=1w&bench=gold"' in html
    assert 'href="/stock/ABC?bench=gold" class="rbtn">Auto</a>' in html
    assert '<input type="hidden" name="bench" value="gold">' in html


def test_chart_page_range(ctx):  # noqa: F811
    _seed(ctx[2])
    _, _, store = ctx
    html = render_chart_page(INST, store, config, range_params={"range": "1w"})
    assert 'class="rangebar"' in html and 'href="/chart/ABC?range=1m"' in html
    assert "<svg" in html
    # window with no candles → still renders, with the bar
    empty = render_chart_page(INST, store, config, range_params={"from": "2001-01-01", "to": "2001-02-01"})
    assert "Not enough candle data" in empty and 'class="rangebar"' in empty


def test_dashboard_range_bar_unchanged(ctx):  # noqa: F811
    bot_state, risk, store = ctx
    now = _now_ist().replace(tzinfo=None)
    html = render_page(bot_state, risk, store, config, range_params={"range": "1m"})
    got = html[html.index('<span class="rangebar">'):html.index('<label class="m-only">')]
    lo = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    to = now.strftime("%Y-%m-%d")
    expected = (
        '<span class="rangebar">\n            <span class="dim" style="font-size:11px">Range:</span>\n'
        '            <a href="/?range=1w" class="rbtn">1W</a><a href="/?range=1m" class="rbtn active">1M</a>'
        '<a href="/?range=1q" class="rbtn">1Q</a><a href="/?range=1y" class="rbtn">1Y</a>'
        '<a href="/?range=all" class="rbtn">All</a>\n'
        '            <form method="GET" action="/" style="display:inline-flex;gap:4px;margin-left:6px;align-items:center">\n'
        f'                <input type="date" name="from" value="{lo}">\n'
        f'                <input type="date" name="to" value="{to}">\n'
        '                <input type="hidden" name="bench" value="nifty50">\n'
        '                <button type="submit" class="rbtn">Apply</button>\n'
        '            </form>\n'
        '            <span class="dim" style="font-size:11px;margin-left:10px">vs:</span>\n'
        '            <a href="/?range=1m&bench=nifty50" class="rbtn active" title="vs Nifty 50">N50</a>'
        '<a href="/?range=1m&bench=banknifty" class="rbtn" title="vs Nifty Bank">Bank</a>'
        '<a href="/?range=1m&bench=midcap100" class="rbtn" title="vs Nifty Midcap 100">Mid</a>'
        '<a href="/?range=1m&bench=smallcap250" class="rbtn" title="vs Nifty Smallcap 250">Small</a>'
        '<a href="/?range=1m&bench=gold" class="rbtn" title="vs Gold (GOLDBEES)">Gold</a>\n'
        '        </span>\n        '
    )
    assert got == expected
    # non-default bench: quick links carry it, form always does
    g2 = render_page(bot_state, risk, store, config, range_params={"range": "1w", "bench": "gold"})
    assert 'href="/?range=1m&bench=gold"' in g2 and 'href="/?range=1m"' not in g2
