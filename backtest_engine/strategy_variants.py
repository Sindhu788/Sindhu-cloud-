"""Self-Generated Strategy Variants (Grand Feature Expansion, Phase 6
Feature 5): branches multiple PARALLEL sibling variants off ONE existing
strategy and tests them side-by-side as competing candidates in one pass.
Genuinely distinct from sindhu_strategy.deterministic_builder (builds
independent NEW candidates from scratch, unrelated to any one existing
strategy) and evolution_engine.mutator (produces exactly ONE sequential
next generation per lineage per tick, never several siblings at once).

Reuses evolution_engine.dna's own concepts_for_dna() pool -- the exact
same pool deterministic_builder already draws from -- to swap ONE
concept-type entry condition for a different concept from the SAME DNA
category, and the same bounded fast-window in-memory re-run
infrastructure Features 6/14 already established. Deliberately scoped to
concept-type conditions only (never indicator-type, which would need full
indicator re-derivation) -- still a genuine, real sibling-variant
comparison."""

from automation_pipeline import optimizer
from backtest_engine.strategy_config import Condition
from backtest_engine.what_if_simulator import FAST_WINDOW_DAYS, MAX_SYMBOLS
from evolution_engine import dna

MAX_VARIANTS = 4


def _concept_condition_indices(config):
    return [i for i, c in enumerate(config.entry_conditions or []) if c.type == "concept" and c.name]


def generate_variants(strategy_config, max_variants=MAX_VARIANTS):
    """Returns a list of {"label", "config"} sibling variants. Never
    mutates strategy_config -- every variant is a fresh clone with exactly
    one entry condition swapped."""
    indices = _concept_condition_indices(strategy_config)
    if not indices:
        return []

    variants = []
    for idx in indices:
        original_name = strategy_config.entry_conditions[idx].name
        my_tags = [tag for tag in dna.DNA_CATEGORIES if original_name in dna.concepts_for_dna(tag)]
        alternatives = set()
        for tag in my_tags:
            alternatives |= set(dna.concepts_for_dna(tag))
        alternatives.discard(original_name)
        for alt_name in sorted(alternatives):
            if len(variants) >= max_variants:
                return variants
            modified = optimizer._clone_config(strategy_config)
            new_conditions = list(modified.entry_conditions)
            new_conditions[idx] = Condition(type="concept", name=alt_name)
            modified.entry_conditions = new_conditions
            variants.append({"label": f"swap \"{original_name}\" -> \"{alt_name}\"", "config": modified})
    return variants


def test_variants(strategy_config, batch, max_variants=MAX_VARIANTS, max_symbols=3):
    """strategy_config: the CEO's real, currently-saved StrategyConfig --
    never mutated. `batch` borrows a real symbol list + date range to
    replay against, same as what_if_simulator.run_what_if."""
    settings = batch.get("settings") or {}
    symbols = settings.get("symbols") or []
    start_ms, end_ms = settings.get("start_ms"), settings.get("end_ms")
    if not symbols or start_ms is None or end_ms is None:
        return None

    symbols = symbols[:min(max_symbols, MAX_SYMBOLS)]
    windowed_start_ms = max(start_ms, end_ms - FAST_WINDOW_DAYS * 24 * 3600 * 1000)
    exchange = batch["exchange"]

    def _net_profit(config):
        total = 0.0
        for symbol in symbols:
            metrics = optimizer._run_in_memory(config, exchange, symbol, settings, windowed_start_ms, end_ms)
            if metrics:
                total += metrics["net_profit"]
        return total

    baseline_profit = _net_profit(strategy_config)
    variants = generate_variants(strategy_config, max_variants=max_variants)
    if not variants:
        return {
            "baseline_net_profit": round(baseline_profit, 2), "variants": [],
            "symbols": symbols, "window_days": FAST_WINDOW_DAYS,
            "reason": "no concept-type entry condition with a same-DNA-category alternative to swap",
        }

    results = []
    for v in variants:
        profit = _net_profit(v["config"])
        results.append({
            "label": v["label"], "net_profit": round(profit, 2),
            "improvement": round(profit - baseline_profit, 2),
        })
    results.sort(key=lambda r: r["improvement"], reverse=True)
    return {
        "baseline_net_profit": round(baseline_profit, 2), "variants": results,
        "symbols": symbols, "window_days": FAST_WINDOW_DAYS,
    }
