"""B.2 -- the 10 zero-AI daily candidates. Pure deterministic recombination
of DNA blocks (evolution_engine.dna), driven by real correlations already
present in the system's accumulated data: every BOT strategy's own scored
lineage (evolution_engine.mutator.research_dna_correlations) PLUS every
currently-tracked strategy's real paper-trading performance
(data_engine.storage.list_paper_strategy_performance, matched back to its
StrategyConfig via backtest_engine.strategy_library.load -- a READ only,
this module never writes to strategy_library). No AI call anywhere in this
module -- confirmed by the Phase 7A grep audit alongside evolution_engine.
"""

from itertools import combinations

from backtest_engine import strategy_library
from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from data_engine import storage
from evolution_engine import dna, mutator as evo_mutator

MAX_COMBO_SIZE = 2
MIN_SAMPLE = 1
_STRUCTURE_FALLBACK = ("support", "resistance")  # same guaranteed-computable pair validator/prepare_context resolve to


def dna_score_correlations():
    """Best-first list of {dna_combo, avg_score, sample_size}: BOT-lineage
    correlations (evolution_engine.mutator.research_dna_correlations)
    combined with every currently-tracked strategy's real paper-trading
    score, whether that strategy is BOT-owned or user-imported -- the
    system's WHOLE accumulated data, per Part B's goal, not just BOT
    lineages (which are empty on a cold start, before this generator has
    ever run)."""
    buckets = {}
    for c in evo_mutator.research_dna_correlations(min_sample=MIN_SAMPLE, max_combo_size=MAX_COMBO_SIZE):
        buckets.setdefault(tuple(c["dna_combo"]), []).extend([c["avg_score"]] * c["sample_size"])

    for perf in storage.list_paper_strategy_performance():
        try:
            config = strategy_library.load(perf["strategy_id"])
        except Exception:
            continue  # not every strategy_id resolves to a saved config (e.g. lesson-only book) -- skip, don't guess
        tags = tuple(sorted(set(dna.extract_dna(config))))
        if not tags:
            continue
        for size in range(1, MAX_COMBO_SIZE + 1):
            for combo in combinations(tags, size):
                buckets.setdefault(combo, []).append(perf["score"])

    results = [
        {"dna_combo": list(combo), "avg_score": round(sum(scores) / len(scores), 2), "sample_size": len(scores)}
        for combo, scores in buckets.items()
    ]
    results.sort(key=lambda r: -r["avg_score"])
    return results


def _pick_dna_combo(index, correlations):
    """Deterministic selection for daily candidate slot `index` (0-9): the
    index-th best historically-correlated combo. Once real correlations run
    out (cold start, or fewer than 10 distinct combos exist yet), cycles
    through every DNA_CATEGORIES pair so 10 candidates still cover
    different ground instead of repeating combo #1 ten times."""
    if index < len(correlations):
        c = correlations[index]
        return c["dna_combo"], f"historically averages {c['avg_score']} over {c['sample_size']} sample(s)"
    all_pairs = list(combinations(dna.DNA_CATEGORIES, 2))
    combo = list(all_pairs[index % len(all_pairs)])
    return combo, "no scored historical correlation for this slot yet -- cycling through DNA category pairs"


def build_candidate(index, timeframe="5m"):
    """Builds ONE deterministic (zero-AI) StrategyConfig for daily slot
    `index`. Returns (config_dict, dna_tags, reason) -- `reason` records
    exactly which correlation (or cold-start rule) produced this candidate,
    so it's traceable rather than a black box, matching the same
    traceability discipline as A.1's lesson generator."""
    correlations = dna_score_correlations()
    combo, reason = _pick_dna_combo(index, correlations)

    concepts_used = []
    for tag in combo:
        pool = dna.concepts_for_dna(tag)
        if pool:
            concepts_used.append(pool[index % len(pool)])
    concepts_used = sorted(set(concepts_used)) or ["candle_break"]

    use_structure = bool({"liquidity", "breakout"} & set(combo))
    if use_structure:
        for c in _STRUCTURE_FALLBACK:
            if c not in concepts_used:
                concepts_used.append(c)
        stop_loss = SLTPSpec(type="structure")
    else:
        stop_loss = SLTPSpec(type="atr_multiple", value=1.5)

    entry_conditions = [Condition(type="concept", name=c) for c in concepts_used[:2]] or \
        [Condition(type="concept", name=concepts_used[0])]
    confirmation_conditions = [Condition(type="concept", name=c) for c in concepts_used[2:]]

    config = StrategyConfig(
        name=f"SINDHU Deterministic Candidate #{index + 1}",
        raw_text=f"Auto-generated (zero-AI) from DNA blocks {combo}: {reason}",
        timeframes={"entry": timeframe},
        concepts_used=concepts_used,
        entry_conditions=entry_conditions,
        confirmation_conditions=confirmation_conditions,
        stop_loss=stop_loss,
        take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0, risk_reward=2.0,
    )
    dna_tags = dna.extract_dna(config)
    return config.to_dict(), dna_tags, f"DNA combo {combo} ({reason})"
