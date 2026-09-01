"""Part 3 of the Telegram/Multi-Strategy/Challenge-Mode task: Challenge
Mode's full redesign (Levels 1 & 2 -- paper_trading/challenge_analysis.py).

Verification requirements this file demonstrates with real stored data:
  - Confidence labeling correctly marks a low-sample combination as
    unproven (Wilson gate, reused not reimplemented).
  - The consistency check correctly flags a combination whose results are
    concentrated in one time window.
  - The system refuses an unrealistic target while still offering a
    genuinely achievable alternative from the same real data.
  - Per-strategy/per-coin/per-combination breakdown is computed from real
    stored trades only.
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


def _trade(pid, strategy_id, strategy_name, symbol, pnl, risk_amount, closed_days_ago,
           entry_time_ms=1700000000000, duration_min=30):
    storage.open_paper_position({
        "id": pid, "exchange": "binance", "symbol": symbol, "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": risk_amount,
        "entry_time": entry_time_ms, "created_at": _iso(closed_days_ago),
        "strategy_id": strategy_id, "strategy_name": strategy_name,
    })
    storage.close_paper_position(
        pid, 100.0, entry_time_ms + duration_min * 60000, pnl, pnl, "take_profit", {}, {},
        _iso(closed_days_ago),
    )


# --------------------------------------------------------------- Level 1: granular breakdown

def test_granular_breakdown_is_computed_per_strategy_per_coin_and_per_combination(test_db):
    for i in range(5):
        _trade(f"a{i}", "stratA", "Strategy A", "BTCUSDT", 5.0, 5.0, closed_days_ago=10 - i)
    for i in range(3):
        _trade(f"b{i}", "stratB", "Strategy B", "ETHUSDT", -2.0, 5.0, closed_days_ago=5 - i)

    breakdown = challenge_analysis.granular_breakdown()

    by_strategy = {r["strategy_id"]: r for r in breakdown["by_strategy"]}
    assert by_strategy["stratA"]["total_closed_trades"] == 5
    assert by_strategy["stratA"]["win_rate_pct"] == 100.0
    assert by_strategy["stratB"]["total_closed_trades"] == 3
    assert by_strategy["stratB"]["win_rate_pct"] == 0.0

    by_coin = {r["symbol"]: r for r in breakdown["by_coin"]}
    assert by_coin["BTCUSDT"]["total_closed_trades"] == 5
    assert by_coin["ETHUSDT"]["total_closed_trades"] == 3

    combos = {(r["strategy_id"], r["symbol"]): r for r in breakdown["by_combination"]}
    assert combos[("stratA", "BTCUSDT")]["total_pnl"] == pytest.approx(25.0)
    assert combos[("stratB", "ETHUSDT")]["total_pnl"] == pytest.approx(-6.0)

    assert breakdown["best_combination"]["strategy_id"] == "stratA"


def test_metrics_include_profit_factor_drawdown_and_avg_duration(test_db):
    _trade("w1", "stratC", "Strategy C", "BTCUSDT", 10.0, 5.0, closed_days_ago=5, duration_min=60)
    _trade("l1", "stratC", "Strategy C", "BTCUSDT", -4.0, 5.0, closed_days_ago=4, duration_min=20)
    breakdown = challenge_analysis.granular_breakdown()
    combo = breakdown["by_combination"][0]
    assert combo["profit_factor"] == pytest.approx(10.0 / 4.0, rel=1e-6)
    assert combo["avg_trade_duration_minutes"] == pytest.approx(40.0)
    assert combo["max_drawdown"] >= 0


# --------------------------------------------------------------- Level 2: confidence labeling (Wilson gate)

def test_low_sample_combination_is_labeled_unproven_even_with_perfect_raw_win_rate(test_db):
    # Only 5 trades, all wins -- a perfect RAW win rate, but nowhere near
    # pattern_stats.MIN_SAMPLE_SIZE (25). Must be labeled unproven, not
    # presented as a confirmed edge.
    for i in range(5):
        _trade(f"u{i}", "stratLow", "Low Sample Strategy", "SOLUSDT", 5.0, 5.0, closed_days_ago=5 - i)

    result = challenge_analysis.recommend_paths(start_amount=100.0, target_amount=110.0, days=30)
    path = next(p for p in result["paths"] if p["strategy_id"] == "stratLow")
    assert path["sample_size"] == 5
    assert path["win_rate_pct"] == 100.0
    assert path["confidence"]["reliable"] is False
    assert path["confidence"]["status"] == "insufficient_data"
    assert "insufficient" in path["confidence"]["conclusion"]


def test_high_sample_combination_with_good_win_rate_is_marked_reliable(test_db):
    for i in range(30):
        pnl = 5.0 if i < 22 else -5.0  # 22/30 wins, well above the 55% Wilson lower-bound line
        _trade(f"r{i}", "stratProven", "Proven Strategy", "BTCUSDT", pnl, 5.0, closed_days_ago=30 - i)

    result = challenge_analysis.recommend_paths(start_amount=100.0, target_amount=110.0, days=60)
    path = next(p for p in result["paths"] if p["strategy_id"] == "stratProven")
    assert path["sample_size"] == 30
    assert path["confidence"]["reliable"] is True
    assert path["confidence"]["status"] == "reliable_good"


# --------------------------------------------------------------- Level 2: consistency check

def test_consistency_check_flags_a_combination_concentrated_in_one_time_window(test_db):
    # 25 modest losing trades spread across many weeks (clears the 25-trade
    # minimum sample size), then one huge winning trade in a single week --
    # almost ALL positive PnL comes from that one window, which is exactly
    # the "might be a fluke" shape.
    for i in range(25):
        _trade(f"c{i}", "stratLumpy", "Lumpy Strategy", "BTCUSDT", -1.0, 5.0, closed_days_ago=180 - i * 5)
    _trade("cbig", "stratLumpy", "Lumpy Strategy", "BTCUSDT", 500.0, 5.0, closed_days_ago=2)

    check = challenge_analysis.consistency_check("stratLumpy", "BTCUSDT")
    assert check["checked"] is True
    assert check["concentrated"] is True
    assert check["share_of_positive_pnl_in_best_window_pct"] >= 60.0


def test_consistency_check_does_not_flag_sustained_performance_across_windows(test_db):
    # Same modest win every ~10 days across many weeks -- spread out, not
    # concentrated in any single window.
    for i in range(30):
        _trade(f"s{i}", "stratSteady", "Steady Strategy", "ETHUSDT", 3.0, 5.0, closed_days_ago=90 - i * 3)

    check = challenge_analysis.consistency_check("stratSteady", "ETHUSDT")
    assert check["checked"] is True
    assert check["concentrated"] is False


def test_consistency_check_declines_to_judge_below_minimum_sample_size(test_db):
    for i in range(5):
        _trade(f"few{i}", "stratFew", "Few Trades", "BTCUSDT", 1.0, 5.0, closed_days_ago=i)
    check = challenge_analysis.consistency_check("stratFew", "BTCUSDT")
    assert check["checked"] is False
    assert check["concentrated"] is None


# --------------------------------------------------------------- Level 2: refuses unrealistic targets, offers alternative

def test_refuses_unrealistic_target_but_offers_a_genuinely_achievable_alternative(test_db):
    # A real, modest but genuine edge: 0.2 R-multiple average over 30 real
    # trades spread across 30 days.
    for i in range(30):
        _trade(f"m{i}", "stratModest", "Modest Strategy", "BTCUSDT", 1.0, 5.0, closed_days_ago=30 - i)

    # Ask for something wildly beyond what this combo has ever shown.
    result = challenge_analysis.recommend_paths(start_amount=100.0, target_amount=100000.0, days=3)
    assert result["any_achievable"] is False
    assert result["fallback"] is not None
    assert result["fallback"]["based_on_strategy_id"] == "stratModest"
    # The fallback must offer something real -- either a realistic amount
    # for the same timeframe, or a realistic timeframe for the same target
    # -- never leaving the user with nothing.
    assert (result["fallback"]["realistic_amount_in_same_days"] is not None
            or result["fallback"]["days_needed_for_original_target"] is not None)
    assert result["fallback"]["realistic_amount_in_same_days"] < 100000.0


def test_achievable_target_is_marked_achievable_with_a_real_path(test_db):
    for i in range(30):
        _trade(f"g{i}", "stratGood", "Good Strategy", "BTCUSDT", 2.0, 5.0, closed_days_ago=30 - i)

    result = challenge_analysis.recommend_paths(start_amount=100.0, target_amount=101.0, days=60)
    assert result["any_achievable"] is True
    achievable = [p for p in result["paths"] if p["achievable_at_this_pace"]]
    assert achievable
    assert achievable[0]["strategy_id"] == "stratGood"


# --------------------------------------------------------------- Level 3: drift detection

def test_drift_check_flags_material_win_rate_degradation(test_db):
    # Baseline was strong (80%); the most recent 15 trades are much worse.
    for i in range(15):
        pnl = -1.0 if i < 12 else 1.0  # 3/15 = 20% recent win rate
        _trade(f"d{i}", "stratDrift", "Drift Strategy", "BTCUSDT", pnl, 5.0, closed_days_ago=15 - i)

    drift = challenge_analysis.check_drift("stratDrift", "BTCUSDT", baseline_win_rate_pct=80.0)
    assert drift["checked"] is True
    assert drift["drifted"] is True
    assert drift["recent_win_rate_pct"] < 30.0


def test_drift_check_does_not_flag_when_performance_holds_up(test_db):
    for i in range(15):
        pnl = 1.0 if i < 12 else -1.0  # 12/15 = 80% recent win rate, matching baseline
        _trade(f"h{i}", "stratHold", "Hold Strategy", "BTCUSDT", pnl, 5.0, closed_days_ago=15 - i)

    drift = challenge_analysis.check_drift("stratHold", "BTCUSDT", baseline_win_rate_pct=80.0)
    assert drift["checked"] is True
    assert drift["drifted"] is False
