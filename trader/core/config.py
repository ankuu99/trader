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
    def product(self) -> str:
        """Kite product type: MIS (intraday) or CNC (delivery/interday)."""
        return self._data.get("product", "MIS")

    @property
    def square_off_enabled(self) -> bool:
        """Whether the system should force-close positions at square_off_time."""
        return bool(self._data["risk"].get("square_off", True))

    @property
    def candle_minutes(self) -> int:
        """LiveFeed candle bucket size in minutes."""
        return int(self._data.get("candle_minutes", 5))

    @property
    def square_off_time(self) -> str:
        return self._data["risk"].get("square_off_time", "15:15")

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
