from unittest.mock import MagicMock, patch

import pytest

import trader.notifications.telegram as tg


@pytest.fixture(autouse=True)
def set_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")


class TestTelegramSend:
    def test_send_returns_true_on_success(self):
        mock_resp = MagicMock()
        mock_resp.ok = True
        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = tg._send("hello")
        assert result is True
        mock_post.assert_called_once()

    def test_send_returns_false_on_http_error(self):
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request"
        with patch("requests.post", return_value=mock_resp):
            result = tg._send("hello")
        assert result is False

    def test_send_returns_false_on_network_error(self):
        import requests as req
        with patch("requests.post", side_effect=req.RequestException("timeout")):
            result = tg._send("hello")
        assert result is False

    def test_send_skips_when_token_missing(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN")
        with patch("requests.post") as mock_post:
            result = tg._send("hello")
        assert result is False
        mock_post.assert_not_called()

    def test_send_skips_when_chat_id_missing(self, monkeypatch):
        monkeypatch.delenv("TELEGRAM_CHAT_ID")
        with patch("requests.post") as mock_post:
            result = tg._send("hello")
        assert result is False
        mock_post.assert_not_called()


class TestNotificationFunctions:
    def _mock_send(self):
        return patch("trader.notifications.telegram._send", return_value=True)

    def test_notify_order_filled_calls_send(self):
        with self._mock_send() as m:
            tg.notify_order_filled("NSE:RELIANCE", "BUY", 12, 2500.0, "RSI(14)", "paper")
        m.assert_called_once()
        text = m.call_args[0][0]
        assert "RELIANCE" in text
        assert "BUY" in text
        assert "2,500.00" in text
        assert "[PAPER]" in text

    def test_notify_order_rejected_calls_send(self):
        with self._mock_send() as m:
            tg.notify_order_rejected("NSE:INFY", "BUY", "max positions reached", "paper")
        m.assert_called_once()
        assert "max positions reached" in m.call_args[0][0]

    def test_notify_daily_pnl_positive(self):
        with self._mock_send() as m:
            tg.notify_daily_pnl(500.0, 200.0, 3, "paper")
        text = m.call_args[0][0]
        assert "📈" in text
        assert "700.00" in text  # net = 500 + 200

    def test_notify_daily_pnl_negative(self):
        with self._mock_send() as m:
            tg.notify_daily_pnl(-400.0, -100.0, 2, "paper")
        text = m.call_args[0][0]
        assert "📉" in text

    def test_notify_halt_calls_send(self):
        with self._mock_send() as m:
            tg.notify_halt(-650.0, 600.0, "paper")
        text = m.call_args[0][0]
        assert "Halted" in text
        assert "650.00" in text

    def test_notify_error_calls_send(self):
        with self._mock_send() as m:
            tg.notify_error("data/live.py", "KiteTicker disconnected")
        text = m.call_args[0][0]
        assert "KiteTicker disconnected" in text

    def test_notify_startup_calls_send(self):
        with self._mock_send() as m:
            tg.notify_startup("paper", ["NSE:RELIANCE", "NSE:INFY"], 4)
        text = m.call_args[0][0]
        assert "RELIANCE" in text
        assert "[PAPER]" in text
        assert "4" in text

    def test_live_tag_shown_correctly(self):
        with self._mock_send() as m:
            tg.notify_order_filled("NSE:RELIANCE", "BUY", 12, 2500.0, "ORB(15m)", "live")
        assert "[LIVE]" in m.call_args[0][0]
