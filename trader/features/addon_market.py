"""market add-on (EXP-07) — NIFTY / India VIX context relative to the stock.

BACKTEST-ONLY CONTEXT: the backtest engine injects `_nifty_close` / `_vix_close` into every
candle dict (aggregated bars inherit them from their last member). Live candles carry neither,
so live would see the neutral all-zero vector. That is acceptable for an experiment.

Columns: rel_strength, nifty_dd, vix_level, vix_chg. Config: features.market.{enabled,
ret_bars, dd_bars, vix_bars}.
"""

from trader.features.addons import ADDONS, FeatureAddon


class MarketContextAddon(FeatureAddon):
    name = "market"

    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self.ret_bars = int(self.cfg.get("ret_bars", 20))
        self.dd_bars = int(self.cfg.get("dd_bars", 50))
        self.vix_bars = int(self.cfg.get("vix_bars", 20))

    @property
    def feature_names(self) -> list[str]:
        return ["rel_strength", "nifty_dd", "vix_level", "vix_chg"]

    @property
    def min_history(self) -> int:
        return max(self.ret_bars, self.vix_bars) + 1

    @staticmethod
    def _pos(v) -> float | None:
        return float(v) if v is not None and float(v) > 0 else None

    def compute(self, candles: list[dict]) -> list[float]:
        last = candles[-1]
        nifty, vix = self._pos(last.get("_nifty_close")), self._pos(last.get("_vix_close"))
        if nifty is None or vix is None:
            return [0.0, 0.0, 0.0, 0.0]
        close = float(last["close"])
        rel = 0.0
        if len(candles) > self.ret_bars:
            ref = candles[-self.ret_bars - 1]
            n0, c0 = self._pos(ref.get("_nifty_close")), float(ref["close"])
            if n0 is not None and c0 > 0:
                rel = (close / c0 - 1.0) - (nifty / n0 - 1.0)
        navail = [self._pos(c.get("_nifty_close")) for c in candles[-self.dd_bars:]]
        navail = [v for v in navail if v is not None]
        dd = nifty / max(navail) - 1.0 if navail else 0.0
        vchg = 0.0
        if len(candles) > self.vix_bars:
            v0 = self._pos(candles[-self.vix_bars - 1].get("_vix_close"))
            if v0 is not None:
                vchg = vix / v0 - 1.0
        return [float(rel), float(dd), float(vix / 20.0 - 1.0), float(vchg)]


ADDONS["market"] = MarketContextAddon
