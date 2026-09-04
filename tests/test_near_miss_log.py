"""Master Task 5, Part 1.5 -- the Near-Miss Log.

Every real signal that gets evaluated for Telegram auto-send and does not
reach High Confidence should be permanently recorded (once per position),
with the actual confluence and pattern-reliability numbers -- so the CEO
can see, over time, how close signals are really coming to the bar without
a one-off manual investigation. Purely observational: never affects any
gate or send decision.
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
        "session": "london", "entry_reason": "test",
        "exchange": "binance", "size": 1.0, "risk_amount": 5.0,
        "entry_time": int(datetime.now(timezone.utc).timestamp() * 1000),
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    pos.update(overrides)
    storage.open_paper_position(pos)
    return pos


def _enable_auto_send(min_ratio=1.0, min_count=1):
    telegram_bot.save_settings(
        bot_token="dummy", channel_id="123", auto_send_enabled=True,
        auto_send_min_confluence_ratio=min_ratio, auto_send_min_confluence_count=min_count,
    )


WEAK_CONFLUENCE = {"passed": 1, "total": 3, "label": "Weak -- 1/3 factors aligned", "factors": []}


def test_a_genuine_near_miss_is_logged_with_real_numbers(test_db):
    _enable_auto_send(min_ratio=1.0)
    _open_position()
    with patch.object(telegram_bot.confluence_mod, "score_confluence", return_value=WEAK_CONFLUENCE):
        tier, reason = telegram_bot.evaluate_auto_send_tier("pos1")
    assert tier is None

    rows = storage.list_near_misses()
    assert len(rows) == 1
    row = rows[0]
    assert row["position_id"] == "pos1"
    assert row["strategy_name"] == "Test Strategy"
    assert row["symbol"] == "BTCUSDT"
    assert row["confluence_passed"] == 1
    assert row["confluence_total"] == 3
    assert abs(row["confluence_ratio"] - (1 / 3)) < 1e-9
    assert row["confluence_required_ratio"] == 1.0
    assert row["pattern_status"] == "insufficient_data"
    assert row["pattern_required"] == pattern_stats.MIN_SAMPLE_SIZE
    assert row["reason"]


def test_a_near_miss_is_only_ever_logged_once_per_position(test_db):
    _enable_auto_send(min_ratio=1.0)
    _open_position()
    with patch.object(telegram_bot.confluence_mod, "score_confluence", return_value=WEAK_CONFLUENCE):
        telegram_bot.evaluate_auto_send_tier("pos1")
        telegram_bot.evaluate_auto_send_tier("pos1")  # simulates a later hourly-sweep re-check
        telegram_bot.evaluate_auto_send_tier("pos1")

    assert len(storage.list_near_misses()) == 1


def test_a_signal_that_qualifies_for_high_confidence_is_not_logged_as_a_near_miss(test_db):
    _enable_auto_send()
    _open_position()
    full_confluence = {"passed": 4, "total": 4, "label": "Strong -- 4/4 factors aligned", "factors": []}
    good_reliability = pattern_stats.classify(wins=23, n=25)
    with patch.object(telegram_bot.confluence_mod, "score_confluence", return_value=full_confluence), \
         patch.object(telegram_bot, "_pattern_reliability_for", return_value=good_reliability), \
         patch.object(storage, "get_paper_realized_pnl_total", return_value=50.0):
        tier, _ = telegram_bot.evaluate_auto_send_tier("pos1")
    assert tier == "high"
    assert storage.list_near_misses() == []


def test_nothing_is_logged_while_auto_send_is_turned_off(test_db):
    """Automation being off is an operational state, not a real 'signal fell
    short of quality' event -- it must not pollute the Near-Miss Log."""
    telegram_bot.save_settings(bot_token="dummy", channel_id="123", auto_send_enabled=False)
    _open_position()
    tier, reason = telegram_bot.evaluate_auto_send_tier("pos1")
    assert tier is None
    assert storage.list_near_misses() == []


def test_low_tier_qualifying_but_withheld_by_high_confidence_only_is_still_a_near_miss(test_db):
    """A signal that clears the LOW tier but is withheld because
    auto_send_high_confidence_only is on IS a genuine near-miss (it fell
    short of HIGH specifically) and must be logged."""
    _enable_auto_send()
    _open_position()
    full_confluence = {"passed": 4, "total": 4, "label": "Strong -- 4/4 factors aligned", "factors": []}
    with patch.object(telegram_bot.confluence_mod, "score_confluence", return_value=full_confluence):
        tier, reason = telegram_bot.evaluate_auto_send_tier("pos1")
    assert tier is None
    assert "only High Confidence" in reason
    rows = storage.list_near_misses()
    assert len(rows) == 1
    assert rows[0]["confluence_passed"] == 4


def test_near_miss_endpoint_reports_a_confluence_deficit_band(test_db):
    from sindhu_web.api import paper_trading as pt_api

    _enable_auto_send(min_ratio=1.0)
    _open_position()
    with patch.object(telegram_bot.confluence_mod, "score_confluence", return_value=WEAK_CONFLUENCE):
        telegram_bot.evaluate_auto_send_tier("pos1")

    result = pt_api.get_near_misses(limit=200)
    assert result["total"] == 1
    assert result["near_misses"][0]["confluence_deficit_pct"] is not None
    assert result["near_misses"][0]["confluence_deficit_pct"] > 0
    assert len(result["confluence_deficit_bands"]) == 1
    assert result["pattern_gate_insufficient_data_count"] == 1
