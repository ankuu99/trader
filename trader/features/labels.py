"""
Labeler abstraction — decides which historical candles are training examples and
their class (0 = local-minimum / buy candidate, 1 = local-maximum / sell candidate).

Extracted from LRExtremaStrategy._train (Stage 4) so label generation is a swappable
plug point. `ExtremaLabeler` reproduces today's geometric-extrema + forward-return
labels exactly. A model is only as good as its labels, so this is the natural place
to add alternative labelers (triple-barrier, meta-labeling, …) in future — they plug
in via `build_labeler` / `labels.type` without touching the strategy.

The labeler returns parallel (indices, classes) lists in the original order
(qualified minima first, then maxima) so the downstream LogisticRegression fit is
byte-identical to the pre-extraction code.
"""

from abc import ABC, abstractmethod

from trader.core.logger import get_logger
from trader.features.indicators import find_local_extrema, linreg_tstat

logger = get_logger(__name__)

# Need at least this many of each class to train a meaningful classifier.
MIN_SAMPLES_PER_CLASS = 2


class Labeler(ABC):
    @abstractmethod
    def label(self, candles: list[dict]) -> tuple[list[int], list[int]]:
        """Return (indices, classes): the candle indices to use as training samples
        and their class labels (0 = buy candidate, 1 = sell candidate). Empty lists
        mean 'not enough signal to train this round'."""


class ExtremaLabeler(Labeler):
    """Geometric local extrema (±extrema_order neighbourhood), with optional
    forward-return filtering of minima (Enhancement A). Behaviour-identical to the
    original LRExtremaStrategy labelling."""

    def __init__(self, instrument: str, params: dict):
        self._instrument = instrument
        self._extrema_order: int = int(params.get("extrema_order", 5))
        _fl = params.get("forward_label") or {}
        self._fl_enabled: bool = bool(_fl.get("enabled", False))
        self._fl_bars: int = int(_fl.get("forward_bars", 150))
        self._fl_min_return_pct: float = float(_fl.get("min_return_pct", 2.0))

    def label(self, candles: list[dict]) -> tuple[list[int], list[int]]:
        closes = [c["close"] for c in candles]
        minima, maxima = find_local_extrema(closes, self._extrema_order)

        if len(minima) < MIN_SAMPLES_PER_CLASS or len(maxima) < MIN_SAMPLES_PER_CLASS:
            logger.warning(
                "LR-Extrema | %s | not enough extrema to train (min=%d max=%d)",
                self._instrument, len(minima), len(maxima),
            )
            return [], []

        # Optionally filter minima by forward return — keep a minimum only if price
        # actually rose >= min_return_pct over the next forward_bars (peak return).
        qualified_minima: list[int] = []
        filtered_out = 0
        for idx in minima:
            if self._fl_enabled:
                fwd_end = min(idx + self._fl_bars, len(candles) - 1)
                if fwd_end > idx:
                    entry_close = candles[idx]["close"]
                    fwd_peak = max(c["close"] for c in candles[idx + 1 : fwd_end + 1])
                    fwd_return = (fwd_peak - entry_close) / entry_close * 100.0 if entry_close > 0 else 0.0
                    if fwd_return < self._fl_min_return_pct:
                        filtered_out += 1
                        continue  # false bottom — never bounced enough
            qualified_minima.append(idx)

        # Fallback: if the filter removed too many, revert to all geometric minima.
        if self._fl_enabled and len(qualified_minima) < MIN_SAMPLES_PER_CLASS:
            logger.warning(
                "LR-Extrema | %s | forward-label filter too strict — kept %d/%d minima "
                "(filtered %d); reverting to geometric labels for this training round",
                self._instrument, len(qualified_minima), len(minima), filtered_out,
            )
            qualified_minima = list(minima)

        indices = qualified_minima + list(maxima)
        classes = [0] * len(qualified_minima) + [1] * len(maxima)
        return indices, classes


class TrendScanningLabeler(Labeler):
    """Trend-scanning labels (López de Prado, *ML for Asset Managers*).

    For each candle, fit forward regressions over every horizon in
    [min_bars, max_bars] and keep the one with the largest |t-stat| on the slope —
    a *statistically chosen* horizon per candle rather than a fixed neighbourhood.
    This is the principled, dynamic-horizon alternative to ExtremaLabeler's fixed
    ±extrema_order window.

    For this buy-the-dip primary the mapping is: a strong forward *up*-trend
    (t-stat >= +t_threshold) marks a bottom -> class 0 (buy candidate); a strong
    forward *down*-trend (t-stat <= -t_threshold) marks a top -> class 1. Candles
    whose best |t-stat| is below the threshold are unlabelled (no clear trend).

    Like ExtremaLabeler, labels use forward candles — fine for *training* labels
    (the model still predicts from past-only features at inference)."""

    def __init__(self, instrument: str, params: dict):
        self._instrument = instrument
        _ts = (params.get("labels") or {}).get("trend_scan") or {}
        self._min_bars: int = int(_ts.get("min_bars", 10))
        self._max_bars: int = int(_ts.get("max_bars", 60))
        self._t_threshold: float = float(_ts.get("t_threshold", 2.0))

    def label(self, candles: list[dict]) -> tuple[list[int], list[int]]:
        closes = [c["close"] for c in candles]
        n = len(closes)
        minima: list[int] = []
        maxima: list[int] = []
        for i in range(0, n - self._min_bars):
            best_t = 0.0
            best_sign = 0
            for L in range(self._min_bars, self._max_bars + 1):
                end = i + L
                if end >= n:
                    break
                _slope, t = linreg_tstat(closes[i: end + 1])
                if abs(t) > abs(best_t):
                    best_t = t
                    best_sign = 1 if t > 0 else -1
            if abs(best_t) >= self._t_threshold:
                if best_sign > 0:
                    minima.append(i)   # forward uptrend -> bottom -> buy candidate
                else:
                    maxima.append(i)   # forward downtrend -> top -> sell candidate

        if len(minima) < MIN_SAMPLES_PER_CLASS or len(maxima) < MIN_SAMPLES_PER_CLASS:
            logger.warning(
                "TrendScan | %s | not enough labels (up=%d down=%d)",
                self._instrument, len(minima), len(maxima),
            )
            return [], []
        indices = minima + maxima
        classes = [0] * len(minima) + [1] * len(maxima)
        return indices, classes


def triple_barrier_label(
    candles: list[dict], entry_idx: int, profit_pct: float, stop_pct: float, max_bars: int,
    atr: float | None = None, atr_mult_pt: float | None = None, atr_mult_sl: float | None = None,
) -> int | None:
    """Meta-label one candidate entry by the triple-barrier method.

    Barriers are percentage-based by default (profit barrier entry × (1+profit_pct/100),
    stop barrier entry × (1-stop_pct/100)). If `atr` and the matching `atr_mult_*` are
    supplied, that side uses a volatility-scaled barrier instead (entry ± atr_mult·ATR) —
    Phase 3a: barriers adapt to each stock's volatility rather than a fixed %.

    A vertical (time) barrier sits max_bars ahead. Returns 1 if the profit barrier is hit
    first, 0 if the stop is hit first, and falls back to the sign of P&L at the time barrier.

    Returns **None** when the full barrier window extends past the available
    candles (entry_idx + max_bars > last index) — the outcome is unknown, so the
    sample is dropped. This is the leakage/truncation guard: callers only ever
    pass candle history up to "now", so a non-None label is always fully resolved
    within the past.

    Intrabar tie (both barriers touched in the same candle) is resolved
    conservatively as a stop (loss), matching the engine's pessimistic fills.
    """
    last = len(candles) - 1
    end = entry_idx + max_bars
    if end > last:
        return None
    entry = candles[entry_idx]["close"]
    if entry <= 0:
        return None
    if atr and atr_mult_pt:
        pt = entry + atr_mult_pt * atr
    else:
        pt = entry * (1 + profit_pct / 100.0)
    if atr and atr_mult_sl:
        sl = entry - atr_mult_sl * atr
    else:
        sl = entry * (1 - stop_pct / 100.0)
    for j in range(entry_idx + 1, end + 1):
        if candles[j]["low"] <= sl:
            return 0
        if candles[j]["high"] >= pt:
            return 1
    return 1 if candles[end]["close"] > entry else 0


def build_labeler(instrument: str, params: dict) -> Labeler:
    """Factory: returns the configured labeler. Driven by the nested `labels.type`
    config (default: extrema). Kept as a plug point for future labelers."""
    labels_cfg = params.get("labels") or {}
    ltype = labels_cfg.get("type", "extrema")
    if ltype == "extrema":
        return ExtremaLabeler(instrument, params)
    if ltype == "trend_scan":
        return TrendScanningLabeler(instrument, params)
    raise ValueError(f"Unknown labeler type {ltype!r}. Available: ['extrema', 'trend_scan']")
