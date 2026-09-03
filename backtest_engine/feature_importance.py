"""Feature Importance Ranking (Grand Feature Expansion, Phase 6 Feature
6): a per-strategy "which of my own conditions actually drive my
performance" tool via leave-one-out ablation. Genuinely distinct from
evolution_engine.mutator's research_dna_correlations(), which ranks DNA-
tag combinations across the WHOLE POPULATION of BOT strategies, never for
one specific strategy's own conditions.

Reuses the exact same bounded, fast, in-memory re-run infrastructure
backtest_engine.what_if_simulator already established (automation_pipeline
.optimizer._run_in_memory, ~30 days, a few symbols) -- removes each of a
strategy's own entry/confirmation conditions ONE AT A TIME and re-runs;
the conditions whose removal hurts net profit the MOST are the ones
actually doing the most work today."""

from automation_pipeline import optimizer
from backtest_engine.what_if_simulator import FAST_WINDOW_DAYS, MAX_SYMBOLS

_ABLATABLE_FIELDS = ("entry_conditions", "confirmation_conditions")


def _condition_label(cond):
    return cond.name or cond.indicator or cond.type


def _net_profit(config, exchange, symbols, settings, start_ms, end_ms):
    total = 0.0
    for symbol in symbols:
        metrics = optimizer._run_in_memory(config, exchange, symbol, settings, start_ms, end_ms)
        if metrics:
            total += metrics["net_profit"]
    return total


def rank_feature_importance(strategy_config, batch, max_symbols=3):
    """strategy_config: the CEO's real, currently-saved StrategyConfig --
    never mutated, only cloned. `batch` borrows a real symbol list + date
    range to replay against, same as what_if_simulator.run_what_if."""
    settings = batch.get("settings") or {}
    symbols = settings.get("symbols") or []
    start_ms, end_ms = settings.get("start_ms"), settings.get("end_ms")
    if not symbols or start_ms is None or end_ms is None:
        return None

    symbols = symbols[:min(max_symbols, MAX_SYMBOLS)]
    window_ms = FAST_WINDOW_DAYS * 24 * 3600 * 1000
    windowed_start_ms = max(start_ms, end_ms - window_ms)
    exchange = batch["exchange"]

    baseline_profit = _net_profit(strategy_config, exchange, symbols, settings, windowed_start_ms, end_ms)

    ablatable = []
    for field_name in _ABLATABLE_FIELDS:
        conditions = getattr(strategy_config, field_name, None) or []
        for i in range(len(conditions)):
            ablatable.append((field_name, i, conditions[i]))

    if len(ablatable) < 2:
        return {
            "baseline_net_profit": round(baseline_profit, 2), "conditions": [],
            "symbols": symbols, "window_days": FAST_WINDOW_DAYS,
            "reason": "needs at least 2 entry/confirmation conditions to compare importance",
        }

    rankings = []
    for field_name, index, cond in ablatable:
        modified = optimizer._clone_config(strategy_config)
        remaining = list(getattr(modified, field_name))
        del remaining[index]
        setattr(modified, field_name, remaining)
        profit_without = _net_profit(modified, exchange, symbols, settings, windowed_start_ms, end_ms)
        rankings.append({
            "field": field_name, "index": index, "label": _condition_label(cond),
            "net_profit_without": round(profit_without, 2),
            "impact": round(baseline_profit - profit_without, 2),
        })

    rankings.sort(key=lambda r: r["impact"], reverse=True)
    return {
        "baseline_net_profit": round(baseline_profit, 2), "conditions": rankings,
        "symbols": symbols, "window_days": FAST_WINDOW_DAYS,
    }
