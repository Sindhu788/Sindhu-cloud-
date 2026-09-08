"""Grand Master Prompt, Phase 4.10: Report Builder -- a real parameterized
report (date range + module selection), unlike every existing report
endpoint (sindhu_web/api/reports.py), which is fixed-shape (one backtest
batch, or a fixed best/worst ranking). Reuses the exact same aggregate
functions every other page already calls for each module -- no new
computation invented, just combined into one report on the caller's own
date range and module choice.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from data_engine import storage

router = APIRouter()

SUPPORTED_MODULES = ("paper_trading", "telegram", "evolution")


class ReportBuilderRequest(BaseModel):
    since: str  # YYYY-MM-DD
    until: str  # YYYY-MM-DD (exclusive)
    modules: list[str]


def _parse_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(400, f"'{s}' must be in YYYY-MM-DD format")


@router.post("/api/report-builder")
def build_report(req: ReportBuilderRequest):
    since_dt = _parse_date(req.since)
    until_dt = _parse_date(req.until)
    if until_dt <= since_dt:
        raise HTTPException(400, "until must be after since")
    unknown = set(req.modules) - set(SUPPORTED_MODULES)
    if unknown:
        raise HTTPException(400, f"Unsupported module(s): {sorted(unknown)} -- must be from {SUPPORTED_MODULES}")

    since_iso, until_iso = since_dt.isoformat(), until_dt.isoformat()
    report = {"since": req.since, "until": req.until, "generated_at": datetime.now(timezone.utc).isoformat()}

    if "paper_trading" in req.modules:
        summary = storage.get_paper_period_summary(since_iso, until_iso)
        strategy_stats = storage.list_paper_strategy_stats(since_iso, until_iso)
        report["paper_trading"] = {
            "closed_trades": summary["closed_trades"], "net_pnl": summary["total_pnl"],
            "win_rate": summary["win_rate"], "active_strategies": summary["active_strategies"],
            "top_5_strategies_by_pnl": strategy_stats[:5],
        }
    if "telegram" in req.modules:
        report["telegram"] = {"messages_sent_in_window": storage.count_telegram_messages_between(since_iso, until_iso)}
    if "evolution" in req.modules:
        comparisons = storage.list_evolution_comparisons_between(since_iso, until_iso)
        report["evolution"] = {
            "comparisons": len(comparisons),
            "rollbacks": sum(1 for c in comparisons if c.get("rolled_back")),
        }

    return report
