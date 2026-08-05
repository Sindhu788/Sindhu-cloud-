"""Strategy Wizard: a second, independent path into the exact same
StrategyConfig the free-text parser (strategy_parser.py) produces --
guided, form-based, zero interpretation. Two rules govern every function
here and may never be violated:

1. NEVER GUESS. Every value this module stores comes directly from an
   explicit field in `wizard_data` (a user selection or user-typed text).
   Nothing here infers meaning from prose the way strategy_parser.py does.
2. NEVER REJECT. A condition that doesn't fit a known concept always saves
   -- as a `Condition(type="raw", manual_review=True, raw_source=...)` --
   rather than blocking the wizard. See has_manual_review() /
   list_manual_review_conditions() for how those get surfaced and
   enforced (blocked from running, never silently executed) at the same
   choke point the existing Incomplete Lock uses.

`build_strategy_config(wizard_data)` is the single entry point: a pure
function, no I/O, no AI calls -- any AI-assisted "does this match an
existing concept?" classification happens BEFORE this is called (see
sindhu_web/api/wizard.py's classify-other endpoint) and its result is
just another explicit field on the condition spec (`matched_concept`),
never re-interpreted here.
"""

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine.validator import known_indicator_names, parameterized_indicator_names

DIRECTION_MODES = {"long_only", "short_only", "both_mirror", "both_independent"}

# SLTPSpec types the engine actually knows how to compute (configured_strategy.py
# ConfiguredStrategy._compute_stop_loss/_compute_take_profit) -- a Wizard SL/TP
# type that maps to one of these is real, executable structure; anything else
# ("Fixed Points" has no engine support today, and adding it would mean
# touching core PnL/execution logic, out of scope for this feature) goes
# through the Other/manual-review path instead of silently producing a
# SLTPSpec the engine will never fill.
_SL_TYPE_MAP = {
    "fixed_pct": "fixed_pct",
    "atr_multiple": "atr_multiple",
    "structure": "structure",
    "signal_candle": "signal_candle",
}
_TP_TYPE_MAP = {
    "fixed_pct": "fixed_pct",
    "rr": "rr",
    "structure": "structure",
    "level": "level",
}

_DIRECTION_FLIP = {"bullish": "bearish", "bearish": "bullish", "up": "down", "down": "up"}
_OP_FLIP = {">": "<", "<": ">", ">=": "<=", "<=": ">="}


def known_concept_catalog():
    """The engine's real, current condition vocabulary, split into the two
    shapes the Wizard's Step 2/3/7 condition builder needs: concept names
    (direction/role/lookback -- BOS, FVG, order blocks, ...) and
    parameterized indicator names (a numeric period plus an optional
    threshold -- EMA, RSI, ...). Read live from validator.py so this can
    never drift out of sync with what the backtest engine actually
    computes."""
    all_names = known_indicator_names()
    parameterized = set(parameterized_indicator_names())
    return {
        "concepts": [n for n in all_names if n not in parameterized],
        "indicators": sorted(parameterized),
    }


def _condition_from_spec(spec, default_role=None):
    """Builds ONE Condition from a single Step 2/3/7 condition spec dict.
    Never guesses: a `known` spec becomes a structured Condition using
    exactly the fields the user set; an `other` spec becomes a raw,
    manual_review Condition carrying the user's own text verbatim, unless
    `matched_concept` was explicitly set (the user confirmed a match to an
    existing concept via the classify-other AI question, or typed it in
    themselves), in which case it's treated as a `known` spec for that
    concept."""
    mode = spec.get("input_mode", "known")

    if mode == "other" and not spec.get("matched_concept"):
        return Condition(
            type="raw",
            text=spec.get("raw_text", ""),
            raw_source=spec.get("raw_text", ""),
            manual_review=True,
            role=spec.get("role") or default_role,
        )

    concept = spec.get("matched_concept") or spec.get("concept")
    catalog = known_concept_catalog()

    if concept in catalog["indicators"]:
        period = spec.get("period")
        params = {"period": int(period)} if period is not None else {}
        op, value = spec.get("op"), spec.get("value")
        if op is not None and value is not None:
            return Condition(
                type="indicator_compare", indicator=concept, params=params,
                op=op, value=float(value), role=spec.get("role") or default_role,
            )
        # No threshold given -- the indicator is still registered (see
        # _collect_indicators below) so it plots/computes, but with nothing
        # to compare against there's no boolean gate to express; recorded
        # as a concept-shaped condition so it's visible in the rule list
        # without inventing a comparison value nobody gave us.
        return Condition(
            type="concept", name=concept, role=spec.get("role") or default_role,
            lookback_bars=spec.get("lookback_bars"),
        )

    return Condition(
        type="concept",
        name=concept,
        direction=spec.get("direction"),
        role=spec.get("role") or default_role,
        lookback_bars=spec.get("lookback_bars"),
    )


def _collect_indicators(condition_specs, wizard_data):
    """StrategyConfig.indicators is a separate list ({"name","params","role"})
    from the condition list itself -- ConfiguredStrategy.prepare_context()
    reads THIS to know which indicator columns to compute at all. A
    condition referencing "ema" with a period is useless unless the same
    period is also registered here."""
    indicators = []
    catalog = known_concept_catalog()
    for spec in condition_specs:
        if spec.get("input_mode") == "other" and not spec.get("matched_concept"):
            continue
        concept = spec.get("matched_concept") or spec.get("concept")
        if concept in catalog["indicators"] and spec.get("period") is not None:
            indicators.append({
                "name": concept, "params": {"period": int(spec["period"])},
                "role": spec.get("role") or wizard_data.get("entry_timeframe_role"),
            })
    return indicators


def _collect_concepts_used(all_conditions):
    used = []
    for c in all_conditions:
        if c.type == "concept" and c.name and c.name not in used:
            used.append(c.name)
        if c.indicator and c.indicator not in used:
            used.append(c.indicator)
    return used


def mirror_condition(condition):
    """Deterministically flips a Condition's already-explicit direction/op
    to the opposite side -- e.g. direction="bullish" -> "bearish", op=">" ->
    "<". This is NOT interpretation of ambiguous text (the Never Guess rule
    is about never inferring meaning from prose); it's a structural
    transformation of a field the user already set explicitly, which is
    exactly what "Both (mirror rules)" asked for. A manual_review condition
    (free text the Wizard couldn't structure) can't be safely flipped --
    its raw text is carried over UNCHANGED to both directions and stays
    manual_review on both, never silently rewritten."""
    if condition.manual_review:
        return Condition(**{**condition.__dict__})
    mirrored = Condition(**{**condition.__dict__})
    if mirrored.direction in _DIRECTION_FLIP:
        mirrored.direction = _DIRECTION_FLIP[mirrored.direction]
    if mirrored.op in _OP_FLIP:
        mirrored.op = _OP_FLIP[mirrored.op]
    return mirrored


def mirror_conditions(conditions):
    return [mirror_condition(c) for c in conditions]


def _build_sl(spec):
    if not spec:
        return SLTPSpec()
    kind = spec.get("type")
    if kind in _SL_TYPE_MAP:
        return SLTPSpec(type=_SL_TYPE_MAP[kind], value=spec.get("value"), level=spec.get("level"))
    return SLTPSpec()  # "other"/unrecognized -- left unknown; surfaced via manual review text separately


def _build_tp(spec):
    if not spec:
        return SLTPSpec()
    kind = spec.get("type")
    if kind in _TP_TYPE_MAP:
        return SLTPSpec(type=_TP_TYPE_MAP[kind], value=spec.get("value"), level=spec.get("level"))
    return SLTPSpec()


def _sl_tp_manual_review(section, spec):
    """A "Fixed Points" (or any other non-executable) SL/TP choice never
    silently produces a SLTPSpec the engine can't fill -- it's surfaced as
    its own manual-review item instead, same as an Other condition."""
    if not spec or spec.get("type") in (None, "", "fixed_pct", "atr_multiple", "structure",
                                          "signal_candle", "rr", "level"):
        return None
    return {
        "section": section,
        "raw_text": spec.get("raw_source") or f"{spec.get('type')}: {spec.get('value')}",
    }


def build_strategy_config(wizard_data):
    """The single entry point. Returns (StrategyConfig, trust_report).
    trust_report = {"total_conditions", "user_set", "manual_review_count",
    "manual_review_items": [{"section","raw_text"}], "trust_score_pct"}."""
    direction_mode = wizard_data.get("direction_mode", "long_only")
    if direction_mode not in DIRECTION_MODES:
        raise ValueError(f"Unknown direction_mode: {direction_mode!r}")

    timeframes = {}
    if wizard_data.get("entry_timeframe"):
        timeframes["entry"] = wizard_data["entry_timeframe"]
    if wizard_data.get("bias_timeframe"):
        timeframes["bias"] = wizard_data["bias_timeframe"]

    session_filter = []
    if wizard_data.get("session") and wizard_data["session"] != "any":
        session_filter.append(wizard_data["session"])

    manual_review_items = []

    def build_bucket(specs, section_label, default_role=None):
        conditions = []
        for spec in specs or []:
            cond = _condition_from_spec(spec, default_role=default_role)
            conditions.append(cond)
            if cond.manual_review:
                manual_review_items.append({"section": section_label, "raw_text": cond.raw_source or ""})
        return conditions

    entry_conditions, long_entry_conditions, short_entry_conditions = [], [], []
    exit_conditions = []

    if direction_mode == "both_independent":
        long_entry_conditions = build_bucket(wizard_data.get("long_entry_conditions"), "Long Entry Conditions", "entry")
        short_entry_conditions = build_bucket(wizard_data.get("short_entry_conditions"), "Short Entry Conditions", "entry")
    elif direction_mode == "both_mirror":
        base = build_bucket(wizard_data.get("entry_conditions"), "Entry Conditions", "entry")
        long_entry_conditions = base
        short_entry_conditions = mirror_conditions(base)
    elif direction_mode == "long_only":
        long_entry_conditions = build_bucket(wizard_data.get("entry_conditions"), "Entry Conditions", "entry")
    else:  # short_only
        short_entry_conditions = build_bucket(wizard_data.get("entry_conditions"), "Entry Conditions", "entry")

    exit_conditions = build_bucket(wizard_data.get("exit_conditions"), "Exit Conditions", "exit")

    # Step 7 (Filters/Discards): StrategyConfig has no separate generic
    # filter-condition list -- a discard filter is mechanically identical
    # to an entry condition (both must hold for entry to fire), so filters
    # are appended to whichever entry bucket(s) are active, exactly the way
    # strategy_parser.py already treats filter-like prose as additional
    # entry conditions rather than inventing a schema field that doesn't
    # exist.
    filter_conditions = build_bucket(wizard_data.get("filters"), "Filters", "entry")
    if filter_conditions:
        if long_entry_conditions or short_entry_conditions:
            long_entry_conditions = long_entry_conditions + (filter_conditions if long_entry_conditions else [])
            short_entry_conditions = short_entry_conditions + (filter_conditions if short_entry_conditions else [])
        else:
            entry_conditions = entry_conditions + filter_conditions

    stop_loss = _build_sl(wizard_data.get("stop_loss"))
    take_profit = _build_tp(wizard_data.get("take_profit"))
    for section, spec in (("Stop Loss", wizard_data.get("stop_loss")), ("Take Profit", wizard_data.get("take_profit"))):
        item = _sl_tp_manual_review(section, spec)
        if item:
            manual_review_items.append(item)

    all_conditions = (
        entry_conditions + long_entry_conditions + short_entry_conditions + exit_conditions
    )
    indicators = (
        _collect_indicators(wizard_data.get("entry_conditions") or [], wizard_data)
        + _collect_indicators(wizard_data.get("long_entry_conditions") or [], wizard_data)
        + _collect_indicators(wizard_data.get("short_entry_conditions") or [], wizard_data)
        + _collect_indicators(wizard_data.get("exit_conditions") or [], wizard_data)
        + _collect_indicators(wizard_data.get("filters") or [], wizard_data)
    )

    config = StrategyConfig(
        name=wizard_data.get("name", "Unnamed Strategy"),
        raw_text="",  # Wizard-built -- there is no source prose to keep
        timeframes=timeframes,
        indicators=indicators,
        concepts_used=_collect_concepts_used(all_conditions),
        entry_conditions=entry_conditions,
        exit_conditions=exit_conditions,
        long_entry_conditions=long_entry_conditions,
        short_entry_conditions=short_entry_conditions,
        stop_loss=stop_loss,
        take_profit=take_profit,
        risk_pct=wizard_data.get("risk_pct"),
        risk_reward=take_profit.value if take_profit.type == "rr" else None,
        session_filter=session_filter,
        tags=["wizard-built"],
    )

    # Trust score counts DISTINCT decisions the user actually made, not the
    # expanded condition lists -- "Both (mirror rules)" and filters (which
    # get appended to BOTH long_entry_conditions and short_entry_conditions,
    # since a discard filter applies to entry in either direction) would
    # otherwise double-count the same single user input as two, inflating
    # the denominator without inflating manual_review_items to match.
    if direction_mode == "both_independent":
        input_condition_count = len(wizard_data.get("long_entry_conditions") or []) + len(wizard_data.get("short_entry_conditions") or [])
    else:
        input_condition_count = len(wizard_data.get("entry_conditions") or [])
    input_condition_count += len(wizard_data.get("exit_conditions") or []) + len(wizard_data.get("filters") or [])
    total = input_condition_count + (1 if wizard_data.get("stop_loss") else 0) + (1 if wizard_data.get("take_profit") else 0)
    manual_count = len(manual_review_items)
    trust_score_pct = round((total - manual_count) / total * 100, 1) if total else 100.0

    trust_report = {
        "total_conditions": total,
        "user_set": total - manual_count,
        "manual_review_count": manual_count,
        "manual_review_items": manual_review_items,
        "trust_score_pct": trust_score_pct,
    }
    return config, trust_report


def has_manual_review(config):
    return any(c.manual_review for c in list_all_conditions(config))


def list_all_conditions(config):
    return (
        list(config.entry_conditions) + list(config.exit_conditions)
        + list(config.confirmation_conditions) + list(config.long_entry_conditions)
        + list(config.short_entry_conditions)
        + [c for g in config.entry_rule_groups for c in g.get("conditions", [])]
    )


def list_manual_review_conditions(config):
    return [c for c in list_all_conditions(config) if c.manual_review]
