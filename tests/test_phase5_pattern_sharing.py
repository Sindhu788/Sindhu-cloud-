"""Grand Master Batch, Phase 5 Item 7 -- Cross-Strategy Pattern Sharing.

A proven pattern from one strategy can be SUGGESTED for another that
trades the same coin, but is never applied without an explicit,
one-at-a-time CEO approval.
"""

from datetime import datetime, timezone

import pytest

from data_engine import config as base_config, storage
from paper_trading import pattern_sharing


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _enable_strategy(strategy_id, supported_coins=None):
    storage.save_paper_strategy_config(strategy_id, True, 1, supported_coins, None, _now_iso())


def test_no_suggestions_with_no_active_patterns(test_db):
    assert pattern_sharing.generate_suggestions() == []


def test_suggests_a_proven_pattern_to_another_enabled_strategy(test_db):
    storage.save_paper_auto_lesson("strat1", "Strategy One", "BTCUSDT", "trending_up", "london",
                                    "boost", 30, 80.0, "proven pattern", _now_iso())
    _enable_strategy("strat2")

    suggestions = pattern_sharing.generate_suggestions()
    assert len(suggestions) == 1
    s = suggestions[0]
    assert s["source_strategy_id"] == "strat1"
    assert s["target_strategy_id"] == "strat2"
    assert s["status"] == "pending"
    # Nothing was actually applied yet.
    assert storage.list_paper_auto_lessons(active_only=True) == [
        row for row in storage.list_paper_auto_lessons(active_only=True) if row["strategy_id"] == "strat1"
    ]


def test_never_suggests_a_strategy_to_itself(test_db):
    storage.save_paper_auto_lesson("strat1", "Strategy One", "BTCUSDT", "trending_up", "london",
                                    "boost", 30, 80.0, "proven pattern", _now_iso())
    _enable_strategy("strat1")
    suggestions = pattern_sharing.generate_suggestions()
    assert suggestions == []


def test_never_suggests_if_target_already_has_the_same_pattern(test_db):
    storage.save_paper_auto_lesson("strat1", "Strategy One", "BTCUSDT", "trending_up", "london",
                                    "boost", 30, 80.0, "proven pattern", _now_iso())
    storage.save_paper_auto_lesson("strat2", "Strategy Two", "BTCUSDT", "trending_up", "london",
                                    "boost", 40, 75.0, "already has its own", _now_iso())
    _enable_strategy("strat2")
    suggestions = pattern_sharing.generate_suggestions()
    assert suggestions == []


def test_respects_coin_restriction_on_target_strategy(test_db):
    storage.save_paper_auto_lesson("strat1", "Strategy One", "BTCUSDT", "trending_up", "london",
                                    "boost", 30, 80.0, "proven pattern", _now_iso())
    _enable_strategy("strat2", supported_coins=["ETHUSDT"])
    suggestions = pattern_sharing.generate_suggestions()
    assert suggestions == []


def test_regenerating_does_not_duplicate_pending_suggestions(test_db):
    storage.save_paper_auto_lesson("strat1", "Strategy One", "BTCUSDT", "trending_up", "london",
                                    "boost", 30, 80.0, "proven pattern", _now_iso())
    _enable_strategy("strat2")
    pattern_sharing.generate_suggestions()
    second = pattern_sharing.generate_suggestions()
    assert second == []
    assert len(pattern_sharing.list_suggestions()) == 1


def test_approve_actually_applies_the_pattern_to_the_target(test_db):
    storage.save_paper_auto_lesson("strat1", "Strategy One", "BTCUSDT", "trending_up", "london",
                                    "boost", 30, 80.0, "proven pattern", _now_iso())
    _enable_strategy("strat2")
    suggestion = pattern_sharing.generate_suggestions()[0]

    pattern_sharing.approve_suggestion(suggestion["id"])

    applied = [r for r in storage.list_paper_auto_lessons(active_only=True) if r["strategy_id"] == "strat2"]
    assert len(applied) == 1
    assert applied[0]["symbol"] == "BTCUSDT"
    assert pattern_sharing.list_suggestions(status="approved")[0]["id"] == suggestion["id"]


def test_reject_never_applies_anything(test_db):
    storage.save_paper_auto_lesson("strat1", "Strategy One", "BTCUSDT", "trending_up", "london",
                                    "boost", 30, 80.0, "proven pattern", _now_iso())
    _enable_strategy("strat2")
    suggestion = pattern_sharing.generate_suggestions()[0]

    pattern_sharing.reject_suggestion(suggestion["id"])

    assert [r for r in storage.list_paper_auto_lessons(active_only=True) if r["strategy_id"] == "strat2"] == []
    assert pattern_sharing.list_suggestions(status="rejected")[0]["id"] == suggestion["id"]


def test_approving_twice_raises(test_db):
    storage.save_paper_auto_lesson("strat1", "Strategy One", "BTCUSDT", "trending_up", "london",
                                    "boost", 30, 80.0, "proven pattern", _now_iso())
    _enable_strategy("strat2")
    suggestion = pattern_sharing.generate_suggestions()[0]
    pattern_sharing.approve_suggestion(suggestion["id"])
    with pytest.raises(ValueError):
        pattern_sharing.approve_suggestion(suggestion["id"])


def test_unknown_suggestion_id_raises(test_db):
    with pytest.raises(ValueError):
        pattern_sharing.approve_suggestion("does-not-exist")
