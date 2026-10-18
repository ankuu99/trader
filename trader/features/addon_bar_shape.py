"""bar_shape add-on (EXP-05) — the reversal-bar shape the base vector misses.

Columns: lower_wick, upper_wick, body (all / range), clv_x_vol (close-location-value x capped
volume ratio), close_vs_prev_low. Config: features.bar_shape.{enabled, vol_bars}.
"""

from trader.features.addons import ADDONS, FeatureAddon


class BarShapeAddon(FeatureAddon):
    name = "bar_shape"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.vol_bars = int(self.cfg.get("vol_bars", 20))

    @property
    def feature_names(self) -> list[str]:
        return ["lower_wick", "upper_wick", "body", "clv_x_vol", "close_vs_prev_low"]

    @property
    def min_history(self) -> int:
        return self.vol_bars

    def compute(self, candles: list[dict]) -> list[float]:
        c = candles[-1]
        o, h, l, cl = float(c["open"]), float(c["high"]), float(c["low"]), float(c["close"])
        rng = h - l
        if rng > 0:
            lower = (min(o, cl) - l) / rng
            upper = (h - max(o, cl)) / rng
            body = (cl - o) / rng
            clv = ((cl - l) - (h - cl)) / rng
        else:
            lower = upper = body = clv = 0.0
        vols = [float(x.get("volume", 0) or 0) for x in candles[-self.vol_bars:]]
        mean_v = sum(vols) / len(vols) if vols else 0.0
        vr = float(c.get("volume", 0) or 0) / mean_v if mean_v > 0 else 1.0
        clv_x_vol = clv * min(vr, 5.0)
        if len(candles) >= 2 and float(candles[-2]["low"]) != 0:
            pl = float(candles[-2]["low"])
            cvpl = (cl - pl) / pl
        else:
            cvpl = 0.0
        return [float(lower), float(upper), float(body), float(clv_x_vol), float(cvpl)]


ADDONS["bar_shape"] = BarShapeAddon
