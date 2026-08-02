"""Batch 4, Task 3 -- Duplicate Strategy Cleanup. Surfaces the SAME DNA-
fingerprint detection already used at import time
(knowledge_compiler.quality.strategy_dna) as a grouped, actionable view,
with archive (never delete) so redundant copies can be cleared out of
normal browsing while staying fully recoverable.
"""

import pytest
from fastapi import HTTPException

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine import strategy_library as lib
from knowledge_compiler import quality as kc_quality
from sindhu_web.api import backtesting


@pytest.fixture(autouse=True)
def isolated_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))
    yield


def _cfg(name, rsi_op="<"):
    return StrategyConfig(
        name=name, timeframes={"entry": "1h"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op=rsi_op, value=30.0)],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    )


def test_two_differently_named_strategies_with_identical_rules_share_dna():
    id1 = lib.create(_cfg("Strategy A"))
    id2 = lib.create(_cfg("Strategy B"))
    dna1 = kc_quality.strategy_dna(lib.load(id1))
    dna2 = kc_quality.strategy_dna(lib.load(id2))
    assert dna1 == dna2


def test_find_duplicate_strategy_groups_finds_the_real_duplicate_pair():
    id1 = lib.create(_cfg("Strategy A"))
    id2 = lib.create(_cfg("Strategy B"))
    lib.create(_cfg("Unrelated Strategy", rsi_op=">"))  # different DNA -- not a duplicate

    groups = kc_quality.find_duplicate_strategy_groups(lib.list_all, lib.load)
    assert len(groups) == 1
    assert set(groups[0]["strategy_ids"]) == {id1, id2}


def test_singleton_strategies_never_form_a_group():
    lib.create(_cfg("Only One"))
    groups = kc_quality.find_duplicate_strategy_groups(lib.list_all, lib.load)
    assert groups == []


def test_endpoint_returns_the_group_with_plain_language_fields(test_db):
    lib.create(_cfg("Strategy A"))
    lib.create(_cfg("Strategy B"))
    result = backtesting.get_duplicate_strategy_groups()
    assert len(result["groups"]) == 1
    members = result["groups"][0]["strategies"]
    assert {m["name"] for m in members} == {"Strategy A", "Strategy B"}
    for m in members:
        assert "imported_at" in m
        assert "rule_count" in m
        assert "last_batch_result" in m


def test_archive_requires_confirmation(test_db):
    id1 = lib.create(_cfg("Strategy A"))
    lib.create(_cfg("Strategy B"))
    with pytest.raises(HTTPException) as exc_info:
        backtesting.archive_strategy(id1, backtesting.ArchiveRequest(confirm=False))
    assert exc_info.value.status_code == 400


def test_archive_marks_strategy_archived_but_never_deletes_it(test_db):
    id1 = lib.create(_cfg("Strategy A"))
    lib.create(_cfg("Strategy B"))
    backtesting.archive_strategy(id1, backtesting.ArchiveRequest(confirm=True))

    meta = next(m for m in lib.list_all() if m["id"] == id1)
    assert meta["archived"] is True
    # Never deleted -- still fully loadable, versions intact.
    cfg = lib.load(id1)
    assert cfg.name == "Strategy A"


def test_archive_blocks_removing_the_last_active_copy_of_a_group(test_db):
    id1 = lib.create(_cfg("Strategy A"))
    id2 = lib.create(_cfg("Strategy B"))
    backtesting.archive_strategy(id1, backtesting.ArchiveRequest(confirm=True))

    with pytest.raises(HTTPException) as exc_info:
        backtesting.archive_strategy(id2, backtesting.ArchiveRequest(confirm=True))
    assert exc_info.value.status_code == 400
    # id2 must still be active -- the block actually prevented it.
    meta = next(m for m in lib.list_all() if m["id"] == id2)
    assert meta["archived"] is False


def test_unarchive_restores_a_strategy_and_needs_no_confirmation(test_db):
    id1 = lib.create(_cfg("Strategy A"))
    lib.create(_cfg("Strategy B"))
    backtesting.archive_strategy(id1, backtesting.ArchiveRequest(confirm=True))
    backtesting.unarchive_strategy(id1)
    meta = next(m for m in lib.list_all() if m["id"] == id1)
    assert meta["archived"] is False


def test_archived_strategy_disappears_from_default_strategies_list(test_db):
    id1 = lib.create(_cfg("Strategy A"))
    lib.create(_cfg("Strategy B"))
    backtesting.archive_strategy(id1, backtesting.ArchiveRequest(confirm=True))

    default_view = backtesting.list_strategies(q="")
    assert id1 not in [s["id"] for s in default_view["strategies"]]

    full_view = backtesting.list_strategies(q="", include_archived=True)
    assert id1 in [s["id"] for s in full_view["strategies"]]


def test_archiving_never_affects_the_copy_kept(test_db):
    """The copy the CEO chooses to keep is never touched -- only the
    strategy explicitly archived changes state."""
    id1 = lib.create(_cfg("Strategy A"))
    id2 = lib.create(_cfg("Strategy B"))
    before_kept = lib.load(id2).to_dict()

    backtesting.archive_strategy(id1, backtesting.ArchiveRequest(confirm=True))

    after_kept_meta = next(m for m in lib.list_all() if m["id"] == id2)
    assert after_kept_meta["archived"] is False
    assert lib.load(id2).to_dict() == before_kept
