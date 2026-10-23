"""Price layer: the pure price_provider (PIT last-close lookup). Network paths are
exercised live only (need Kite auth), not in CI."""

import pandas as pd

from trader.fvm.data.prices import price_provider


def _df(dates, closes):
    return pd.DataFrame({"timestamp": pd.to_datetime(dates), "open": closes,
                         "high": closes, "low": closes, "close": closes,
                         "volume": [1] * len(closes)})


def test_price_provider_returns_last_close_on_or_before_asof():
    pd_data = {"AAA": _df(["2026-01-01", "2026-02-01", "2026-03-01"], [100, 110, 120])}
    f = price_provider(pd_data, "2026-02-15")
    assert f("AAA") == 110.0          # last close on/before 15 Feb
    assert f("aaa") == 110.0          # case-insensitive
    assert f("MISSING") is None


def test_price_provider_none_before_first_bar():
    pd_data = {"AAA": _df(["2026-02-01"], [110])}
    assert price_provider(pd_data, "2026-01-01")("AAA") is None
