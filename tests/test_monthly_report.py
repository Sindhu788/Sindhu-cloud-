"""Grand Feature Expansion, Phase 3 Feature 13: Monthly Auto-Report
(paper_trading/monthly_report.py) -- same shape as the pre-existing
weekly_report.py, own 30-day interval and own storage table/generation
gate so the two schedules never interfere with each other.
"""

from datetime import datetime, timezone
from unittest.mock import patch

from data_engine import config as base_config, feature_toggles, storage
from paper_trading import monthly_report


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


def test_generate_monthly_report_includes_the_sparkline(test_db, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(test_db).rsplit("test_sindhu.db", 1)[0])
    _close("p1", pnl=100.0, closed_at=datetime.now(timezone.utc).isoformat())
    result = monthly_report.generate_monthly_report()
    assert "Monthly Report" in result["report_text"]
    assert "daily PnL" in result["report_text"]


def test_maybe_generate_sends_to_telegram_when_master_is_on(test_db, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(test_db).rsplit("test_sindhu.db", 1)[0])
    with patch("paper_trading.telegram_bot._master_enabled", return_value=True), \
         patch("paper_trading.telegram_bot._raw_send", return_value=(True, None)) as mock_send:
        result = monthly_report.maybe_generate_monthly_report()

    assert result is not None
    assert result["telegram_sent"] is True
    mock_send.assert_called_once()
    logged = storage.list_telegram_messages(limit=10)
    assert any(m["trigger_type"] == "monthly_report" for m in logged)


def test_maybe_generate_respects_its_own_30_day_gate(test_db, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(test_db).rsplit("test_sindhu.db", 1)[0])
    with patch("paper_trading.telegram_bot._master_enabled", return_value=True), \
         patch("paper_trading.telegram_bot._raw_send", return_value=(True, None)) as mock_send:
        first = monthly_report.maybe_generate_monthly_report()
        second = monthly_report.maybe_generate_monthly_report()
    assert first is not None
    assert second is None
    mock_send.assert_called_once()


def test_monthly_gate_is_independent_of_the_weekly_gate(test_db, monkeypatch):
    """The two report types must never block or interfere with each
    other -- a weekly report having just been generated must not prevent
    (or force) a monthly one, and vice versa."""
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(test_db).rsplit("test_sindhu.db", 1)[0])
    from paper_trading import weekly_report
    with patch("paper_trading.telegram_bot._master_enabled", return_value=True), \
         patch("paper_trading.telegram_bot._raw_send", return_value=(True, None)):
        weekly_report.maybe_generate_weekly_report()
        monthly_result = monthly_report.maybe_generate_monthly_report()
    assert monthly_result is not None  # not blocked by the weekly report having just run


def test_returns_none_when_feature_toggle_is_off(test_db, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(test_db).rsplit("test_sindhu.db", 1)[0])
    feature_toggles.set_toggle("monthly_report_enabled", False)
    with patch("paper_trading.telegram_bot._raw_send") as mock_send:
        result = monthly_report.maybe_generate_monthly_report()
    assert result is None
    mock_send.assert_not_called()
