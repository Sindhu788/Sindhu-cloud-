import psutil
from fastapi import APIRouter

from data_engine import storage, config
from data_engine.paths import disk_usage_bytes
from backtest_engine.reports import quick_batch_summary
from paper_trading.engine import engine as paper_engine
from paper_trading import config as paper_config
from sindhu_web import cache
from sindhu_web.jobs import job_manager
from knowledge_engine.scoring import compute_knowledge_score

router = APIRouter()

APP_VERSION = "5.1"
NAV_ICONS = {
    "home": "dashboard", "market": "market", "data": "database", "strategies": "layers",
    "knowledge": "book", "backtesting": "flask", "paper_trading": "wallet",
    "reflection": "mirror", "evolution": "dna", "reports": "chart", "news": "news",
    "telegram": "send", "settings": "gear", "knowledge_compiler": "compiler",
    "ai_center": "ai_center", "backtest_history": "history", "ceo": "ceo",
    "pipeline_history": "history",
}
NAV_PAGES = [
    {"id": "ceo", "label": "SINDHU CEO", "enabled": True, "icon": NAV_ICONS["ceo"]},
    {"id": "home", "label": "Dashboard", "enabled": True, "icon": NAV_ICONS["home"]},
    {"id": "market", "label": "Market", "enabled": True, "icon": NAV_ICONS["market"]},
    {"id": "data", "label": "Data", "enabled": True, "icon": NAV_ICONS["data"]},
    {"id": "strategies", "label": "Strategies", "enabled": True, "icon": NAV_ICONS["strategies"]},
    {"id": "knowledge", "label": "Knowledge", "enabled": True, "icon": NAV_ICONS["knowledge"]},
    {"id": "knowledge_compiler", "label": "Knowledge Compiler", "enabled": True, "icon": NAV_ICONS["knowledge_compiler"]},
    {"id": "ai_center", "label": "AI Center", "enabled": True, "icon": NAV_ICONS["ai_center"]},
    {"id": "backtesting", "label": "Backtesting", "enabled": True, "icon": NAV_ICONS["backtesting"]},
    {"id": "backtest_history", "label": "Backtest History", "enabled": True, "icon": NAV_ICONS["backtest_history"]},
    {"id": "pipeline_history", "label": "Pipeline History", "enabled": True, "icon": NAV_ICONS["pipeline_history"]},
    {"id": "paper_trading", "label": "Paper Trading", "enabled": True, "icon": NAV_ICONS["paper_trading"]},
    {"id": "reflection", "label": "Reflection", "enabled": False, "icon": NAV_ICONS["reflection"]},
    {"id": "evolution", "label": "Evolution", "enabled": False, "icon": NAV_ICONS["evolution"]},
    {"id": "reports", "label": "Reports", "enabled": True, "icon": NAV_ICONS["reports"]},
    {"id": "news", "label": "News", "enabled": False, "icon": NAV_ICONS["news"]},
    {"id": "telegram", "label": "Telegram", "enabled": False, "icon": NAV_ICONS["telegram"]},
    {"id": "settings", "label": "Settings", "enabled": True, "icon": NAV_ICONS["settings"]},
]


@router.get("/api/nav")
def get_nav():
    return {"pages": [p for p in NAV_PAGES if p["enabled"]]}


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
            cache.cached("knowledge_report", 60, storage.get_knowledge_report)
        ),
        "task_summary": task_summary,
        "module_status": module_status,
        # Cached: disk_usage_bytes() walks the whole data tree (an 8.9GB
        # database plus candle/report files) and measured 5.0 SECONDS
        # uncached. /api/home is polled by every page's topbar, so paying
        # that on every single poll made the entire app feel frozen. Disk
        # usage changes slowly -- a 5-minute-old number is fine here.
        "disk_usage_bytes": cache.cached("disk_usage_bytes", 300, disk_usage_bytes),
        "exchange": exchanges_cfg["default"],
        "latest_batch": account,
        "evolution_score": None,
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
