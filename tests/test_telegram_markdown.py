"""
Telegram Markdown safety — every "Trailing Stop Activated" alert failed live
(Aug 31 → Oct 13, 20 × HTTP 400 "can't parse entities") because the trigger type
PATTERN_TOP / PROFIT_PCT carried a bare "_", which Markdown reads as an unclosed
italic. The type now goes in a code span, and _send falls back to plain text on
any parse-entities 400 so a formatting slip never drops an alert.
"""
from types import SimpleNamespace

from trader.notifications import telegram


def _resp(status, text=""):
    return SimpleNamespace(status_code=status, ok=200 <= status < 300, text=text)


def _arm(monkeypatch, responses):
    calls = []

    def fake_post(url, json, timeout):
        calls.append(json)
        return responses.pop(0)

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    monkeypatch.setattr(telegram, "_enabled", True)
    monkeypatch.setattr(telegram.requests, "post", fake_post)
    return calls


def test_trailing_alert_puts_trigger_type_in_code_span(monkeypatch):
    calls = _arm(monkeypatch, [_resp(200)])
    telegram.notify_trailing_activated("NSE:X", 100.0, 107.0, 7.0, 2.0, "PATTERN_TOP", "live")
    text = calls[0]["text"]
    assert "`PATTERN_TOP`" in text
    # No bare underscore outside code spans → Markdown v1 has nothing to italicise.
    outside = text.split("`")[0::2]
    assert not any("_" in seg for seg in outside)


def test_parse_entities_400_resends_as_plain_text(monkeypatch):
    calls = _arm(monkeypatch, [
        _resp(400, '{"ok":false,"description":"Bad Request: can\'t parse entities: ..."}'),
        _resp(200),
    ])
    assert telegram._send("Reason : BAD_REASON") is True
    assert calls[0]["parse_mode"] == "Markdown"
    assert "parse_mode" not in calls[1] and calls[1]["text"] == "Reason : BAD_REASON"


def test_other_failures_do_not_retry(monkeypatch):
    calls = _arm(monkeypatch, [_resp(401, "Unauthorized")])
    assert telegram._send("hi") is False
    assert len(calls) == 1
