import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / "config" / ".env"
_config_env = os.getenv("TRADER_CONFIG")
CONFIG_FILE = Path(_config_env) if _config_env else ROOT / "config" / "config.yaml"

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
        return self._data["strategies"].get(name, {})

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
    def log_level(self) -> str:
        return self._data["logging"]["level"]

    @property
    def log_dir(self) -> Path:
        return ROOT / self._data["logging"]["dir"]


config = _load()
