"""Batch 3, Task 3 -- the Incomplete Lock. A strategy whose multi-pass
extraction (Task 1) plus retries (Task 2) still left rules unresolved is
blocked from backtesting, optimization, and paper trading until the CEO
explicitly overrides it -- because the user has no trading background
and cannot judge for themselves whether a "missing rule" matters, an
incomplete strategy's numbers must never silently look like a fair test.

All user-facing text here is plain conversational Roman Urdu/Hinglish,
never a raw internal identifier (condition type names, "confluence
score", etc.) -- matching the whole batch's requirement.
"""

from data_engine import storage


def _lock_from_report(report):
    """Pure function, no I/O -- shared by check_strategy_lock (single) and
    check_strategy_locks_bulk (many) so the two can never disagree."""
    if report is None:
        return {
            "locked": False, "overridden": False, "missing_rules": [],
            "expected_count": 0, "captured_count": 0, "has_report": False,
        }
    missing = [r for r in report["rules"] if r["status"] != "captured"]
    locked = bool(missing) and not report["overridden"]
    return {
        "locked": locked, "overridden": report["overridden"], "missing_rules": missing,
        "expected_count": report["expected_rule_count"], "captured_count": report["captured_rule_count"],
        "has_report": True,
    }


def check_strategy_lock(strategy_id):
    """Returns {"locked", "overridden", "missing_rules", "expected_count",
    "captured_count", "has_report"}.

    A strategy with NO fidelity report at all is NEVER locked -- there is
    no evidence it's incomplete (it may predate this feature, or have
    been imported via Offline Mode with no AI available). The lock only
    ever applies to a strategy that was actually checked by the
    multi-pass pipeline and found to have missing rules -- never a
    blanket freeze over the whole existing library."""
    report = storage.get_extraction_fidelity_report_for_strategy(strategy_id)
    return _lock_from_report(report)


def check_strategy_locks_bulk(strategy_ids):
    """One query for many strategies (data_engine.storage.
    get_latest_extraction_fidelity_reports_for_strategies) instead of one
    per strategy -- for list views (the Strategies table's lock badges)
    that would otherwise pay N round-trips just to show a flag. Returns
    {strategy_id: same shape as check_strategy_lock()}."""
    reports = storage.get_latest_extraction_fidelity_reports_for_strategies(strategy_ids)
    return {sid: _lock_from_report(reports.get(sid)) for sid in strategy_ids}


def lock_message(lock_status, lang="ur"):
    """Plain-language explanation (Roman Urdu by default, English when
    lang="en" -- Batch 5, Task 3), or None if not locked. Pure Python
    string templates in both languages -- no AI translation call."""
    if not lock_status["locked"]:
        return None
    n = len(lock_status["missing_rules"])
    first = lock_status["missing_rules"][0]["text"] if lock_status["missing_rules"] else ""
    if lang == "en":
        rule_word = "rule" if n == 1 else "rules"
        return (
            f"This strategy can't be tested yet -- the system couldn't fully understand {n} {rule_word} from it. "
            f"For example: \"{first}\" -- this isn't reflected in the backtest yet, so the results wouldn't be accurate. "
            "If you want to test it anyway, go to the Strategy Profile page and press \"Test Anyway\" -- "
            "every result will then always show a warning that it came from an incomplete strategy."
        )
    rule_word = "rule" if n == 1 else "rules"
    return (
        f"Yeh strategy abhi test nahi ho sakti -- iske {n} {rule_word} system ko poori tarah samajh nahi aaye. "
        f"Ek example: \"{first}\" -- yeh baat abhi tak backtest mein shamil nahi hai, is liye result sahi nahi honge. "
        "Agar aap phir bhi test karna chahte hain to Strategy Profile page par jaakar \"Test Anyway\" dabayein -- "
        "phir har result ke saath yeh warning hamesha dikhegi ke yeh adhoori strategy se aaya hai."
    )


def raise_if_locked(strategy_id, lang="ur"):
    """Call at the top of any backtest/optimize/paper-trading entry
    point. Raises ValueError(message) if locked -- callers translate
    that into an HTTP 423 (Locked) or equivalent; never silently no-ops
    and never lets a locked strategy through."""
    status = check_strategy_lock(strategy_id)
    if status["locked"]:
        raise ValueError(lock_message(status, lang=lang))
    return status


def set_override(strategy_id, overridden):
    storage.set_extraction_fidelity_override(strategy_id, overridden)


def verification_summary(strategy_id, lang="ur"):
    """The full side-by-side view data + a plain-language overall summary
    (Roman Urdu by default, English when lang="en" -- Batch 5, Task 3) --
    what Task 3's dashboard page reads directly. Never raw internal
    identifiers: "original_text" is always the user's own document
    wording (quoted verbatim), and "understood_as" is the AI's own
    plain-language description generated AT EXTRACTION TIME (see
    ai_integration.sentence_level_extraction._describe_fragment /
    schema.build_comparison_prompt) -- for a strategy extracted before
    this bilingual support existed, that stored text stays in whichever
    language it was originally generated in (Roman Urdu); re-running the
    extraction (the "Check Again" button) regenerates it bilingually.
    This function's OWN template text (summary_text, the fallback
    "not understood" line) is always correct in either language
    regardless of when the strategy was extracted, since it's a plain
    Python string choice, not stored AI output."""
    report = storage.get_extraction_fidelity_report_for_strategy(strategy_id)
    lock = check_strategy_lock(strategy_id)
    en = lang == "en"

    if report is None:
        return {
            "has_report": False,
            "summary_text": (
                "This strategy hasn't been checked yet -- it may have been imported before this "
                "verification feature existed. Use the button below to check it now."
                if en else
                "Is strategy ka abhi tak koi check nahi hua -- shayad yeh naya verification feature aane se pehle import hui thi. Neeche button se check karwa sakte hain."
            ),
            "rows": [], "locked": False, "overridden": False,
            "expected_count": 0, "captured_count": 0, "retry_count": 0, "provider": None,
        }

    total = report["expected_rule_count"]
    captured = report["captured_rule_count"]
    missing = total - captured
    if en:
        if total == 0:
            summary_text = "No trading rule was found in this document -- it may have just been notes or a lesson, not a strategy."
        elif missing == 0:
            summary_text = f"Good news -- the system correctly understood all {total} rules in this strategy, nothing is missing."
        else:
            rule_word_total = "rule" if total == 1 else "rules"
            rule_word_missing = "rule" if missing == 1 else "rules"
            summary_text = (
                f"This document has {total} {rule_word_total} in total, of which {captured} the system understood correctly. "
                f"{missing} {rule_word_missing} still weren't understood -- see the list below for which ones."
            )
    else:
        if total == 0:
            summary_text = "Is document mein koi trading rule nahi mila -- shayad yeh sirf notes ya lesson tha, strategy nahi."
        elif missing == 0:
            summary_text = f"Achi khabar -- is strategy ke total {total} rules system ne sahi tarah samajh liye hain, kuch bhi missing nahi hai."
        else:
            rule_word_total = "rule tha" if total == 1 else "rules the"
            rule_word_missing = "rule" if missing == 1 else "rules"
            summary_text = (
                f"Is document mein total {total} {rule_word_total}, jinme se {captured} system ne sahi samjhe. "
                f"{missing} {rule_word_missing} abhi tak samajh nahi aaye -- neeche list mein dekh sakte hain kaunse."
            )

    not_understood_fallback = "This wasn't understood by the system yet." if en else "Yeh baat abhi tak system ko samajh nahi aayi."
    rows = [
        {
            "id": r["id"], "category": r["category"], "original_text": r["text"],
            "captured": r["status"] == "captured", "status": r["status"],
            "understood_as": r.get("captured_as") or (
                not_understood_fallback if r["status"] != "captured" else None
            ),
        }
        for r in report["rules"]
    ]
    return {
        "has_report": True, "summary_text": summary_text, "rows": rows,
        "locked": lock["locked"], "overridden": lock["overridden"],
        "expected_count": total, "captured_count": captured,
        "retry_count": report["retry_count"], "provider": report["provider"],
    }
