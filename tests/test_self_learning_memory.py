"""Master Task 3, Phase 1.9/1.11: self_learning_engine/memory.py + the
underlying data_engine.storage self_learning_attempts persistence.
"""

from datetime import datetime, timezone

import pytest

from backtest_engine.strategy_config import Condition, SLTPSpec, StrategyConfig
from backtest_engine import strategy_library as lib
from data_engine import storage
from self_learning_engine import memory


@pytest.fixture(autouse=True)
def isolated_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))


def _now():
    return datetime.now(timezone.utc).isoformat()


def test_record_and_list_round_trip(test_db):
    memory.record_outcome(
        "attempt1", ["liquidity", "volume"], ["order_block", "poc"], 0,
        "rejected", "profit factor below 1.0 in the validation period", _now(),
    )
    history = memory.attempt_history()
    assert len(history) == 1
    assert history[0]["outcome"] == "rejected"
    assert history[0]["dna_combo"] == ["liquidity", "volume"]


def test_has_been_rejected_before_true_after_a_rejection(test_db):
    memory.record_outcome("a1", ["liquidity", "volume"], ["order_block", "poc"], 0, "rejected", "no edge", _now())
    assert memory.has_been_rejected_before(["liquidity", "volume"], ["order_block", "poc"]) is True


def test_has_been_rejected_before_false_for_a_never_tried_combo(test_db):
    assert memory.has_been_rejected_before(["session", "risk"], ["session_open"]) is False


def test_different_concepts_for_the_same_combo_are_not_treated_as_the_same_attempt(test_db):
    memory.record_outcome("a1", ["liquidity", "volume"], ["order_block", "poc"], 0, "rejected", "no edge", _now())
    # Same DNA combo, but a DIFFERENT concept was drawn (variant cycling) --
    # this is a genuinely different candidate, not a repeat.
    assert memory.has_been_rejected_before(["liquidity", "volume"], ["support", "poc"]) is False


def test_attempt_count_for_combo_counts_regardless_of_outcome(test_db):
    memory.record_outcome("a1", ["trend", "momentum"], ["ema", "rsi"], 0, "rejected", "no edge", _now())
    memory.record_outcome("a2", ["trend", "momentum"], ["ema", "macd"], 1, "accepted", "passed both OOS periods", _now())
    assert memory.attempt_count_for_combo(["trend", "momentum"]) == 2


def _make_strategy(name, concepts_used):
    cfg = StrategyConfig(
        name=name, timeframes={"entry": "5m"},
        entry_conditions=[Condition(type="concept", name=concepts_used[0])],
        concepts_used=concepts_used,
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0,
    )
    return lib.create(cfg)


def test_check_duplicate_against_library_finds_a_near_identical_strategy(test_db):
    _make_strategy("Existing Strategy", ["order_block", "poc", "liquidity_sweep"])
    warnings = memory.check_duplicate_against_library(["order_block", "poc", "liquidity_sweep"])
    assert len(warnings) == 1
    assert warnings[0]["strategy_name"] == "Existing Strategy"


def test_check_duplicate_against_library_clean_for_a_genuinely_new_combo(test_db):
    _make_strategy("Existing Strategy", ["order_block", "poc"])
    warnings = memory.check_duplicate_against_library(["session_open", "candle_break"])
    assert warnings == []
