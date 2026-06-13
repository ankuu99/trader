"""
PARITY / characterization harness — Stage 0 prestage for the rearchitecture.

Purpose
-------
Stages 1-3 of the rearchitecture (todo_revamp.md) are *behaviour-preserving*
refactors: extracting FeaturePipeline / Model / Policy out of the
LRExtremaStrategy monolith. The only way to *prove* behaviour is unchanged is to
freeze the system's exact numeric output now and assert byte-equality after every
refactor.

Unlike test_strategy_flows.py (which stubs the model + scaler and only checks
flow), and unlike test_integration.py (which checks sanity *invariants*), this
file pins the **exact** output:

  1. test_feature_vector_golden  — the real _compute_features output on a fixed
     candle fixture, with the depth/MACD add-ons both off and on. This is the
     targeted check for Stage 1 (FeaturePipeline extraction).
  2. test_pipeline_golden        — the full Strategy -> RiskManager -> OrderManager
     chain replayed over the real HAL fixture, snapshotting every trade and every
     signal. Covers Stages 2 (Model) and 3 (Policy) too.

Determinism
-----------
Verified bit-reproducible across fresh processes. sklearn solver output can drift
across library minor versions, so the golden is version-bound: if numpy/sklearn
are upgraded and this test fails, regenerate the golden in a *dedicated, reviewed*
commit (never silently) and note the version bump.

  Pinned at generation time: numpy 2.4.4, scikit-learn 1.8.0

Regenerating the golden (only when behaviour is *intentionally* changed):
    REGEN_GOLDEN=1 .venv/bin/python -m pytest tests/test_parity_golden.py -q

Normal run (asserts equality):
    .venv/bin/python -m pytest tests/test_parity_golden.py -q
"""

import json
import os
from pathlib import Path

import numpy as np

from trader.strategies.lr_extrema import LRExtremaStrategy

# Reuse the integration harness (real chain, no stubs) and its fixture loader.
from .test_integration import (
    Config,
    PipelineRunner,
    _STRATEGY_PARAMS,
    _TEST_CONFIG_DATA,
    _patched_config,
    load_candles,
    simulate_ticks,
    FIXTURE_DIR,
    INSTRUMENT,
)

GOLDEN_DIR = Path(__file__).parent / "fixtures"
GOLDEN_PIPELINE = GOLDEN_DIR / "golden_pipeline.json"
GOLDEN_FEATURES = GOLDEN_DIR / "golden_features.json"

_REGEN = os.environ.get("REGEN_GOLDEN") == "1"

# Precision for float comparison — pipeline is deterministic on a fixed machine,
# this guards only against last-bit cross-platform noise.
_FEATURE_ROUND = 9
_PIPELINE_ROUND = 6


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_candles():
    return load_candles(FIXTURE_DIR / "candles.csv", INSTRUMENT)


def _round(v, places):
    return round(v, places) if isinstance(v, float) else v


def _compare_or_write(path: Path, snapshot: dict):
    """If REGEN, write the snapshot. Else load the golden and assert equality."""
    if _REGEN:
        path.write_text(json.dumps(snapshot, indent=2, default=str, sort_keys=True))
        return
    assert path.exists(), (
        f"Golden file {path.name} missing. Generate it once with "
        f"REGEN_GOLDEN=1 pytest tests/test_parity_golden.py"
    )
    golden = json.loads(path.read_text())
    # Round-trip the fresh snapshot through json so types match the golden exactly.
    fresh = json.loads(json.dumps(snapshot, default=str, sort_keys=True))
    assert fresh == golden, (
        f"Parity FAILED against {path.name}. Behaviour changed. If this change is "
        f"intentional, regenerate the golden with REGEN_GOLDEN=1 in a dedicated commit."
    )


# ---------------------------------------------------------------------------
# 0a. Feature-vector golden — the targeted Stage-1 check
# ---------------------------------------------------------------------------

def test_feature_vector_golden():
    """Pin the real _compute_features output at several indices, with the
    depth/MACD add-ons both disabled (6 features) and enabled (9 features)."""
    candles = _load_candles()

    # Indices spanning warmup edge -> end of fixture.
    sample_idx = [25, 100, 300, 700, 1200, len(candles) - 1]

    variants = {
        "base6": dict(_STRATEGY_PARAMS),
        "depth_macd9": {
            **_STRATEGY_PARAMS,
            # Stage 1: feature add-ons live under the nested features: block.
            # Values match the pre-Stage-1 flat depth_feature/macd_feature exactly,
            # so the golden vectors are unchanged.
            "features": {
                "volume_ma_bars": 5,
                "depth": {"enabled": True, "lookback_bars": 50},
                "macd": {"enabled": True, "fast": 12, "slow": 26,
                         "signal_period": 9, "hist_lookback": 5},
            },
        },
    }

    snapshot: dict = {}
    for vname, params in variants.items():
        strat = LRExtremaStrategy(INSTRUMENT, params)
        rows = {}
        for idx in sample_idx:
            feat = strat._features.compute(candles[: idx + 1])
            rows[str(idx)] = (
                None if feat is None
                else [round(float(x), _FEATURE_ROUND) for x in feat]
            )
        snapshot[vname] = rows

    _compare_or_write(GOLDEN_FEATURES, snapshot)


# ---------------------------------------------------------------------------
# 0b. End-to-end pipeline golden — covers Stages 2 & 3 too
# ---------------------------------------------------------------------------

def _run_pipeline_snapshot() -> dict:
    cfg = Config(_TEST_CONFIG_DATA)
    candles = _load_candles()
    with _patched_config(cfg):
        runner = PipelineRunner(INSTRUMENT, _STRATEGY_PARAMS, cfg)
        for candle in candles:
            runner.run_candle(candle)
            for tick in simulate_ticks(candle):
                runner.run_tick(tick)

    s = runner.summary()
    return {
        "trades": [
            {k: _round(v, _PIPELINE_ROUND) for k, v in t.items()}
            for t in runner.trades
        ],
        "signals": [
            {"type": sig["type"], "price": _round(sig["price"], _PIPELINE_ROUND)}
            for sig in runner.signals
        ],
        "filter_block_reasons": [fb["reason"] for fb in runner.filter_blocks],
        "aggregate": {
            "total_candles": s["total_candles"],
            "signals_entry": s["signals_entry"],
            "signals_exit": s["signals_exit"],
            "entry_fills": s["entry_fills"],
            "exit_fills": s["exit_fills"],
            "rejected_cancelled": s["rejected_cancelled"],
            "trades_closed": s["trades_closed"],
            "wins": s["wins"],
            "losses": s["losses"],
            "total_pnl": _round(s["total_pnl"], _PIPELINE_ROUND),
            "best_trade_pnl": _round(s["best_trade_pnl"], _PIPELINE_ROUND),
            "worst_trade_pnl": _round(s["worst_trade_pnl"], _PIPELINE_ROUND),
            "peak_capital_deployed": _round(s["peak_capital_deployed"], _PIPELINE_ROUND),
        },
    }


def test_pipeline_golden():
    """Replay the real fixture through the full chain and assert every trade and
    signal matches the frozen golden exactly."""
    snapshot = _run_pipeline_snapshot()
    _compare_or_write(GOLDEN_PIPELINE, snapshot)


# ---------------------------------------------------------------------------
# 0c. Determinism guard — same process, two runs must be identical
# ---------------------------------------------------------------------------

def test_pipeline_is_deterministic():
    """Two runs in the same process must produce byte-identical snapshots.
    (Cross-process determinism is verified manually; see module docstring.)"""
    a = _run_pipeline_snapshot()
    b = _run_pipeline_snapshot()
    assert json.dumps(a, sort_keys=True, default=str) == \
        json.dumps(b, sort_keys=True, default=str)
