"""Historical What-If Simulator (Grand Feature Expansion, Phase 5 Feature
14): "what if this ONE parameter had been different, replayed against the
same real historical data" -- a genuine counterfactual RE-SIMULATION,
distinct from both Monte Carlo (backtest_engine/monte_carlo.py, reshuffles
an already-recorded trade PnL sequence, no re-simulation at all) and
Challenge Mode's own "What-If" (paper_trading/challenge_analysis.py,
filters which real, already-existing strategy-coin combos to consider for
a savings-style target -- never changes a historical parameter and
re-runs).

Reuses automation_pipeline.optimizer's own in-memory backtest re-run
(_run_in_memory -- a thin wrapper over ConfiguredStrategy + engine.
run_backtest, no database writes) exactly as automation_pipeline.
walk_forward already does, rather than building a second in-memory runner.
Bounded to the same "~30 days, a few symbols" fast-subset convention the
Optimizer's own default screening window already uses (see optimizer.py's
docstring) -- a full-history, every-coin re-simulation would be too slow
for a synchronous request, so this is an honest, clearly-scoped preview,
not a full validation pass (a strategy can still be re-optimized and
fully re-validated the normal way if a what-if result looks promising)."""

from automation_pipeline import optimizer
from backtest_engine.strategy_config import SLTPSpec

FAST_WINDOW_DAYS = 30
MAX_SYMBOLS = 5
_SLTP_FIELDS = {"stop_loss", "take_profit"}


def _apply_parameter_changes(config, parameter_changes):
    modified = optimizer._clone_config(config)
    for field, value in parameter_changes.items():
        if field in _SLTP_FIELDS and isinstance(value, dict):
            value = SLTPSpec(**value)
        setattr(modified, field, value)
    return modified


def run_what_if(strategy_config, batch, parameter_changes, max_symbols=3):
    """Returns {"original": {...}, "modified": {...}, "symbols": [...],
    "window_days": N} or None if the reference batch has no usable
    settings (symbols/date range) to replay against.

    `strategy_config` is the CEO's real, currently-saved StrategyConfig
    (from backtest_engine.strategy_library.load) -- never mutated, only
    cloned. `batch` is storage.get_batch(batch_id)'s dict, used purely to
    borrow a real symbol list + date range to replay against; its own
    original results are never touched or recomputed in place."""
    settings = batch.get("settings") or {}
    symbols = settings.get("symbols") or []
    start_ms, end_ms = settings.get("start_ms"), settings.get("end_ms")
    if not symbols or start_ms is None or end_ms is None:
        return None

    max_symbols = min(max_symbols, MAX_SYMBOLS)
    symbols = symbols[:max_symbols]
    window_ms = FAST_WINDOW_DAYS * 24 * 3600 * 1000
    windowed_start_ms = max(start_ms, end_ms - window_ms)

    exchange = batch["exchange"]
    modified_config = _apply_parameter_changes(strategy_config, parameter_changes)

    original_trades_total, modified_trades_total = 0, 0
    original_net, modified_net = 0.0, 0.0
    per_symbol = []
    for symbol in symbols:
        original = optimizer._run_in_memory(strategy_config, exchange, symbol, settings, windowed_start_ms, end_ms)
        modified = optimizer._run_in_memory(modified_config, exchange, symbol, settings, windowed_start_ms, end_ms)
        per_symbol.append({"symbol": symbol, "original": original, "modified": modified})
        if original:
            original_trades_total += original["total_trades"]
            original_net += original["net_profit"]
        if modified:
            modified_trades_total += modified["total_trades"]
            modified_net += modified["net_profit"]

    return {
        "symbols": symbols,
        "window_days": FAST_WINDOW_DAYS,
        "per_symbol": per_symbol,
        "original": {"total_trades": original_trades_total, "net_profit": round(original_net, 2)},
        "modified": {"total_trades": modified_trades_total, "net_profit": round(modified_net, 2)},
        "parameter_changes": parameter_changes,
    }
