"""Grand Feature Expansion, Phase 4 Feature 22: Undo/Rollback UI Config --
strategy_library.restore_version() restores an older saved version as a
new current version, never deleting or overwriting anything on disk.
"""

import pytest

from backtest_engine import strategy_library as lib
from backtest_engine.strategy_config import Condition, SLTPSpec, StrategyConfig
from sindhu_web.api.backtesting import RestoreVersionRequest, restore_strategy_version


@pytest.fixture(autouse=True)
def isolated_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path))
    yield


def _config(name, risk_pct):
    return StrategyConfig(
        name=name,
        timeframes={"entry": "1m"},
        indicators=[{"name": "sma", "params": {"period": 3}, "role": "entry"}],
        entry_conditions=[
            Condition(type="price_compare", op=">", indicator="sma", params={"period": 3}),
        ],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=risk_pct,
    )


def test_restore_creates_a_new_version_not_an_overwrite():
    sid = lib.create(_config("Strat", 1.0))
    lib.save_version(sid, _config("Strat", 2.0))
    lib.save_version(sid, _config("Strat", 3.0))
    assert lib._read_meta(sid)["current_version"] == 3

    new_version = lib.restore_version(sid, 1)
    assert new_version == 4
    assert lib._read_meta(sid)["current_version"] == 4
    assert lib.load(sid).risk_pct == 1.0
    # V1, V2, V3 all still exist untouched on disk.
    assert lib.load(sid, 1).risk_pct == 1.0
    assert lib.load(sid, 2).risk_pct == 2.0
    assert lib.load(sid, 3).risk_pct == 3.0


def test_restore_records_a_plain_language_reason():
    sid = lib.create(_config("Strat", 1.0))
    lib.save_version(sid, _config("Strat", 2.0))
    lib.restore_version(sid, 1)
    history = lib.version_history(sid)
    assert history[-1]["reason"] == "Restored from version 1"


def test_cannot_restore_the_current_version():
    sid = lib.create(_config("Strat", 1.0))
    with pytest.raises(ValueError):
        lib.restore_version(sid, 1)


def test_cannot_restore_a_nonexistent_version():
    sid = lib.create(_config("Strat", 1.0))
    with pytest.raises(ValueError):
        lib.restore_version(sid, 99)


def test_endpoint_restores_and_invalidates_cache(test_db):
    sid = lib.create(_config("Strat", 1.0))
    lib.save_version(sid, _config("Strat", 2.0))
    result = restore_strategy_version(sid, RestoreVersionRequest(version=1))
    assert result["ok"] is True
    assert result["new_version"] == 3
    assert lib.load(sid).risk_pct == 1.0


def test_endpoint_404s_for_unknown_strategy(test_db):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        restore_strategy_version("does-not-exist", RestoreVersionRequest(version=1))
    assert exc_info.value.status_code == 404


def test_endpoint_400s_for_current_version(test_db):
    from fastapi import HTTPException
    sid = lib.create(_config("Strat", 1.0))
    with pytest.raises(HTTPException) as exc_info:
        restore_strategy_version(sid, RestoreVersionRequest(version=1))
    assert exc_info.value.status_code == 400
