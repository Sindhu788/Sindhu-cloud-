"""Grand Feature Expansion, Phase 6 Feature 8: Cross-Coin Group Validation
(backtest_engine/cross_coin_validation.py) -- whether a strategy's real
backtest performance holds up similarly across low/medium/high VOLATILITY
groups of coins (computed fresh from real data every time), distinct from
the existing flat per-coin ranking table.
"""

import pytest

from backtest_engine import cross_coin_validation
from data_engine import storage


def _seed_batch_with_results(batch_id, results):
    """results: list of (symbol, total_trades, wins, net_profit)."""
    storage.create_batch(batch_id, "Test Strategy", "binance",
                          {"initial_balance": 10000.0}, "2026-01-01T00:00:00+00:00")
    for symbol, total_trades, wins, net_profit in results:
        storage.save_result(
            batch_id, symbol, "1h", "completed",
            {"total_trades": total_trades, "wins": wins, "losses": total_trades - wins,
             "win_rate": round(wins / total_trades * 100, 2) if total_trades else 0.0,
             "net_profit": net_profit},
            "2026-01-01T00:00:00+00:00",
        )


def test_unknown_batch_returns_none(test_db):
    assert cross_coin_validation.validate_across_coin_groups("does-not-exist") is None


def test_no_completed_results_returns_empty_groups(test_db):
    storage.create_batch("batch1", "Test Strategy", "binance", {"initial_balance": 10000.0}, "2026-01-01T00:00:00+00:00")
    result = cross_coin_validation.validate_across_coin_groups("batch1")
    assert result["groups"] == []
    assert result["consistent_across_groups"] is None


def test_groups_by_volatility_and_flags_consistency(test_db, monkeypatch):
    def fake_score(exchange, symbol):
        # DOGEUSDT/SHIBUSDT = high vol, ETHUSDT/BTCUSDT = low vol.
        vol = {"BTCUSDT": 1.0, "ETHUSDT": 1.5, "DOGEUSDT": 8.0, "SHIBUSDT": 9.0}[symbol]
        return {"symbol": symbol, "volatility_pct": vol}

    monkeypatch.setattr(cross_coin_validation, "_coin_activity_score", fake_score)
    _seed_batch_with_results("batch2", [
        ("BTCUSDT", 20, 12, 100.0), ("ETHUSDT", 20, 11, 90.0),
        ("DOGEUSDT", 20, 8, -50.0), ("SHIBUSDT", 20, 7, -60.0),
    ])
    result = cross_coin_validation.validate_across_coin_groups("batch2")
    groups = {g["group"]: g for g in result["groups"]}
    assert "low_volatility" in groups
    assert "high_volatility" in groups
    # Low-vol coins won more than high-vol coins in this fixture.
    assert groups["low_volatility"]["win_rate"] > groups["high_volatility"]["win_rate"]
    assert result["consistent_across_groups"] is False  # a real, disclosed >20pt swing


def test_consistent_performance_across_groups_is_flagged_true(test_db, monkeypatch):
    def fake_score(exchange, symbol):
        vol = {"BTCUSDT": 1.0, "DOGEUSDT": 8.0}[symbol]
        return {"symbol": symbol, "volatility_pct": vol}

    monkeypatch.setattr(cross_coin_validation, "_coin_activity_score", fake_score)
    _seed_batch_with_results("batch3", [
        ("BTCUSDT", 20, 12, 100.0), ("DOGEUSDT", 20, 11, 90.0),
    ])
    result = cross_coin_validation.validate_across_coin_groups("batch3")
    assert result["consistent_across_groups"] is True


def test_a_symbol_that_cannot_be_scored_is_simply_excluded(test_db, monkeypatch):
    def fake_score(exchange, symbol):
        if symbol == "UNSCORABLE":
            return None
        return {"symbol": symbol, "volatility_pct": 1.0}

    monkeypatch.setattr(cross_coin_validation, "_coin_activity_score", fake_score)
    _seed_batch_with_results("batch4", [
        ("BTCUSDT", 20, 12, 100.0), ("UNSCORABLE", 20, 10, 50.0),
    ])
    result = cross_coin_validation.validate_across_coin_groups("batch4")
    total_coins = sum(g["coin_count"] for g in result["groups"])
    assert total_coins == 1  # UNSCORABLE excluded, only BTCUSDT grouped


def test_endpoint_returns_the_validation(test_db, monkeypatch):
    from sindhu_web.api.backtesting import get_cross_coin_validation

    monkeypatch.setattr(cross_coin_validation, "_coin_activity_score",
                         lambda exchange, symbol: {"symbol": symbol, "volatility_pct": 1.0})
    _seed_batch_with_results("batch5", [("BTCUSDT", 20, 12, 100.0)])
    result = get_cross_coin_validation("batch5")
    assert len(result["groups"]) == 1


def test_endpoint_404s_for_unknown_batch(test_db):
    from fastapi import HTTPException
    from sindhu_web.api.backtesting import get_cross_coin_validation

    with pytest.raises(HTTPException) as exc_info:
        get_cross_coin_validation("does-not-exist")
    assert exc_info.value.status_code == 404
