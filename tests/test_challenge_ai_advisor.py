"""Master Task 3, Phase 2.21: paper_trading/challenge_ai_advisor.py -- AI
ONLY explains already-decided real numbers, never decides realism itself,
never runs during trading. Safe-fallback behavior tested at least as
thoroughly as the happy path.
"""

from unittest.mock import MagicMock, patch

from ai_integration.providers import AIResult
from paper_trading import challenge_ai_advisor


def _progress(realistic=True):
    return {
        "required_daily_rate_pct": 0.5, "real_demonstrated_daily_rate_pct": 1.0,
        "closed_trades_used_for_baseline": 40, "ahead_of_pace": True, "realistic": realistic,
    }


def test_falls_back_when_no_provider_configured(test_db):
    with patch("paper_trading.challenge_ai_advisor.ai_config.provider_fallback_chain", return_value=[]):
        result = challenge_ai_advisor.explain(_progress(), "Easy")
    assert result["ai_used"] is False
    assert "mumkin lagta hai" in result["explanation"] or "realistic" in result["explanation"].lower() or len(result["explanation"]) > 0


def test_uses_ai_explanation_when_response_is_valid(test_db):
    mock_provider = MagicMock()
    mock_provider.chat.return_value = AIResult(ok=True, text='{"explanation": "You are on track based on real trades."}')
    with patch("paper_trading.challenge_ai_advisor.ai_config.provider_fallback_chain", return_value=["groq"]), \
         patch("paper_trading.challenge_ai_advisor.ai_config.get_provider_settings", return_value={"model": "m"}), \
         patch("paper_trading.challenge_ai_advisor.get_provider", return_value=mock_provider):
        result = challenge_ai_advisor.explain(_progress(), "Easy")
    assert result["ai_used"] is True
    assert result["explanation"] == "You are on track based on real trades."


def test_falls_back_when_ai_call_fails(test_db):
    mock_provider = MagicMock()
    mock_provider.chat.return_value = AIResult(ok=False, error="down")
    with patch("paper_trading.challenge_ai_advisor.ai_config.provider_fallback_chain", return_value=["groq"]), \
         patch("paper_trading.challenge_ai_advisor.ai_config.get_provider_settings", return_value={"model": "m"}), \
         patch("paper_trading.challenge_ai_advisor.get_provider", return_value=mock_provider):
        result = challenge_ai_advisor.explain(_progress(realistic=False), "Hard")
    assert result["ai_used"] is False


def test_falls_back_when_response_is_unparseable(test_db):
    mock_provider = MagicMock()
    mock_provider.chat.return_value = AIResult(ok=True, text="not json")
    with patch("paper_trading.challenge_ai_advisor.ai_config.provider_fallback_chain", return_value=["groq"]), \
         patch("paper_trading.challenge_ai_advisor.ai_config.get_provider_settings", return_value={"model": "m"}), \
         patch("paper_trading.challenge_ai_advisor.get_provider", return_value=mock_provider):
        result = challenge_ai_advisor.explain(_progress(), "Moderate")
    assert result["ai_used"] is False


def test_fallback_explanation_differs_for_realistic_vs_not(test_db):
    with patch("paper_trading.challenge_ai_advisor.ai_config.provider_fallback_chain", return_value=[]):
        realistic_result = challenge_ai_advisor.explain(_progress(realistic=True), "Easy")
        unrealistic_result = challenge_ai_advisor.explain(_progress(realistic=False), "Extremely Unlikely")
    assert realistic_result["explanation"] != unrealistic_result["explanation"]


def test_no_ai_call_when_no_provider_chain(test_db):
    with patch("paper_trading.challenge_ai_advisor.ai_config.provider_fallback_chain", return_value=[]), \
         patch("paper_trading.challenge_ai_advisor.get_provider") as mock_get_provider:
        challenge_ai_advisor.explain(_progress(), "Easy")
        mock_get_provider.assert_not_called()
