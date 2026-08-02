"""Quality Check -- runs just before saving. Deduplicates rules, merges
repeated concept mentions to their canonical form, flags conflicting
conditions, and produces a stable "DNA" fingerprint for strategies and
lessons so two differently-worded pastes of the same idea converge to the
same identity instead of piling up as separate duplicate records.
"""

import hashlib
import re

from knowledge_compiler import dictionary


def _condition_key(cond):
    params_key = tuple(sorted(cond.params.items())) if cond.params else ()
    params2_key = tuple(sorted(cond.params2.items())) if getattr(cond, "params2", None) else ()
    text_key = cond.text.strip().lower() if cond.type == "raw" and cond.text else None
    return (cond.type, cond.indicator, params_key, cond.op, cond.value, cond.name, cond.direction,
            text_key, getattr(cond, "indicator2", None), params2_key)


def dedupe_conditions(conditions):
    seen = set()
    result = []
    for c in conditions:
        key = _condition_key(c)
        if key in seen:
            continue
        seen.add(key)
        result.append(c)
    return result


def dedupe_rules(config):
    """Mutates `config` in place, removing exact-duplicate conditions within
    each bucket (entry/long/short/exit/confirmation). Returns it for chaining."""
    config.entry_conditions = dedupe_conditions(config.entry_conditions)
    config.long_entry_conditions = dedupe_conditions(config.long_entry_conditions)
    config.short_entry_conditions = dedupe_conditions(config.short_entry_conditions)
    config.exit_conditions = dedupe_conditions(config.exit_conditions)
    config.confirmation_conditions = dedupe_conditions(config.confirmation_conditions)
    return config


def merge_concepts(concepts_used):
    """Canonicalizes and deduplicates a concepts_used list, preserving order."""
    merged = []
    for c in concepts_used:
        canonical = dictionary.normalize_term(c)
        if canonical not in merged:
            merged.append(canonical)
    return merged


def detect_conflicts(config):
    """Trivial, deterministic contradiction check: the same indicator/concept
    referenced with opposite comparison directions inside the SAME bucket
    (e.g. "close above EMA50" and "close below EMA50" both required as entry
    conditions). Reports the conflict -- never auto-resolves it."""
    conflicts = []
    for bucket_name in ("entry_conditions", "long_entry_conditions", "short_entry_conditions", "exit_conditions"):
        bucket = getattr(config, bucket_name)

        by_indicator_op = {}
        for c in bucket:
            key = c.indicator
            if not key or c.op not in (">", "<"):
                continue
            by_indicator_op.setdefault(key, set()).add(c.op)
        for key, ops in by_indicator_op.items():
            if ">" in ops and "<" in ops:
                conflicts.append(
                    f"Conflicting conditions in {bucket_name.replace('_', ' ')}: "
                    f"'{key}' required both above and below in the same rule set."
                )

        by_concept_dir = {}
        for c in bucket:
            if c.type == "concept" and c.direction:
                by_concept_dir.setdefault(c.name, set()).add(c.direction)
        for name, dirs in by_concept_dir.items():
            if "bullish" in dirs and "bearish" in dirs:
                conflicts.append(
                    f"Conflicting conditions in {bucket_name.replace('_', ' ')}: "
                    f"'{name}' required both bullish and bearish in the same rule set."
                )
    return conflicts


def _normalized_text(text):
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def strategy_dna(config):
    """Stable fingerprint: two differently-worded pastes describing the
    identical rule set converge to the same DNA once normalized/sorted.
    Falls back to normalized raw text when no conditions were extracted at
    all -- otherwise every empty/near-empty parse would collide on the same
    fingerprint regardless of what the CEO actually pasted."""
    has_conditions = config.entry_conditions or config.exit_conditions or config.confirmation_conditions
    if not has_conditions:
        return hashlib.sha256(("rawtext::" + _normalized_text(config.raw_text)).encode("utf-8")).hexdigest()[:16]

    parts = []
    for bucket_name in ("entry_conditions", "exit_conditions", "confirmation_conditions"):
        keys = sorted(str(_condition_key(c)) for c in getattr(config, bucket_name))
        parts.append(f"{bucket_name}:{'|'.join(keys)}")
    parts.append(f"sl:{config.stop_loss.type}:{config.stop_loss.value}")
    parts.append(f"tp:{config.take_profit.type}:{config.take_profit.value}")
    parts.append(f"risk:{config.risk_pct}:{config.risk_reward}")
    parts.append(f"tf:{sorted(config.timeframes.items())}")
    blob = "||".join(parts)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def lesson_dna(lesson):
    """Condition-based fingerprint for enforceable lessons (wording-independent
    -- two differently-phrased versions of the same executable rule collapse
    to one DNA). Falls back to normalized description text for non-enforceable
    (pure prose) lessons, since there's no structural rule to fingerprint and
    category+rule_type alone is far too coarse -- it would treat every
    unrelated Psychology tip with no detected direction as one "duplicate"."""
    keys = sorted(str(_condition_key(c)) for c in lesson.conditions)
    if keys:
        blob = f"{lesson.category}||{lesson.rule_type}||{lesson.direction}||{'|'.join(keys)}"
    else:
        blob = f"{lesson.category}||nodna||{_normalized_text(lesson.description)}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def find_duplicate_strategy(dna, library_list_all, library_load):
    """Read-only scan of the Knowledge Library for a strategy sharing the
    same DNA. Returns its id, or None."""
    for meta in library_list_all():
        try:
            existing = library_load(meta["id"])
        except Exception:
            continue
        if strategy_dna(existing) == dna:
            return meta["id"]
    return None


def find_duplicate_strategy_groups(library_list_all, library_load, include_archived=False):
    """Batch 4, Task 3 -- Duplicate Strategy Cleanup. Groups every strategy
    currently in the Knowledge Library by the SAME strategy_dna() already
    used at import time to block exact re-saves (no new/fuzzy detection
    algorithm here, deliberately -- this only surfaces what that existing
    logic already considers identical). Returns [{"dna": str, "strategy_ids": [id, ...]}]
    for every DNA shared by 2 or more strategies; singletons are omitted.

    `include_archived` controls whether already-archived strategies count
    toward a group -- False (the default) so a group the CEO has already
    resolved down to one active copy stops showing up as still-a-problem."""
    by_dna = {}
    for meta in library_list_all():
        if not include_archived and meta.get("archived"):
            continue
        try:
            config = library_load(meta["id"])
        except Exception:
            continue
        by_dna.setdefault(strategy_dna(config), []).append(meta["id"])
    return [
        {"dna": dna, "strategy_ids": ids}
        for dna, ids in by_dna.items()
        if len(ids) >= 2
    ]


def searchable_tags(doc_type, concepts_used, timeframes=None, direction=None, category=None):
    tags = list(dict.fromkeys(concepts_used))
    if doc_type:
        tags.append(doc_type.lower())
    if timeframes:
        tags.extend(sorted(set(timeframes.values())))
    if direction:
        tags.append(direction)
    if category:
        tags.append(category.lower())
    return list(dict.fromkeys(tags))
