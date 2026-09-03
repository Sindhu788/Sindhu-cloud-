"""Failed Hypothesis Memory (Grand Feature Expansion, Phase 6 Feature 3):
evolution_engine/rollback.py already permanently records every regressed
mutation (evolution_comparisons rows, verdict="regressed") -- that memory
already existed. What was missing: nothing ever READ it before generating
a new hypothesis, so the exact same already-failed idea could be proposed
again with no memory of it. evolution_engine/dna.py's dna_overlap() was
already written specifically for this ("avoid producing a near-duplicate
of an existing lineage") but had zero callers anywhere in the codebase.

This module wires that existing function into the generation pipeline as
an advisory filter -- generation-time analysis, not a live-trade
execution gate, so it can skip/avoid a candidate outright rather than
merely warn."""

from data_engine import storage
from evolution_engine import dna

DUPLICATE_OVERLAP_THRESHOLD = 3  # 3+ shared DNA tags counts as "too similar to a known failure"


def regressed_dna_history(limit=500):
    """DNA tags of every generation that was ever rolled back for
    regressing. Reads the DNA already stored on each regressed
    bot_strategy row (never recomputed -- see storage.create_bot_strategy's
    dna_tags) rather than re-deriving it from the raw config."""
    comparisons = [c for c in storage.list_evolution_comparisons(limit=limit) if c["verdict"] == "regressed"]
    history = []
    for comp in comparisons:
        child = storage.get_bot_strategy(comp["child_id"])
        if child and child.get("dna"):
            history.append({"child_id": comp["child_id"], "dna": child["dna"]})
    return history


def matches_a_known_failure(candidate_dna, history=None):
    """Returns the first past-regressed lineage this candidate overlaps
    with at or above DUPLICATE_OVERLAP_THRESHOLD, or None. Checked against
    a supplied `history` (regressed_dna_history()'s own shape) when given,
    to avoid re-querying the database once per candidate in a tight loop."""
    history = history if history is not None else regressed_dna_history()
    for entry in history:
        overlap = dna.dna_overlap(candidate_dna, entry["dna"])
        if len(overlap) >= DUPLICATE_OVERLAP_THRESHOLD:
            return {"child_id": entry["child_id"], "overlap": overlap}
    return None
