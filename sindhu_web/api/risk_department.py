"""Risk Department (Grand Master Prompt, Phase 1.6): one consolidated,
read-only view of every safety gate/limit's CURRENT live state. This page
does not implement any new risk logic -- it only calls the exact same
functions each gate already exposes elsewhere (Kill Switch, Account
Drawdown Guard, per-strategy Drawdown pauses, Coin Blacklist, the Wilson
Score reliability gate, the per-strategy 5-coin position cap, the
Incomplete Lock, Signal Freshness, and -- local-only, since the Evolution
Engine never runs in cloud_runtime -- the Evolution/Rollback gate and the
Governor's CPU/RAM/queue limits).

Nothing here can weaken or bypass a gate; every field is a read.
"""
from datetime import datetime, timezone

from fastapi import APIRouter

from ai_integration import extraction_lock
from backtest_engine import strategy_library
from data_engine import storage
from paper_trading import account_drawdown_guard, coin_blacklist, config as pt_config
from paper_trading import kill_switch, pattern_stats, telegram_bot
from sindhu_web.security import CLOUD_MODE

router = APIRouter()


def _wilson_gate_summary():
    from paper_trading import insights
    patterns = storage.list_paper_coin_pattern_memory(None, since=insights.fresh_session_start())
    crossed = 0
    for p in patterns:
        result = pattern_stats.classify(p["wins"], p["trades"])
        if result.get("sample_size", 0) >= pattern_stats.MIN_SAMPLE_SIZE:
            crossed += 1
    return {
        "min_sample_size": pattern_stats.MIN_SAMPLE_SIZE,
        "total_patterns_tracked": len(patterns),
        "patterns_crossed_threshold": crossed,
    }


def _position_cap_usage():
    configs = storage.list_paper_strategy_configs()
    settings = pt_config.load()
    default_max = settings.get("max_open_trades", 5)
    rows = []
    for sid, cfg in configs.items():
        if not cfg.get("enabled"):
            continue
        max_coins = cfg.get("max_open_trades_override") or default_max
        open_symbols = storage.get_open_paper_position_symbols(sid)
        rows.append({
            "strategy_id": sid,
            "open_coins": len(open_symbols),
            "max_coins": max_coins,
            "at_cap": len(open_symbols) >= max_coins,
        })
    rows.sort(key=lambda r: -r["open_coins"])
    return rows


def _incomplete_lock_summary():
    active_ids = [s["id"] for s in strategy_library.list_all() if not s.get("archived")]
    locks = extraction_lock.check_strategy_locks_bulk(active_ids)
    locked = [sid for sid, l in locks.items() if l["locked"]]
    return {"total_active_strategies": len(active_ids), "locked_count": len(locked), "locked_strategy_ids": locked}


def _evolution_gate_summary():
    """Local-only: the Evolution Engine (and its Governor) never runs in
    cloud_runtime -- see cloud_runtime/app.py's own import-graph tests.
    Rollback/comparison history is still read here from storage directly
    (no evolution_engine import needed), since that's just DB rows and is
    honest to show wherever the process happens to be reading its DB."""
    comparisons = storage.list_evolution_comparisons(limit=50)
    rolled_back = sum(1 for c in comparisons if c.get("rolled_back"))
    result = {
        "trade_threshold_for_judgement": 100,
        "recent_comparisons_checked": len(comparisons),
        "recent_rollbacks": rolled_back,
        "governor": None,
    }
    if not CLOUD_MODE:
        from evolution_engine.engine import engine as evo_engine
        status = evo_engine.status()
        result["governor"] = status.get("governor")
        result["running"] = status.get("running")
    return result


def get_risk_department_summary():
    tg_settings = telegram_bot.load_settings()
    return {
        "kill_switch": kill_switch.status(),
        "account_drawdown": account_drawdown_guard.status(),
        "paused_strategies": storage.list_paused_strategies(),
        "coin_blacklist": coin_blacklist.list_all(),
        "confluence_threshold": {
            "auto_send_min_confluence_ratio": tg_settings.get("auto_send_min_confluence_ratio"),
            "auto_send_min_confluence_count": tg_settings.get("auto_send_min_confluence_count"),
        },
        "signal_freshness_minutes": tg_settings.get("signal_freshness_minutes"),
        "wilson_gate": _wilson_gate_summary(),
        "position_cap_usage": _position_cap_usage(),
        "incomplete_lock": _incomplete_lock_summary(),
        "evolution_gate": _evolution_gate_summary(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/risk-department")
def risk_department_endpoint():
    return get_risk_department_summary()
