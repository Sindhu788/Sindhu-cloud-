"""Grand Master Prompt, Phase 4.16 (Module Dependency Map), 4.17
(Readiness Meter), 4.18 (Focus Mode support), and 4.20 (Project Timeline
addition). Small, mostly-static/documentation-shaped endpoints -- module
dependencies and feature readiness are structural facts about this
codebase, not something meaningfully "computed" at runtime.
"""
from fastapi import APIRouter

router = APIRouter()

# Phase 4.16: hand-documented from the actual import graph (backtest_engine
# imported by paper_trading, evolution_engine imported by paper_trading's
# lesson_generator, etc.) -- kept here as ONE place to update if a real
# dependency changes, rather than scattered comments. "impact_if_down" is
# deliberately plain-language, not a formal SLA.
MODULE_DEPENDENCY_MAP = [
    {"module": "Data Engine", "depends_on": [], "impact_if_down": "Nothing else can fetch market data -- Backtesting and Paper Trading both stop."},
    {"module": "Backtest Engine", "depends_on": ["Data Engine"], "impact_if_down": "No new backtests can run; Paper Trading keeps running (it reuses this engine's trade mechanics, but doesn't need it live)."},
    {"module": "Strategy Library", "depends_on": [], "impact_if_down": "No strategy can be loaded, created, or edited -- Backtesting/Paper Trading/Evolution all stall."},
    {"module": "Paper Trading Engine", "depends_on": ["Data Engine", "Strategy Library", "Backtest Engine (trade mechanics)"], "impact_if_down": "No live simulated trading, no new signals, no Telegram sends."},
    {"module": "Telegram", "depends_on": ["Paper Trading Engine"], "impact_if_down": "No signal delivery to the CEO's phone -- trading itself is unaffected."},
    {"module": "Evolution Engine", "depends_on": ["Strategy Library", "Backtest Engine"], "impact_if_down": "No new strategy variants generated -- existing strategies keep trading unaffected. Local-only, never runs on cloud."},
    {"module": "Self-Learning Engine", "depends_on": ["Strategy Library", "Backtest Engine", "Paper Trading Engine (trade history)"], "impact_if_down": "No new candidate strategies discovered -- everything else unaffected. Local-only."},
    {"module": "Database (SQLite/Postgres)", "depends_on": [], "impact_if_down": "Total outage -- every module above depends on it directly or indirectly."},
]

# Phase 4.17: a documented, honest heuristic -- NOT derived from deep
# telemetry (this codebase doesn't track per-feature production incident
# history). Risk & Safety features are the longest-standing, most
# battle-tested category (Kill Switch, Drawdown Guard, etc. -- present
# since early sessions); Signals/Other are the main day-to-day surface,
# labeled Production; Self-Learning is the newest, most actively-changing
# category, labeled Testing. This mapping is by CATEGORY, not per
# individual feature -- a finer-grained score isn't honestly supportable
# with data this codebase actually has.
FEATURE_READINESS_BY_CATEGORY = {
    "Risk & Safety": "Stable",
    "Signals": "Production",
    "Other": "Production",
    "Self-Learning": "Testing",
}


@router.get("/api/project-meta/dependency-map")
def get_dependency_map():
    return {"modules": MODULE_DEPENDENCY_MAP}


@router.get("/api/project-meta/readiness")
def get_readiness_meter():
    from sindhu_web.api.feature_control import _feature_defs
    rows = [{"id": f["id"], "name": f["name"], "category": f["category"],
             "readiness": FEATURE_READINESS_BY_CATEGORY.get(f["category"], "Production")}
            for f in _feature_defs()]
    return {"features": rows, "categories": FEATURE_READINESS_BY_CATEGORY}
