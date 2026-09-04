"""Phase 1.9 (duplicate-idea detector) + Phase 1.11 (persistent rejected-idea
memory) -- combined here because both answer the same underlying question
before building/re-testing a candidate: "has this genuinely been tried
before, or is this too similar to something that already exists?"

Two independent checks, per Phase 1.9's own wording:
  (a) genuine similarity against all currently-saved strategies' actual
      rule structure -- reuses backtest_engine.strategy_library.
      find_similarity_warnings (fuzzy Jaccard over concepts_used), the
      SAME "before you build something 80%+ identical" check the rest of
      the project already uses elsewhere. Not name-matching.
  (b) a persistent log of previously-rejected combinations -- new
      data_engine.storage.self_learning_attempts table, checked before a
      new candidate for the same DNA combo is proposed.
"""

from backtest_engine import strategy_library
from data_engine import storage

# A combo rejected for being unprofitable is worth retrying only once
# meaningfully more paper-trading/BOT-lineage data has accumulated -- not on
# every single weekly cycle. This is intentionally generous (Phase 1.10's
# weekly cap already limits how often a full cycle runs at all), so this
# exists mainly to stop the SAME combo+concepts being proposed twice in a
# row within one cycle's retry loop, not to gate across many weeks.
REVISIT_AFTER_ATTEMPTS = 1


def check_duplicate_against_library(concepts_used, exclude_strategy_id=None):
    """Part (a): real rule-structure similarity against every saved
    strategy. Returns the similarity-warnings list unchanged (empty = no
    genuine duplicate found)."""
    return strategy_library.find_similarity_warnings(concepts_used, exclude_strategy_id=exclude_strategy_id)


def has_been_rejected_before(dna_combo, concepts_drawn):
    """Part (b): True if this EXACT combo+concepts pairing was already
    proposed and rejected -- a candidate_builder variant cycle should move
    on to a different variant rather than re-test something already known
    not to work, without a genuinely new reason (more accumulated data) to
    revisit it."""
    matches = storage.find_matching_self_learning_attempts(dna_combo, concepts_drawn=concepts_drawn)
    rejected = [m for m in matches if m["outcome"] == "rejected"]
    return len(rejected) >= REVISIT_AFTER_ATTEMPTS


def attempt_count_for_combo(dna_combo):
    """How many times (any concepts/variant) this DNA combo has been
    attempted at all -- used by the discovery cycle to decide whether to
    keep cycling variants of the same combo or move to the next-best one."""
    return len(storage.find_matching_self_learning_attempts(dna_combo))


def record_outcome(attempt_id, dna_combo, concepts_drawn, variant, outcome, reason, now_iso,
                    strategy_id=None, discovery_metrics=None, validation_metrics=None):
    """Single write-through to the persistent log -- every candidate this
    engine ever builds gets one row here, accepted or rejected alike, per
    Phase 1.11's explicit requirement to never hide a rejection."""
    storage.record_self_learning_attempt(
        attempt_id, dna_combo, concepts_drawn, variant, outcome, reason, now_iso,
        strategy_id=strategy_id, discovery_metrics=discovery_metrics, validation_metrics=validation_metrics,
    )


def attempt_history(limit=500):
    return storage.list_self_learning_attempts(limit=limit)
