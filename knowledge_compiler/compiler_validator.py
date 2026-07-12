"""Extends -- never replaces -- backtest_engine.validator.validate(). A raw
strategy parse is never rejected outright: for each missing item, this
module tries (in order) a safe configured default, a standard Trading
Dictionary value, then a compatible value borrowed from a similar strategy
already in the Knowledge Library. Only what's still missing after all three
passes is reported back as needing CEO clarification.

Deliberately never guesses anything safety-critical from nothing: a missing
stop-loss, missing/unclear entry or exit rules, or an unrecognized
indicator name always needs a real answer -- inventing trade logic or a
risk parameter with no basis at all would defeat the entire point of a
deterministic, non-guessing compiler.
"""

from backtest_engine import validator as base_validator
from backtest_engine.strategy_config import SLTPSpec
from backtest_engine.strategy_library import list_all, load
from knowledge_compiler.normalizer import READY_FOR_BACKTEST, NEEDS_CLARIFICATION

DEFAULT_RISK_PCT = 1.0
DEFAULT_RR = 2.0
DEFAULT_ENTRY_TIMEFRAME = "1h"
DEFAULT_INDICATOR_PERIODS = {"ema": 20, "sma": 20, "rsi": 14, "atr": 14}
DEFAULT_STOP_LOSS_PCT = 2.0


def _find_similar_strategy(config):
    """Deterministic similarity check: the Knowledge Library strategy with
    the most overlapping concepts_used (need at least 2 shared concepts to
    count as "similar enough" to borrow a value from). Read-only."""
    best, best_score = None, 1
    for meta in list_all():
        try:
            candidate = load(meta["id"])
        except Exception:
            continue
        overlap = len(set(candidate.concepts_used) & set(config.concepts_used))
        if overlap > best_score:
            best, best_score = candidate, overlap
    return best


def _fill_default_indicator_periods(config, resolved_defaults):
    for ind in config.indicators:
        if not ind.get("params", {}).get("period") and ind.get("name") in DEFAULT_INDICATOR_PERIODS:
            period = DEFAULT_INDICATOR_PERIODS[ind["name"]]
            ind.setdefault("params", {})["period"] = period
            resolved_defaults.append(f"{ind['name'].upper()} period defaulted to {period} (Trading Dictionary standard)")


def resolve_and_validate(config):
    """Returns (config, status, clarification_notes, resolved_defaults).
    `config` is mutated in place with any safely-resolved defaults."""
    resolved_defaults = []
    _fill_default_indicator_periods(config, resolved_defaults)

    errors = base_validator.validate(config)
    if not errors:
        return config, READY_FOR_BACKTEST, [], resolved_defaults

    similar = None
    remaining = []

    for err in errors:
        if err.startswith("Missing risk %"):
            config.risk_pct = DEFAULT_RISK_PCT
            resolved_defaults.append(f"risk % defaulted to {DEFAULT_RISK_PCT} (configured default)")
            continue

        if err.startswith("Missing take profit"):
            if config.risk_reward is not None:
                config.take_profit = SLTPSpec(type="rr", value=config.risk_reward)
                resolved_defaults.append(f"take profit derived from detected risk:reward ({config.risk_reward}:1)")
            else:
                config.risk_reward = DEFAULT_RR
                config.take_profit = SLTPSpec(type="rr", value=DEFAULT_RR)
                resolved_defaults.append(f"take profit defaulted to {DEFAULT_RR}:1 risk:reward (configured default)")
            continue

        if err.startswith("Missing entry timeframe"):
            if similar is None:
                similar = _find_similar_strategy(config)
            if similar and "entry" in similar.timeframes:
                config.timeframes["entry"] = similar.timeframes["entry"]
                resolved_defaults.append(
                    f"entry timeframe borrowed from similar strategy '{similar.name}' ({similar.timeframes['entry']})"
                )
            else:
                config.timeframes["entry"] = DEFAULT_ENTRY_TIMEFRAME
                resolved_defaults.append(f"entry timeframe defaulted to {DEFAULT_ENTRY_TIMEFRAME} (configured default)")
            continue

        if err.startswith("Missing stop loss"):
            if similar is None:
                similar = _find_similar_strategy(config)
            if similar and similar.stop_loss.type != "unknown":
                config.stop_loss = similar.stop_loss
                resolved_defaults.append(
                    f"stop loss borrowed from similar strategy '{similar.name}' ({similar.stop_loss.type})"
                )
                continue
            # Safety-critical with genuinely no basis to borrow from --
            # never invent a %/ATR value out of thin air.
            remaining.append(err)
            continue

        # Missing/unclear entry or exit rules, invalid indicator/concept
        # names, and invalid risk:reward values all require a real answer
        # from the CEO -- inventing trade logic or fixing a typo by
        # guessing would be exactly the kind of guess this system refuses
        # to make.
        remaining.append(err)

    if remaining:
        return config, NEEDS_CLARIFICATION, remaining, resolved_defaults
    return config, READY_FOR_BACKTEST, [], resolved_defaults


def force_ready(config, clarification_notes, resolved_defaults):
    """Used ONLY by the AI-Native Structured Extraction path (v7 -- AI
    Knowledge Learning Engine): the CEO's spec requires every AI-confident
    (>=70%) import to automatically become Backtesting Ready with no
    clarification gate. resolve_and_validate() above deliberately refuses to
    invent a stop-loss with no basis at all -- this is the one safety-net
    default that's still needed to make that guarantee true in practice,
    clearly logged as a default rather than silently pretended to be
    AI-derived. `clarification_notes` (resolve_and_validate()'s own
    "remaining" errors) are returned unchanged, now purely informational
    since the caller no longer treats them as blocking -- never re-derived
    from validate() again here, which would just duplicate them. Never used
    by the old text-parser path -- that path's exact behavior (including
    genuinely blocking on an unresolved strategy) is completely unchanged."""
    if config.stop_loss.type == "unknown":
        config.stop_loss = SLTPSpec(type="fixed_pct", value=DEFAULT_STOP_LOSS_PCT)
        resolved_defaults = resolved_defaults + [
            f"stop loss defaulted to {DEFAULT_STOP_LOSS_PCT}% (AI-confident import safety net -- no basis was found or borrowed)"
        ]
    return config, READY_FOR_BACKTEST, clarification_notes, resolved_defaults
