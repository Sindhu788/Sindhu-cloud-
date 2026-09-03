"""Grand Feature Expansion, Phase 2 Feature 19: Weekly Performance Digest.
paper_trading/weekly_report.py already existed (dashboard-only, no
Telegram delivery, no chart/visual) -- this adds the two missing pieces:
a plain-text Unicode sparkline of daily PnL (the "chart/visual" this
feature is named for) and an actual Telegram send, reusing the exact same
generation/persistence gate that already prevents more than one report
per REPORT_INTERVAL_DAYS.
"""

from datetime import datetime, timezone
from unittest.mock import patch

from data_engine import config as base_config, feature_toggles, storage
from paper_trading import weekly_report


def _close(position_id, pnl, closed_at, strategy_id="strat1"):
    pos = {
        "id": position_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": closed_at,
        "strategy_id": strategy_id, "strategy_name": "Test Strategy",
    }
    storage.open_paper_position(pos)
    storage.close_paper_position(
        position_id, 100.0 + pnl, 1700000100000, pnl, pnl / 100.0 * 100,
        "take_profit" if pnl >= 0 else "stop_loss", {}, {}, closed_at,
    )


def test_sparkline_reports_no_data_plainly_when_nothing_closed(test_db):
    now = datetime.now(timezone.utc).isoformat()
    text = weekly_report._daily_pnl_sparkline("2026-01-01T00:00:00+00:00", now)
    assert "No closed trades yet" in text


def test_sparkline_renders_one_bar_per_day_with_real_values(test_db):
    _close("p1", pnl=100.0, closed_at="2026-01-01T12:00:00+00:00")
    _close("p2", pnl=-50.0, closed_at="2026-01-03T12:00:00+00:00")
    text = weekly_report._daily_pnl_sparkline("2026-01-01T00:00:00+00:00", "2026-01-03T23:59:59+00:00")
    assert "lowest $-50" in text
    assert "highest $100" in text
    # 3 calendar days in range -> 3 sparkline characters before the two spaces
    bars = text.split("  ")[0]
    assert len(bars) == 3


def test_generate_weekly_report_includes_the_sparkline_in_its_text(test_db, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(test_db).rsplit("test_sindhu.db", 1)[0])
    _close("p1", pnl=100.0, closed_at=datetime.now(timezone.utc).isoformat())
    result = weekly_report.generate_weekly_report()
    assert "daily PnL" in result["report_text"]


def test_maybe_generate_sends_the_report_to_telegram_when_master_is_on(test_db, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(test_db).rsplit("test_sindhu.db", 1)[0])
    with patch("paper_trading.telegram_bot._master_enabled", return_value=True), \
         patch("paper_trading.telegram_bot._raw_send", return_value=(True, None)) as mock_send:
        result = weekly_report.maybe_generate_weekly_report()

    assert result is not None
    assert result["telegram_sent"] is True
    mock_send.assert_called_once()
    logged = storage.list_telegram_messages(limit=10)
    assert any(m["trigger_type"] == "weekly_report" for m in logged)


def test_maybe_generate_does_not_send_when_telegram_master_is_off(test_db, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(test_db).rsplit("test_sindhu.db", 1)[0])
    with patch("paper_trading.telegram_bot._master_enabled", return_value=False), \
         patch("paper_trading.telegram_bot._raw_send") as mock_send:
        result = weekly_report.maybe_generate_weekly_report()

    assert result is not None
    assert "telegram_sent" not in result
    mock_send.assert_not_called()


def test_maybe_generate_respects_the_existing_7_day_gate_and_only_sends_once(test_db, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(test_db).rsplit("test_sindhu.db", 1)[0])
    with patch("paper_trading.telegram_bot._master_enabled", return_value=True), \
         patch("paper_trading.telegram_bot._raw_send", return_value=(True, None)) as mock_send:
        first = weekly_report.maybe_generate_weekly_report()
        second = weekly_report.maybe_generate_weekly_report()

    assert first is not None
    assert second is None
    mock_send.assert_called_once()


def test_maybe_generate_returns_none_when_feature_toggle_is_off(test_db, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(test_db).rsplit("test_sindhu.db", 1)[0])
    feature_toggles.set_toggle("weekly_report_enabled", False)
    with patch("paper_trading.telegram_bot._raw_send") as mock_send:
        result = weekly_report.maybe_generate_weekly_report()
    assert result is None
    mock_send.assert_not_called()
