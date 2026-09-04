"""Master Task 3, Phase 1.1/1.3: self_learning_engine/combination_scorer.py
-- real system-wide evidence (never a guess) for which DNA-tag combinations
and which coins have performed best, pooling BOT-lineage evolution scores
with live paper-trading performance and a per-coin breakdown.
"""

from datetime import datetime, timezone

import pytest

from backtest_engine.strategy_config import Condition, SLTPSpec, StrategyConfig
from backtest_engine import strategy_library as lib
from data_engine import storage
from self_learning_engine import combination_scorer


@pytest.fixture(autouse=True)
def isolated_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))


def _make_strategy(name, concepts_used):
    cfg = StrategyConfig(
        name=name, timeframes={"entry": "5m"},
        entry_conditions=[Condition(type="concept", name=concepts_used[0])],
        concepts_used=concepts_used,
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0,
    )
    return lib.create(cfg)


def _close_a_trade(strategy_id, strategy_name, symbol, pnl, is_win):
    now = datetime.now(timezone.utc).isoformat()
    with storage.get_conn() as conn:
        conn.execute(
            """INSERT INTO paper_positions
               (id, exchange, symbol, direction, entry_price, exit_price, size,
                entry_time, exit_time, pnl, status, strategy_id, strategy_name,
                created_at, closed_at)
               VALUES (?, 'binance', ?, 'long', 100, 105, 1, 0, 1, ?, 'closed', ?, ?, ?, ?)""",
            (f"{strategy_id}-{symbol}-{pnl}", symbol, pnl, strategy_id, strategy_name, now, now),
        )
    storage.update_paper_strategy_performance(strategy_id, strategy_name, pnl, is_win, None, now)


def test_scores_a_combo_from_real_paper_trading_performance(test_db):
    # liquidity_sweep -> {"liquidity"}, poc -> {"volume"} (evolution_engine/dna.py)
    sid = _make_strategy("Sweep+POC Strategy", ["liquidity_sweep", "poc"])
    _close_a_trade(sid, "Sweep+POC Strategy", "BTCUSDT", 50.0, True)
    _close_a_trade(sid, "Sweep+POC Strategy", "BTCUSDT", 30.0, True)

    results = combination_scorer.score_combinations()
    combo = next(r for r in results if r["dna_combo"] == ["liquidity", "volume"])
    assert combo["sample_size"] >= 1
    assert combo["best_coins"][0]["symbol"] == "BTCUSDT"
    assert combo["best_coins"][0]["total_pnl"] == 80.0


def test_best_coins_ranks_by_total_pnl_descending(test_db):
    sid = _make_strategy("Multi-Coin Strategy", ["fvg", "order_block"])  # both {"liquidity"/"breakout"}
    _close_a_trade(sid, "Multi-Coin Strategy", "ETHUSDT", 10.0, True)
    _close_a_trade(sid, "Multi-Coin Strategy", "SOLUSDT", 90.0, True)

    results = combination_scorer.score_combinations()
    combo = next(r for r in results if set(r["dna_combo"]) == {"breakout", "liquidity"})
    symbols_in_order = [c["symbol"] for c in combo["best_coins"]]
    assert symbols_in_order.index("SOLUSDT") < symbols_in_order.index("ETHUSDT")


def test_results_are_sorted_best_score_first(test_db):
    now = datetime.now(timezone.utc).isoformat()
    sid_good = _make_strategy("Good Combo Strategy", ["fvg", "order_block"])  # -> {"breakout", "liquidity"}
    storage.update_paper_strategy_performance(sid_good, "Good Combo Strategy", 300.0, True, None, now)

    sid_bad = _make_strategy("Bad Combo Strategy", ["ema", "volume"])  # -> {"trend", "volume"}
    storage.update_paper_strategy_performance(sid_bad, "Bad Combo Strategy", -300.0, False, None, now)

    results = combination_scorer.score_combinations()
    scores = [r["avg_score"] for r in results]
    assert scores == sorted(scores, reverse=True)
    assert results[0]["dna_combo"] == ["breakout", "liquidity"]


def test_no_data_returns_empty_list(test_db):
    assert combination_scorer.score_combinations() == []
