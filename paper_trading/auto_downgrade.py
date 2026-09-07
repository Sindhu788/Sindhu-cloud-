"""Grand Master Prompt, Phase 2.4: Auto-Downgrade Rule.

If a strategy's last 100 PAPER-TRADING closed trades show a Profit Factor
below 1.0, OR a peak-to-trough drawdown within that same 100-trade window
exceeding a sensible dollar threshold, this strategy's LIVE paper-trading
classification is flagged "downgraded" here.

This is DELIBERATELY separate from and never overrides the backtest-based
Profitable/Under-Evaluation label (sindhu_web/strategy_aggregate.py) --
that label answers "did this strategy look good in backtesting", this one
answers "is it actually performing in live paper trading right now". A
strategy can be Backtest-Profitable and Live-Downgraded at the same time,
or vice versa -- both are shown, neither is silently replaced by the
other.

NEVER auto-disables, auto-pauses, or removes a strategy -- that already
exists as a completely separate mechanism (paper_trading/drawdown_guard.py,
the per-strategy consecutive-loss pause). This module only classifies and
permanently logs (via storage.record_audit_event) the MOMENT a strategy's
status changes, so the CEO can see the history, not just today's snapshot.

Scheduling follows the same "check hourly, only act once genuinely due"
convention as paper_trading/status_ping.py and cloud_sync.py.
"""
import threading
from datetime import datetime, timezone

from data_engine import storage
from data_engine.logging_setup import log as default_log

MIN_TRADES_FOR_EVALUATION = 100
# A "sensible threshold" per the task's own wording -- there is no existing
# per-strategy dollar drawdown threshold elsewhere to reuse, so this picks
# 25% of the strategy's own configured initial_balance as a conservative,
# clearly-documented default. Deliberately a plain module constant (not a
# new user-facing setting) -- can be promoted to a real setting later if
# the CEO wants it tunable, without changing the rule's meaning.
DRAWDOWN_THRESHOLD_FRACTION_OF_INITIAL_BALANCE = 0.25
CHECK_INTERVAL_SECONDS = 3600

_stop_flag = threading.Event()
_thread = None


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _peak_to_trough_drawdown(pnls_oldest_first):
    """Max peak-to-trough decline of the cumulative pnl curve built purely
    from these trades' own pnl (not the strategy's real running balance --
    this module only ever sees the last N trades, not the full history a
    true equity curve would need). Returned in the same dollar units as
    pnl; 0.0 if the curve never dips below a prior peak."""
    cumulative = 0.0
    peak = 0.0
    worst = 0.0
    for pnl in pnls_oldest_first:
        cumulative += pnl or 0.0
        peak = max(peak, cumulative)
        worst = min(worst, cumulative - peak)
    return abs(worst)


def evaluate_strategy(strategy_id, initial_balance=10000.0):
    """Computes the CURRENT live classification from real closed-trade
    data -- never reads or writes any cached "downgraded" flag itself
    (that's check_and_log_if_changed()'s job). Returns a dict always
    containing "available" and, when True, "downgraded"/"profit_factor"/
    "sample_size"/"reason"."""
    trades = storage.get_last_n_closed_paper_trades(strategy_id, n=MIN_TRADES_FOR_EVALUATION)
    if len(trades) < MIN_TRADES_FOR_EVALUATION:
        return {"available": False, "sample_size": len(trades),
                "reason": f"Only {len(trades)}/{MIN_TRADES_FOR_EVALUATION} closed paper trades so far."}

    pnls_newest_first = [t["pnl"] or 0.0 for t in trades]
    pnls_oldest_first = list(reversed(pnls_newest_first))
    gross_profit = sum(p for p in pnls_newest_first if p > 0)
    gross_loss = abs(sum(p for p in pnls_newest_first if p < 0))
    pf = (gross_profit / gross_loss) if gross_loss else None
    drawdown = _peak_to_trough_drawdown(pnls_oldest_first)
    drawdown_threshold = initial_balance * DRAWDOWN_THRESHOLD_FRACTION_OF_INITIAL_BALANCE

    pf_fails = pf is not None and pf < 1.0
    dd_fails = drawdown > drawdown_threshold
    downgraded = pf_fails or dd_fails

    reasons = []
    if pf_fails:
        reasons.append(f"Profit Factor {pf:.2f} over last {MIN_TRADES_FOR_EVALUATION} trades is below 1.0")
    if dd_fails:
        reasons.append(f"drawdown {drawdown:.2f} over last {MIN_TRADES_FOR_EVALUATION} trades exceeds "
                        f"the {drawdown_threshold:.2f} threshold ({DRAWDOWN_THRESHOLD_FRACTION_OF_INITIAL_BALANCE:.0%} of initial balance)")

    return {
        "available": True,
        "downgraded": downgraded,
        "profit_factor": round(pf, 4) if pf is not None else None,
        "drawdown": round(drawdown, 2),
        "drawdown_threshold": round(drawdown_threshold, 2),
        "sample_size": len(trades),
        "reason": "; ".join(reasons) if reasons else "Performing within normal bounds.",
    }


def check_and_log_if_changed(strategy_id, initial_balance=10000.0):
    """Evaluates, and writes a permanent audit_trail_log entry ONLY the
    moment the downgraded flag actually flips (not on every check) --
    otherwise an hourly scheduler would flood the audit trail with an
    identical "still downgraded" row forever."""
    result = evaluate_strategy(strategy_id, initial_balance=initial_balance)
    if not result["available"]:
        return result

    previous = storage.get_paper_downgrade_state(strategy_id)
    now = _now_iso()
    storage.set_paper_downgrade_state(
        strategy_id, result["downgraded"], result["profit_factor"], result["sample_size"], result["reason"], now,
    )
    changed = previous is None or bool(previous["downgraded"]) != result["downgraded"]
    if changed:
        storage.record_audit_event(
            strategy_id, "strategy_downgrade",
            f"{'DOWNGRADED' if result['downgraded'] else 'RESTORED'} (live paper-trading): {result['reason']}",
            now,
        )
        default_log(f"[auto-downgrade] {strategy_id}: {'DOWNGRADED' if result['downgraded'] else 'RESTORED'} -- {result['reason']}")
    return result


def check_all_enabled_strategies():
    """Only strategies actually taking real paper trades are worth
    checking -- an archived/never-enabled strategy has no closed-trade
    window to evaluate anyway (evaluate_strategy() would just report
    "available": False for it every time)."""
    from paper_trading import config as pt_config
    initial_balance = pt_config.load().get("initial_balance", 10000.0)
    configs = storage.list_paper_strategy_configs()
    results = {}
    for strategy_id, cfg in configs.items():
        if not cfg.get("enabled"):
            continue
        results[strategy_id] = check_and_log_if_changed(strategy_id, initial_balance=initial_balance)
    return results


def _loop():
    default_log(f"[auto-downgrade] scheduler started -- checks every {CHECK_INTERVAL_SECONDS}s "
                f"whether any enabled strategy's last {MIN_TRADES_FOR_EVALUATION} live paper trades "
                f"cross the downgrade thresholds.")
    while not _stop_flag.is_set():
        try:
            check_all_enabled_strategies()
        except Exception as e:
            default_log(f"[auto-downgrade] check failed: {e!r}")
        _stop_flag.wait(CHECK_INTERVAL_SECONDS)


def start_scheduler_thread():
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop_flag.clear()
    _thread = threading.Thread(target=_loop, daemon=True)
    _thread.start()


def stop_scheduler_thread():
    _stop_flag.set()
