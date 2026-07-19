"""A.4/A.5 -- Generation Manager. Every BOT strategy and BOT lesson is part
of a lineage (BOT_S101 -> BOT_S101_G2 -> BOT_S101_G3, ...); this module is
the only place new lineages/generations get created, so id-format and
"never overwrite, never delete" are enforced in exactly one spot rather than
re-implemented by every caller (mutator, sindhu_strategy generator, lesson
generator).
"""

import re

from data_engine import storage

_STRATEGY_BASE_RE = re.compile(r"^BOT_S(\d+)$")
_LESSON_BASE_RE = re.compile(r"^BOT_L(\d+)$")


def _next_base_id(existing_base_ids, pattern, prefix):
    max_n = 0
    for base_id in existing_base_ids:
        m = pattern.match(base_id)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"{prefix}{max_n + 1:03d}"


def next_strategy_base_id():
    return _next_base_id(storage.list_bot_strategy_base_ids(), _STRATEGY_BASE_RE, "BOT_S")


def next_lesson_base_id():
    return _next_base_id(storage.list_bot_lesson_base_ids(), _LESSON_BASE_RE, "BOT_L")


def create_new_strategy_lineage(name, config_dict, dna_tags, origin, made_with_ai, reason, now_iso, base_id=None):
    """Generation 1 of a brand-new BOT strategy lineage. Used by the SINDHU
    Strategy Generator (Part B) for each of its 11 daily candidates, and by
    the Evolution Engine when a mutation is different enough from its parent
    to be considered a fresh lineage rather than a next generation."""
    base_id = base_id or next_strategy_base_id()
    strategy_id = f"{base_id}_G1"
    storage.create_bot_strategy(
        id=strategy_id, base_id=base_id, generation=1, parent_id=None, name=name,
        config_dict=config_dict, dna_tags=dna_tags, origin=origin,
        made_with_ai=made_with_ai, mutation_reason=reason, now_iso=now_iso,
    )
    return strategy_id


def create_next_strategy_generation(base_id, name, config_dict, dna_tags, origin, made_with_ai, reason, now_iso,
                                     max_generations=None):
    """The next generation in an existing lineage. Returns None (creates
    nothing) if base_id has no prior generation (caller should have used
    create_new_strategy_lineage instead) or if max_generations is already
    reached (A.3 Governor cap) -- both are safe no-ops, never a partial
    write."""
    latest = storage.latest_generation_for_base(base_id)
    if latest is None:
        return None
    if max_generations is not None and latest["generation"] >= max_generations:
        return None
    generation = latest["generation"] + 1
    strategy_id = f"{base_id}_G{generation}"
    storage.create_bot_strategy(
        id=strategy_id, base_id=base_id, generation=generation, parent_id=latest["id"], name=name,
        config_dict=config_dict, dna_tags=dna_tags, origin=origin,
        made_with_ai=made_with_ai, mutation_reason=reason, now_iso=now_iso,
    )
    return strategy_id


def create_new_lesson_lineage(title, category, description, derived_from, conditions, confidence, now_iso, base_id=None):
    base_id = base_id or next_lesson_base_id()
    lesson_id = f"{base_id}_G1"
    storage.create_bot_lesson(
        id=lesson_id, base_id=base_id, generation=1, parent_id=None, title=title, category=category,
        description=description, derived_from=derived_from, conditions=conditions,
        confidence=confidence, now_iso=now_iso,
    )
    return lesson_id


def create_next_lesson_generation(base_id, title, category, description, derived_from, conditions, confidence, now_iso):
    """A.5 -- lesson generations refine accuracy as more data arrives.
    Same lineage id scheme and same "never overwrite" guarantee as
    strategies."""
    latest = storage.latest_generation_for_lesson_base(base_id)
    if latest is None:
        return None
    generation = latest["generation"] + 1
    lesson_id = f"{base_id}_G{generation}"
    storage.create_bot_lesson(
        id=lesson_id, base_id=base_id, generation=generation, parent_id=latest["id"], title=title, category=category,
        description=description, derived_from=derived_from, conditions=conditions,
        confidence=confidence, now_iso=now_iso,
    )
    return lesson_id


def lineage_history(base_id):
    """Every generation ever created for one strategy lineage, oldest
    first -- the full audit trail A.4 requires ("every generation is stored
    permanently")."""
    rows = storage.list_bot_strategies(base_id=base_id, limit=10_000)
    return sorted(rows, key=lambda r: r["generation"])
