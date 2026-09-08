"""Grand Master Prompt, Phase 5: Sanity Check Alert -- confirmed this
genuinely did not exist for live signals/trades (backtest_engine/
sanity_check.py is a pre-backtest strategy-config check, unrelated).
"""
from data_engine import storage
from paper_trading import sanity_check_alert


def test_normal_position_raises_no_flags():
    position = {"symbol": "BTCUSDT", "entry_price": 100.0, "stop_loss": 98.0,
                "risk_amount": 50.0, "size": 1.0}
    assert sanity_check_alert.check_position(position, book_balance=10000.0) == []


def test_oversized_risk_is_flagged():
    position = {"symbol": "BTCUSDT", "entry_price": 100.0, "stop_loss": 98.0,
                "risk_amount": 2000.0, "size": 1.0}
    reasons = sanity_check_alert.check_position(position, book_balance=10000.0)
    assert any("unusually large" in r for r in reasons)


def test_suspiciously_tight_stop_is_flagged():
    position = {"symbol": "BTCUSDT", "entry_price": 100.0, "stop_loss": 99.99,
                "risk_amount": 10.0, "size": 1.0}
    reasons = sanity_check_alert.check_position(position, book_balance=10000.0)
    assert any("suspiciously tight" in r for r in reasons)


def test_suspiciously_wide_stop_is_flagged():
    position = {"symbol": "BTCUSDT", "entry_price": 100.0, "stop_loss": 10.0,
                "risk_amount": 10.0, "size": 1.0}
    reasons = sanity_check_alert.check_position(position, book_balance=10000.0)
    assert any("suspiciously wide" in r for r in reasons)


def test_nonpositive_size_is_flagged():
    position = {"symbol": "BTCUSDT", "entry_price": 100.0, "stop_loss": 98.0,
                "risk_amount": 10.0, "size": 0}
    reasons = sanity_check_alert.check_position(position, book_balance=10000.0)
    assert any("zero or negative" in r for r in reasons)


def test_check_and_alert_writes_to_paper_alerts_only_when_flagged(test_db):
    good_position = {"id": "p1", "symbol": "BTCUSDT", "entry_price": 100.0, "stop_loss": 98.0,
                      "risk_amount": 50.0, "size": 1.0}
    assert sanity_check_alert.check_and_alert(good_position, "sidA", "Test Strategy", 10000.0) is None
    assert storage.list_paper_alerts(limit=10) == []

    bad_position = {"id": "p2", "symbol": "ETHUSDT", "entry_price": 100.0, "stop_loss": 98.0,
                     "risk_amount": 5000.0, "size": 1.0}
    message = sanity_check_alert.check_and_alert(bad_position, "sidA", "Test Strategy", 10000.0)
    assert message is not None
    alerts = storage.list_paper_alerts(limit=10)
    assert len(alerts) == 1
    assert alerts[0]["alert_type"] == "sanity_check"


def test_check_and_alert_never_raises_on_missing_fields(test_db):
    """A lesson-only book (no strategy_name) or a position missing an
    optional field must never crash this -- it's purely informational."""
    sparse_position = {"id": "p3", "symbol": "BTCUSDT", "entry_price": 100.0, "size": 1.0}
    result = sanity_check_alert.check_and_alert(sparse_position, None, None, 10000.0)
    assert result is None  # nothing to flag with no stop_loss/risk_amount present
