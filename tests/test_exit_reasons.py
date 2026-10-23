"""Exit-reason tagging tests.

Every strategy-driven exit must carry a reason code on its ExitDecision, so the
live signals log (and the dashboard) shows WHY a position closed. Previously the
two highest-volume live paths — tick exits (hard stop / trailing) and the
hold-bars timeout — returned an ExitDecision with exit_reason=None, leaving the
reason as "—" in the UI and indistinguishable from a manual/external sell.
"""
import pytest

from trader.policy.base import PositionState
from trader.policy.extrema_exit import ExtremaExitPolicy


class _FakeStrat:
    """Minimal context the exit policy needs for tick/hold-bars paths."""
    instrument = "NSE:TEST"

    def __init__(self):
        self._pos = PositionState()
        self._last_p_max = 0.0

    def is_flat(self) -> bool:
        return self._pos.entry_price is None


_PARAMS = {"hold_bars": 10, "profit_pct": 3.0, "trail_pct": 1.5, "stop_pct": 3.0}


def test_hold_bars_exit_tagged_strategy():
    pol = ExtremaExitPolicy(_PARAMS)
    s = _FakeStrat()
    s._pos.entry_price = 100.0
    s._pos.held_bars = 10  # == hold_bars
    decision = pol.candle_exit(s, {"timestamp": "2026-06-25T10:00", "close": 101.0}, 101.0)
    assert decision is not None
    assert decision.exit_reason == "STRATEGY"


def test_hard_stop_exit_tagged_sl():
    pol = ExtremaExitPolicy(_PARAMS)
    s = _FakeStrat()
    s._pos.entry_price = 100.0
    s._pos.peak_close = 100.0
    # -10% — well past the 3% hard stop.
    decision = pol.tick_exit(s, {"timestamp": "2026-06-25T10:00"}, 90.0)
    assert decision is not None
    assert decision.exit_reason == "SL"


def test_trailing_stop_exit_tagged_trailing():
    pol = ExtremaExitPolicy(_PARAMS)
    s = _FakeStrat()
    s._pos.entry_price = 100.0
    s._pos.peak_close = 110.0
    s._pos.trailing_active = True
    # +8% (above floor, no hard stop) but -1.82% off the 110 peak > 1.5% trail.
    decision = pol.tick_exit(s, {"timestamp": "2026-06-25T10:00"}, 108.0)
    assert decision is not None
    assert decision.exit_reason == "TRAILING"
