"""Grand Master Prompt, Phase 4.4 (Module Health Score) and 4.11 (Project
Score): read-only endpoints over sindhu_web/module_health.py's scoring
functions. See that module's own docstring for the transparent-formula
guarantee -- nothing here invents a new score independently of it.
"""
from fastapi import APIRouter

from sindhu_web import module_health

router = APIRouter()


@router.get("/api/module-health")
def get_module_health():
    return {"modules": module_health.compute_all_module_scores()}


@router.get("/api/project-score")
def get_project_score():
    """Phase 4.11: one overall number across Reliability/Stability/
    Performance/Risk -- built ONLY from the already-transparent per-module
    scores above, weighted-averaged over whichever modules are actually
    applicable on this deployment (a module scored None, e.g. Evolution on
    cloud, is excluded rather than dragging the average down for a module
    that was never expected to run here)."""
    modules = module_health.compute_all_module_scores()
    applicable = [m for m in modules.values() if m["score"] is not None]
    overall = round(sum(m["score"] for m in applicable) / len(applicable), 1) if applicable else None
    # The four named categories are each mapped from the module scores
    # most relevant to that category -- documented here, not hidden:
    reliability = _avg(modules, ["database", "telegram"])
    stability = _avg(modules, ["paper_trading", "evolution"])
    performance = _avg(modules, ["paper_trading"])
    risk = _avg(modules, ["paper_trading", "evolution"])
    return {
        "overall": overall,
        "reliability": reliability,
        "stability": stability,
        "performance": performance,
        "risk": risk,
        "modules": modules,
        "formula_note": ("overall = plain average of every applicable module's score; "
                          "reliability = avg(database, telegram); stability = avg(paper_trading, evolution); "
                          "performance = paper_trading score; risk = avg(paper_trading, evolution). "
                          "A module not running on this deployment (score=None) is excluded, never counted as 0."),
    }


def _avg(modules, keys):
    values = [modules[k]["score"] for k in keys if modules.get(k) and modules[k]["score"] is not None]
    return round(sum(values) / len(values), 1) if values else None


@router.get("/api/decision-center")
def get_decision_center():
    """Phase 4.1: Biggest Problem / Recommended Action / Estimated Impact /
    Priority Level, computed fresh from real state every request -- never
    a static placeholder. Every problem listed here is sourced from an
    already-existing gate/status function (Risk Department's own summary,
    Module Health Score above); this endpoint only ranks and picks the
    single worst one to lead with, plus a count of everything else."""
    from sindhu_web.api.risk_department import get_risk_department_summary

    risk = get_risk_department_summary()
    problems = []
    if risk["kill_switch"]["active"]:
        problems.append({
            "problem": "Kill Switch is ACTIVE -- all trading is halted.",
            "action": "Review why it was triggered on the Risk page, then deactivate once resolved.",
            "impact": "Zero new trades executing across every strategy.",
            "priority": "critical",
        })
    if risk["account_drawdown"]["paused"]:
        problems.append({
            "problem": f"Account-wide drawdown circuit-breaker is active ({risk['account_drawdown']['drawdown_pct']}% drawdown from peak).",
            "action": "Review recent losing trades on the Risk page before resuming.",
            "impact": "Every strategy is paused from opening new trades.",
            "priority": "critical",
        })
    if risk["paused_strategies"]:
        problems.append({
            "problem": f"{len(risk['paused_strategies'])} strategy(ies) paused on consecutive losses.",
            "action": "Review their recent trades on the Strategy Lifecycle page.",
            "impact": f"{len(risk['paused_strategies'])} strategy(ies) not taking new trades right now.",
            "priority": "high",
        })
    if risk["incomplete_lock"]["locked_count"]:
        problems.append({
            "problem": f"{risk['incomplete_lock']['locked_count']} strategy(ies) are locked (incomplete extraction).",
            "action": "Resolve the missing rules on the Clarification page.",
            "impact": "These strategies cannot be tested or traded until resolved.",
            "priority": "medium",
        })
    modules = module_health.compute_all_module_scores()
    for name, m in modules.items():
        if m["score"] is not None and m["score"] < 60:
            problems.append({
                "problem": f"{name.replace('_', ' ').title()} module health is low ({m['score']}/100): {'; '.join(m['reasons'])}",
                "action": f"Check the {name.replace('_', ' ')} module directly.",
                "impact": "Degraded reliability in this area.",
                "priority": "medium",
            })

    if not problems:
        return {"biggest_problem": None, "recommended_action": None, "estimated_impact": None,
                "priority_level": None, "all_problems_count": 0,
                "message": "No significant problems detected right now."}

    order = {"critical": 0, "high": 1, "medium": 2}
    problems.sort(key=lambda p: order.get(p["priority"], 9))
    top = problems[0]
    return {
        "biggest_problem": top["problem"], "recommended_action": top["action"],
        "estimated_impact": top["impact"], "priority_level": top["priority"],
        "all_problems_count": len(problems),
    }
