"""Confidence-filtering task, items 4.2-4.4: every Telegram signal message
must clearly say whether its strategy has a real profitable live
paper-trading record or is still under evaluation, must carry an extra
risk disclaimer without exception when it's profitable, and must be
labeled distinctly when it comes from a Challenge Mode-scoped
strategy+coin. See paper_trading/telegram_bot.py's _profitability_label /
_challenge_mode_tag and PROFITABLE_RISK_DISCLAIMER.
"""

from unittest.mock import patch

import pytest

from data_engine import config as base_config, storage
from paper_trading import challenge_mode, challenge_multi, telegram_bot


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _position(**overrides):
    base = {
        "id": "pos1", "strategy_id": "strat1", "strategy_name": "Test Strategy",
        "symbol": "BTCUSDT", "direction": "long", "entry_price": 100.0,
        "stop_loss": 95.0, "take_profit": 110.0, "market_state": "trending_up",
        "session": "london", "entry_reason": "test",
    }
    base.update(overrides)
    return base


def test_strategy_with_no_trade_history_is_labeled_under_evaluation():
    with patch.object(storage, "get_paper_account_summary",
                       return_value={"realized_pnl_total": 0.0, "closed_count": 0, "win_count": 0}):
        text = telegram_bot.format_signal_message(_position(), lang="en")
    assert "STILL UNDER EVALUATION" in text
    assert "PROFITABLE STRATEGY" not in text
    assert telegram_bot.PROFITABLE_RISK_DISCLAIMER not in text


def test_strategy_with_enough_wins_is_labeled_profitable_with_extra_disclaimer():
    with patch.object(storage, "get_paper_account_summary",
                       return_value={"realized_pnl_total": 250.0, "closed_count": 30, "win_count": 20}):
        text = telegram_bot.format_signal_message(_position(), lang="en")
    assert "PROFITABLE STRATEGY" in text
    assert "STILL UNDER EVALUATION" not in text
    assert telegram_bot.PROFITABLE_RISK_DISCLAIMER in text


def test_enough_trades_but_net_negative_pnl_is_not_labeled_profitable():
    """A real sample size alone must never be enough -- the strategy also
    has to actually be net positive live."""
    with patch.object(storage, "get_paper_account_summary",
                       return_value={"realized_pnl_total": -10.0, "closed_count": 40, "win_count": 15}):
        text = telegram_bot.format_signal_message(_position(), lang="en")
    assert "PROFITABLE STRATEGY" not in text
    assert telegram_bot.PROFITABLE_RISK_DISCLAIMER not in text


def test_positive_pnl_but_too_few_trades_is_not_labeled_profitable_yet():
    """Same 25-trade bar pattern_stats.MIN_SAMPLE_SIZE uses elsewhere --
    not a softer, second threshold invented just for this label."""
    with patch.object(storage, "get_paper_account_summary",
                       return_value={"realized_pnl_total": 50.0, "closed_count": 5, "win_count": 4}):
        text = telegram_bot.format_signal_message(_position(), lang="en")
    assert "PROFITABLE STRATEGY" not in text
    assert "STILL UNDER EVALUATION" in text


def test_no_strategy_id_shows_neither_profitability_label():
    text = telegram_bot.format_signal_message(_position(strategy_id=None), lang="en")
    assert "PROFITABLE STRATEGY" not in text
    assert "STILL UNDER EVALUATION" not in text


def test_no_active_challenge_shows_no_challenge_tag():
    text = telegram_bot.format_signal_message(_position(), lang="en")
    assert "CHALLENGE MODE SIGNAL" not in text


def test_challenge_scoped_to_this_exact_strategy_and_coin_is_tagged():
    challenge_mode.set_challenge(100, 200, 30, scope_strategy_id="strat1", scope_symbol="BTCUSDT")
    text = telegram_bot.format_signal_message(_position(strategy_id="strat1", symbol="BTCUSDT"), lang="en")
    assert "CHALLENGE MODE SIGNAL" in text


def test_challenge_scoped_to_a_different_strategy_is_not_tagged():
    challenge_mode.set_challenge(100, 200, 30, scope_strategy_id="strat2", scope_symbol="ETHUSDT")
    text = telegram_bot.format_signal_message(_position(strategy_id="strat1", symbol="BTCUSDT"), lang="en")
    assert "CHALLENGE MODE SIGNAL" not in text


def test_system_wide_unscoped_challenge_does_not_tag_every_signal():
    """A system-wide challenge (no scope_strategy_id) tracks the blended
    account, not one specific signal -- tagging every single signal as
    "the" Challenge Mode signal would be misleading."""
    challenge_mode.set_challenge(100, 200, 30)
    text = telegram_bot.format_signal_message(_position(), lang="en")
    assert "CHALLENGE MODE SIGNAL" not in text


# ------------------------------------------------------------ Master Task 4, Phase 3.7
# Multi-challenge attribution: with up to 3 simultaneous challenges (the
# NEWER paper_trading.challenge_multi system, separate from the original
# single-challenge challenge_mode.py above), a signal must name WHICH
# specific challenge it belongs to, not a single generic tag.

def test_a_signal_scoped_to_one_multi_challenge_names_it_specifically(test_db):
    challenge_multi.create_challenge("Weekly Push", 1000.0, 1200.0, "weekly",
                                      scope_strategy_id="strat1", scope_symbol="BTCUSDT")
    text = telegram_bot.format_signal_message(_position(strategy_id="strat1", symbol="BTCUSDT"), lang="en")
    assert "CHALLENGE SIGNAL: Weekly Push" in text


def test_a_signal_matching_two_active_challenges_names_both(test_db):
    challenge_multi.create_challenge("Weekly Push", 1000.0, 1200.0, "weekly",
                                      scope_strategy_id="strat1", scope_symbol="BTCUSDT")
    challenge_multi.create_challenge("Aggressive Monthly", 500.0, 2000.0, "monthly",
                                      scope_strategy_id="strat1", scope_symbol="BTCUSDT")
    text = telegram_bot.format_signal_message(_position(strategy_id="strat1", symbol="BTCUSDT"), lang="en")
    assert "CHALLENGE SIGNAL: Weekly Push" in text
    assert "CHALLENGE SIGNAL: Aggressive Monthly" in text


def test_a_signal_not_matching_any_multi_challenge_scope_is_not_tagged(test_db):
    challenge_multi.create_challenge("Weekly Push", 1000.0, 1200.0, "weekly",
                                      scope_strategy_id="strat_other", scope_symbol="ETHUSDT")
    text = telegram_bot.format_signal_message(_position(strategy_id="strat1", symbol="BTCUSDT"), lang="en")
    assert "CHALLENGE SIGNAL" not in text


def test_an_archived_multi_challenge_no_longer_tags_new_signals(test_db):
    c = challenge_multi.create_challenge("Weekly Push", 1000.0, 1200.0, "weekly",
                                          scope_strategy_id="strat1", scope_symbol="BTCUSDT")
    challenge_multi.archive_challenge(c["id"])
    text = telegram_bot.format_signal_message(_position(strategy_id="strat1", symbol="BTCUSDT"), lang="en")
    assert "CHALLENGE SIGNAL" not in text


def test_a_system_wide_unscoped_multi_challenge_does_not_tag_every_signal(test_db):
    challenge_multi.create_challenge("Blended Target", 1000.0, 1200.0, "weekly")
    text = telegram_bot.format_signal_message(_position(), lang="en")
    assert "CHALLENGE SIGNAL" not in text


def test_a_challenge_label_with_html_special_characters_is_escaped(test_db):
    """label is CEO-typed free text and Telegram sends with parse_mode=HTML
    -- an unescaped '<'/'&' would otherwise risk breaking message
    delivery."""
    challenge_multi.create_challenge("<b>Injected</b> & Push", 1000.0, 1200.0, "weekly",
                                      scope_strategy_id="strat1", scope_symbol="BTCUSDT")
    text = telegram_bot.format_signal_message(_position(strategy_id="strat1", symbol="BTCUSDT"), lang="en")
    assert "&lt;b&gt;Injected&lt;/b&gt; &amp; Push" in text
    assert "<b>Injected</b> & Push" not in text
