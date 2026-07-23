"""Phase 2 (BACKTESTING_MASTER_SPEC.md Requirements 12/13/16): runs ONE
real backtest with full instrumentation and produces a single
VerificationReport covering the whole chain -- Strategy JSON -> Rule
Engine -> Trade Execution -> Trade Results -- plus a Debug Mode log
(Rule Loaded -> Rule Executed -> Trade Open -> Trade Closed -> PnL ->
Verification) and a final PASS/FAIL verdict. Never silently drops a
finding: PASS requires every rule reached (no SKIPPED) and every trade
independently re-verified (trade_validator.validate_all_trades).
"""

from datetime import datetime, timezone

from backtest_engine.configured_strategy import ConfiguredStrategy
from backtest_engine.engine import run_backtest
from backtest_engine import strategy_verifier, trade_validator


def _now():
    return datetime.now(timezone.utc).isoformat()


def run_verification(config, merged_or_context, settings, symbol="?"):
    """`merged_or_context` is either a MultiTimeframeContext (has a
    `.frames` attribute -- prepare_context() is called on it here) or an
    already-merged dataframe. Returns a VerificationReport dict."""
    debug_log = []

    def _log(stage, **extra):
        debug_log.append({"stage": stage, "at": _now(), **extra})

    strat = ConfiguredStrategy(config)

    total_rules = sum(len(getattr(config, b, []) or []) for b in strategy_verifier._BUCKETS)
    _log("strategy_loaded", strategy_name=config.name, symbol=symbol)
    _log("rule_loaded", total_rules=total_rules)

    if hasattr(merged_or_context, "frames"):
        merged = strat.prepare_context(merged_or_context)
    else:
        merged = merged_or_context
    df = strat.prepare(merged)
    _log("data_loaded", bars=len(df))

    coverage_counts = strategy_verifier.install_coverage_trace(strat)

    def _on_trade(trade):
        _log("trade_open", trade_num=trade["trade_num"], side=trade["side"],
             entry_time=trade["entry_time"], entry_price=trade["entry_price"],
             entry_type=trade.get("entry_type"))
        _log("trade_closed", trade_num=trade["trade_num"], exit_time=trade["exit_time"],
             exit_price=trade["exit_price"], exit_reason=trade["exit_reason"])
        _log("pnl", trade_num=trade["trade_num"], pnl=trade["pnl"], gross_pnl=trade.get("gross_pnl"))

    _log("rule_executed_start")
    trades, equity_curve, final_balance = run_backtest(df, strat, settings, on_trade=_on_trade)
    _log("rule_executed_end", trades=len(trades))
    _log("results_generated", trade_count=len(trades), final_balance=final_balance)

    coverage = strategy_verifier.verify_rule_coverage(config, coverage_counts)
    skipped = [f for f in coverage if f["status"] == "SKIPPED"]

    validation = trade_validator.validate_all_trades(trades, df)
    for trade_num, issues in validation["issues_by_trade"].items():
        _log("verification", trade_num=trade_num, status="FAIL", issues=issues)
    verified_ok = {t["trade_num"] for t in trades} - set(validation["issues_by_trade"].keys())
    for trade_num in verified_ok:
        _log("verification", trade_num=trade_num, status="PASS")

    overall_pass = validation["pass"] and not skipped

    return {
        "symbol": symbol,
        "strategy_name": config.name,
        "generated_at": _now(),
        "overall_status": "PASS" if overall_pass else "FAIL",
        "rule_coverage": coverage,
        "rules_skipped": skipped,
        "trade_validation": validation,
        "debug_log": debug_log,
        "trade_count": len(trades),
        "final_balance": final_balance,
        "trades": trades,
        "equity_curve": equity_curve,
    }
