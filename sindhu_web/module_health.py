"""Grand Master Prompt, Phase 4.4: Module Health Score -- a 0-100 score
per module (Paper Trading, Telegram, Database, and, local-only, Evolution
+ Self-Learning), with a fully transparent formula: every point deduction
is named in `reasons`, nothing is a black box. Every input is read from a
function that already exists elsewhere (engine.status(), kill_switch.
status(), telegram_bot.public_settings(), etc.) -- this module computes no
new trade/strategy logic, it only scores already-computed state.

Phase 4.11 (Project Score) combines these into one overall number.
"""
from sindhu_web.security import CLOUD_MODE


def _clamp(score):
    return max(0, min(100, score))


def score_paper_trading():
    from paper_trading.engine import engine
    from paper_trading import kill_switch, account_drawdown_guard

    status = engine.status()
    score, reasons = 100, []
    if not status["running"]:
        score -= 50
        reasons.append("Engine is not running (-50)")
    if kill_switch.status()["active"]:
        score -= 30
        reasons.append("Kill switch is active (-30)")
    if account_drawdown_guard.status()["paused"]:
        score -= 20
        reasons.append("Account-wide drawdown circuit-breaker is active (-20)")
    return {"module": "paper_trading", "score": _clamp(score), "reasons": reasons or ["Running normally"]}


def score_telegram():
    from paper_trading import telegram_bot

    settings = telegram_bot.public_settings()
    score, reasons = 100, []
    if not settings.get("token_configured") or not settings.get("channel_id"):
        score -= 60
        reasons.append("Bot token or channel not configured yet (-60)")
    elif not settings.get("master_send_enabled"):
        score -= 30
        reasons.append("Sending is switched off (-30)")
    if settings.get("proxy_enabled") and not settings.get("proxy_configured"):
        score -= 10
        reasons.append("Proxy is enabled but not configured (-10)")
    return {"module": "telegram", "score": _clamp(score), "reasons": reasons or ["Configured and sending"]}


def score_database():
    from data_engine import storage
    from sindhu_web.api.system import _recent_errors

    score, reasons = 100, []
    try:
        storage.db_file_size_bytes()
    except Exception:
        score -= 100
        reasons.append("Database file is not reachable (-100)")
        return {"module": "database", "score": 0, "reasons": reasons}
    error_count = len(_recent_errors(limit=20))
    if error_count:
        deduction = min(40, error_count * 4)
        score -= deduction
        reasons.append(f"{error_count} recent error line(s) in the log (-{deduction})")
    return {"module": "database", "score": _clamp(score), "reasons": reasons or ["No recent errors, reachable"]}


def score_evolution():
    if CLOUD_MODE:
        return {"module": "evolution", "score": None, "reasons": ["Evolution Engine does not run on this cloud deployment"]}
    from evolution_engine.engine import engine as evo_engine
    from data_engine import storage

    status = evo_engine.status()
    score, reasons = 100, []
    if not status.get("running"):
        score -= 20
        reasons.append("Not currently running (-20, not necessarily unhealthy -- may simply be off)")
    comparisons = storage.list_evolution_comparisons(limit=20)
    if comparisons:
        rollback_rate = sum(1 for c in comparisons if c.get("rolled_back")) / len(comparisons)
        if rollback_rate > 0.5:
            score -= 30
            reasons.append(f"{rollback_rate:.0%} of the last {len(comparisons)} comparisons were rolled back (-30)")
    gov = status.get("governor") or {}
    if gov.get("cpu_percent", 0) > gov.get("cpu_limit_percent", 100):
        score -= 15
        reasons.append("Governor CPU limit currently exceeded (-15)")
    return {"module": "evolution", "score": _clamp(score), "reasons": reasons or ["Running normally, no excess rollbacks"]}


def score_self_learning():
    if CLOUD_MODE:
        return {"module": "self_learning", "score": None, "reasons": ["Self-Learning Engine does not run on this cloud deployment"]}
    from data_engine import storage
    from self_learning_engine import discovery_cycle

    score, reasons = 100, []
    latest = storage.get_latest_self_learning_cycle()
    if not latest:
        score -= 20
        reasons.append("No discovery cycle has ever run yet (-20, informational -- not necessarily unhealthy)")
    elif not discovery_cycle.should_run_new_cycle() and latest.get("status") == "failed":
        score -= 40
        reasons.append("Latest discovery cycle failed (-40)")
    return {"module": "self_learning", "score": _clamp(score), "reasons": reasons or ["Discovery cycles running normally"]}


def compute_all_module_scores():
    return {
        "paper_trading": score_paper_trading(),
        "telegram": score_telegram(),
        "database": score_database(),
        "evolution": score_evolution(),
        "self_learning": score_self_learning(),
    }
