"""SINDHU Strategy Generator (Phase 7A, Part B) -- generates entirely new
BOT strategy candidates from scratch, built from the system's accumulated
data (backtest/paper-trading performance, self-generated lessons, DNA
correlations). Distinct from evolution_engine (Part A), which improves
EXISTING BOT strategies across generations -- this package only ever
creates generation-1 lineages.

Hard daily limit: exactly 11 candidates/day (B.1), of which exactly 1 may
use a single AI call and the other 10 are pure deterministic recombination
(B.2) -- enforced structurally by data_engine.storage.
try_reserve_ai_generation_call, not by convention.
"""
