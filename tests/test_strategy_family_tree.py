"""Grand Feature Expansion, Phase 4 Feature 1: Strategy Family Tree
(sindhu_web/api/concepts_usage.py's get_strategy_family_tree) -- the
inverse presentation of the pre-existing get_concepts_usage() (concept ->
strategies): strategies GROUPED by shared concept, filtered to genuine
families (2+ members), with strategies belonging to no family surfaced
separately.
"""

import pytest

from backtest_engine import strategy_library as lib
from backtest_engine.strategy_config import Condition, SLTPSpec, StrategyConfig
from sindhu_web.api.concepts_usage import get_strategy_family_tree


@pytest.fixture(autouse=True)
def isolated_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path))
    yield


def _config(name, concepts_used):
    cfg = StrategyConfig(
        name=name,
        timeframes={"entry": "1m"},
        indicators=[{"name": "sma", "params": {"period": 3}, "role": "entry"}],
        entry_conditions=[
            Condition(type="price_compare", op=">", indicator="sma", params={"period": 3}),
        ],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    )
    cfg.concepts_used = concepts_used
    return cfg


def test_two_strategies_sharing_a_concept_form_a_family(test_db):
    lib.create(_config("Strat A", ["order_block"]))
    lib.create(_config("Strat B", ["order_block"]))
    result = get_strategy_family_tree()
    family = next(f for f in result["families"] if f["concept"] == "Order Block (OB)")
    assert family["member_count"] == 2
    assert set(family["strategies"]) == {"Strat A", "Strat B"}


def test_a_lone_strategy_on_a_concept_is_not_a_family(test_db):
    lib.create(_config("Solo Strategy", ["fvg"]))
    result = get_strategy_family_tree()
    assert not any(f["concept"] == "Fair Value Gap (FVG)" for f in result["families"])
    assert "Solo Strategy" in result["ungrouped_strategies"]


def test_a_strategy_can_belong_to_multiple_families(test_db):
    lib.create(_config("Multi", ["order_block", "fvg"]))
    lib.create(_config("OB Only", ["order_block"]))
    lib.create(_config("FVG Only", ["fvg"]))
    result = get_strategy_family_tree()
    ob_family = next(f for f in result["families"] if f["concept"] == "Order Block (OB)")
    fvg_family = next(f for f in result["families"] if f["concept"] == "Fair Value Gap (FVG)")
    assert "Multi" in ob_family["strategies"]
    assert "Multi" in fvg_family["strategies"]
    assert "Multi" not in result["ungrouped_strategies"]


def test_a_strategy_using_no_known_concept_is_ungrouped(test_db):
    lib.create(_config("Mystery Strategy", ["some_unrecognized_key"]))
    result = get_strategy_family_tree()
    assert "Mystery Strategy" in result["ungrouped_strategies"]


def test_families_are_sorted_largest_first(test_db):
    lib.create(_config("A", ["order_block"]))
    lib.create(_config("B", ["order_block"]))
    lib.create(_config("C", ["order_block"]))
    lib.create(_config("D", ["fvg"]))
    lib.create(_config("E", ["fvg"]))
    result = get_strategy_family_tree()
    sizes = [f["member_count"] for f in result["families"]]
    assert sizes == sorted(sizes, reverse=True)


def test_archived_strategies_are_excluded(test_db):
    sid = lib.create(_config("Archived One", ["order_block"]))
    lib.create(_config("Active One", ["order_block"]))
    lib.set_archived(sid, True)
    result = get_strategy_family_tree()
    assert not any(f["concept"] == "Order Block (OB)" for f in result["families"])
    assert "Archived One" not in result["ungrouped_strategies"]


def test_empty_library_has_no_families_or_ungrouped(test_db):
    result = get_strategy_family_tree()
    assert result["families"] == []
    assert result["ungrouped_strategies"] == []
