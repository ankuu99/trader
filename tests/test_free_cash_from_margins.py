from trader.risk.manager import free_cash_from_margins as f


def test_prefers_net_over_opening_cash():
    m = {"net": 125102.9, "available": {"cash": 25102.9, "opening_balance": 25102.9,
                                        "live_balance": 125102.9, "intraday_payin": 100000}}
    assert f(m) == 125102.9


def test_intraday_buys_reduce_net():
    m = {"net": 3733.0, "available": {"cash": 157733.0, "live_balance": 3733.0}}
    assert f(m) == 3733.0


def test_falls_back_to_live_balance():
    assert f({"available": {"live_balance": 42.0, "cash": 10.0}}) == 42.0


def test_falls_back_to_cash():
    assert f({"available": {"cash": 10.0}}) == 10.0


def test_none_and_non_numeric_skipped():
    assert f({"net": None, "available": {"live_balance": "abc", "cash": 10.0}}) == 10.0
    assert f({"net": True, "available": {"cash": 7}}) == 7.0


def test_negative_net_returned():
    assert f({"net": -500.0}) == -500.0


def test_unusable_payload_returns_none():
    assert f({}) is None
    assert f({"available": None}) is None
    assert f(None) is None
