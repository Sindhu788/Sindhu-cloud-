"""Batch 4, Task 5 -- System Maturity Level. A real Level 1-5 indicator
computed only from data the system already has, never manually set.
Verifies each rung of the ladder against representative real data states,
using the same storage functions (open/close_paper_position,
create/finalize_evolution_comparison, log_telegram_message) the real
engine and evolution loop use -- not mocks of the maturity module itself.
"""

from datetime import datetime, timezone

import pytest

from data_engine import storage
from knowledge_engine import maturity


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _close_trades(strategy_id, wins, losses):
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    i = 0
    for _ in range(wins):
        i += 1
        pid = f"{strategy_id}-w{i}"
        storage.open_paper_position({
            "id": pid, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
            "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0, "entry_time": now_ms,
            "created_at": _now_iso(), "strategy_id": strategy_id, "strategy_name": strategy_id,
        })
        storage.close_paper_position(pid, exit_price=110.0, exit_time=now_ms, pnl=10.0, pnl_pct=10.0,
                                      exit_reason="take_profit", lifecycle={}, reflection={}, closed_at=_now_iso(),
                                      book_key=strategy_id)
    for _ in range(losses):
        i += 1
        pid = f"{strategy_id}-l{i}"
        storage.open_paper_position({
            "id": pid, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
            "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0, "entry_time": now_ms,
            "created_at": _now_iso(), "strategy_id": strategy_id, "strategy_name": strategy_id,
        })
        storage.close_paper_position(pid, exit_price=95.0, exit_time=now_ms, pnl=-5.0, pnl_pct=-5.0,
                                      exit_reason="stop_loss", lifecycle={}, reflection={}, closed_at=_now_iso(),
                                      book_key=strategy_id)


def test_level_1_when_no_strategy_has_25_trades(test_db):
    _close_trades("strat1", wins=5, losses=5)  # only 10 trades total
    result = maturity.compute_maturity_level()
    assert result["level"] == 1
    assert result["level_name"] == "Bootstrapping"


def test_level_2_when_25plus_trades_but_no_evolution_gate_completion(test_db):
    _close_trades("strat1", wins=10, losses=15)  # 25 trades, no gate activity
    result = maturity.compute_maturity_level()
    assert result["level"] == 2
    assert result["metrics"]["strategies_with_25plus_trades"] == 1
    assert result["metrics"]["evolution_gate_completions"] == 0


def test_level_3_when_evolution_gate_has_completed(test_db):
    _close_trades("strat1", wins=10, losses=15)
    cid = storage.create_evolution_comparison("base1", "parent1", "child1", 100, {"trades": 100}, _now_iso())
    storage.finalize_evolution_comparison(cid, {"trades": 100}, "improved", False, _now_iso())
    result = maturity.compute_maturity_level()
    assert result["level"] == 3
    assert result["metrics"]["evolution_gate_completions"] == 1


def test_level_3_not_reached_if_comparison_still_pending(test_db):
    """A comparison created but not yet finalized (after_json/verdict
    still NULL) must not count -- the gate hasn't actually judged
    anything yet."""
    _close_trades("strat1", wins=10, losses=15)
    storage.create_evolution_comparison("base1", "parent1", "child1", 100, {"trades": 100}, _now_iso())
    result = maturity.compute_maturity_level()
    assert result["level"] == 2


def test_level_4_when_one_strategy_is_statistically_proven_and_signal_sent(test_db):
    _close_trades("strat1", wins=23, losses=2)  # 25 trades, 92% win rate -- reliable_good
    cid = storage.create_evolution_comparison("base1", "parent1", "child1", 100, {}, _now_iso())
    storage.finalize_evolution_comparison(cid, {}, "improved", False, _now_iso())
    storage.log_telegram_message("pos1", "strat1", "strat1", "manual", "text", True, None, _now_iso())

    result = maturity.compute_maturity_level()
    assert result["level"] == 4
    assert result["metrics"]["strategies_statistically_proven_positive"] == 1


def test_level_4_not_reached_without_a_sent_signal(test_db):
    _close_trades("strat1", wins=23, losses=2)
    cid = storage.create_evolution_comparison("base1", "parent1", "child1", 100, {}, _now_iso())
    storage.finalize_evolution_comparison(cid, {}, "improved", False, _now_iso())
    result = maturity.compute_maturity_level()
    assert result["level"] == 3


def test_level_5_when_two_strategies_proven_and_recent_signals(test_db):
    _close_trades("strat1", wins=23, losses=2)
    _close_trades("strat2", wins=24, losses=1)
    cid = storage.create_evolution_comparison("base1", "parent1", "child1", 100, {}, _now_iso())
    storage.finalize_evolution_comparison(cid, {}, "improved", False, _now_iso())
    storage.log_telegram_message("pos1", "strat1", "strat1", "manual", "text", True, None, _now_iso())

    result = maturity.compute_maturity_level()
    assert result["level"] == 5
    assert result["metrics"]["strategies_statistically_proven_positive"] == 2


def test_level_never_rounds_up_when_only_one_proven_strategy(test_db):
    """Level 5 requires 2 statistically proven strategies -- one is not
    enough, no matter how good its numbers are."""
    _close_trades("strat1", wins=23, losses=2)
    cid = storage.create_evolution_comparison("base1", "parent1", "child1", 100, {}, _now_iso())
    storage.finalize_evolution_comparison(cid, {}, "improved", False, _now_iso())
    storage.log_telegram_message("pos1", "strat1", "strat1", "manual", "text", True, None, _now_iso())
    result = maturity.compute_maturity_level()
    assert result["level"] == 4  # not 5


def test_lessons_book_is_never_counted_as_a_strategy(test_db):
    """The synthetic __lessons__ book (trades not tied to any specific
    strategy) must never inflate the strategy count."""
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    for i in range(30):
        pid = f"lesson-trade-{i}"
        storage.open_paper_position({
            "id": pid, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
            "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0, "entry_time": now_ms,
            "created_at": _now_iso(), "strategy_id": None, "strategy_name": None,
        })
        storage.close_paper_position(pid, exit_price=110.0, exit_time=now_ms, pnl=10.0, pnl_pct=10.0,
                                      exit_reason="take_profit", lifecycle={}, reflection={}, closed_at=_now_iso(),
                                      book_key=None)
    metrics = maturity.compute_maturity_metrics()
    assert metrics["total_strategy_books"] == 0
    assert metrics["strategies_with_25plus_trades"] == 0


def test_metrics_and_criteria_text_are_always_present(test_db):
    result = maturity.compute_maturity_level()
    assert isinstance(result["criteria_text"], str) and result["criteria_text"]
    assert result["next_level"] == 2
    assert result["next_level_criteria_text"]
