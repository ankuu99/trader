"""Per-stock timeframe config: strategy_timeframe, warmup_days_for, timeframe_warnings."""
from trader.core.config import Config


def make_config(**overrides):
    data = {
        "env": "paper",
        "candle_timeframe": "15minute",
        "capital": {"total": 50000, "max_risk_per_trade_pct": 7.0, "daily_loss_limit_pct": 10.0},
        "watchlist": ["NSE:AAA", "NSE:BBB"],
        "strategies": {"lr_extrema": {"enabled": True, "warmup_bars": 200, "lookback_bars": 600}},
        "risk": {"max_open_positions": 5, "default_sl_pct": 2},
        "data": {"db_path": "data/test.db", "historical_cache_days": 90},
    }
    data.update(overrides)
    return Config(data)


def test_default_timeframe_is_base():
    cfg = make_config()
    assert cfg.strategy_timeframe("NSE:AAA") == "15minute"


def test_per_stock_timeframe_override():
    cfg = make_config(per_stock_params={"NSE:AAA": {"lr_extrema": {"timeframe": "day"}}})
    assert cfg.strategy_timeframe("NSE:AAA") == "day"
    assert cfg.strategy_timeframe("NSE:BBB") == "15minute"


def test_warmup_days_base_tf_uses_cache_days():
    cfg = make_config()
    assert cfg.warmup_days_for("NSE:AAA") == 90


def test_warmup_days_derived_for_day_tf():
    cfg = make_config(per_stock_params={"NSE:AAA": {"lr_extrema": {
        "timeframe": "day", "warmup_bars": 100, "lookback_bars": 300,
    }}})
    # (100+300) bars / 1 per day * 1.45 = 580 calendar days
    assert cfg.warmup_days_for("NSE:AAA") == 580
    assert cfg.warmup_days_for("NSE:BBB") == 90


def test_warmup_days_derived_for_4hour_tf():
    cfg = make_config(per_stock_params={"NSE:AAA": {"lr_extrema": {
        "timeframe": "4hour", "warmup_bars": 100, "lookback_bars": 300,
    }}})
    # 400 bars / 2 per day * 1.45 = 290 calendar days
    assert cfg.warmup_days_for("NSE:AAA") == 290


def test_warnings_empty_for_base_tf_watchlist():
    assert make_config().timeframe_warnings() == []


def test_warning_for_missing_tf_sensitive_overrides():
    cfg = make_config(per_stock_params={"NSE:AAA": {"lr_extrema": {
        "timeframe": "day", "hold_bars": 20,
    }}})
    warnings = cfg.timeframe_warnings()
    assert len(warnings) == 1
    assert "NSE:AAA" in warnings[0]
    assert "stop_pct" in warnings[0]
    assert "hold_bars" not in warnings[0]  # explicitly overridden — not flagged


def test_no_warning_when_all_sensitive_params_overridden():
    full = {
        "timeframe": "day", "warmup_bars": 100, "lookback_bars": 300,
        "hold_bars": 20, "retrain_every": 10, "extrema_order": 3,
        "stop_pct": 8.0, "trail_pct": 4.0, "profit_pct": 6.0,
        "sell_min_pct": 4.0, "min_hold_before_exit": 2, "volume_ma_bars": 20,
    }
    cfg = make_config(per_stock_params={"NSE:AAA": {"lr_extrema": full}})
    assert cfg.timeframe_warnings() == []


def test_warning_for_unknown_timeframe():
    cfg = make_config(per_stock_params={"NSE:AAA": {"lr_extrema": {"timeframe": "2hour"}}})
    warnings = cfg.timeframe_warnings()
    assert len(warnings) == 1 and "unknown timeframe" in warnings[0]


def test_warning_when_base_is_not_15minute():
    cfg = make_config(
        candle_timeframe="5minute",
        per_stock_params={"NSE:AAA": {"lr_extrema": {"timeframe": "day"}}},
    )
    assert any("requires base candle_timeframe '15minute'" in w
               for w in cfg.timeframe_warnings())
