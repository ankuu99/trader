"""Regression test for the cross-day reconnect bug (2026-07-14/15 outage).

KiteTicker.connect() issues connectWS() from the calling thread and only spawns
the reactor thread when the reactor isn't running. On the first cross-day
reconnect of a long-lived process the reactor is already running, so the
connect must be handed to the reactor thread via callFromThread — otherwise the
connection attempt is silently dropped and the feed never comes back.
"""

from unittest.mock import MagicMock, patch

from trader.data.live import LiveFeed


def _make_feed():
    with patch("trader.data.live.KiteTicker") as kt:
        feed = LiveFeed("key", "token", timeframe_minutes=15)
    return feed, kt.return_value


def test_reconnect_uses_call_from_thread_when_reactor_running():
    feed, ticker = _make_feed()
    feed._suspended = True
    with patch("twisted.internet.reactor") as reactor:
        reactor.running = True
        feed.reconnect()
    reactor.callFromThread.assert_called_once_with(ticker.connect, threaded=True)
    ticker.connect.assert_not_called()
    assert feed._suspended is False


def test_reconnect_connects_directly_when_reactor_not_running():
    feed, ticker = _make_feed()
    feed._suspended = True
    with patch("twisted.internet.reactor") as reactor:
        reactor.running = False
        feed.reconnect()
    reactor.callFromThread.assert_not_called()
    ticker.connect.assert_called_once_with(threaded=True)


def test_reconnect_noop_when_not_suspended():
    feed, ticker = _make_feed()
    with patch("twisted.internet.reactor") as reactor:
        reactor.running = True
        feed.reconnect()
    reactor.callFromThread.assert_not_called()
    ticker.connect.assert_not_called()
