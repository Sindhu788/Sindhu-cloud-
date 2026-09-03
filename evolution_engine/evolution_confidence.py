"""Evolution Confidence Score (Grand Feature Expansion, Phase 6 Feature
10): how much to trust ONE finalized evolution/tuning outcome (an
evolution_comparisons row) -- genuinely distinct from paper_trading/
confidence.py (per-TRADE signal confidence) and pattern_stats.py
(per-pattern statistical classification, used for signal gating). Neither
of those existed for judging an EVOLUTION comparison's own trustworthiness.

A plain, documented weighted sum -- same "no hidden model, every component
shown" convention already used by paper_trading.insights.
compute_strategy_health_score. Weights (sum to 100):
  - Sample size (40): the "after" generation's own trade count, scaled
    against rollback.MIN_TRADES_FOR_COMPARISON (100) -- full marks once it
    has at least that many, since that's already this codebase's own
    established floor for judging a generation fairly.
  - Improvement margin (40): how far apart before/after actually were
    across the 4 core metrics rollback.py already compares (win_rate,
    total_pnl, avg_profit_factor, max_drawdown_pct) -- a wide, decisive
    swing (either direction) scores higher than a razor-thin one, since a
    razor-thin difference is more likely to be noise.
  - Metric coverage (20): how many of the 4 core metrics were actually
    comparable (present on both sides) -- a verdict backed by all 4 is
    more trustworthy than one judged on the bare minimum of 3.
"""

from evolution_engine.rollback import _CORE_METRICS, MIN_TRADES_FOR_COMPARISON

SAMPLE_SIZE_WEIGHT = 40.0
MARGIN_WEIGHT = 40.0
COVERAGE_WEIGHT = 20.0


def _relative_margin(before, after, higher_is_better):
    """How far apart before/after are, relative to the larger magnitude of
    the two -- a scale-independent 0..1+ swing size. 0 when unchanged."""
    denom = max(abs(before), abs(after), 1e-9)
    diff = (after - before) if higher_is_better else (before - after)
    return diff / denom


def compute_confidence(comparison):
    """comparison: a finalized evolution_comparisons dict (storage.
    list_evolution_comparisons()'s own row shape) -- must have both
    "before" and "after" populated (i.e. already judged, not pending)."""
    before, after = comparison.get("before"), comparison.get("after")
    if not before or not after:
        return {"confidence_score": None, "components": None,
                "reason": "not yet judged -- no 'after' numbers to compare"}

    trades = after.get("trades", 0) or 0
    sample_size_score = min(SAMPLE_SIZE_WEIGHT, (trades / MIN_TRADES_FOR_COMPARISON) * SAMPLE_SIZE_WEIGHT)

    margins = []
    comparable = 0
    for key, higher_is_better in _CORE_METRICS:
        b, a = before.get(key), after.get(key)
        if b is None or a is None:
            continue
        comparable += 1
        margins.append(abs(_relative_margin(b, a, higher_is_better)))

    coverage_score = (comparable / len(_CORE_METRICS)) * COVERAGE_WEIGHT
    # Average relative swing, capped at 1.0 (a 100%+ swing on any single
    # metric already earns full marks for this component -- beyond that
    # doesn't mean "more trustworthy," just "a bigger number").
    avg_margin = min(1.0, (sum(margins) / len(margins))) if margins else 0.0
    margin_score = avg_margin * MARGIN_WEIGHT

    total = round(sample_size_score + margin_score + coverage_score, 1)
    return {
        "confidence_score": total,
        "components": {
            "sample_size_score": round(sample_size_score, 1),
            "margin_score": round(margin_score, 1),
            "coverage_score": round(coverage_score, 1),
            "trades": trades, "comparable_metrics": comparable,
        },
        "reason": None,
    }
