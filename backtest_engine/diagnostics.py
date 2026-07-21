"""Condition-Hit Report -- when a backtest produces 0 trades on a coin,
this answers "why": for each entry condition individually, how many bars it
was actually true (respecting its own lookback window), and how many bars
every one of them was true together. Pure rule-based counting, reusing the
exact same evaluator every real trade decision uses (ConfiguredStrategy._eval)
-- never a separate approximation that could disagree with the real engine.
"""

from backtest_engine.configured_strategy import ConfiguredStrategy


def _describe_condition(cond):
    if cond.type == "concept":
        direction = f"{cond.direction} " if cond.direction else ""
        window = cond.lookback_bars if cond.lookback_bars is not None else 10
        window_desc = "same bar" if window <= 1 else f"within {window} bars"
        return f"{direction}{cond.name} ({window_desc})"
    if cond.type == "indicator_compare":
        return f"{cond.indicator} {cond.op} {cond.value}"
    if cond.type == "price_compare":
        return f"price {cond.op} {cond.indicator}"
    if cond.type == "indicator_vs_indicator":
        return f"{cond.indicator} {cond.op} {cond.indicator2}"
    if cond.type == "session":
        return f"session = {cond.name}"
    if cond.type == "trend":
        return f"trend = {cond.direction}"
    return cond.text or "unclear condition"


def condition_hit_report(config, merged_df):
    """Returns:
    {"total_bars": int,
     "per_condition": [{"description": str, "true_bars": int}, ...],
     "all_together_bars": int}
    Covers entry_conditions AND confirmation_conditions -- ConfiguredStrategy.
    on_bar() requires BOTH buckets true together before it will ever return a
    buy/sell Signal (entry_conditions first, then confirmation_conditions
    gates on top), so a diagnostic that only looked at entry_conditions could
    report heavy hits on every entry condition while missing the real reason
    for 0 trades: a confirmation_conditions combination that can never be
    satisfied (e.g. "rsi < 30" AND "rsi > 70" required together). Combining
    both buckets here mirrors on_bar()'s actual AND-gate exactly. An
    empty/unusable frame returns zeros rather than raising, since this only
    ever runs as a diagnostic after the real backtest already completed
    (successfully, with 0 trades)."""
    n = len(merged_df)
    # A Long/Short strategy has two independent gates instead of one shared
    # entry_conditions -- report on whichever is populated (or both) rather
    # than silently reporting nothing just because entry_conditions itself
    # is empty by design in that mode.
    entry_side = list(config.entry_conditions) or (list(config.long_entry_conditions) + list(config.short_entry_conditions))
    conditions = entry_side + list(config.confirmation_conditions)

    if not conditions or n == 0:
        return {"total_bars": n, "per_condition": [], "all_together_bars": 0}

    strat = ConfiguredStrategy(config)
    # Defensive, not just relying on the caller (mtf_worker.py) having
    # already run this dataframe through engine.run_backtest -- prepare()
    # is what aliases entry_close/entry_open/... to close/open/... that
    # price_compare conditions read directly. Idempotent: a no-op if the
    # aliases already exist.
    merged_df = strat.prepare(merged_df)
    hit_flags = [[False] * n for _ in conditions]

    for i in range(n):
        for ci, cond in enumerate(conditions):
            try:
                hit_flags[ci][i] = bool(strat._eval(cond, merged_df, i))
            except Exception:
                hit_flags[ci][i] = False

    all_together_bars = sum(
        1 for i in range(n) if all(hit_flags[ci][i] for ci in range(len(conditions)))
    )
    per_condition = [
        {"description": _describe_condition(cond), "true_bars": sum(hit_flags[ci])}
        for ci, cond in enumerate(conditions)
    ]

    return {"total_bars": n, "per_condition": per_condition, "all_together_bars": all_together_bars}


def plain_language_diagnosis(report):
    """Part 2 (auto-surfaced 0-trade diagnosis): turns a condition_hit_report
    dict into one plain-English sentence explaining WHY this coin produced
    zero trades, so it reads directly in the results view instead of
    requiring someone to interpret a raw true_bars table themselves.

    Distinguishes two real failure shapes:
    - one or more conditions never fired at all (the common case -- e.g. a
      role/timeframe or concepts_used mismatch like the ones Part 1 fixes)
    - every condition fires on its own, but never all together on the same
      bar (a genuinely-strict-combination case, not a silent bug)."""
    per_condition = report.get("per_condition") or []
    if not per_condition:
        return "No entry conditions were defined for this strategy, so there was nothing to evaluate."

    def _fmt(n):
        return f"{n:,}"

    never_fired = [pc for pc in per_condition if pc["true_bars"] == 0]
    fired = [pc for pc in per_condition if pc["true_bars"] > 0]

    if never_fired:
        blocking = " and ".join(f"'{pc['description']}'" for pc in never_fired)
        plural = "condition" if len(never_fired) == 1 else "conditions"
        sentence = f"This coin got 0 trades because the {blocking} {plural} never triggered (0 times)"
        if fired:
            others = ", ".join(f"{pc['description']}: {_fmt(pc['true_bars'])}" for pc in fired)
            sentence += f", while other conditions triggered thousands of times ({others})."
        else:
            sentence += "."
        return sentence

    # Every condition fired individually, but never all on the same bar.
    detail = ", ".join(f"{pc['description']}: {_fmt(pc['true_bars'])}" for pc in fired)
    return (
        f"Every condition triggered on its own ({detail}), but never all at the same time -- "
        f"0 of {_fmt(report.get('total_bars', 0))} bars had all of them true together. "
        f"The combination may be too strict, or two conditions may be contradictory."
    )
