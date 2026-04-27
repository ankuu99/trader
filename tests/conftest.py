"""
Shared test fixtures and setup.

Must set dummy env vars before any trader module is imported,
since config.py validates KITE_API_KEY / KITE_API_SECRET at import time.
"""
import os
os.environ.setdefault("KITE_API_KEY", "test_key")
os.environ.setdefault("KITE_API_SECRET", "test_secret")

from datetime import datetime

import pytest

from trader.notifications import telegram
telegram.disable()  # suppress all notifications during tests


def candle(close, *, open_=None, high=None, low=None, volume=1000, ts=None):
    """Build a minimal candle dict."""
    return {
        "open":      open_  if open_  is not None else close,
        "high":      high   if high   is not None else close,
        "low":       low    if low    is not None else close,
        "close":     close,
        "volume":    volume,
        "timestamp": ts or datetime(2025, 6, 1, 10, 0),
    }


@pytest.fixture
def make_candle():
    return candle
