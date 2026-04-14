import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Paths
ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / "config" / ".env"
# Allow TRADER_CONFIG env var to select a different config file (e.g. interday)
_config_env = os.getenv("TRADER_CONFIG")
CONFIG_FILE = Path(_config_env) if _config_env else ROOT / "config" / "config.yaml"

# Required environment variables — startup fails if any are missing
_REQUIRED_ENV = ["KITE_API_KEY", "KITE_API_SECRET"]


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

    # ------------------------------------------------------------------ #
    # Top-level                                                            #
    # ------------------------------------------------------------------ #

    @property
    def env(self) -> str:
        """Operating mode: development | paper | live"""
        return self._data["env"]

    # ------------------------------------------------------------------ #
    # Credentials (from environment, never from config.yaml)              #
    # ------------------------------------------------------------------ #

    @property
    def kite_api_key(self) -> str:
        return os.environ["KITE_API_KEY"]

    @property
    def kite_api_secret(self) -> str:
        return os.environ["KITE_API_SECRET"]

    @property
    def kite_access_token(self) -> str | None:
        return os.getenv("KITE_ACCESS_TOKEN") or None

    # ------------------------------------------------------------------ #
    # Capital & risk                                                       #
    # ------------------------------------------------------------------ #

    @property
    def capital(self) -> dict:
        return self._data["capital"]

    @property
    def total_capital(self) -> float:
        return float(self.capital["total"])

    @property
    def max_risk_per_trade_pct(self) -> float:
        return float(self.capital["max_risk_per_trade_pct"])

    @property
    def max_risk_per_trade(self) -> float:
        return self.total_capital * self.max_risk_per_trade_pct / 100

    @property
    def daily_loss_limit(self) -> float:
        pct = float(self.capital["daily_loss_limit_pct"])
        return self.total_capital * pct / 100

    # ------------------------------------------------------------------ #
    # Watchlist                                                            #
    # ------------------------------------------------------------------ #

    @property
    def watchlist(self) -> list[str]:
        return self._data.get("watchlist", [])

    # ------------------------------------------------------------------ #
    # Strategies                                                           #
    # ------------------------------------------------------------------ #

    @property
    def strategy(self, name: str) -> dict:
        return self._data["strategies"].get(name, {})

    def strategy_config(self, name: str) -> dict:
        return self._data["strategies"].get(name, {})

    # ------------------------------------------------------------------ #
    # Risk                                                                 #
    # ------------------------------------------------------------------ #

    @property
    def max_open_positions(self) -> int:
        return int(self._data["risk"]["max_open_positions"])

    @property
    def weekly_loss_limit(self) -> float:
        """Weekly loss limit in rupees. 0 means disabled."""
        pct = float(self._data["risk"].get("weekly_loss_limit_pct", 0))
        return self.total_capital * pct / 100

    @property
    def regime_filter_enabled(self) -> bool:
        return bool(self._data["risk"].get("regime_filter", {}).get("enabled", False))

    @property
    def regime_index_symbol(self) -> str:
        return self._data["risk"].get("regime_filter", {}).get("index_symbol", "NSE:NIFTY 50")

    @property
    def regime_dma_period(self) -> int:
        return int(self._data["risk"].get("regime_filter", {}).get("dma_period", 200))

    @property
    def regime_max_drawdown_pct(self) -> float:
        return float(self._data["risk"].get("regime_filter", {}).get("max_drawdown_pct", 15.0))

    @property
    def atr_sizing_enabled(self) -> bool:
        return bool(self._data["risk"].get("position_sizing", {}).get("atr_based", False))

    @property
    def atr_sizing_multiplier(self) -> float:
        return float(self._data["risk"].get("position_sizing", {}).get("atr_multiplier", 2.0))

    @property
    def max_position_pct(self) -> float:
        """Cap a single position at this % of total capital. 0 means no cap."""
        return float(self._data["risk"].get("position_sizing", {}).get("max_position_pct", 8.0))

    @property
    def default_sl_pct(self) -> float:
        """Fallback SL distance as % of price when no ATR is available. Default 2%."""
        return float(self._data["risk"].get("default_sl_pct", 2.0))

    @property
    def trailing_stop_enabled(self) -> bool:
        return bool(self._data["risk"].get("trailing_stop", {}).get("enabled", False))

    @property
    def chandelier_period(self) -> int:
        return int(self._data["risk"].get("trailing_stop", {}).get("period", 22))

    @property
    def chandelier_multiplier(self) -> float:
        return float(self._data["risk"].get("trailing_stop", {}).get("multiplier", 3.0))

    @property
    def product(self) -> str:
        """Kite product type — always CNC (delivery). No intraday MIS trading."""
        return "CNC"

    @property
    def candle_timeframe(self) -> str:
        """Candle period for signal generation: 5minute, 15minute, 30minute, 60minute, day."""
        return self._data.get("candle_timeframe", "day")

    @property
    def candle_minutes(self) -> int:
        """LiveFeed candle bucket size in minutes, derived from candle_timeframe."""
        mapping = {"5minute": 5, "15minute": 15, "30minute": 30, "60minute": 60, "day": 390}
        return mapping.get(self.candle_timeframe, 390)

    # ------------------------------------------------------------------ #
    # Data                                                                 #
    # ------------------------------------------------------------------ #

    @property
    def db_path(self) -> Path:
        return ROOT / self._data["data"]["db_path"]

    @property
    def historical_cache_days(self) -> int:
        return int(self._data["data"]["historical_cache_days"])

    # ------------------------------------------------------------------ #
    # Logging                                                              #
    # ------------------------------------------------------------------ #

    @property
    def log_level(self) -> str:
        return self._data["logging"]["level"]

    @property
    def log_dir(self) -> Path:
        return ROOT / self._data["logging"]["dir"]


# Module-level singleton — import and use directly:
#   from trader.core.config import config
config = _load()
