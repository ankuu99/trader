"""atr_dist add-on (EXP-06) — distance from the EMA in ATR units, and ATR as a fraction of price.

Columns: ema_dist_atr (clipped [-10, 10]), atr_ratio. Config: features.atr_dist.{enabled,
ema_period, atr_period}.
"""

from trader.features import indicators
from trader.features.addons import ADDONS, FeatureAddon


class AtrDistAddon(FeatureAddon):
    name = "atr_dist"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.ema_period = int(self.cfg.get("ema_period", 20))
        self.atr_period = int(self.cfg.get("atr_period", 14))

    @property
    def feature_names(self) -> list[str]:
        return ["ema_dist_atr", "atr_ratio"]

    @property
    def min_history(self) -> int:
        return max(5 * self.ema_period, self.atr_period + 1)

    def compute(self, candles: list[dict]) -> list[float]:
        closes = [float(c["close"]) for c in candles]
        close = closes[-1]
        ema_s = indicators.ema_series(closes[-5 * self.ema_period:], self.ema_period)
        atr = indicators.atr_at(candles, len(candles) - 1, self.atr_period)
        if not ema_s or atr <= 0:
            dist = 0.0
        else:
            dist = max(-10.0, min(10.0, (close - ema_s[-1]) / atr))
        ratio = atr / close if close else 0.0
        return [float(dist), float(ratio)]


ADDONS["atr_dist"] = AtrDistAddon
