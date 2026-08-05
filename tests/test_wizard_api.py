"""Strategy Wizard API layer: the manual-review run-time gate (same "don't
run unverified logic" enforcement point as the existing Incomplete Lock),
the save endpoint (NEVER REJECT -- always saves, even with Manual Review
items), and the classify-other AI call's graceful degradation when no
provider is available."""

import pytest
from fastapi import HTTPException

from backtest_engine import strategy_library as lib
from ai_integration import config as ai_config
from sindhu_web.api import backtesting, wizard as wizard_api


def _isolated_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))


def _wizard_data_with_manual_review():
    return {
        "name": "Manual Review Blocked Strategy",
        "entry_timeframe": "5m",
        "direction_mode": "long_only",
        "entry_conditions": [
            {"input_mode": "known", "concept": "fvg", "direction": "bullish", "role": "entry"},
            {"input_mode": "other", "raw_text": "wait for the moon to align with Jupiter"},
        ],
        "stop_loss": {"type": "fixed_pct", "value": 1.0},
        "take_profit": {"type": "rr", "value": 2.0},
        "risk_pct": 1.0,
    }


def _wizard_data_fully_dropdown():
    return {
        "name": "Clean Wizard Strategy",
        "entry_timeframe": "5m",
        "direction_mode": "long_only",
        "entry_conditions": [
            {"input_mode": "known", "concept": "fvg", "direction": "bullish", "role": "entry"},
        ],
        "stop_loss": {"type": "fixed_pct", "value": 1.0},
        "take_profit": {"type": "rr", "value": 2.0},
        "risk_pct": 1.0,
    }


def test_save_endpoint_never_rejects_a_strategy_with_manual_review_items(test_db, tmp_path, monkeypatch):
    _isolated_library(tmp_path, monkeypatch)
    result = wizard_api.save_wizard_strategy(wizard_api.SaveRequest(wizard_data=_wizard_data_with_manual_review()))
    assert result["strategy_id"]
    assert result["trust_report"]["manual_review_count"] == 1


def test_run_backtest_is_blocked_for_a_wizard_strategy_with_manual_review(test_db, tmp_path, monkeypatch):
    _isolated_library(tmp_path, monkeypatch)
    saved = wizard_api.save_wizard_strategy(wizard_api.SaveRequest(wizard_data=_wizard_data_with_manual_review()))

    req = backtesting.RunRequest(strategy_id=saved["strategy_id"], all_coins=False, symbols=["BTCUSDT"])
    with pytest.raises(HTTPException) as exc_info:
        backtesting.run_backtest(req)

    assert exc_info.value.status_code == 423
    assert "moon to align with Jupiter" in exc_info.value.detail


def test_run_backtest_is_not_blocked_for_a_fully_dropdown_wizard_strategy(test_db, tmp_path, monkeypatch):
    _isolated_library(tmp_path, monkeypatch)
    monkeypatch.setattr(backtesting.storage, "load_symbols", lambda exchange: ["BTCUSDT"])
    saved = wizard_api.save_wizard_strategy(wizard_api.SaveRequest(wizard_data=_wizard_data_fully_dropdown()))

    req = backtesting.RunRequest(strategy_id=saved["strategy_id"], all_coins=False, symbols=["BTCUSDT"])
    try:
        backtesting.run_backtest(req)
    except HTTPException as e:
        assert e.status_code != 423  # may fail later for unrelated reasons (no market data), never on manual review


# ------------------------------------------------------------- classify-other AI call

def test_classify_other_degrades_gracefully_with_no_ai_provider(monkeypatch):
    monkeypatch.setattr(ai_config, "provider_fallback_chain", lambda: [])
    result = wizard_api.classify_other(wizard_api.ClassifyRequest(raw_text="some undefined thing"))
    assert result == {"matched_concept": None, "ai_available": False, "provider": None}


def test_classify_other_returns_none_when_every_provider_fails(monkeypatch):
    monkeypatch.setattr(ai_config, "provider_fallback_chain", lambda: ["groq"])

    def fake_chain(text, chain, system_prompt, endpoint_label, parse_fn):
        return None, None, "groq: connection refused"

    monkeypatch.setattr(wizard_api, "call_provider_chain_generic", fake_chain)
    result = wizard_api.classify_other(wizard_api.ClassifyRequest(raw_text="some undefined thing"))
    assert result["matched_concept"] is None
    assert result["ai_available"] is True  # a provider WAS configured, it just didn't produce a usable match


def test_classify_other_returns_matched_concept_when_ai_confirms(monkeypatch):
    monkeypatch.setattr(ai_config, "provider_fallback_chain", lambda: ["groq"])

    def fake_chain(text, chain, system_prompt, endpoint_label, parse_fn):
        return parse_fn("fvg"), "groq", None

    monkeypatch.setattr(wizard_api, "call_provider_chain_generic", fake_chain)
    result = wizard_api.classify_other(wizard_api.ClassifyRequest(raw_text="a gap nobody traded in"))
    assert result["matched_concept"] == "fvg"


def test_concept_library_endpoint_returns_real_catalog():
    result = wizard_api.get_concept_library()
    assert "fvg" in result["concepts"]
    assert "ema" in result["indicators"]
