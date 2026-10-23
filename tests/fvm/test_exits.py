"""Exit stack: precedence + each clock (thesis / price / trailing / valuation / recycle)."""

import pandas as pd

from trader.fvm import exits

BASE = [100.0] * 40 + [102, 104, 106, 108, 110, 112, 114, 116, 118, 120]  # ma10>ma40, close 120


def weekly(closes):
    ts = pd.date_range("2024-01-05", periods=len(closes), freq="W-FRI")
    return pd.DataFrame({"timestamp": ts, "open": closes, "high": closes,
                         "low": [c * 0.98 for c in closes], "close": closes,
                         "volume": [1000.0] * len(closes)})


def _state(entry, wsnh=0, peak=None, trimmed=False):
    return {"entry_price": entry, "peak_close": peak or entry,
            "weeks_since_new_high": wsnh, "trimmed": trimmed}


def test_thesis_break_takes_precedence():
    # healthy price but veto failed -> still exits on the thesis clock
    act, reason = exits.decide_exit(weekly(BASE), _state(100), veto_passed=False, peg=1.0)
    assert (act, reason) == (exits.EXIT, "thesis_break")


def test_hold_when_everything_intact():
    act, reason = exits.decide_exit(weekly(BASE), _state(100), veto_passed=True, peg=1.5)
    assert (act, reason) == (exits.HOLD, None)


def test_price_break_when_underwater_below_40w():
    closes = [100.0] * 40 + [102, 104, 106, 108, 110, 112, 114, 116, 118, 95]
    act, reason = exits.decide_exit(weekly(closes), _state(150), veto_passed=True)
    assert (act, reason) == (exits.EXIT, "price_break")     # not in profit -> wide 40w stop


def test_trailing_when_in_profit_below_10w():
    closes = [100.0] * 40 + [102, 104, 106, 108, 110, 112, 114, 116, 118, 108]
    act, reason = exits.decide_exit(weekly(closes), _state(80), veto_passed=True)
    assert (act, reason) == (exits.EXIT, "trailing")        # in profit -> tightened 10w stop


def test_valuation_exhaustion_trims():
    act, reason = exits.decide_exit(weekly(BASE), _state(100), veto_passed=True, peg=4.5)
    assert (act, reason) == (exits.TRIM, "valuation_exhaustion")


def test_valuation_exhaustion_not_repeated_after_trim():
    act, reason = exits.decide_exit(weekly(BASE), _state(100, trimmed=True), veto_passed=True, peg=4.5)
    assert act == exits.HOLD


def test_recycle_after_stall():
    act, reason = exits.decide_exit(weekly(BASE), _state(100, wsnh=exits.RECYCLE_WEEKS),
                                    veto_passed=True, peg=1.0)
    assert (act, reason) == (exits.EXIT, "recycle")


def test_update_tracking_resets_on_new_high():
    s = _state(100, wsnh=5, peak=110)
    exits.update_tracking(s, 115)            # new high
    assert s["peak_close"] == 115 and s["weeks_since_new_high"] == 0
    exits.update_tracking(s, 112)            # no new high
    assert s["weeks_since_new_high"] == 1
