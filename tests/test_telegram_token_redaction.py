"""Full System Verification Audit (2026-09-13): requests/urllib3 connection
exceptions frequently embed the full request URL in their own string
representation -- and _raw_send's URL contains the raw bot token
(f"https://api.telegram.org/bot{token}/sendMessage"). This module's own
docstring has always claimed the token is "NEVER... written to the log";
these tests prove that claim actually holds for the one branch that could
have violated it (a connection-level failure, not a clean API response).
"""
from unittest.mock import patch

import pytest
import requests

from datetime import datetime, timezone

from data_engine import config as base_config, storage
from paper_trading import telegram_bot


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _configure(token="123456789:AAFakeTokenForTestingOnly12345"):
    telegram_bot.save_settings(bot_token=token, channel_id="999")
    return token


def test_raw_send_never_leaks_token_on_connection_exception():
    token = _configure()
    fake_exc = requests.exceptions.ConnectionError(
        f"HTTPSConnectionPool(host='api.telegram.org', port=443): "
        f"Max retries exceeded with url: /bot{token}/sendMessage "
        f"(Caused by NewConnectionError('...'))"
    )
    with patch("paper_trading.telegram_bot.requests.post", side_effect=fake_exc), \
         patch("paper_trading.telegram_bot.time.sleep"):
        ok, err = telegram_bot._raw_send("test message")

    assert ok is False
    assert token not in err
    assert "[REDACTED]" in err


def test_send_private_document_never_leaks_token_on_connection_exception(tmp_path):
    token = _configure()
    telegram_bot.save_settings(personal_chat_id="111")
    pdf_path = tmp_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    fake_exc = requests.exceptions.ConnectionError(
        f"Max retries exceeded with url: /bot{token}/sendDocument"
    )
    with patch("paper_trading.telegram_bot.requests.post", side_effect=fake_exc), \
         patch("paper_trading.telegram_bot.time.sleep"):
        result = telegram_bot.send_private_document(str(pdf_path))

    assert result["ok"] is False
    assert token not in result["error"]
    assert "[REDACTED]" in result["error"]


def test_raw_send_still_reports_clean_api_error_descriptions_unredacted():
    """A real Telegram API response (not a connection exception) never
    contains the token in the first place -- confirms the redaction logic
    doesn't over-match and corrupt a normal, safe error description."""
    _configure()

    class FakeResp:
        status_code = 400
        def json(self):
            return {"ok": False, "description": "Bad Request: chat not found"}

    with patch("paper_trading.telegram_bot.requests.post", return_value=FakeResp()):
        ok, err = telegram_bot._raw_send("test message")

    assert ok is False
    assert err == "Bad Request: chat not found"


def test_telegram_log_endpoint_redacts_any_pre_existing_leaked_token_on_read(test_db):
    """Defense-in-depth: even if a row written BEFORE this fix already has
    a token-embedding string in its error column, the real dashboard-
    facing endpoint (GET /api/paper-trading/telegram/log) must never
    display it."""
    from sindhu_web.api.paper_trading import get_telegram_log

    leaked_token = "987654321:BBLeakedTokenFromBeforeTheFix999"
    storage.log_telegram_message(
        "pos1", "strat1", "Test Strategy", "automatic", "msg", False,
        f"failed after 3 attempts: ConnectionError('.../bot{leaked_token}/sendMessage')",
        datetime.now(timezone.utc).isoformat(),
    )

    result = get_telegram_log(limit=10)

    assert leaked_token not in str(result)
    assert "[REDACTED]" in result["messages"][0]["error"]
