"""Master Task 3, Phase 1.2: self_learning_engine/ai_advisor.py -- AI ONLY
re-ranks an already-scored combination list, never invents concepts, never
runs during backtest/paper-trading. Verifies the safe-fallback behavior
(no provider configured, provider call fails, unparseable response) at
least as thoroughly as the happy path, since "AI unavailable" must never
break discovery.
"""

from unittest.mock import MagicMock, patch

import pytest

from ai_integration.providers import AIResult
from self_learning_engine import ai_advisor


def _candidates():
    return [
        {"dna_combo": ["liquidity", "volume"], "avg_score": 40.0, "sample_size": 5, "best_coins": [{"symbol": "BTCUSDT"}]},
        {"dna_combo": ["trend", "momentum"], "avg_score": 30.0, "sample_size": 3, "best_coins": []},
    ]


def test_no_candidates_returns_none(test_db):
    assert ai_advisor.select_next_combination([]) is None


def test_falls_back_to_top_scored_when_no_provider_configured(test_db):
    with patch("self_learning_engine.ai_advisor.ai_config.provider_fallback_chain", return_value=[]):
        result = ai_advisor.select_next_combination(_candidates())
    assert result["ai_used"] is False
    assert result["combo"]["dna_combo"] == ["liquidity", "volume"]


def test_uses_ai_choice_when_response_is_valid(test_db):
    mock_provider = MagicMock()
    mock_provider.chat.return_value = AIResult(ok=True, text='{"chosen_index": 1, "reason": "more session diversity"}')
    with patch("self_learning_engine.ai_advisor.ai_config.provider_fallback_chain", return_value=["groq"]), \
         patch("self_learning_engine.ai_advisor.ai_config.get_provider_settings", return_value={"model": "test-model"}), \
         patch("self_learning_engine.ai_advisor.get_provider", return_value=mock_provider):
        result = ai_advisor.select_next_combination(_candidates())
    assert result["ai_used"] is True
    assert result["chosen_index"] == 1
    assert result["combo"]["dna_combo"] == ["trend", "momentum"]
    assert result["reason"] == "more session diversity"


def test_falls_back_when_ai_call_fails(test_db):
    mock_provider = MagicMock()
    mock_provider.chat.return_value = AIResult(ok=False, error="rate limited")
    with patch("self_learning_engine.ai_advisor.ai_config.provider_fallback_chain", return_value=["groq"]), \
         patch("self_learning_engine.ai_advisor.ai_config.get_provider_settings", return_value={"model": "test-model"}), \
         patch("self_learning_engine.ai_advisor.get_provider", return_value=mock_provider):
        result = ai_advisor.select_next_combination(_candidates())
    assert result["ai_used"] is False
    assert result["combo"]["dna_combo"] == ["liquidity", "volume"]


def test_falls_back_when_ai_response_is_unparseable(test_db):
    mock_provider = MagicMock()
    mock_provider.chat.return_value = AIResult(ok=True, text="not json at all")
    with patch("self_learning_engine.ai_advisor.ai_config.provider_fallback_chain", return_value=["groq"]), \
         patch("self_learning_engine.ai_advisor.ai_config.get_provider_settings", return_value={"model": "test-model"}), \
         patch("self_learning_engine.ai_advisor.get_provider", return_value=mock_provider):
        result = ai_advisor.select_next_combination(_candidates())
    assert result["ai_used"] is False


def test_falls_back_when_ai_chooses_an_out_of_range_index(test_db):
    mock_provider = MagicMock()
    mock_provider.chat.return_value = AIResult(ok=True, text='{"chosen_index": 99, "reason": "x"}')
    with patch("self_learning_engine.ai_advisor.ai_config.provider_fallback_chain", return_value=["groq"]), \
         patch("self_learning_engine.ai_advisor.ai_config.get_provider_settings", return_value={"model": "test-model"}), \
         patch("self_learning_engine.ai_advisor.get_provider", return_value=mock_provider):
        result = ai_advisor.select_next_combination(_candidates())
    assert result["ai_used"] is False


def test_ai_never_called_when_candidate_list_is_empty(test_db):
    """The advisor must short-circuit before touching any provider chain at
    all when there is nothing to rank -- confirms AI is only ever reached
    from inside select_next_combination's real ranking path, never as a
    side effect of merely calling this module."""
    with patch("self_learning_engine.ai_advisor.get_provider") as mock_get_provider:
        ai_advisor.select_next_combination([])
        mock_get_provider.assert_not_called()
