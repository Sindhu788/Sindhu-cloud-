"""Tests for the Web-Sourced Strategies rate limit (Part 3, item 2) --
storage.research_run_log + sindhu_web.api.research's rate-limit gate."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from data_engine import storage, config as base_config
from sindhu_web.api import research


def _iso(dt):
    return dt.isoformat()


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """research.load_settings()/update_settings() write through
    data_engine.config's JSON-file store, separate from the SQLite test_db
    fixture -- without this, these tests would read/write the real
    data/config/research_settings.json on disk instead of a throwaway one."""
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def test_no_runs_logged_is_never_rate_limited(test_db):
    assert storage.count_research_runs_since(_iso(datetime.now(timezone.utc) - timedelta(days=1))) == 0
    research._check_rate_limit()  # should not raise


def test_rate_limit_blocks_after_max_runs_per_day(test_db):
    research.update_settings(research.SettingsUpdate(max_runs_per_day=1))
    storage.log_research_run("search", "test query", 2, datetime.now(timezone.utc).isoformat())

    with pytest.raises(HTTPException) as exc_info:
        research._check_rate_limit()
    assert exc_info.value.status_code == 429


def test_rate_limit_only_counts_last_24_hours(test_db):
    research.update_settings(research.SettingsUpdate(max_runs_per_day=1))
    old_run = datetime.now(timezone.utc) - timedelta(hours=25)
    storage.log_research_run("search", "old query", 1, old_run.isoformat())

    research._check_rate_limit()  # the old run is outside the 24h window -- should not raise


def test_settings_persist_and_reject_invalid_values(test_db):
    research.update_settings(research.SettingsUpdate(max_runs_per_day=3))
    assert research.load_settings()["max_runs_per_day"] == 3

    with pytest.raises(HTTPException):
        research.update_settings(research.SettingsUpdate(max_runs_per_day=0))


def test_higher_limit_allows_more_runs(test_db):
    research.update_settings(research.SettingsUpdate(max_runs_per_day=2))
    now = datetime.now(timezone.utc).isoformat()
    storage.log_research_run("search", "q1", 1, now)
    research._check_rate_limit()  # 1 used, limit 2 -- fine
    storage.log_research_run("search", "q2", 1, now)
    with pytest.raises(HTTPException):
        research._check_rate_limit()  # 2 used, limit 2 -- blocked
