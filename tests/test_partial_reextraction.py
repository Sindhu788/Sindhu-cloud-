"""Item 5 (Parser & Extraction Improvements) -- Partial Re-Extraction.

Proves a single field of an ALREADY-SAVED strategy can be re-extracted
from its own original source text, without re-running the whole document,
and that every other field is provably left untouched -- demonstrated with
a real before/after diff, not just a passing assertion on one field.
"""

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine import strategy_library as lib
from ai_integration import self_correction
from sindhu_web.api import clarification as clar_api


def _isolated_library(tmp_path, monkeypatch):
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))


def _saved_strategy(**overrides):
    base = dict(
        name="Partial Re-Extraction Test Strategy",
        raw_text="Enter long when RSI crosses above 30. Stop-loss is a fixed 1%. Take-profit is 2:1 risk:reward.",
        timeframes={"entry": "5m"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op=">", value=30.0, params={"period": 14})],
        exit_conditions=[],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0, risk_reward=2.0,
    )
    base.update(overrides)
    return StrategyConfig(**base)


class _FakeResult:
    def __init__(self, text):
        self.ok, self.text, self.tokens_in, self.tokens_out, self.latency_ms, self.error = True, text, 1, 1, 1, None


class _FakeProvider:
    def __init__(self, text):
        self._text = text

    def chat(self, *a, **k):
        return _FakeResult(self._text)


def _mock_ai(monkeypatch, response_json_text):
    import ai_integration.config as ai_config
    import ai_integration.providers as ai_providers
    monkeypatch.setattr(ai_config, "provider_fallback_chain", lambda: ["fake"])
    monkeypatch.setattr(ai_config, "get_provider_settings", lambda n: {"model": "m"})
    monkeypatch.setattr(ai_providers, "get_provider", lambda n, s: _FakeProvider(response_json_text))


def test_partial_reextract_rejects_unknown_field():
    cfg = _saved_strategy()
    ok, note = self_correction.partial_reextract(cfg, "risk_pct")
    assert ok is False
    assert "not a re-extractable field" in note


def test_partial_reextract_skipped_cleanly_when_ai_disabled():
    cfg = _saved_strategy()
    ok, note = self_correction.partial_reextract(cfg, "stop_loss", use_ai=False)
    assert ok is False
    assert "disabled" in note.lower()


def test_partial_reextract_changes_only_the_requested_field(monkeypatch):
    """The core proof: re-extracting stop_loss must change stop_loss and
    NOTHING else -- entry_conditions, exit_conditions, take_profit,
    risk_pct, timeframes all stay byte-identical."""
    cfg = _saved_strategy()
    before = cfg.to_dict()

    _mock_ai(monkeypatch, '{"stop_loss": {"type": "atr_multiple", "value": 2.0}, "explanation": "Uses 2x ATR, not a fixed percent."}')
    ok, note = self_correction.partial_reextract(cfg, "stop_loss")

    assert ok is True
    assert cfg.stop_loss.type == "atr_multiple"
    assert cfg.stop_loss.value == 2.0

    after = cfg.to_dict()
    for key in before:
        if key == "stop_loss":
            continue
        assert after[key] == before[key], f"'{key}' changed but was not the requested field"


def test_partial_reextract_of_entry_conditions_leaves_exit_and_risk_untouched(monkeypatch):
    cfg = _saved_strategy()
    before_exit = list(cfg.exit_conditions)
    before_stop_loss = cfg.stop_loss
    before_risk_pct = cfg.risk_pct

    _mock_ai(monkeypatch, '{"entry_conditions": [{"type": "indicator_compare", "indicator": "rsi", "op": "<", "value": 25.0, "params": {"period": 14}}], "explanation": "Corrected threshold."}')
    ok, note = self_correction.partial_reextract(cfg, "entry_conditions")

    assert ok is True
    assert cfg.entry_conditions[0].value == 25.0
    assert cfg.entry_conditions[0].op == "<"
    assert cfg.exit_conditions == before_exit
    assert cfg.stop_loss == before_stop_loss
    assert cfg.risk_pct == before_risk_pct


def test_partial_reextract_rejects_unusable_response(monkeypatch):
    cfg = _saved_strategy()
    before = cfg.to_dict()
    _mock_ai(monkeypatch, '{"explanation": "nothing to change"}')
    ok, note = self_correction.partial_reextract(cfg, "stop_loss")
    assert ok is False
    assert cfg.to_dict() == before  # nothing mutated on failure


def test_reextract_field_endpoint_saves_a_new_version_and_confirms_isolation(test_db, tmp_path, monkeypatch):
    """End-to-end through the actual API endpoint: saved strategy -> partial
    re-extraction of one field -> new version saved -> every other field
    reported unchanged."""
    _isolated_library(tmp_path, monkeypatch)
    strategy_id = lib.create(_saved_strategy())

    _mock_ai(monkeypatch, '{"take_profit": {"type": "fixed_pct", "value": 3.0}, "explanation": "Fixed 3% target, not RR-based."}')
    result = clar_api.reextract_field(strategy_id, clar_api.ReextractFieldRequest(field="take_profit"))

    assert result["success"] is True
    assert result["new_version"] == 2
    assert result["unexpectedly_changed_fields"] == []

    reloaded = lib.load(strategy_id)
    assert reloaded.take_profit.type == "fixed_pct"
    assert reloaded.take_profit.value == 3.0
    assert reloaded.stop_loss.type == "fixed_pct"  # untouched
    assert reloaded.stop_loss.value == 1.0
