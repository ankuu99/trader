"""sr add-on (EXP-08) — distance/strength of the nearest support and resistance level.

Levels = clusters of confirmed pivot closes (minima U maxima) in the last `lookback` closes,
EXCLUDING the current bar (no look-ahead). Columns: sup_dist, sup_touches, res_dist, res_touches.
Config: features.sr.{enabled, lookback, pivot_order, tol_pct, min_touches, cap}.
"""

from trader.features import indicators
from trader.features.addons import ADDONS, FeatureAddon


class SupportResistanceAddon(FeatureAddon):
    name = "sr"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.lookback = int(self.cfg.get("lookback", 300))
        self.pivot_order = int(self.cfg.get("pivot_order", 3))
        self.tol_pct = float(self.cfg.get("tol_pct", 1.5))
        self.min_touches = int(self.cfg.get("min_touches", 2))
        self.cap = float(self.cfg.get("cap", 0.25))

    @property
    def feature_names(self) -> list[str]:
        return ["sup_dist", "sup_touches", "res_dist", "res_touches"]

    @property
    def min_history(self) -> int:
        return self.lookback + 1

    def _levels(self, window: list[float]) -> list[tuple[float, int]]:
        mins, maxs = indicators.find_local_extrema(window, self.pivot_order)
        prices = sorted(window[i] for i in set(mins) | set(maxs))
        clusters: list[list[float]] = []
        for p in prices:
            if clusters and p <= (sum(clusters[-1]) / len(clusters[-1])) * (1 + self.tol_pct / 100.0):
                clusters[-1].append(p)
            else:
                clusters.append([p])
        return [(sum(cl) / len(cl), len(cl)) for cl in clusters if len(cl) >= self.min_touches]

    def compute(self, candles: list[dict]) -> list[float]:
        closes = [float(c["close"]) for c in candles]
        close = closes[-1]
        window = closes[-self.lookback - 1:-1]
        levels = self._levels(window)
        sup = [lv for lv in levels if lv[0] <= close]
        res = [lv for lv in levels if lv[0] > close]
        sup_lv = max(sup, key=lambda lv: lv[0]) if sup else None
        res_lv = min(res, key=lambda lv: lv[0]) if res else None
        if sup_lv and close:
            sd = min(max((close - sup_lv[0]) / close, 0.0), self.cap)
            st = float(sup_lv[1])
        else:
            sd, st = self.cap, 0.0
        if res_lv and close:
            rd = min(max((res_lv[0] - close) / close, 0.0), self.cap)
            rt = float(res_lv[1])
        else:
            rd, rt = self.cap, 0.0
        return [float(sd), st, float(rd), rt]


ADDONS["sr"] = SupportResistanceAddon
