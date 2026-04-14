"""
Project-wide pytest fixtures.

The autouse fixture below pins capital and risk settings to stable test values so
that test assertions don't drift when config.yaml is tuned for live trading.

Tests that specifically exercise position-sizing caps re-enable max_position_pct
via their own monkeypatch calls.
"""

import pytest


@pytest.fixture(autouse=True)
def _stable_test_config(monkeypatch):
    """
    Pin capital to ₹20,000 and disable max_position_pct for all tests.

    Rationale:
    - Tests that check specific quantities (qty == 8, pnl == 400, etc.) were
      written against 20,000 capital with 1% risk (max_risk = 200).
    - max_position_pct is a portfolio-level cap tested in TestATRSizing; it
      should not silently zero out quantities in unrelated tests.
    """
    import trader.core.config as cfg_mod
    data = cfg_mod.config._data

    # Pin capital section
    orig_capital = data["capital"].copy()
    data["capital"]["total"] = 20000
    data["capital"]["max_risk_per_trade_pct"] = 1.0

    # Standardize position_sizing: disable ATR-based sizing and per-position cap.
    # Tests that specifically exercise these features re-enable them via monkeypatch.
    ps = data["risk"].setdefault("position_sizing", {})
    orig_ps = ps.copy()
    ps["atr_based"] = False
    ps["max_position_pct"] = 0

    yield

    # Restore
    data["capital"].update(orig_capital)
    ps.clear()
    ps.update(orig_ps)
