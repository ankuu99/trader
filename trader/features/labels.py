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
from trader.features.indicators import find_local_extrema

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


def build_labeler(instrument: str, params: dict) -> Labeler:
    """Factory: returns the configured labeler. Driven by the nested `labels.type`
    config (default: extrema). Kept as a plug point for future labelers."""
    labels_cfg = params.get("labels") or {}
    ltype = labels_cfg.get("type", "extrema")
    if ltype == "extrema":
        return ExtremaLabeler(instrument, params)
    raise ValueError(f"Unknown labeler type {ltype!r}. Available: ['extrema']")
