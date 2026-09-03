"""Unified Strategy Detail View (Dashboard Consolidation Group, item 6):
one function that pulls together everything about a single strategy that
is currently scattered across separate features -- Confidence Score,
Sharpe/Max Drawdown, Market Regime for its actively-traded coins,
Correlation Warnings it's involved in, Drawdown Protection status, Lesson
Candidates/Auto-Lessons, and version Genealogy. Every value here is read
from the already-existing, already-verified source for that data -- this
module computes NOTHING new, it only assembles.
"""

from data_engine import storage
from backtest_engine import strategy_library as lib
from backtest_engine.strategy_safety_check import run_safety_check
from backtest_engine.performance_dashboard import evaluate_strategy_performance
from backtest_engine import validator
from paper_trading import insights, regime, correlation


def get_strategy_profile(strategy_id, exchange, correlation_warnings=None):
    """correlation_warnings: pass the caller's already-cached
    correlation.detect_warnings(exchange) result (see the ~60s-cold
    warning in correlation.py) -- if omitted, computes it fresh here,
    which is fine for tests/scripts but would make a live endpoint slow
    on every uncached call."""
    meta = next((m for m in lib.list_all() if m["id"] == strategy_id), None)
    if not meta:
        return None

    since = insights.fresh_session_start()
    confidence = insights.all_confidence_scores().get(strategy_id)
    streak = insights.compute_streak(strategy_id)
    risk = insights.compute_risk_metrics(strategy_id, since=since)
    # Grand Feature Expansion, Phase 3 Feature 7: Value at Risk. Uses ALL
    # historical closed trades (no `since` scoping) unlike Sharpe/Sortino
    # above -- a real 95th-percentile estimate needs pattern_stats.MIN_SAMPLE_SIZE
    # (25) trades, which a fresh session alone would rarely have yet.
    var = insights.compute_value_at_risk(strategy_id)
    # Grand Feature Expansion, Phase 3 Feature 2: Strategy Health Score.
    # Uses ALL historical trades (no `since` scoping), same reasoning as
    # Value at Risk above -- a composite trust score should reflect the
    # strategy's whole track record, not just the current session.
    health = insights.compute_strategy_health_score(strategy_id)
    # Grand Feature Expansion, Phase 3 Feature 12: Strategy Aging Analysis.
    aging = insights.compute_strategy_aging(strategy_id)
    # Grand Feature Expansion, Phase 3 Feature 8: MAE/MFE aggregate.
    mae_mfe = insights.compute_mae_mfe_stats(strategy_id)
    paused, pause_reason, paused_at = storage.is_strategy_paused(strategy_id)

    lesson_candidates = [c for c in storage.list_paper_lesson_candidates() if c["strategy_id"] == strategy_id]
    auto_lessons = [l for l in storage.list_paper_auto_lessons(active_only=True) if l["strategy_id"] == strategy_id]
    avoid_rules = [r for r in storage.list_paper_auto_avoid_rules(active_only=True) if r["strategy_id"] == strategy_id]

    open_positions = [p for p in storage.get_open_paper_positions(exchange) if p.get("strategy_id") == strategy_id]
    symbols = sorted(set(p["symbol"] for p in open_positions))
    regimes = {}
    for s in symbols:
        try:
            r = regime.classify_regime(exchange, s)
        except Exception:
            r = None
        if r:
            regimes[s] = r["regime"]

    all_warnings = correlation_warnings if correlation_warnings is not None else correlation.detect_warnings(exchange)
    my_warnings = [w for w in all_warnings if any(s in symbols for s in w["symbols"])]

    try:
        cfg = lib.load(strategy_id)
        safety_passed = run_safety_check(cfg)["passed"] and not validator.validate(cfg)
    except Exception:
        safety_passed = False
    try:
        perf = evaluate_strategy_performance(strategy_id)
        backtest_verdict = perf.get("verdict") if perf else None
    except Exception:
        backtest_verdict = None
    with storage.get_conn() as conn:
        stats_row = conn.execute(
            "SELECT COUNT(*), SUM(CASE WHEN status='closed' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN status='closed' AND pnl>0 THEN 1 ELSE 0 END) "
            "FROM paper_positions WHERE strategy_id=? AND created_at >= ?", (strategy_id, since)
        ).fetchone()
    total, closed, wins = stats_row
    closed = closed or 0
    win_rate = round((wins or 0) / closed * 100, 1) if closed else 0.0
    readiness = insights.real_trading_readiness(
        strategy_id, {"closed_trades": closed, "win_rate": win_rate},
        safety_passed, meta.get("walk_forward_status"),
    )

    # Batch 5, Task 2: if this strategy was re-extracted with a materially
    # different result, everything traded before that correction was
    # generated under an incomplete understanding of the rules and its
    # accumulated performance numbers cannot be trusted. Never hidden,
    # never deleted -- surfaced explicitly with the real old-vs-new counts
    # so the CEO can see exactly what changed and why.
    supersession = None
    correction = storage.get_latest_extraction_correction(strategy_id)
    if correction:
        superseded_stats = storage.get_versioned_paper_stats(strategy_id)
        corrected_stats = storage.get_versioned_paper_stats(strategy_id, min_version=correction["corrected_at_version"])
        superseded_only_count = superseded_stats["closed_count"] - corrected_stats["closed_count"]
        supersession = {
            "corrected_at_version": correction["corrected_at_version"],
            "corrected_at": correction["corrected_at"],
            "previous_expected_count": correction["previous_expected_count"],
            "previous_captured_count": correction["previous_captured_count"],
            "new_expected_count": correction["new_expected_count"],
            "new_captured_count": correction["new_captured_count"],
            "superseded_trade_count": max(superseded_only_count, 0),
            "superseded_signals_sent": storage.count_telegram_signals_for_superseded_positions(
                strategy_id, correction["corrected_at_version"]),
            "corrected_stats": corrected_stats,
        }

    return {
        "id": strategy_id, "name": meta["name"], "status": meta.get("status"),
        "archived": meta.get("archived", False),
        "walk_forward_status": meta.get("walk_forward_status"),
        "backtest_verdict": backtest_verdict,
        "confidence_score": confidence,
        "streak": streak,
        "risk_metrics": risk,
        "value_at_risk": var,
        "health_score": health,
        "aging": aging,
        "mae_mfe": mae_mfe,
        "paused": paused, "pause_reason": pause_reason, "paused_at": paused_at,
        "open_position_count": len(open_positions),
        "traded_coin_regimes": regimes,
        "correlation_warnings": my_warnings,
        "lesson_candidates": lesson_candidates,
        "auto_lessons": auto_lessons,
        "auto_avoid_rules": avoid_rules,
        "genealogy": lib.version_history(strategy_id),
        "real_trading_readiness": readiness,
        "supersession": supersession,
    }
