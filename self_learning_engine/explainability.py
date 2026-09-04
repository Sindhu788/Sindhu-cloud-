"""Phase 1.12: Discovery Explainability Report -- for every discovered
candidate (accepted OR rejected), a clear record of which concepts were
combined and why, what the out-of-sample validation showed in BOTH
periods, and the final decision and why. Pure formatting over data
discovery_cycle.py already has in hand -- no new computation here.
"""


def build_report(dna_combo, drawn_concepts, ai_suggestion, gate_result, outcome, strategy_id=None, early_rejection_reason=None):
    """gate_result: validation_gate.evaluate()'s return value, or None if
    the candidate never reached the backtest stage (e.g. a structural
    duplicate or a validation-error rejection caught earlier) -- in that
    case early_rejection_reason carries the specific why."""
    lines = [
        f"Concepts combined: {', '.join(drawn_concepts)} (DNA tags: {', '.join(dna_combo)})",
    ]
    if ai_suggestion and ai_suggestion.get("ai_used"):
        lines.append(f"AI suggested this combination: {ai_suggestion['reason']}")
    else:
        lines.append("Chosen by real-data scoring alone (no AI suggestion used this cycle).")

    if gate_result:
        d, v = gate_result["discovery_metrics"], gate_result["validation_metrics"]
        if d:
            lines.append(
                f"Discovery period: {d['total_trades']} trades, {d['win_rate']}% win rate, "
                f"profit factor {d['profit_factor']}."
            )
        if v:
            lines.append(
                f"Validation period: {v['total_trades']} trades, {v['win_rate']}% win rate, "
                f"profit factor {v['profit_factor']}."
            )
        if gate_result.get("win_rate_benchmark_pct") is not None:
            lines.append(
                f"Real-data win-rate benchmark: {gate_result['win_rate_benchmark_pct']}% "
                f"(from {gate_result['profitable_strategy_count_for_benchmark']} currently profitable strategies)."
            )
        if gate_result["passed"]:
            lines.append("Result: PASSED both out-of-sample periods independently.")
        else:
            lines.append("Result: REJECTED -- " + "; ".join(gate_result["reasons"]))
    else:
        lines.append(
            "Never reached backtesting -- rejected before that stage"
            + (f": {early_rejection_reason}." if early_rejection_reason else ".")
        )

    lines.append(f"Final decision: {outcome.upper()}" + (f" (saved as strategy {strategy_id})" if strategy_id else ""))

    return {
        "dna_combo": dna_combo,
        "drawn_concepts": drawn_concepts,
        "ai_used": bool(ai_suggestion and ai_suggestion.get("ai_used")),
        "ai_reason": ai_suggestion.get("reason") if ai_suggestion else None,
        "gate_result": gate_result,
        "outcome": outcome,
        "strategy_id": strategy_id,
        "narrative": "\n".join(lines),
    }
