"""
Startup capital-seeding contract (D1 fix).

Regression guard for the bug where the buying-power cap was encoded into
cumulative_pnl (`adjusted_pnl = effective - total_capital`), corrupting lifetime
P&L and ratcheting it down every restart. The fix seeds cumulative_pnl untouched
and caps buying power separately via config.set_effective_capital().

These tests mirror the post-reconciliation cap logic in main.py.
"""
import pytest

from trader.core.config import config
from trader.risk.manager import RiskManager


@pytest.fixture
def restore_capital():
    orig_total = config._data["capital"]["total"]
    orig_base = config._base_capital
    yield
    config._data["capital"]["total"] = orig_total
    config._base_capital = orig_base


def _apply_cap(risk: RiskManager, kite_cash: float) -> float:
    """Mirror main.py's post-reconciliation cap: bound config ceiling by the real
    account equity (free cash + already-deployed holdings), no double-count."""
    config_ceiling = config.total_capital
    account_equity = kite_cash + risk.capital_deployed
    effective = min(config_ceiling, account_equity)
    config.set_effective_capital(effective)
    return effective


def test_cap_below_ceiling_does_not_touch_pnl(restore_capital):
    """The old bug rewrote cumulative_pnl when kite_cash < ceiling. It must not."""
    config._data["capital"]["total"] = 250_000.0
    risk = RiskManager()
    risk.seed_cumulative_pnl(-2_000.0)                 # real persisted P&L

    effective = _apply_cap(risk, kite_cash=200_000.0)  # flat, cash < ceiling

    assert effective == 200_000.0
    assert risk.cumulative_pnl == -2_000.0             # UNCHANGED
    # capital_available = effective + pnl - deployed - pending
    assert risk.capital_available == pytest.approx(200_000.0 - 2_000.0)


def test_cap_with_holdings_no_double_count(restore_capital):
    """kite_cash is post-deployment; equity = cash + deployed. Deployed must not
    be subtracted twice."""
    config._data["capital"]["total"] = 250_000.0
    risk = RiskManager()
    risk.seed_cumulative_pnl(0.0)
    risk.seed_position("NSE:X", qty=100, avg_price=500.0)  # deploys 50,000

    effective = _apply_cap(risk, kite_cash=150_000.0)      # 150k free + 50k held

    assert effective == 200_000.0
    # Free cash available for new trades = effective - deployed = 150k (not 100k).
    assert risk.capital_available == pytest.approx(150_000.0)


def test_ceiling_caps_a_rich_account(restore_capital):
    """When equity exceeds the config ceiling, buying power is bounded by config."""
    config._data["capital"]["total"] = 250_000.0
    risk = RiskManager()
    risk.seed_cumulative_pnl(0.0)

    effective = _apply_cap(risk, kite_cash=400_000.0)

    assert effective == 250_000.0
    assert risk.capital_available == pytest.approx(250_000.0)


def test_persisted_pnl_seeded_verbatim(restore_capital):
    """Whatever value is persisted is what gets seeded — no derivation."""
    risk = RiskManager()
    risk.seed_cumulative_pnl(-71_473.18)
    assert risk.cumulative_pnl == pytest.approx(-71_473.18)
