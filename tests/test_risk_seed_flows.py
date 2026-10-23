"""
RiskManager seeding flow tests (R6-1, R6-2).

Tests position seeding from DB, realised P&L seeding from broker,
and halt triggering when seeded P&L already breaches daily limit.
"""
import pytest
from unittest.mock import patch, PropertyMock

from trader.risk.manager import RiskManager
from trader.core.config import config


# ---------------------------------------------------------------------------
# R6-1: seed_position — DB-based position seeding
# ---------------------------------------------------------------------------

def test_seed_position_deploys_capital():
    """seed_position must record the position and increase capital_deployed."""
    risk = RiskManager()

    risk.seed_position("NSE:TEST", qty=100, avg_price=50.0)

    assert "NSE:TEST" in risk._open_positions
    assert risk._open_positions["NSE:TEST"] == 100
    assert risk._capital_deployed == pytest.approx(5000.0, abs=1.0)


def test_seed_position_multiple_instruments():
    """Seeding multiple positions accumulates capital_deployed correctly."""
    risk = RiskManager()

    risk.seed_position("NSE:A", qty=100, avg_price=50.0)   # 5000
    risk.seed_position("NSE:B", qty=200, avg_price=25.0)   # 5000

    assert risk._capital_deployed == pytest.approx(10000.0, abs=1.0)
    assert len(risk._open_positions) == 2


def test_seeded_position_can_be_closed():
    """A seeded position must be closeable via close_position."""
    risk = RiskManager()
    risk.seed_position("NSE:TEST", qty=100, avg_price=50.0)

    risk.close_position("NSE:TEST", exit_price=55.0)

    assert "NSE:TEST" not in risk._open_positions
    assert risk._capital_deployed == pytest.approx(0.0, abs=1.0)
    assert risk._realised_pnl == pytest.approx(500.0, abs=1.0)  # (55-50)*100


def test_seeded_position_blocks_duplicate_entry():
    """A seeded position must block a new ENTRY signal for the same instrument."""
    from trader.strategies.base import Direction, Signal, SignalType
    risk = RiskManager()
    risk.seed_position("NSE:TEST", qty=100, avg_price=50.0)

    signal = Signal(
        instrument="NSE:TEST",
        direction=Direction.BUY,
        signal_type=SignalType.ENTRY,
        price_hint=51.0,
        strategy="test",
        stop_loss_hint=49.0,
    )
    order = risk.validate(signal)

    assert order is None


# ---------------------------------------------------------------------------
# R6-2: seed_realised_pnl — P&L seeding from broker on restart
# ---------------------------------------------------------------------------

def test_seed_realised_pnl_updates_tracker():
    """Seeding realised P&L must update _realised_pnl."""
    risk = RiskManager()
    risk.seed_realised_pnl(-500.0)

    assert risk._realised_pnl == pytest.approx(-500.0)


def test_seed_realised_pnl_zero_is_noop():
    """Seeding 0 P&L must not trigger halt or change state."""
    risk = RiskManager()
    risk.seed_realised_pnl(0.0)

    assert risk._realised_pnl == 0.0
    assert not risk._halted


def test_seed_realised_pnl_triggers_halt_when_limit_breached():
    """If seeded P&L already exceeds daily limit, halt must activate immediately."""
    with patch.object(type(config), "daily_loss_limit",
                      new_callable=PropertyMock, return_value=1000.0), \
         patch.object(type(config), "env",
                      new_callable=PropertyMock, return_value="live"):
        risk = RiskManager()
        risk.seed_realised_pnl(-1500.0)  # exceeds 1000 limit

    assert risk._halted is True


def test_seed_realised_pnl_no_halt_when_within_limit():
    """If seeded P&L is within daily limit, no halt must be triggered."""
    with patch.object(type(config), "daily_loss_limit",
                      new_callable=PropertyMock, return_value=1000.0):
        risk = RiskManager()
        risk.seed_realised_pnl(-500.0)

    assert risk._halted is False


def test_seed_realised_pnl_positive_does_not_halt():
    """Positive seeded P&L (profitable exits while down) must never trigger halt."""
    risk = RiskManager()
    risk.seed_realised_pnl(2000.0)

    assert risk._halted is False


def test_further_losses_after_seed_still_trigger_halt():
    """After seeding near-limit P&L, one more loss must cross the threshold and halt."""
    with patch.object(type(config), "daily_loss_limit",
                      new_callable=PropertyMock, return_value=1000.0), \
         patch.object(type(config), "env",
                      new_callable=PropertyMock, return_value="live"):
        risk = RiskManager()
        risk.seed_realised_pnl(-800.0)  # within limit, no halt yet
        assert not risk._halted

        risk.seed_position("NSE:TEST", qty=100, avg_price=50.0)
        risk.close_position("NSE:TEST", exit_price=47.0)  # -300 loss → total -1100 > -1000

    assert risk._halted is True


# ---------------------------------------------------------------------------
# Interaction: seeded positions + entry blocking
# ---------------------------------------------------------------------------

def test_seeded_positions_count_toward_max_open():
    """Seeded positions must count toward max_open_positions limit."""
    with patch.object(type(config), "max_open_positions",
                      new_callable=PropertyMock, return_value=1):
        from trader.strategies.base import Direction, Signal, SignalType
        risk = RiskManager()
        risk.seed_position("NSE:EXISTING", qty=50, avg_price=100.0)

        signal = Signal(
            instrument="NSE:NEW",
            direction=Direction.BUY,
            signal_type=SignalType.ENTRY,
            price_hint=100.0,
            strategy="test",
            stop_loss_hint=98.0,
        )
        order = risk.validate(signal)

    assert order is None
