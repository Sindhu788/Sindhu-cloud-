"""Master Task 3, Phase 2: the new multi-challenge API endpoints in
sindhu_web/api/paper_trading.py -- calls the endpoint functions directly,
same convention as test_strategy_overview.py.
"""

from unittest.mock import patch

import pytest

from data_engine import config as base_config
from sindhu_web.api import paper_trading as pt_api


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def test_list_challenges_starts_empty(test_db):
    assert pt_api.list_challenges_with_progress()["challenges"] == []


def test_create_challenge_via_api(test_db):
    req = pt_api.MultiChallengeCreateRequest(
        label="My Weekly Push", start_amount=1000.0, target_amount=1200.0, timeframe_type="weekly",
    )
    result = pt_api.create_multi_challenge(req)
    assert result["ok"] is True
    assert result["challenge"]["label"] == "My Weekly Push"
    assert result["challenge"]["days"] == 7

    listed = pt_api.list_challenges_with_progress()["challenges"]
    assert len(listed) == 1


def test_create_challenge_rejects_a_fourth(test_db):
    for label in ("A", "B", "C"):
        pt_api.create_multi_challenge(pt_api.MultiChallengeCreateRequest(
            label=label, start_amount=1000.0, target_amount=1200.0, timeframe_type="daily",
        ))
    with pytest.raises(Exception):
        pt_api.create_multi_challenge(pt_api.MultiChallengeCreateRequest(
            label="D", start_amount=1000.0, target_amount=1200.0, timeframe_type="daily",
        ))


def test_archive_removes_from_active_list(test_db):
    created = pt_api.create_multi_challenge(pt_api.MultiChallengeCreateRequest(
        label="A", start_amount=1000.0, target_amount=1200.0, timeframe_type="daily",
    ))
    challenge_id = created["challenge"]["challenge_id"]
    pt_api.archive_multi_challenge(challenge_id)
    assert pt_api.list_challenges_with_progress()["challenges"] == []


def test_extend_deadline_via_api(test_db):
    created = pt_api.create_multi_challenge(pt_api.MultiChallengeCreateRequest(
        label="A", start_amount=1000.0, target_amount=1200.0, timeframe_type="daily",
    ))
    challenge_id = created["challenge"]["challenge_id"]
    result = pt_api.extend_multi_challenge(challenge_id, pt_api.ChallengeExtendRequest(new_days=21))
    assert result["challenge"]["days"] == 21


def test_full_analysis_returns_all_sections(test_db):
    created = pt_api.create_multi_challenge(pt_api.MultiChallengeCreateRequest(
        label="A", start_amount=1000.0, target_amount=2000.0, timeframe_type="custom", days=30,
    ))
    challenge_id = created["challenge"]["challenge_id"]

    with patch("paper_trading.challenge_ai_advisor.ai_config.provider_fallback_chain", return_value=[]):
        result = pt_api.get_challenge_full_analysis(challenge_id)

    assert result["progress"]["challenge_id"] == challenge_id
    assert "difficulty" in result
    assert "best_worst_likely" in result
    assert "give_up_point" in result
    assert "compounding_comparison" in result
    assert "achievability_trend" in result
    assert result["ai_explanation"]["ai_used"] is False


def test_full_analysis_404_for_unknown_challenge(test_db):
    with pytest.raises(Exception):
        pt_api.get_challenge_full_analysis("does-not-exist")


def test_replay_endpoint(test_db):
    result = pt_api.replay_challenge(pt_api.ChallengeReplayRequest(
        start_amount=1000.0, target_amount=2000.0, days_ago_started=10,
    ))
    assert result["trades_counted"] == 0
    assert result["ending_amount"] == 1000.0


def test_rotation_suggestion_endpoint(test_db):
    result = pt_api.get_rotation_suggestion()
    assert result["suggestion"] is None
