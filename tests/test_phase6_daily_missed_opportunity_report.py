"""Grand Master Batch, Phase 6 Item 13 -- Daily "Missed Opportunity" Report.

A day-boundary digest of telegram_bot's existing Near-Miss Log, distinct
from the live cumulative log itself.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from data_engine import config as base_config, feature_toggles, storage
from paper_trading import daily_missed_opportunity_report as report_mod


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _near_miss(position_id, strategy_name, created_at, reason="confluence too weak"):
    storage.save_near_miss({
        "position_id": position_id, "strategy_id": strategy_name, "strategy_name": strategy_name,
        "symbol": "BTCUSDT", "confluence_ratio": 0.5, "confluence_passed": 2, "confluence_total": 4,
        "confluence_required_ratio": 1.0, "confluence_required_count": 3,
        "pattern_status": "insufficient_data", "pattern_trades": 5, "pattern_required": 25,
        "pattern_win_rate_pct": None, "live_pnl": None, "reason": reason,
    }, created_at)


def test_empty_day_reports_zero(test_db):
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    result = report_mod.generate_report(day=yesterday)
    assert result["total_missed"] == 0
    assert "No signals were gated out" in result["report_text"]


def test_counts_only_the_specified_day(test_db):
    target_day = date(2026, 3, 15)
    _near_miss("p1", "Strat A", "2026-03-15T10:00:00+00:00")
    _near_miss("p2", "Strat A", "2026-03-15T14:00:00+00:00")
    _near_miss("p3", "Strat B", "2026-03-14T10:00:00+00:00")  # different day -- excluded
    _near_miss("p4", "Strat B", "2026-03-16T10:00:00+00:00")  # different day -- excluded

    result = report_mod.generate_report(day=target_day)
    assert result["total_missed"] == 2
    assert result["date"] == "2026-03-15"


def test_groups_by_strategy_ranked_descending(test_db):
    target_day = date(2026, 3, 15)
    for i in range(3):
        _near_miss(f"pA{i}", "Strat A", "2026-03-15T10:00:00+00:00")
    _near_miss("pB0", "Strat B", "2026-03-15T11:00:00+00:00")

    result = report_mod.generate_report(day=target_day)
    assert result["by_strategy"][0] == {"strategy_name": "Strat A", "count": 3}
    assert result["by_strategy"][1] == {"strategy_name": "Strat B", "count": 1}


def test_maybe_send_respects_weekly_report_feature_toggle(test_db):
    feature_toggles.set_toggle("weekly_report_enabled", False)
    assert report_mod.maybe_send_daily_report() is None


def test_maybe_send_only_once_per_real_day(test_db):
    feature_toggles.set_toggle("weekly_report_enabled", True)
    with patch("paper_trading.telegram_bot._master_enabled", return_value=False):
        first = report_mod.maybe_send_daily_report()
        second = report_mod.maybe_send_daily_report()
    assert first is not None
    assert second is None


def test_maybe_send_sends_a_real_telegram_message_when_enabled(test_db):
    feature_toggles.set_toggle("weekly_report_enabled", True)
    from paper_trading import telegram_bot
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}
        result = report_mod.maybe_send_daily_report()
    assert result["telegram_sent"] is True
    assert mock_post.called
