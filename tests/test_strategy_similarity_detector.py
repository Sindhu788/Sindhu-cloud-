"""Grand Feature Expansion, Phase 4 Feature 2: Strategy Similarity
Detector (backtest_engine/strategy_library.py's find_similarity_warnings)
-- fuzzy similarity (Jaccard index over concepts_used) against every
ACTIVE strategy, distinct from the pre-existing EXACT-duplicate hash
check and from graveyard.py's buried-strategies-only, count-based check.
"""

import pytest

from backtest_engine import strategy_library as lib
from backtest_engine.strategy_config import Condition, SLTPSpec, StrategyConfig
from sindhu_web.api.backtesting import SimilarityCheckRequest, check_strategy_similarity


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


def test_identical_concept_sets_are_100_percent_similar(test_db):
    lib.create(_config("Existing", ["fvg", "order_block", "choch"]))
    warnings = lib.find_similarity_warnings(["fvg", "order_block", "choch"])
    assert warnings[0]["similarity_pct"] == 100.0
    assert warnings[0]["strategy_name"] == "Existing"


def test_below_threshold_is_not_flagged(test_db):
    lib.create(_config("Existing", ["fvg", "order_block", "choch", "pdh"]))
    # Only 1 of 4 concepts shared -- well below the 80% default threshold.
    warnings = lib.find_similarity_warnings(["fvg"])
    assert warnings == []


def test_exact_boundary_at_threshold_is_flagged(test_db):
    lib.create(_config("Existing", ["a", "b", "c", "d", "e"]))
    # 4 of 5 shared = 80% Jaccard exactly.
    warnings = lib.find_similarity_warnings(["a", "b", "c", "d"], threshold_pct=80.0)
    assert len(warnings) == 1


def test_empty_concepts_used_returns_no_warnings(test_db):
    lib.create(_config("Existing", ["fvg"]))
    assert lib.find_similarity_warnings([]) == []


def test_excludes_the_strategy_being_edited_from_comparing_against_itself(test_db):
    sid = lib.create(_config("Self", ["fvg", "order_block"]))
    warnings = lib.find_similarity_warnings(["fvg", "order_block"], exclude_strategy_id=sid)
    assert warnings == []


def test_archived_strategies_are_never_flagged_as_similar(test_db):
    sid = lib.create(_config("Archived", ["fvg", "order_block"]))
    lib.set_archived(sid, True)
    warnings = lib.find_similarity_warnings(["fvg", "order_block"])
    assert warnings == []


def test_warnings_sorted_most_similar_first(test_db):
    lib.create(_config("Close Match", ["a", "b", "c"]))
    lib.create(_config("Exact Match", ["a", "b"]))
    warnings = lib.find_similarity_warnings(["a", "b"], threshold_pct=50.0)
    assert warnings[0]["strategy_name"] == "Exact Match"
    assert warnings[0]["similarity_pct"] == 100.0


def test_endpoint_returns_warnings(test_db):
    lib.create(_config("Existing", ["fvg", "order_block"]))
    result = check_strategy_similarity(SimilarityCheckRequest(concepts_used=["fvg", "order_block"]))
    assert len(result["warnings"]) == 1
    assert result["warnings"][0]["strategy_name"] == "Existing"
