"""A.2 -- Evolution Engine responsibilities: Analyze, Compare, Improve,
Mutate, Research, Rank, Archive, Generate new generations of EXISTING BOT
strategies. Deliberately never touches strategy_library (user-imported
strategies) -- every function here only reads/writes bot_strategies, so the
A.9 constraint is structural (there is no import of strategy_library
anywhere in this module).

Mutation itself is a fixed rule table over already-observed numbers
(evolution score breakdown, detected market regime), applied by
market_regime.adapt_params_for_regime -- not a random search and not a
learned model.
"""

from itertools import combinations

from data_engine import storage
from evolution_engine import generation_manager, market_regime, dna, rollback

MIN_TRADES_TO_JUDGE = 10        # a bot_strategy needs at least this many backtest trades before Archive can act on its score
ARCHIVE_SCORE_THRESHOLD = 20.0  # active strategies scoring below this (with enough trades) get archived, never deleted


def rank_strategies(base_id=None):
    """A.2's "Rank" -- every scored, active BOT strategy ordered best-first.
    Unscored strategies (no backtest run yet) sort last, not zero, so they
    aren't misread as "worst"."""
    rows = storage.list_bot_strategies(base_id=base_id, status="active", limit=5000)
    return sorted(rows, key=lambda s: (s["evolution_score"] is None, -(s["evolution_score"] or 0)))


def archive_underperformers(now_iso, threshold=ARCHIVE_SCORE_THRESHOLD, min_trades=MIN_TRADES_TO_JUDGE):
    """A.2's "Archive" -- flips status to 'archived' (see
    storage.archive_bot_strategy: never a DELETE) for any active BOT
    strategy that has actually been evaluated (enough backtest trades to
    trust the number) and still scores below threshold. Returns the list of
    ids archived this call."""
    archived = []
    for s in storage.list_bot_strategies(status="active", limit=5000):
        if s.get("evolution_score") is None:
            continue
        trades = (s.get("backtest_summary") or {}).get("trades", 0)
        if trades < min_trades:
            continue
        if s["evolution_score"] < threshold:
            storage.archive_bot_strategy(s["id"], now_iso)
            archived.append(s["id"])
    return archived


def research_dna_correlations(min_sample=3, max_combo_size=2):
    """A.2's "Research" -- cross-references every scored, active BOT
    strategy's DNA tags (evolution_engine.dna.extract_dna, already stored
    per-strategy) against its evolution_score to find which DNA tag
    combinations correlate with higher scores. Pure aggregation over
    numbers already in bot_strategies -- no model, no learning. Returns a
    best-first list of {dna_combo, avg_score, sample_size}; this is exactly
    what sindhu_strategy.deterministic_builder consults to justify each
    non-AI candidate ("Liquidity + Session historically scores highest")."""
    scored = [s for s in storage.list_bot_strategies(status="active", limit=5000) if s.get("evolution_score") is not None]
    buckets = {}
    for s in scored:
        tags = tuple(sorted(set(s.get("dna") or [])))
        for size in range(1, max_combo_size + 1):
            for combo in combinations(tags, size):
                buckets.setdefault(combo, []).append(s["evolution_score"])
    results = []
    for combo, scores in buckets.items():
        if len(scores) < min_sample:
            continue
        results.append({"dna_combo": list(combo), "avg_score": round(sum(scores) / len(scores), 2), "sample_size": len(scores)})
    results.sort(key=lambda r: -r["avg_score"])
    return results


def compare_generations(base_id):
    """A.2's "Compare" -- every generation of one lineage side by side,
    oldest first, so an improvement (or regression) across generations is
    directly visible."""
    return generation_manager.lineage_history(base_id)


def regime_context_for(base_id):
    """Grand Feature Expansion, Phase 6 Feature 9: Regime-Aware Evolution --
    mutate_strategy's own regime-adaptation branch below already existed,
    but was effectively DEAD CODE: its only real caller (evolution_engine.
    engine._tick) never passed exchange/symbol/timeframe, so the branch
    never fired in production. Derives all 3 from the lineage's own latest
    real backtest (sindhu_strategy.lifecycle.validate_and_backtest already
    records batch_id in backtest_summary) -- the same real coin/exchange
    this lineage was actually just tested against, not an arbitrary guess.
    Returns (None, None, None) when the lineage has no backtested batch
    yet, in which case mutate_strategy's regime branch simply stays
    skipped, exactly as it always has."""
    latest = rollback.effective_generation(base_id)
    if not latest:
        return None, None, None
    batch_id = (latest.get("backtest_summary") or {}).get("batch_id")
    if not batch_id:
        return None, None, None
    batch = storage.get_batch(batch_id)
    if not batch:
        return None, None, None
    symbols = (batch.get("settings") or {}).get("symbols") or []
    if not symbols:
        return None, None, None
    timeframe = (latest.get("config") or {}).get("timeframes", {}).get("entry")
    if not timeframe:
        return None, None, None
    return batch["exchange"], symbols[0], timeframe


def mutate_strategy(base_id, governor, now_iso, exchange=None, symbol=None, timeframe=None):
    """A.2's "Improve/Mutate/Generate new generations" for ONE existing BOT
    strategy lineage. Branches the newest generation's config by nudging a
    small set of numeric fields according to (a) which score component was
    weakest last time, and (b) the market regime detected right now (A.8) --
    both fixed rule tables, never random and never AI. Returns the new
    generation's id, or None if there's nothing to mutate (no prior
    generation), the lineage hasn't crossed its next 100-completed-trades
    evolution gate yet (see evolution_engine.rollback -- independent from
    and never touches the 25-trade Wilson score gate used elsewhere for
    signal confidence), or the Governor's max_generations_per_strategy cap
    for this lineage has already been reached."""
    latest = rollback.effective_generation(base_id)
    if latest is None:
        return None

    can_evolve, threshold = rollback.should_evolve(base_id, latest)
    if not can_evolve:
        return None

    config = dict(latest["config"])
    reasons = []

    breakdown = latest.get("score_breakdown") or {}
    if breakdown:
        weakest = min(
            (k for k in breakdown if not k.startswith("_")),
            key=lambda k: breakdown[k],
            default=None,
        )
        if weakest == "avg_rr" and config.get("risk_reward"):
            new_rr = round(min(config["risk_reward"] * 1.15, 5.0), 3)
            reasons.append(f"weakest component was avg_rr ({breakdown['avg_rr']:.1f}) -> risk_reward {config['risk_reward']} -> {new_rr}")
            config["risk_reward"] = new_rr
        elif weakest == "drawdown" and config.get("risk_pct"):
            new_rp = round(max(config["risk_pct"] * 0.85, 0.25), 3)
            reasons.append(f"weakest component was drawdown ({breakdown['drawdown']:.1f}) -> risk_pct {config['risk_pct']} -> {new_rp}")
            config["risk_pct"] = new_rp
        elif weakest == "stability":
            prior_be = config.get("breakeven_at_rr")
            config["breakeven_at_rr"] = 1.0
            reasons.append(f"weakest component was stability ({breakdown['stability']:.1f}) -> breakeven_at_rr {prior_be} -> 1.0")

    if exchange and symbol and timeframe:
        regime = market_regime.detect_regime(exchange, symbol, timeframe)
        adapted, regime_changes = market_regime.adapt_params_for_regime(config, regime)
        if regime_changes:
            config = adapted
            reasons.extend(regime_changes)

    if not reasons:
        reasons.append("no scored weakness or regime signal yet -- carried forward unchanged as a fresh generation for re-evaluation")

    dna_tags = dna.extract_dna(config)
    # Generation number for the id/label comes from the lineage's true
    # highest generation ever created (storage.latest_generation_for_base),
    # not `latest` (the effective/in-use one, which can be an earlier
    # generation after a rollback) -- generation numbers must always keep
    # incrementing and never collide with an already-archived generation's.
    true_latest = storage.latest_generation_for_base(base_id)
    new_name = f"{latest['name'].split(' (Gen')[0]} (Gen {true_latest['generation'] + 1})"
    new_id = generation_manager.create_next_strategy_generation(
        base_id, new_name, config, dna_tags, "evolution_mutation", False,
        "; ".join(reasons), now_iso, max_generations=governor.max_generations_per_strategy,
    )
    if new_id:
        rollback.record_evolution_event(base_id, latest, new_id, threshold, now_iso)
    return new_id
