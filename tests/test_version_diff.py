"""Item 6 (Parser & Extraction Improvements) -- Extraction History /
Versioning. Full-snapshot versioning already existed (strategy_library.py);
this covers what was genuinely missing: a reason/changelog per version, and
a real diff view between two versions instead of full raw JSON dumps."""

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine import strategy_library as lib
from sindhu_web.api import backtesting as bt_api


def _isolated_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))


def _strategy(**overrides):
    base = dict(
        name="Version Diff Test Strategy",
        raw_text="test",
        timeframes={"entry": "5m"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op=">", value=30.0)],
        exit_conditions=[],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0, risk_reward=2.0,
    )
    base.update(overrides)
    return StrategyConfig(**base)


def test_version_1_has_no_reason_never_fabricated(tmp_path, monkeypatch):
    _isolated_library(tmp_path, monkeypatch)
    strategy_id = lib.create(_strategy())
    versions = lib.version_history(strategy_id)
    assert len(versions) == 1
    assert versions[0]["reason"] is None


def test_save_version_with_a_reason_is_recorded_and_never_lost(tmp_path, monkeypatch):
    _isolated_library(tmp_path, monkeypatch)
    strategy_id = lib.create(_strategy())
    cfg = lib.load(strategy_id)
    cfg.risk_pct = 2.0
    lib.save_version(strategy_id, cfg, reason="Risk % corrected during clarification")

    versions = lib.version_history(strategy_id)
    assert len(versions) == 2
    assert versions[1]["reason"] == "Risk % corrected during clarification"
    # Old behavior unchanged: a caller that never passes reason still works.
    cfg.risk_pct = 3.0
    lib.save_version(strategy_id, cfg)
    versions = lib.version_history(strategy_id)
    assert versions[2]["reason"] is None


def test_diff_versions_reports_exactly_what_changed(tmp_path, monkeypatch):
    _isolated_library(tmp_path, monkeypatch)
    strategy_id = lib.create(_strategy())
    cfg = lib.load(strategy_id)
    cfg.stop_loss = SLTPSpec(type="atr_multiple", value=2.0)
    cfg.risk_pct = 1.5
    lib.save_version(strategy_id, cfg, reason="Re-extracted stop-loss")

    changes = lib.diff_versions(strategy_id, 1, 2)
    changed_fields = {c["field"] for c in changes}
    assert "stop_loss" in changed_fields
    assert "risk_pct" in changed_fields
    assert "entry_conditions" not in changed_fields  # untouched -- must not appear as a false diff

    sl_change = next(c for c in changes if c["field"] == "stop_loss")
    assert sl_change["label"] == "Stop-Loss"
    assert sl_change["before"]["type"] == "fixed_pct"
    assert sl_change["after"]["type"] == "atr_multiple"


def test_diff_versions_is_empty_for_two_identical_versions(tmp_path, monkeypatch):
    _isolated_library(tmp_path, monkeypatch)
    strategy_id = lib.create(_strategy())
    cfg = lib.load(strategy_id)
    lib.save_version(strategy_id, cfg)  # no real change
    assert lib.diff_versions(strategy_id, 1, 2) == []


def test_diff_versions_never_touches_raw_text_field(tmp_path, monkeypatch):
    _isolated_library(tmp_path, monkeypatch)
    strategy_id = lib.create(_strategy(raw_text="original document text"))
    cfg = lib.load(strategy_id)
    cfg.risk_pct = 5.0
    lib.save_version(strategy_id, cfg)
    changes = lib.diff_versions(strategy_id, 1, 2)
    assert not any(c["field"] == "raw_text" for c in changes)


def test_diff_endpoint_returns_404_for_missing_version(tmp_path, monkeypatch):
    from fastapi import HTTPException
    _isolated_library(tmp_path, monkeypatch)
    strategy_id = lib.create(_strategy())
    try:
        bt_api.get_strategy_version_diff(strategy_id, 1, 99)
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 404


def test_old_versions_are_never_deleted_by_saving_a_new_one(tmp_path, monkeypatch):
    _isolated_library(tmp_path, monkeypatch)
    strategy_id = lib.create(_strategy())
    cfg = lib.load(strategy_id)
    cfg.risk_pct = 9.0
    lib.save_version(strategy_id, cfg)
    v1 = lib.load(strategy_id, version=1)
    assert v1.risk_pct == 1.0  # the original is still fully intact
