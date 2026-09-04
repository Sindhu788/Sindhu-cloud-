"""Master Task 3, Phase 2 (Challenge Mode Part 1) -- the new analysis
functions in paper_trading/challenge_analysis.py: difficulty rating,
best/worst/likely range, adaptive risk suggestion, risk-level warning,
give-up-point check, loss-streak impact, best historical period finder,
historical replay, and strategy rotation suggestion.
"""

from datetime import datetime, timedelta, timezone

import pytest

from data_engine import config as base_config, storage
from paper_trading import challenge_analysis, pattern_stats


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _iso(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _trade(pid, strategy_id, symbol, pnl, risk_amount, closed_days_ago, market_state=None,
           entry_time_ms=1700000000000):
    storage.open_paper_position({
        "id": pid, "exchange": "binance", "symbol": symbol, "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": risk_amount,
        "entry_time": entry_time_ms, "created_at": _iso(closed_days_ago),
        "strategy_id": strategy_id, "strategy_name": strategy_id, "market_state": market_state,
    })
    storage.close_paper_position(
        pid, 100.0, entry_time_ms + 30 * 60000, pnl, pnl, "take_profit", {}, {}, _iso(closed_days_ago),
    )


# --------------------------------------------------------------- difficulty_rating

def test_difficulty_easy_when_required_pace_is_a_fraction_of_real_pace():
    assert challenge_analysis.difficulty_rating(0.2, 1.0) == "Easy"


def test_difficulty_extremely_unlikely_with_no_real_pace():
    assert challenge_analysis.difficulty_rating(1.0, None) == "Extremely Unlikely"
    assert challenge_analysis.difficulty_rating(1.0, 0.0) == "Extremely Unlikely"


def test_difficulty_extremely_unlikely_far_beyond_real_pace():
    assert challenge_analysis.difficulty_rating(10.0, 1.0) == "Extremely Unlikely"


def test_difficulty_moderate_and_hard_bands():
    assert challenge_analysis.difficulty_rating(0.9, 1.0) == "Moderate"
    assert challenge_analysis.difficulty_rating(1.8, 1.0) == "Hard"


# --------------------------------------------------------------- best_worst_likely_range

def test_best_worst_likely_range_with_no_history(test_db):
    result = challenge_analysis.best_worst_likely_range(1000.0, 2000.0, 30)
    assert result["best_case"] is None


def test_best_worst_likely_range_spans_real_combinations(test_db):
    for i in range(30):
        _trade(f"good{i}", "strat_good", "BTCUSDT", 20.0, 10.0, closed_days_ago=1)
    for i in range(30):
        _trade(f"bad{i}", "strat_bad", "ETHUSDT", -5.0, 10.0, closed_days_ago=1)
    result = challenge_analysis.best_worst_likely_range(1000.0, 1100.0, 30)
    assert result["best_case"]["strategy_name"] == "strat_good"
    assert result["worst_case"]["strategy_name"] == "strat_bad"


# --------------------------------------------------------------- suggest_adaptive_risk_pct / risk_level_warning

def test_suggest_adaptive_risk_pct_none_without_positive_edge():
    assert challenge_analysis.suggest_adaptive_risk_pct(1.0, avg_r_multiple=0, trades_per_day=1, current_risk_pct=1.0) is None
    assert challenge_analysis.suggest_adaptive_risk_pct(1.0, avg_r_multiple=None, trades_per_day=1, current_risk_pct=1.0) is None


def test_suggest_adaptive_risk_pct_computes_a_specific_number():
    result = challenge_analysis.suggest_adaptive_risk_pct(
        required_daily_rate_pct=2.0, avg_r_multiple=2.0, trades_per_day=1.0, current_risk_pct=1.0,
    )
    assert result["suggested_risk_pct"] == 1.0  # required 2%/day = avg_r(2) * risk(1%) * freq(1/day)


def test_risk_level_warning_flags_a_large_increase():
    result = challenge_analysis.risk_level_warning(suggested_risk_pct=3.0, current_risk_pct=1.0)
    assert result["warn"] is True


def test_risk_level_warning_silent_for_a_small_increase():
    result = challenge_analysis.risk_level_warning(suggested_risk_pct=1.2, current_risk_pct=1.0)
    assert result["warn"] is False


def test_risk_level_warning_flags_above_max_sane_ceiling():
    result = challenge_analysis.risk_level_warning(suggested_risk_pct=8.0, current_risk_pct=1.0)
    assert result["warn"] is True
    assert "beyond any reasonable ceiling" in result["messages"][0]


# --------------------------------------------------------------- give_up_point_check

def test_give_up_point_implausible_when_deadline_passed():
    result = challenge_analysis.give_up_point_check(remaining_days=0, best_case_days_to_target=5)
    assert result["implausible"] is True


def test_give_up_point_implausible_when_best_case_exceeds_remaining_time():
    result = challenge_analysis.give_up_point_check(remaining_days=5, best_case_days_to_target=50)
    assert result["implausible"] is True


def test_give_up_point_not_implausible_when_still_reachable():
    result = challenge_analysis.give_up_point_check(remaining_days=50, best_case_days_to_target=5)
    assert result["implausible"] is False


# --------------------------------------------------------------- loss_streak_impact

def test_loss_streak_impact_too_few_trades(test_db):
    for i in range(3):
        _trade(f"t{i}", "s1", "BTCUSDT", -10.0, 10.0, closed_days_ago=1)
    result = challenge_analysis.loss_streak_impact("s1", "BTCUSDT", start_amount=1000.0)
    assert result["checked"] is False


def test_loss_streak_impact_finds_the_real_worst_streak(test_db):
    # 3 losses, 1 win, 4 losses (the real worst run), then wins to reach MIN_SAMPLE_SIZE.
    day = 30
    for i in range(3):
        _trade(f"l1_{i}", "s1", "BTCUSDT", -10.0, 10.0, closed_days_ago=day); day -= 1
    _trade("w1", "s1", "BTCUSDT", 20.0, 10.0, closed_days_ago=day); day -= 1
    for i in range(4):
        _trade(f"l2_{i}", "s1", "BTCUSDT", -10.0, 10.0, closed_days_ago=day); day -= 1
    for i in range(pattern_stats.MIN_SAMPLE_SIZE):
        _trade(f"w2_{i}", "s1", "BTCUSDT", 20.0, 10.0, closed_days_ago=day); day -= 1

    result = challenge_analysis.loss_streak_impact("s1", "BTCUSDT", start_amount=1000.0)
    assert result["checked"] is True
    assert result["worst_historical_losing_streak"] == 4


# --------------------------------------------------------------- find_best_historical_period

def test_find_best_historical_period_none_without_history(test_db):
    assert challenge_analysis.find_best_historical_period("s1", "BTCUSDT", window_days=7) is None


def test_find_best_historical_period_finds_a_real_window(test_db):
    for i in range(10):
        _trade(f"t{i}", "s1", "BTCUSDT", 30.0, 10.0, closed_days_ago=10 - i)
    result = challenge_analysis.find_best_historical_period("s1", "BTCUSDT", window_days=7)
    assert result is not None
    assert result["growth_multiple"] > 1.0
    assert result["trades_in_window"] >= 2


# --------------------------------------------------------------- replay_challenge

def test_replay_challenge_computes_a_real_ending_amount(test_db):
    for i in range(10):
        _trade(f"t{i}", "s1", "BTCUSDT", 20.0, 10.0, closed_days_ago=5 - i * 0.4)
    result = challenge_analysis.replay_challenge(1000.0, 1050.0, days_ago_started=10, strategy_id="s1", symbol="BTCUSDT")
    assert result["trades_counted"] > 0
    assert result["ending_amount"] > 1000.0


def test_replay_challenge_zero_trades_leaves_amount_unchanged(test_db):
    result = challenge_analysis.replay_challenge(1000.0, 2000.0, days_ago_started=5, strategy_id="ghost", symbol="XXXUSDT")
    assert result["trades_counted"] == 0
    assert result["ending_amount"] == 1000.0
    assert result["would_have_reached_target"] is False


# --------------------------------------------------------------- strategy_rotation_suggestion

def test_strategy_rotation_needs_at_least_two_strategies(test_db):
    for i in range(pattern_stats.MIN_SAMPLE_SIZE):
        _trade(f"t{i}", "only_one", "BTCUSDT", 10.0, 10.0, closed_days_ago=1, market_state="trending")
    result = challenge_analysis.strategy_rotation_suggestion()
    assert result["suggestion"] is None


def test_strategy_rotation_suggests_complementary_strategies(test_db):
    for i in range(pattern_stats.MIN_SAMPLE_SIZE):
        _trade(f"a{i}", "strat_a", "BTCUSDT", 10.0, 10.0, closed_days_ago=1, market_state="trending")
    for i in range(pattern_stats.MIN_SAMPLE_SIZE):
        _trade(f"b{i}", "strat_b", "ETHUSDT", 10.0, 10.0, closed_days_ago=1, market_state="ranging")

    result = challenge_analysis.strategy_rotation_suggestion()
    assert result["suggestion"] is not None
    states = {result["suggestion"]["strategy_a"]["best_in"], result["suggestion"]["strategy_b"]["best_in"]}
    assert states == {"trending", "ranging"}


def test_strategy_rotation_no_suggestion_when_all_best_in_same_state(test_db):
    for i in range(pattern_stats.MIN_SAMPLE_SIZE):
        _trade(f"a{i}", "strat_a", "BTCUSDT", 10.0, 10.0, closed_days_ago=1, market_state="trending")
    for i in range(pattern_stats.MIN_SAMPLE_SIZE):
        _trade(f"b{i}", "strat_b", "ETHUSDT", 5.0, 10.0, closed_days_ago=1, market_state="trending")

    result = challenge_analysis.strategy_rotation_suggestion()
    assert result["suggestion"] is None
