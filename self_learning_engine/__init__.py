"""Master Task 3, Phase 1: the Self-Learning Engine.

IMPORTANT DISTINCTION from evolution_engine (per this task's own spec): the
Evolution Engine makes small tweaks to individual EXISTING strategies (e.g.
adjusting an SL buffer). This package discovers entirely NEW candidate
strategies by combining existing proven concepts in new ways. It is a
genuinely separate system -- it never imports evolution_engine.engine (the
Governor/tick-loop), and evolution_engine never imports this package.

Reuses existing primitives throughout rather than rebuilding them:
evolution_engine.dna (the concept/DNA vocabulary), evolution_engine.mutator.
research_dna_correlations (BOT-lineage scoring), sindhu_strategy.
deterministic_builder's condition-construction helpers, backtest_engine.
validator/runner/strategy_library (the real backtest pipeline),
backtest_engine.strategy_library.find_similarity_warnings (structural
duplicate detection), paper_trading.pattern_stats (the 25-trade Wilson
gate threshold), and evolution_engine.governor.Governor (resource limits).

LOCAL-ONLY: like the rest of the backtest pipeline, this package requires
the full local historical database and is never imported by cloud_runtime/
app.py (the lightweight cloud runner) -- see that module's own docstring
for the same scope boundary backtest_engine/evolution_engine already
observe.
"""
