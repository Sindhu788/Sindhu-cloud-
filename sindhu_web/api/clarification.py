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
from backtest_engine.validator import validate, _KNOWN_INDICATORS
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


def build_issues(cfg, hidden_rules=None):
    """Turns validate(cfg)'s flat error strings into structured, actionable
    issues. One issue per distinct problem, each carrying enough shape for
    the frontend to render the right control (free-text redescribe, a
    small set of suggested options, or a reject button) without any
    string-parsing on the client side."""
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

        if err.startswith("Invalid risk %"):
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

    return issues


def _apply_resolution(cfg, resolution_id, action, text, value):
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
        if field == "entry_timeframe":
            if not value:
                return False, "No timeframe provided."
            cfg.timeframes["entry"] = str(value)
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
            return True, f"Risk:reward set to {cfg.risk_reward}:1."
        if field == "risk_pct":
            if value is None:
                return False, "No risk % value provided."
            cfg.risk_pct = float(value)
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
        if cond.type == "indicator_compare":
            cond.indicator = new_name
        elif cond.type == "concept":
            cond.name = new_name
        else:
            return False, "This condition type can't be fixed this way."
        return True, f"Changed to '{new_name}'."

    return False, f"Unknown action '{action}'."


class ClarifyResolution(BaseModel):
    id: str
    action: str  # "edit" | "set_field" | "reject" | "replace_indicator" | "mark_manual_review"
    text: Optional[str] = None
    value: Any = None


class ClarifyRequest(BaseModel):
    resolutions: List[ClarifyResolution]


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
        "raw_text": cfg.raw_text,
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
            ok, detail = _apply_resolution(cfg, r.id, r.action, r.text, r.value)
            (applied if ok else failed).append({"id": r.id, "detail": detail})
        except Exception as exc:
            failed.append({"id": r.id, "detail": str(exc)})

    lib.save_version(strategy_id, cfg)

    errors = validate(cfg)
    status = "READY_FOR_BACKTEST" if not errors else "NEEDS_CLARIFICATION"
    stored = lib.get_clarification(strategy_id) or {}
    issues = build_issues(cfg, stored.get("hidden_rules"))

    if status == "NEEDS_CLARIFICATION":
        lib.set_clarification(strategy_id, {
            "notes": errors, "hidden_rules": stored.get("hidden_rules") or [],
            "confidence_pct": stored.get("confidence_pct"), "updated_at": _now_iso(),
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
