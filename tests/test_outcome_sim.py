"""simulate_exit_outcomes — canonical non-model exit simulator (TD-018)."""

import numpy as np

from trader.policy.outcome import simulate_exit_outcomes


def test_success_before_stale():
    p = {"profit_pct": 7.0, "stop_pct": 20.0, "hold_bars": 50, "stale_exit_enabled": True,
         "stale_check_bars": 10, "stale_min_gain_pct": 0.5}
    closes = [100, 101, 102, 103, 105, 107.5] + [107.5] * 60
    good, ret, ex = simulate_exit_outcomes(closes, p)
    assert good[0] and ret[0] == 7.0 and ex[0] == 5


def test_stale_tier1_fails():
    p = {"profit_pct": 7.0, "stop_pct": 20.0, "hold_bars": 50, "stale_exit_enabled": True,
         "stale_check_bars": 4, "stale_min_gain_pct": 0.5}
    good, ret, ex = simulate_exit_outcomes([100.0] * 80, p)
    assert not good[0] and ex[0] == 4 and ret[0] == 0.0


def test_hard_stop():
    p = {"profit_pct": 7.0, "stop_pct": 10.0, "hold_bars": 50}
    closes = [100, 99, 95, 85] + [85] * 60
    good, ret, ex = simulate_exit_outcomes(closes, p)
    assert not good[0] and ret[0] <= -10.0 and ex[0] == 3


def test_truncated_is_nan():
    p = {"profit_pct": 7.0, "stop_pct": 20.0, "hold_bars": 50}
    good, ret, ex = simulate_exit_outcomes([100.0] * 60, p)
    assert np.isnan(ret[-1]) and np.isnan(ret[55]) and not np.isnan(ret[0])


def test_matches_stage_a():
    from scripts.campaign import stage_a
    assert stage_a.simulate_exits is simulate_exit_outcomes
