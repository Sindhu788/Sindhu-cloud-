"""Grand Feature Expansion, Phase 3 Feature 18: Slippage Sensitivity Test
(backtest_engine.slippage_sensitivity.run_slippage_sensitivity_test) --
distinct from the pre-existing backtest_engine/stress_test.py (which
varies MARKET conditions, not a cost assumption). Recomputes a completed
batch's real trades' PnL under progressively worse EXTRA slippage, reusing
the exact same directional _apply_slippage formula the real backtest
already used, rather than re-running the simulation.
"""

from data_engine import storage
from backtest_engine import slippage_sensitivity


def _save_trade(batch_id, symbol, trade_num, side, entry_price, exit_price, size, pnl):
    with storage.get_conn() as conn:
        conn.execute(
            """INSERT INTO backtest_trades
               (batch_id, symbol, timeframe, trade_num, side, entry_time, entry_price,
                exit_time, exit_price, size, pnl, pnl_pct, exit_reason)
               VALUES (?, ?, '1h', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'take_profit')""",
            (batch_id, symbol, trade_num, side, 1700000000000, entry_price,
             1700003600000, exit_price, size, pnl, pnl / (entry_price * size) * 100),
        )


def _setup_batch(batch_id="b1"):
    storage.create_batch(batch_id, "Test Strategy", "binance", {"initial_balance": 1000.0}, "2026-01-01T00:00:00+00:00")


def test_no_trades_reports_a_clear_reason(test_db):
    _setup_batch()
    result = slippage_sensitivity.run_slippage_sensitivity_test("b1")
    assert result["levels"] == []
    assert "no closed trades" in result["reason"]


def test_baseline_level_recomputes_close_to_the_recorded_pnl(test_db):
    _setup_batch()
    # Long trade: bought at 100, sold at 110, size 1 -> $10 pnl, matches recorded.
    _save_trade("b1", "BTCUSDT", 1, "long", 100.0, 110.0, 1.0, 10.0)
    result = slippage_sensitivity.run_slippage_sensitivity_test("b1", extra_slippage_levels=(0.0, 0.01))
    baseline = result["levels"][0]
    assert baseline["extra_slippage_pct"] == 0.0
    assert baseline["total_pnl"] == 10.0  # 0% EXTRA slippage -- exactly the recorded prices


def test_worsening_slippage_reduces_pnl_for_a_long_trade(test_db):
    _setup_batch()
    _save_trade("b1", "BTCUSDT", 1, "long", 100.0, 110.0, 1.0, 10.0)
    result = slippage_sensitivity.run_slippage_sensitivity_test("b1", extra_slippage_levels=(0.0, 0.01, 0.05))
    pnls = [lvl["total_pnl"] for lvl in result["levels"]]
    assert pnls[0] > pnls[1] > pnls[2]  # strictly worse as extra slippage increases


def test_a_thin_edge_finds_a_breakeven_level(test_db):
    _setup_batch()
    # A wafer-thin real edge ($0.30 on a $100 notional) should break even
    # at a small extra-slippage level -- a fragile edge.
    _save_trade("b1", "BTCUSDT", 1, "long", 100.0, 100.3, 1.0, 0.3)
    result = slippage_sensitivity.run_slippage_sensitivity_test("b1", extra_slippage_levels=(0.0, 0.001, 0.002, 0.01, 0.05))
    assert result["breakeven_extra_slippage_pct"] is not None
    assert result["breakeven_extra_slippage_pct"] <= 0.5
    assert result["fragile"] is True


def test_a_durable_edge_never_breaks_even_in_the_tested_range(test_db):
    _setup_batch()
    _save_trade("b1", "BTCUSDT", 1, "long", 100.0, 500.0, 1.0, 400.0)
    result = slippage_sensitivity.run_slippage_sensitivity_test("b1", extra_slippage_levels=(0.0, 0.001, 0.01))
    assert result["breakeven_extra_slippage_pct"] is None
    assert result["fragile"] is False


def test_short_trades_are_handled_with_the_correct_direction(test_db):
    _setup_batch()
    # Short: sold at 110, bought back at 100, size 1 -> $10 pnl.
    _save_trade("b1", "BTCUSDT", 1, "short", 110.0, 100.0, 1.0, 10.0)
    result = slippage_sensitivity.run_slippage_sensitivity_test("b1", extra_slippage_levels=(0.0, 0.01))
    assert result["levels"][0]["total_pnl"] == 10.0
    assert result["levels"][1]["total_pnl"] < 10.0  # also degrades under worse slippage
