"""Master Task 3, Phase 1.4: self_learning_engine/candidate_builder.py --
manual StrategyConfig construction from a discovered DNA combo, reusing
sindhu_strategy.deterministic_builder's condition-construction helpers.
"""

from backtest_engine.validator import validate
from evolution_engine import dna
from self_learning_engine import candidate_builder


def test_build_candidate_produces_a_valid_config():
    config, tags, drawn = candidate_builder.build_candidate(["liquidity", "volume"])
    errors = validate(config)
    assert errors == [], f"candidate failed validation: {errors}"


def test_build_candidate_meets_minimum_1_to_2_risk_reward():
    config, tags, drawn = candidate_builder.build_candidate(["breakout", "momentum"])
    assert config.take_profit.type == "rr"
    assert config.take_profit.value >= 2.0
    assert config.risk_reward >= 2.0


def test_build_candidate_dna_tags_include_the_requested_combo():
    config, tags, drawn = candidate_builder.build_candidate(["liquidity", "session"])
    assert "liquidity" in tags
    assert "session" in tags


def test_variant_cycles_through_different_concepts_for_a_multi_concept_tag():
    # "liquidity" has many concepts (support, resistance, order_block, ...) --
    # different variants must be able to draw different ones.
    pool_size = len(dna.concepts_for_dna("liquidity"))
    assert pool_size > 1
    _, _, drawn_a = candidate_builder.build_candidate(["liquidity", "volume"], variant=0)
    _, _, drawn_b = candidate_builder.build_candidate(["liquidity", "volume"], variant=1)
    assert drawn_a != drawn_b or pool_size <= 1


def test_no_ai_call_anywhere_in_this_module():
    import self_learning_engine.candidate_builder as mod
    assert not hasattr(mod, "ai_integration")
    assert "ai_integration" not in mod.__dict__
    assert "strategy_parser" not in mod.__dict__
