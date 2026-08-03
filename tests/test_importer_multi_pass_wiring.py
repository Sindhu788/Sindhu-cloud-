"""Batch 5, Task 1 -- ai_integration.importer.import_document routes
declared strategy content through the sentence-level extraction pipeline
(replacing Batch 3's multi-pass approach for that case), persists the
completeness comparison, and links it to the saved strategy. Lesson/mixed
content and cache hits are unaffected. All AI calls mocked -- no network.
"""

from unittest.mock import patch

from ai_integration import importer, schema
from data_engine import storage


def _fake_sentence_level_result(strategy_dict, expected=3, captured=2):
    return {
        "result": {**dict(schema._REQUIRED_KEYS), "confidence": 90, "strategy": strategy_dict},
        "provider": "groq",
        "call_count": 5,
        "retry_count": 0,
        "rule_inventory": {"candidates": [{"id": i, "text": f"rule {i}", "signals": ["entry_exit"]} for i in range(1, expected + 1)], "count": expected},
        "comparison": {
            "expected_count": expected, "captured_count": captured,
            "rules": [
                {"id": i, "text": f"rule {i}", "category": "entry_exit",
                 "status": "captured" if i <= captured else "missing", "captured_as": "x" if i <= captured else None}
                for i in range(1, expected + 1)
            ],
        },
        "error": None,
    }


_MINIMAL_STRATEGY = {
    "name": "Test Strategy", "timeframes": {"entry": "1h"}, "indicators": [], "concepts_used": ["bos"],
    "entry_conditions": [{"type": "concept", "name": "bos", "direction": "bullish"}],
    "long_entry_conditions": [], "short_entry_conditions": [], "entry_rule_groups": [],
    "exit_conditions": [], "confirmation_conditions": [],
    "stop_loss": {"type": "fixed_pct", "value": 1.0, "level": None},
    "take_profit": {"type": "rr", "value": 2.0, "level": None},
    "risk_pct": 1.0, "risk_reward": 2.0, "session_filter": [], "trend_filter": None, "day_filter": [],
    "breakeven_at_rr": None, "entry_type": "market", "entry_price_offset_pct": None,
    "sl_distance_filter_pct": None, "min_risk_reward_filter": None, "primary_target_lookback_bars": None,
    "partial_take_profit": None,
}


def test_strategy_content_type_uses_sentence_level_and_saves_fidelity_report(test_db, tmp_path, monkeypatch):
    from data_engine import config as base_config
    from backtest_engine import strategy_library as strategy_library_pkg
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(strategy_library_pkg, "_LIBRARY_DIR", str(tmp_path / "library"))

    fake_result = _fake_sentence_level_result(_MINIMAL_STRATEGY, expected=3, captured=2)
    with patch.object(importer.sentence_level_extraction, "run_sentence_level_extraction", return_value=fake_result) as mock_sle, \
         patch.object(importer.deep_understanding, "understand_document_structured") as mock_single, \
         patch.object(importer, "_maybe_trigger_pipeline"):
        result = importer.import_document(
            "Some strategy text with entry/exit rules.", title="Test Strategy",
            content_type="strategy",
        )

    mock_sle.assert_called_once()
    mock_single.assert_not_called()  # single-pass path must not run for declared strategy content
    assert result["extraction_fidelity"]["expected_rule_count"] == 3
    assert result["extraction_fidelity"]["captured_rule_count"] == 2

    saved_strategy_ids = [s["saved_strategy_id"] for s in result["document"].get("strategies") or [] if s.get("saved_strategy_id")]
    assert saved_strategy_ids
    report = storage.get_extraction_fidelity_report_for_strategy(saved_strategy_ids[0])
    assert report is not None
    assert report["expected_rule_count"] == 3
    assert report["captured_rule_count"] == 2


def test_lesson_content_type_still_uses_single_pass_not_sentence_level(test_db, tmp_path, monkeypatch):
    from data_engine import config as base_config
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))

    single_pass_result = {"result": None, "provider": None, "error": None}
    with patch.object(importer.deep_understanding, "understand_document_structured", return_value=single_pass_result) as mock_single, \
         patch.object(importer.sentence_level_extraction, "run_sentence_level_extraction") as mock_sle:
        importer.import_document("Some lesson text.", title="Test Lesson", content_type="lesson")

    mock_single.assert_called_once()
    mock_sle.assert_not_called()


def test_cache_hit_skips_sentence_level_extraction_entirely(test_db, tmp_path, monkeypatch):
    from data_engine import config as base_config
    from backtest_engine import strategy_library as strategy_library_pkg
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(strategy_library_pkg, "_LIBRARY_DIR", str(tmp_path / "library"))

    raw_text = "Cached strategy text."
    content_hash = importer._content_hash(raw_text)
    cached_ai_result = {**dict(schema._REQUIRED_KEYS), "confidence": 90, "strategy": _MINIMAL_STRATEGY}
    storage.save_ai_import_cache(content_hash, cached_ai_result, "groq", "2026-01-01T00:00:00+00:00")

    with patch.object(importer.sentence_level_extraction, "run_sentence_level_extraction") as mock_sle, \
         patch.object(importer, "_maybe_trigger_pipeline"):
        result = importer.import_document(raw_text, title="Cached Strategy", content_type="strategy")

    mock_sle.assert_not_called()
    assert result["served_from_cache"] is True
    assert result["extraction_fidelity"] is None
