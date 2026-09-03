"""Grand Feature Expansion, Phase 5 Feature 2: Time-of-Day Trading Filter
(paper_trading/time_of_day_filter.py) -- blocks NEW entries during a
configured UTC hour window. Genuinely distinct from Phase 3's
time_of_day_performance_breakdown (a read-only stats query, never read by
the trading loop) -- this is a real, live gate wired into
risk_manager.evaluate().
"""

from datetime import datetime, timezone

from paper_trading import config as pt_config, risk_manager, time_of_day_filter


def _settings(**overrides):
    s = dict(pt_config._DEFAULTS)
    s.update(overrides)
    return s


def test_disabled_by_default_never_blocks():
    now = datetime(2026, 1, 1, 3, 0, tzinfo=timezone.utc)
    assert time_of_day_filter.is_blocked_now(now=now, settings=_settings()) is False


def test_zero_width_window_means_always_off():
    settings = _settings(time_filter_enabled=True, time_filter_block_start_utc="05:00", time_filter_block_end_utc="05:00")
    now = datetime(2026, 1, 1, 5, 0, tzinfo=timezone.utc)
    assert time_of_day_filter.is_blocked_now(now=now, settings=settings) is False


def test_same_day_window_blocks_inside_and_allows_outside():
    settings = _settings(time_filter_enabled=True, time_filter_block_start_utc="13:00", time_filter_block_end_utc="14:00")
    inside = datetime(2026, 1, 1, 13, 30, tzinfo=timezone.utc)
    outside = datetime(2026, 1, 1, 15, 0, tzinfo=timezone.utc)
    assert time_of_day_filter.is_blocked_now(now=inside, settings=settings) is True
    assert time_of_day_filter.is_blocked_now(now=outside, settings=settings) is False


def test_overnight_window_wraps_around_midnight():
    settings = _settings(time_filter_enabled=True, time_filter_block_start_utc="23:00", time_filter_block_end_utc="07:00")
    late_night = datetime(2026, 1, 1, 23, 30, tzinfo=timezone.utc)
    early_morning = datetime(2026, 1, 2, 5, 0, tzinfo=timezone.utc)
    midday = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert time_of_day_filter.is_blocked_now(now=late_night, settings=settings) is True
    assert time_of_day_filter.is_blocked_now(now=early_morning, settings=settings) is True
    assert time_of_day_filter.is_blocked_now(now=midday, settings=settings) is False


def test_end_is_exclusive():
    settings = _settings(time_filter_enabled=True, time_filter_block_start_utc="13:00", time_filter_block_end_utc="14:00")
    exactly_end = datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc)
    assert time_of_day_filter.is_blocked_now(now=exactly_end, settings=settings) is False


def test_risk_manager_rejects_a_trade_during_the_blocked_window(test_db, monkeypatch):
    settings = _settings(time_filter_enabled=True, time_filter_block_start_utc="00:00", time_filter_block_end_utc="23:59")
    candidate = {"stop_loss": 95.0, "entry_price": 100.0}
    approved, reason, size, risk_amount = risk_manager.evaluate("strat1", "BTCUSDT", candidate, settings)
    assert approved is False
    assert "time-of-day" in reason


def test_risk_manager_allows_a_trade_outside_the_blocked_window(test_db):
    settings = _settings(time_filter_enabled=False)
    candidate = {"stop_loss": 95.0, "entry_price": 100.0}
    approved, reason, size, risk_amount = risk_manager.evaluate("strat1", "BTCUSDT", candidate, settings)
    assert approved is True
