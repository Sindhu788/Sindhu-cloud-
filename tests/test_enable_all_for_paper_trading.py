"""CEO Task A -- "Enable All for Paper Trading" button
(POST /api/paper-trading/strategy-config/enable-all). Must go through the
exact same activation write the per-strategy button already uses, never
enable a strategy that fails either mandatory gate, skip already-enabled
strategies, and trigger the group sync afterward.
"""
import pytest

from backtest_engine import strategy_library as lib
from backtest_engine.strategy_config import Condition, SLTPSpec, StrategyConfig
from data_engine import storage
from paper_trading import strategy_groups
from sindhu_web.api import paper_trading as pt_api


@pytest.fixture(autouse=True)
def isolated_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))


def _valid_config(name="Valid Strategy", **overrides):
    base = dict(
        name=name,
        timeframes={"entry": "5m"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30)],
        exit_conditions=[Condition(type="indicator_compare", indicator="macd", op=">", value=0)],
        concepts_used=["resistance"],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.5),
        risk_pct=1.0, risk_reward=2.5,
    )
    base.update(overrides)
    return StrategyConfig(**base)


def test_enables_every_eligible_strategy(test_db):
    sid1 = lib.create(_valid_config("Strategy A"))
    sid2 = lib.create(_valid_config("Strategy B"))

    result = pt_api.enable_all_for_paper_trading()

    assert result["enabled_count"] == 2
    assert {e["strategy_id"] for e in result["enabled"]} == {sid1, sid2}
    configs = storage.list_paper_strategy_configs()
    assert configs[sid1]["enabled"] is True
    assert configs[sid2]["enabled"] is True


def test_skips_strategy_that_fails_validator(test_db):
    good = lib.create(_valid_config("Good Strategy"))
    bad = lib.create(_valid_config("Bad Strategy", timeframes={}))

    result = pt_api.enable_all_for_paper_trading()

    assert {e["strategy_id"] for e in result["enabled"]} == {good}
    assert {b["strategy_id"] for b in result["blocked"]} == {bad}
    configs = storage.list_paper_strategy_configs()
    assert bad not in configs or not configs[bad].get("enabled")


def test_skips_already_enabled_strategy(test_db):
    sid = lib.create(_valid_config("Already On"))
    storage.save_paper_strategy_config(sid, True, 5, [], [], "2026-01-01T00:00:00+00:00")

    result = pt_api.enable_all_for_paper_trading()

    assert result["enabled_count"] == 0
    assert {e["strategy_id"] for e in result["already_enabled"]} == {sid}


def test_skips_archived_strategy(test_db):
    sid = lib.create(_valid_config("Archived One"))
    meta = lib._read_meta(sid)
    meta["archived"] = True
    lib._write_meta(sid, meta)

    result = pt_api.enable_all_for_paper_trading()

    assert result["enabled_count"] == 0
    configs = storage.list_paper_strategy_configs()
    assert sid not in configs or not configs[sid].get("enabled")


def test_triggers_group_sync_after_enabling(test_db, monkeypatch):
    monkeypatch.setattr(strategy_groups, "CHALLENGE_SIZE", 0)
    lib.create(_valid_config("Fresh Strategy"))

    result = pt_api.enable_all_for_paper_trading()

    assert "group_sync" in result
    assignments = storage.list_paper_strategy_groups()
    assert len(assignments) == 1
    assert list(assignments.values())[0] in ("losing", "profitable", "challenge")


def test_cleans_up_the_bogus_row_from_the_route_shadowing_incident(test_db):
    """2026-09-09 incident: before the {strategy_id} route was reordered
    to stop shadowing this one, every real click here actually hit
    update_strategy_config(strategy_id="enable-all"), writing a garbage
    paper_strategy_config row keyed by the literal string "enable-all" (never
    a real strategy id). This handler must self-heal that artifact on the
    very next real invocation rather than leaving it there forever."""
    storage.save_paper_strategy_config("enable-all", True, 5, [], [], "2026-01-01T00:00:00+00:00")

    pt_api.enable_all_for_paper_trading()

    configs = storage.list_paper_strategy_configs()
    assert "enable-all" not in configs


def test_never_calls_validator_or_safety_check_live(test_db, monkeypatch):
    """Same fast-path guarantee as the strategy-overview fix -- reads
    cached meta fields only, no per-strategy recomputation."""
    lib.create(_valid_config("Strategy A"))
    lib.create(_valid_config("Strategy B"))

    monkeypatch.setattr(pt_api.validator, "validate",
                         lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called")))
    monkeypatch.setattr(pt_api, "run_safety_check",
                         lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called")))

    result = pt_api.enable_all_for_paper_trading()

    assert result["enabled_count"] == 2
