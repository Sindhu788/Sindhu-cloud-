"""Master Task 3, Phase 1: sindhu_web/api/self_learning.py."""

import time
from unittest.mock import patch

import pytest

from data_engine import config as base_config, feature_toggles
from sindhu_web.api import self_learning as sl_api


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    sl_api._run_in_progress = False
    yield
    sl_api._run_in_progress = False


def test_status_reports_no_cycle_yet(test_db):
    result = sl_api.get_status()
    assert result["latest_cycle"] is None
    assert result["run_in_progress"] is False


def test_status_reports_would_run_now_when_due(test_db):
    result = sl_api.get_status()
    assert result["would_run_now"] is True  # feature enabled by default, no prior cycle


def test_status_reports_would_not_run_when_disabled(test_db):
    feature_toggles.set_toggle("self_learning_engine_enabled", False)
    result = sl_api.get_status()
    assert result["would_run_now"] is False


def test_cycles_and_attempts_endpoints_start_empty(test_db):
    assert sl_api.get_cycles()["cycles"] == []
    assert sl_api.get_attempts()["attempts"] == []


def test_combination_scores_endpoint_returns_a_list(test_db):
    result = sl_api.get_combination_scores()
    assert result["combinations"] == []


def test_run_now_starts_a_background_cycle_and_reports_started(test_db):
    with patch("self_learning_engine.discovery_cycle.run_discovery_cycle", return_value={"status": "no_data"}) as mock_run:
        result = sl_api.run_now()
    assert result["started"] is True
    # Give the background thread a brief moment to actually invoke it.
    for _ in range(50):
        if mock_run.called:
            break
        time.sleep(0.02)
    assert mock_run.called


def test_run_now_refuses_a_second_concurrent_run(test_db):
    sl_api._run_in_progress = True
    result = sl_api.run_now()
    assert result["started"] is False
