"""B.4 -- Candidate Lifecycle. Every daily SINDHU Strategy candidate is
already saved permanently at creation time (evolution_engine.generation_manager,
never overwritten/deleted) and is routed through the EXACT SAME
validation -> backtest -> report pipeline already used for user-imported
strategies: backtest_engine.validator.validate(), backtest_engine.runner.
run_mtf_batch(), and backtest_engine.reports.generate_report() -- no
separate/lighter pipeline for BOT candidates, so a BOT candidate's measured
performance is directly comparable to any user strategy's.
"""

from datetime import datetime, timezone

from backtest_engine import validator, runner, reports
from backtest_engine.strategy_config import StrategyConfig
from data_engine import storage
from evolution_engine import scoring, rollback


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def validate_and_backtest(bot_strategy_id, exchange, symbols, settings=None, use_multiprocessing=False):
    """Runs one bot_strategy through the real validate()/run_mtf_batch()/
    generate_report() pipeline, then computes and stores its Evolution
    Score (evolution_engine.scoring) from the real result. Never raises for
    an invalid config -- an invalid candidate stays saved (created already)
    and is simply recorded as such, per B.4's "saved permanently...even if
    low-quality." Returns
    {"validated", "errors", "batch_id", "backtest_summary", "evolution_score"}."""
    row = storage.get_bot_strategy(bot_strategy_id)
    if row is None:
        raise ValueError(f"unknown bot strategy id: {bot_strategy_id}")

    config = StrategyConfig.from_dict(row["config"])
    errors = validator.validate(config)
    if errors:
        storage.update_bot_strategy_result(bot_strategy_id, backtest_summary={"errors": errors}, now_iso=_now_iso())
        return {"validated": False, "errors": errors, "batch_id": None, "backtest_summary": None, "evolution_score": None}

    full_settings = dict(settings or {"initial_balance": 10000.0, "risk_pct_default": 1.0})
    batch_id = runner.run_mtf_batch(config, exchange, symbols, full_settings, use_multiprocessing=use_multiprocessing)
    summary = reports.generate_report(batch_id)

    stats = {
        "trades": summary.get("total_trades", 0),
        "wins": summary.get("wins", 0),
        "total_pnl": summary.get("total_pnl") or 0.0,
        "avg_rr": summary.get("avg_risk_reward"),
        "max_drawdown_pct": summary.get("max_drawdown_pct"),
        "profit_factor": summary.get("avg_profit_factor"),
    }
    score, breakdown = scoring.compute_evolution_score(stats)
    backtest_summary = {
        "batch_id": batch_id, "trades": stats["trades"], "wins": summary.get("wins"),
        "losses": summary.get("losses"), "win_rate": summary.get("win_rate"),
        "total_pnl": summary.get("total_pnl"), "max_drawdown_pct": summary.get("max_drawdown_pct"),
        "avg_profit_factor": summary.get("avg_profit_factor"), "avg_risk_reward": summary.get("avg_risk_reward"),
    }
    now_iso = _now_iso()
    storage.update_bot_strategy_result(bot_strategy_id, evolution_score=score, score_breakdown=breakdown,
                                        backtest_summary=backtest_summary, now_iso=now_iso)
    # Task 2: if this generation is the child of a pending evolution
    # before/after comparison and now has enough of its own trades, judge it
    # against its parent and roll back automatically if it did worse.
    rollback.try_finalize_comparison(bot_strategy_id, now_iso)
    return {"validated": True, "errors": [], "batch_id": batch_id, "backtest_summary": backtest_summary, "evolution_score": score}
