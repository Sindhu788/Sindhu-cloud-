"""Part 1 -- the clarification flow for strategies saved with status
NEEDS_CLARIFICATION. Two endpoints:

GET  /api/backtesting/strategies/{id}/clarification -- explains, in plain
     structured "issues", exactly what's unclear/missing, reusing whatever
     reasoning the AI extraction already generated (strategy_library's
     persisted `clarification` record -- see knowledge_compiler/compiler.py's
     _finalize_and_save_strategy) plus the live validator errors.

POST /api/backtesting/strategies/{id}/clarify -- applies the CEO's answers
     (redescribe a rule as free text and re-parse it, pick a suggested
     value, or drop an unresolved condition), re-validates, saves a new
     version, and -- if the strategy is now READY_FOR_BACKTEST -- triggers
     the same automation pipeline a fresh import would (Part 2/3), so
     resolving a clarification is not a dead end either.

Never guesses: every action here is either something the CEO explicitly
typed/picked, or a straight re-run of the same deterministic parser/
validator every other strategy already goes through.
"""

import difflib
import re
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backtest_engine import strategy_library as lib
from backtest_engine.strategy_config import Condition, SLTPSpec
from backtest_engine.strategy_parser import parse_conditions
from backtest_engine.validator import validate, _KNOWN_INDICATORS, _numeric_bound
from backtest_engine.strategy_safety_check import run_safety_check
from data_engine.logging_setup import log as file_log
from sindhu_web import sync

router = APIRouter()

_BUCKETS = ("entry_conditions", "long_entry_conditions", "short_entry_conditions",
            "exit_conditions", "confirmation_conditions")

_SUPPORTED_VOCAB_HINT = (
    "Supported condition types: indicator comparisons (RSI/EMA/SMA/MACD/ATR/volume vs. a "
    "number), price vs. an indicator (e.g. \"close above EMA50\"), a trading session "
    "(london/ny/asian), or a known market-structure concept (BOS, CHoCH, FVG, order block, "
    "breaker block, liquidity sweep, support/resistance, PDH/PDL). Anything else (e.g. "
    "trendline breaks, chart patterns like head-and-shoulders, Elliott wave, Fibonacci "
    "levels) is not currently executable by the backtest engine."
)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _bucket_label(bucket):
    return bucket.replace("_conditions", "").replace("_", " ")


def _describe_condition(cond):
    if cond.type == "indicator_compare":
        return f"{cond.indicator} {cond.op} {cond.value}"
    if cond.type == "price_compare":
        return f"price {cond.op} {cond.indicator}" + (f"({cond.params.get('period')})" if cond.params.get("period") else "")
    if cond.type == "indicator_vs_indicator":
        p1 = cond.params.get("period") if cond.params else None
        p2 = cond.params2.get("period") if cond.params2 else None
        return f"{cond.indicator}{f'({p1})' if p1 else ''} {cond.op} {cond.indicator2}{f'({p2})' if p2 else ''}"
    if cond.type == "concept":
        return f"{cond.name}" + (f" ({cond.direction})" if cond.direction else "")
    if cond.type == "session":
        return f"{cond.name} session"
    if cond.type == "trend":
        return f"trend {cond.direction}"
    return cond.text or "unrecognized"


def _match_hidden_rule(hidden_rules, needle):
    """Best-effort match of a validator error's quoted text (or bad
    indicator name) against the AI's own per-field reasoning, so the
    clarification UI can show *why the AI itself* flagged this as
    uncertain, not just a generic validator message."""
    if not hidden_rules or not needle:
        return None
    needle_lower = needle.lower()
    for hr in hidden_rules:
        evidence = (hr.get("evidence") or "").lower()
        field = (hr.get("field") or "").lower()
        if evidence and (evidence in needle_lower or needle_lower in evidence):
            return hr
        if field and field in needle_lower:
            return hr
    return None


def _can_reject(cfg, bucket):
    # Confirmation rules are always optional. Exit rules can be dropped as
    # long as either a real stop-loss or another exit condition remains --
    # otherwise the strategy would silently never exit a trade. Entry rules
    # can always be dropped (if it was the only one, "Missing entry rules"
    # simply reappears as a fresh, clearer issue on the next fetch).
    if bucket == "confirmation_conditions":
        return True
    if bucket == "exit_conditions":
        return cfg.stop_loss.type != "unknown" or len(cfg.exit_conditions) > 1
    return True


# Clarification Page (Step 3, Part B): a short, plain-language "why is
# this being asked" and "why it matters" per issue KIND, plus a concrete
# worked example -- keyed by "kind" since the reason text itself already
# varies per specific issue (it names the exact rule text/field). These
# three additions are what turn a bare validator error into a real
# question a non-technical CEO can answer confidently.
_ISSUE_COPY = {
    "raw_condition": {
        "why_asking": "Yeh rule samajh nahi aaya jo aapne likha tha -- system galat guess nahi karna chahta.",
        "why_matters": "Agar yeh rule galat samjha gaya to backtest un cheezon ko test karega jo aapne actually nahi kaha.",
        "example": 'Misaal: "price sweeps below the previous low" -> "liquidity sweep" (bearish) select kar sakte hain.',
    },
    "missing_conditions": {
        "why_asking": "Bina entry/exit rule ke strategy kabhi trade hi nahi karegi.",
        "why_matters": "Yeh strategy ka sabse bunyadi hissa hai -- iske bina backtest chalega hi nahi.",
        "example": 'Misaal: "buy when price closes above the 50 EMA".',
    },
    "invalid_indicator": {
        "why_asking": "Aapne jo naam likha woh SINDHU ki known list mein nahi hai.",
        "why_matters": "Galat indicator select hone se strategy kuch aur hi test karegi.",
        "example": "Misaal: agar aapne \"volume profile POC\" likha ho, to \"poc\" concept select karein.",
    },
    "missing_field": {
        "why_asking": "Yeh number/setting text mein clearly nahi mila.",
        "why_matters": "Risk aur stop-loss settings trading capital ki safety ke liye zaroori hain.",
        "example": "Misaal: \"risk 1% per trade\" ya \"stop 2x ATR\".",
    },
    "other": {
        "why_asking": "System ko is cheez mein confidence nahi hai.",
        "why_matters": "Bina resolve kiye yeh strategy backtest ke liye ready nahi hogi.",
        "example": None,
    },
    "contradiction": {
        "why_asking": "Do rules ek dusre se ulat hain -- dono ek sath kabhi sach nahi ho sakte.",
        "why_matters": "Agar yeh contradiction resolve nahi hui, to strategy ka yeh hissa kabhi trigger hi nahi hoga.",
        "example": 'Misaal: "RSI 30 se neeche" aur "RSI 70 se upar" dono ek waqt mein zaroori nahi ho sakte.',
    },
    "quality_filter_threshold": {
        "why_asking": "Document mein ek quality check ka zikr hai (jaise 'strong candles'), lekin exact number nahi diya gaya.",
        "why_matters": "Bina exact number ke yeh filter backtest mein apply nahi ho sakta.",
        "example": 'Misaal: "strong candles" ka matlab ho sakta hai candle body kam se kam 50% ya 70% honi chahiye.',
    },
}


def _issue_copy(kind):
    return _ISSUE_COPY.get(kind, _ISSUE_COPY["other"])


def _find_impossible_combination_issues(cfg):
    """Item 3 (Contradiction Detection) -- surfaces genuinely-impossible
    AND-gates (the same indicator required above AND below overlapping
    thresholds on the same bar, e.g. "RSI < 30" and "RSI > 70" both
    required together) as first-class, ACTIONABLE Clarification issues.

    This is the exact numeric-bound conflict validator.validate() already
    detects (reused here, never reimplemented) -- but until now it only
    ever reached the Clarification Page as an inert "other" issue with no
    way to resolve it (can_reject=False, no suggested_options). It is
    deliberately never auto-picked by self_correction.py's own repair
    (see self_correction._repair_contradictory_entry_gate's docstring: a
    conflict with no structural direction signal "is deliberately left
    for Level 2 rather than guessed at here") -- there is no safe default
    side to keep, so the user must choose which rule to remove."""
    issues = []
    seen_pairs = set()
    gates = [
        ("entry_conditions", "confirmation_conditions"),
        ("long_entry_conditions", "confirmation_conditions"),
        ("short_entry_conditions", "confirmation_conditions"),
    ]
    for b1_name, b2_name in gates:
        b1, b2 = getattr(cfg, b1_name), getattr(cfg, b2_name)
        if not b1:
            continue
        combined = [(b1_name, i, c) for i, c in enumerate(b1)] + [(b2_name, i, c) for i, c in enumerate(b2)]
        by_key = {}
        for bucket_name, idx, cond in combined:
            bound = _numeric_bound(cond)
            if bound is None:
                continue
            key = (cond.indicator, tuple(sorted((cond.params or {}).items())))
            by_key.setdefault(key, []).append((bound, bucket_name, idx, cond))
        for (indicator, _params), items in by_key.items():
            lowers = [t for t in items if t[0][0] == "lower"]
            uppers = [t for t in items if t[0][0] == "upper"]
            if not lowers or not uppers:
                continue
            lower_bound, lower_bucket, lower_idx, lower_cond = max(lowers, key=lambda t: t[0][1])
            upper_bound, upper_bucket, upper_idx, upper_cond = min(uppers, key=lambda t: t[0][1])
            if lower_bound[1] < upper_bound[1]:
                continue  # not actually a conflict -- there's a valid range between them
            pair_key = tuple(sorted([(lower_bucket, lower_idx), (upper_bucket, upper_idx)]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            lower_label = f"{indicator} {lower_cond.op} {lower_cond.value}"
            upper_label = f"{indicator} {upper_cond.op} {upper_cond.value}"
            issues.append({
                "id": f"contradiction:{lower_bucket}:{lower_idx}:{upper_bucket}:{upper_idx}",
                "kind": "contradiction",
                "reason": (
                    f'"{lower_label}" and "{upper_label}" are both required at the same time, but '
                    f"{indicator} can never satisfy both on the same bar -- this part of the strategy "
                    f"can never trigger as written."
                ),
                "detail": "Pick which of the two conflicting rules to keep; the other one gets removed.",
                "original_text": None, "ai_reason": None, "ai_confidence": None,
                "suggested_options": [
                    {"label": f'Keep "{upper_label}", remove "{lower_label}"',
                     "action": "remove_condition", "value": {"bucket": lower_bucket, "index": lower_idx}},
                    {"label": f'Keep "{lower_label}", remove "{upper_label}"',
                     "action": "remove_condition", "value": {"bucket": upper_bucket, "index": upper_idx}},
                ],
                "can_reject": False,
            })
    return issues


def _find_unspecified_quality_filter_issues(cfg):
    """Two-Focused-Day Push, Part 1+2 -- a candle_body_pct condition with
    no min_pct is a GENUINE ambiguity (e.g. "a valid sweep should occur
    with strong candles" -- the rule clearly exists, only the exact
    threshold isn't quantified in the source text), surfaced with real
    multiple-choice options instead of being silently dropped as
    commentary or stuck as an unresolvable dead end."""
    issues = []
    for bucket_name in _BUCKETS:
        bucket = getattr(cfg, bucket_name, None)
        if not bucket:
            continue
        for idx, cond in enumerate(bucket):
            if cond.type != "candle_body_pct" or cond.params.get("min_pct") is not None:
                continue
            issues.append({
                "id": f"quality_filter:{bucket_name}:{idx}",
                "kind": "quality_filter_threshold",
                "reason": (
                    "A candle-strength quality check was found (\"strong candles\" / avoid small or "
                    "Doji candles), but the source text doesn't give an exact percentage."
                ),
                "detail": "Pick how strict this filter should be, or define your own threshold below.",
                "original_text": None, "ai_reason": None, "ai_confidence": None,
                "suggested_options": [
                    {"label": "Candle body must be at least 50% of its full range",
                     "action": "set_quality_filter_threshold",
                     "value": {"bucket": bucket_name, "index": idx, "min_pct": 50.0}},
                    {"label": "Candle body must be at least 70% of its full range",
                     "action": "set_quality_filter_threshold",
                     "value": {"bucket": bucket_name, "index": idx, "min_pct": 70.0}},
                    {"label": "No strict rule -- treat as a soft/manual judgment filter (not enforced)",
                     "action": "remove_condition", "value": {"bucket": bucket_name, "index": idx}},
                ],
                "can_reject": True,
            })
    return issues


def _find_unspecified_stop_loss_buffer_issue(cfg):
    """Two-Focused-Day Push, Part 1+2 -- stop_loss.type="signal_candle"
    with no value is the second genuine ambiguity from the reference
    document ("leave a small margin (buffer) beyond the exact high or
    low" -- the STRUCTURE of the stop [signal_candle: the sweep's own
    high/low] is completely clear, only the buffer % isn't quantified).
    Without this, _compute_stop_loss silently defaults to a ZERO buffer
    (spec.value or 0.0), running the strategy on an assumption the CEO was
    never told about."""
    spec = cfg.stop_loss
    if spec.type != "signal_candle" or spec.value is not None:
        return []
    return [{
        "id": "field:stop_loss", "kind": "quality_filter_threshold",
        "reason": (
            "The stop-loss is placed at the sweep's own high/low with a buffer beyond it, but the "
            "source text doesn't give an exact buffer size."
        ),
        "detail": "Pick a buffer size, or define your own below.",
        "original_text": None, "ai_reason": None, "ai_confidence": None,
        "suggested_options": [
            {"label": "0.1% buffer beyond the level", "action": "set_field",
             "value": {"type": "signal_candle", "value": 0.1}},
            {"label": "0.2% buffer beyond the level", "action": "set_field",
             "value": {"type": "signal_candle", "value": 0.2}},
            {"label": "0.5% buffer beyond the level", "action": "set_field",
             "value": {"type": "signal_candle", "value": 0.5}},
            {"label": "No buffer -- exact level", "action": "set_field",
             "value": {"type": "signal_candle", "value": 0.0}},
        ],
        "can_reject": False,
    }]


def _safety_check_issues(cfg, claimed_reason_prefixes):
    """The remaining Automatic Strategy Safety Check findings (duplicate
    exit clauses, an exit gate with no realistic room, bare pdh+pdl,
    unreachable dead entry buckets) -- these are ALSO genuine
    contradictions/logic conflicts, but self_correction.py's Level 1
    auto_repair already fixes all four of them deterministically for
    every strategy that goes through the AI import pipeline (see
    self_correction.auto_repair). They only reach here for strategies
    saved through a path that skips that repair (Strategy Wizard, a raw
    paste, or an older library entry) -- read-only visibility (Item 3
    requires them surfaced, not silently hidden) rather than a one-click
    fix, since a safe generic repair already lives in self_correction.py
    and duplicating it here would be a second implementation of the same
    logic."""
    result = run_safety_check(cfg)
    issues = []
    for i, reason in enumerate(result["reasons"]):
        if any(reason.startswith(p) for p in claimed_reason_prefixes):
            continue  # already surfaced as an actionable contradiction issue above
        issues.append({
            "id": f"safety:{i}", "kind": "contradiction", "reason": reason,
            "detail": "This was found by SINDHU's automatic Strategy Safety Check.",
            "original_text": None, "ai_reason": None, "ai_confidence": None,
            "suggested_options": None, "can_reject": False,
        })
    return issues


def build_issues(cfg, hidden_rules=None):
    """Turns validate(cfg)'s flat error strings into structured, actionable
    issues. One issue per distinct problem, each carrying enough shape for
    the frontend to render the right control (free-text redescribe, a
    small set of suggested options, or a reject button) without any
    string-parsing on the client side. Also carries a why_asking/
    why_matters/example triple (Clarification Page features 6 and 9) so
    the frontend never needs its own per-kind copy."""
    errors = validate(cfg)
    issues = []
    claimed = set()

    def _unclaimed_raw_index(bucket, text):
        for idx, cond in enumerate(getattr(cfg, bucket)):
            if cond.type == "raw" and cond.text == text and (bucket, idx) not in claimed:
                return idx
        return None

    # validator.py's "Unclear entry rule" message is the SAME wording
    # regardless of which of the three entry buckets the condition actually
    # lives in (entry_conditions vs. long/short_entry_conditions -- Batch 6's
    # per-direction rule sets), so which bucket to search in isn't in the
    # error text itself. Try all three real entry buckets in order rather
    # than assuming "entry" always means the generic entry_conditions list
    # -- a mixed long/short document (which routes into long_entry_conditions/
    # short_entry_conditions, leaving entry_conditions empty) would otherwise
    # have every one of its unclear rules silently never surfaced as a
    # fixable clarification issue.
    _SECTION_TO_BUCKETS = {
        "entry": ("entry_conditions", "long_entry_conditions", "short_entry_conditions"),
        "exit": ("exit_conditions",),
    }

    def _find_unclaimed_raw(section, text):
        for bucket in _SECTION_TO_BUCKETS[section]:
            idx = _unclaimed_raw_index(bucket, text)
            if idx is not None:
                return bucket, idx
        return None, None

    def _unclaimed_invalid_index(bucket, bad_name):
        for idx, cond in enumerate(getattr(cfg, bucket)):
            if (bucket, idx) in claimed:
                continue
            if cond.type == "indicator_compare" and cond.indicator == bad_name and cond.indicator not in _KNOWN_INDICATORS:
                return idx
            if cond.type == "concept" and cond.name == bad_name and cond.name not in _KNOWN_INDICATORS:
                return idx
        return None

    for err in errors:
        if err.startswith("Impossible combination"):
            continue  # handled below by _find_impossible_combination_issues -- actionable, not a dead-end

        m = re.match(r'^Unclear (entry|exit) rule, needs clarification: "(.*)"$', err)
        if m:
            section, text = m.group(1), m.group(2)
            bucket, idx = _find_unclaimed_raw(section, text)
            if idx is None:
                continue
            claimed.add((bucket, idx))
            hr = _match_hidden_rule(hidden_rules, text)
            issues.append({
                "id": f"{bucket}:{idx}", "kind": "raw_condition", "section": bucket, "index": idx,
                "reason": f'The {section} rule "{text}" could not be matched to a supported condition type.',
                "detail": _SUPPORTED_VOCAB_HINT,
                "original_text": text,
                "ai_reason": hr.get("reason") if hr else None,
                "ai_confidence": hr.get("confidence") if hr else None,
                "suggested_options": None,
                "can_reject": _can_reject(cfg, bucket),
            })
            continue

        if err.startswith("Missing entry rules"):
            issues.append({
                "id": "entry_conditions:new", "kind": "missing_conditions", "section": "entry_conditions", "index": None,
                "reason": "No entry rule was detected at all.",
                "detail": "Describe when this strategy should enter a trade. " + _SUPPORTED_VOCAB_HINT,
                "original_text": None, "ai_reason": None, "ai_confidence": None,
                "suggested_options": None, "can_reject": False,
            })
            continue

        if err.startswith("Missing exit rules"):
            issues.append({
                "id": "exit_conditions:new", "kind": "missing_conditions", "section": "exit_conditions", "index": None,
                "reason": "No exit rule or stop-loss was detected.",
                "detail": "Describe when this strategy should exit, or set a stop-loss below. " + _SUPPORTED_VOCAB_HINT,
                "original_text": None, "ai_reason": None, "ai_confidence": None,
                "suggested_options": None, "can_reject": False,
            })
            continue

        if err.startswith("Missing entry timeframe"):
            issues.append({
                "id": "field:entry_timeframe", "kind": "missing_field", "field": "entry_timeframe",
                "reason": "No entry timeframe was detected.",
                "detail": "Which timeframe should entries be evaluated on?",
                "suggested_options": [{"label": tf, "value": tf} for tf in ("5m", "15m", "1h", "4h", "1d")],
                "can_reject": False,
            })
            continue

        if err.startswith("Missing stop loss"):
            issues.append({
                "id": "field:stop_loss", "kind": "missing_field", "field": "stop_loss",
                "reason": "No stop-loss could be determined or borrowed from a similar strategy.",
                "detail": "A stop-loss is safety-critical -- pick a method below, or type a custom %.",
                "suggested_options": [
                    {"label": "Fixed 1%", "value": {"type": "fixed_pct", "value": 1.0}},
                    {"label": "Fixed 2%", "value": {"type": "fixed_pct", "value": 2.0}},
                    {"label": "Fixed 3%", "value": {"type": "fixed_pct", "value": 3.0}},
                    {"label": "1.5x ATR", "value": {"type": "atr_multiple", "value": 1.5}},
                    {"label": "2x ATR", "value": {"type": "atr_multiple", "value": 2.0}},
                ],
                "can_reject": False,
            })
            continue

        m = re.match(r"^Invalid indicator(?:/concept)? in ([\w ]+): '(.+)'$", err)
        if m:
            bucket_label, bad_name = m.group(1), m.group(2)
            bucket = bucket_label.replace(" ", "_")
            idx = _unclaimed_invalid_index(bucket, bad_name)
            if idx is None:
                continue
            claimed.add((bucket, idx))
            suggestions = difflib.get_close_matches(bad_name, sorted(_KNOWN_INDICATORS), n=3, cutoff=0.4)
            issues.append({
                "id": f"{bucket}:{idx}", "kind": "invalid_indicator", "section": bucket, "index": idx,
                "reason": f"'{bad_name}' is not a supported indicator or concept.",
                "detail": "Pick a close match below, or redescribe the whole condition as free text.",
                "original_text": bad_name,
                "ai_reason": None, "ai_confidence": None,
                "suggested_options": [{"label": s, "value": s} for s in suggestions] or None,
                "can_reject": _can_reject(cfg, bucket),
            })
            continue

        if err.startswith("Invalid risk:reward ratio"):
            issues.append({
                "id": "field:risk_reward", "kind": "missing_field", "field": "risk_reward",
                "reason": err, "detail": "Pick a risk:reward ratio.",
                "suggested_options": [{"label": f"{v}:1", "value": v} for v in (1.5, 2.0, 2.5, 3.0)],
                "can_reject": False,
            })
            continue

        if err.startswith("Invalid risk %") or err.startswith("Missing risk %"):
            # Two-Focused-Day Push, Part 1: genuine ambiguity #3 -- a
            # document that only states the RISK:REWARD RATIO (e.g. "1:2")
            # but never says how much of the account to risk per trade
            # previously fell through this exact branch's own "Invalid"
            # prefix check (missing was never checked at all) into the
            # generic, unresolvable "other" dead end.
            issues.append({
                "id": "field:risk_pct", "kind": "missing_field", "field": "risk_pct",
                "reason": err, "detail": "Pick a risk % per trade.",
                "suggested_options": [{"label": f"{v}%", "value": v} for v in (0.5, 1.0, 1.5, 2.0)],
                "can_reject": False,
            })
            continue

        # Anything not specifically classified above is still surfaced,
        # read-only, so nothing the validator flags is ever silently hidden.
        issues.append({
            "id": f"other:{len(issues)}", "kind": "other", "reason": err, "detail": None,
            "suggested_options": None, "can_reject": False,
        })

    issues += _find_impossible_combination_issues(cfg)
    issues += _find_unspecified_quality_filter_issues(cfg)
    issues += _find_unspecified_stop_loss_buffer_issue(cfg)
    issues += _safety_check_issues(cfg, claimed_reason_prefixes=("Impossible combination",))

    for issue in issues:
        copy = _issue_copy(issue.get("kind"))
        issue.setdefault("why_asking", copy["why_asking"])
        issue.setdefault("why_matters", copy["why_matters"])
        issue.setdefault("example", copy["example"])
    return issues


def ambiguity_overview(confidence_pct, issues):
    """Item 8 -- a deterministic, at-a-glance breakdown of an imported
    strategy into confidently-understood vs uncertain vs unresolved, built
    purely from data the pipeline already computed (confidence_pct from the
    AI's own extraction pass, plus the same `issues` list the Clarification
    Center already shows). No new AI call, no new score invented -- this
    only re-buckets existing numbers for a simpler visual.

    "uncertain" = an issue the system could still make a specific guess
    about (suggested_options present, or the AI attached its own
    ai_confidence >= 50 to the underlying hidden rule) -- these are things
    a one-click answer can likely resolve.
    "unresolved" = an issue with no suggestion at all (raw free-text
    condition, missing field, unmapped indicator) -- these genuinely need
    the user's own input."""
    uncertain, unresolved = 0, 0
    for issue in issues:
        has_suggestion = bool(issue.get("suggested_options"))
        ai_conf = issue.get("ai_confidence")
        if has_suggestion or (ai_conf is not None and ai_conf >= 50):
            uncertain += 1
        else:
            unresolved += 1

    pct = confidence_pct if confidence_pct is not None else (100.0 if not issues else 0.0)
    if pct >= 70 and unresolved == 0:
        status = "good"
    elif unresolved > 0 or pct < 40:
        status = "attention"
    else:
        status = "warning"

    return {
        "confidence_pct": round(pct, 1) if pct is not None else None,
        "uncertain_count": uncertain,
        "unresolved_count": unresolved,
        "status": status,
    }


def _apply_resolution(cfg, resolution_id, action, text, value, strategy_id=None):
    kind, _, rest = resolution_id.partition(":")

    if action == "reject":
        if kind not in _BUCKETS:
            return False, "This issue can't be rejected."
        bucket = getattr(cfg, kind)
        idx = int(rest)
        if idx >= len(bucket):
            return False, "That condition no longer exists (already resolved)."
        removed = bucket.pop(idx)
        return True, f'Removed the unresolved {_bucket_label(kind)} rule: "{_describe_condition(removed)}"'

    if action == "mark_manual_review":
        # The one-click suggested default: accept the rule as-is, deferred
        # for later human review, instead of guessing a structured meaning
        # for it or silently deleting it. Resolves the clarification (the
        # condition stops being an "unclear rule" validator error -- see
        # Condition.is_unclear()), but the strategy still can't actually
        # backtest until a human resolves it for real: the SAME
        # manual-review run-time gate the Strategy Wizard's "Other/bilkul
        # naya" path uses (wizard.has_manual_review, enforced in
        # sindhu_web/api/backtesting.py's run endpoint) blocks it there.
        if kind in _BUCKETS and rest == "new":
            return False, "Nothing to mark -- there's no specific rule text for a missing-condition issue yet. Type something first."
        if kind not in _BUCKETS:
            return False, "This issue can't be marked for manual review."
        bucket = getattr(cfg, kind)
        idx = int(rest)
        if idx >= len(bucket):
            return False, "That condition no longer exists (already resolved)."
        cond = bucket[idx]
        if cond.type != "raw":
            return False, "Only an unrecognized (raw) rule can be marked for manual review."
        cond.manual_review = True
        cond.raw_source = cond.text
        return True, f'Marked for Manual Review: "{cond.text}" -- kept exactly as written, excluded from live execution until resolved.'

    if action == "set_quality_filter_threshold":
        # Two-Focused-Day Push, Part 2: resolves a candle_body_pct
        # condition whose min_pct was left unspecified (a genuine
        # ambiguity, not a dead end) by filling in the chosen threshold --
        # goes through the exact same bucket+index mutation + save/
        # validate path as every other resolution, no shortcut.
        if not isinstance(value, dict) or "bucket" not in value or "index" not in value:
            return False, "No quality filter was specified."
        target_bucket, target_idx, min_pct = value["bucket"], value["index"], value.get("min_pct")
        if target_bucket not in _BUCKETS:
            return False, "Unknown bucket for this condition."
        bucket = getattr(cfg, target_bucket)
        if target_idx >= len(bucket):
            return False, "That condition no longer exists (already resolved)."
        cond = bucket[target_idx]
        if cond.type != "candle_body_pct":
            return False, "This condition is not a candle-quality filter."
        if min_pct is None:
            return False, "No threshold percentage was provided."
        cond.params = {"min_pct": float(min_pct)}
        return True, f"Candle-quality filter set to at least {min_pct}% body."

    if action == "remove_condition":
        # Item 3 (Contradiction Detection): resolves an impossible-combination
        # issue by removing whichever of the two conflicting conditions the
        # user chose to drop. Same mechanics as "reject" (pop by bucket+index)
        # but driven by the option's own {bucket, index} value rather than the
        # resolution id, since one contradiction issue offers two different
        # removal targets from a single card.
        if not isinstance(value, dict) or "bucket" not in value or "index" not in value:
            return False, "No condition was specified to remove."
        target_bucket, target_idx = value["bucket"], value["index"]
        if target_bucket not in _BUCKETS:
            return False, "Unknown bucket for this condition."
        bucket = getattr(cfg, target_bucket)
        if target_idx >= len(bucket):
            return False, "That condition no longer exists (already resolved)."
        removed = bucket.pop(target_idx)
        return True, f'Removed the conflicting {_bucket_label(target_bucket)} rule: "{_describe_condition(removed)}"'

    if action == "unmark_manual_review":
        # Clarification Page feature 8 (edit a previously-given answer):
        # the one-click "Manual Review" default is the most common answer
        # given, so this is the concrete, bounded "undo" this task ships --
        # reopens a manual_review condition as an unresolved raw rule again
        # so it re-appears in build_issues() to be answered differently.
        if kind not in _BUCKETS:
            return False, "This issue can't be reopened."
        bucket = getattr(cfg, kind)
        idx = int(rest)
        if idx >= len(bucket):
            return False, "That condition no longer exists."
        cond = bucket[idx]
        if not cond.manual_review:
            return False, "This rule wasn't marked Manual Review."
        cond.manual_review = False
        return True, f'Reopened for a fresh answer: "{cond.text}"'

    if action == "edit":
        if not text or not text.strip():
            return False, "No replacement text was provided."
        new_conditions = parse_conditions(text)
        still_raw = [c for c in new_conditions if c.type == "raw"]

        if kind in _BUCKETS and rest == "new":
            bucket = getattr(cfg, kind)
            bucket.extend(new_conditions)
            if still_raw:
                return False, f'Still couldn\'t understand "{still_raw[0].text}". {_SUPPORTED_VOCAB_HINT}'
            return True, f"Added {len(new_conditions)} {_bucket_label(kind)} rule(s): " + ", ".join(_describe_condition(c) for c in new_conditions)

        if kind in _BUCKETS:
            bucket = getattr(cfg, kind)
            idx = int(rest)
            if idx >= len(bucket):
                return False, "That condition no longer exists (already resolved)."
            if not still_raw:
                bucket[idx:idx + 1] = new_conditions
                return True, "Understood as: " + ", ".join(_describe_condition(c) for c in new_conditions)
            # Keep it visible (with the newly-typed text) instead of silently
            # discarding the CEO's attempt -- the next GET will show it as
            # still unresolved, with the same honest explanation.
            bucket[idx] = Condition(type="raw", text=text.strip())
            return False, f'Still couldn\'t understand "{text.strip()}". {_SUPPORTED_VOCAB_HINT}'

        return False, "Unknown issue id."

    if action == "set_field":
        if kind != "field":
            return False, "Unknown field issue id."
        field = rest

        def _learn(v):
            # Item 10: only ever logs the 3 eligible, text-free fields
            # (correction_learning itself ignores anything else) -- a real
            # human choice, recorded so a genuinely repeated pattern can
            # eventually be recognized as unambiguous.
            if strategy_id:
                from ai_integration import correction_learning
                correction_learning.record_resolution(field, v, strategy_id)

        if field == "entry_timeframe":
            if not value:
                return False, "No timeframe provided."
            cfg.timeframes["entry"] = str(value)
            _learn(str(value))
            return True, f"Entry timeframe set to {value}."
        if field == "stop_loss":
            v = value or {}
            sl_type = v.get("type", "fixed_pct")
            sl_value = v.get("value")
            if sl_value is None:
                return False, "No stop-loss value provided."
            cfg.stop_loss = SLTPSpec(type=sl_type, value=float(sl_value))
            return True, f"Stop loss set to {sl_type} ({sl_value})."
        if field == "risk_reward":
            if value is None:
                return False, "No risk:reward value provided."
            cfg.risk_reward = float(value)
            if cfg.take_profit.type in ("unknown", "rr"):
                cfg.take_profit = SLTPSpec(type="rr", value=cfg.risk_reward)
            _learn(cfg.risk_reward)
            return True, f"Risk:reward set to {cfg.risk_reward}:1."
        if field == "risk_pct":
            if value is None:
                return False, "No risk % value provided."
            cfg.risk_pct = float(value)
            _learn(cfg.risk_pct)
            return True, f"Risk % set to {cfg.risk_pct}."
        return False, f"Unknown field '{field}'."

    if action == "replace_indicator":
        if kind not in _BUCKETS:
            return False, "Unknown issue id."
        bucket = getattr(cfg, kind)
        idx = int(rest)
        if idx >= len(bucket):
            return False, "That condition no longer exists (already resolved)."
        cond = bucket[idx]
        new_name = str(value)
        old_name = cond.indicator if cond.type == "indicator_compare" else cond.name if cond.type == "concept" else None
        if cond.type == "indicator_compare":
            cond.indicator = new_name
        elif cond.type == "concept":
            cond.name = new_name
        else:
            return False, "This condition type can't be fixed this way."
        # Item 4 (Terminology Learning): the user just taught the system
        # what an unrecognized name means -- save it so the SAME name is
        # auto-resolved (see self_correction._repair_known_term_aliases)
        # rather than re-asked about on a future import.
        if old_name:
            from ai_integration import dictionary_builder
            dictionary_builder.save_learned_alias(old_name, new_name)
        return True, f"Changed to '{new_name}'."

    return False, f"Unknown action '{action}'."


class ClarifyResolution(BaseModel):
    id: str
    action: str  # "edit" | "set_field" | "reject" | "replace_indicator" | "mark_manual_review" | "unmark_manual_review" | "remove_condition"
    text: Optional[str] = None
    value: Any = None


class ClarifyRequest(BaseModel):
    resolutions: List[ClarifyResolution]


class ClarifyPreviewRequest(BaseModel):
    id: str
    text: str


@router.get("/api/backtesting/strategies/{strategy_id}/clarification")
def get_clarification(strategy_id: str):
    try:
        cfg = lib.load(strategy_id)
    except FileNotFoundError:
        raise HTTPException(404, "strategy not found")

    stored = lib.get_clarification(strategy_id) or {}
    errors = validate(cfg)
    issues = build_issues(cfg, stored.get("hidden_rules"))
    return {
        "strategy_id": strategy_id, "name": cfg.name,
        "status": "READY_FOR_BACKTEST" if not errors else "NEEDS_CLARIFICATION",
        "errors": errors, "issues": issues,
        "hidden_rules": stored.get("hidden_rules") or [],
        "confidence_pct": stored.get("confidence_pct"),
        "ambiguity_overview": ambiguity_overview(stored.get("confidence_pct"), issues),
        "raw_text": cfg.raw_text,
        "answer_log": stored.get("answer_log") or [],
    }


@router.post("/api/backtesting/strategies/{strategy_id}/clarify")
def clarify_strategy(strategy_id: str, req: ClarifyRequest):
    try:
        cfg = lib.load(strategy_id)
    except FileNotFoundError:
        raise HTTPException(404, "strategy not found")

    applied, failed = [], []
    for r in req.resolutions:
        try:
            ok, detail = _apply_resolution(cfg, r.id, r.action, r.text, r.value, strategy_id=strategy_id)
            (applied if ok else failed).append({"id": r.id, "detail": detail})
        except Exception as exc:
            failed.append({"id": r.id, "detail": str(exc)})

    lib.save_version(strategy_id, cfg, reason="Clarification applied")

    errors = validate(cfg)
    status = "READY_FOR_BACKTEST" if not errors else "NEEDS_CLARIFICATION"
    stored = lib.get_clarification(strategy_id) or {}
    issues = build_issues(cfg, stored.get("hidden_rules"))

    if status == "NEEDS_CLARIFICATION":
        # Clarification Page feature 8 (edit a previously-given answer):
        # every successful resolution this round is appended to a running
        # log so the page can show "you already answered this" and offer
        # unmark_manual_review to reopen it. Only kept while the strategy
        # is still NEEDS_CLARIFICATION -- once fully resolved the record
        # is cleared exactly as before this feature (unchanged behavior).
        answer_log = list(stored.get("answer_log") or [])
        now = _now_iso()
        applied_ids = {a["id"] for a in applied}
        for r in req.resolutions:
            if r.id in applied_ids:
                detail = next(a["detail"] for a in applied if a["id"] == r.id)
                answer_log.append({
                    "id": r.id, "action": r.action, "text": r.text, "value": r.value,
                    "detail": detail, "at": now,
                })
        lib.set_clarification(strategy_id, {
            "notes": errors, "hidden_rules": stored.get("hidden_rules") or [],
            "confidence_pct": stored.get("confidence_pct"), "updated_at": now,
            "answer_log": answer_log,
        })
    else:
        lib.set_clarification(strategy_id, None)

    pipeline_job_id = None
    if status == "READY_FOR_BACKTEST":
        try:
            from automation_pipeline.pipeline import trigger_pipeline_for_strategy
            pipeline_job_id = trigger_pipeline_for_strategy(strategy_id, cfg.name)
        except Exception as exc:
            file_log(f"[clarification] Failed to auto-trigger pipeline for '{cfg.name}' ({strategy_id}): {exc!r}")

    sync.notify("strategy", "updated", f"Clarification applied to '{cfg.name}'", id=strategy_id)
    return {
        "status": status, "applied": applied, "failed": failed,
        "remaining_issues": issues, "pipeline_job_id": pipeline_job_id,
    }


class ReextractFieldRequest(BaseModel):
    field: str


@router.post("/api/backtesting/strategies/{strategy_id}/reextract-field")
def reextract_field(strategy_id: str, req: ReextractFieldRequest):
    """Item 5 (Partial Re-Extraction): redo ONE field of an already-saved
    strategy straight from its own original source text, without re-running
    the whole document through the AI import pipeline. Every other field is
    provably untouched -- self_correction.partial_reextract only ever
    assigns the single requested attribute. Saves a new version on success
    (Item 6), so the previous value of the field is never lost."""
    from ai_integration import self_correction

    try:
        cfg = lib.load(strategy_id)
    except FileNotFoundError:
        raise HTTPException(404, "strategy not found")

    if req.field not in self_correction.PARTIAL_REEXTRACT_FIELDS:
        raise HTTPException(400, f"'{req.field}' is not a re-extractable field.")

    before_snapshot = cfg.to_dict()
    ok, note = self_correction.partial_reextract(cfg, req.field)
    if not ok:
        return {"success": False, "note": note, "field": req.field}

    self_correction.auto_repair(cfg)
    new_version = lib.save_version(strategy_id, cfg, reason=f"Re-extracted '{req.field}'")

    unchanged_fields = [
        k for k in before_snapshot
        if k != req.field and before_snapshot[k] != cfg.to_dict().get(k)
    ]
    sync.notify("strategy", "updated", f"'{req.field}' re-extracted for '{cfg.name}'", id=strategy_id)
    return {
        "success": True, "note": note, "field": req.field, "new_version": new_version,
        "unexpectedly_changed_fields": unchanged_fields,  # should always be empty -- surfaced for transparency
    }


@router.post("/api/backtesting/strategies/{strategy_id}/clarify/preview")
def preview_clarification_answer(strategy_id: str, req: ClarifyPreviewRequest):
    """Clarification Page feature 7 (CRITICAL SAFETY FEATURE): before any
    free-text answer is actually saved, this echoes back exactly how the
    SAME parser (parse_conditions) understood it -- read-only, mutates
    nothing. The frontend must show this and get an explicit second
    confirmation click before calling POST .../clarify for real. Free
    text is never silently accepted as understood."""
    try:
        cfg = lib.load(strategy_id)
    except FileNotFoundError:
        raise HTTPException(404, "strategy not found")
    if not req.text or not req.text.strip():
        return {"understood_as": None, "still_unclear": True, "conditions": []}
    parsed = parse_conditions(req.text)
    still_unclear = any(c.type == "raw" for c in parsed)
    return {
        "understood_as": ", ".join(_describe_condition(c) for c in parsed) if parsed else None,
        "still_unclear": still_unclear,
        "conditions": [{"type": c.type, "description": _describe_condition(c)} for c in parsed],
    }


@router.get("/api/backtesting/clarification/all")
def get_all_pending_clarifications():
    """Clarification Page feature 5: every strategy's pending questions in
    one grouped list -- loops the same build_issues() used per-strategy,
    over every strategy currently NEEDS_CLARIFICATION. Read-only, cheap
    (in-memory validate() per strategy, no AI calls)."""
    groups = []
    total_issues = 0
    for meta in lib.list_all():
        strategy_id = meta["id"]
        try:
            cfg = lib.load(strategy_id)
        except FileNotFoundError:
            continue
        errors = validate(cfg)
        if not errors:
            continue
        stored = lib.get_clarification(strategy_id) or {}
        issues = build_issues(cfg, stored.get("hidden_rules"))
        if not issues:
            continue
        total_issues += len(issues)
        groups.append({
            "strategy_id": strategy_id, "name": cfg.name,
            "issue_count": len(issues), "issues": issues,
            "ambiguity_overview": ambiguity_overview(stored.get("confidence_pct"), issues),
        })
    return {"groups": groups, "strategy_count": len(groups), "total_issues": total_issues}


def _read_mode_summary(cfg, errors):
    """Clarification Page feature 10 (Read Mode): the ENTIRE strategy as a
    plain, conversational Roman Urdu summary -- one section per structural
    part, no internal identifiers exposed (a concept name like "order_block"
    becomes readable Roman Urdu text, never shown raw). Each section is
    independently editable from the frontend (a section id it can route
    an Edit click back to a specific clarification issue or condition)."""
    def conds_text(conds):
        if not conds:
            return "Koi rule nahi mila."
        return "; ".join(_describe_condition(c) for c in conds)

    sections = []
    entry_conds = cfg.entry_conditions or cfg.long_entry_conditions or cfg.short_entry_conditions
    if cfg.entry_rule_groups:
        entry_text = " | ".join(
            f'{g.get("label", "Setup")}: {conds_text(g.get("conditions") or [])}' for g in cfg.entry_rule_groups
        )
    elif cfg.long_entry_conditions or cfg.short_entry_conditions:
        entry_text = (
            f"Long (buy) mein: {conds_text(cfg.long_entry_conditions)}. "
            f"Short (sell) mein: {conds_text(cfg.short_entry_conditions)}."
        )
    else:
        entry_text = conds_text(entry_conds)
    sections.append({"id": "entry", "title": "Entry -- Trade Kab Shuru Hogi", "text": entry_text})

    sections.append({"id": "exit", "title": "Exit -- Trade Kab Band Hogi", "text": conds_text(cfg.exit_conditions)})

    sl = cfg.stop_loss
    if sl.type == "unknown":
        sl_text = "Stop-loss set nahi hai -- yeh risky hai."
    elif sl.type == "fixed_pct":
        sl_text = f"Entry se {sl.value}% neeche/upar stop-loss."
    elif sl.type == "atr_multiple":
        sl_text = f"ATR ka {sl.value}x stop-loss distance ke taur par."
    elif sl.type == "structure":
        sl_text = "Market structure (order block/FVG/support-resistance) ke hisaab se stop-loss."
    else:
        sl_text = f"Stop-loss type: {sl.type}."
    tp = cfg.take_profit
    if tp.type == "unknown":
        tp_text = "Take-profit set nahi hai."
    elif tp.type == "rr":
        tp_text = f"Risk ka {tp.value}x target (Risk:Reward {tp.value}:1)."
    elif tp.type == "fixed_pct":
        tp_text = f"Entry se {tp.value}% door target."
    else:
        tp_text = f"Take-profit type: {tp.type}."
    sections.append({"id": "sltp", "title": "Stop-Loss aur Take-Profit", "text": f"{sl_text} {tp_text}"})

    risk_bits = []
    if cfg.risk_pct is not None:
        risk_bits.append(f"Har trade mein capital ka {cfg.risk_pct}% risk hoga.")
    if cfg.risk_reward is not None:
        risk_bits.append(f"Risk:Reward target {cfg.risk_reward}:1 hai.")
    sections.append({
        "id": "risk", "title": "Risk Management",
        "text": " ".join(risk_bits) if risk_bits else "Koi risk setting nahi mili.",
    })

    filt_bits = []
    if cfg.session_filter:
        filt_bits.append(f"Sirf {', '.join(cfg.session_filter)} session mein trade hogi.")
    if cfg.day_filter:
        filt_bits.append(f"Sirf in dino mein: {', '.join(cfg.day_filter)}.")
    sections.append({
        "id": "filters", "title": "Session aur Din ki Pabandi",
        "text": " ".join(filt_bits) if filt_bits else "Koi session/din ki pabandi nahi hai -- har waqt trade ho sakti hai.",
    })

    # Uses the SAME validate(cfg) errors the actual Incomplete Lock gate is
    # computed from -- not a separate, narrower heuristic -- so this status
    # line can never claim "all clear" while a real validator error (e.g.
    # an exit concept missing from concepts_used) is still blocking the
    # strategy from actually running.
    manual_review_count = sum(1 for bucket in _BUCKETS for c in getattr(cfg, bucket) if c.manual_review)
    sections.append({
        "id": "status", "title": "Abhi Ka Status",
        "text": (
            f"{len(errors)} sawaal/masla abhi bhi baaki hai: {'; '.join(errors)}"
            if errors else
            (f"{manual_review_count} rule(s) Manual Review par hain (chalti strategy mein shamil nahi)." if manual_review_count
             else "Sab kuch clear hai, backtest ke liye ready.")
        ),
    })
    return sections


@router.get("/api/backtesting/strategies/{strategy_id}/read-mode")
def get_read_mode(strategy_id: str):
    try:
        cfg = lib.load(strategy_id)
    except FileNotFoundError:
        raise HTTPException(404, "strategy not found")
    errors = validate(cfg)
    return {
        "strategy_id": strategy_id, "name": cfg.name,
        "ready_for_backtest": not errors,
        "sections": _read_mode_summary(cfg, errors),
    }
