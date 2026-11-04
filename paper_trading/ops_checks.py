"""Operational self-checks shown to the owner: user-facing warnings and a Local-vs-Cloud settings parity check.

Nothing here changes a setting, a gate or a trade. Secrets are never included (tokens / ids are reported as booleans).
"""
import os
import time

# Keys whose values must match between Local and Cloud for the system to behave the same.
PAPER_KEYS = (
    "max_open_trades", "max_portfolio_risk_pct_per_coin", "cooldown_minutes", "priority_rule",
    "opposite_signal_policy", "coin_filter_top_n", "tick_interval_seconds", "lookback_days",
    "drawdown_pause_streak_threshold", "drawdown_pause_pct_threshold", "account_drawdown_pause_pct_threshold",
    "cooling_off_loss_streak", "cooling_off_hours", "ensemble_voting_min_agreeing_strategies",
    "initial_balance", "dry_run", "risk_pct_default", "commission_pct",
)
TELEGRAM_KEYS = (
    "master_send_enabled", "auto_send_enabled", "auto_send_high_confidence_only", "channel_group_filter",
    "auto_send_min_confluence_ratio", "auto_send_min_confluence_count", "signal_freshness_minutes",
    "signal_price_drift_pct", "rate_limit_per_hour", "silent_hours_enabled", "min_confidence_pct_to_send",
)
# Differences that are intentional by design (Cloud publishes; Local never sends public signals).
EXPECTED_DIFFERENT = {
    "telegram.master_send_enabled", "telegram.auto_send_enabled", "telegram.bot_token_set",
    "telegram.channel_id_set", "paper.engine_enabled",
}


def settings_snapshot():
    """Secret-free view of the settings that matter for signals."""
    from paper_trading import config as pt_config, telegram_bot
    paper = pt_config.load()
    tg = telegram_bot.load_settings()
    snap = {"paper": {k: paper.get(k) for k in PAPER_KEYS}, "telegram": {k: tg.get(k) for k in TELEGRAM_KEYS}}
    snap["paper"]["engine_enabled"] = bool(paper.get("engine_enabled"))
    snap["telegram"]["bot_token_set"] = bool(tg.get("bot_token"))
    snap["telegram"]["channel_id_set"] = bool(tg.get("channel_id"))
    return snap


def diff_snapshots(local, cloud):
    """Returns {"differences": [{key, local, cloud, expected}], "unexpected": n}."""
    rows = []
    for section in ("paper", "telegram"):
        a, b = local.get(section, {}), cloud.get(section, {})
        for key in sorted(set(a) | set(b)):
            if a.get(key) != b.get(key):
                full = f"{section}.{key}"
                rows.append({"key": full, "local": a.get(key), "cloud": b.get(key), "expected": full in EXPECTED_DIFFERENT})
    return {"differences": rows, "unexpected": sum(1 for r in rows if not r["expected"])}


def collect_warnings(now=None):
    """Plain-language list of things the owner should know. Each: {level, code, message}."""
    from data_engine import db_backend
    from paper_trading.engine import engine as _engine
    from paper_trading import kill_switch, market_data_guard, signal_ownership, telegram_bot, config as pt_config
    now = time.time() if now is None else now
    cloud = str(os.environ.get("SINDHU_CLOUD_MODE", "")).strip().lower() in ("1", "true", "yes", "on")
    out = []
    try:
        if kill_switch.is_active():
            out.append({"level": "critical", "code": "kill_switch", "message": "Kill switch is ACTIVE: all trading is halted."})
        st = {"last_tick_at": getattr(_engine, "_last_tick_at", None)}
        running = bool(getattr(_engine, "_running", False))
        enabled = bool(pt_config.load().get("engine_enabled"))
        if cloud and not running:
            out.append({"level": "critical", "code": "engine_off", "message": "Cloud paper trading is OFF - no signals can be produced."})
        elif running and st.get("last_tick_at"):
            from datetime import datetime
            try:
                last = datetime.fromisoformat(str(st["last_tick_at"]).replace("Z", "+00:00")).timestamp()
                if now - last > 300:
                    out.append({"level": "warning", "code": "stale_scan", "message": f"Last market scan was {int((now - last) // 60)} min ago (expected every ~30 s). Data may be stale."})
            except Exception:
                pass
        if running is False and enabled and not cloud:
            out.append({"level": "info", "code": "local_engine_off", "message": "Local paper engine is off (normal: Cloud publishes signals)."})
    except Exception:
        pass
    if cloud:
        for blocker in signal_ownership.delivery_blockers(telegram_bot.load_settings()):
            out.append({"level": "critical", "code": "delivery_blocked", "message": "Signals will NOT be sent: " + blocker})
    if cloud:
        try:
            if not telegram_bot.load_settings().get("personal_chat_id"):
                out.append({"level": "warning", "code": "no_owner_chat", "message": "Owner alerts are OFF: set your private chat id in Settings > Telegram (personal_chat_id) to receive watchdog alerts and the daily health summary."})
        except Exception:
            pass
    if cloud:
        try:
            from paper_trading import instance_state
            ps = instance_state.ping_summary(now)
            if not ps["pinger_active"] and ps["process_age_seconds"] > 900:
                seen = ps["seconds_since_last_external_ping"]
                out.append({"level": "warning", "code": "no_pinger",
                            "message": "No external pinger seen on /health" + ("" if seen is None else f" (last ping {int(seen // 60)} min ago)")
                                       + ": the free Render instance will sleep when idle and scans stop. See docs/PINGER_SETUP.md."})
        except Exception:
            pass
    summary = market_data_guard.rejection_summary()
    if summary["rejected_in_window"]:
        out.append({"level": "warning", "code": "market_data_rejected",
                    "message": f"{summary['rejected_in_window']} candle frames were skipped in the last hour (stale/invalid data): "
                               + "; ".join(f"{k} x{v}" for k, v in list(summary['by_reason'].items())[:2])})
    try:
        from data_engine import db_size_guard
        usage = db_size_guard.database_usage()
        if usage.get("pct") is not None and usage["pct"] >= 80:
            out.append({"level": "warning", "code": "db_size", "message": f"Database is {usage['pct']}% full."})
    except Exception:
        pass
    return out
