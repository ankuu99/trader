"""
Slow-TF position cap (risk.max_slow_tf_positions).

Aggregated-TF (4hour/day) round-trips hold capital 2-3.5x longer per trade than
15m ones (live forensics 2026-08-16); the cap stops them from occupying every
funded slot. Base-TF entries must never be blocked by it.
"""
import pytest

from trader.core.config import config
from trader.risk.manager import RiskManager
from trader.strategies.base import Direction, Signal, SignalType


SLOW_A, SLOW_B, SLOW_C = "NSE:SLOWA", "NSE:SLOWB", "NSE:SLOWC"
FAST = "NSE:FASTA"


def _entry(instrument, price=100.0, sl=98.0) -> Signal:
    return Signal(
        instrument=instrument,
        direction=Direction.BUY,
        signal_type=SignalType.ENTRY,
        price_hint=price,
        strategy="test",
        stop_loss_hint=sl,
    )


@pytest.fixture
def slow_tf_config():
    """Mark SLOW_A/B/C as day-TF stocks and set the cap to 2; restore after."""
    risk_block = config._data["risk"]
    saved_cap = risk_block.get("max_slow_tf_positions")
    saved_psp = config._data.get("per_stock_params")
    config._data["per_stock_params"] = {
        s: {"lr_extrema": {"timeframe": "day"}} for s in (SLOW_A, SLOW_B, SLOW_C)
    }
    risk_block["max_slow_tf_positions"] = 2
    config._aggregated_tf_cache = {}
    yield
    risk_block["max_slow_tf_positions"] = saved_cap
    if saved_psp is None:
        config._data.pop("per_stock_params", None)
    else:
        config._data["per_stock_params"] = saved_psp
    config._aggregated_tf_cache = {}


def test_slow_entry_blocked_at_cap(slow_tf_config):
    risk = RiskManager()
    risk.on_order_filled(SLOW_A, 100.0, 10)
    risk.on_order_filled(SLOW_B, 100.0, 10)

    assert risk.validate(_entry(SLOW_C)) is None
    assert risk._last_reject_reason == "slow_tf_limit"


def test_base_tf_entry_unaffected_by_saturated_cap(slow_tf_config):
    risk = RiskManager()
    risk.on_order_filled(SLOW_A, 100.0, 10)
    risk.on_order_filled(SLOW_B, 100.0, 10)

    assert risk.validate(_entry(FAST)) is not None


def test_pending_slow_entry_counts_toward_cap(slow_tf_config):
    risk = RiskManager()
    risk.on_order_filled(SLOW_A, 100.0, 10)
    assert risk.validate(_entry(SLOW_B)) is not None  # pending, not yet filled

    assert risk.validate(_entry(SLOW_C)) is None
    assert risk._last_reject_reason == "slow_tf_limit"


def test_cap_frees_slot_after_close(slow_tf_config):
    risk = RiskManager()
    risk.on_order_filled(SLOW_A, 100.0, 10)
    risk.on_order_filled(SLOW_B, 100.0, 10)
    risk.close_position(SLOW_A, 105.0)

    assert risk.validate(_entry(SLOW_C)) is not None


def test_cap_disabled_when_null(slow_tf_config):
    config._data["risk"]["max_slow_tf_positions"] = None
    risk = RiskManager()
    risk.on_order_filled(SLOW_A, 100.0, 10)
    risk.on_order_filled(SLOW_B, 100.0, 10)

    assert risk.validate(_entry(SLOW_C)) is not None
