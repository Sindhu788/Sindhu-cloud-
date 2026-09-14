"""Grand Master Batch, Phase 5 Item 8 -- "Frozen" vs "Active" learning
toggle per strategy. Stops Evolution mutation and Self-Learning lesson
auto-apply for ONE strategy without touching any other strategy or
paper trading itself.
"""

from datetime import datetime, timezone

import pytest

from data_engine import config as base_config, storage
from evolution_engine import mutator, generation_manager
from evolution_engine.governor import Governor
from paper_trading import lesson_auto_apply, learning_freeze

CONFIG = {"risk_reward": 2.0, "risk_pct": 1.0, "entry_timeframe": "5m"}


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def test_starts_active_not_frozen():
    assert learning_freeze.is_frozen("BOT_S001") is False


def test_set_and_clear_freeze():
    learning_freeze.set_frozen("BOT_S001", True)
    assert learning_freeze.is_frozen("BOT_S001") is True
    learning_freeze.set_frozen("BOT_S001", False)
    assert learning_freeze.is_frozen("BOT_S001") is False


def test_freezing_one_strategy_never_affects_another():
    learning_freeze.set_frozen("BOT_S001", True)
    assert learning_freeze.is_frozen("BOT_S002") is False


def test_frozen_strategy_is_never_mutated(test_db):
    strategy_id = generation_manager.create_new_strategy_lineage(
        "Test", CONFIG, ["trend"], "sindhu_deterministic", False, "seed", _now_iso(), base_id="BOT_S001",
    )
    storage.update_bot_strategy_result(
        strategy_id, evolution_score=50.0, score_breakdown={"_final_score": 50.0},
        backtest_summary={"trades": 150, "win_rate": 50.0, "total_pnl": 100.0,
                           "avg_profit_factor": 1.5, "max_drawdown_pct": 5.0},
        now_iso=_now_iso(),
    )
    learning_freeze.set_frozen("BOT_S001", True)

    # Would normally mutate (150 >= 100 trades) but is frozen.
    new_id = mutator.mutate_strategy("BOT_S001", Governor(), _now_iso())
    assert new_id is None
    # Even an explicit force must never mutate a frozen strategy.
    new_id_forced = mutator.mutate_strategy("BOT_S001", Governor(), _now_iso(), force=True)
    assert new_id_forced is None
    assert storage.latest_generation_for_base("BOT_S001")["generation"] == 1


def _closed_trade(pos_id, strategy_id, pnl):
    pos = {
        "id": pos_id, "strategy_id": strategy_id, "strategy_name": strategy_id,
        "symbol": "BTCUSDT", "direction": "long", "entry_price": 100.0,
        "stop_loss": 95.0, "take_profit": 110.0, "market_state": "trending_up",
        "session": "london", "entry_reason": "test", "exchange": "binance",
        "size": 1.0, "risk_amount": 5.0, "entry_time": 0,
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    storage.open_paper_position(pos)
    storage.close_paper_position(
        pos_id, 101.0 if pnl > 0 else 99.0, 0, pnl, pnl, "take_profit", {}, {},
        "2026-01-02T00:00:00+00:00", book_key=strategy_id,
    )


def test_frozen_strategy_pattern_is_never_promoted(test_db):
    # 30 real closed trades, 25 wins -- a clearly statistically reliable
    # pattern that would normally be promoted.
    for i in range(30):
        _closed_trade(f"pos{i}", "strat1", 1.0 if i < 25 else -1.0)

    learning_freeze.set_frozen("strat1", True)
    lesson_auto_apply.promote_candidates()
    assert storage.list_paper_auto_lessons(active_only=True) == []


def test_unfrozen_strategy_pattern_is_still_promoted_normally(test_db):
    # Same real setup, but NOT frozen -- confirms freezing strat1 above
    # doesn't accidentally break the normal promotion path for everyone.
    for i in range(30):
        _closed_trade(f"pos{i}", "strat2", 1.0 if i < 25 else -1.0)

    lesson_auto_apply.promote_candidates()
    assert len(storage.list_paper_auto_lessons(active_only=True)) == 1
