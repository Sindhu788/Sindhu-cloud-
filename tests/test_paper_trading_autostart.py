"""Batch 9, Task 3: Paper Trading Engine auto-start on server launch.
pt_config's "engine_enabled" records the CEO's last EXPLICIT start/stop
choice (written the instant the API endpoint is called, not just on a
clean shutdown, since base_config.save_config writes synchronously to
disk) -- resume_engine_on_startup() must restore to exactly that state,
never forcing anything on."""

from unittest.mock import patch

import pytest

from data_engine import config as base_config
from paper_trading import config as pt_config
from paper_trading.engine import engine, resume_engine_on_startup


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def test_default_is_off():
    assert pt_config.load()["engine_enabled"] is False


def test_starting_the_engine_persists_enabled_true():
    with patch.object(engine, "start", return_value=True) as mock_start:
        # Mirrors exactly what sindhu_web/api/paper_trading.py's
        # start_engine() endpoint does.
        engine.start(log=lambda m: None, on_event=lambda p: None)
        pt_config.update(engine_enabled=True)
    assert pt_config.load()["engine_enabled"] is True


def test_stopping_the_engine_persists_enabled_false():
    pt_config.update(engine_enabled=True)
    with patch.object(engine, "stop", return_value=True):
        engine.stop()
        pt_config.update(engine_enabled=False)
    assert pt_config.load()["engine_enabled"] is False


def test_resume_starts_the_engine_when_it_was_on(test_db):
    pt_config.update(engine_enabled=True)
    with patch.object(engine, "start", return_value=True) as mock_start:
        resume_engine_on_startup()
    mock_start.assert_called_once()


def test_resume_never_forces_the_engine_on_when_it_was_off(test_db):
    pt_config.update(engine_enabled=False)
    with patch.object(engine, "start", return_value=True) as mock_start:
        resume_engine_on_startup()
    mock_start.assert_not_called()


def test_resume_respects_a_deliberate_off_even_after_a_prior_on_session(test_db):
    """The user turns it on, then explicitly off again -- resume must
    honor the LATEST explicit choice, not just "was it ever on"."""
    pt_config.update(engine_enabled=True)
    pt_config.update(engine_enabled=False)
    with patch.object(engine, "start", return_value=True) as mock_start:
        resume_engine_on_startup()
    mock_start.assert_not_called()


def test_state_survives_without_any_graceful_shutdown_call(test_db):
    """No clean-exit hook is involved in persisting this at all -- the
    write already happened synchronously the instant start()/stop() was
    called (pt_config.update -> base_config.save_config, a plain
    synchronous file write). Simulates a real ungraceful restart: config
    is read fresh, with no shutdown-time code having run in between."""
    pt_config.update(engine_enabled=True)
    # No clean shutdown call of any kind here -- simulates power loss.
    reloaded = pt_config.load()
    assert reloaded["engine_enabled"] is True
    with patch.object(engine, "start", return_value=True) as mock_start:
        resume_engine_on_startup()
    mock_start.assert_called_once()


def test_resume_stays_off_when_kill_switch_is_active(test_db):
    """Grand Feature Expansion, Phase 1 Feature 1 (Kill-Switch): a kill
    switch left active from before a restart must win over even an
    explicit engine_enabled=True -- resume_engine_on_startup() must never
    quietly bring trading back after an emergency stop."""
    from paper_trading import kill_switch
    pt_config.update(engine_enabled=True)
    kill_switch.activate(reason="test", close_positions=False)
    with patch.object(engine, "start", return_value=True) as mock_start:
        resume_engine_on_startup()
    mock_start.assert_not_called()
