"""
Stale re-arm tests.

Tier-1 stale keys on best-gain-since-entry, one-shot: any early pop >= min_gain_pct
disarms it for the life of the position (the GESHIP/REDTAPE unguarded-runway failure).
With `exits.stale.rearm` enabled, the progress check re-runs at every check_bars
multiple over a ROLLING window — exit (reason STALE_REARM) iff the best gain over the
last check_bars bars is < min_gain_pct AND current gain < cur_floor_pct.

Config-gated, defaults OFF; the last test guards that inertness.
"""
from types import SimpleNamespace

from trader.core.config import flatten_strategy_params
from trader.policy.base import PositionState
from trader.policy.extrema_exit import ExtremaExitPolicy


class _FakeStrat:
    instrument = "NSE:TEST"

    def __init__(self, closes=()):
        self._pos = PositionState()
        self._last_p_max = 0.0
        self._candles = [{"close": c} for c in closes]
        self.signal_log = []
        self._model = SimpleNamespace(is_trained=False)

    def is_flat(self) -> bool:
        return self._pos.entry_price is None


def _policy(rearm=None):
    cfg = {"exits": {
        "hold_bars": 100,
        "hard_stop": {"stop_pct": 20},
        "stale": {"check_bars": 10, "min_gain_pct": 0.5,
                  **({"rearm": rearm} if rearm is not None else {})},
    }}
    return ExtremaExitPolicy(flatten_strategy_params(cfg))


def _popped_strat(closes, held_bars=20, entry=100.0):
    """A position whose early pop disarmed tier-1 (max_gain_pct >= min_gain)."""
    s = _FakeStrat(closes)
    s._pos.entry_price = entry
    s._pos.held_bars = held_bars
    s._pos.max_gain_pct = 1.0
    return s


REARM = {"enabled": True, "cur_floor_pct": -2.0}


def test_flatten_resolves_rearm_keys():
    p = flatten_strategy_params(
        {"exits": {"stale": {"check_bars": 10, "rearm": {"enabled": True, "cur_floor_pct": -3.0}}}})
    assert p["stale_rearm_enabled"] is True
    assert p["stale_rearm_cur_floor_pct"] == -3.0
    # presence without enabled: true stays off
    p2 = flatten_strategy_params({"exits": {"stale": {"rearm": {"cur_floor_pct": -3.0}}}})
    assert p2["stale_rearm_enabled"] is False


def test_rearm_fires_at_checkpoint_when_underwater_and_no_recent_pop():
    pol = _policy(REARM)
    s = _popped_strat([97.0] * 10, held_bars=20)   # rolling best -3% < 0.5%, cur -3% < -2%
    d = pol.candle_exit(s, {"timestamp": "t", "close": 97.0}, 97.0)
    assert d is not None
    assert d.exit_reason == "STALE_REARM"


def test_rearm_only_evaluates_at_check_bars_multiples():
    pol = _policy(REARM)
    s = _popped_strat([97.0] * 10, held_bars=21)   # 21 is not a multiple of 10
    assert pol.candle_exit(s, {"timestamp": "t", "close": 97.0}, 97.0) is None


def test_rearm_spares_position_above_current_floor():
    pol = _policy(REARM)
    s = _popped_strat([99.0] * 10, held_bars=20)   # cur -1% is above the -2% floor
    assert pol.candle_exit(s, {"timestamp": "t", "close": 99.0}, 99.0) is None


def test_rearm_spares_position_with_recent_pop():
    pol = _policy(REARM)
    closes = [97.0] * 9 + [101.0]                  # rolling best +1% >= 0.5%
    s = _popped_strat(closes, held_bars=20)
    assert pol.candle_exit(s, {"timestamp": "t", "close": 97.0}, 97.0) is None


def test_rearm_fires_again_at_later_multiples():
    pol = _policy(REARM)
    s = _popped_strat([97.0] * 10, held_bars=30)   # 3x check_bars
    d = pol.candle_exit(s, {"timestamp": "t", "close": 97.0}, 97.0)
    assert d is not None and d.exit_reason == "STALE_REARM"


def test_tier1_still_fires_first_when_never_popped():
    """A position that never popped exits via plain STALE at check_bars — the
    re-arm path must not change tier-1 behaviour."""
    pol = _policy(REARM)
    s = _FakeStrat([97.0] * 10)
    s._pos.entry_price = 100.0
    s._pos.held_bars = 10
    s._pos.max_gain_pct = 0.1                      # never reached 0.5%
    d = pol.candle_exit(s, {"timestamp": "t", "close": 97.0}, 97.0)
    assert d is not None
    assert d.exit_reason == "STALE"


def test_rearm_disabled_by_default_is_inert():
    pol = _policy()                                # no rearm block at all
    s = _popped_strat([97.0] * 10, held_bars=20)
    assert pol.candle_exit(s, {"timestamp": "t", "close": 97.0}, 97.0) is None
