"""Urgent bug fix, 2026-09-09: GET /api/paper-trading/strategy-overview
timed out (15000ms) on Render -- confirmed the cause was recomputing
validator.validate() + run_safety_check() (plus a redundant full config
reload) for every library strategy on every single page view. Both gates
(and the display-only fixed R:R) are now computed once per save and
cached in meta.json (backtest_engine.strategy_library._compute_activation_gates),
so a listing endpoint never has to recompute or reload anything.
"""
import pytest

from backtest_engine import strategy_library as lib
from backtest_engine.strategy_config import Condition, SLTPSpec, StrategyConfig
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


def test_create_caches_both_gates_and_fixed_rr(test_db):
    sid = lib.create(_valid_config())
    meta = lib._read_meta(sid)

    assert meta["safety_status"] == "ready"
    assert meta["safety_reasons"] == []
    assert meta["validator_status"] == "ready"
    assert meta["validator_errors"] == []
    assert meta["fixed_rr"] == 2.5


def test_invalid_strategy_caches_validator_errors(test_db):
    # No entry timeframe -- the validator rejects this.
    bad = _valid_config(timeframes={})
    sid = lib.create(bad)
    meta = lib._read_meta(sid)

    assert meta["validator_status"] == "needs_clarification"
    assert len(meta["validator_errors"]) > 0


def test_save_version_refreshes_cached_gates(test_db):
    sid = lib.create(_valid_config())
    assert lib._read_meta(sid)["fixed_rr"] == 2.5

    lib.save_version(sid, _valid_config(take_profit=SLTPSpec(type="rr", value=4.0)))
    meta = lib._read_meta(sid)
    assert meta["fixed_rr"] == 4.0


def test_recheck_safety_backfills_missing_fields_and_returns_safety_shape(test_db):
    sid = lib.create(_valid_config())
    # Simulate a strategy saved before validator_status/fixed_rr existed.
    meta = lib._read_meta(sid)
    del meta["validator_status"]
    del meta["fixed_rr"]
    lib._write_meta(sid, meta)

    result = lib.recheck_safety(sid)

    assert result == {"status": "ready", "reasons": [], "passed": True}
    refreshed = lib._read_meta(sid)
    assert refreshed["validator_status"] == "ready"
    assert refreshed["fixed_rr"] == 2.5


def test_strategy_overview_never_calls_validator_or_safety_check_directly(test_db, monkeypatch):
    """The whole point of the fix: the listing endpoint must read the
    cached meta fields, never re-run either gate or reload the full
    config per row."""
    lib.create(_valid_config("Strategy A"))
    lib.create(_valid_config("Strategy B"))

    monkeypatch.setattr(pt_api.validator, "validate",
                         lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called")))
    monkeypatch.setattr(pt_api, "run_safety_check",
                         lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called")))
    monkeypatch.setattr(pt_api.lib, "load",
                         lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not reload full config")))

    result = pt_api.get_strategy_overview()

    assert len(result["strategies"]) == 2
    for row in result["strategies"]:
        assert row["can_activate"] is True


def test_strategy_overview_reflects_cached_blocked_reason(test_db):
    bad = _valid_config(timeframes={})
    lib.create(bad)

    result = pt_api.get_strategy_overview()

    row = result["strategies"][0]
    assert row["can_activate"] is False
    assert row["activation_blocked_reason"]


def test_strategy_overview_handles_pre_cache_meta_gracefully(test_db):
    """A strategy saved before this fix has neither safety_status nor
    validator_status -- must be treated as blocked (never silently
    assumed safe), not crash."""
    sid = lib.create(_valid_config())
    meta = lib._read_meta(sid)
    del meta["safety_status"]
    del meta["validator_status"]
    lib._write_meta(sid, meta)

    result = pt_api.get_strategy_overview()

    row = result["strategies"][0]
    assert row["can_activate"] is False
    assert "not yet computed" in row["activation_blocked_reason"]
