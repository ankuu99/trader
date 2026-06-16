"""
WindowFeaturePipeline — raw multi-channel price-window features (Plan 5).

Unlike ExtremaFeaturePipeline (which compresses the trailing window into 6 hand-
engineered scalars), this pipeline emits the *raw normalized window* itself so a
nonlinear model (MLPModel) can learn the candle-by-candle morphology of a bottom
— the "shape over N candles" that scalar slopes/curvature erase.

Output is a single flat vector of length `window * len(channels)`, laid out
channel-major: [close_0..close_{w-1}, volume_0.., norm_price_0..]. Keeping it a 1-D
vector preserves the FeaturePipeline contract, so the strategy training loop and
the ExtremaModel interface need no changes — the model reshapes internally if it
wants to.

Per-channel normalization (within each window, so it's scale-invariant across
stocks and price levels):
  - close      : z-score of the window closes        (captures path shape)
  - volume     : z-score of the window volumes       (captures volume morphology)
  - norm_price : per-bar (close-low)/(high-low)      (already in [0,1])

Config (nested `features:` block, selected via `features.type: window`):
    window   : number of trailing candles in the window   (default 24)
    channels : list of channel names to include
               (default ["close", "volume", "norm_price"])

NOTE: positional entry gates (ExtremaEntryPolicy, which reads x[0]/x[1]/x[5]) are
incompatible with this layout. They must stay disabled (entry_gates: {}) when using
the window pipeline — the gate semantics assume the extrema scalar vector.
"""

import numpy as np

from trader.features.base import FeaturePipeline

_VALID_CHANNELS = ("close", "volume", "norm_price")


def _zscore(values: list[float]) -> list[float]:
    n = len(values)
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n
    std = var ** 0.5
    if std == 0.0:
        return [0.0] * n
    return [(v - mean) / std for v in values]


class WindowFeaturePipeline(FeaturePipeline):
    def __init__(self, cfg: dict | None = None):
        cfg = cfg or {}
        self._window: int = int(cfg.get("window", 24))
        channels = cfg.get("channels") or list(_VALID_CHANNELS)
        bad = [c for c in channels if c not in _VALID_CHANNELS]
        if bad:
            raise ValueError(f"Unknown window channels {bad}. Valid: {list(_VALID_CHANNELS)}")
        self._channels: list[str] = list(channels)

    @property
    def min_history(self) -> int:
        return self._window

    @property
    def feature_names(self) -> list[str]:
        return [f"{ch}{i}" for ch in self._channels for i in range(self._window)]

    def compute(self, candles: list[dict]) -> "np.ndarray | None":
        w = self._window
        if len(candles) < w:
            return None
        # candles may be a deque (live/on_candle) which doesn't support slicing.
        win = list(candles)[-w:]
        closes = [c["close"] for c in win]
        volumes = [float(c.get("volume", 0)) for c in win]

        out: list[float] = []
        for ch in self._channels:
            if ch == "close":
                out.extend(_zscore(closes))
            elif ch == "volume":
                out.extend(_zscore(volumes))
            elif ch == "norm_price":
                out.extend(
                    (c["close"] - c["low"]) / (c["high"] - c["low"])
                    if c["high"] != c["low"] else 0.5
                    for c in win
                )
        return np.array(out, dtype=float)
