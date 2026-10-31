"""Regression tests for the 2026-08-28 "feed went dark all session" outage.

Timeline of the bug: the process restarted at 01:33 IST, `start()` connected the
KiteTicker on the PREVIOUS day's access token, that token expired at midnight, and
kiteconnect's ticker looped 403 reconnects until its 50-attempt cap and gave up.
At 09:00 `pre_market()` did `update_access_token()` (rebuilds the ticker) then
`reconnect()` — but `reconnect()` returned immediately because `_suspended` was
False (`disconnect()` had never run in this process's lifetime). The rebuilt
ticker was never connected: zero ticks, 8 open positions unmonitored.

The fix makes `reconnect()` key on whether the socket is ACTUALLY up (plus a
"ticker was rebuilt" flag set by `update_access_token`) rather than on
`_suspended`, while staying a true no-op when the socket is already live.
"""

from unittest.mock import MagicMock, patch

from trader.data.live import LiveFeed


def _make_feed(n_tickers: int = 2):
    """Build a LiveFeed whose KiteTicker constructor yields distinct mocks, so a
    rebuild in update_access_token() is observable as a different object."""
    tickers = [MagicMock(name=f"ticker{i}") for i in range(n_tickers)]
    patcher = patch("trader.data.live.KiteTicker", side_effect=tickers)
    kt = patcher.start()
    feed = LiveFeed("key", "old-token", timeframe_minutes=15)
    return feed, tickers, kt, patcher


def test_overnight_restart_token_swap_connects_new_ticker():
    """start() overnight → token expires, ticker gives up → pre_market swaps the
    token and calls reconnect() ⇒ the NEW ticker gets connected exactly once."""
    feed, tickers, _kt, patcher = _make_feed()
    try:
        old, new = tickers
        feed.start(threaded=True)
        old.connect.assert_called_once_with(threaded=True)
        # Token died in the night; kiteconnect burned its retries and gave up.
        old.is_connected.return_value = False

        feed.update_access_token("key", "fresh-token")
        assert feed._ticker is new
        # rebuild alone must not connect — reconnect() owns that
        new.connect.assert_not_called()

        with patch("twisted.internet.reactor") as reactor:
            reactor.running = False
            feed.reconnect()

        new.connect.assert_called_once_with(threaded=True)
        old.connect.assert_called_once_with(threaded=True)  # no second connect
        assert feed._suspended is False
        assert feed._needs_reconnect is False
    finally:
        patcher.stop()


def test_reconnect_is_noop_when_socket_already_connected():
    """Normal same-day startup: start() connected and the socket is live, so the
    09:00 pre_market reconnect() must not connect a second time."""
    feed, tickers, _kt, patcher = _make_feed(n_tickers=1)
    try:
        (ticker,) = tickers
        feed.start(threaded=True)
        ticker.is_connected.return_value = True

        with patch("twisted.internet.reactor") as reactor:
            reactor.running = True
            feed.reconnect()

        reactor.callFromThread.assert_not_called()
        ticker.connect.assert_called_once_with(threaded=True)  # only start()'s call
    finally:
        patcher.stop()


def test_reconnect_connects_when_socket_is_down_without_token_swap():
    """Feed started, socket silently dead, no token change — reconnect() must
    still heal it (this is the general form of the outage)."""
    feed, tickers, _kt, patcher = _make_feed(n_tickers=1)
    try:
        (ticker,) = tickers
        feed.start(threaded=True)
        ticker.is_connected.return_value = False

        with patch("twisted.internet.reactor") as reactor:
            reactor.running = True
            feed.reconnect()

        reactor.callFromThread.assert_called_once_with(ticker.connect, threaded=True)
    finally:
        patcher.stop()


def test_reconnect_treats_is_connected_exception_as_disconnected():
    feed, tickers, _kt, patcher = _make_feed(n_tickers=1)
    try:
        (ticker,) = tickers
        feed.start(threaded=True)
        ticker.is_connected.side_effect = RuntimeError("ws gone")

        with patch("twisted.internet.reactor") as reactor:
            reactor.running = False
            feed.reconnect()

        assert ticker.connect.call_count == 2  # start() + heal
    finally:
        patcher.stop()


def test_normal_cross_day_disconnect_then_reconnect():
    """Existing behaviour preserved: 15:35 disconnect → next-day 09:00 reconnect
    connects and clears _suspended (even though the mock's is_connected is truthy
    by default, _suspended forces the reconnect)."""
    feed, tickers, _kt, patcher = _make_feed(n_tickers=1)
    try:
        (ticker,) = tickers
        feed.start(threaded=True)
        feed.disconnect()
        assert feed._suspended is True
        ticker.close.assert_called_once()

        with patch("twisted.internet.reactor") as reactor:
            reactor.running = True
            feed.reconnect()

        reactor.callFromThread.assert_called_once_with(ticker.connect, threaded=True)
        assert feed._suspended is False
    finally:
        patcher.stop()


def test_reconnect_before_start_is_noop():
    """main.py calls pre_market() (→ reconnect()) BEFORE feed.start() on startup;
    connecting there would double-connect."""
    feed, tickers, _kt, patcher = _make_feed(n_tickers=1)
    try:
        (ticker,) = tickers
        with patch("twisted.internet.reactor") as reactor:
            reactor.running = False
            feed.reconnect()
        ticker.connect.assert_not_called()
        reactor.callFromThread.assert_not_called()
    finally:
        patcher.stop()


def test_update_access_token_closes_old_socket_and_rebinds_callbacks():
    feed, tickers, _kt, patcher = _make_feed()
    try:
        old, new = tickers
        feed.start(threaded=True)
        old.is_connected.return_value = True

        feed.update_access_token("key", "fresh-token")

        old.close.assert_called_once()
        assert feed._ticker is new
        assert new.on_connect == feed._on_connect
        assert new.on_ticks == feed._on_ticks
        assert new.on_order_update == feed._on_order_update
        assert new.on_close == feed._on_close
        assert new.on_error == feed._on_error
        assert new.on_reconnect == feed._on_reconnect
        assert feed._needs_reconnect is True
    finally:
        patcher.stop()


def test_update_access_token_kills_retry_loop_on_dead_ticker():
    """is_connected() is False while the ticker is still burning 403 retries — the
    teardown must be unconditional, and must stop that loop."""
    feed, tickers, _kt, patcher = _make_feed()
    try:
        old, _new = tickers
        feed.start(threaded=True)
        old.is_connected.return_value = False

        feed.update_access_token("key", "fresh-token")

        old.close.assert_called_once()
        old.stop_retry.assert_called_once()
    finally:
        patcher.stop()


def test_update_access_token_before_start_does_not_arm_reconnect():
    feed, tickers, _kt, patcher = _make_feed()
    try:
        feed.update_access_token("key", "fresh-token")
        assert feed._needs_reconnect is False
        _old, new = tickers
        with patch("twisted.internet.reactor") as reactor:
            reactor.running = False
            feed.reconnect()
        new.connect.assert_not_called()
    finally:
        patcher.stop()
