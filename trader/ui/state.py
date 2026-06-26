"""
BotState — lightweight shared object between the main bot thread and the dashboard thread.

The main thread writes; the dashboard thread reads only.
All field types (datetime, bool, dict) are safe to read without locks under CPython's GIL.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class BotState:
    started_at: datetime = field(default_factory=datetime.now)
    last_candle_at: datetime | None = None  # updated by handle_candle() on every candle
    halted: bool = False                    # mirrors risk.is_halted()
    warmup_done: bool = False               # set True after strategy warm-up completes
    warmup_status: dict = field(default_factory=dict)
    # warmup_status shape: { "NSE:SYMBOL": {"status": "TRAINED"|"WARMING_UP"|"N/A", "candles": int} }
    model_scores: dict = field(default_factory=dict)
    # model_scores shape: { "NSE:SYMBOL": {"p_min": float, "p_max": float,
    #   "drivers": [ {"name": str, "value": float, "kind": "contrib"|"raw"}, ... ] } }
