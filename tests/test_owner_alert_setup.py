import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from paper_trading import monitoring, telegram_bot


@pytest.mark.parametrize("value,ok", [("", True), ("123456789", True), ("-1001234567890", True), (" 98765 ", True),
                                      ("1234", False), ("12345678901234567", False), ("@myname", False),
                                      ("123456:ABC-DEF1234ghIkl", False), ("abc", False), ("12 34 56", False)])
def test_chat_id_format(value, ok):
    assert telegram_bot.validate_chat_id(value)[0] is ok


def _client(monkeypatch, chat_id="123456789"):
    from sindhu_web.api import ops_checks
    app = FastAPI(); app.include_router(ops_checks.router)
    monkeypatch.setattr(telegram_bot, "load_settings", lambda: {"personal_chat_id": chat_id})
    monkeypatch.setattr(monitoring, "_limiter", monitoring.Limiter())
    return TestClient(app)


def test_test_alert_needs_a_saved_chat_id(monkeypatch):
    r = _client(monkeypatch, "").post("/api/ops/test-owner-alert")
    assert r.status_code == 400 and "chat id" in r.json()["error"]


def test_test_alert_sends_once_to_the_private_chat_and_is_rate_limited(monkeypatch):
    c = _client(monkeypatch)
    sent = []
    monkeypatch.setattr(telegram_bot, "send_private_message", lambda t: sent.append(t) or {"ok": True, "error": None})
    assert c.post("/api/ops/test-owner-alert").json() == {"ok": True}
    r = c.post("/api/ops/test-owner-alert")
    assert r.status_code == 429 and len(sent) == 1 and sent[0].startswith("[SINDHU test alert]")


def test_failed_test_alert_does_not_start_the_cooldown(monkeypatch):
    c = _client(monkeypatch)
    monkeypatch.setattr(telegram_bot, "send_private_message", lambda t: {"ok": False, "error": "chat not found"})
    r = c.post("/api/ops/test-owner-alert")
    assert r.status_code == 502 and "chat not found" in r.json()["error"]
    monkeypatch.setattr(telegram_bot, "send_private_message", lambda t: {"ok": True, "error": None})
    assert c.post("/api/ops/test-owner-alert").status_code == 200


def test_the_system_never_calls_the_test_alert_by_itself():
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    users = [p for p in list(root.glob("paper_trading/*.py")) + list(root.glob("cloud_runtime/*.py")) if "test_owner_alert" in p.read_text(encoding="utf-8", errors="ignore")]
    assert users == []


def test_settings_endpoint_rejects_a_bot_token_as_chat_id(test_db):
    from sindhu_web.api import paper_trading as api
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        api.update_telegram_settings(api.TelegramSettingsUpdate(personal_chat_id="123456:ABCdef"))
    assert e.value.status_code == 422
