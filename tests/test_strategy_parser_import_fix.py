"""Regression coverage for the URGENT strategy-import field-routing bug
(2026-08-04): the parser was classifying stop-loss/take-profit/risk lines
as unclear entry rules while simultaneously reporting those same fields as
missing, and document scaffolding (STEP headings, Source: lines, bare
section headers, numbered-list line-wrapping) leaked into the rule list as
spurious "unclear" fragments. These tests reproduce the exact inputs from
that bug report."""

from backtest_engine.strategy_parser import parse_strategy_text
from backtest_engine.validator import validate


def test_attempt_3_stop_loss_below_entry_price_binds_correctly():
    cfg = parse_strategy_text("Stop loss: fixed 0.3% below entry price", "A3")
    assert cfg.stop_loss.type == "fixed_pct"
    assert cfg.stop_loss.value == 0.3
    assert cfg.warnings == []


def test_attempt_4_sl_tp_risk_all_bind_and_none_are_misrouted_as_entry():
    doc = (
        "Stop loss: fixed percent 0.3\n"
        "Take profit: risk reward ratio 4\n"
        "Risk percent: 1\n"
    )
    cfg = parse_strategy_text(doc, "A4")
    assert cfg.stop_loss.type == "fixed_pct" and cfg.stop_loss.value == 0.3
    assert cfg.take_profit.type == "rr" and cfg.take_profit.value == 4.0
    assert cfg.risk_pct == 1.0
    assert cfg.warnings == []
    assert cfg.entry_conditions == []


def test_raw_document_with_scaffolding_and_wrapped_numbered_item():
    doc = """STEP 1 -- Strategy Overview
Source: YouTube video transcript, ICT concepts [1, 2]

RISK MANAGEMENT:
Risk percent: 1
Stop loss: fixed percent 0.3
Take profit: risk reward ratio 4

FILTERS:
Session: London

Entry Rules:
1. Wait for a liquidity sweep of the previous day low
2. Confirm bullish BOS on the 1-minute chart
3. Enter on retracement into the FVG
4. On the 1-minute chart,
wait for a bullish engulfing candle
(opposite direction)

Timeframes:
Entry: 1m
Bias: 4H
"""
    cfg = parse_strategy_text(doc, "Raw Doc Test")

    assert cfg.stop_loss.type == "fixed_pct" and cfg.stop_loss.value == 0.3
    assert cfg.take_profit.type == "rr" and cfg.take_profit.value == 4.0
    assert cfg.risk_pct == 1.0
    assert cfg.session_filter == ["london"]
    assert cfg.timeframes == {"entry": "1m", "bias": "4h"}
    assert cfg.warnings == []
    assert cfg.missing == []

    concept_names = [c.name for c in cfg.entry_conditions if c.type == "concept"]
    assert concept_names == ["liquidity_sweep", "bos", "fvg", "engulfing"]
    assert len(cfg.entry_conditions) == 4


def test_natural_language_signal_candle_stop_loss():
    cfg = parse_strategy_text(
        "Stop loss: below the low of the candle that created the FVG", "SC"
    )
    assert cfg.stop_loss.type == "signal_candle"


def test_long_and_short_sections_route_per_direction_without_merge_or_rejection():
    doc = """Long Entry Rules:
Bullish BOS on the 1H chart
Enter on retracement into bullish FVG

Short Entry Rules:
Bearish BOS on the 1H chart
Enter on retracement into bearish FVG

Stop loss: fixed 0.3%
Take profit: RR 4
Risk percent: 1
"""
    cfg = parse_strategy_text(doc, "LongShort Test")
    assert cfg.warnings == []
    assert cfg.entry_conditions == []

    long_names = [(c.name, c.direction) for c in cfg.long_entry_conditions]
    short_names = [(c.name, c.direction) for c in cfg.short_entry_conditions]
    assert long_names == [("bos", "bullish"), ("fvg", "bullish")]
    assert short_names == [("bos", "bearish"), ("fvg", "bearish")]

    errors = validate(cfg)
    assert not any("keep one direction per strategy" in e for e in errors)


def test_risk_reward_spoken_forms():
    for text, expected in [
        ("Take profit: 1:4", 4.0),
        ("Take profit: 1 to 4 risk reward", 4.0),
        ("Take profit: RR 4", 4.0),
        ("Take profit: 4R", 4.0),
    ]:
        cfg = parse_strategy_text(text, "RR")
        assert cfg.take_profit.type == "rr" and cfg.take_profit.value == expected, text
