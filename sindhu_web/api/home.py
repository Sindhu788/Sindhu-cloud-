from datetime import datetime, timezone

import psutil
from fastapi import APIRouter

from data_engine import storage, config
from data_engine.paths import disk_usage_bytes
from backtest_engine.reports import quick_batch_summary
from backtest_engine import strategy_library
from paper_trading.engine import engine as paper_engine
from paper_trading import config as paper_config
from sindhu_web import cache
from sindhu_web.jobs import job_manager
from knowledge_engine.scoring import compute_knowledge_score
from knowledge_engine.engine import get_display_knowledge_report
from knowledge_engine.maturity import compute_maturity_level

router = APIRouter()

APP_VERSION = "5.1"
NAV_ICONS = {
    "home": "dashboard", "market": "market", "data": "database", "strategies": "layers",
    "knowledge": "book", "backtesting": "flask", "paper_trading": "wallet",
    "evolution": "dna", "reports": "chart",
    "settings": "gear", "knowledge_compiler": "compiler",
    "ai_center": "ai_center", "backtest_history": "history", "ceo": "ceo",
    "pipeline_history": "history", "sindhu_strategy": "spark",
    "web_sourced_strategies": "news", "control_center": "ceo",
    "telegram_dashboard": "send", "evolution_history": "history",
    "signal_tracker": "target", "strategy_lab": "flask",
    "clarification_center": "book", "external_signals": "send",
    "compare": "mirror", "live_logs": "spark", "project_status": "news",
    "strategy_lifecycle": "layers", "incidents": "flask", "self_learning": "spark",
    "challenge_mode": "target",
}

# Navigation Audit + Reorganization: every page now belongs to exactly one
# named group, rendered as labeled sections in the sidebar instead of one
# long flat list. Dead placeholder entries that were never built
# (Reflection, News, a separate disabled "Telegram" entry -- real
# Telegram settings live inside Settings) have been removed outright
# rather than just left disabled.
NAV_GROUPS = ["Overview", "Project", "Strategies", "Backtesting", "Paper Trading", "Intelligence", "Strategy Lab",
              "External Signals", "Control", "Reports"]

NAV_PAGES = [
    # Overview
    {"id": "ceo", "label": "SINDHU CEO", "enabled": True, "icon": NAV_ICONS["ceo"], "group": "Overview"},
    {"id": "home", "label": "Dashboard", "enabled": True, "icon": NAV_ICONS["home"], "group": "Overview"},

    # Project: 3 consolidated views replacing the earlier scattered
    # standalone pages (Strategy Optimizer, Project Overview) -- Compare
    # (all 14 strategies side by side), Live Logs (running/queued/recent
    # jobs), Project Status (what-changed log, summary, pending, feedback).
    {"id": "compare", "label": "Compare", "enabled": True, "icon": NAV_ICONS["compare"], "group": "Project"},
    {"id": "live_logs", "label": "Live Logs", "enabled": True, "icon": NAV_ICONS["live_logs"], "group": "Project"},
    {"id": "project_status", "label": "Project Status", "enabled": True,
     "icon": NAV_ICONS["project_status"], "group": "Project"},
    # Strategy Lifecycle: one consolidated table -- every active strategy's
    # backtest result, real computed why-win/why-loss summary (Part 1), and
    # confirmation-strictness optimizer result (Part 2) in one place, with a
    # gated "Move to paper trading" action per row. See
    # sindhu_web/api/strategy_lifecycle.py.
    {"id": "strategy_lifecycle", "label": "Strategy Lifecycle", "enabled": True,
     "icon": NAV_ICONS["strategy_lifecycle"], "group": "Project"},
    # Incident Management (Grand Feature Expansion, Phase 1 Feature 4): a
    # structured problem -> detection -> root cause -> fix -> test ->
    # resolution record. See sindhu_web/api/incidents.py.
    {"id": "incidents", "label": "Incidents", "enabled": True,
     "icon": NAV_ICONS["incidents"], "group": "Project"},
    # Concepts Library is still a standalone static page (concepts.html),
    # not ported into the SPA's hash-routed PAGES{} -- external_url makes
    # app.js's renderNav() link straight to it instead of a `#hash`, so it's
    # reachable by one click without touching the page's own content/logic.
    {"id": "concepts", "label": "Concepts", "enabled": True, "icon": NAV_ICONS["knowledge"],
     "group": "Project", "external_url": "/static/concepts.html"},

    # Strategies: everything about building, importing, and understanding a strategy
    {"id": "strategies", "label": "Strategies", "enabled": True, "icon": NAV_ICONS["strategies"], "group": "Strategies"},
    {"id": "sindhu_strategy", "label": "SINDHU Strategy", "enabled": True, "icon": NAV_ICONS["sindhu_strategy"], "group": "Strategies"},
    {"id": "web_sourced_strategies", "label": "Web-Sourced Strategies", "enabled": True,
     "icon": NAV_ICONS["web_sourced_strategies"], "group": "Strategies"},
    {"id": "knowledge", "label": "Knowledge", "enabled": True, "icon": NAV_ICONS["knowledge"], "group": "Strategies"},
    {"id": "knowledge_compiler", "label": "Knowledge Compiler", "enabled": True,
     "icon": NAV_ICONS["knowledge_compiler"], "group": "Strategies"},
    {"id": "ai_center", "label": "AI Center", "enabled": True, "icon": NAV_ICONS["ai_center"], "group": "Strategies"},
    # Clarification Page (Step 3, Part B): the dedicated place to resolve
    # every strategy's unclear/unmapped items -- replaces the earlier
    # inline modal-only flow (openClarifyBox) with a full page (progress
    # counter, grouped-by-strategy list, Read Mode summary, etc.).
    {"id": "clarification_center", "label": "Clarification", "enabled": True,
     "icon": NAV_ICONS["clarification_center"], "group": "Strategies"},

    # Backtesting: running backtests and reviewing their raw results
    {"id": "backtesting", "label": "Backtesting", "enabled": True, "icon": NAV_ICONS["backtesting"], "group": "Backtesting"},
    {"id": "backtest_history", "label": "Backtest History", "enabled": True,
     "icon": NAV_ICONS["backtest_history"], "group": "Backtesting"},
    {"id": "pipeline_history", "label": "Pipeline History", "enabled": True,
     "icon": NAV_ICONS["pipeline_history"], "group": "Backtesting"},

    # Paper Trading: everything about the live (fake-money) trading loop --
    # Telegram Signals lives here too (Batch 6, Task 2): paper trading is
    # what generates the signals Telegram sends, so the two belong together
    # rather than Telegram Signals sitting under Control. Nav grouping only
    # -- id/route/API untouched, so every existing link/bookmark still works.
    {"id": "paper_trading", "label": "Paper Trading", "enabled": True, "icon": NAV_ICONS["paper_trading"], "group": "Paper Trading"},
    {"id": "telegram_dashboard", "label": "Telegram Signals", "enabled": True,
     "icon": NAV_ICONS["telegram_dashboard"], "group": "Paper Trading"},
    {"id": "signal_tracker", "label": "Signal Tracker", "enabled": True,
     "icon": NAV_ICONS["signal_tracker"], "group": "Paper Trading"},
    {"id": "market", "label": "Market", "enabled": True, "icon": NAV_ICONS["market"], "group": "Paper Trading"},
    {"id": "data", "label": "Data", "enabled": True, "icon": NAV_ICONS["data"], "group": "Paper Trading"},

    # Master Task 3, Phase 2.1: Challenge Mode gets its own standalone nav
    # page (the original single-challenge widget stays embedded inside
    # Paper Trading too, untouched, for backward compatibility) -- this new
    # page is the one that supports 2-3 simultaneous challenges side by
    # side plus the rest of Phase 2's analysis features.
    {"id": "challenge_mode", "label": "Challenge Mode", "enabled": True,
     "icon": NAV_ICONS["challenge_mode"], "group": "Paper Trading"},

    # Intelligence: self-learning / evolutionary systems
    {"id": "evolution", "label": "Evolution", "enabled": True, "icon": NAV_ICONS["evolution"], "group": "Intelligence"},
    {"id": "evolution_history", "label": "Evolution History", "enabled": True,
     "icon": NAV_ICONS["evolution_history"], "group": "Intelligence"},

    # Master Task 3, Phase 1: Self-Learning Engine -- deliberately its own
    # nav entry, NOT folded into Evolution above: Evolution only tweaks
    # existing strategies, this discovers brand-new candidate strategies
    # by combining concepts. Kept in the same "Intelligence" group since
    # both are automated strategy-improvement systems the CEO checks on
    # together, just genuinely separate mechanisms underneath.
    {"id": "self_learning", "label": "Self-Learning Engine", "enabled": True,
     "icon": NAV_ICONS["self_learning"], "group": "Intelligence"},

    # Strategy Lab: a weekly, honest check for a genuinely profitable
    # strategy -- real, after-cost results only, never a losing strategy
    # dressed up as "best." Its own top-level section since it's a
    # standing verdict the CEO should be able to find at a glance, not
    # buried inside another page.
    {"id": "strategy_lab", "label": "Strategy Lab", "enabled": True,
     "icon": NAV_ICONS["strategy_lab"], "group": "Strategy Lab"},

    # External Signal Tracker: a COMPLETELY SEPARATE module from the
    # CEO's own Paper Trading above -- external Telegram channels the CEO
    # merely follows, paper-traded and scored in total isolation, never
    # mixed with the CEO's own strategy results. Deliberately its own
    # top-level nav group (not folded into "Paper Trading") so this
    # separation is visible in the nav itself, not just in the data.
    {"id": "external_signals", "label": "External Signal Tracker", "enabled": True,
     "icon": NAV_ICONS["external_signals"], "group": "External Signals"},

    # Control: the one place to turn automated features on/off, plus account/app settings
    {"id": "control_center", "label": "Control Center", "enabled": True,
     "icon": NAV_ICONS["control_center"], "group": "Control"},
    {"id": "settings", "label": "Settings", "enabled": True, "icon": NAV_ICONS["settings"], "group": "Control"},

    # Reports: cross-strategy summaries, not raw per-batch results (see Backtesting)
    {"id": "reports", "label": "Reports", "enabled": True, "icon": NAV_ICONS["reports"], "group": "Reports"},
]


@router.get("/api/nav")
def get_nav():
    return {"pages": [p for p in NAV_PAGES if p["enabled"]], "groups": NAV_GROUPS}


@router.get("/api/strategy-summary")
def get_strategy_summary():
    """Read-only, cross-strategy aggregate summary for the Home dashboard --
    same underlying data as the Strategy Comparison Board (each strategy's
    latest completed batch), just aggregated. Cached briefly since the Home
    page can poll this like every other topbar-driven card."""
    return cache.cached("strategy_aggregate_summary", 30, _compute_strategy_summary)


def _compute_strategy_summary():
    """Full Strategy Count Audit task, Part 2: the real computation now
    lives in sindhu_web/strategy_aggregate.py (extracted so strategy_
    lifecycle.py, mounted on cloud_runtime/app.py, doesn't have to import
    this whole module -- see that module's own docstring for why). Kept
    as a thin wrapper here so this file's existing name/behavior/cache key
    stay unchanged for every current caller."""
    from sindhu_web.strategy_aggregate import compute_strategy_summary
    return compute_strategy_summary()


@router.get("/api/home")
def get_home():
    exchanges = cache.cached("exchanges", 60, storage.load_all_exchanges)
    total_candles = cache.cached("total_candles", 60, storage.count_all_rows)
    coin_count = cache.cached(
        "coin_count", 60,
        lambda: len(storage.load_symbols(exchanges[0])) if exchanges else 0,
    )

    jobs = job_manager.list_jobs()
    running_jobs = [j.to_dict() for j in jobs if j.status == "running"]

    task_summary = {
        "running": sum(1 for j in jobs if j.status == "running"),
        "waiting": 0,
        "completed": sum(1 for j in jobs if j.status in ("completed", "stopped")),
        "failed": sum(1 for j in jobs if j.status == "error"),
    }
    module_status = {
        "Data Engine": "Running" if any(j.kind == "download" and j.status == "running" for j in jobs) else "Idle",
        "Backtesting Engine": "Running" if any(j.kind == "backtest" and j.status == "running" for j in jobs) else "Idle",
        "Knowledge Engine": "Running",
        "Paper Trading Engine": "Running" if paper_engine.is_running() else "Idle",
        "Dashboard": "Running",
    }

    exchanges_cfg = config.load_or_seed("exchanges.json", config.DEFAULTS["exchanges.json"])
    account = cache.cached("home_account_snapshot", 15, _account_snapshot)

    return {
        "project_status": "Knowledge Compiler (Strategy + Lesson Engine upgrade)",
        "version": APP_VERSION,
        "system_health": "OK",
        "database_status": "Connected",
        "database_size_bytes": storage.db_file_size_bytes(),
        "total_coins": coin_count,
        "available_timeframes": config.SUPPORTED_INTERVALS,
        "total_candles": total_candles,
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "ram_percent": psutil.virtual_memory().percent,
        "current_task": running_jobs[0] if running_jobs else None,
        "running_jobs": running_jobs,
        "knowledge_score": compute_knowledge_score(
            cache.cached("knowledge_report", 60, get_display_knowledge_report)
        ),
        "task_summary": task_summary,
        "module_status": module_status,
        # Cached: disk_usage_bytes() walks the whole data tree (an 8.9GB
        # database plus candle/report files) and measured 5.0 SECONDS
        # uncached. /api/home is polled by every page's topbar, so paying
        # that on every single poll made the entire app feel frozen. Disk
        # usage changes slowly -- a 5-minute-old number is fine here.
        "disk_usage_bytes": cache.cached_nonblocking("disk_usage_bytes", 300, disk_usage_bytes, 0),
        "exchange": exchanges_cfg["default"],
        "latest_batch": account,
        "evolution_score": None,
        # Batch 4, Task 5: real, honest Level 1-5 maturity indicator --
        # cached briefly since /api/home is polled by every page's topbar
        # and this recomputes several real queries, not because the
        # numbers themselves change fast.
        "maturity": cache.cached("system_maturity", 30, compute_maturity_level),
    }


def _account_snapshot():
    """Balance/PnL/Win Rate/Total Trades for the Home page's Overview
    cards -- combined across every strategy's independent Paper Trading
    book (each strategy starts from the same configured initial_balance
    and accrues its own realized pnl; see paper_trading.guards.book_key).
    Prefers the live Paper Trading account once it has any trade history;
    falls back to the most recent completed Backtest so the cards aren't
    empty before Paper Trading has run its first trade.

    Reads storage.list_paper_account_states() (O(1) running totals kept in
    sync by close_paper_position()) instead of materializing every closed
    position via list_closed_paper_positions(limit=100000) just to count
    wins/trades -- this endpoint is polled by every page's topbar, so it
    needs to stay cheap as paper trade history grows."""
    states = storage.list_paper_account_states()
    closed_count = sum(s["closed_count"] for s in states)
    if closed_count:
        settings = paper_config.load()
        initial_balance = settings.get("initial_balance", 10000.0)
        total_pnl = sum(s["realized_pnl_total"] for s in states)
        win_count = sum(s["win_count"] for s in states)
        combined_initial = initial_balance * len(states)
        balance = combined_initial + total_pnl
        win_rate = win_count / closed_count * 100
        profit_pct = (balance - combined_initial) / combined_initial * 100 if combined_initial else 0.0
        return {
            "strategy": "Paper Trading (live account)", "final_balance": round(balance, 2),
            "profit_pct": round(profit_pct, 2), "win_rate": round(win_rate, 2),
            "total_trades": closed_count, "max_drawdown_pct": None,
        }
    return _latest_batch_snapshot()


def _latest_batch_snapshot():
    # Uses quick_batch_summary() (not generate_report()) -- the Home page
    # only ever shows these 6 fields, not the full coin/timeframe ranking
    # or session analysis, so there's no need to re-scan every trade in the
    # batch every 15 seconds. generate_report() over a 150k-trade batch
    # took 20-45s and made /api/home (polled by every page's topbar) stall
    # the whole app.
    for batch in storage.list_recent_batches(limit=10):
        if batch["status"] != "completed":
            continue
        try:
            r = quick_batch_summary(batch["batch_id"])
        except Exception:
            continue
        if not r:
            continue
        return {
            "strategy": r["strategy"], "final_balance": r["avg_final_balance"],
            "profit_pct": r["avg_profit_pct"], "win_rate": r["win_rate"],
            "total_trades": r["total_trades"], "max_drawdown_pct": r["max_drawdown_pct"],
        }
    return None
