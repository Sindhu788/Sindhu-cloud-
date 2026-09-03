"""Grand Feature Expansion, Phase 3 Feature 1: Sanity Check Alert
(backtest_engine/result_plausibility.py) -- flags a COMPLETED backtest
result as suspiciously implausible (near-0%/near-100% win rate, an
absurd average profit %, or an absurd trades-per-coin count) before
anyone treats it as real. Distinct from the pre-existing
backtest_engine/sanity_check.py, which runs BEFORE a backtest checking
for a structural zero-trade bug -- this runs AFTER, on real results.
"""

from data_engine import storage
from backtest_engine import result_plausibility


def _make_batch(batch_id, strategy_name, symbol_results, initial_balance=1000.0):
    """symbol_results: list of (total_trades, wins, final_balance, profit_pct, max_drawdown_pct) tuples,
    one per symbol (so symbol_count == len(symbol_results))."""
    storage.create_batch(batch_id, strategy_name, "binance", {"initial_balance": initial_balance}, "2026-01-01T00:00:00+00:00")
    for i, (total_trades, wins, final_balance, profit_pct, max_dd) in enumerate(symbol_results):
        storage.save_result(
            batch_id, f"COIN{i}USDT", "1h", "completed",
            {"total_trades": total_trades, "wins": wins, "final_balance": final_balance,
             "profit_pct": profit_pct, "max_drawdown_pct": max_dd},
            "2026-01-01T00:00:00+00:00",
        )
    storage.update_batch_status(batch_id, "completed", "2026-01-01T00:00:00+00:00")


def test_a_normal_result_is_plausible(test_db):
    _make_batch("b1", "Normal Strategy", [(20, 11, 1100.0, 10.0, 8.0)])
    result = result_plausibility.check_batch_plausibility("b1")
    assert result["plausible"] is True
    assert result["flags"] == []


def test_near_zero_win_rate_with_real_sample_is_flagged(test_db):
    _make_batch("b1", "Suspicious Strategy", [(20, 0, 900.0, -10.0, 15.0)])
    result = result_plausibility.check_batch_plausibility("b1")
    assert result["plausible"] is False
    assert any("always losing" in f for f in result["flags"])


def test_near_zero_win_rate_with_tiny_sample_is_not_flagged(test_db):
    """A 0% win rate over 2 trades is unremarkable noise, not suspicious."""
    _make_batch("b1", "New Strategy", [(2, 0, 990.0, -1.0, 2.0)])
    result = result_plausibility.check_batch_plausibility("b1")
    assert result["plausible"] is True


def test_near_perfect_win_rate_with_real_sample_is_flagged(test_db):
    _make_batch("b1", "Too Good Strategy", [(20, 20, 2000.0, 100.0, 0.0)])
    result = result_plausibility.check_batch_plausibility("b1")
    assert result["plausible"] is False
    assert any("always winning" in f for f in result["flags"])


def test_extreme_profit_pct_is_flagged(test_db):
    _make_batch("b1", "Bug Strategy", [(20, 10, 1000.0, 8000.0, 5.0)])
    result = result_plausibility.check_batch_plausibility("b1")
    assert result["plausible"] is False
    assert any("extreme return" in f for f in result["flags"])


def test_extreme_trades_per_symbol_is_flagged(test_db):
    _make_batch("b1", "Never Cools Down", [(6000, 3000, 1500.0, 50.0, 10.0)])
    result = result_plausibility.check_batch_plausibility("b1")
    assert result["plausible"] is False
    assert any("re-entry frequency" in f for f in result["flags"])


def test_a_batch_with_no_trades_is_not_flagged(test_db):
    storage.create_batch("b1", "No Trades", "binance", {"initial_balance": 1000.0}, "2026-01-01T00:00:00+00:00")
    storage.update_batch_status("b1", "completed", "2026-01-01T00:00:00+00:00")
    result = result_plausibility.check_batch_plausibility("b1")
    assert result["plausible"] is True


def test_unknown_batch_id_is_not_flagged(test_db):
    result = result_plausibility.check_batch_plausibility("does-not-exist")
    assert result["plausible"] is True
    assert result["summary"] is None


def test_sweep_creates_one_alert_per_implausible_batch(test_db):
    _make_batch("b1", "Suspicious", [(20, 0, 900.0, -10.0, 15.0)])
    _make_batch("b2", "Normal", [(20, 11, 1100.0, 10.0, 8.0)])

    flagged = result_plausibility.sweep_recently_completed_batches()
    assert flagged == ["b1"]
    alerts = storage.list_paper_alerts()
    matches = [a for a in alerts if a["alert_type"] == "backtest_implausible_result"]
    assert len(matches) == 1
    assert matches[0]["strategy_id"] == "b1"


def test_sweep_never_re_alerts_the_same_batch_twice(test_db):
    _make_batch("b1", "Suspicious", [(20, 0, 900.0, -10.0, 15.0)])
    first = result_plausibility.sweep_recently_completed_batches()
    second = result_plausibility.sweep_recently_completed_batches()
    assert first == ["b1"]
    assert second == []
    matches = [a for a in storage.list_paper_alerts() if a["alert_type"] == "backtest_implausible_result"]
    assert len(matches) == 1


def test_sweep_ignores_batches_that_are_not_yet_completed(test_db):
    storage.create_batch("b1", "Still Running", "binance", {"initial_balance": 1000.0}, "2026-01-01T00:00:00+00:00")
    storage.save_result(
        "b1", "COIN0USDT", "1h", "completed",
        {"total_trades": 20, "wins": 0, "final_balance": 900.0, "profit_pct": -10.0, "max_drawdown_pct": 15.0},
        "2026-01-01T00:00:00+00:00",
    )
    # Deliberately never call update_batch_status -- batch stays "running".
    flagged = result_plausibility.sweep_recently_completed_batches()
    assert flagged == []
