"""Urgent bug fix, 2026-09-09: right after the route-shadowing fix made
"Enable All for Paper Trading" reachable for the first time, it activated
75 real strategies -- and the Paper Trading page immediately failed to
load with "GET /api/paper-trading/status timed out after 15000ms".

/api/paper-trading/status was already fixed (single connection via
get_paper_status_snapshot) and confirmed fast in isolation, so the
timeout wasn't coming from status() itself. Root cause was upstream: the
enable-all POST activated each strategy with its own
save_paper_strategy_config() call, then strategy_groups.
sync_group_assignments() assigned each of those same 75 strategies to a
group with its own upsert_paper_strategy_group() call -- 150 sequential
fresh Postgres connections (no pooling on the cloud runner) in one
request. That alone was slow enough to blow the request's own 15s
budget, and while it ran it starved concurrent page-load requests
(including /status) of their share of Postgres's limited free-tier
connection slots. Same bug class as the status/analytics timeouts,
triggered by activation-batch size instead of strategy count or request
volume.
"""
from data_engine import storage
from paper_trading import strategy_groups
from sindhu_web.api import paper_trading as pt_api
from backtest_engine import strategy_library as lib
from backtest_engine.strategy_config import Condition, SLTPSpec, StrategyConfig

import pytest


@pytest.fixture(autouse=True)
def isolated_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))


def _valid_config(name):
    return StrategyConfig(
        name=name,
        timeframes={"entry": "5m"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30)],
        exit_conditions=[Condition(type="indicator_compare", indicator="macd", op=">", value=0)],
        concepts_used=["resistance"],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.5),
        risk_pct=1.0, risk_reward=2.5,
    )


def _counting_get_conn(monkeypatch, call_count):
    real_get_conn = storage.get_conn

    def counting():
        call_count["n"] += 1
        return real_get_conn()

    monkeypatch.setattr(storage, "get_conn", counting)


def test_batch_activation_uses_one_connection_for_many_strategies(test_db, monkeypatch):
    call_count = {"n": 0}
    _counting_get_conn(monkeypatch, call_count)

    storage.enable_paper_strategy_configs_batch([f"strat{i}" for i in range(30)], 5, "2026-01-01T00:00:00+00:00")

    assert call_count["n"] == 1
    configs = storage.list_paper_strategy_configs()
    assert all(configs[f"strat{i}"]["enabled"] for i in range(30))


def test_batch_group_assignment_uses_one_connection_for_many_strategies(test_db, monkeypatch):
    for i in range(30):
        storage.save_paper_strategy_config(f"strat{i}", True, 5, [], [], "2026-01-01T00:00:00+00:00")

    call_count = {"n": 0}
    _counting_get_conn(monkeypatch, call_count)

    result = strategy_groups.sync_group_assignments()

    # _strategy_universe's 2 reads + list_paper_strategy_groups (already
    # assigned) + 1 batch write -- a small constant, not one per strategy.
    assert call_count["n"] <= 4
    assert sum(len(v) for v in result["assigned"].values()) == 30


def test_enable_all_end_to_end_stays_low_on_connections_at_scale(test_db, monkeypatch):
    """The real incident, reproduced: 75 eligible strategies through the
    actual endpoint, counting every get_conn() call across activation AND
    the group sync that follows in the same request."""
    for i in range(75):
        lib.create(_valid_config(f"Strategy {i}"))

    call_count = {"n": 0}
    _counting_get_conn(monkeypatch, call_count)

    result = pt_api.enable_all_for_paper_trading()

    assert result["enabled_count"] == 75
    # Before this fix: 75 (activation) + 75 (group assignment) = 150+
    # connections in this one request. Now: a small constant number of
    # batched reads/writes regardless of how many strategies were enabled.
    assert call_count["n"] < 10
