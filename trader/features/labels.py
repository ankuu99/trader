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


def collapse_clusters(indices: list[int], max_gap: int) -> list[int]:
    """Collapse runs of nearby indices (gap <= max_gap) to the cluster centre.

    Flat price plateaus make every tied bar qualify as a geometric extremum,
    double-labelling the same turning point; the lab measured labeler precision
    at 0.5 on zero-noise data purely from this."""
    if not indices:
        return []
    out, cluster = [], [indices[0]]
    for idx in indices[1:]:
        if idx - cluster[-1] <= max_gap:
            cluster.append(idx)
        else:
            out.append(cluster[len(cluster) // 2])
            cluster = [idx]
    out.append(cluster[len(cluster) // 2])
    return out


class Labeler(ABC):
    @abstractmethod
    def label(self, candles: list[dict]) -> tuple[list[int], list[int]]:
        """Return (indices, classes): the candle indices to use as training samples
        and their class labels (0 = buy candidate, 1 = sell candidate). Empty lists
        mean 'not enough signal to train this round'."""


class ExtremaLabeler(Labeler):
    """Geometric local extrema (±extrema_order neighbourhood), with optional
    forward-return filtering of minima (Enhancement A). Behaviour-identical to the
    original LRExtremaStrategy labelling.

    Optional neutral class (labels.neutral): additionally emits class-2 samples
    drawn from candles that are ≥ margin_bars away from every geometric extremum.
    Without it the binary model must split P(min)+P(max)=1 on every candle — an
    ordinary hard-falling candle reads as a near-certain minimum. The neutral class
    gives that probability mass somewhere to go. Sampling is deterministic (evenly
    spaced), so retrains are reproducible."""

    def __init__(self, instrument: str, params: dict):
        self._instrument = instrument
        self._extrema_order: int = int(params.get("extrema_order", 5))
        # labels.collapse_ties: merge tied/adjacent extrema runs to one sample.
        # Default OFF to preserve the live golden-parity behaviour.
        self._collapse_ties: bool = bool(
            (params.get("labels") or {}).get("collapse_ties", False))
        _fl = params.get("forward_label") or {}
        self._fl_enabled: bool = bool(_fl.get("enabled", False))
        self._fl_bars: int = int(_fl.get("forward_bars", 150))
        self._fl_min_return_pct: float = float(_fl.get("min_return_pct", 2.0))
        _nc = (params.get("labels") or {}).get("neutral") or {}
        self._neutral_enabled: bool = bool(_nc.get("enabled", False))
        # neutrals emitted per extremum sample (1.0 => balanced with min+max count)
        self._neutral_ratio: float = float(_nc.get("ratio", 1.0))
        # min distance from any extremum; None => extrema_order
        _margin = _nc.get("margin_bars")
        self._neutral_margin: int = int(_margin) if _margin is not None else self._extrema_order

    def label(self, candles: list[dict]) -> tuple[list[int], list[int]]:
        closes = [c["close"] for c in candles]
        minima, maxima = find_local_extrema(closes, self._extrema_order)
        if self._collapse_ties:
            minima = collapse_clusters(minima, self._extrema_order)
            maxima = collapse_clusters(maxima, self._extrema_order)

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

        if self._neutral_enabled:
            neutrals = self._sample_neutrals(
                len(candles), set(minima), set(maxima), len(indices)
            )
            indices += neutrals
            classes += [2] * len(neutrals)

        return indices, classes

    def _sample_neutrals(
        self, n_candles: int, minima: set, maxima: set, n_extrema: int
    ) -> list[int]:
        return sample_neutrals(n_candles, minima | maxima, self._neutral_margin,
                               round(self._neutral_ratio * n_extrema))


def sample_neutrals(n_candles: int, extrema: set, margin: int, target: int) -> list[int]:
    """Evenly-spaced candle indices ≥ margin bars from every extremum.
    Deterministic — no RNG — so successive retrains on the same window
    produce the same labels. Index 20 onward only (feature min_history=21;
    keeps sample counts honest rather than silently dropped downstream)."""
    excluded = set()
    for e in extrema:
        excluded.update(range(e - margin, e + margin + 1))
    candidates = [i for i in range(20, n_candles) if i not in excluded]
    if target <= 0 or not candidates:
        return []
    if target >= len(candidates):
        return candidates
    step = len(candidates) / target
    picked = {candidates[int(k * step)] for k in range(target)}
    return sorted(picked)


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


def zigzag_pivots(closes: list[float], reversal_pct: float) -> tuple[list[int], list[int]]:
    """Swing pivots by minimum-percent reversal (classic zigzag, no ATR).

    A pivot low is confirmed when price rises >= reversal_pct% off the running
    minimum; a pivot high when it falls >= reversal_pct% off the running maximum.
    Returns (low_indices, high_indices).

    Key property vs the fixed ±order neighbourhood: reversals are measured in %,
    so a dip on a rising baseline is still a dip — trend does not hide it."""
    n = len(closes)
    if n < 3:
        return [], []
    r = reversal_pct / 100.0
    lows: list[int] = []
    highs: list[int] = []
    trend = 0  # 0 unknown, +1 up (seeking high), -1 down (seeking low)
    min_i, min_p = 0, closes[0]
    max_i, max_p = 0, closes[0]
    for i in range(1, n):
        c = closes[i]
        if trend == 0:
            if c < min_p:
                min_i, min_p = i, c
            if c > max_p:
                max_i, max_p = i, c
            if min_p > 0 and c >= min_p * (1 + r):
                lows.append(min_i)
                trend, max_i, max_p = 1, i, c
            elif max_p > 0 and c <= max_p * (1 - r):
                highs.append(max_i)
                trend, min_i, min_p = -1, i, c
        elif trend > 0:  # uptrend: ratchet the max, confirm a high on -r reversal
            if c > max_p:
                max_i, max_p = i, c
            elif max_p > 0 and c <= max_p * (1 - r):
                highs.append(max_i)
                trend, min_i, min_p = -1, i, c
        else:  # downtrend: ratchet the min, confirm a low on +r reversal
            if c < min_p:
                min_i, min_p = i, c
            elif min_p > 0 and c >= min_p * (1 + r):
                lows.append(min_i)
                trend, max_i, max_p = 1, i, c
    return lows, highs


class ZigZagLabeler(Labeler):
    """Zigzag swing-pivot labels (`labels.type: zigzag`).

    Pivot lows -> class 0 (buy candidate), pivot highs -> class 1. Like the other
    labelers, confirmation uses forward candles — fine for *training* labels; the
    model still predicts from past-only features at inference.

    Config: labels.zigzag.reversal_pct (minimum % reversal to confirm a pivot).

    Volatility-scaled reversal (labels.zigzag.vol_scaled): instead of one fixed
    percentage across stocks with very different volatilities, the reversal is
    k × σ where σ is the std of bar-to-bar % returns over the training window
    (close-only — deliberately NOT ATR), clamped to [min_pct, max_pct]. The label
    scale then adapts per stock AND per retrain window, removing the fragile
    reversal_pct magic number (the fixed 5% was a spike, not a plateau —
    neighbours 4%/6% scored 33-52% worse on the 2025-26 day-TF sweep)."""

    def __init__(self, instrument: str, params: dict):
        self._instrument = instrument
        _labels = params.get("labels") or {}
        _zz = _labels.get("zigzag") or {}
        self._reversal_pct: float = float(_zz.get("reversal_pct", 2.0))
        _vs = _zz.get("vol_scaled") or {}
        self._vol_scaled: bool = bool(_vs.get("enabled", False))
        self._vol_k: float = float(_vs.get("k", 2.5))
        self._vol_min_pct: float = float(_vs.get("min_pct", 1.0))
        self._vol_max_pct: float = float(_vs.get("max_pct", 10.0))
        _nc = _labels.get("neutral") or {}
        self._neutral_enabled: bool = bool(_nc.get("enabled", False))
        self._neutral_ratio: float = float(_nc.get("ratio", 1.0))
        _margin = _nc.get("margin_bars")
        self._neutral_margin: int = int(_margin) if _margin is not None else 10

    def _effective_reversal_pct(self, closes: list[float]) -> float:
        if not self._vol_scaled or len(closes) < 20:
            return self._reversal_pct
        rets = [(b - a) / a * 100.0 for a, b in zip(closes[:-1], closes[1:]) if a > 0]
        if len(rets) < 19:
            return self._reversal_pct
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        sigma = var ** 0.5
        return max(self._vol_min_pct, min(self._vol_max_pct, self._vol_k * sigma))

    def label(self, candles: list[dict]) -> tuple[list[int], list[int]]:
        closes = [c["close"] for c in candles]
        lows, highs = zigzag_pivots(closes, self._effective_reversal_pct(closes))
        if len(lows) < MIN_SAMPLES_PER_CLASS or len(highs) < MIN_SAMPLES_PER_CLASS:
            logger.warning(
                "ZigZag | %s | not enough pivots to train (low=%d high=%d)",
                self._instrument, len(lows), len(highs),
            )
            return [], []
        indices = lows + highs
        classes = [0] * len(lows) + [1] * len(highs)
        if self._neutral_enabled:
            neutrals = sample_neutrals(
                len(candles), set(indices), self._neutral_margin,
                round(self._neutral_ratio * len(indices)))
            indices += neutrals
            classes += [2] * len(neutrals)
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
    if ltype == "zigzag":
        return ZigZagLabeler(instrument, params)
    raise ValueError(
        f"Unknown labeler type {ltype!r}. Available: ['extrema', 'trend_scan', 'zigzag']")
