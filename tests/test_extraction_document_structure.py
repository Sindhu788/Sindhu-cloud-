"""Two-Focused-Day Push, Part 1 -- Extraction Quality Fix. Unit tests using
real fragments from the actual failing document the CEO pasted (a
markdown-heavy 4H Fractal Sweep Scalping strategy: headers, bold labels,
nested bullets, and advisory prose mixed with real rules).

Confirmed root causes (via a real re-import against the live AI pipeline,
not guessed):
1. Bold-only section-label lines ("**Placement:**") were never recognized
   as structural scaffolding for single-model documents -- only a 2+
   "Model N:" document tracked ANY section heading at all, so a normal
   single-model document's "Entry Rules" / "Stop Loss Rules" / "Take
   Profit Rules" structure gave isolated per-statement AI calls zero
   section context.
2. An isolated statement backward-referencing something DEFINED earlier
   in the document ("the marked 4H high level", established by an
   earlier "identify the most recent Fractal high/low... draw horizontal
   lines" statement) had no way to resolve that reference in total
   isolation -- it fell back to type="raw" (a clarification dead end)
   even though the rule is completely unambiguous once you've read the
   whole document.
3. A "strong candles"/"avoid Doji candles" quality-check statement had NO
   vocabulary equivalent at all, so the AI's only options were "not a
   rule" (silently dropping a REAL ambiguity the CEO should be asked
   about) or "raw" (an unlabeled dead end) -- neither correctly signals
   "this is a genuine, real clarification question."

These tests are pure/deterministic (no AI call) -- they check the
pre-processing and post-processing SINDHU controls directly, matching the
project's testing convention for this pipeline (mocked-AI end-to-end
coverage already exists in test_extraction_pipeline_improvements.py)."""

from ai_integration.deterministic_rules import (
    count_candidate_rules, extract_document_preambles, split_into_statements_with_labels,
)
from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine.configured_strategy import ConfiguredStrategy
from backtest_engine.validator import validate
from sindhu_web.api import clarification as clar_api
import pandas as pd

FRACTAL_SWEEP_DOC = """This 5-minute scalping strategy focuses on identifying major support and resistance levels on a high timeframe and trading "price sweeps" on a lower timeframe.

### **1. Setup and Preparation**
*   **Indicators:** Use the **Williams Fractals** indicator to automatically identify swing highs and swing lows.
*   **Timeframes:**
    *   **Analysis Timeframe:** Use the **4-hour (4H) chart** to mark your key levels.
    *   **Execution Timeframe:** Use the **5-minute (5M) chart** for entering and managing trades.
*   **Marking the Levels:** On the 4H chart, identify the most recent **Fractal high** and **Fractal low**. Draw horizontal lines at these points to create your trading range.

### **2. Entry Rules**
Once levels are marked, switch to the 5M chart and hide the Fractals to avoid visual clutter.

#### **Short Entry (Sell)**
*   **The Sweep:** Wait for the price to rise above the marked 4H high level.
*   **The Re-entry:** The entry is triggered when the price **closes back inside the range** (below the 4H high line).
*   **Quality Check:** A valid sweep should ideally occur with **strong candles**. If the price lingers above the level with very small or Doji candles, the sweep is less reliable and might fail.

#### **Long Entry (Buy)**
*   **The Sweep:** Wait for the price to drop below the marked 4H low level.
*   **The Re-entry:** Enter the trade when a candle **closes back above the 4H low level**, indicating price has reclaimed the range.
*   **Quality Check:** Ensure the price moves decisively back into the range after the sweep.

### **3. Stop Loss (SL) Rules**
*   **Placement:**
    *   For **Short trades**, place the SL **slightly above the high** created by the sweep.
    *   For **Long trades**, place the SL **slightly below the low** created by the sweep.
*   **Margin Buffer:** It is recommended to leave a **small margin (buffer)** beyond the exact high or low to prevent being prematurely stopped out by minor price fluctuations.

### **4. Take Profit (TP) Rules**
*   **Risk-to-Reward Ratio:** This strategy strictly utilizes a **1:2 risk-to-reward ratio**.
*   For every $1 you risk, your target should be $2 in profit.

### **Key Considerations for Success**
*   **Patience:** If the price is stuck in the middle of the 4H range, avoid trading until it reaches one of the boundaries to perform a sweep.
*   **Avoid Selective Trading:** The strategy should be applied consistently to all qualifying setups to maintain confidence in its effectiveness.
*   **Continuous Monitoring:** As new Fractals form on the 4H chart, you must update your high and low markings accordingly to reflect the most current market structure.
"""


# ------------------------------------------------------------ Root cause 1: bold-only section labels

def test_bold_only_section_label_lines_are_never_treated_as_standalone_statements():
    """'*   **Placement:**' must never itself become a rule candidate --
    it is pure structural scaffolding, same as a markdown heading."""
    labeled = split_into_statements_with_labels(FRACTAL_SWEEP_DOC)
    texts = [t for t, _m, _s in labeled]
    assert not any(t.strip().rstrip(":") == "Placement" for t in texts)
    assert not any(t.strip() == "Margin Buffer:" for t in texts)


def test_single_model_document_still_gets_section_labels_now():
    """Regression for the actual gap: a normal (single-model) document's
    ordinary section headings ('Short Entry (Sell)', 'Stop Loss (SL)
    Rules') previously produced NO section_label at all (that tracking
    only ever ran for 2+-model documents) -- now it does."""
    labeled = split_into_statements_with_labels(FRACTAL_SWEEP_DOC)
    sweep_stmt = next((t, s) for t, _m, s in labeled if "Wait for the price to rise above" in t)
    assert sweep_stmt[1] == "Short Entry (Sell)"
    long_sweep_stmt = next((t, s) for t, _m, s in labeled if "Wait for the price to drop below" in t)
    assert long_sweep_stmt[1] == "Long Entry (Buy)"


def test_candidate_rules_carry_the_new_section_label_field():
    result = count_candidate_rules(FRACTAL_SWEEP_DOC)
    sl_candidate = next(c for c in result["candidates"] if "place the SL" in c["text"] and "Short" in c["text"])
    assert sl_candidate["section_label"] == "Placement"


# ------------------------------------------------------------ Root cause 2: backward-reference preamble

def test_document_preamble_captures_the_level_definition():
    """The actual missing piece: 'the marked 4H high/low level' is defined
    by this earlier statement -- it must be recoverable as context."""
    preambles = extract_document_preambles(FRACTAL_SWEEP_DOC)
    preamble = preambles[None]  # single-model document
    assert "Fractal high" in preamble
    assert "Fractal low" in preamble
    assert "trading range" in preamble


def test_document_preamble_never_includes_the_actual_entry_rules():
    """The preamble is background only -- it must stop before the real
    Entry Rules content, never duplicate/leak the rules themselves."""
    preambles = extract_document_preambles(FRACTAL_SWEEP_DOC)
    preamble = preambles[None]
    assert "Wait for the price to rise above" not in preamble
    assert "strong candles" not in preamble


def test_document_preamble_is_bounded_in_length():
    huge_doc = "Setup: " + ("This is filler background text. " * 200) + "\nEntry: buy when RSI < 30."
    preambles = extract_document_preambles(huge_doc)
    assert len(preambles[None]) <= 700


# ------------------------------------------------------------ Root cause 3: candle-quality vocabulary (candle_body_pct)

def test_candle_body_pct_condition_type_is_recognized_by_the_validator():
    cfg = StrategyConfig(
        name="Candle Quality Test", raw_text="test", timeframes={"entry": "5m"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30.0),
                           Condition(type="candle_body_pct", params={"min_pct": 50.0})],
        exit_conditions=[], stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.0), risk_pct=1.0, risk_reward=2.0,
    )
    errors = validate(cfg)
    assert not any("Invalid indicator" in e for e in errors)  # never mistaken for an unknown indicator


def test_candle_body_pct_with_no_min_pct_becomes_an_actionable_clarification_issue():
    """The actual fix for genuine ambiguity #1 (strong candles/Doji, no
    exact percentage given): must surface as a real, resolvable question
    with multiple-choice options -- not silently dropped, not a dead end."""
    cfg = StrategyConfig(
        name="Candle Quality Test", raw_text="test", timeframes={"entry": "5m"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30.0),
                           Condition(type="candle_body_pct", params={"min_pct": None})],
        exit_conditions=[], stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.0), risk_pct=1.0, risk_reward=2.0,
    )
    issues = clar_api.build_issues(cfg)
    quality_issues = [i for i in issues if i["kind"] == "quality_filter_threshold"]
    assert len(quality_issues) == 1
    options = quality_issues[0]["suggested_options"]
    assert len(options) == 3
    labels = [o["label"] for o in options]
    assert any("50%" in l for l in labels)
    assert any("70%" in l for l in labels)
    assert any("soft" in l.lower() or "manual" in l.lower() for l in labels)


def test_candle_body_pct_evaluator_correctly_rejects_a_doji_candle():
    """A Doji (open==close) has 0% body -- must fail any positive min_pct,
    matching the plain-language meaning of 'avoid Doji candles' exactly."""
    cfg = StrategyConfig(
        name="Doji Test", raw_text="test", timeframes={"entry": "5m"},
        entry_conditions=[Condition(type="candle_body_pct", params={"min_pct": 50.0})],
        exit_conditions=[], stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.0), risk_pct=1.0, risk_reward=2.0,
    )
    strat = ConfiguredStrategy(cfg)
    df = pd.DataFrame({
        "entry_open": [100.0], "entry_high": [102.0], "entry_low": [98.0], "entry_close": [100.0],
    })
    strat.prepare(df)
    result = strat._eval(cfg.entry_conditions[0], df, 0)
    assert bool(result) is False


def test_candle_body_pct_evaluator_accepts_a_strong_candle():
    cfg = StrategyConfig(
        name="Strong Candle Test", raw_text="test", timeframes={"entry": "5m"},
        entry_conditions=[Condition(type="candle_body_pct", params={"min_pct": 50.0})],
        exit_conditions=[], stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.0), risk_pct=1.0, risk_reward=2.0,
    )
    strat = ConfiguredStrategy(cfg)
    # Body = |103-100| = 3, range = 104-99 = 5 -> body_pct = 60% >= 50%
    df = pd.DataFrame({
        "entry_open": [100.0], "entry_high": [104.0], "entry_low": [99.0], "entry_close": [103.0],
    })
    strat.prepare(df)
    result = strat._eval(cfg.entry_conditions[0], df, 0)
    assert bool(result) is True


def test_user_can_resolve_the_candle_quality_ambiguity_with_a_multiple_choice_option(test_db, tmp_path, monkeypatch):
    from backtest_engine import strategy_library as lib
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))
    cfg = StrategyConfig(
        name="Candle Quality Resolve Test", raw_text="test", timeframes={"entry": "5m"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30.0),
                           Condition(type="candle_body_pct", params={"min_pct": None})],
        exit_conditions=[], stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.0), risk_pct=1.0, risk_reward=2.0,
    )
    strategy_id = lib.create(cfg)
    issue = [i for i in clar_api.build_issues(cfg) if i["kind"] == "quality_filter_threshold"][0]
    fifty_pct_option = next(o for o in issue["suggested_options"] if "50%" in o["label"])

    req = clar_api.ClarifyRequest(resolutions=[
        clar_api.ClarifyResolution(id=issue["id"], action=fifty_pct_option["action"], value=fifty_pct_option["value"]),
    ])
    result = clar_api.clarify_strategy(strategy_id, req)
    assert len(result["applied"]) == 1

    resolved = lib.load(strategy_id)
    body_conds = [c for c in resolved.entry_conditions if c.type == "candle_body_pct"]
    assert body_conds[0].params["min_pct"] == 50.0
    # Genuinely resolved -- the issue is gone on the next fetch.
    assert not any(i["kind"] == "quality_filter_threshold" for i in clar_api.build_issues(resolved))


# ------------------------------------------------------------ Genuine ambiguity #2: SL buffer size

def test_unspecified_signal_candle_buffer_is_a_real_clarification_issue():
    """Genuine ambiguity #2 from the reference case: 'leave a small margin
    (buffer) beyond the exact high or low' -- the STOP STRUCTURE
    (signal_candle: the sweep's own high/low) is completely clear, only
    the buffer % isn't quantified. Without this, _compute_stop_loss
    silently assumes a ZERO buffer -- must be surfaced, not assumed."""
    cfg = StrategyConfig(
        name="Buffer Test", raw_text="test", timeframes={"entry": "5m"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30.0)],
        exit_conditions=[], stop_loss=SLTPSpec(type="signal_candle", value=None),
        take_profit=SLTPSpec(type="rr", value=2.0), risk_pct=1.0, risk_reward=2.0,
    )
    issues = clar_api.build_issues(cfg)
    buffer_issues = [i for i in issues if i["id"] == "field:stop_loss"]
    assert len(buffer_issues) == 1
    labels = [o["label"] for o in buffer_issues[0]["suggested_options"]]
    assert any("0.1%" in l for l in labels)
    assert any("0.2%" in l for l in labels)
    assert any("0.5%" in l for l in labels)
    assert any("No buffer" in l for l in labels)


def test_a_fully_specified_signal_candle_stop_loss_raises_no_buffer_issue():
    cfg = StrategyConfig(
        name="Buffer Specified Test", raw_text="test", timeframes={"entry": "5m"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30.0)],
        exit_conditions=[], stop_loss=SLTPSpec(type="signal_candle", value=0.2),
        take_profit=SLTPSpec(type="rr", value=2.0), risk_pct=1.0, risk_reward=2.0,
    )
    issues = clar_api.build_issues(cfg)
    assert not any(i["id"] == "field:stop_loss" for i in issues)


def test_user_can_resolve_the_buffer_ambiguity_with_a_multiple_choice_option(test_db, tmp_path, monkeypatch):
    from backtest_engine import strategy_library as lib
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))
    cfg = StrategyConfig(
        name="Buffer Resolve Test", raw_text="test", timeframes={"entry": "5m"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30.0)],
        exit_conditions=[], stop_loss=SLTPSpec(type="signal_candle", value=None),
        take_profit=SLTPSpec(type="rr", value=2.0), risk_pct=1.0, risk_reward=2.0,
    )
    strategy_id = lib.create(cfg)
    issue = [i for i in clar_api.build_issues(cfg) if i["id"] == "field:stop_loss"][0]
    option = next(o for o in issue["suggested_options"] if "0.2%" in o["label"])

    req = clar_api.ClarifyRequest(resolutions=[
        clar_api.ClarifyResolution(id=issue["id"], action=option["action"], value=option["value"]),
    ])
    result = clar_api.clarify_strategy(strategy_id, req)
    assert len(result["applied"]) == 1

    resolved = lib.load(strategy_id)
    assert resolved.stop_loss.type == "signal_candle"
    assert resolved.stop_loss.value == 0.2
    assert not any(i["id"] == "field:stop_loss" for i in clar_api.build_issues(resolved))


# ------------------------------------------------------------ Genuine ambiguity #3: risk % per trade

def test_missing_risk_pct_is_a_real_resolvable_issue_not_a_dead_end():
    """Genuine ambiguity #3: the reference document only states the
    RISK:REWARD RATIO (1:2), never how much of the account to risk per
    trade. Real bug found: build_issues() only ever matched validator's
    "Invalid risk %" error text, never "Missing risk %" (which is what
    validator actually raises when risk_pct is None) -- so this fell
    through to the generic, unresolvable "other" catch-all."""
    cfg = StrategyConfig(
        name="Risk Pct Missing Test", raw_text="test", timeframes={"entry": "5m"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30.0)],
        exit_conditions=[], stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.0), risk_pct=None, risk_reward=2.0,
    )
    errors = validate(cfg)
    assert any(e.startswith("Missing risk %") for e in errors)

    issues = clar_api.build_issues(cfg)
    assert not any(i["kind"] == "other" and "risk %" in (i.get("reason") or "").lower() for i in issues)
    risk_issues = [i for i in issues if i["id"] == "field:risk_pct"]
    assert len(risk_issues) == 1
    assert risk_issues[0]["suggested_options"]  # a real, resolvable choice, not a dead end


def test_user_can_resolve_missing_risk_pct_with_a_multiple_choice_option(test_db, tmp_path, monkeypatch):
    from backtest_engine import strategy_library as lib
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))
    cfg = StrategyConfig(
        name="Risk Pct Resolve Test", raw_text="test", timeframes={"entry": "5m"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30.0)],
        exit_conditions=[], stop_loss=SLTPSpec(type="fixed_pct", value=1.0),
        take_profit=SLTPSpec(type="rr", value=2.0), risk_pct=None, risk_reward=2.0,
    )
    strategy_id = lib.create(cfg)
    issue = [i for i in clar_api.build_issues(cfg) if i["id"] == "field:risk_pct"][0]
    option = next(o for o in issue["suggested_options"] if o["label"] == "1.0%")

    req = clar_api.ClarifyRequest(resolutions=[
        clar_api.ClarifyResolution(id=issue["id"], action="set_field", value=option["value"]),
    ])
    result = clar_api.clarify_strategy(strategy_id, req)
    assert len(result["applied"]) == 1
    resolved = lib.load(strategy_id)
    assert resolved.risk_pct == 1.0
