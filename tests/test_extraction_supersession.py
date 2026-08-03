"""Batch 5, Task 2 -- flagging paper trading data affected by incomplete
extraction. When Task 1's re-extraction produces a genuinely different
config for a strategy, everything traded before that point was traded
under an incomplete understanding and must be marked superseded: never
deleted, clearly warned about, and never blended into "corrected"
statistics going forward.
"""

from datetime import datetime, timezone

import pytest

from data_engine import storage
from paper_trading import strategy_profile


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _close_trade(strategy_id, pnl, pos_id, strategy_version):
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    storage.open_paper_position({
        "id": pos_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0, "entry_time": now_ms,
        "created_at": _now_iso(), "strategy_id": strategy_id, "strategy_name": strategy_id,
        "strategy_version": strategy_version,
    })
    storage.close_paper_position(
        pos_id, exit_price=100.0 + pnl, exit_time=now_ms, pnl=pnl, pnl_pct=pnl,
        exit_reason="take_profit", lifecycle={}, reflection={}, closed_at=_now_iso(),
        book_key=strategy_id,
    )


def test_correction_is_recorded_and_retrievable(test_db):
    assert storage.get_latest_extraction_correction("strat1") is None
    storage.save_strategy_extraction_correction(
        "strat1", corrected_at_version=3, previous_expected_count=19, previous_captured_count=9,
        new_expected_count=27, new_captured_count=25, reason="sentence-level re-extraction", now_iso=_now_iso(),
    )
    correction = storage.get_latest_extraction_correction("strat1")
    assert correction["corrected_at_version"] == 3
    assert correction["previous_captured_count"] == 9
    assert correction["new_captured_count"] == 25


def test_only_the_most_recent_correction_is_returned(test_db):
    storage.save_strategy_extraction_correction(
        "strat1", 2, 10, 5, 15, 12, "first fix", "2025-01-01T00:00:00+00:00",
    )
    storage.save_strategy_extraction_correction(
        "strat1", 4, 15, 12, 20, 19, "second fix", "2025-06-01T00:00:00+00:00",
    )
    correction = storage.get_latest_extraction_correction("strat1")
    assert correction["corrected_at_version"] == 4
    assert correction["reason"] == "second fix"


def test_versioned_stats_excludes_trades_before_the_correction(test_db):
    _close_trade("strat1", pnl=10.0, pos_id="old1", strategy_version=1)
    _close_trade("strat1", pnl=-5.0, pos_id="old2", strategy_version=2)
    _close_trade("strat1", pnl=20.0, pos_id="new1", strategy_version=3)

    all_stats = storage.get_versioned_paper_stats("strat1")
    assert all_stats["closed_count"] == 3

    corrected_only = storage.get_versioned_paper_stats("strat1", min_version=3)
    assert corrected_only["closed_count"] == 1
    assert corrected_only["realized_pnl_total"] == 20.0


def test_old_trade_history_is_never_deleted_by_marking_a_correction(test_db):
    _close_trade("strat1", pnl=10.0, pos_id="old1", strategy_version=1)
    storage.save_strategy_extraction_correction("strat1", 2, 10, 5, 15, 12, "fix", _now_iso())

    trades = storage.list_paper_closed_trades_ordered(strategy_id="strat1")
    assert len(trades) == 1
    assert trades[0]["pnl"] == 10.0


def test_telegram_signals_for_superseded_positions_are_counted(test_db):
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    storage.open_paper_position({
        "id": "old_pos", "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0, "entry_time": now_ms,
        "created_at": _now_iso(), "strategy_id": "strat1", "strategy_name": "strat1",
        "strategy_version": 1,
    })
    storage.open_paper_position({
        "id": "new_pos", "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0, "entry_time": now_ms,
        "created_at": _now_iso(), "strategy_id": "strat1", "strategy_name": "strat1",
        "strategy_version": 3,
    })
    storage.log_telegram_message("old_pos", "strat1", "strat1", "manual", "text", True, None, _now_iso())
    storage.log_telegram_message("new_pos", "strat1", "strat1", "manual", "text", True, None, _now_iso())

    count = storage.count_telegram_signals_for_superseded_positions("strat1", corrected_at_version=3)
    assert count == 1  # only the pre-correction (version 1) position's signal


def test_failed_signal_sends_are_never_counted(test_db):
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    storage.open_paper_position({
        "id": "old_pos", "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0, "entry_time": now_ms,
        "created_at": _now_iso(), "strategy_id": "strat1", "strategy_name": "strat1",
        "strategy_version": 1,
    })
    storage.log_telegram_message("old_pos", "strat1", "strat1", "manual", "text", False, "failed", _now_iso())
    count = storage.count_telegram_signals_for_superseded_positions("strat1", corrected_at_version=3)
    assert count == 0


def test_no_correction_means_no_supersession_marker(test_db, monkeypatch, tmp_path):
    from backtest_engine import strategy_library as lib
    from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))
    cfg = StrategyConfig(
        name="Strat", timeframes={"entry": "1h"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30.0)],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    )
    strategy_id = lib.create(cfg)
    profile = strategy_profile.get_strategy_profile(strategy_id, "binance")
    assert profile["supersession"] is None


def test_supersession_appears_in_strategy_profile_with_real_counts(test_db, monkeypatch, tmp_path):
    from backtest_engine import strategy_library as lib
    from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))
    cfg = StrategyConfig(
        name="Strat", timeframes={"entry": "1h"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30.0)],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    )
    strategy_id = lib.create(cfg)

    _close_trade(strategy_id, pnl=10.0, pos_id="old1", strategy_version=1)
    _close_trade(strategy_id, pnl=20.0, pos_id="new1", strategy_version=2)
    storage.save_strategy_extraction_correction(
        strategy_id, corrected_at_version=2, previous_expected_count=19, previous_captured_count=9,
        new_expected_count=27, new_captured_count=25, reason="sentence-level re-extraction", now_iso=_now_iso(),
    )

    profile = strategy_profile.get_strategy_profile(strategy_id, "binance")
    supersession = profile["supersession"]
    assert supersession is not None
    assert supersession["corrected_at_version"] == 2
    assert supersession["superseded_trade_count"] == 1
    assert supersession["corrected_stats"]["closed_count"] == 1
    assert supersession["corrected_stats"]["realized_pnl_total"] == 20.0
