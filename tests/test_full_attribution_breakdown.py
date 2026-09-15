"""Grand Master Batch #2, Phase 1.1: real evidence for
challenge_analysis.full_attribution_breakdown() -- exit reason, market
condition, timeframe, and setup(entry-reason) dimensions, computed from
real stored closed trades only, same as granular_breakdown()'s existing
by_strategy/by_coin dimensions.
"""

from datetime import datetime, timezone

import pytest

from data_engine import config as base_config, storage
from paper_trading import challenge_analysis


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


def _trade(pid, pnl, exit_reason, market_state, timeframe, entry_reason, strategy_id="strat1"):
    storage.open_paper_position({
        "id": pid, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": strategy_id, "strategy_name": "Test Strategy",
        "market_state": market_state, "timeframe": timeframe, "entry_reason": entry_reason,
    })
    storage.close_paper_position(
        pid, 100.0 + pnl, 1700000600000, pnl, pnl, exit_reason, {}, {},
        "2026-01-02T00:00:00+00:00",
    )


def test_breakdown_by_exit_reason(test_db):
    _trade("t1", 10.0, "take_profit", "trending_up", "15m", "breakout")
    _trade("t2", -5.0, "stop_loss", "trending_up", "15m", "breakout")
    _trade("t3", 8.0, "take_profit", "ranging", "1h", "mean_reversion")

    result = challenge_analysis.full_attribution_breakdown()
    by_reason = {r["exit_reason"]: r for r in result["by_exit_reason"]}
    assert by_reason["take_profit"]["total_closed_trades"] == 2
    assert by_reason["take_profit"]["total_pnl"] == pytest.approx(18.0)
    assert by_reason["stop_loss"]["total_closed_trades"] == 1
    assert by_reason["stop_loss"]["total_pnl"] == pytest.approx(-5.0)


def test_breakdown_by_market_condition(test_db):
    _trade("t1", 10.0, "take_profit", "trending_up", "15m", "breakout")
    _trade("t2", -5.0, "stop_loss", "ranging", "15m", "breakout")

    result = challenge_analysis.full_attribution_breakdown()
    by_condition = {r["market_condition"]: r for r in result["by_market_condition"]}
    assert by_condition["trending_up"]["total_pnl"] == pytest.approx(10.0)
    assert by_condition["ranging"]["total_pnl"] == pytest.approx(-5.0)


def test_breakdown_by_timeframe_and_setup(test_db):
    _trade("t1", 10.0, "take_profit", "trending_up", "15m", "breakout")
    _trade("t2", 3.0, "take_profit", "trending_up", "1h", "pullback")

    result = challenge_analysis.full_attribution_breakdown()
    by_tf = {r["timeframe"]: r for r in result["by_timeframe"]}
    assert by_tf["15m"]["total_pnl"] == pytest.approx(10.0)
    assert by_tf["1h"]["total_pnl"] == pytest.approx(3.0)

    by_setup = {r["setup"]: r for r in result["by_setup"]}
    assert by_setup["breakout"]["total_pnl"] == pytest.approx(10.0)
    assert by_setup["pullback"]["total_pnl"] == pytest.approx(3.0)


def test_missing_dimension_groups_under_unknown_not_dropped(test_db):
    # _closed_rows() (shared with granular_breakdown()) already excludes
    # rows with no strategy_id at all -- this tests the "unknown" bucket
    # for a real, strategy-attributed trade that simply predates a field
    # (e.g. exit_reason never recorded), not a lesson-only trade.
    storage.open_paper_position({
        "id": "u1", "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0,
        "entry_time": 1700000000000, "created_at": "2026-01-01T00:00:00+00:00",
        "strategy_id": "strat1", "strategy_name": "Test Strategy",
    })
    storage.close_paper_position(
        "u1", 105.0, 1700000600000, 5.0, 5.0, None, {}, {}, "2026-01-02T00:00:00+00:00",
    )
    result = challenge_analysis.full_attribution_breakdown()
    by_reason = {r["exit_reason"]: r for r in result["by_exit_reason"]}
    assert by_reason["unknown"]["total_closed_trades"] == 1


def test_endpoint_is_reachable(test_db):
    from sindhu_web.api.paper_trading import get_full_attribution_breakdown
    result = get_full_attribution_breakdown()
    assert "by_exit_reason" in result and "by_market_condition" in result
