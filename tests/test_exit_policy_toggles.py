"""Unit tests for the exit-action additions:
- flatten_strategy_params resolves the new nested toggles to flat keys
- ExtremaExitPolicy confidence-sized trailing distance interpolation
- toggle defaults preserve legacy behaviour
"""
from types import SimpleNamespace

from trader.core.config import flatten_strategy_params
from trader.policy.extrema_exit import ExtremaExitPolicy
from trader.risk.manager import RiskManager
from trader.strategies.base import Direction, Signal, SignalType


def _policy(**trailing_pattern):
    """Build a policy from nested config, flattened as the strategy would."""
    cfg = {
        "exits": {
            "hold_bars": 200,
            "sell_min_pct": 3.0,
            "hard_stop": {"stop_pct": 20},
            "trailing": {"profit_pct": 5, "trail_pct": 2, **trailing_pattern.get("trailing", {})},
            "pattern_top": {"sell_threshold": 0.85, **trailing_pattern.get("pattern_top", {})},
        }
    }
    return ExtremaExitPolicy(flatten_strategy_params(cfg))


def test_flatten_resolves_new_toggles():
    p = flatten_strategy_params({
        "exits": {
            "trailing": {
                "enabled": False,
                "confidence_sizing": {"enabled": True, "trail_loose": 6, "trail_tight": 2,
                                      "p_lo": 0.5, "p_hi": 0.9},
            },
            "pattern_top": {"direct_exit": True},
        }
    })
    assert p["trailing_enabled"] is False
    assert p["pattern_top_direct_exit"] is True
    assert p["trail_conf_enabled"] is True
    assert p["trail_loose"] == 6 and p["trail_tight"] == 2
    assert p["trail_conf_p_lo"] == 0.5 and p["trail_conf_p_hi"] == 0.9


def test_toggle_defaults_preserve_legacy():
    pol = _policy()
    assert pol._trailing_enabled is True
    assert pol._pattern_top_direct_exit is False
    assert pol._trail_conf_enabled is False
    # static trail distance regardless of P(max)
    strat = SimpleNamespace(_last_p_max=0.99)
    assert pol._effective_trail_pct(strat) == 2


def test_confidence_sized_trail_interpolation():
    pol = _policy(trailing={"confidence_sizing": {
        "enabled": True, "trail_loose": 6, "trail_tight": 2, "p_lo": 0.5, "p_hi": 0.9}})
    assert pol._trail_conf_enabled is True
    # at/below p_lo -> loose; at/above p_hi -> tight; midpoint -> halfway
    assert pol._effective_trail_pct(SimpleNamespace(_last_p_max=0.40)) == 6
    assert pol._effective_trail_pct(SimpleNamespace(_last_p_max=0.90)) == 2
    assert abs(pol._effective_trail_pct(SimpleNamespace(_last_p_max=0.70)) - 4.0) < 1e-9
    # missing attribute is safe (treated as 0 -> loose end)
    assert pol._effective_trail_pct(SimpleNamespace()) == 6


# --- Step 2: scale-out / partial exit ---

def test_flatten_resolves_scale_out():
    p = flatten_strategy_params({
        "exits": {"pattern_top": {"scale_out": {"enabled": True, "fraction": 0.7}}}
    })
    assert p["pattern_top_scale_out_enabled"] is True
    assert p["pattern_top_scale_out_fraction"] == 0.7


def test_validate_exit_partial_quantity():
    risk = RiskManager()
    risk.on_order_filled("NSE:TEST", 100.0, 100)
    sig = Signal(instrument="NSE:TEST", direction=Direction.BUY, signal_type=SignalType.EXIT,
                 price_hint=110.0, strategy="t", exit_fraction=0.7)
    order = risk.validate(sig)
    assert order is not None and order.quantity == 70
    # full position still tracked until the fill is processed
    assert risk._open_positions["NSE:TEST"] == 100


def test_reduce_position_keeps_remainder():
    risk = RiskManager()
    risk.on_order_filled("NSE:TEST", 100.0, 100)
    risk.reduce_position("NSE:TEST", 70, 110.0)
    assert risk._open_positions["NSE:TEST"] == 30          # remainder open
    assert abs(risk._position_values["NSE:TEST"] - 3000.0) < 1e-6  # 30 @ entry 100
    assert abs(risk.cumulative_pnl - 700.0) < 1e-6         # (110-100)*70
    # reducing the rest closes it out
    risk.reduce_position("NSE:TEST", 30, 110.0)
    assert "NSE:TEST" not in risk._open_positions


# --- Regime-widened trailing (ride the leg in a close-level uptrend) ---

def _ramp_candles(n, start=100.0, step=0.5):
    return [{"close": start + i * step} for i in range(n)]


def _flat_candles(n, price=100.0):
    return [{"close": price} for _ in range(n)]


def test_flatten_resolves_regime_widening():
    p = flatten_strategy_params({
        "exits": {"trailing": {"regime_widening": {
            "enabled": True, "lookback_bars": 100, "min_slope_pct": 0.05, "trail_wide": 5}}}
    })
    assert p["trail_regime_enabled"] is True
    assert p["trail_regime_lookback"] == 100
    assert p["trail_regime_min_slope_pct"] == 0.05
    assert p["trail_wide"] == 5


def test_regime_widening_default_off_preserves_legacy():
    pol = _policy()
    assert pol._trail_regime_enabled is False
    strat = SimpleNamespace(_last_p_max=0.0, _candles=_ramp_candles(200))
    assert pol._effective_trail_pct(strat) == 2  # static trail, no widening


def test_regime_widening_widens_in_uptrend_and_reverts_when_flat():
    pol = _policy(trailing={"regime_widening": {
        "enabled": True, "lookback_bars": 50, "min_slope_pct": 0.05, "trail_wide": 5}})
    strat = SimpleNamespace(_last_p_max=0.0, _pos=SimpleNamespace(held_bars=0),
                            _candles=_ramp_candles(60))

    # uptrend ramp: per-candle cache update sets the flag; trail widens to 5
    pol._regime_uptrend = pol._uptrend_slope(strat._candles, 50, 0.05)
    assert pol._regime_uptrend is True
    assert pol._effective_trail_pct(strat) == 5

    # flat tape: flag drops, trail reverts to the static 2
    strat._candles = _flat_candles(60)
    pol._regime_uptrend = pol._uptrend_slope(strat._candles, 50, 0.05)
    assert pol._regime_uptrend is False
    assert pol._effective_trail_pct(strat) == 2


def test_regime_widening_never_tightens():
    # trail_wide below the base trail must not tighten the trail (max() semantics)
    pol = _policy(trailing={"regime_widening": {
        "enabled": True, "lookback_bars": 50, "min_slope_pct": 0.05, "trail_wide": 1}})
    pol._regime_uptrend = True
    assert pol._effective_trail_pct(SimpleNamespace(_last_p_max=0.0)) == 2


def test_regime_widening_insufficient_history_is_safe():
    pol = _policy(trailing={"regime_widening": {
        "enabled": True, "lookback_bars": 100, "min_slope_pct": 0.05, "trail_wide": 5}})
    assert pol._uptrend_slope(_ramp_candles(10), 100, 0.05) is False
