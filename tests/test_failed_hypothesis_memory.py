"""Grand Feature Expansion, Phase 6 Feature 3: Failed Hypothesis Memory
(evolution_engine/failed_hypothesis_memory.py) -- wires evolution_engine.
dna.dna_overlap() (previously written but never called anywhere) into the
generation pipeline so a new candidate too similar to a past-regressed
lineage is skipped rather than knowingly repeated. The regressed-lineage
record itself (evolution_comparisons, verdict="regressed") already
existed; what was missing was ever reading it.
"""

from datetime import datetime, timezone

from data_engine import storage
from evolution_engine import failed_hypothesis_memory, generation_manager
from sindhu_strategy import generator as generator_mod

CONFIG = {"risk_reward": 2.0, "risk_pct": 1.0, "entry_timeframe": "5m"}


def _seed_regressed_lineage(dna_tags, now_iso="2026-01-01T00:00:00+00:00"):
    base_id = generation_manager.create_new_strategy_lineage(
        "Parent", CONFIG, dna_tags, "sindhu_deterministic", False, "seed", now_iso,
    )
    child_id = generation_manager.create_new_strategy_lineage(
        "Child", CONFIG, dna_tags, "sindhu_deterministic", False, "mutation", now_iso, base_id=base_id,
    )
    comp_id = storage.create_evolution_comparison(base_id, base_id, child_id, 100, {"win_rate": 60.0}, now_iso)
    storage.finalize_evolution_comparison(comp_id, {"win_rate": 30.0}, "regressed", True, now_iso)
    return child_id


def test_empty_history_matches_nothing(test_db):
    assert failed_hypothesis_memory.regressed_dna_history() == []
    assert failed_hypothesis_memory.matches_a_known_failure(["trend", "momentum"]) is None


def test_regressed_lineage_is_recorded_in_history(test_db):
    child_id = _seed_regressed_lineage(["trend", "momentum", "risk"])
    history = failed_hypothesis_memory.regressed_dna_history()
    assert len(history) == 1
    assert history[0]["child_id"] == child_id
    assert history[0]["dna"] == ["momentum", "risk", "trend"] or sorted(history[0]["dna"]) == ["momentum", "risk", "trend"]


def test_improved_lineage_is_never_counted_as_a_failure(test_db):
    base_id = generation_manager.create_new_strategy_lineage(
        "Parent", CONFIG, ["trend"], "sindhu_deterministic", False, "seed", "2026-01-01T00:00:00+00:00",
    )
    child_id = generation_manager.create_new_strategy_lineage(
        "Child", CONFIG, ["trend"], "sindhu_deterministic", False, "mutation", "2026-01-01T00:00:00+00:00", base_id=base_id,
    )
    comp_id = storage.create_evolution_comparison(base_id, base_id, child_id, 100, {"win_rate": 30.0}, "2026-01-01T00:00:00+00:00")
    storage.finalize_evolution_comparison(comp_id, {"win_rate": 60.0}, "improved", False, "2026-01-01T00:00:00+00:00")
    assert failed_hypothesis_memory.regressed_dna_history() == []


def test_high_overlap_candidate_matches_a_known_failure(test_db):
    _seed_regressed_lineage(["trend", "momentum", "risk"])
    match = failed_hypothesis_memory.matches_a_known_failure(["trend", "momentum", "risk", "volume"])
    assert match is not None
    assert sorted(match["overlap"]) == ["momentum", "risk", "trend"]


def test_low_overlap_candidate_does_not_match(test_db):
    _seed_regressed_lineage(["trend", "momentum", "risk"])
    match = failed_hypothesis_memory.matches_a_known_failure(["trend", "volume"])
    assert match is None


def test_generator_skips_a_candidate_matching_a_known_failure(test_db, monkeypatch):
    _seed_regressed_lineage(["trend", "momentum", "risk"])

    call_log = []
    real_build = generator_mod.deterministic_builder.build_candidate

    def spy_build(index, timeframe="5m"):
        config_dict, dna_tags, reason = real_build(index, timeframe=timeframe)
        call_log.append(index)
        # Force the very first index to look exactly like the known
        # failure, regardless of what the real deterministic builder drew.
        if index == 0:
            dna_tags = ["trend", "momentum", "risk"]
        return config_dict, dna_tags, reason

    monkeypatch.setattr(generator_mod.deterministic_builder, "build_candidate", spy_build)
    monkeypatch.setattr(generator_mod, "DAILY_CAP", 1)
    # Neutralize the AI-assisted slot (would otherwise attempt a real AI
    # call) -- the exception is already caught by generate_daily_candidates
    # itself, same as a genuine AI failure, falling through to the
    # deterministic loop this test is actually about.
    monkeypatch.setattr(generator_mod.ai_builder, "build_ai_candidate",
                         lambda: (_ for _ in ()).throw(RuntimeError("no AI in tests")))

    created = generator_mod.generate_daily_candidates(now_iso="2026-02-01T00:00:00+00:00")
    assert len(created) == 1
    # Index 0 was skipped (matched a known failure) -- the created
    # candidate must have come from a later index.
    assert call_log[0] == 0
    assert len(call_log) > 1
