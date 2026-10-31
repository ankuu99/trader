"""
Policy layer — entry gates and the exit stack as separable, swappable units.

Extracted from LRExtremaStrategy (Stage 3 of the rearchitecture, see todo_revamp.md).
The model answers "what will price do"; the policy answers "what do I do about it" —
entries (gates) and exits (hold/stale/momentum/pattern-top + tick-speed SL/trailing/
breakeven/EOD). Position state lives in a single PositionState object the policies mutate.

  - base.py         : PositionState, ExitDecision, normalize_params
  - extrema_entry.py: ExtremaEntryPolicy (the entry gates)
  - extrema_exit.py : ExtremaExitPolicy (candle- and tick-speed exits)
"""

from trader.policy.base import ExitDecision, PositionState
from trader.policy.extrema_entry import ExtremaEntryPolicy
from trader.policy.extrema_exit import ExtremaExitPolicy

__all__ = [
    "PositionState",
    "ExitDecision",
    "ExtremaEntryPolicy",
    "ExtremaExitPolicy",
]
