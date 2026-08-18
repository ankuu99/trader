"""
Full-state restore after a rejected EXIT order (CAS failure mode).

A FULL exit resets PositionState at signal emission; if the order is then
rejected (e.g. a last-candle exit dying in Zerodha's 15:30 Closing Auction
Session), the whole pre-emission state — hold/stale clocks, trail anchor,
scale-out guard — must come back, not just the entry price (TVSMOTOR
2026-08-17: held_bars 200->0 silently deferred a timeout exit ~8 sessions).
"""
from datetime import datetime

from trader.strategies.lr_extrema import LRExtremaStrategy
from trader.strategies.base import Direction, SignalType


_PARAMS = {
    "warmup_bars":    5,
    "threshold":      0.70,
    "profit_pct":     4.0,
    "stop_pct":       2.0,
    "hold_bars":      5,
    "retrain_every":  50,
    "extrema_order":  2,
}


def _candle(close):
    return {
        "open": close, "high": close, "low": close, "close": close,
        "volume": 1000, "timestamp": datetime(2025, 6, 1, 10, 0),
    }


def _in_position_strategy() -> LRExtremaStrategy:
    """Strategy holding a position with rich, non-default PositionState."""
    strat = LRExtremaStrategy("NSE:TEST", _PARAMS)
    strat._candles.extend(_candle(100.0) for _ in range(25))
    strat.position = Direction.BUY
    pos = strat._pos
    pos.entry_price = 100.0
    pos.fill_price = 100.0
    pos.held_bars = 200
    pos.peak_close = 112.0
    pos.trailing_active = True
    pos.pattern_top_trailing = True
    pos.max_gain_pct = 12.0
    pos.breakeven_active = True
    pos.partial_taken = True
    return strat


def _order(status, *, partial=False):
    return {
        "instrument": "NSE:TEST",
        "direction": Direction.SELL,
        "signal_type": SignalType.EXIT,
        "status": status,
        "price": 111.0,
        "quantity": 9,
        "partial": partial,
    }


def _emit_hold_bars_exit(strat):
    """Drive the policy's hold-bars exit (held_bars >= hold_bars) — resets state
    at emission exactly as live does."""
    decision = strat._exit_policy.candle_exit(strat, _candle(111.0), 111.0)
    assert decision is not None and decision.exit_reason == "STRATEGY"
    # emission wiped the live fields
    assert strat._pos.entry_price is None
    assert strat._pos.held_bars == 0
    return decision


def test_rejected_exit_restores_full_state():
    strat = _in_position_strategy()
    _emit_hold_bars_exit(strat)

    strat.on_order_update(_order("REJECTED"))

    pos = strat._pos
    assert pos.entry_price == 100.0
    assert pos.held_bars == 200
    assert pos.peak_close == 112.0
    assert pos.trailing_active is True
    assert pos.pattern_top_trailing is True
    assert pos.max_gain_pct == 12.0
    assert pos.breakeven_active is True
    assert pos.partial_taken is True
    assert strat.position == Direction.BUY  # base leaves position flag intact


def test_rejected_exit_retriggers_hold_bars_next_candle():
    """After restore, the hold-bars timeout must re-fire on the next candle."""
    strat = _in_position_strategy()
    _emit_hold_bars_exit(strat)
    strat.on_order_update(_order("REJECTED"))

    decision = strat._exit_policy.candle_exit(strat, _candle(110.0), 110.0)
    assert decision is not None and decision.exit_reason == "STRATEGY"


def test_complete_exit_clears_state_and_snapshot():
    strat = _in_position_strategy()
    _emit_hold_bars_exit(strat)

    strat.on_order_update(_order("COMPLETE"))

    pos = strat._pos
    assert pos.entry_price is None
    assert pos.held_bars == 0
    assert pos.trailing_active is False
    assert pos.partial_taken is False
    assert strat.position is None
    # snapshot discarded — a later spurious rejection restores nothing
    assert pos.restore_snapshot() is False


def test_partial_scale_out_fill_untouched():
    """A partial (scale-out) COMPLETE fill keeps the position state intact."""
    strat = _in_position_strategy()

    strat.on_order_update(_order("COMPLETE", partial=True))

    pos = strat._pos
    assert pos.entry_price == 100.0
    assert pos.held_bars == 200
    assert pos.trailing_active is True
    assert strat.position == Direction.BUY


def test_cancelled_exit_restores_like_rejected():
    strat = _in_position_strategy()
    _emit_hold_bars_exit(strat)

    strat.on_order_update(_order("CANCELLED"))

    assert strat._pos.entry_price == 100.0
    assert strat._pos.held_bars == 200


def test_no_snapshot_falls_back_to_fill_price():
    """Restart between emission and rejection: no snapshot — legacy fallback."""
    strat = _in_position_strategy()
    _emit_hold_bars_exit(strat)
    strat._pos.clear_snapshot()  # simulate snapshot lost to a restart

    strat.on_order_update(_order("REJECTED"))

    assert strat._pos.entry_price == 100.0  # from surviving fill_price
    assert strat._pos.held_bars == 0        # clocks are genuinely gone in this path


def test_new_entry_discards_stale_exit_snapshot():
    """A COMPLETE ENTRY begins a new lifecycle — an old exit snapshot must not
    restore into it if that position's exit later gets rejected... the fresh
    emission snapshot (not the stale one) must win."""
    strat = _in_position_strategy()
    _emit_hold_bars_exit(strat)          # snapshot with held_bars=200 pending
    strat.on_order_update(_order("COMPLETE"))  # exit fills — snapshot discarded

    entry = {
        "instrument": "NSE:TEST",
        "direction": Direction.BUY,
        "signal_type": SignalType.ENTRY,
        "status": "COMPLETE",
        "price": 105.0,
        "quantity": 9,
    }
    strat.on_order_update(entry)
    assert strat._pos.entry_price == 105.0
    assert strat._pos.held_bars == 0
    assert strat._pos.restore_snapshot() is False
