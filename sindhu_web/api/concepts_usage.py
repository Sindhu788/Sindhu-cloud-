"""Concepts Library -- "Strategies Using This Concept" cross-reference
(purely additive to the existing read-only /static/concepts.html page, no
new page/nav entry). Read-only: never modifies strategy data or the
concepts_reference.json content, only reads both and joins them.

Matching rule: a strategy counts as using a Concepts Library entry only if
one of that entry's own concepts_used keys (see _CONCEPT_KEYS below)
literally appears in that strategy's real StrategyConfig.concepts_used list
-- never guessed from the strategy's NAME. This is a deliberately literal
match: a strategy whose composite concept (e.g. "pdhl_mtf_reversal") is
built ON TOP OF a primitive (previous_day_high_low) without that primitive's
own key ("pdh"/"pdl") also appearing in concepts_used will NOT be counted
for that primitive's card, even though it clearly uses the idea -- flagged
here rather than silently "fixed" by guessing, since the task's own
instruction is to read the strategy's actual stored data, not its name."""

from fastapi import APIRouter

from backtest_engine import strategy_library

router = APIRouter()

# Concepts Library display name -> the concepts_used string key(s) that
# represent it in a real StrategyConfig. Built by reading exactly which
# concepts.py primitive/composite backs each Concepts Library entry (see
# ConfiguredStrategy._compute_concept_columns) -- e.g. pin_bar() IS Hammer
# (bull) / Shooting Star (bear), so both "candlestick_patterns" (the
# Candlestick Pattern Reversal Strategy's own umbrella concept, which also
# calls pin_bar() internally) and the plain "pin_bar" key used directly by
# other strategies count toward Hammer/Shooting Star.
_CONCEPT_KEYS = {
    "Doji": ["candlestick_patterns"],
    "Hammer": ["candlestick_patterns", "pin_bar"],
    "Inverted Hammer": [],  # reference doc's own note: "related, not built as a full concept here"
    "Shooting Star": ["candlestick_patterns", "pin_bar"],
    "Hanging Man": [],  # reference doc's own note: "related, not built as a full concept here"
    "Spinning Top": [],  # not yet defined, no engine primitive
    "Bullish Engulfing": ["engulfing"],
    "Bearish Engulfing": ["engulfing"],
    "Tweezer Top": [],  # not yet defined, no engine primitive
    "Tweezer Bottom": [],  # not yet defined, no engine primitive
    "Morning Star": ["candlestick_patterns"],
    "Evening Star": ["candlestick_patterns"],
    "Three White Soldiers": [],  # "defined" in the reference doc, but no concepts.py primitive/key exists for it yet
    "Three Black Crows": [],  # same as above
    "Support & Resistance": ["support", "resistance"],
    "Liquidity Sweep": ["liquidity_sweep"],
    "Equal Highs/Lows": ["equal_highs_lows"],
    "Previous High/Low": ["pdh", "pdl"],
    "Fair Value Gap (FVG)": ["fvg"],
    "Order Block (OB)": ["order_block"],
    "Market Structure Shift (MSS) / Change of Character (CHoCH)": ["choch", "mss_reversal"],
    "Premium & Discount": ["premium_discount_zone"],
}


@router.get("/api/concepts/usage")
def get_concepts_usage():
    active = [s for s in strategy_library.list_all() if not s.get("archived")]
    configs = []
    for meta in active:
        cfg = strategy_library.load(meta["id"])
        configs.append((meta["name"], set(cfg.concepts_used or [])))

    usage = {}
    for concept_name, keys in _CONCEPT_KEYS.items():
        matched = sorted({name for name, used in configs if used & set(keys)})
        usage[concept_name] = {"count": len(matched), "strategies": matched}
    return {"total_active_strategies": len(active), "usage": usage}


@router.get("/api/concepts/family-tree")
def get_strategy_family_tree():
    """Grand Feature Expansion, Phase 4 Feature 1: Strategy Family Tree --
    strategies GROUPED by their shared Concepts Library entry, the inverse
    presentation of get_concepts_usage() above (concept -> strategies).
    Reuses the exact same matching data -- never re-derived -- filtered to
    genuine families (2+ member strategies; a single-strategy "family"
    isn't really one) and sorted largest-first. Also reports strategies
    that belong to NO family yet, so this doubles as "which strategies
    aren't clustered with anything" visibility."""
    usage_result = get_concepts_usage()
    usage = usage_result["usage"]

    families = [
        {"concept": name, "member_count": data["count"], "strategies": data["strategies"]}
        for name, data in usage.items() if data["count"] >= 2
    ]
    families.sort(key=lambda f: f["member_count"], reverse=True)

    all_active_names = {s["name"] for s in strategy_library.list_all() if not s.get("archived")}
    grouped_names = {name for f in families for name in f["strategies"]}
    ungrouped = sorted(all_active_names - grouped_names)

    return {
        "families": families, "ungrouped_strategies": ungrouped,
        "total_active_strategies": usage_result["total_active_strategies"],
    }
