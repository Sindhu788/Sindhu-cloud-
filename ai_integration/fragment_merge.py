"""Shared additive-merge logic for combining multiple partial strategy
extraction fragments (each schema._clean_strategy()-shaped) into one
strategy dict, without ever letting a later fragment silently overwrite
a field an earlier one already resolved. Used by both
ai_integration.multi_pass_extraction (merging retry results) and
ai_integration.sentence_level_extraction (merging one fragment per
candidate statement, Batch 5, Task 1).
"""


def merge_list(*lists):
    out = []
    for lst in lists:
        for item in lst or []:
            if item not in out:
                out.append(item)
    return out


def merge_fragment_additive(existing, fragment):
    """Merges `fragment` INTO `existing` -- additive only. A field
    `existing` already resolved is never overwritten by `fragment` (list
    fields are unioned/deduped instead; scalar fields only fill in if
    `existing`'s value is still the "nothing found" default)."""
    if not fragment:
        return existing
    if not existing:
        return fragment
    merged = dict(existing)
    merged["entry_conditions"] = merge_list(existing.get("entry_conditions"), fragment.get("entry_conditions"))
    merged["long_entry_conditions"] = merge_list(existing.get("long_entry_conditions"), fragment.get("long_entry_conditions"))
    merged["short_entry_conditions"] = merge_list(existing.get("short_entry_conditions"), fragment.get("short_entry_conditions"))
    if not existing.get("entry_rule_groups"):
        merged["entry_rule_groups"] = fragment.get("entry_rule_groups") or existing.get("entry_rule_groups") or []
    merged["exit_conditions"] = merge_list(existing.get("exit_conditions"), fragment.get("exit_conditions"))
    merged["confirmation_conditions"] = merge_list(existing.get("confirmation_conditions"), fragment.get("confirmation_conditions"))

    if (existing.get("stop_loss") or {}).get("type", "unknown") == "unknown" \
            and (fragment.get("stop_loss") or {}).get("type", "unknown") != "unknown":
        merged["stop_loss"] = fragment["stop_loss"]
    if (existing.get("take_profit") or {}).get("type", "unknown") == "unknown" \
            and (fragment.get("take_profit") or {}).get("type", "unknown") != "unknown":
        merged["take_profit"] = fragment["take_profit"]
    if existing.get("risk_pct") is None and fragment.get("risk_pct") is not None:
        merged["risk_pct"] = fragment["risk_pct"]
    if existing.get("risk_reward") is None and fragment.get("risk_reward") is not None:
        merged["risk_reward"] = fragment["risk_reward"]
    merged["session_filter"] = merge_list(existing.get("session_filter"), fragment.get("session_filter"))
    merged["day_filter"] = merge_list(existing.get("day_filter"), fragment.get("day_filter"))
    if existing.get("trend_filter") is None and fragment.get("trend_filter"):
        merged["trend_filter"] = fragment["trend_filter"]
    if existing.get("breakeven_at_rr") is None and fragment.get("breakeven_at_rr") is not None:
        merged["breakeven_at_rr"] = fragment["breakeven_at_rr"]
    if (existing.get("entry_type") or "market") == "market" and fragment.get("entry_type") not in (None, "market"):
        merged["entry_type"] = fragment["entry_type"]
    if existing.get("entry_price_offset_pct") is None and fragment.get("entry_price_offset_pct") is not None:
        merged["entry_price_offset_pct"] = fragment["entry_price_offset_pct"]
    if not existing.get("sl_distance_filter_pct") and fragment.get("sl_distance_filter_pct"):
        merged["sl_distance_filter_pct"] = fragment["sl_distance_filter_pct"]
    if existing.get("min_risk_reward_filter") is None and fragment.get("min_risk_reward_filter") is not None:
        merged["min_risk_reward_filter"] = fragment["min_risk_reward_filter"]
        merged["primary_target_lookback_bars"] = fragment.get("primary_target_lookback_bars")
    if not existing.get("partial_take_profit") and fragment.get("partial_take_profit"):
        merged["partial_take_profit"] = fragment["partial_take_profit"]

    merged["timeframes"] = {**(fragment.get("timeframes") or {}), **(existing.get("timeframes") or {})}
    merged["indicators"] = merge_list(existing.get("indicators"), fragment.get("indicators"))
    merged["concepts_used"] = merge_list(existing.get("concepts_used"), fragment.get("concepts_used"))
    if not existing.get("name") and fragment.get("name"):
        merged["name"] = fragment["name"]
    return merged
