"""
Live-path plumbing for the scale-in + loss re-entry block release (2026-10-17).

1. The loss re-entry countdown survives restarts. The EC2 box reboots every
   morning, so an in-memory countdown expired overnight and a 3-session block
   covered only the rest of the exit day. Store.save_loss_reentry/load_loss_reentry
   round-trip it through the state table (main.py saves after every full close and
   after post-market reset_day, seeds at boot).
2. The live scale-in pool is funded only by account equity ABOVE the base capital,
   capped at budget_pct of the config-file base — never reserved out of the base.
"""
from trader.core.config import Config
from trader.data.store import Store
from trader.risk.manager import RiskManager, scale_in_pool
from tests.test_loss_reentry_block import _block, _entry, _open_position

WATCH = ["NSE:TEST", "NSE:OTHER"]


def _boot(store) -> RiskManager:
    """A fresh process: new RiskManager seeded from the state table."""
    risk = RiskManager()
    risk.seed_loss_reentry(store.load_loss_reentry(WATCH))
    return risk


def test_countdown_survives_daily_reboots(tmp_path):
    store = Store(tmp_path / "s.db")
    with _block(sessions=3):
        risk = RiskManager()
        _open_position(risk)
        risk.close_position("NSE:TEST", 95.0)           # losing exit → armed (3)
        store.save_loss_reentry(risk.loss_reentry_state, WATCH)
        risk.reset_day()                                 # exit day's post-market → 2
        store.save_loss_reentry(risk.loss_reentry_state, WATCH)

        risk = _boot(store)                              # next morning
        assert risk.loss_reentry_state == {"NSE:TEST": 2}
        assert risk.validate(_entry()) is None
        assert risk._last_reject_reason == "loss_reentry_block"
        risk.reset_day()                                 # → 1
        store.save_loss_reentry(risk.loss_reentry_state, WATCH)

        risk = _boot(store)
        assert risk.validate(_entry()) is None
        risk.reset_day()                                 # → expired
        store.save_loss_reentry(risk.loss_reentry_state, WATCH)

        risk = _boot(store)                              # third session after exit
        assert risk.loss_reentry_state == {}
        assert risk.validate(_entry()) is not None


def test_expired_keys_are_cleared_not_resurrected(tmp_path):
    store = Store(tmp_path / "s.db")
    store.save_loss_reentry({"NSE:TEST": 2, "NSE:OTHER": 1}, WATCH)
    store.save_loss_reentry({"NSE:TEST": 1}, WATCH)
    assert store.load_loss_reentry(WATCH) == {"NSE:TEST": 1}
    assert store.get_state("NSE:OTHER.loss_reentry_sessions", -1.0) == -1.0


def test_pool_is_only_the_equity_above_the_base():
    assert scale_in_pool(494_000, 600_000, 60_000) == 0.0       # below base → no add-ons
    assert scale_in_pool(600_000, 600_000, 60_000) == 0.0       # exactly the base
    assert scale_in_pool(630_000, 600_000, 60_000) == 30_000    # partial pool
    assert scale_in_pool(700_000, 600_000, 60_000) == 60_000    # capped


def _cfg(total=600_000, pct=10):
    return Config({
        "env": "live", "candle_timeframe": "15minute",
        "capital": {"total": total, "max_risk_per_trade_pct": 5.0, "daily_loss_limit_pct": 10.0},
        "risk": {"max_open_positions": 25, "default_sl_pct": 2.0, "risk_reward": 4.0},
        "scale_in": {"enabled": True, "fraction_pct": 50, "max_addons": 2, "budget_pct": pct},
        "strategies": {}, "watchlist": [], "data": {"db_path": "x.db", "historical_cache_days": 5},
    })


def test_live_override_and_cap_follow_the_config_file_base():
    cfg = _cfg()
    assert cfg.scale_in_budget == 60_000                 # backtest/paper: pct of capital
    cfg.set_effective_capital(494_000)                   # live: account below the base
    assert cfg.scale_in_budget_cap == 60_000             # cap stays on the ₹6L file base
    cfg.set_scale_in_budget(scale_in_pool(494_000, cfg.base_capital, cfg.scale_in_budget_cap))
    assert cfg.scale_in_budget == 0.0
    cfg.set_scale_in_budget(scale_in_pool(640_000, cfg.base_capital, cfg.scale_in_budget_cap))
    assert cfg.scale_in_budget == 40_000
