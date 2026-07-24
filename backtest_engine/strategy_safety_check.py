"""Automatic Strategy Safety Check: runs once a strategy has been built
into a StrategyConfig (new import, existing library entry, or an
optimizer candidate) and gates whether it's allowed to reach the backtest
engine at all. Does not parse or build strategies -- purely a post-build
static check, called from strategy_library (on every save, so status is
always current) and from every real backtest entry point (mtf_worker,
verification_engine), so nothing ever reaches engine.run_backtest without
passing through it first.

Three checks, each one root-caused from a real bug this project actually
hit:

1. check_duplicate_entry_exit_clauses -- Liquidity Sweep & FVG Validation
   Strategy: exit_conditions exactly duplicated two of its three
   entry_conditions, so the exit gate was already satisfied the instant a
   position opened. 93.9% of its trades closed within 1 bar; the account
   was ground to zero by commission/slippage churn, not a real loss.
2. check_exit_gives_realistic_room -- the same failure mode, generalized:
   an exit gate built entirely from slow-moving price-level concepts (or
   that reads the same underlying signal as an entry clause under a
   different threshold) risks the identical outcome even without an exact
   duplicate.
3. check_contradictory_entry_gates -- Daily High-Low Liquidity Strategy:
   a bare 'pdh' condition (close > previous-day-high) and a bare 'pdl'
   condition (close < previous-day-low) were both required in the same
   AND-gated entry_conditions list. previous-day-high is always >=
   previous-day-low, so this could never be true -- confirmed live at
   7,927 evaluations, 0 true. validator.py's existing numeric-bound
   contradiction check doesn't cover this (it only looks at
   indicator_compare thresholds, not concept-type level comparisons), so
   it slipped through undetected until the Verification Engine caught it
   at runtime. This check closes that specific gap, on top of reusing
   validator.py's existing contradiction detection.
"""

from backtest_engine import validator

# Concepts whose bare/direction-free evaluation (see
# ConfiguredStrategy._eval's "concept" branch) is a slow-moving PRICE
# LEVEL proximity or position check -- once true, these typically stay
# true for many consecutive bars (a support/resistance zone, a previous
# day's high/low, a volume profile POC/value-area, a session's high/low
# or open). An exit gate built only from these structurally risks
# re-triggering almost immediately after entry.
_SLOW_LEVEL_CONCEPTS = {
    "support", "resistance", "pdh", "pdl", "poc", "value_area",
    "session_high_low", "session_open", "lvn", "hvn",
}


def _cond_signature(cond, ignore_op_value=False):
    """A comparable key identifying what a condition actually reads and
    (optionally) what threshold it demands. ignore_op_value=False is an
    EXACT-duplicate key; True is a looser "same underlying signal" key
    used to catch near-duplicates that survive the exact match."""
    base = (cond.type, cond.indicator, cond.name, cond.role, cond.direction, cond.indicator2, cond.text)
    if ignore_op_value:
        return base
    return base + (
        tuple(sorted((cond.params or {}).items())), cond.op, cond.value,
        tuple(sorted((cond.params2 or {}).items())),
    )


def _describe(cond):
    if cond.type == "concept":
        d = f" ({cond.direction})" if cond.direction else ""
        r = f" [role={cond.role}]" if cond.role else ""
        return f"concept:{cond.name}{d}{r}"
    if cond.type in ("indicator_compare", "price_compare"):
        r = f" [role={cond.role}]" if cond.role else ""
        return f"{cond.type}:{cond.indicator} {cond.op} {cond.value}{r}"
    if cond.type == "indicator_vs_indicator":
        r = f" [role={cond.role}]" if cond.role else ""
        return f"{cond.indicator} {cond.op} {cond.indicator2}{r}"
    return f"{cond.type}:{cond.name or cond.text}"


def _entry_buckets(config):
    return [
        ("entry_conditions", list(config.entry_conditions)),
        ("long_entry_conditions", list(config.long_entry_conditions)),
        ("short_entry_conditions", list(config.short_entry_conditions)),
    ]


def check_duplicate_entry_exit_clauses(config):
    """CHECK 1: any exit_conditions clause that exactly duplicates a
    clause already required in an entry bucket."""
    reasons = []
    entry_sigs = {}
    for bucket_name, bucket in _entry_buckets(config):
        for cond in bucket:
            if cond.type == "raw":
                continue  # never evaluates True (ConfiguredStrategy._eval), so text-matching it is meaningless
            entry_sigs.setdefault(_cond_signature(cond), (bucket_name, cond))

    for i, exit_cond in enumerate(config.exit_conditions):
        if exit_cond.type == "raw":
            continue
        sig = _cond_signature(exit_cond)
        if sig in entry_sigs:
            bucket_name, entry_cond = entry_sigs[sig]
            reasons.append(
                f"Exit condition #{i} ({_describe(exit_cond)}) is IDENTICAL to a condition already "
                f"required in {bucket_name} ({_describe(entry_cond)}). That clause is guaranteed true "
                f"the moment a position opens, so the exit gate can be satisfied again almost "
                f"immediately -- the exact defect found in Liquidity Sweep & FVG Validation Strategy "
                f"(93.9% of trades closed within 1 bar, account ground to zero by commission/slippage)."
            )
    return reasons


def check_exit_gives_realistic_room(config):
    """CHECK 2: exit conditions that structurally can't give a trade a
    realistic chance to travel toward its stop-loss/take-profit -- either
    because every exit clause is a slow-moving price-level concept, or
    because an individual exit clause reads the same underlying signal as
    an entry clause under a different threshold (a near-duplicate that
    Check 1's exact match wouldn't catch)."""
    reasons = []
    if not config.exit_conditions:
        return reasons  # no rule-based exit -- only stop_loss/take_profit decide; nothing to flag

    if all(c.type == "concept" and c.name in _SLOW_LEVEL_CONCEPTS for c in config.exit_conditions):
        names = sorted({c.name for c in config.exit_conditions})
        reasons.append(
            f"Every exit condition relies only on slow-moving price-level concepts ({', '.join(names)}), "
            f"which typically stay true for many consecutive bars once satisfied. An exit gate built "
            f"entirely from these gives a trade little to no realistic room to travel toward its "
            f"stop-loss or take-profit before closing itself out."
        )

    entry_sigs_loose = set()
    exact_sigs = set()
    for _, bucket in _entry_buckets(config):
        for cond in bucket:
            if cond.type == "raw":
                continue
            entry_sigs_loose.add(_cond_signature(cond, ignore_op_value=True))
            exact_sigs.add(_cond_signature(cond))
    for i, exit_cond in enumerate(config.exit_conditions):
        if exit_cond.type == "raw":
            continue
        if _cond_signature(exit_cond) in exact_sigs:  # already reported as an exact duplicate by Check 1
            continue
        if _cond_signature(exit_cond, ignore_op_value=True) in entry_sigs_loose:
            reasons.append(
                f"Exit condition #{i} ({_describe(exit_cond)}) reads the SAME underlying signal as an "
                f"entry condition (same indicator/concept, role, and direction, different threshold) -- "
                f"very likely to become true again within a bar or two of entry, not giving the trade "
                f"realistic room to reach its stop-loss/take-profit."
            )
    return reasons


def check_contradictory_entry_gates(config):
    """CHECK 3: logically-impossible AND-gates. Reuses validator.py's own
    contradiction detection (numeric-bound indicator_compare conflicts,
    same-concept-both-directions), plus a new check for bare pdh + bare
    pdl co-required in the same AND-gate (previous-day-high is always >=
    previous-day-low, so both can never be true together)."""
    reasons = [e for e in validator.validate(config)
               if e.startswith("Impossible combination") or "BOTH bullish and bearish" in e]

    gates = [("entry_conditions + confirmation_conditions",
              list(config.entry_conditions) + list(config.confirmation_conditions))]
    if config.long_entry_conditions:
        gates.append(("long_entry_conditions + confirmation_conditions",
                       list(config.long_entry_conditions) + list(config.confirmation_conditions)))
    if config.short_entry_conditions:
        gates.append(("short_entry_conditions + confirmation_conditions",
                       list(config.short_entry_conditions) + list(config.confirmation_conditions)))

    for bucket_name, bucket in gates:
        has_pdh = any(c.type == "concept" and c.name == "pdh" for c in bucket)
        has_pdl = any(c.type == "concept" and c.name == "pdl" for c in bucket)
        if has_pdh and has_pdl:
            reasons.append(
                f"Impossible combination in {bucket_name}: a bare 'pdh' condition requires "
                f"close > previous-day-high, and a bare 'pdl' condition requires close < "
                f"previous-day-low, required together -- but previous-day-high is always >= "
                f"previous-day-low (both come from the same day's real range), so these can never "
                f"both be true on the same bar. This is the exact defect behind Daily High-Low "
                f"Liquidity Strategy's permanent 0-trade result."
            )
    return reasons


def run_safety_check(config):
    """Returns {"status": "ready"|"needs_review", "passed": bool,
    "reasons": [str, ...]}. Empty reasons list = passed. Never raises --
    a strategy that can't even be checked cleanly (missing fields, etc.)
    is a validator.validate() concern, not this one's."""
    reasons = []
    reasons += check_duplicate_entry_exit_clauses(config)
    reasons += check_exit_gives_realistic_room(config)
    reasons += check_contradictory_entry_gates(config)
    passed = not reasons
    return {"status": "ready" if passed else "needs_review", "passed": passed, "reasons": reasons}
