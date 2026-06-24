"""Unit tests for the exit-action additions:
- flatten_strategy_params resolves the new nested toggles to flat keys
- ExtremaExitPolicy confidence-sized trailing distance interpolation
- toggle defaults preserve legacy behaviour
"""
from types import SimpleNamespace

from trader.core.config import flatten_strategy_params
from trader.policy.extrema_exit import ExtremaExitPolicy


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
