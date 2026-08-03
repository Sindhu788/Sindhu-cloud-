"""Batch 3, Task 3 -- the Incomplete Lock: a strategy with unresolved
rules (after Task 2's retries) is blocked from backtesting/optimization/
paper trading until explicitly overridden; overridden results stay
permanently tagged. Also covers the plain Roman Urdu/Hinglish side-by-
side verification summary.
"""

from ai_integration import extraction_lock
from data_engine import storage


def _save_report(content_hash, strategy_id, rules, retry_count=0):
    expected = len(rules)
    captured = sum(1 for r in rules if r["status"] == "captured")
    storage.save_extraction_fidelity_report(
        content_hash, expected, captured, 5, rules, "groq", "2026-01-01T00:00:00+00:00", retry_count=retry_count,
    )
    storage.set_extraction_fidelity_strategy_id(content_hash, strategy_id)


# ------------------------------------------------------------ check_strategy_lock

def test_strategy_with_no_report_is_not_locked(test_db):
    status = extraction_lock.check_strategy_lock("strat_never_audited")
    assert status["locked"] is False
    assert status["has_report"] is False


def test_strategy_with_all_rules_captured_is_not_locked(test_db):
    _save_report("hash1", "strat1", [
        {"id": 1, "text": "rule one", "category": "entry", "status": "captured", "captured_as": "x"},
        {"id": 2, "text": "rule two", "category": "exit", "status": "captured", "captured_as": "y"},
    ])
    status = extraction_lock.check_strategy_lock("strat1")
    assert status["locked"] is False
    assert status["has_report"] is True


def test_strategy_with_a_missing_rule_is_locked(test_db):
    _save_report("hash2", "strat2", [
        {"id": 1, "text": "rule one", "category": "entry", "status": "captured", "captured_as": "x"},
        {"id": 2, "text": "SL rule not captured", "category": "exit", "status": "missing", "captured_as": None},
    ])
    status = extraction_lock.check_strategy_lock("strat2")
    assert status["locked"] is True
    assert len(status["missing_rules"]) == 1
    assert status["missing_rules"][0]["text"] == "SL rule not captured"


def test_unknown_status_also_counts_as_locked(test_db):
    """"unknown" (comparison call itself failed) is not the same as
    "captured" -- must still block, never silently treated as fine."""
    _save_report("hash3", "strat3", [
        {"id": 1, "text": "rule one", "category": "entry", "status": "unknown", "captured_as": None},
    ])
    status = extraction_lock.check_strategy_lock("strat3")
    assert status["locked"] is True


def test_override_unlocks_the_strategy(test_db):
    _save_report("hash4", "strat4", [
        {"id": 1, "text": "missing rule", "category": "entry", "status": "missing", "captured_as": None},
    ])
    assert extraction_lock.check_strategy_lock("strat4")["locked"] is True

    extraction_lock.set_override("strat4", True)
    status = extraction_lock.check_strategy_lock("strat4")
    assert status["locked"] is False
    assert status["overridden"] is True
    assert len(status["missing_rules"]) == 1  # still tracked, just not blocking


def test_un_overriding_re_locks_the_strategy(test_db):
    _save_report("hash5", "strat5", [
        {"id": 1, "text": "missing rule", "category": "entry", "status": "missing", "captured_as": None},
    ])
    extraction_lock.set_override("strat5", True)
    assert extraction_lock.check_strategy_lock("strat5")["locked"] is False
    extraction_lock.set_override("strat5", False)
    assert extraction_lock.check_strategy_lock("strat5")["locked"] is True


# ------------------------------------------------------------ lock_message / raise_if_locked

def test_lock_message_is_plain_roman_urdu_and_names_the_rule(test_db):
    _save_report("hash6", "strat6", [
        {"id": 1, "text": "Stop loss must be below the swing low", "category": "exit", "status": "missing", "captured_as": None},
    ])
    status = extraction_lock.check_strategy_lock("strat6")
    msg = extraction_lock.lock_message(status)
    assert "Stop loss must be below the swing low" in msg
    assert "confluence" not in msg.lower()
    assert "wilson" not in msg.lower()


def test_lock_message_is_none_when_not_locked(test_db):
    status = {"locked": False, "missing_rules": []}
    assert extraction_lock.lock_message(status) is None


def test_raise_if_locked_raises_with_plain_message(test_db):
    import pytest
    _save_report("hash7", "strat7", [
        {"id": 1, "text": "a missing rule", "category": "entry", "status": "missing", "captured_as": None},
    ])
    with pytest.raises(ValueError, match="a missing rule"):
        extraction_lock.raise_if_locked("strat7")


def test_raise_if_locked_does_not_raise_when_complete(test_db):
    _save_report("hash8", "strat8", [
        {"id": 1, "text": "a rule", "category": "entry", "status": "captured", "captured_as": "x"},
    ])
    extraction_lock.raise_if_locked("strat8")  # must not raise


# ------------------------------------------------------------ verification_summary

def test_verification_summary_for_unaudited_strategy(test_db):
    summary = extraction_lock.verification_summary("strat_new")
    assert summary["has_report"] is False
    assert summary["rows"] == []
    assert "abhi tak" in summary["summary_text"]


def test_verification_summary_lists_rows_with_original_text_and_plain_understanding(test_db):
    _save_report("hash9", "strat9", [
        {"id": 1, "text": "Buy when price crosses above resistance", "category": "entry",
         "status": "captured", "captured_as": "Jab price resistance se upar jaaye tab system dekhta hai"},
        {"id": 2, "text": "Risk only 1% per trade", "category": "filters", "status": "missing", "captured_as": None},
    ])
    summary = extraction_lock.verification_summary("strat9")
    assert summary["expected_count"] == 2
    assert summary["captured_count"] == 1
    assert len(summary["rows"]) == 2
    assert summary["rows"][0]["original_text"] == "Buy when price crosses above resistance"
    assert summary["rows"][0]["captured"] is True
    assert summary["rows"][1]["captured"] is False
    assert summary["rows"][1]["understood_as"]  # a plain-language placeholder, never blank
    assert "1 rule" in summary["summary_text"] or "1 " in summary["summary_text"]


def test_verification_summary_all_captured_says_so_in_plain_language(test_db):
    _save_report("hash10", "strat10", [
        {"id": 1, "text": "rule one", "category": "entry", "status": "captured", "captured_as": "x"},
    ])
    summary = extraction_lock.verification_summary("strat10")
    assert "Achi khabar" in summary["summary_text"]


# ------------------------------------------------------------ Batch 5, Task 3: bilingual coverage

def test_lock_message_in_english(test_db):
    status = {"locked": True, "missing_rules": [{"text": "Risk 1% per trade"}]}
    msg = extraction_lock.lock_message(status, lang="en")
    assert "can't be tested yet" in msg
    assert "Risk 1% per trade" in msg
    assert "Test Anyway" in msg


def test_lock_message_default_is_roman_urdu(test_db):
    status = {"locked": True, "missing_rules": [{"text": "Risk 1% per trade"}]}
    msg = extraction_lock.lock_message(status)
    assert "abhi test nahi ho sakti" in msg
    assert "Risk 1% per trade" in msg  # the exact original rule text interpolates cleanly either way


def test_verification_summary_unaudited_in_english(test_db):
    summary = extraction_lock.verification_summary("strat_new", lang="en")
    assert summary["has_report"] is False
    assert "hasn't been checked yet" in summary["summary_text"]


def test_verification_summary_missing_rules_in_english_interpolates_numbers_cleanly(test_db):
    _save_report("hash11", "strat11", [
        {"id": 1, "text": "Buy when price crosses above resistance", "category": "entry",
         "status": "captured", "captured_as": "x"},
        {"id": 2, "text": "Risk only 1% per trade", "category": "filters", "status": "missing", "captured_as": None},
    ])
    summary = extraction_lock.verification_summary("strat11", lang="en")
    assert "2 rules" in summary["summary_text"]
    assert "1 the system understood correctly" in summary["summary_text"]
    assert summary["rows"][1]["understood_as"] == "This wasn't understood by the system yet."


def test_verification_summary_all_captured_in_english(test_db):
    _save_report("hash12", "strat12", [
        {"id": 1, "text": "rule one", "category": "entry", "status": "captured", "captured_as": "x"},
    ])
    summary = extraction_lock.verification_summary("strat12", lang="en")
    assert "Good news" in summary["summary_text"]


def test_verification_summary_no_rules_found_in_both_languages(test_db):
    _save_report("hash13", "strat13", [])
    ur = extraction_lock.verification_summary("strat13")
    en = extraction_lock.verification_summary("strat13", lang="en")
    assert "koi trading rule nahi mila" in ur["summary_text"]
    assert "No trading rule was found" in en["summary_text"]


def test_raise_if_locked_uses_requested_language(test_db):
    import pytest
    _save_report("hash14", "strat14", [
        {"id": 1, "text": "Risk only 1% per trade", "category": "filters", "status": "missing", "captured_as": None},
    ])
    with pytest.raises(ValueError) as exc_info:
        extraction_lock.raise_if_locked("strat14", lang="en")
    assert "can't be tested yet" in str(exc_info.value)
