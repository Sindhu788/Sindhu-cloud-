"""Item 10 (User Correction Learning) -- when the CEO resolves the SAME
recurring clarification question repeatedly with a CONSISTENT answer, stop
asking about it again.

CRITICAL SAFETY CONSTRAINT (from the task spec): must never cause the
system to silently assume an answer on a materially different case, must
only suppress a question where the pattern match is unambiguous, and must
remain fully auditable with an override.

Deliberately narrow in scope for exactly that reason: this only applies to
"missing_field" clarification issues (entry_timeframe, risk_pct,
risk_reward -- explicitly NOT stop_loss, which is safety-critical and
always stays an explicit human choice). Those three carry NO
strategy-specific text at all -- unlike raw_condition/invalid_indicator,
whose meaning genuinely depends on THIS document's own wording, a
missing_field question is LITERALLY the same question every single time
it appears ("no risk % was detected, pick one"). That sameness is what
makes the pattern match provably unambiguous: there is no "materially
different case" a generic missing-field question could be confused with.

Every auto-applied answer is logged to the SAME strategy's clarification
record (never a separate, hidden log) so it is always visible on the
Clarification Page with a plain explanation of why, and can always be
reopened."""

import json
import os
from datetime import datetime, timezone

from data_engine import paths

_HISTORY_PATH = os.path.join(paths.HISTORY_DIR, "clarification_correction_history.json")
_MAX_HISTORY_PER_KEY = 50
CONSISTENCY_WINDOW = 3       # the most recent N resolutions of this exact question
MIN_DISTINCT_STRATEGIES = 2  # must be a real repeated PATTERN, not one strategy edited 3x

ELIGIBLE_FIELDS = ("entry_timeframe", "risk_pct", "risk_reward")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _read():
    try:
        with open(_HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _write(data):
    try:
        os.makedirs(os.path.dirname(_HISTORY_PATH), exist_ok=True)
        with open(_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def record_resolution(field, value, strategy_id):
    """Logs one real, human-made resolution of a missing_field question --
    never invented, always a genuine choice the CEO made. Silently ignores
    fields outside ELIGIBLE_FIELDS (never learns a pattern for anything
    safety-critical or text-dependent)."""
    if field not in ELIGIBLE_FIELDS:
        return
    data = _read()
    entries = data.setdefault(field, [])
    entries.append({"value": value, "strategy_id": strategy_id, "at": _now_iso()})
    data[field] = entries[-_MAX_HISTORY_PER_KEY:]
    _write(data)


def learned_suggestion(field):
    """Returns {"value", "based_on": N} if the last CONSISTENCY_WINDOW
    resolutions of this EXACT question were all the identical answer, from
    at least MIN_DISTINCT_STRATEGIES different strategies -- otherwise
    None. Never guesses from a single strategy's repeated edits, and never
    from a mixed/inconsistent history."""
    if field not in ELIGIBLE_FIELDS:
        return None
    entries = _read().get(field, [])
    if len(entries) < CONSISTENCY_WINDOW:
        return None
    recent = entries[-CONSISTENCY_WINDOW:]
    first_value = recent[0]["value"]
    if not all(e["value"] == first_value for e in recent):
        return None
    if len({e["strategy_id"] for e in recent}) < MIN_DISTINCT_STRATEGIES:
        return None
    return {"value": first_value, "based_on": len(recent)}


def apply_learned_corrections(cfg):
    """Mutates `cfg` in place, filling in any currently-missing/invalid
    eligible field for which an unambiguous learned pattern exists.
    Returns a list of {"field", "value", "based_on"} for what was
    auto-applied -- always surfaced to the caller, never silently hidden.
    Deliberately mirrors self_correction.py's own "mutate + report" shape
    rather than introducing a second pattern."""
    applied = []

    if "entry" not in (cfg.timeframes or {}):
        s = learned_suggestion("entry_timeframe")
        if s:
            cfg.timeframes = dict(cfg.timeframes or {})
            cfg.timeframes["entry"] = str(s["value"])
            applied.append({"field": "entry_timeframe", "value": s["value"], "based_on": s["based_on"]})

    if cfg.risk_pct is None or not (0 < cfg.risk_pct <= 100):
        s = learned_suggestion("risk_pct")
        if s:
            cfg.risk_pct = float(s["value"])
            applied.append({"field": "risk_pct", "value": s["value"], "based_on": s["based_on"]})

    if cfg.risk_reward is not None and cfg.risk_reward <= 0:
        s = learned_suggestion("risk_reward")
        if s:
            cfg.risk_reward = float(s["value"])
            applied.append({"field": "risk_reward", "value": s["value"], "based_on": s["based_on"]})

    return applied
