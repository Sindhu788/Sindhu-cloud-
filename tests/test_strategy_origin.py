"""Master 15-Item task, Item 5: Strategy Origin Clarity Check."""
from sindhu_web.api.backtesting import _compute_strategy_origin
from self_learning_engine.discovery_cycle import DISCOVERED_STRATEGY_TAG


def test_self_learning_tag_maps_to_self_learning_generated():
    meta = {"tags": ["concept_based_strategy", DISCOVERED_STRATEGY_TAG]}
    assert _compute_strategy_origin(meta) == "Self-Learning-Generated"


def test_manual_build_tag_maps_to_manual():
    meta = {"tags": ["manual_build", "new_batch_5"]}
    assert _compute_strategy_origin(meta) == "Manual"


def test_no_tags_at_all_defaults_to_manual():
    """No third origin is possible in this data source (Evolution never
    writes into strategy_library) -- absence of the self-learning tag
    means Manual, not an unknown/guessed value."""
    meta = {"tags": []}
    assert _compute_strategy_origin(meta) == "Manual"


def test_missing_tags_key_does_not_raise():
    assert _compute_strategy_origin({}) == "Manual"
