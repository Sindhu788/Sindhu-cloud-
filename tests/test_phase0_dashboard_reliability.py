"""Master Task 3, Phase 0.8: dashboard reliability/visibility additions --
today's live trade counter (storage.count_paper_trades_opened_since,
surfaced via engine.status()["trades_today"]) and the One-Click Health
Check (paper_trading/health_check.py).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from data_engine import config as base_config, storage
from paper_trading import health_check
from paper_trading.engine import engine as real_engine


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _open_position(**overrides):
    pos = {
        "id": overrides.pop("id", "pos1"), "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": "strat1", "strategy_name": "Test Strategy",
    }
    pos.update(overrides)
    storage.open_paper_position(pos)
    return pos


def test_count_paper_trades_opened_since_only_counts_after_the_cutoff(test_db):
    _open_position(id="old", created_at="2026-01-01T00:00:00+00:00")
    _open_position(id="new", created_at="2026-06-01T00:00:00+00:00")
    assert storage.count_paper_trades_opened_since("2026-03-01T00:00:00+00:00") == 1
    assert storage.count_paper_trades_opened_since("2025-01-01T00:00:00+00:00") == 2


def test_engine_status_reports_trades_today(test_db):
    now_iso = datetime.now(timezone.utc).isoformat()
    yesterday_iso = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    _open_position(id="today", created_at=now_iso)
    _open_position(id="yesterday", created_at=yesterday_iso)
    status = real_engine.status()
    assert status["trades_today"] == 1


def test_health_check_reports_database_and_engine_ok(test_db):
    with patch("paper_trading.health_check.get_exchange_client") as mock_client_factory:
        mock_client = MagicMock()
        mock_client.get_tickers.return_value = {"BTCUSDT": {"last": 100.0}}
        mock_client_factory.return_value = mock_client
        result = health_check.run_health_check()

    names = {c["name"]: c for c in result["checks"]}
    assert names["Database connection"]["ok"] is True
    assert names["Paper Trading engine"]["ok"] is True
    assert names["Live candle/ticker fetch"]["ok"] is True
    assert result["all_ok"] is True


def test_health_check_reports_exchange_failure_honestly(test_db):
    with patch("paper_trading.health_check.get_exchange_client", side_effect=RuntimeError("exchange down")):
        result = health_check.run_health_check()

    names = {c["name"]: c for c in result["checks"]}
    assert names["Live candle/ticker fetch"]["ok"] is False
    assert "exchange down" in names["Live candle/ticker fetch"]["detail"]
    assert result["all_ok"] is False
