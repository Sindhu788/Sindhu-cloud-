"""Signal-start readiness: with the Cloud settings (owner=cloud, dry-run off, safe-start unset) a Losing-group
signal is withheld with a logged reason while a Profitable/Challenge signal passes; SAFE_START=1 sends nothing.
No real Telegram call is ever made (requests.post is mocked and asserted)."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from data_engine import config as base_config, storage
from paper_trading import strategy_groups, telegram_bot


@pytest.fixture(autouse=True)
def cloud_like_env(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("SINDHU_CLOUD_MODE", "1")
    monkeypatch.setenv("SINDHU_PUBLIC_SIGNAL_OWNER", "cloud")
    monkeypatch.setenv("SINDHU_TELEGRAM_DRY_RUN", "0")
    monkeypatch.delenv("SINDHU_SAFE_START", raising=False)
    monkeypatch.setattr(telegram_bot, "_fetch_live_price", lambda *a, **k: None)
    telegram_bot.save_settings(bot_token="123456:TESTTOKEN", channel_id="-100123", master_send_enabled=True,
                               auto_send_enabled=True, channel_group_filter="profitable_challenge")
    yield


def _position(strategy_id):
    pid = f"pos-{strategy_id}"
    now = int(datetime.now(timezone.utc).timestamp() * 1000)
    storage.open_paper_position({
        "id": pid, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long", "entry_price": 100.0,
        "size": 1.0, "risk_amount": 5.0, "entry_time": now, "stop_loss": 95.0, "take_profit": 110.0,
        "strategy_id": strategy_id, "strategy_name": strategy_id, "confidence": 80.0, "status": "open",
    }) if hasattr(storage, "open_paper_position") else None
    return {"id": pid, "strategy_id": strategy_id, "symbol": "BTCUSDT", "direction": "long", "entry_price": 100.0,
            "entry_time": now}


@pytest.mark.parametrize("group,expected_ok", [("losing", False), ("profitable", True), ("challenge", True)])
def test_combined_group_filter_withholds_losing_and_passes_profitable_and_challenge(test_db, group, expected_ok):
    sid = f"s-{group}"
    strategy_groups.assign_group(sid, group, auto=False) if hasattr(strategy_groups, "assign_group") else None
    with patch.object(strategy_groups, "get_group", return_value=group):
        ok, reason = telegram_bot.group_filter_check({"strategy_id": sid})
    assert ok is expected_ok
    if not expected_ok:
        assert "profitable_challenge" in reason and "losing" in reason


def test_cloud_settings_public_delivery_is_allowed_and_safe_start_blocks_everything(test_db, monkeypatch):
    from paper_trading import signal_ownership
    settings = telegram_bot.load_settings()
    assert signal_ownership.delivery_blockers(settings) == []
    monkeypatch.setenv("SINDHU_SAFE_START", "1")
    assert any("SAFE_START" in b for b in signal_ownership.delivery_blockers(settings))


def test_dry_run_and_non_cloud_owner_never_reach_the_network(test_db, monkeypatch):
    posted = MagicMock()
    with patch("requests.post", posted), patch("requests.Session.post", posted):
        monkeypatch.setenv("SINDHU_TELEGRAM_DRY_RUN", "1")
        ok, _ = telegram_bot._raw_send("hello")
        assert ok is False
        monkeypatch.setenv("SINDHU_TELEGRAM_DRY_RUN", "0")
        monkeypatch.setenv("SINDHU_PUBLIC_SIGNAL_OWNER", "disabled")
        ok, msg = telegram_bot._raw_send("hello")
        assert ok is False and "Public delivery blocked" in msg
    assert posted.call_count == 0
