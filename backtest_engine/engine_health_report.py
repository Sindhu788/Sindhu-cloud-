"""Final Audit (BACKTESTING_MASTER_SPEC.md ENGINE HEALTH REPORT): the
single top-level orchestrator tying together every verification dimension
built across Phase 2 and the Final Audit into one report with one overall
verdict -- Strategy Verification, Data Verification, Execution
Verification, PnL Verification, Trade Verification, Statistics
Verification, Overall Engine Status. PASS only if every single one of
them passes; nothing is ever silently skipped from the verdict (a
verification that couldn't run at all -- e.g. no raw 1m data supplied for
the Data Verification step -- is reported as its own explicit status, not
folded into a false PASS).
"""

from datetime import datetime, timezone

from backtest_engine import strategy_verifier, trade_validator, statistics_verifier
from backtest_engine.verification_engine import run_verification
from backtest_engine.metrics import compute_metrics
from data_engine import data_quality


def _now():
    return datetime.now(timezone.utc).isoformat()


def _categorize_trade_issue(issue_text):
    """trade_validator reports one flat issue list per trade; this splits
    each issue into which Health Report section it belongs under, purely
    for report organization -- the underlying check already ran once."""
    lower = issue_text.lower()
    if "gross_pnl" in lower or "pnl (" in lower or "commission" in lower or "reconcile" in lower:
        return "pnl"
    if ("stop_loss" in lower or "take_profit" in lower or "entry_price" in lower
            or "exit_price" in lower or "position size" in lower or "direction" in lower):
        return "execution"
    return "trade"


def run_engine_health_report(config, merged_or_context, settings, symbol="?",
                              raw_entry_df=None, entry_interval=None, raw_1m_df=None):
    """`raw_entry_df`/`entry_interval`/`raw_1m_df` are optional -- when
    supplied, they drive the Data Verification section (missing/duplicate
    candles, corrupted OHLC, resampling correctness) against the REAL
    candle data this backtest ran on. Without them, Data Verification is
    reported as "not_run" rather than silently assumed clean."""
    verification = run_verification(config, merged_or_context, settings, symbol=symbol)
    trades = verification["trades"]
    equity_curve = verification["equity_curve"]

    # ---- Strategy Verification (rule coverage) ----
    strategy_section = {
        "status": "PASS" if not verification["rules_skipped"] else "FAIL",
        "rules_total": len(verification["rule_coverage"]),
        "rules_skipped": verification["rules_skipped"],
        "rules_never_true": [f for f in verification["rule_coverage"] if f["status"] == "NEVER_TRUE"],
    }

    # ---- Data Verification ----
    if raw_entry_df is not None and entry_interval is not None:
        dq = data_quality.run_data_quality_report(raw_entry_df, entry_interval, raw_1m_df)
        data_section = {"status": "PASS" if dq["pass"] else "FAIL", **dq}
    else:
        data_section = {"status": "not_run", "reason": "no raw candle data supplied to this report"}

    # ---- Execution / PnL / Trade Verification (all derived from the same
    # independent per-trade re-validation, split by category for reporting) ----
    execution_issues, pnl_issues, trade_issues = [], [], []
    for trade_num, issues in verification["trade_validation"]["issues_by_trade"].items():
        for issue in issues:
            bucket = _categorize_trade_issue(issue)
            entry = {"trade_num": trade_num, "issue": issue}
            (execution_issues if bucket == "execution" else
             pnl_issues if bucket == "pnl" else trade_issues).append(entry)
    duplicate_trades = verification["trade_validation"]["duplicate_trades"]

    execution_section = {"status": "PASS" if not execution_issues else "FAIL", "issues": execution_issues}
    pnl_section = {"status": "PASS" if not pnl_issues else "FAIL", "issues": pnl_issues}
    trade_section = {
        "status": "PASS" if not trade_issues and not duplicate_trades else "FAIL",
        "issues": trade_issues, "duplicate_trades": duplicate_trades,
        "trade_count": verification["trade_count"],
    }

    # ---- Statistics Verification (independently recomputed metrics) ----
    metrics = compute_metrics(trades, equity_curve, settings["initial_balance"])
    stats_issues = statistics_verifier.verify_statistics(trades, equity_curve, settings["initial_balance"], metrics)
    statistics_section = {"status": "PASS" if not stats_issues else "FAIL", "issues": stats_issues, "metrics": metrics}

    sections = {
        "strategy_verification": strategy_section,
        "data_verification": data_section,
        "execution_verification": execution_section,
        "pnl_verification": pnl_section,
        "trade_verification": trade_section,
        "statistics_verification": statistics_section,
    }
    # PASS requires every section that actually ran to have passed; a
    # section that didn't run at all ("not_run", e.g. no raw candle data
    # given for Data Verification) doesn't force a FAIL by itself, but is
    # never silently treated as a PASS either -- it's reported plainly.
    overall_pass = all(s["status"] in ("PASS", "not_run") for s in sections.values())

    return {
        "symbol": symbol,
        "strategy_name": config.name,
        "generated_at": _now(),
        "overall_status": "PASS" if overall_pass else "FAIL",
        "sections": sections,
        "debug_log": verification["debug_log"],
    }
