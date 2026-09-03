"""Strategy Lineage Explainability (Grand Feature Expansion, Phase 6
Feature 7): raw generation history (generation_manager.lineage_history),
each generation's own mutation_reason, and evolution_comparisons' verdicts
already exist in 3 separate places -- nothing tied them together into one
plain-language "why this strategy is what it is today" narrative. This
module is pure synthesis: it computes nothing new, it only assembles and
writes up what already exists, reusing rollback.effective_generation()
for "which generation is actually active right now" rather than
re-deriving that logic."""

from data_engine import storage
from evolution_engine import generation_manager, rollback


def explain_lineage(base_id):
    generations = generation_manager.lineage_history(base_id)
    if not generations:
        return None

    comparisons = storage.list_evolution_comparisons(base_id=base_id, limit=1000)
    comparison_by_child = {c["child_id"]: c for c in comparisons}

    first = generations[0]
    lines = [
        f"Generation 1 (\"{first['name']}\") was created on {first['created_at'][:10]} "
        f"via {first['origin']}" + (f": {first['mutation_reason']}." if first.get("mutation_reason") else ".")
    ]

    for gen in generations[1:]:
        reason = gen.get("mutation_reason") or "no reason recorded"
        line = f"Generation {gen['generation']} was created on {gen['created_at'][:10]}: {reason}."
        comp = comparison_by_child.get(gen["id"])
        if comp and comp.get("verdict") == "regressed":
            line += " After enough real trades, this generation performed WORSE than its parent and was automatically rolled back."
        elif comp and comp.get("verdict") == "improved":
            line += " After enough real trades, this generation performed better than its parent and was kept."
        elif comp:
            line += " Still waiting for enough real trades to judge whether this change actually helped."
        lines.append(line)

    active = rollback.effective_generation(base_id)
    if active and active["id"] != generations[-1]["id"]:
        lines.append(
            f"The lineage is currently pinned back to generation {active['generation']} "
            f"(a later generation was rolled back for regressing)."
        )
    elif active:
        lines.append(f"Generation {active['generation']} is the current, active version of this lineage.")

    return {
        "base_id": base_id,
        "generation_count": len(generations),
        "active_generation": active["generation"] if active else None,
        "narrative": " ".join(lines),
    }
