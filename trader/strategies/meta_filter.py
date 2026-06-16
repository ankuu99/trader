"""
MetaFilter — meta-labeling precision gate, owned by LRExtremaStrategy.

Wraps the secondary stack (MetaFeaturePipeline + MetaModel + triple-barrier labels).
It is a no-op when disabled or untrained, so it slots into the strategy without
changing default behaviour (parity-preserving).

Lifecycle:
  - train(...) : called from the strategy's _train after the primary is fit. Scans the
                 (past-only) candle buffer for primary firings, triple-barrier-labels
                 each, computes meta-features, and fits the MetaModel.
  - allow(x)   : called at the entry site. Returns (take_trade, p_win). When disabled or
                 untrained, returns (True, 1.0) so entries pass through unchanged.
"""

from trader.core.logger import get_logger
from trader.features.indicators import atr_at
from trader.features.labels import MIN_SAMPLES_PER_CLASS, triple_barrier_label
from trader.features.meta_features import MetaFeaturePipeline
from trader.models.meta import MetaModel

logger = get_logger(__name__)


class MetaFilter:
    def __init__(self, instrument: str, params: dict):
        self._instrument = instrument
        meta = params.get("meta_label") or {}
        self.enabled: bool = bool(meta.get("enabled", False))
        self.meta_threshold: float = float(meta.get("meta_threshold", 0.5))
        _sizing = meta.get("sizing") or {}
        self.sizing_enabled: bool = bool(_sizing.get("enabled", False))
        self._size_min_fraction: float = float(_sizing.get("min_fraction", 0.5))
        self._size_max_fraction: float = float(_sizing.get("max_fraction", 1.0))
        self._features = MetaFeaturePipeline(meta.get("features") or {})
        self._model = MetaModel(meta.get("model") or {})
        _b = meta.get("barriers") or {}
        self._b_profit = _b.get("profit_pct")
        self._b_stop = _b.get("stop_pct")
        self._b_maxbars = _b.get("max_bars")
        # Phase 3a: ATR-scaled barriers. When atr_mult_pt/sl set, the label uses
        # entry ± mult·ATR instead of the % barrier on that side.
        self._atr_mult_pt = _b.get("atr_mult_pt")
        self._atr_mult_sl = _b.get("atr_mult_sl")
        self._atr_period = int(_b.get("atr_period", 14))

    @property
    def is_trained(self) -> bool:
        return self._model.is_trained

    def _barriers(self, exit_defaults: dict) -> tuple[float, float, int]:
        profit = self._b_profit if self._b_profit is not None else exit_defaults["profit_pct"]
        stop = self._b_stop if self._b_stop is not None else exit_defaults["stop_pct"]
        max_bars = self._b_maxbars if self._b_maxbars is not None else exit_defaults["max_bars"]
        return float(profit), float(stop), int(max_bars)

    def features_for(self, candles, p_min: float, p_max: float, threshold: float):
        return self._features.compute(candles, p_min=p_min, p_max=p_max, threshold=threshold)

    def allow(self, x_meta) -> tuple[bool, float]:
        """Return (take_trade, p_win). No-op pass-through when disabled/untrained/None."""
        if not self.enabled or not self._model.is_trained or x_meta is None:
            return True, 1.0
        p_win = self._model.predict_proba(x_meta)
        return (p_win >= self.meta_threshold), p_win

    def size_weight(self, p_win: float) -> float | None:
        """Map P(win) to a quantity multiplier for confidence sizing (Phase 2).

        Linearly scales p_win from [meta_threshold, 1.0] onto
        [min_fraction, max_fraction] — a barely-passing firing gets min_fraction,
        a fully-confident one gets max_fraction. Returns None (full size) when
        sizing is disabled, so the binary gate behaviour is unchanged."""
        if not self.sizing_enabled:
            return None
        denom = max(1.0 - self.meta_threshold, 1e-6)
        scaled = (p_win - self.meta_threshold) / denom
        scaled = min(max(scaled, 0.0), 1.0)
        return self._size_min_fraction + (self._size_max_fraction - self._size_min_fraction) * scaled

    def train(self, candles, primary_pipeline, primary_predict, threshold, veto, exit_defaults):
        """Fit the meta-model on the primary's historical firings (past-only buffer)."""
        if not self.enabled:
            return
        candles = list(candles)
        profit_pct, stop_pct, max_bars = self._barriers(exit_defaults)
        start = max(primary_pipeline.min_history, self._features.min_history)

        rows, labels = [], []
        for i in range(start, len(candles)):
            x = primary_pipeline.compute(candles[: i + 1])
            if x is None:
                continue
            p_min, p_max = primary_predict(x)
            if not (p_min >= threshold and p_max < veto):
                continue
            atr = (
                atr_at(candles, i, self._atr_period)
                if (self._atr_mult_pt or self._atr_mult_sl) else None
            )
            label = triple_barrier_label(
                candles, i, profit_pct, stop_pct, max_bars,
                atr=atr, atr_mult_pt=self._atr_mult_pt, atr_mult_sl=self._atr_mult_sl,
            )
            if label is None:  # incomplete barrier window — drop (leakage guard)
                continue
            x_meta = self._features.compute(candles[: i + 1], p_min=p_min, p_max=p_max, threshold=threshold)
            if x_meta is None:
                continue
            rows.append(x_meta)
            labels.append(label)

        n_win = labels.count(1)
        n_loss = labels.count(0)
        if n_win < MIN_SAMPLES_PER_CLASS or n_loss < MIN_SAMPLES_PER_CLASS:
            # Not enough of both classes — leave prior model (or untrained) intact.
            logger.debug(
                "MetaFilter | %s | insufficient samples (win=%d loss=%d) — skip fit",
                self._instrument, n_win, n_loss,
            )
            return

        self._model.fit(rows, labels)
        logger.info(
            "MetaFilter trained | %s | firings=%d (win=%d loss=%d) | thr=%.2f",
            self._instrument, len(labels), n_win, n_loss, self.meta_threshold,
        )
