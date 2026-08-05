"""Validates a parsed StrategyConfig before it's allowed to run. Every
check here maps directly to a spec requirement: missing timeframe, missing
entry/exit, missing SL/TP, invalid indicator, invalid RR, invalid risk.
Never guesses a fix -- only reports what's wrong so the dashboard can ask
the CEO to clarify.
"""

_KNOWN_INDICATORS = {
    "ema", "sma", "vwap", "rsi", "macd", "atr", "volume",
    "support", "resistance", "bos", "choch", "fvg",
    "order_block", "breaker_block", "liquidity_sweep",
    "pdh", "pdl", "pdh_sweep", "pdl_sweep",
    "candle_break",
    # Volume-based
    "poc", "value_area", "lvn", "hvn", "aggression",
    # Structure-based
    "mitigation_block", "imbalance", "equal_highs_lows", "swing_high", "swing_low",
    # Session-based
    "session_high_low", "session_open",
    # Price-action
    "engulfing", "pin_bar", "inside_bar",
    # Advanced Concept Library expansion
    "premium_discount_zone", "rejection_block", "orb", "initial_balance",
    "anchored_vwap", "cvd", "kill_zone",
}

# Of _KNOWN_INDICATORS above, these are numeric-parameter indicators (take a
# period, can be compared with a threshold via indicator_compare/
# indicator_vs_indicator/price_compare) rather than structural/ICT concepts
# (take a direction/role, used via a "concept" Condition). Used by the
# Strategy Wizard (backtest_engine.wizard.known_concept_catalog()) to decide
# which parameter fields to show for a selected condition type -- kept next
# to _KNOWN_INDICATORS so the two can never silently drift apart.
_PARAMETERIZED_INDICATORS = {"ema", "sma", "vwap", "rsi", "macd", "atr", "volume"}

_KNOWN_CONDITION_TYPES = {"indicator_compare", "price_compare", "indicator_vs_indicator", "concept", "session", "trend", "candle_range_pct"}


def known_indicator_names():
    """The engine's real, current vocabulary of indicator/concept names
    (backtest_engine.concepts's computable columns) -- a public read-only
    view of _KNOWN_INDICATORS so callers outside this module (the Strategy
    Wizard's dynamic condition-type dropdown) never need to reach into a
    private module attribute or maintain their own separate copy that could
    drift out of sync as concepts are added here."""
    return sorted(_KNOWN_INDICATORS)


def parameterized_indicator_names():
    """The subset of known_indicator_names() that take a numeric period
    parameter (EMA, RSI, ...) rather than a direction/role (BOS, FVG, ...)."""
    return sorted(_PARAMETERIZED_INDICATORS)

_KNOWN_ENTRY_TYPES = {
    "market", "current_candle_close", "limit", "stop",
    "signal_candle_high", "signal_candle_low", "next_candle_open",
}
_TRAILING_STOP_TYPES = {"pct", "atr_multiple"}

# Mirrors the OR-gates in ConfiguredStrategy.prepare_context() (backtest_engine/
# configured_strategy.py): each concept-type condition name only gets its
# underlying column(s) actually computed if concepts_used contains at least
# one of the names listed here. If a condition references a concept whose
# gate is never satisfied, prepare_context() never builds that column, so
# _get()/_within() silently return None/False on every bar -- the condition
# can never be true, with no error, just zero trades forever.
_CONCEPT_REQUIRES_ANY_OF = {
    "bos": {"bos", "choch"},
    "choch": {"choch"},
    "fvg": {"fvg"},
    "order_block": {"order_block", "breaker_block"},
    "breaker_block": {"breaker_block"},
    "support": {"support", "resistance", "liquidity_sweep"},
    "resistance": {"support", "resistance", "liquidity_sweep"},
    "liquidity_sweep": {"liquidity_sweep"},
    "volume": {"volume"},
    "pdh": {"pdh", "pdl", "pdh_sweep", "pdl_sweep"},
    "pdl": {"pdh", "pdl", "pdh_sweep", "pdl_sweep"},
    "pdh_sweep": {"pdh_sweep", "pdl_sweep"},
    "pdl_sweep": {"pdh_sweep", "pdl_sweep"},
    "candle_break": {"candle_break"},
    "poc": {"poc", "value_area"},
    "value_area": {"poc", "value_area"},
    "lvn": {"lvn"},
    "hvn": {"hvn"},
    "aggression": {"aggression"},
    "mitigation_block": {"mitigation_block"},
    "imbalance": {"imbalance"},
    "equal_highs_lows": {"equal_highs_lows"},
    "swing_high": {"swing_high", "swing_low"},
    "swing_low": {"swing_high", "swing_low"},
    "session_high_low": {"session_high_low"},
    "session_open": {"session_open"},
    "engulfing": {"engulfing"},
    "pin_bar": {"pin_bar"},
    "inside_bar": {"inside_bar"},
}

# A "structure" stop-loss reads the zone columns ConfiguredStrategy.
# _compute_stop_loss() looks up (order block -> FVG -> support/resistance).
# Those columns only exist if prepare_context() computed them, which it only
# does when concepts_used names one of these. With none of them, EVERY bar
# returns a null stop-loss forever: in backtesting the trade silently falls
# back to fixed-fraction sizing with no protective stop, and in paper
# trading risk_manager.evaluate() rejects the trade outright ("no stop-loss
# could be computed"), so the strategy can never trade at all. Measured on
# the real "LSI plus Halftrend" strategy: 54,138 bars checked, 54,138 null
# stop-losses, zero usable.
_STRUCTURE_SL_SOURCES = {"order_block", "breaker_block", "fvg", "support", "resistance", "liquidity_sweep"}

# The engine resamples to these exact interval strings (data_engine.config
# .SUPPORTED_INTERVALS). Friendly aliases like "daily" reach the resampler
# and raise "Unsupported interval 'daily'", which aborts the whole backtest
# with a hard crash rather than a clear validation message -- measured on
# the real "Break and Bounce" strategy (bias='daily').
_VALID_INTERVALS = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"}
_INTERVAL_ALIASES = {
    "daily": "1d", "day": "1d", "1day": "1d", "d": "1d",
    "weekly": "1w", "week": "1w", "1week": "1w", "w": "1w",
    "hourly": "1h", "hour": "1h", "1hour": "1h", "h": "1h",
    "4hour": "4h", "4hr": "4h",
    "minute": "1m", "1min": "1m", "5min": "5m", "15min": "15m", "30min": "30m",
}


def normalize_timeframes(timeframes):
    """Maps friendly interval names onto the exact strings the resampler
    accepts ("daily" -> "1d"). Returns (normalized_dict, changed_list) and
    never invents a value it doesn't recognise -- anything unknown is left
    untouched so validate() reports it instead of silently guessing."""
    normalized, changed = {}, []
    for role, tf in (timeframes or {}).items():
        key = str(tf).strip().lower()
        if key in _VALID_INTERVALS:
            normalized[role] = key
        elif key in _INTERVAL_ALIASES:
            normalized[role] = _INTERVAL_ALIASES[key]
            changed.append((role, tf, _INTERVAL_ALIASES[key]))
        else:
            normalized[role] = tf
    return normalized, changed


def _numeric_bound(cond):
    """For an indicator_compare condition with a numeric threshold, returns
    ("lower", value) if it requires the indicator ABOVE value (>, >=), or
    ("upper", value) if it requires it BELOW value (<, <=). None otherwise."""
    if cond.type != "indicator_compare" or cond.value is None:
        return None
    if cond.op in (">", ">="):
        return ("lower", cond.value)
    if cond.op in ("<", "<="):
        return ("upper", cond.value)
    return None


def validate(config):
    """Returns a list of human-readable error strings. Empty list = valid,
    safe to run. Does not mutate `config`."""
    errors = []

    if "entry" not in config.timeframes:
        errors.append("Missing entry timeframe. Specify which timeframe entries are evaluated on.")

    # Every declared timeframe must be an interval the resampler actually
    # supports -- otherwise the backtest dies mid-run with a raw
    # "Unsupported interval" exception instead of failing cleanly here.
    for role, tf in (config.timeframes or {}).items():
        key = str(tf).strip().lower()
        if key in _VALID_INTERVALS:
            continue
        if key in _INTERVAL_ALIASES:
            errors.append(
                f"Timeframe '{tf}' (role '{role}') isn't a supported interval -- "
                f"use '{_INTERVAL_ALIASES[key]}' instead."
            )
        else:
            errors.append(
                f"Timeframe '{tf}' (role '{role}') isn't a supported interval. "
                f"Choose one of: {', '.join(sorted(_VALID_INTERVALS))}."
            )

    # A structure-based stop-loss needs at least one concept that actually
    # produces a structural zone, or it can never compute a stop at all.
    if config.stop_loss.type == "structure" and not (_STRUCTURE_SL_SOURCES & set(config.concepts_used)):
        errors.append(
            "Stop loss is 'structure' but concepts_used has none of "
            f"{sorted(_STRUCTURE_SL_SOURCES)} -- no structural zone is ever computed, so no "
            "stop-loss can be calculated and the strategy can never place a protected trade. "
            "Add the concept this strategy's stop is based on, or use a fixed % / ATR stop."
        )

    # A strategy with separate Long/Short entry rule sets, OR branching
    # entry_rule_groups (N alternative entry paths -- e.g. a different rule
    # per market "shape"/regime), satisfies "has entry rules" via EITHER of
    # those instead of entry_conditions -- see ConfiguredStrategy.on_bar(),
    # which prioritizes entry_rule_groups, then long/short_entry_conditions,
    # over entry_conditions whenever populated.
    uses_long_short = bool(config.long_entry_conditions or config.short_entry_conditions)
    uses_rule_groups = bool(config.entry_rule_groups)
    if not config.entry_conditions and not uses_long_short and not uses_rule_groups:
        errors.append("Missing entry rules. No entry conditions were detected.")
    else:
        # A long-only or short-only strategy (only one of the two rule sets
        # populated) is a legitimate, valid design -- not flagged here.
        for bucket_name in ("entry_conditions", "long_entry_conditions", "short_entry_conditions"):
            for c in getattr(config, bucket_name):
                if c.is_unclear():
                    errors.append(f'Unclear entry rule, needs clarification: "{c.text}"')
        for idx, group in enumerate(config.entry_rule_groups):
            label = group.get("label") or f"group #{idx}"
            if group.get("direction") not in ("bullish", "bearish"):
                errors.append(
                    f"entry_rule_groups[{idx}] ('{label}') has direction "
                    f"{group.get('direction')!r} -- must be 'bullish' or 'bearish'."
                )
            if not group.get("conditions"):
                errors.append(f"entry_rule_groups[{idx}] ('{label}') has no conditions -- an empty group can never fire.")
            for c in group.get("conditions") or []:
                if c.is_unclear():
                    errors.append(f'Unclear entry rule in entry_rule_groups[{idx}] (\'{label}\'), needs clarification: "{c.text}"')

    if not config.exit_conditions and config.stop_loss.type == "unknown":
        errors.append("Missing exit rules. No exit conditions or stop-loss were detected.")
    else:
        unclear = [c for c in config.exit_conditions if c.is_unclear()]
        for c in unclear:
            errors.append(f'Unclear exit rule, needs clarification: "{c.text}"')

    if config.stop_loss.type == "unknown":
        errors.append("Missing stop loss. Specify a fixed %, an ATR multiple, or a structure-based SL.")

    if config.take_profit.type == "unknown":
        errors.append("Missing take profit. Specify a fixed %, or a risk:reward ratio.")

    if config.risk_pct is None:
        errors.append("Missing risk %. Specify how much of the balance to risk per trade.")
    elif not (0 < config.risk_pct <= 100):
        errors.append(f"Invalid risk %: {config.risk_pct}. Must be between 0 and 100.")

    if config.risk_reward is not None and config.risk_reward <= 0:
        errors.append(f"Invalid risk:reward ratio: {config.risk_reward}. Must be greater than 0.")

    # -------------------------------------------- Trade Execution Engine
    entry_type = (config.entry_type or "market").strip().lower()
    if entry_type not in _KNOWN_ENTRY_TYPES:
        errors.append(
            f"Unknown entry_type '{config.entry_type}'. Must be one of: {', '.join(sorted(_KNOWN_ENTRY_TYPES))}."
        )
    # Batch 6, Task 4: per-direction overrides -- optional, only validated
    # when actually set (None means "use entry_type", already validated
    # above, so a strategy that never sets these is unaffected).
    for field_name, override in (("long_entry_type", config.long_entry_type), ("short_entry_type", config.short_entry_type)):
        if override is not None and override.strip().lower() not in _KNOWN_ENTRY_TYPES:
            errors.append(
                f"Unknown {field_name} '{override}'. Must be one of: {', '.join(sorted(_KNOWN_ENTRY_TYPES))}."
            )
    if entry_type in ("limit", "stop") and config.entry_price_offset_pct is not None:
        if config.entry_price_offset_pct < 0:
            errors.append(
                f"Invalid entry_price_offset_pct: {config.entry_price_offset_pct}. Must be >= 0 "
                "(direction relative to price is implied by entry_type/side, not the sign)."
            )

    if config.partial_take_profit is not None:
        ptp = config.partial_take_profit
        trigger_rr = ptp.get("trigger_rr")
        close_fraction = ptp.get("close_fraction")
        if trigger_rr is None or trigger_rr <= 0:
            errors.append("partial_take_profit.trigger_rr must be a positive number.")
        if close_fraction is None or not (0 < close_fraction < 1):
            errors.append("partial_take_profit.close_fraction must be between 0 and 1 (exclusive).")
        if config.stop_loss.type == "unknown":
            errors.append(
                "partial_take_profit requires a real stop-loss (its trigger is measured in multiples "
                "of the original risk) -- stop_loss is currently 'unknown'."
            )

    if config.trailing_stop is not None:
        ts = config.trailing_stop
        ts_type = ts.get("type")
        ts_value = ts.get("value")
        if ts_type not in _TRAILING_STOP_TYPES:
            errors.append(f"trailing_stop.type must be one of {sorted(_TRAILING_STOP_TYPES)}, got {ts_type!r}.")
        if ts_value is None or ts_value <= 0:
            errors.append("trailing_stop.value must be a positive number.")

    if config.time_exit_bars is not None and config.time_exit_bars <= 0:
        errors.append(f"time_exit_bars must be a positive integer, got {config.time_exit_bars}.")

    def _named_condition_buckets():
        """Yields (label, [Condition, ...]) for every AND-gated bucket in
        the strategy, including each entry_rule_groups group individually
        -- shared by every check below that needs to look at "every
        condition, tagged with where it came from"."""
        for bucket_name in ("entry_conditions", "long_entry_conditions", "short_entry_conditions",
                             "exit_conditions", "confirmation_conditions"):
            yield bucket_name.replace("_", " "), getattr(config, bucket_name)
        for idx, group in enumerate(config.entry_rule_groups):
            label = group.get("label") or f"entry_rule_groups[{idx}]"
            yield f"entry rule group '{label}'", group.get("conditions") or []

    for bucket_label, bucket in _named_condition_buckets():
        for cond in bucket:
            if cond.type not in _KNOWN_CONDITION_TYPES:
                continue
            if cond.type == "indicator_compare" and cond.indicator not in _KNOWN_INDICATORS:
                errors.append(f"Invalid indicator in {bucket_label}: {cond.indicator!r}")
            if cond.type == "indicator_vs_indicator" and (
                    cond.indicator not in _KNOWN_INDICATORS or cond.indicator2 not in _KNOWN_INDICATORS):
                errors.append(
                    f"Invalid indicator in {bucket_label}: "
                    f"{cond.indicator!r} vs {cond.indicator2!r}"
                )
            if cond.type == "concept" and cond.name not in _KNOWN_INDICATORS:
                errors.append(f"Invalid indicator/concept in {bucket_label}: {cond.name!r}")

    # An indicator's role must be one of the strategy's OWN declared
    # timeframes -- ConfiguredStrategy._indicator_column() builds the
    # evaluation column name from that role (e.g. role "confirmation" ->
    # column "confirmation_volume"). If no timeframe was declared for that
    # role, MultiTimeframeContext never builds a dataframe for it, so the
    # column never exists: any condition referencing that indicator is
    # silently always false forever, with no error and zero trades.
    for ind in config.indicators:
        role = ind.get("role")
        if role and role not in config.timeframes:
            errors.append(
                f"Indicator '{ind.get('name')}' has role '{role}' but no '{role}' timeframe is "
                f"declared -- add a '{role}' timeframe or change the indicator's role."
            )

    # A concept condition (bos/fvg/support/pdh/...) only gets its column
    # computed if concepts_used actually lists a name that satisfies its
    # gate in prepare_context() -- see _CONCEPT_REQUIRES_ANY_OF above. This
    # catches the same "silently always false" failure mode as the role
    # check, via a different mechanism: the condition references a concept
    # that was never added to concepts_used.
    concepts_used_set = set(config.concepts_used)
    for bucket_label, bucket in _named_condition_buckets():
        for cond in bucket:
            if cond.type != "concept" or cond.name not in _CONCEPT_REQUIRES_ANY_OF:
                continue
            required_any = _CONCEPT_REQUIRES_ANY_OF[cond.name]
            if not (required_any & concepts_used_set):
                errors.append(
                    f"Concept '{cond.name}' is used in {bucket_label} but "
                    f"concepts_used doesn't include any of {sorted(required_any)} -- its indicator "
                    f"is never computed, so this condition can never be true. "
                    f"Add one of {sorted(required_any)} to concepts_used."
                )

    # The same concept demanded in BOTH directions on the same bar (e.g.
    # bullish candle_break AND bearish candle_break in entry_conditions) is
    # never a real rule -- entry_conditions are AND-ed, so this reads as
    # "the market must break up and down simultaneously". In practice it is
    # either impossible (0 trades) or near-always-true (fires on almost
    # every bar, no edge at all). It shows up when a document describing a
    # long setup AND a mirror-image short setup gets flattened into one
    # condition list; the two setups need to be separate strategies.
    same_direction_buckets = [
        (n.replace("_", " "), getattr(config, n))
        for n in ("entry_conditions", "long_entry_conditions", "short_entry_conditions", "confirmation_conditions")
    ] + [
        (f"entry rule group '{group.get('label') or f'#{idx}'}'", group.get("conditions") or [])
        for idx, group in enumerate(config.entry_rule_groups)
    ]
    for bucket_label, bucket in same_direction_buckets:
        seen_directions = {}
        for cond in bucket:
            if cond.type != "concept" or cond.direction not in ("bullish", "bearish"):
                continue
            seen_directions.setdefault(cond.name, set()).add(cond.direction)
        for concept_name, directions in seen_directions.items():
            if len(directions) > 1:
                errors.append(
                    f"'{concept_name}' is required in BOTH bullish and bearish direction in "
                    f"{bucket_label}, but these are AND-ed on the same bar -- the market "
                    f"cannot do both at once. This usually means a long setup and a mirrored short setup "
                    f"were merged; keep one direction per strategy."
                )

    # Two numeric-threshold conditions on the SAME indicator+params can
    # never both be true if one requires the value ABOVE X and another
    # requires it BELOW Y with Y <= X (e.g. "rsi < 30" AND "rsi > 70",
    # required together) -- proven root cause of a real 0-trade strategy
    # (Daily High-Low Liquidity Strategy: confirmation_conditions required
    # rsi(5) < 30 AND rsi(5) > 70 simultaneously, 0 of 107k+ bars). Checked
    # across entry_conditions + confirmation_conditions combined, since
    # ConfiguredStrategy.on_bar() ANDs both buckets together before ever
    # producing a signal -- that's the real all-must-be-true gate. A
    # strategy using separate Long/Short rule sets has TWO independent
    # gates instead (long+confirmation, short+confirmation) -- checked
    # separately, since long_entry_conditions and short_entry_conditions
    # are never ANDed together (that's the whole point of separating
    # them), so merging them here would flag a false "impossible
    # combination" for the completely normal case of a long rule wanting
    # e.g. "ema > 50" and the mirrored short rule wanting "ema < 50".
    # exit_conditions is its own independent AND-gate (only evaluated once
    # a position is already open) so it's checked separately.
    gates = [("entry conditions + confirmation conditions",
              list(config.entry_conditions) + list(config.confirmation_conditions))]
    if config.long_entry_conditions:
        gates.append(("long entry conditions + confirmation conditions",
                       list(config.long_entry_conditions) + list(config.confirmation_conditions)))
    if config.short_entry_conditions:
        gates.append(("short entry conditions + confirmation conditions",
                       list(config.short_entry_conditions) + list(config.confirmation_conditions)))
    for idx, group in enumerate(config.entry_rule_groups):
        label = group.get("label") or f"#{idx}"
        gates.append((f"entry rule group '{label}' + confirmation conditions",
                       list(group.get("conditions") or []) + list(config.confirmation_conditions)))
    gates.append(("exit conditions", config.exit_conditions))
    for label, bucket in gates:
        by_key = {}
        for cond in bucket:
            bound = _numeric_bound(cond)
            if bound is None:
                continue
            key = (cond.indicator, tuple(sorted((cond.params or {}).items())))
            by_key.setdefault(key, []).append((bound, cond))
        for (indicator, _params), items in by_key.items():
            lowers = [(v, c) for (kind, v), c in items if kind == "lower"]
            uppers = [(v, c) for (kind, v), c in items if kind == "upper"]
            if not lowers or not uppers:
                continue
            lower_v, lower_c = max(lowers, key=lambda t: t[0])
            upper_v, upper_c = min(uppers, key=lambda t: t[0])
            if lower_v >= upper_v:
                errors.append(
                    f"Impossible combination in {label}: '{indicator} {lower_c.op} {lower_v}' and "
                    f"'{indicator} {upper_c.op} {upper_v}' are both required together but can never "
                    f"both be true on the same bar -- remove or correct one of these conditions."
                )

    return errors


def is_valid(config):
    return len(validate(config)) == 0
