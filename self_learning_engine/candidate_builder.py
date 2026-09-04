"""Phase 1.4: manual StrategyConfig construction for a discovered DNA-tag
combination -- built the same way every other strategy in this project is
built, never via ai_integration/ or strategy_parser.py at runtime.

Reuses sindhu_strategy.deterministic_builder's already-tested condition-
construction helpers (_condition_for, _usable_dna_names, _STRUCTURE_FALLBACK)
rather than re-deriving "how does a concept name become a real Condition" --
that logic already fixed a real bug (numeric indicators silently getting 0
trades when wrapped in a boolean concept condition) and must not be forked.
This module only supplies WHICH combo to build and WHICH concept to draw
from each tag (the discovery/scoring logic itself, combination_scorer.py),
not how to turn a name into a Condition.
"""

from backtest_engine.strategy_config import Condition, SLTPSpec, StrategyConfig
from evolution_engine import dna
from sindhu_strategy import deterministic_builder as det_builder


def build_candidate(dna_combo, timeframe="5m", variant=0):
    """Builds ONE StrategyConfig for a given DNA-tag combo (e.g.
    ["liquidity", "volume"]). `variant` cycles which concept is drawn from
    each tag's pool (pool[variant % len(pool)]) so repeated discovery
    cycles over the same combo don't always propose the identical
    candidate -- duplicate_detector.py is what actually decides whether a
    variant is too similar to something already tried, this just gives it
    something new to compare.

    Returns (config, dna_tags_present, drawn_concepts) -- drawn_concepts is
    used by explainability.py to say plainly which concepts were combined."""
    dna_combo = sorted(dna_combo)
    drawn = []
    for tag in dna_combo:
        pool = det_builder._usable_dna_names(dna.concepts_for_dna(tag))
        if pool:
            drawn.append(pool[variant % len(pool)])
    drawn = sorted(set(drawn)) or ["candle_break"]

    use_structure = bool({"liquidity", "breakout"} & set(dna_combo))
    if use_structure:
        for c in det_builder._STRUCTURE_FALLBACK:
            if c not in drawn:
                drawn.append(c)
        stop_loss = SLTPSpec(type="structure")
    else:
        stop_loss = SLTPSpec(type="atr_multiple", value=1.5)

    conditions, indicators, concepts_used = [], [], []
    for name in drawn:
        cond, indicator_decl, concept_name = det_builder._condition_for(name)
        if cond is None:
            continue
        conditions.append(cond)
        if indicator_decl is not None:
            indicators.append(indicator_decl)
        if concept_name is not None:
            concepts_used.append(concept_name)

    if not conditions:
        conditions = [Condition(type="concept", name="candle_break")]
        concepts_used = ["candle_break"]

    combo_label = "+".join(dna_combo)
    config = StrategyConfig(
        name=f"Self-Learning Candidate ({combo_label}, v{variant})",
        raw_text=(
            f"Auto-discovered by the Self-Learning Engine from DNA combo {dna_combo} "
            f"(concepts drawn: {drawn}, variant {variant}). Manually constructed -- "
            f"no AI call in this step."
        ),
        timeframes={"entry": timeframe},
        indicators=indicators,
        concepts_used=sorted(set(concepts_used)),
        entry_conditions=conditions[:2],
        confirmation_conditions=conditions[2:],
        stop_loss=stop_loss,
        # Phase 1.8's mandatory minimum 1:2 Risk:Reward, satisfied at
        # construction time -- validation_gate.py still checks it again
        # against the ACTUAL realized RR from backtest trades, since a
        # structure-based stop-loss's real RR can differ from this target.
        take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0, risk_reward=2.0,
    )
    dna_tags_present = dna.extract_dna(config)
    return config, dna_tags_present, drawn
