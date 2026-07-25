"""Self-Correcting Import Pipeline.

SINDHU's core rule is that the user pastes a strategy and nothing else --
they have no trading background, so they cannot be asked to resolve a
trading-logic problem. Detection alone (validator.py,
strategy_safety_check.py) is therefore not enough: every detected issue
has to lead to an automatic FIX. This module is that fix layer, in three
escalating levels:

LEVEL 1 -- free, every import, zero extra AI calls. Two halves:
  (a) PREVENTIVE: the AI is instructed (schema.py's prompt, inside the
      SAME extraction call that already happens) to self-verify its own
      output before returning it -- did it capture every entry/exit rule,
      and would its output survive the three safety checks.
  (b) ENFORCING: `auto_repair()` below -- deterministic, AI-free structural
      repairs for the failure modes that have a provably correct mechanical
      fix. This runs regardless of whether the AI followed (a), so a
      prompt the model ignored still can't produce a broken strategy.

LEVEL 2 -- ONE small targeted AI call, only for what Level 1 could not
  resolve, scoped to the single failing piece (not a re-import of the whole
  document). Deliberately rare; every trigger is counted (see
  `get_telemetry()`) so a rising Level 2 rate is visible as a signal that
  Level 1 needs improving.

LEVEL 3 -- last resort only. The strategy is flagged for the user in
  plain, non-trading language explaining what is missing and why it could
  not be resolved automatically.

Scope: the AI import + review pipeline only. Nothing here touches the
backtest or paper-trading engines.
"""

import json
import os
from datetime import datetime, timezone

from data_engine import paths
from backtest_engine import validator
from backtest_engine import strategy_safety_check as safety
from backtest_engine.strategy_config import Condition

_TELEMETRY_PATH = os.path.join(paths.HISTORY_DIR, "self_correction_stats.json")

# Concepts whose bare form encodes an unambiguous directional bias, so a
# contradictory AND-gate containing them can be split into long/short
# branches deterministically (no judgement call, no guessing). Anything
# NOT listed here contributes no direction and is treated as a shared
# filter that belongs on BOTH branches.
_DIRECTIONAL_CONCEPTS = {
    "pdh": "bullish",   # close > previous-day high
    "pdl": "bearish",   # close < previous-day low
}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------ telemetry

def _read_telemetry():
    try:
        with open(_TELEMETRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    for key in ("level_0_clean", "level_1_auto_fixed", "level_2_targeted_ai", "level_3_flagged"):
        data.setdefault(key, 0)
    data.setdefault("recent", [])
    return data


def record_outcome(level, strategy_name, repairs=None, remaining=None):
    """Counts one self-correction outcome. Level 2's rate is the signal
    that matters: if it climbs, Level 1's deterministic repairs (or the
    prompt's self-verification) need extending to cover whatever keeps
    escaping them. Never raises -- telemetry must never break an import."""
    key = {0: "level_0_clean", 1: "level_1_auto_fixed",
           2: "level_2_targeted_ai", 3: "level_3_flagged"}.get(level)
    if key is None:
        return
    try:
        data = _read_telemetry()
        data[key] += 1
        data["recent"] = ([{
            "at": _now_iso(), "level": level, "strategy": strategy_name,
            "repairs": list(repairs or []), "remaining": list(remaining or []),
        }] + data["recent"])[:50]
        os.makedirs(paths.HISTORY_DIR, exist_ok=True)
        with open(_TELEMETRY_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def get_telemetry():
    """{level_0_clean, level_1_auto_fixed, level_2_targeted_ai,
    level_3_flagged, recent: [...], level_2_rate_pct}."""
    data = _read_telemetry()
    total = sum(data[k] for k in
                ("level_0_clean", "level_1_auto_fixed", "level_2_targeted_ai", "level_3_flagged"))
    data["total"] = total
    data["level_2_rate_pct"] = round(data["level_2_targeted_ai"] / total * 100, 2) if total else 0.0
    return data


# ------------------------------------------------------------ helpers

def _condition_direction(cond):
    """The direction a single condition implies, or None if it implies
    none (a neutral filter that belongs on every branch)."""
    if cond.type == "concept":
        if cond.direction in ("bullish", "bearish"):
            return cond.direction
        return _DIRECTIONAL_CONCEPTS.get(cond.name)
    if cond.type == "trend":
        if cond.direction == "up":
            return "bullish"
        if cond.direction == "down":
            return "bearish"
    return None


def _entry_bucket_names():
    return ("entry_conditions", "long_entry_conditions", "short_entry_conditions")


def _all_entry_conditions(config):
    out = []
    for name in _entry_bucket_names():
        out.extend(getattr(config, name))
    for group in config.entry_rule_groups:
        out.extend(group.get("conditions") or [])
    return out


def _has_real_sltp(config):
    """A rule-based exit gate can only be safely removed if the position
    still has SOME way to close -- a real stop-loss or take-profit."""
    return config.stop_loss.type != "unknown" or config.take_profit.type != "unknown"


def _can_close_positions(config):
    """Does this strategy have ANY way to close a position -- a stop-loss,
    a take-profit, or a rule-based exit gate?"""
    return _has_real_sltp(config) or bool(config.exit_conditions)


def _can_open_positions(config):
    return bool(config.entry_conditions or config.long_entry_conditions
                or config.short_entry_conditions or config.entry_rule_groups)


def repair_is_acceptable(original, candidate):
    """A repair must FIX the strategy without breaking something else.
    Passing the safety check alone is not sufficient evidence of that: an
    "exit_conditions: []" patch trivially satisfies both exit-related
    safety checks (no exit rules means no duplicated or unreachable exit
    rules) while leaving a position that can never close at all. Found by
    this module's own test suite, against a Level 2 patch that would
    otherwise have been accepted and reported as a success.

    So a candidate is accepted only if it passes the safety check AND has
    not lost the ability to open or close a position relative to where it
    started. Comparing against `original` rather than demanding those
    absolutely matters: a strategy that already couldn't close a position
    before any repair is a pre-existing gap for the validator to report,
    not something this repair introduced or should be blamed for."""
    if not safety.run_safety_check(candidate)["passed"]:
        return False
    if _can_close_positions(original) and not _can_close_positions(candidate):
        return False
    if _can_open_positions(original) and not _can_open_positions(candidate):
        return False
    return True


# ------------------------------------------------------------ Level 1 repairs

def _repair_duplicate_exit_clauses(config):
    """Safety check 1. An exit clause structurally identical to an entry
    clause is already true the instant the position opens, so the trade
    closes on the very next bar -- the defect that ground Liquidity Sweep
    & FVG Validation Strategy's account to zero on commission alone. The
    duplicate is an extraction artifact, never a real rule (no author
    writes "exit when the same thing that just made you enter is true"),
    so removing it is the provably correct repair: it restores the
    stop-loss/take-profit exits the author actually described."""
    if not config.exit_conditions:
        return []
    entry_sigs = {safety._cond_signature(c) for c in _all_entry_conditions(config) if c.type != "raw"}
    kept, removed = [], []
    for cond in config.exit_conditions:
        if cond.type != "raw" and safety._cond_signature(cond) in entry_sigs:
            removed.append(cond)
        else:
            kept.append(cond)
    if not removed:
        return []
    if not kept and not _has_real_sltp(config):
        # Removing every exit clause would leave the position with no way
        # out at all -- worse than the duplicate. Escalate instead.
        return []
    config.exit_conditions = kept
    return [
        f"Removed exit rule '{safety._describe(c)}' because it was an exact copy of an entry rule "
        f"(the trade would have closed on the bar right after it opened); exits now come from the "
        f"stop-loss/take-profit the strategy already defines."
        for c in removed
    ]


def _repair_unreachable_exit_gate(config):
    """Safety check 2. An exit gate built ONLY from slow-moving price-level
    concepts (support/resistance/pdh/pdl/POC/value-area/...) stays true for
    many consecutive bars once satisfied, so it re-fires almost immediately
    after entry and the trade never gets room to reach its target. Only
    repairable when a real stop-loss or take-profit exists to take over --
    otherwise removing it would leave the trade with no exit at all, so
    that case escalates instead of being "fixed" into something worse."""
    if not config.exit_conditions or not _has_real_sltp(config):
        return []
    if not all(c.type == "concept" and c.name in safety._SLOW_LEVEL_CONCEPTS for c in config.exit_conditions):
        return []
    names = sorted({c.name for c in config.exit_conditions})
    config.exit_conditions = []
    return [
        f"Removed the exit rules based on {', '.join(names)} -- those are slow-moving price levels that "
        f"stay true for many bars in a row, so the trade would have closed almost immediately after "
        f"opening instead of running to its target. Exits now come from the strategy's own "
        f"stop-loss/take-profit."
    ]


def _repair_contradictory_entry_gate(config):
    """Safety check 3. Conditions inside one entry bucket are AND-ed on the
    same bar, so a bucket demanding both a bullish and a bearish condition
    can never fire (Daily High-Low Liquidity Strategy: "close above the
    previous day's high" AND "close below the previous day's low", 7,927
    evaluations, 0 true).

    This is essentially always one cause: a document describing a long
    setup AND its mirrored short setup got flattened into a single list.
    The correct repair is therefore to un-flatten it -- split the bucket
    into two direction-tagged alternative entry paths (entry_rule_groups),
    with every non-directional condition kept as a shared filter on BOTH
    branches. That restores exactly what the author wrote, and is the
    reason entry_rule_groups exists.

    Only splits when direction is structurally unambiguous (an explicit
    bullish/bearish concept direction, a directional trend condition, or a
    bare pdh/pdl whose meaning is fixed by definition). A contradiction
    with no such signal -- e.g. "RSI < 30" AND "RSI > 70", where deciding
    which side is the long leg is a trading judgement, not a mechanical
    fact -- is deliberately left for Level 2 rather than guessed at here."""
    contradictory = {}
    for name in _entry_bucket_names():
        bucket = getattr(config, name)
        if not bucket:
            continue
        directions = {_condition_direction(c) for c in bucket}
        if "bullish" in directions and "bearish" in directions:
            contradictory[name] = bucket
    if not contradictory:
        return []

    repairs = []
    groups = list(config.entry_rule_groups)
    for name in _entry_bucket_names():
        bucket = getattr(config, name)
        if not bucket:
            continue
        label_base = {"entry_conditions": "Entry", "long_entry_conditions": "Long entry",
                      "short_entry_conditions": "Short entry"}[name]
        if name in contradictory:
            bullish = [c for c in bucket if _condition_direction(c) == "bullish"]
            bearish = [c for c in bucket if _condition_direction(c) == "bearish"]
            shared = [c for c in bucket if _condition_direction(c) is None]
            groups.append({"label": f"{label_base} (long setup)", "direction": "bullish",
                           "conditions": shared + bullish})
            groups.append({"label": f"{label_base} (short setup)", "direction": "bearish",
                           "conditions": shared + bearish})
            repairs.append(
                f"'{label_base}' demanded {len(bullish)} upward and {len(bearish)} downward condition(s) "
                f"at the same moment, which the market can never do at once, so it could never trade. "
                f"Split into two separate setups -- one for the upward case ("
                f"{', '.join(safety._describe(c) for c in bullish)}) and one for the downward case ("
                f"{', '.join(safety._describe(c) for c in bearish)})"
                + (f", each still requiring {', '.join(safety._describe(c) for c in shared)}." if shared else ".")
            )
        else:
            direction = next((d for d in (_condition_direction(c) for c in bucket) if d), None)
            if direction is None:
                direction = "bearish" if name == "short_entry_conditions" else "bullish"
            groups.append({"label": label_base, "direction": direction, "conditions": list(bucket)})
        setattr(config, name, [])

    config.entry_rule_groups = groups
    return repairs


def auto_repair(config):
    """LEVEL 1 (enforcing half): every deterministic, AI-free repair, applied
    in place. Returns a list of plain-language descriptions of what was
    changed (empty = nothing needed repairing). Only ever makes a change
    whose correctness is structural, never a trading judgement."""
    repairs = []
    repairs += _repair_contradictory_entry_gate(config)
    repairs += _repair_duplicate_exit_clauses(config)
    repairs += _repair_unreachable_exit_gate(config)
    return repairs


# ------------------------------------------------------------ Level 2

_LEVEL2_SYSTEM_PROMPT = (
    "You are repairing ONE specific defect in an already-extracted trading strategy. "
    "You are NOT re-reading or re-extracting the whole strategy -- only the piece named below.\n\n"
    "Return ONLY a JSON object (no prose, no code fence) of the form:\n"
    '{"entry_rule_groups": [{"label": "...", "direction": "bullish"|"bearish", "conditions": [<condition>]}], '
    '"exit_conditions": [<condition>], "explanation": "one short sentence"}\n'
    "Include ONLY the key(s) you are actually changing; omit the rest.\n\n"
    "Rules that make a repair valid:\n"
    "- Conditions inside ONE list are AND-ed on the SAME bar. Two conditions that can never both be "
    "true at once (e.g. an indicator required both below X and above Y, or price required both above "
    "one level and below a lower one) must NEVER share a list.\n"
    "- If the source text describes a long setup and a short setup, they are SEPARATE entries in "
    "entry_rule_groups with opposite \"direction\" values -- never merged into one list.\n"
    "- An exit condition must never be an exact copy of an entry condition, and must not be built only "
    "from slow-moving price levels (support/resistance/previous-day high/low/value area), or the trade "
    "closes on the bar right after it opens.\n"
    "- Use only this condition vocabulary: {\"type\": \"indicator_compare\"|\"price_compare\"|"
    "\"indicator_vs_indicator\"|\"concept\"|\"session\"|\"trend\"|\"raw\", \"indicator\": name, "
    "\"params\": {\"period\": N}, \"op\": \">\"|\"<\", \"value\": number, \"name\": concept name, "
    "\"direction\": \"bullish\"|\"bearish\"|null, \"role\": timeframe role or null, \"text\": original "
    "phrase (only when type=\"raw\")}.\n"
    "- Never invent a rule the source text does not support. If the text genuinely does not say, leave "
    "that piece out rather than guessing."
)


def _build_level2_prompt(config, issues):
    """Deliberately compact: only the failing piece and the source lines
    that mention it -- NOT the whole document. This is what keeps Level 2 a
    small targeted call instead of a second full import."""
    current = {
        "entry_rule_groups": [
            {"label": g.get("label"), "direction": g.get("direction"),
             "conditions": [safety._describe(c) for c in g.get("conditions") or []]}
            for g in config.entry_rule_groups
        ],
        "entry_conditions": [safety._describe(c) for c in config.entry_conditions],
        "long_entry_conditions": [safety._describe(c) for c in config.long_entry_conditions],
        "short_entry_conditions": [safety._describe(c) for c in config.short_entry_conditions],
        "exit_conditions": [safety._describe(c) for c in config.exit_conditions],
    }
    # Pull only the source lines that plausibly relate to the failing rules,
    # capped -- never the entire document.
    keywords = set()
    for issue in issues:
        for token in issue.replace("'", " ").replace("(", " ").replace(")", " ").split():
            if len(token) > 3 and token.islower():
                keywords.add(token)
    relevant = []
    for line in (config.raw_text or "").splitlines():
        low = line.lower()
        if any(k in low for k in keywords) or any(w in low for w in ("entry", "exit", "long", "short", "buy", "sell")):
            relevant.append(line.strip())
        if len(relevant) >= 40:
            break

    return (
        f"STRATEGY: {config.name}\n\n"
        f"THE DEFECT(S) TO FIX (and nothing else):\n" + "\n".join(f"- {i}" for i in issues) + "\n\n"
        f"CURRENT EXTRACTED RULES (human-readable summary):\n{json.dumps(current, indent=2)}\n\n"
        f"RELEVANT LINES FROM THE ORIGINAL SOURCE TEXT:\n" + "\n".join(relevant[:40])
    )


def _apply_level2_patch(config, patch):
    """Applies only the keys the AI actually returned, converting raw dicts
    into real Condition objects. Never trusted blindly -- the caller
    re-runs the full safety check afterwards and rolls back if the patch
    didn't actually resolve the defect."""
    from ai_integration.schema import _clean_condition
    from ai_integration.strategy_builder import build_condition

    def _conditions(raw):
        out = []
        for entry in raw or []:
            cleaned = _clean_condition(entry)
            if not cleaned:
                continue
            built = build_condition(cleaned)
            if built:
                out.append(built)
        return out

    changed = False
    if isinstance(patch.get("entry_rule_groups"), list):
        groups = []
        for g in patch["entry_rule_groups"]:
            if not isinstance(g, dict) or g.get("direction") not in ("bullish", "bearish"):
                continue
            conds = _conditions(g.get("conditions"))
            if conds:
                groups.append({"label": str(g.get("label") or ""), "direction": g["direction"], "conditions": conds})
        if groups:
            config.entry_rule_groups = groups
            config.entry_conditions = []
            config.long_entry_conditions = []
            config.short_entry_conditions = []
            changed = True
    if isinstance(patch.get("exit_conditions"), list):
        config.exit_conditions = _conditions(patch["exit_conditions"])
        changed = True
    return changed


def targeted_ai_fix(config, issues, use_ai=True):
    """LEVEL 2: ONE small follow-up AI call, scoped to `issues` only.
    Returns (succeeded: bool, note: str). Never raises, never falls back to
    a full re-import. The patch is applied to a COPY and kept only if it
    genuinely clears the issues -- an AI "fix" that doesn't fix anything is
    discarded rather than silently making things different-but-still-broken."""
    if not use_ai:
        return False, "AI is disabled, so the targeted repair step was skipped."
    try:
        from ai_integration import config as ai_config
        from ai_integration import providers as ai_providers
        from backtest_engine.strategy_config import StrategyConfig

        chain = ai_config.provider_fallback_chain()
        if not chain:
            return False, "No AI provider is configured, so the targeted repair step was skipped."

        prompt = _build_level2_prompt(config, issues)
        raw = None
        for provider_name in chain:
            try:
                settings = ai_config.get_provider_settings(provider_name)
                provider = ai_providers.get_provider(provider_name, settings)
                result = provider.chat(prompt, system=_LEVEL2_SYSTEM_PROMPT)
                try:
                    from data_engine import storage
                    storage.save_ai_usage_log(
                        provider_name, settings.get("model"), "/ai/import/level2-targeted-repair",
                        "success" if result.ok else "error", _now_iso(),
                        tokens_in=result.tokens_in, tokens_out=result.tokens_out,
                        latency_ms=result.latency_ms,
                        error_message=None if result.ok else result.error,
                    )
                except Exception:
                    pass
                if result.ok and (result.text or "").strip():
                    raw = result.text
                    break
            except Exception:
                continue
        if raw is None:
            return False, "Every AI provider failed during the targeted repair step."

        from ai_integration.schema import _CODE_FENCE_RE
        cleaned = _CODE_FENCE_RE.sub("", raw).strip()
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end == -1:
            return False, "The targeted repair response was not usable JSON."
        patch = json.loads(cleaned[start:end + 1])

        candidate = StrategyConfig.from_dict(config.to_dict())
        if not _apply_level2_patch(candidate, patch):
            return False, "The targeted repair response contained no usable correction."
        auto_repair(candidate)  # deterministic pass over the AI's own patch
        if not repair_is_acceptable(config, candidate):
            return False, "The targeted repair did not resolve the problem, so it was discarded."

        for field in ("entry_rule_groups", "entry_conditions", "long_entry_conditions",
                      "short_entry_conditions", "exit_conditions", "concepts_used", "indicators"):
            setattr(config, field, getattr(candidate, field))
        return True, str(patch.get("explanation") or "Repaired by a targeted follow-up AI check.")
    except Exception as exc:
        return False, f"The targeted repair step could not run ({exc})."


# ------------------------------------------------------------ Level 3

# Markers are matched against the EXACT strings produced by
# backtest_engine.strategy_safety_check / validator -- keep them in sync
# with those modules if their wording ever changes.
_PLAIN_LANGUAGE = [
    ("is IDENTICAL to a condition already required in",
     "Its rule for closing a trade repeats one of its rules for opening a trade, which would close every "
     "trade almost immediately, and the original text does not say what should close the trade instead."),
    ("reads the SAME underlying signal as an entry condition",
     "Its rule for closing a trade relies on the same signal that opens the trade, so trades would close "
     "almost immediately, and the original text does not say what should close the trade instead."),
    ("slow-moving price-level concepts",
     "Its rules for closing a trade are all based on price levels that stay valid for a long time, so "
     "trades would close almost immediately, and the text gives no stop-loss or profit target to use "
     "instead."),
    ("Impossible combination",
     "It requires two things that can never be true at the same moment, and the text does not make clear "
     "which one belongs to the buy side and which to the sell side."),
    ("BOTH bullish and bearish",
     "It requires the same signal in both the up and the down direction at once, and the text does not "
     "make clear which belongs to the buy side and which to the sell side."),
    ("Missing entry rules", "No rules for opening a trade could be found in the text at all."),
    ("Missing stop loss", "No stop-loss was stated anywhere in the text."),
    ("Missing take profit", "No profit target was stated anywhere in the text."),
    ("Missing risk", "No risk-per-trade amount was stated anywhere in the text."),
]

_GENERIC_PLAIN = (
    "Part of this strategy's wording could not be turned into a rule that can be tested, and the text "
    "does not give enough detail to resolve it automatically."
)


def plain_language_summary(issues):
    """LEVEL 3: translates the engine's technical findings into wording a
    non-trader can act on. Anything without a known translation falls back
    to a generic plain sentence rather than leaking raw engine wording
    (field names, condition syntax) at the user -- they have no trading
    background and no way to act on that. The untranslated technical text
    is still returned separately in `remaining_issues` for the logs."""
    out = []
    for issue in issues:
        out.append(next((plain for marker, plain in _PLAIN_LANGUAGE if marker in issue), _GENERIC_PLAIN))
    seen, unique = set(), []
    for item in out:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


# ------------------------------------------------------------ orchestrator

def self_correct(config, use_ai=True, allow_level2=True):
    """The full three-level flow for ONE strategy. Mutates `config` in
    place and returns:
      {"level": 0|1|2|3, "status": "ready"|"needs_review",
       "repairs": [...plain-language descriptions of what was fixed...],
       "remaining_issues": [...technical...],
       "user_message": str|None (plain language, only at level 3),
       "level2_note": str|None}

    level 0 = was already clean, nothing to do
    level 1 = deterministic repairs resolved it (no AI call)
    level 2 = one targeted AI call resolved what level 1 could not
    level 3 = still unresolved -- flagged for the user in plain language
    """
    from backtest_engine.strategy_config import StrategyConfig

    before = safety.run_safety_check(config)
    if before["passed"]:
        record_outcome(0, config.name)
        return {"level": 0, "status": "ready", "repairs": [], "remaining_issues": [],
                "user_message": None, "level2_note": None}

    # Snapshot BEFORE mutating, so repair_is_acceptable() can tell "this
    # repair broke something" apart from "this was already missing".
    original = StrategyConfig.from_dict(config.to_dict())

    repairs = auto_repair(config)
    after = safety.run_safety_check(config)
    if after["passed"] and repair_is_acceptable(original, config):
        record_outcome(1, config.name, repairs)
        return {"level": 1, "status": "ready", "repairs": repairs, "remaining_issues": [],
                "user_message": None, "level2_note": None}

    level2_note = None
    if allow_level2:
        ok, level2_note = targeted_ai_fix(config, after["reasons"], use_ai=use_ai)
        if ok and repair_is_acceptable(original, config):
            repairs = repairs + [f"A focused follow-up check corrected the remaining problem: {level2_note}"]
            record_outcome(2, config.name, repairs)
            return {"level": 2, "status": "ready", "repairs": repairs, "remaining_issues": [],
                    "user_message": None, "level2_note": level2_note}

    remaining = safety.run_safety_check(config)["reasons"] + [
        e for e in validator.validate(config)
        if e.startswith("Missing entry rules") or e.startswith("Missing stop loss")
        or e.startswith("Missing take profit")
    ]
    record_outcome(3, config.name, repairs, remaining)
    return {
        "level": 3, "status": "needs_review", "repairs": repairs, "remaining_issues": remaining,
        "user_message": (
            "This strategy could not be made ready automatically. "
            + " ".join(plain_language_summary(remaining))
            + " The original text would need to say this explicitly before it can be tested."
        ),
        "level2_note": level2_note,
    }
