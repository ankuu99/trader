"""
Weekly-restart enablers: config .env hot-reload + LiveFeed ticker rebuild.

The daily prod restart existed only to adopt the 08:15 IST TOTP token refresh.
These cover the two pieces that let the bot adopt a new token in-process:
Config.reload_env() re-sources config/.env, and LiveFeed.update_access_token()
rebuilds the KiteTicker (the ws URL embeds the token at construction) while
preserving subscriptions, handlers and candle state.
"""

import os

import trader.core.config as config_mod
from trader.core.config import config
from trader.data.live import LiveFeed


def test_reload_env_picks_up_new_token(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("KITE_ACCESS_TOKEN=fresh-token-123\n")
    monkeypatch.setattr(config_mod, "ENV_FILE", env_file)
    monkeypatch.setenv("KITE_ACCESS_TOKEN", "stale-token")

    assert config.kite_access_token == "stale-token"
    returned = config.reload_env()

    assert returned == "fresh-token-123"
    assert os.environ["KITE_ACCESS_TOKEN"] == "fresh-token-123"


def test_reload_env_unchanged_token_is_noop(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("KITE_ACCESS_TOKEN=same-token\n")
    monkeypatch.setattr(config_mod, "ENV_FILE", env_file)
    monkeypatch.setenv("KITE_ACCESS_TOKEN", "same-token")

    assert config.reload_env() == "same-token"


def test_update_access_token_rebuilds_ticker_and_preserves_state():
    feed = LiveFeed(api_key="key", access_token="old-token", timeframe_minutes=15)
    feed.subscribe([111, 222])
    tick_handler = lambda t: None
    candle_handler = lambda c: None
    feed.register_tick_handler(tick_handler)
    feed.register_candle_handler(candle_handler)
    feed._partials[111] = {"candle_start": None, "open": 1, "high": 1,
                           "low": 1, "close": 1, "volume": 0}
    old_ticker = feed._ticker

    feed.update_access_token("key", "new-token")

    assert feed._ticker is not old_ticker
    # all callbacks re-bound onto the new ticker
    assert feed._ticker.on_connect == feed._on_connect
    assert feed._ticker.on_ticks == feed._on_ticks
    assert feed._ticker.on_order_update == feed._on_order_update
    assert feed._ticker.on_close == feed._on_close
    assert feed._ticker.on_error == feed._on_error
    assert feed._ticker.on_reconnect == feed._on_reconnect
    # subscriptions, handlers and candle state carry over
    assert feed._tokens == [111, 222]
    assert tick_handler in feed._tick_handlers
    assert candle_handler in feed._candle_handlers
    assert 111 in feed._partials


def test_update_access_token_safe_when_disconnected():
    feed = LiveFeed(api_key="key", access_token="old-token")
    # never connected — is_connected() must not blow up the swap
    feed.update_access_token("key", "new-token")
    assert feed._ticker is not None
