import os
from datetime import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / "config" / ".env"
_config_env = os.getenv("TRADER_CONFIG")
CONFIG_FILE = Path(_config_env) if _config_env else ROOT / "config" / "config.yaml"

_REQUIRED_ENV = ["KITE_API_KEY", "KITE_API_SECRET"]


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _set(dst: dict, key: str, src: dict, src_key: str) -> None:
    if src_key in src:
        dst[key] = src[src_key]


def flatten_strategy_params(params: dict) -> dict:
    """Resolve the human-facing nested `entry_gates:` / `exits:` config blocks into
    the flat keys the strategy and its policies read internally. Returns a copy.

    Nested config is the UX; flat keys are the internal wire format. A present
    optional gate/exit block means *enabled* (presence = enabled). Absent blocks
    emit nothing — the consumer applies its own (disabled) default. `features:` /
    `model:` / `forward_label:` blocks are left nested (read directly by their
    owners). Idempotent: flat callers (tests/calibrate) pass through unchanged.

    Centralised here so every config consumer — the strategy AND the live UI
    (trader/ui, which reads config.strategy_config) — sees the same flat keys."""
    p = dict(params)

    exits = p.get("exits")
    if isinstance(exits, dict):
        _set(p, "hold_bars", exits, "hold_bars")
        _set(p, "sell_min_pct", exits, "sell_min_pct")

        hard_stop = exits.get("hard_stop") or {}
        _set(p, "stop_pct", hard_stop, "stop_pct")

        trailing = exits.get("trailing") or {}
        _set(p, "trailing_enabled", trailing, "enabled")
        _set(p, "profit_pct", trailing, "profit_pct")
        _set(p, "trail_pct", trailing, "trail_pct")
        _set(p, "force_trailing_close_time", trailing, "force_close_time")
        _set(p, "pattern_top_floor_enabled", trailing, "pattern_top_floor_enabled")
        # Confidence-sized trailing (Step 1): trail distance scales with P(max) —
        # loose when no top suspected, tight as a top firms up. Presence = enabled.
        if "confidence_sizing" in trailing:
            cs = trailing["confidence_sizing"] or {}
            p["trail_conf_enabled"] = bool(cs.get("enabled", True))
            _set(p, "trail_loose", cs, "trail_loose")
            _set(p, "trail_tight", cs, "trail_tight")
            _set(p, "trail_conf_p_lo", cs, "p_lo")
            _set(p, "trail_conf_p_hi", cs, "p_hi")

        pattern_top = exits.get("pattern_top") or {}
        _set(p, "sell_threshold", pattern_top, "sell_threshold")
        _set(p, "min_hold_before_exit", pattern_top, "min_hold_before_exit")
        _set(p, "pattern_top_direct_exit", pattern_top, "direct_exit")
        # Scale-out (Step 2): on a pattern-top, sell `fraction` and trail the rest.
        # Presence = enabled.
        if "scale_out" in pattern_top:
            so = pattern_top["scale_out"] or {}
            p["pattern_top_scale_out_enabled"] = bool(so.get("enabled", True))
            _set(p, "pattern_top_scale_out_fraction", so, "fraction")
        # Exit-side trend guard (default off): suppress the pattern-top firing while
        # price is in a clean uptrend, so a trending leg isn't misread as a top.
        # Presence does NOT enable — `enabled` must be true.
        if "trend_guard" in pattern_top:
            tg = pattern_top["trend_guard"] or {}
            p["pattern_top_trend_guard_enabled"] = bool(tg.get("enabled", False))
            _set(p, "pattern_top_trend_guard_lookback", tg, "lookback_bars")
            _set(p, "pattern_top_trend_guard_min_slope_pct", tg, "min_slope_pct")

        if "stale" in exits:
            p["stale_exit_enabled"] = True
            st = exits["stale"] or {}
            _set(p, "stale_check_bars", st, "check_bars")
            _set(p, "stale_min_gain_pct", st, "min_gain_pct")
        if "stale_2" in exits:
            p["stale_exit_2_enabled"] = True
            st = exits["stale_2"] or {}
            _set(p, "stale_check_bars_2", st, "check_bars")
            _set(p, "stale_min_gain_pct_2", st, "min_gain_pct")
        if "momentum_decay" in exits:
            p["momentum_exit_enabled"] = True
            md = exits["momentum_decay"] or {}
            _set(p, "momentum_exit_p_min_floor", md, "p_min_floor")
            _set(p, "momentum_exit_min_bars", md, "min_bars")
        if "breakeven" in exits:
            p["breakeven_stop_enabled"] = True
            be = exits["breakeven"] or {}
            _set(p, "breakeven_trigger_pct", be, "trigger_pct")
            _set(p, "breakeven_buffer_pct", be, "buffer_pct")

    gates = p.get("entry_gates")
    if isinstance(gates, dict):
        volume = gates.get("volume") or {}
        _set(p, "entry_min_volume_ratio", volume, "min_ratio")
        norm_price = gates.get("norm_price") or {}
        _set(p, "entry_min_norm_price", norm_price, "min")
        if "prior_decline" in gates:
            p["entry_require_prior_decline"] = True
        if "trend" in gates:
            p["trend_gate_enabled"] = True
            tr = gates["trend"] or {}
            _set(p, "trend_gate_lookback", tr, "lookback")
            _set(p, "trend_gate_min_return", tr, "min_return")
        if "rsi" in gates:
            p["rsi_gate_enabled"] = True
            r = gates["rsi"] or {}
            _set(p, "rsi_period", r, "period")
            _set(p, "rsi_gate_max", r, "max")
        if "stoch_rsi" in gates:
            p["stoch_rsi_gate_enabled"] = True
            s = gates["stoch_rsi"] or {}
            _set(p, "stoch_rsi_period", s, "period")
            _set(p, "stoch_rsi_smooth_k", s, "smooth_k")
            _set(p, "stoch_rsi_gate_max", s, "max")
        if "macd" in gates:
            p["macd_gate_enabled"] = True
            m = gates["macd"] or {}
            _set(p, "macd_fast", m, "fast")
            _set(p, "macd_slow", m, "slow")
            _set(p, "macd_signal_period", m, "signal_period")
            _set(p, "macd_slope_ma_period", m, "slope_ma_period")
            _set(p, "macd_slope_threshold", m, "slope_threshold")
        if "ht_trend" in gates:
            p["ht_trend_gate_enabled"] = True
            ht = gates["ht_trend"] or {}
            _set(p, "ht_trend_rsi_period", ht, "rsi_period")
            _set(p, "ht_trend_rsi_downtrend_max", ht, "rsi_downtrend_max")
            _set(p, "ht_trend_rsi_oversold", ht, "rsi_oversold")
            _set(p, "ht_trend_oversold_lookback", ht, "oversold_lookback")
            ht_macd = ht.get("macd") or {}
            _set(p, "ht_trend_macd_fast", ht_macd, "fast")
            _set(p, "ht_trend_macd_slow", ht_macd, "slow")
            _set(p, "ht_trend_macd_signal_period", ht_macd, "signal_period")
            _set(p, "ht_trend_macd_slope_ma_period", ht_macd, "slope_ma_period")

    return p


def _load() -> "Config":
    load_dotenv(ENV_FILE)
    missing = [k for k in _REQUIRED_ENV if not os.getenv(k)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}. "
            f"Check your .env file."
        )
    with open(CONFIG_FILE) as f:
        data = yaml.safe_load(f)
    return Config(data)


class Config:
    def __init__(self, data: dict):
        self._data = data
        # Preserve the config-file capital before any runtime override (e.g. set_effective_capital).
        # Used as the compounding base so Kite available cash never inflates position sizing.
        self._base_capital: float = float(data["capital"]["total"])

    @property
    def env(self) -> str:
        return self._data["env"]

    @property
    def kite_api_key(self) -> str:
        return os.environ["KITE_API_KEY"]

    @property
    def kite_api_secret(self) -> str:
        return os.environ["KITE_API_SECRET"]

    @property
    def kite_access_token(self) -> str | None:
        return os.getenv("KITE_ACCESS_TOKEN") or None

    @property
    def total_capital(self) -> float:
        return float(self._data["capital"]["total"])

    @property
    def base_capital(self) -> float:
        """Config-file capital, never overridden by runtime adjustments. Used as the
        compounding base so Kite available cash doesn't inflate position sizing."""
        return self._base_capital

    def set_effective_capital(self, amount: float) -> None:
        """Override total_capital at runtime (e.g. capped by Kite available cash).
        All derived properties (daily_loss_limit, max_risk_per_trade, etc.) update automatically."""
        self._data["capital"]["total"] = amount

    @property
    def max_risk_per_trade_pct(self) -> float:
        return float(self._data["capital"]["max_risk_per_trade_pct"])

    @property
    def max_risk_per_trade(self) -> float:
        return self.total_capital * self.max_risk_per_trade_pct / 100

    @property
    def daily_loss_limit(self) -> float:
        pct = float(self._data["capital"]["daily_loss_limit_pct"])
        return self.total_capital * pct / 100

    @property
    def watchlist(self) -> list[str]:
        return self._data.get("watchlist", [])
    

    @property
    def interested(self) -> list[str]:
        return self._data.get("interested", [])

    def strategy_config(self, name: str) -> dict:
        return flatten_strategy_params(self._data["strategies"].get(name, {}))

    def get_strategy_params(self, instrument: str, strategy_name: str) -> dict:
        """Return strategy params for instrument, deep-merging any per_stock_params
        overrides. Merge happens on the raw nested config (so nested per-stock
        overrides combine correctly), then the result is flattened."""
        base = self._data["strategies"].get(strategy_name, {})
        override = (
            (self._data.get("per_stock_params") or {})
            .get(instrument, {})
            .get(strategy_name, {})
        )
        merged = _deep_merge(base, override) if override else base
        return flatten_strategy_params(merged)

    @property
    def max_open_positions(self) -> int:
        return int(self._data["risk"]["max_open_positions"])

    @property
    def gtt_enabled(self) -> bool:
        return bool(self._data["risk"].get("gtt_enabled", True))

    @property
    def order_type(self) -> str:
        """'MARKET' or 'LIMIT' — controls live order placement only."""
        return self._data["risk"].get("order_type", "market").upper()

    @property
    def market_protection_pct(self) -> float:
        """Price buffer % added to MARKET orders to satisfy Zerodha's market-protection requirement.
        BUY:  limit = price_hint × (1 + pct/100)  — ceiling, won't pay more than this.
        SELL: limit = price_hint × (1 - pct/100)  — floor, won't receive less than this.
        Default 1% keeps fills near market while meeting API requirements."""
        return float(self._data["risk"].get("market_protection_pct", 1.0))

    @property
    def default_sl_pct(self) -> float:
        return float(self._data["risk"]["default_sl_pct"])

    @property
    def risk_reward(self) -> float:
        return float(self._data["risk"].get("risk_reward", 2.0))

    @property
    def compounding(self) -> bool:
        """When True, per-stock capital cap scales with base_capital + cumulative_pnl."""
        return bool(self._data["risk"].get("compounding", False))

    @property
    def max_capital_per_stock(self) -> float:
        pct = float(self._data["risk"].get("max_capital_per_stock_pct", 100.0))
        return self.total_capital * pct / 100

    @property
    def product(self) -> str:
        return "CNC"

    @property
    def candle_timeframe(self) -> str:
        return self._data.get("candle_timeframe", "day")

    @property
    def candle_minutes(self) -> int:
        mapping = {"minute": 1, "5minute": 5, "15minute": 15, "30minute": 30, "60minute": 60, "4hour": 240, "day": 390}
        return mapping.get(self.candle_timeframe, 390)

    @property
    def db_path(self) -> Path:
        return ROOT / self._data["data"]["db_path"]

    @property
    def historical_cache_days(self) -> int:
        return int(self._data["data"]["historical_cache_days"])

    @property
    def ui_enabled(self) -> bool:
        return bool(self._data.get("ui", {}).get("enabled", False))

    @property
    def ui_port(self) -> int:
        return int(self._data.get("ui", {}).get("port", 8080))

    @property
    def trading_start(self) -> time:
        val = self._data["risk"].get("trading_start", "09:30")
        h, m = val.split(":")
        return time(int(h), int(m))

    @property
    def trading_end(self) -> time:
        val = self._data["risk"].get("trading_end", "15:30")
        h, m = val.split(":")
        return time(int(h), int(m))

    @property
    def log_level(self) -> str:
        return self._data["logging"]["level"]

    @property
    def log_dir(self) -> Path:
        return ROOT / self._data["logging"]["dir"]


config = _load()
