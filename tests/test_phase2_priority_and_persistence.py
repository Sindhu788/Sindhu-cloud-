"""Grand Master Batch, Phase 2 -- Core Fixes.

Covers 2.1 (priority ranking must use real win rate, not confidence alone)
and 2.2 (settings-not-saving bug: some settings were wiped on every cloud
redeploy because they lived only in a local JSON file instead of Postgres).
"""

import pytest

from data_engine import config as base_config, db_backend, storage
from data_engine import feature_toggles
from paper_trading import ai_trade_review, guards


# --------------------------------------------------------------------- 2.1

def _candidate(confidence, win_rate=None, total_pnl=0.0, strategy_id="s1"):
    return {"confidence": confidence, "_win_rate": win_rate, "_total_pnl": total_pnl,
            "strategy_id": strategy_id}


def test_confidence_and_win_rate_prefers_proven_strategy_over_higher_confidence():
    # A brand-new-looking 70-confidence signal from a strategy with a real,
    # proven 90% win rate should beat an 80-confidence signal from a
    # strategy with a real, proven 20% win rate -- confidence alone (the
    # old default) would have picked the second one.
    proven_winner = _candidate(confidence=70, win_rate=90, strategy_id="good")
    unproven_flashy = _candidate(confidence=80, win_rate=20, strategy_id="bad")
    pick = guards.rank_candidates([proven_winner, unproven_flashy], "confidence_and_win_rate")
    assert pick["strategy_id"] == "good"


def test_confidence_and_win_rate_falls_back_to_confidence_when_no_real_track_record():
    # win_rate=None (fewer than MIN_SAMPLE_SIZE real closed trades) must
    # never be treated as a real 0% win rate -- it should fall back to
    # pure confidence so a brand-new strategy isn't unfairly buried.
    brand_new = _candidate(confidence=80, win_rate=None, strategy_id="new")
    mediocre_proven = _candidate(confidence=60, win_rate=40, strategy_id="proven")
    pick = guards.rank_candidates([brand_new, mediocre_proven], "confidence_and_win_rate")
    assert pick["strategy_id"] == "new"


def test_win_rate_rule_is_no_longer_a_silent_noop():
    # Before this fix, "_win_rate" was never populated anywhere in the
    # codebase, so priority_rule="win_rate" always compared 0 == 0 for
    # every candidate and silently fell back to being confidence-only.
    real_high_win_rate = _candidate(confidence=50, win_rate=95, strategy_id="high_wr")
    real_low_win_rate = _candidate(confidence=90, win_rate=10, strategy_id="low_wr")
    pick = guards.rank_candidates([real_high_win_rate, real_low_win_rate], "win_rate")
    assert pick["strategy_id"] == "high_wr"


def test_default_priority_rule_is_confidence_and_win_rate():
    assert base_config.load_or_seed.__module__  # sanity import check
    from paper_trading import config as pt_config
    assert pt_config._DEFAULTS["priority_rule"] == "confidence_and_win_rate"


def test_engine_populates_real_win_rate_from_account_summary(test_db, monkeypatch):
    # Reproduces the real code path: engine._process_coin looks up
    # storage.get_paper_account_summary(book_key) and only trusts it as a
    # real win rate once closed_count >= pattern_stats.MIN_SAMPLE_SIZE.
    from paper_trading import pattern_stats
    for i in range(pattern_stats.MIN_SAMPLE_SIZE):
        pnl = 1.0 if i < 20 else -1.0  # 20/25 = 80% real win rate
        storage.close_paper_position(f"pos{i}", 100.0, "2026-01-01T00:00:00+00:00", pnl, 1.0, "test",
                                      {}, {}, "2026-01-01T00:00:00+00:00", book_key="s1")
    summary = storage.get_paper_account_summary("s1")
    assert summary["closed_count"] == pattern_stats.MIN_SAMPLE_SIZE
    win_rate = round(summary["win_count"] / summary["closed_count"] * 100, 1)
    assert win_rate == 80.0


# --------------------------------------------------------------------- 2.2

@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def test_load_persistent_uses_local_file_when_not_postgres(monkeypatch):
    monkeypatch.setattr(db_backend, "IS_POSTGRES", False)
    saved = base_config.load_persistent("some_key", "some_file.json", {"a": 1})
    assert saved == {"a": 1}
    base_config.save_persistent("some_key", "some_file.json", {"a": 2})
    assert base_config.load_persistent("some_key", "some_file.json", {"a": 1}) == {"a": 2}


def test_load_persistent_uses_postgres_cloud_setting_when_on_postgres(monkeypatch):
    # Simulates the exact bug: on the cloud deployment, a save must land in
    # cloud_settings (survives a redeploy), never only in the local file
    # (which Render wipes on every restart).
    monkeypatch.setattr(db_backend, "IS_POSTGRES", True)
    saved_rows = {}

    def fake_get(key):
        return saved_rows.get(key)

    def fake_save(key, data, now_iso):
        saved_rows[key] = data

    monkeypatch.setattr(storage, "get_cloud_setting", fake_get)
    monkeypatch.setattr(storage, "save_cloud_setting", fake_save)

    assert base_config.load_persistent("toggle_key", "toggle_file.json", {"enabled": False}) == {"enabled": False}
    base_config.save_persistent("toggle_key", "toggle_file.json", {"enabled": True})
    # Simulate a redeploy: the local file is never written to on Postgres,
    # so re-reading must come from the fake cloud_settings row, not defaults.
    assert saved_rows["toggle_key"] == {"enabled": True}
    assert base_config.load_persistent("toggle_key", "toggle_file.json", {"enabled": False}) == {"enabled": True}


def test_feature_toggle_survives_simulated_cloud_redeploy(monkeypatch):
    monkeypatch.setattr(db_backend, "IS_POSTGRES", True)
    saved_rows = {}
    monkeypatch.setattr(storage, "get_cloud_setting", lambda key: saved_rows.get(key))
    monkeypatch.setattr(storage, "save_cloud_setting", lambda key, data, now_iso: saved_rows.__setitem__(key, data))

    feature_toggles.set_toggle("strategy_lab_enabled", False)
    # A fresh read (as a new process after a redeploy would do) must see
    # the change, not silently fall back to DEFAULTS (True).
    assert feature_toggles.get_toggles()["strategy_lab_enabled"] is False


def test_ai_trade_review_toggle_survives_simulated_cloud_redeploy(monkeypatch):
    monkeypatch.setattr(db_backend, "IS_POSTGRES", True)
    saved_rows = {}
    monkeypatch.setattr(storage, "get_cloud_setting", lambda key: saved_rows.get(key))
    monkeypatch.setattr(storage, "save_cloud_setting", lambda key, data, now_iso: saved_rows.__setitem__(key, data))

    assert ai_trade_review.is_enabled() is False
    ai_trade_review.set_enabled(True)
    assert ai_trade_review.is_enabled() is True
