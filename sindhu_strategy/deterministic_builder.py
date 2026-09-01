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


# --------------------------------------------------------------------------
# Numeric indicators drawn from a DNA pool used to be wrapped in
# `Condition(type="concept", name=...)`, which reads a boolean EVENT column.
# `ema`/`sma`/`vwap`/`macd`/`rsi`/`atr`/`volume` have no such column, so those
# conditions could never be True -- 102 of the 132 already-saved candidates
# carry one. Confirmed on a real backtest of Candidate #1 over 120,650
# AAVEUSDT 5m bars: its own condition report read
# `aggression (within 10 bars)=60474, ema (within 10 bars)=0` -- the boolean
# concept fired 60k times, the EMA "concept" literally never.
#
# Each numeric indicator is now emitted as the condition type it actually
# needs. `dna._CONCEPT_DNA` is deliberately left alone: a strategy holding an
# EMA genuinely has "trend" DNA, so `extract_dna()` must keep seeing these
# names.

# CEO-approved standard default: price ABOVE the moving average is a
# bullish/buy-side bias, price BELOW it is bearish/sell-side. These are all
# price-LEVEL indicators, so comparing price against them is meaningful.
_PRICE_LEVEL_INDICATORS = {"ema": 20, "sma": 20, "vwap": None}

# RSI is not a price level, so the price-vs-level rule cannot apply to it.
# Its own universal standard default is the 30/70 oversold/overbought pair;
# the bullish/buy-side half is "oversold", matching the bullish bias the
# builder produces by default (see _infer_direction).
_RSI_OVERSOLD = 30.0

# MACD is not a price level either, but it already has real, implemented
# boolean event concepts in the engine -- reuse one rather than invent a
# comparison. Verified firing on real data: 6,393 hits over 17,281 bars.
_EVENT_CONCEPT_FOR = {"macd": "macd_signal_cross"}

# ATR (volatility) and volume (participation) carry no direction at all, so
# there is no standard bullish/bearish default to apply. Excluded rather than
# guessed at.
_NON_DIRECTIONAL_INDICATORS = {"atr", "volume"}


def _condition_for(name):
    """Turn one drawn DNA name into (condition, indicator_declaration,
    concept_name). Exactly one of `condition` is always returned; the other
    two are None when not applicable. Returns (None, None, None) for a name
    with no honest directional meaning."""
    if name in _PRICE_LEVEL_INDICATORS:
        period = _PRICE_LEVEL_INDICATORS[name]
        params = {"period": period} if period else {}
        # "price above the moving average = bullish bias"
        return (Condition(type="price_compare", indicator=name, params=dict(params), op=">"),
                {"name": name, "params": dict(params), "role": "entry"},
                None)
    if name == "rsi":
        return (Condition(type="indicator_compare", indicator="rsi", params={"period": 14},
                          op="<", value=_RSI_OVERSOLD),
                {"name": "rsi", "params": {"period": 14}, "role": "entry"},
                None)
    if name in _EVENT_CONCEPT_FOR:
        concept = _EVENT_CONCEPT_FOR[name]
        return (Condition(type="concept", name=concept, direction="bullish"),
                {"name": name, "params": {}, "role": "entry"},
                concept)
    if name in _NON_DIRECTIONAL_INDICATORS:
        return (None, None, None)
    # Everything else is already a real boolean event concept.
    return (Condition(type="concept", name=name), None, name)


def _usable_dna_names(pool):
    """Drop only the names that have no honest directional meaning at all
    (ATR, volume). Everything else is now genuinely usable -- see
    _condition_for."""
    return [name for name in pool if name not in _NON_DIRECTIONAL_INDICATORS]


def build_candidate(index, timeframe="5m"):
    """Builds ONE deterministic (zero-AI) StrategyConfig for daily slot
    `index`. Returns (config_dict, dna_tags, reason) -- `reason` records
    exactly which correlation (or cold-start rule) produced this candidate,
    so it's traceable rather than a black box, matching the same
    traceability discipline as A.1's lesson generator."""
    correlations = dna_score_correlations()
    combo, reason = _pick_dna_combo(index, correlations)

    drawn = []
    for tag in combo:
        pool = _usable_dna_names(dna.concepts_for_dna(tag))
        if pool:
            drawn.append(pool[index % len(pool)])
    drawn = sorted(set(drawn)) or ["candle_break"]

    use_structure = bool({"liquidity", "breakout"} & set(combo))
    if use_structure:
        for c in _STRUCTURE_FALLBACK:
            if c not in drawn:
                drawn.append(c)
        stop_loss = SLTPSpec(type="structure")
    else:
        stop_loss = SLTPSpec(type="atr_multiple", value=1.5)

    # Each drawn name becomes the condition TYPE it actually needs -- a
    # price_compare for a moving average, an indicator_compare for RSI, a
    # real event concept otherwise (see _condition_for). Previously every
    # name was forced into a boolean concept condition, which silently
    # guaranteed 0 trades for any candidate that drew a numeric indicator.
    conditions, indicators, concepts_used = [], [], []
    for name in drawn:
        cond, indicator_decl, concept_name = _condition_for(name)
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

    entry_conditions = conditions[:2]
    confirmation_conditions = conditions[2:]

    config = StrategyConfig(
        name=f"SINDHU Deterministic Candidate #{index + 1}",
        raw_text=f"Auto-generated (zero-AI) from DNA blocks {combo}: {reason}",
        timeframes={"entry": timeframe},
        indicators=indicators,
        concepts_used=sorted(set(concepts_used)),
        entry_conditions=entry_conditions,
        confirmation_conditions=confirmation_conditions,
        stop_loss=stop_loss,
        take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0, risk_reward=2.0,
    )
    dna_tags = dna.extract_dna(config)
    return config.to_dict(), dna_tags, f"DNA combo {combo} ({reason})"
