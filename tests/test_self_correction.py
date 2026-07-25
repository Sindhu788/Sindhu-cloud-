"""Self-Correcting Import Pipeline (ai_integration/self_correction.py).

The point of this module is that a DETECTED problem must always become a
FIXED problem -- the user has no trading background and cannot resolve a
rule conflict themselves. So these tests check three things, not one:
  1. each deterministic repair actually fixes its own failure mode,
  2. the repaired strategy is genuinely valid afterwards (passes both the
     safety check AND the validator) -- not merely different,
  3. the engine REFUSES to guess where a fix would be a trading judgement
     rather than a structural fact, escalating instead of inventing.

Every failing fixture reproduces a real defect this project hit: the
duplicated exit clause (Liquidity Sweep & FVG Validation Strategy) and the
contradictory pdh/pdl AND-gate (Daily High-Low Liquidity Strategy).
"""

import pytest

from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine.strategy_safety_check import run_safety_check
from backtest_engine import validator
from ai_integration import self_correction


@pytest.fixture(autouse=True)
def _no_telemetry_writes(monkeypatch):
    """Tests must not pollute the real lifetime telemetry counters."""
    monkeypatch.setattr(self_correction, "record_outcome", lambda *a, **k: None)


def _clean_config():
    return StrategyConfig(
        name="Clean", timeframes={"entry": "1h"},
        indicators=[{"name": "rsi", "params": {"period": 14}, "role": None}],
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30.0)],
        exit_conditions=[],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0,
    )


def _duplicate_exit_config():
    """Liquidity Sweep & FVG Validation Strategy's real defect."""
    return StrategyConfig(
        name="Duplicate Exit", timeframes={"entry": "15m"},
        concepts_used=["support", "resistance", "fvg"],
        entry_conditions=[
            Condition(type="concept", name="support", direction="bullish"),
            Condition(type="concept", name="fvg", direction="bullish"),
        ],
        exit_conditions=[Condition(type="concept", name="support", direction="bullish")],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0,
    )


def _contradictory_pdh_pdl_config():
    """Daily High-Low Liquidity Strategy's real defect: 7,927 evaluations,
    0 true, because pdh (close ABOVE previous-day high) and pdl (close
    BELOW previous-day low) were AND-ed on the same bar."""
    return StrategyConfig(
        name="Contradictory PDH/PDL", timeframes={"entry": "5m", "analysis": "1h"},
        concepts_used=["pdh", "pdl", "volume"],
        entry_conditions=[
            Condition(type="concept", name="volume"),
            Condition(type="concept", name="pdh", role="analysis"),
            Condition(type="concept", name="pdl", role="analysis"),
        ],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0,
    )


# ------------------------------------------------------------ Level 0

def test_clean_strategy_is_level_0_and_untouched():
    cfg = _clean_config()
    before = cfg.to_dict()
    result = self_correction.self_correct(cfg, use_ai=False, allow_level2=False)
    assert result["level"] == 0
    assert result["status"] == "ready"
    assert result["repairs"] == []
    assert cfg.to_dict() == before  # a clean strategy must not be "repaired" into something else


# ------------------------------------------------------------ Level 1: duplicate exit

def test_duplicate_exit_clause_is_removed():
    cfg = _duplicate_exit_config()
    assert run_safety_check(cfg)["passed"] is False
    result = self_correction.self_correct(cfg, use_ai=False, allow_level2=False)
    assert result["level"] == 1
    assert result["status"] == "ready"
    assert cfg.exit_conditions == []
    assert run_safety_check(cfg)["passed"] is True


def test_duplicate_exit_is_kept_when_removing_it_would_leave_no_exit_at_all():
    """Removing the only exit rule from a strategy with no stop-loss and no
    take-profit would leave a position that can never close -- strictly
    worse than the duplicate. Must escalate instead of "fixing" it."""
    cfg = _duplicate_exit_config()
    cfg.stop_loss = SLTPSpec(type="unknown")
    cfg.take_profit = SLTPSpec(type="unknown")
    result = self_correction.self_correct(cfg, use_ai=False, allow_level2=False)
    assert len(cfg.exit_conditions) == 1  # untouched
    assert result["level"] == 3


# ------------------------------------------------------------ Level 1: unreachable exit gate

def test_exit_gate_of_only_slow_levels_is_removed_when_sltp_exists():
    cfg = StrategyConfig(
        name="Slow Exit", timeframes={"entry": "15m"},
        concepts_used=["support", "resistance", "fvg"],
        entry_conditions=[Condition(type="concept", name="fvg", direction="bullish")],
        exit_conditions=[
            Condition(type="concept", name="support"),
            Condition(type="concept", name="resistance"),
        ],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0,
    )
    result = self_correction.self_correct(cfg, use_ai=False, allow_level2=False)
    assert result["level"] == 1
    assert cfg.exit_conditions == []
    assert run_safety_check(cfg)["passed"] is True


# ------------------------------------------------------------ Level 1: contradictory gate

def test_contradictory_pdh_pdl_gate_is_split_into_two_directional_setups():
    cfg = _contradictory_pdh_pdl_config()
    result = self_correction.self_correct(cfg, use_ai=False, allow_level2=False)
    assert result["level"] == 1
    assert result["status"] == "ready"
    assert cfg.entry_conditions == []
    assert len(cfg.entry_rule_groups) == 2

    directions = {g["direction"] for g in cfg.entry_rule_groups}
    assert directions == {"bullish", "bearish"}

    bull = next(g for g in cfg.entry_rule_groups if g["direction"] == "bullish")
    bear = next(g for g in cfg.entry_rule_groups if g["direction"] == "bearish")
    assert any(c.name == "pdh" for c in bull["conditions"])
    assert not any(c.name == "pdl" for c in bull["conditions"])
    assert any(c.name == "pdl" for c in bear["conditions"])
    assert not any(c.name == "pdh" for c in bear["conditions"])
    # the non-directional filter must survive on BOTH branches, not be dropped
    assert any(c.name == "volume" for c in bull["conditions"])
    assert any(c.name == "volume" for c in bear["conditions"])

    assert run_safety_check(cfg)["passed"] is True
    assert validator.validate(cfg) == []


def test_same_concept_in_both_directions_is_split():
    cfg = StrategyConfig(
        name="Both Directions", timeframes={"entry": "1m"},
        concepts_used=["candle_break"],
        entry_conditions=[
            Condition(type="concept", name="candle_break", direction="bullish"),
            Condition(type="concept", name="candle_break", direction="bearish"),
        ],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0,
    )
    result = self_correction.self_correct(cfg, use_ai=False, allow_level2=False)
    assert result["level"] == 1
    assert len(cfg.entry_rule_groups) == 2
    assert run_safety_check(cfg)["passed"] is True


def test_numeric_contradiction_is_not_guessed_at_and_escalates():
    """"RSI < 30" AND "RSI > 70" is impossible, but deciding which side is
    the long leg is a trading judgement, not a structural fact. The
    deterministic layer must NOT invent an answer -- it escalates."""
    cfg = StrategyConfig(
        name="Numeric Contradiction", timeframes={"entry": "1h"},
        indicators=[{"name": "rsi", "params": {"period": 5}, "role": None}],
        entry_conditions=[
            Condition(type="indicator_compare", indicator="rsi", params={"period": 5}, op="<", value=30.0),
            Condition(type="indicator_compare", indicator="rsi", params={"period": 5}, op=">", value=70.0),
        ],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.0),
        risk_pct=1.0,
    )
    result = self_correction.self_correct(cfg, use_ai=False, allow_level2=False)
    assert result["level"] == 3
    assert cfg.entry_rule_groups == []  # nothing invented
    assert len(cfg.entry_conditions) == 2  # left exactly as it was


# ------------------------------------------------------------ Level 3

def test_level_3_message_is_plain_language_with_no_engine_jargon():
    cfg = _duplicate_exit_config()
    cfg.stop_loss = SLTPSpec(type="unknown")
    cfg.take_profit = SLTPSpec(type="unknown")
    result = self_correction.self_correct(cfg, use_ai=False, allow_level2=False)
    assert result["level"] == 3
    msg = result["user_message"]
    assert msg
    for jargon in ("entry_conditions", "exit_conditions", "_cond_signature",
                   "entry_rule_groups", "concept:", "AND-gate"):
        assert jargon not in msg


def test_plain_language_summary_never_leaks_raw_engine_wording():
    """An unrecognised technical finding must fall back to a generic plain
    sentence, NOT be passed through verbatim -- the user has no trading
    background and cannot act on 'exit_conditions[0] concept:support'. The
    raw text is still available to developers via remaining_issues."""
    out = self_correction.plain_language_summary(
        ["exit_conditions[0] concept:support failed _cond_signature check"]
    )
    assert out == [self_correction._GENERIC_PLAIN]


# ------------------------------------------------------------ Level 2 gating

def test_level_2_is_skipped_cleanly_when_ai_is_unavailable():
    cfg = _duplicate_exit_config()
    cfg.stop_loss = SLTPSpec(type="unknown")
    cfg.take_profit = SLTPSpec(type="unknown")
    ok, note = self_correction.targeted_ai_fix(cfg, ["some issue"], use_ai=False)
    assert ok is False
    assert "disabled" in note.lower()


def test_level_2_patch_is_discarded_if_it_does_not_actually_fix_the_problem(monkeypatch):
    """An AI "repair" that leaves the strategy still broken must be thrown
    away, not silently applied -- otherwise Level 2 could make a strategy
    different-but-still-wrong and report success."""
    cfg = _duplicate_exit_config()
    cfg.stop_loss = SLTPSpec(type="unknown")
    cfg.take_profit = SLTPSpec(type="unknown")

    monkeypatch.setattr(self_correction, "_build_level2_prompt", lambda c, i: "x")

    class _FakeResult:
        ok, text, tokens_in, tokens_out, latency_ms, error = True, '{"exit_conditions": []}', 1, 1, 1, None

    class _FakeProvider:
        def chat(self, *a, **k):
            return _FakeResult()

    import ai_integration.config as ai_config
    import ai_integration.providers as ai_providers
    monkeypatch.setattr(ai_config, "provider_fallback_chain", lambda: ["fake"])
    monkeypatch.setattr(ai_config, "get_provider_settings", lambda n: {"model": "m"})
    monkeypatch.setattr(ai_providers, "get_provider", lambda n, s: _FakeProvider())

    # Emptying exit_conditions here leaves a strategy with no stop-loss, no
    # take-profit and no exit rule -- still not safe, so it must be rejected.
    ok, note = self_correction.targeted_ai_fix(cfg, ["issue"], use_ai=True)
    assert ok is False
    assert len(cfg.exit_conditions) == 1  # rolled back, original untouched


# ------------------------------------------------------------ telemetry

def test_telemetry_reports_a_level_2_rate(tmp_path, monkeypatch):
    monkeypatch.setattr(self_correction, "_TELEMETRY_PATH", str(tmp_path / "stats.json"))
    monkeypatch.undo()  # keep the real record_outcome for this one test only
    monkeypatch.setattr(self_correction, "_TELEMETRY_PATH", str(tmp_path / "stats.json"))
    self_correction.record_outcome(1, "a")
    self_correction.record_outcome(1, "b")
    self_correction.record_outcome(2, "c")
    self_correction.record_outcome(3, "d")
    tel = self_correction.get_telemetry()
    assert tel["total"] == 4
    assert tel["level_1_auto_fixed"] == 2
    assert tel["level_2_targeted_ai"] == 1
    assert tel["level_2_rate_pct"] == 25.0
