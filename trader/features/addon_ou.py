"""`ou` feature add-on (EXP-10): Ornstein-Uhlenbeck s-score and normalised half-life."""

import math

from trader.features.addons import ADDONS, FeatureAddon
from trader.features.ou import ou_score


class OUAddon(FeatureAddon):
    name = "ou"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self._window = int(self.cfg.get("window", 60))

    @property
    def feature_names(self) -> list[str]:
        return ["ou_s", "ou_hl_norm"]

    @property
    def min_history(self) -> int:
        return self._window + 1

    def compute(self, candles: list[dict]) -> list[float]:
        closes = [float(c["close"]) for c in candles]
        s, hl = ou_score(closes, self._window)
        hl_norm = 2.0 if not math.isfinite(hl) else min(hl / self._window, 2.0)
        return [float(s), float(hl_norm)]


ADDONS["ou"] = OUAddon
