"""Knowledge Quality Score -- a purely derived metric computed from an
already-compiled document (CompiledDocument.to_dict()). Never stored
separately from the document it describes: completeness/confidence/
automation-ready/backtesting-ready/score can always be recomputed on
demand from classification_confidence, status, and the strategies/lessons
already saved, so there's nothing here that could drift out of sync with
the real data.

v6 (AI Knowledge Learning Engine) adds hidden_rule_count/
avg_hidden_rule_confidence, purely reporting what the Deep Understanding
pass already attached to the document (doc["hidden_rules"]) -- never a new
persisted metric, and confidence_pct is unaffected by it (a document with
zero hidden rules because none were needed is not penalized).

v8: for an AI-assisted document, automation_ready no longer requires
doc["unresolved"] to be empty -- those notes are the AI's own transparency
trail (missing_rules/inferred-field audit), not a blocking condition. The
CEO's spec requires Automation/Backtesting Ready to read TRUE whenever the
AI's own confidence already cleared knowledge_compiler.compiler.
AI_CONFIDENCE_ACCEPT_THRESHOLD (status is already READY_FOR_BACKTEST by
that point). The old rule-based path (ai_assisted=False) is unchanged --
it still gates on genuinely unresolved items, since that path's "unresolved"
list is a real blocking validator finding, not an FYI note."""


def _strategy_completeness(strategy_result):
    cfg = strategy_result["config"]
    checks = [
        bool(cfg["entry_conditions"]),
        bool(cfg["exit_conditions"]) or cfg["stop_loss"]["type"] != "unknown",
        cfg["stop_loss"]["type"] != "unknown",
        cfg["take_profit"]["type"] != "unknown",
        cfg["risk_pct"] is not None,
        bool(cfg["timeframes"].get("entry")),
    ]
    return sum(1 for c in checks if c) / len(checks) * 100


def compute_knowledge_score(doc):
    """doc: the dict from CompiledDocument.to_dict() (or storage.get_compiled_document()).
    Returns {"completeness_pct", "confidence_pct", "automation_ready",
    "backtesting_ready", "knowledge_score"}."""
    strategies = doc.get("strategies") or []
    lessons = doc.get("lessons") or []

    if strategies:
        completeness_pct = sum(_strategy_completeness(s) for s in strategies) / len(strategies)
        resolved_defaults_count = sum(len(s.get("resolved_defaults") or []) for s in strategies)
        backtesting_ready = any(s.get("status") == "READY_FOR_BACKTEST" for s in strategies)
    elif lessons:
        completeness_pct = 100.0  # a pure lesson/prose document has no strategy fields to be missing
        resolved_defaults_count = 0
        backtesting_ready = False  # nothing executable to backtest
    else:
        completeness_pct = 0.0
        resolved_defaults_count = 0
        backtesting_ready = False

    classification_confidence_pct = (doc.get("classification_confidence") or 0) * 100
    confidence_pct = max(0.0, min(100.0, classification_confidence_pct - 5 * resolved_defaults_count))

    draft_lessons = sum(1 for l in lessons if l.get("lesson", {}).get("status") == "draft")
    if doc.get("ai_assisted"):
        automation_ready = backtesting_ready and draft_lessons == 0
    else:
        automation_ready = backtesting_ready and draft_lessons == 0 and not doc.get("unresolved")

    knowledge_score = round((completeness_pct + confidence_pct) / 2, 1)

    hidden_rules = doc.get("hidden_rules") or []
    hidden_rule_count = len(hidden_rules)
    avg_hidden_rule_confidence = (
        round(sum(r.get("confidence", 0) for r in hidden_rules) / hidden_rule_count * 100, 1)
        if hidden_rule_count else None
    )

    return {
        "completeness_pct": round(completeness_pct, 1),
        "confidence_pct": round(confidence_pct, 1),
        "automation_ready": automation_ready,
        "backtesting_ready": backtesting_ready,
        "knowledge_score": knowledge_score,
        "hidden_rule_count": hidden_rule_count,
        "avg_hidden_rule_confidence_pct": avg_hidden_rule_confidence,
    }
