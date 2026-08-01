"""Task 2 (Priority Batch 1) -- the 100-completed-trades Evolution gate,
before/after comparison recording, and automatic rollback.

Deliberately entirely separate from paper_trading.pattern_stats' 25-trade
Wilson score gate (used for signal confidence in paper_trading/telegram_bot.py
and paper_trading/auto_avoid.py) -- that gate is untouched by this module and
this module is never imported by it. This gate governs one thing only:
whether evolution_engine.mutator.mutate_strategy is allowed to create a new
generation for a BOT strategy lineage.

Trade count source: a BOT strategy generation's own backtest_summary.trades
(set once per generation by sindhu_strategy.lifecycle.validate_and_backtest),
never live paper trading -- BOT-generated candidates are not paper-traded.
"""

from datetime import datetime, timezone

from data_engine import storage

TRADE_THRESHOLD_STEP = 100      # evolve at 100, 200, 300, ... completed trades
MIN_TRADES_FOR_COMPARISON = 100  # a new generation needs this many of its own trades before its performance is judged

# The 4 core metrics Task 2 names for the before/after comparison and the
# rollback decision. `higher_is_better=False` for max_drawdown_pct since a
# LOWER drawdown is the better outcome.
_CORE_METRICS = [
    ("win_rate", True),
    ("total_pnl", True),
    ("avg_profit_factor", True),
    ("max_drawdown_pct", False),
]


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _trades_of(generation_row):
    if not generation_row:
        return 0
    return (generation_row.get("backtest_summary") or {}).get("trades", 0) or 0


def effective_generation(base_id):
    """The generation of `base_id` that is actually "in use" right now --
    normally the newest one, but pinned back to an earlier generation after
    a rollback. This is what mutate_strategy should branch its next mutation
    from, so a rolled-back generation's config is never built on top of."""
    gate = storage.get_trade_gate(base_id)
    if gate and gate.get("active_generation_id"):
        pinned = storage.get_bot_strategy(gate["active_generation_id"])
        if pinned is not None:
            return pinned
    return storage.latest_generation_for_base(base_id)


def should_evolve(base_id, generation_row=None):
    """Returns (True, threshold) if `base_id`'s effective generation has
    crossed a new 100-trade threshold that hasn't been evolved yet, else
    (False, None). Independent of and never touches the 25-trade Wilson
    score gate used elsewhere for signal confidence."""
    generation_row = generation_row if generation_row is not None else effective_generation(base_id)
    trades = _trades_of(generation_row)
    if trades < TRADE_THRESHOLD_STEP:
        return False, None
    threshold = (trades // TRADE_THRESHOLD_STEP) * TRADE_THRESHOLD_STEP
    gate = storage.get_trade_gate(base_id)
    last_evolved = gate["last_threshold_evolved"] if gate else 0
    if threshold <= last_evolved:
        return False, None
    return True, threshold


def record_evolution_event(base_id, parent_row, child_id, threshold, now_iso=None):
    """Called immediately after a new generation is created and the gate
    passed: captures the parent's real numbers as "before" (the child has no
    numbers yet -- it hasn't been backtested), marks this threshold as used
    for this lineage, and makes the new generation the active one (pending
    proof it isn't worse -- see try_finalize_comparison)."""
    now_iso = now_iso or _now_iso()
    before = _metrics_snapshot(parent_row)
    storage.create_evolution_comparison(base_id, parent_row["id"], child_id, threshold, before, now_iso)
    storage.set_trade_gate_threshold(base_id, threshold, now_iso)
    storage.set_active_generation_id(base_id, child_id, now_iso)


def _metrics_snapshot(generation_row):
    summary = (generation_row.get("backtest_summary") or {}) if generation_row else {}
    return {
        "trades": summary.get("trades", 0),
        "win_rate": summary.get("win_rate"),
        "total_pnl": summary.get("total_pnl"),
        "avg_profit_factor": summary.get("avg_profit_factor"),
        "max_drawdown_pct": summary.get("max_drawdown_pct"),
    }


def _is_regression(before, after):
    """"Worse... across the core metrics" is read as: worse on a majority
    (at least 3 of the 4) of win_rate / net PnL / profit factor / max
    drawdown, not noise on a single metric. Any metric missing on either
    side (None) is skipped rather than counted -- can't judge what wasn't
    measured. Returns True only if at least 3 metrics were actually
    comparable AND a majority of those came out worse."""
    worse_count = 0
    comparable_count = 0
    for key, higher_is_better in _CORE_METRICS:
        b, a = before.get(key), after.get(key)
        if b is None or a is None:
            continue
        comparable_count += 1
        is_worse = (a < b) if higher_is_better else (a > b)
        if is_worse:
            worse_count += 1
    if comparable_count < 3:
        return False
    return worse_count >= 3


def try_finalize_comparison(bot_strategy_id, now_iso=None):
    """Called after any BOT strategy generation gets a fresh backtest result
    (sindhu_strategy.lifecycle.validate_and_backtest). If this generation is
    the "child" of a pending (not-yet-judged) evolution event and now has
    enough of its own trades to be judged fairly, computes the after
    snapshot + verdict, and rolls back (pins the lineage's active generation
    back to the parent) if the child performed worse. Returns the finalized
    comparison dict, or None if there was nothing pending / not enough
    trades yet."""
    now_iso = now_iso or _now_iso()
    pending = storage.get_pending_comparison_for_child(bot_strategy_id)
    if pending is None:
        return None

    child = storage.get_bot_strategy(bot_strategy_id)
    if child is None or _trades_of(child) < MIN_TRADES_FOR_COMPARISON:
        return None

    after = _metrics_snapshot(child)
    regressed = _is_regression(pending["before"], after)
    verdict = "regressed" if regressed else "improved"

    storage.finalize_evolution_comparison(pending["id"], after, verdict, regressed, now_iso)
    if regressed:
        storage.set_active_generation_id(pending["base_id"], pending["parent_id"], now_iso)

    return {**pending, "after": after, "verdict": verdict, "rolled_back": regressed}
