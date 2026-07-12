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
    Covers entry_conditions only -- that's the bucket that decides whether
    a trade is even considered. An empty/unusable frame returns zeros
    rather than raising, since this only ever runs as a diagnostic after
    the real backtest already completed (successfully, with 0 trades)."""
    n = len(merged_df)
    conditions = config.entry_conditions

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
