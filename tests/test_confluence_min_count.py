"""Batch 6, Task 3 -- Stricter Confluence Scoring: High Confidence now
requires a minimum ABSOLUTE count of aligned confluence factors, on top
of the existing ratio requirement. The ratio alone can be satisfied by as
few as 1/1 counted factor (the other 3 were "neutral" -- not enough data,
excluded from the denominator); this closes that gap using the same
already-computed confluence numbers. HIGH tier only -- the Low tier's
fallback purpose and the 25-trade Wilson gate are both untouched.
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from data_engine import config as base_config, storage
from paper_trading import telegram_bot, pattern_stats


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


@pytest.fixture(autouse=True)
def no_real_live_price(monkeypatch):
    monkeypatch.setattr(telegram_bot, "_fetch_live_price", lambda *a, **k: None)


def _open_position(**overrides):
    pos = {
        "id": "pos1", "strategy_id": "strat1", "strategy_name": "Test Strategy",
        "symbol": "BTCUSDT", "direction": "long", "entry_price": 100.0,
        "stop_loss": 95.0, "take_profit": 110.0, "market_state": "trending_up",
        "session": "london", "entry_reason": "test", "exchange": "binance",
        "size": 1.0, "risk_amount": 5.0,
        "entry_time": int(datetime.now(timezone.utc).timestamp() * 1000),
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    pos.update(overrides)
    storage.open_paper_position(pos)
    return pos


def _enable_auto_send(min_ratio=0.0, min_count=3):
    telegram_bot.save_settings(
        bot_token="dummy", channel_id="123", auto_send_enabled=True,
        auto_send_min_confluence_ratio=min_ratio, auto_send_min_confluence_count=min_count,
    )


def _good_reliability():
    return pattern_stats.classify(wins=23, n=25)  # reliable_good


def test_default_minimum_count_is_three():
    assert telegram_bot._DEFAULTS["auto_send_min_confluence_count"] == 3
    assert telegram_bot.public_settings()["auto_send_min_confluence_count"] == 3


def test_high_tier_blocked_when_ratio_is_perfect_but_count_is_too_low(test_db):
    """A 100% ratio from only 2 counted factors (the other 2 were neutral)
    must NOT qualify for High Confidence under the new minimum-count bar."""
    _enable_auto_send(min_ratio=1.0, min_count=3)
    _open_position()
    thin_confluence = {"passed": 2, "total": 2, "label": "Strong -- 2/2 factors aligned", "factors": []}
    with patch.object(telegram_bot.confluence_mod, "score_confluence", return_value=thin_confluence), \
         patch.object(telegram_bot, "_pattern_reliability_for", return_value=_good_reliability()), \
         patch.object(storage, "get_paper_realized_pnl_total", return_value=10.0):
        should_send, reason = telegram_bot.evaluate_auto_send("pos1")
    assert should_send is False
    assert "too few factors" in reason


def test_high_tier_qualifies_at_exactly_the_minimum_count_boundary(test_db):
    """Boundary case: passed == min_count exactly must qualify (not just >)."""
    _enable_auto_send(min_ratio=1.0, min_count=3)
    _open_position()
    exact_confluence = {"passed": 3, "total": 3, "label": "Strong -- 3/3 factors aligned", "factors": []}
    with patch.object(telegram_bot.confluence_mod, "score_confluence", return_value=exact_confluence), \
         patch.object(telegram_bot, "_pattern_reliability_for", return_value=_good_reliability()), \
         patch.object(storage, "get_paper_realized_pnl_total", return_value=10.0):
        should_send, reason = telegram_bot.evaluate_auto_send("pos1")
    assert should_send is True


def test_high_tier_qualifies_above_the_minimum_count(test_db):
    _enable_auto_send(min_ratio=1.0, min_count=3)
    _open_position()
    full_confluence = {"passed": 4, "total": 4, "label": "Strong -- 4/4 factors aligned", "factors": []}
    with patch.object(telegram_bot.confluence_mod, "score_confluence", return_value=full_confluence), \
         patch.object(telegram_bot, "_pattern_reliability_for", return_value=_good_reliability()), \
         patch.object(storage, "get_paper_realized_pnl_total", return_value=10.0):
        should_send, reason = telegram_bot.evaluate_auto_send("pos1")
    assert should_send is True


def test_low_tier_is_never_affected_by_the_minimum_count(test_db):
    """The Low tier's whole purpose is being the fallback when the high
    bar isn't cleared -- it must keep accepting a thin (e.g. 2/2) but
    ratio-passing confluence exactly as before."""
    _enable_auto_send(min_ratio=1.0, min_count=3)
    _open_position()
    thin_confluence = {"passed": 2, "total": 2, "label": "Strong -- 2/2 factors aligned", "factors": []}
    with patch.object(telegram_bot.confluence_mod, "score_confluence", return_value=thin_confluence), \
         patch.object(storage, "get_paper_realized_pnl_total", return_value=10.0):
        should_send, reason = telegram_bot.evaluate_auto_send_low_tier("pos1")
    assert should_send is True


def test_configured_min_count_of_one_restores_the_old_ratio_only_behavior(test_db):
    """Setting the new knob to 1 (the previous effective floor) reproduces
    exactly what the system did before this task -- an explicit opt-out,
    never a hardcoded removal of the old behavior."""
    _enable_auto_send(min_ratio=1.0, min_count=1)
    _open_position()
    thin_confluence = {"passed": 1, "total": 1, "label": "Strong -- 1/1 factors aligned", "factors": []}
    with patch.object(telegram_bot.confluence_mod, "score_confluence", return_value=thin_confluence), \
         patch.object(telegram_bot, "_pattern_reliability_for", return_value=_good_reliability()), \
         patch.object(storage, "get_paper_realized_pnl_total", return_value=10.0):
        should_send, reason = telegram_bot.evaluate_auto_send("pos1")
    assert should_send is True


def test_wilson_gate_still_independently_required_after_count_passes(test_db):
    """The 25-trade Wilson gate is a SEPARATE, independent requirement --
    passing the new minimum-count bar must never bypass it."""
    _enable_auto_send(min_ratio=1.0, min_count=3)
    _open_position()
    full_confluence = {"passed": 4, "total": 4, "label": "Strong -- 4/4 factors aligned", "factors": []}
    with patch.object(telegram_bot.confluence_mod, "score_confluence", return_value=full_confluence):
        should_send, reason = telegram_bot.evaluate_auto_send("pos1")
    assert should_send is False
    assert "statistically confident" in reason
