"""Master Task Expansion, Part 2: Cloud-Aware Local Auto-Stop.
See paper_trading/cloud_aware_auto_stop.py's module docstring for the full
design and safety contract.
"""
from unittest.mock import MagicMock, patch

import pytest

from data_engine import config as base_config
from paper_trading import cloud_aware_auto_stop as auto_stop


@pytest.fixture(autouse=True)
def isolated_local_config(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(config_dir))
    yield


def _fake_sync_target(cloud_url="https://sindhu-cloud-1.onrender.com", sync_secret="s3cr3t"):
    return {"cloud_url": cloud_url, "sync_secret": sync_secret}


def _fake_cloud_response(status_code=200, paper_trading_running=True, telegram_sending_enabled=True):
    resp = MagicMock(status_code=status_code)
    resp.json.return_value = {"ok": True, "paper_trading_running": paper_trading_running,
                               "telegram_sending_enabled": telegram_sending_enabled}
    return resp


# ------------------------------------------------------------- check_cloud_status

def test_check_cloud_status_returns_none_when_no_target_configured():
    assert auto_stop.check_cloud_status(None, None) == (None, None)
    assert auto_stop.check_cloud_status("https://x.example", None) == (None, None)


def test_check_cloud_status_returns_none_on_network_error():
    import requests
    with patch("requests.get", side_effect=requests.ConnectionError("boom")):
        assert auto_stop.check_cloud_status("https://x.example", "s3cr3t") == (None, None)


def test_check_cloud_status_returns_none_on_wrong_secret_401():
    with patch("requests.get", return_value=MagicMock(status_code=401)):
        assert auto_stop.check_cloud_status("https://x.example", "wrong") == (None, None)


def test_check_cloud_status_parses_a_real_looking_response():
    with patch("requests.get", return_value=_fake_cloud_response(paper_trading_running=True, telegram_sending_enabled=False)):
        result = auto_stop.check_cloud_status("https://x.example", "s3cr3t")
    assert result == (True, False)


# ------------------------------------------------------------- check_and_maybe_stop_local

def _patch_sync_target(**kwargs):
    return patch("paper_trading.strategy_sync.get_sync_target", return_value=_fake_sync_target(**kwargs))


def test_stops_local_engine_when_cloud_is_both_on():
    with _patch_sync_target(), patch("requests.get", return_value=_fake_cloud_response(paper_trading_running=True, telegram_sending_enabled=True)):
        fake_engine = MagicMock()
        fake_engine.is_running.return_value = True
        fake_engine.stop.return_value = True
        with patch("paper_trading.engine.engine", fake_engine):
            auto_stop.check_and_maybe_stop_local()
        fake_engine.stop.assert_called_once()
    state = auto_stop.get_state()
    assert state["paused_by_cloud"] is True
    assert state["paused_at"] is not None


def test_does_not_stop_when_only_one_of_the_two_is_on():
    with _patch_sync_target(), patch("requests.get", return_value=_fake_cloud_response(paper_trading_running=True, telegram_sending_enabled=False)):
        fake_engine = MagicMock()
        fake_engine.is_running.return_value = True
        with patch("paper_trading.engine.engine", fake_engine):
            auto_stop.check_and_maybe_stop_local()
        fake_engine.stop.assert_not_called()
    assert auto_stop.get_state()["paused_by_cloud"] is False


def test_never_treats_an_unreachable_cloud_as_both_on():
    import requests
    with _patch_sync_target(), patch("requests.get", side_effect=requests.ConnectionError("boom")):
        fake_engine = MagicMock()
        fake_engine.is_running.return_value = True
        with patch("paper_trading.engine.engine", fake_engine):
            auto_stop.check_and_maybe_stop_local()
        fake_engine.stop.assert_not_called()
    assert auto_stop.get_state()["paused_by_cloud"] is False
    assert "unreachable" in auto_stop.get_state()["last_check_result"]


def test_never_re_stops_an_already_stopped_engine():
    """engine.stop() itself should not even be attempted if it's already
    off -- avoids a spurious 'paused_by_cloud' flip from a check that
    changed nothing real."""
    with _patch_sync_target(), patch("requests.get", return_value=_fake_cloud_response(paper_trading_running=True, telegram_sending_enabled=True)):
        fake_engine = MagicMock()
        fake_engine.is_running.return_value = False
        with patch("paper_trading.engine.engine", fake_engine):
            auto_stop.check_and_maybe_stop_local()
        fake_engine.stop.assert_not_called()


def test_clearing_the_pause_reason_does_not_restart_the_engine():
    """The task's own explicit rule: going from both-on to not-both-on
    must NEVER itself start the engine back up."""
    auto_stop._save_state(paused_by_cloud=True, paused_at="2026-01-01T00:00:00+00:00")
    with _patch_sync_target(), patch("requests.get", return_value=_fake_cloud_response(paper_trading_running=False, telegram_sending_enabled=True)):
        fake_engine = MagicMock()
        fake_engine.is_running.return_value = False
        with patch("paper_trading.engine.engine", fake_engine):
            auto_stop.check_and_maybe_stop_local()
        fake_engine.start.assert_not_called()
    assert auto_stop.get_state()["paused_by_cloud"] is False


def test_resume_only_clears_state_never_touches_the_engine_itself():
    """resume_local_after_cloud_pause() is called by the API endpoint right
    BEFORE it separately calls engine.start() -- this function itself must
    never start anything, so a bug here can never accidentally auto-resume
    trading from anywhere else that might call it."""
    auto_stop._save_state(paused_by_cloud=True, paused_at="2026-01-01T00:00:00+00:00")
    with patch("paper_trading.engine.engine") as fake_engine:
        auto_stop.resume_local_after_cloud_pause()
        fake_engine.start.assert_not_called()
    assert auto_stop.get_state()["paused_by_cloud"] is False
