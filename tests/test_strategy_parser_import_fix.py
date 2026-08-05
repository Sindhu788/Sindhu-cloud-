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


_REAL_HTF_FVG_DOC = """STEP 1 — INVENTORY
TOTAL RULES FOUND: 24
HTF analysis timeframe
Source: "Higher-Timeframe Bias/Analysis: The presenter uses a 15-minute time frame looking at the previous 2 to 3 days worth of price to identify Fair Value Gaps (FVGs)."
Entry timeframe
Source: "Actual trade execution and intraday setups are performed on the 1 minute time frame."
Identify HTF FVG
Source: "Locate a series of three candles where the first candle's wick does not overlap with the third candle's wick."
Wait for New York open
Source: "Wait for the New York stock market to open at 9:30."
Price must reach HTF FVG
Source: "Price must gravitate toward a 15-minute FVG."
Reaction must occur at midpoint
Source: "Show a clean response or immediate rejection off the midpoint of that zone."
Market structure failure
Source: "Wait for a failure to make a new high/low."
Change of Character
Source: "Followed by a change of character where price pushes above or below a key level."
Displacement required
Source: "Price must show a significant sign of strength or displacement."
Displacement must create 1m FVG
Source: "Leaves behind a new 1-minute FVG."
Entry location
Source: "Place a limit order to enter exactly at the midpoint area of the newly produced 1-minute FVG."
Long SL placement
Source: "Setting a stop loss underneath the fair value gap producing candle."
Short SL placement
Source: "Stop loss over the fair value gap producing candle."
Move SL to breakeven (short)
Source: "Closes below this last point."
Move SL to breakeven (long)
Source: "Breaks underneath this low."
Minimum RR target
Source: "Immediate and at least 1 to four (1:4) risk-to-reward ratio."
Target selection
Source: "Midpoint of this higher timeframe fair value gap or the next bullish/bearish fair value gap."
Partial exit example
Source: "Half my position off."
Full exit example
Source: "The entire trade off the table."
Avoid chop
Source: "Skip trading inside the range."
Midpoint must hold
Source: "If the 15-minute midpoint is not respected or does not show a rejection, the setup is not valid."
Trendline confluence
Source: "Only enter if the entry aligns with an underside or an oversize retest of a trend line."
Force filter
Source: "Pushing with force to break out of this level that previously wasn't able to be broken."
Level invalidation
Source: "If price disrespects a level by candle closing outside of it, it may invalidate the move."

STEP 2 — CATEGORIZATION
ENTRY CONDITIONS
Rules: 3, 4, 5, 6, 7, 8, 9, 10, 11
EXIT CONDITIONS
Rules: 14, 15, 18, 19
STOP LOSS
Rules: 12, 13
TAKE PROFIT
Rules: 16, 17
FILTERS / DISCARDS
Rules: 20, 21, 22, 23, 24
RISK & POSITION SIZING
Risk examples and position calculator guidance.
TIMEFRAMES & SESSIONS
Rules: 1, 2, 4
DIRECTION-SPECIFIC RULES
Long/Short mirror rules.

STEP 3 — FINAL MACHINE-READABLE SPECIFICATION
[Full specification as previously extracted, including all NOT SPECIFIED items for: clean response definition, immediate rejection definition, midpoint respected definition, Change of Character definition, failure to make high/low definition, key level definition, significant sign of strength definition, displacement definition, pushing with force definition, nonsense chop definition, trendline drawing rules, trendline retest tolerance, buffer for Stop Loss, exact breakeven trigger, which candle produces the FVG if multiple exist, which target has priority when multiple FVGs exist, whether partial exits are mandatory or discretionary, position sizing formula, maximum simultaneous trades, maximum daily loss, maximum daily trades, trading end time, news filter, spread/slippage filter, weekend handling, time zone handling, whether candle closes or intrabar touches are used]

Long setup: reject bullish HTF FVG, fail to make lower low, bullish ChoCH, bullish displacement, bullish 1m FVG, long entry
Short setup: reject bearish HTF FVG, fail to make higher high, bearish ChoCH, bearish displacement, bearish 1m FVG, short entry

STEP 6 — SELF-VERIFICATION
Inventory found: 24 rules
Final output contains: 24 rules
Verification result: Every rule from the Step 1 inventory appears in the final specification. No inventoried rule was omitted.
"""


def test_real_htf_fvg_document_binds_sl_tp_and_handles_long_short():
    """The real CEO-submitted document that first exposed this bug --
    uses "Rule Name" / 'Source: "quoted text"' pairs (not label:value
    lines), a numeric rule-index list under each category header, bare
    ALL-CAPS category titles with no colon, and a bracketed NOT-SPECIFIED
    notes block -- none of which the earlier fix's test fixtures covered."""
    cfg = parse_strategy_text(_REAL_HTF_FVG_DOC, "Real HTF FVG Doc")

    assert cfg.stop_loss.type == "structure"
    assert cfg.take_profit.type == "rr" and cfg.take_profit.value == 4.0
    assert cfg.timeframes.get("bias") == "15m"
    assert cfg.timeframes.get("entry") == "1m"

    # Genuinely not specified anywhere in the document (its own STEP 3
    # block explicitly lists "position sizing formula" as NOT SPECIFIED)
    # -- must be honestly reported as missing, never guessed.
    assert cfg.risk_pct is None
    assert "risk %" in cfg.missing

    # Mixed long/short content must route per-direction, not be merged or
    # rejected.
    assert len(cfg.long_entry_conditions) > 0
    assert len(cfg.short_entry_conditions) > 0
    long_concepts = {c.name for c in cfg.long_entry_conditions if c.type == "concept"}
    short_concepts = {c.name for c in cfg.short_entry_conditions if c.type == "concept"}
    assert "fvg" in long_concepts and "choch" in long_concepts
    assert "fvg" in short_concepts and "choch" in short_concepts

    errors = validate(cfg)
    assert not any("keep one direction per strategy" in e for e in errors)

    # No document scaffolding (category index lists, bare ALL-CAPS
    # headings, the bracketed NOT-SPECIFIED aside) leaked in as fabricated
    # "unclear" rules -- only genuine terse phrases from the document's
    # own prose remain, a small, real, answerable set.
    assert len(cfg.warnings) <= 6
    for w in cfg.warnings:
        assert "TIMEFRAMES" not in w and "RULES:" not in w.upper()


def test_risk_reward_spoken_forms():
    for text, expected in [
        ("Take profit: 1:4", 4.0),
        ("Take profit: 1 to 4 risk reward", 4.0),
        ("Take profit: RR 4", 4.0),
        ("Take profit: 4R", 4.0),
    ]:
        cfg = parse_strategy_text(text, "RR")
        assert cfg.take_profit.type == "rr" and cfg.take_profit.value == expected, text
