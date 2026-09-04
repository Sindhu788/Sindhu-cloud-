"""Phase 1.5 (full real backtest pipeline), 1.10 (weekly cap, not daily),
1.13 (checkpointed, resumable), 1.14 (Governor resource compliance) --
orchestrates one complete Self-Learning discovery cycle end to end.

Every heavy step reuses an existing primitive: backtest_engine.validator/
runner (the exact same validate() -> run_mtf_batch() pipeline every other
strategy in this project goes through -- no separate, lighter pipeline),
automation_pipeline.walk_forward.TRAIN_FRACTION (the project's one existing
"how do we split history into an earlier vs later period" ratio, reused
rather than inventing a second undocumented split), evolution_engine.
governor.Governor (resource limits), and backtest_engine.strategy_library.
create (the exact same persistence path a manually-built strategy uses).
"""

import uuid
from datetime import datetime, timedelta, timezone

from automation_pipeline.walk_forward import TRAIN_FRACTION
from backtest_engine import runner, strategy_library
from backtest_engine.validator import validate
from data_engine import config as base_config, feature_toggles, storage
from evolution_engine.governor import Governor
from self_learning_engine import ai_advisor, candidate_builder, combination_scorer, explainability, memory, validation_gate

WEEKLY_INTERVAL_DAYS = 7
MAX_VARIANT_ATTEMPTS = 5  # how many concept-draw variants of the SAME combo to try before moving on
DISCOVERED_STRATEGY_TAG = "self-learning-discovered"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _default_exchange():
    cfg = base_config.load_or_seed("exchanges.json", base_config.DEFAULTS["exchanges.json"])
    return cfg["default"]


def compute_global_split(exchange, symbols, train_fraction=TRAIN_FRACTION):
    """Discovery period = the earlier train_fraction of the WHOLE symbol
    universe's combined available history; validation period = the
    remaining, more recent slice -- chronological, never shuffled, same
    reasoning as walk_forward.py's own single-symbol split, just computed
    across every symbol in the batch so both periods use the identical
    real date range for every coin. None if no symbol has any data yet."""
    mins, maxes = [], []
    for symbol in symbols:
        lo, hi = storage.get_symbol_time_bounds(exchange, symbol)
        if lo is not None:
            mins.append(lo)
        if hi is not None:
            maxes.append(hi)
    if not mins or not maxes:
        return None
    global_min, global_max = min(mins), max(maxes)
    if global_max <= global_min:
        return None
    split_point = global_min + int((global_max - global_min) * train_fraction)
    return {
        "discovery_start_ms": global_min, "discovery_end_ms": split_point,
        "validation_start_ms": split_point, "validation_end_ms": global_max,
    }


def _run_real_period_batch(config, exchange, symbols, settings, start_ms, end_ms):
    """The real, unmodified backtest pipeline -- same runner.run_mtf_batch
    every manually-built strategy's batch goes through, just scoped to one
    period's date range. Returns a batch_id."""
    return runner.run_mtf_batch(config, exchange, symbols, settings, start_ms=start_ms, end_ms=end_ms)


def should_run_new_cycle():
    """Phase 1.10: a full discovery-and-test cycle at most once per week --
    the CEO explicitly does not want daily forced discovery. Mirrors
    infra_weekly_digest.py's exact 7-day gate shape."""
    if not feature_toggles.is_enabled("self_learning_engine_enabled"):
        return False
    last = storage.get_latest_self_learning_cycle()
    if not last:
        return True
    last_dt = datetime.fromisoformat(last["started_at"])
    return datetime.now(timezone.utc) - last_dt >= timedelta(days=WEEKLY_INTERVAL_DAYS)


def run_discovery_cycle(exchange=None, symbols=None, settings=None, run_batch_fn=None, force=False):
    """One full cycle: score real combinations -> AI-assisted pick -> build
    a candidate -> real out-of-sample backtest -> gate -> persist if
    accepted, log the reason either way. Never raises for "nothing to try"
    or "not enough historical data" -- those are normal, honestly-reported
    outcomes, not errors.

    `run_batch_fn` is injectable (defaults to the real backtest pipeline)
    so this orchestration can be tested without running an actual 50-coin
    backtest -- production callers should never pass it."""
    if not force and not should_run_new_cycle():
        return {"status": "skipped_weekly_cap"}

    governor = Governor()
    if not governor.resource_ok():
        return {"status": "skipped_resource_limit", "resource_check": governor._last_resource_check}

    cycle_id = uuid.uuid4().hex[:12]
    started_at = _now_iso()
    storage.save_self_learning_cycle(cycle_id, started_at, started_at, status="in_progress")

    exchange = exchange or _default_exchange()
    symbols = symbols or storage.load_symbols(exchange)
    settings = settings or {"initial_balance": 10000.0, "risk_pct_default": 1.0}
    run_batch_fn = run_batch_fn or _run_real_period_batch

    candidates = combination_scorer.score_combinations()
    if not candidates:
        report = {"status": "no_data", "narrative": "No scored combinations yet -- not enough accumulated system data."}
        storage.save_self_learning_cycle(cycle_id, started_at, _now_iso(), status="no_data", report_json=_dump(report))
        return report

    chosen = ai_advisor.select_next_combination(candidates)
    dna_combo = sorted(chosen["combo"]["dna_combo"])

    split = compute_global_split(exchange, symbols)
    if split is None:
        report = {"status": "no_data", "narrative": "No historical candle data available yet to split into two periods."}
        storage.save_self_learning_cycle(cycle_id, started_at, _now_iso(), status="no_data", report_json=_dump(report))
        return report

    outcome, gate_result, strategy_id, drawn, reason = None, None, None, None, None
    for variant in range(MAX_VARIANT_ATTEMPTS):
        config, dna_tags, drawn = candidate_builder.build_candidate(dna_combo, variant=variant)

        if memory.has_been_rejected_before(dna_combo, drawn):
            continue

        dup_warnings = memory.check_duplicate_against_library(config.concepts_used)
        if dup_warnings:
            outcome, reason = "rejected", (
                f"structural duplicate of existing strategy '{dup_warnings[0]['strategy_name']}' "
                f"({dup_warnings[0]['similarity_pct']}% similar concepts)"
            )
            break

        errors = validate(config)
        if errors:
            outcome, reason = "rejected", f"failed the standard strategy validator: {'; '.join(errors)}"
            break

        discovery_batch_id = run_batch_fn(
            config, exchange, symbols, settings, split["discovery_start_ms"], split["discovery_end_ms"])
        validation_batch_id = run_batch_fn(
            config, exchange, symbols, settings, split["validation_start_ms"], split["validation_end_ms"])
        discovery_metrics = validation_gate.compute_period_metrics(discovery_batch_id)
        validation_metrics = validation_gate.compute_period_metrics(validation_batch_id)
        gate_result = validation_gate.evaluate(discovery_metrics, validation_metrics, config.risk_reward)

        if gate_result["passed"]:
            strategy_id = strategy_library.create(config, tags=[DISCOVERED_STRATEGY_TAG])
            outcome, reason = "accepted", "passed both out-of-sample periods independently"
        else:
            outcome, reason = "rejected", "; ".join(gate_result["reasons"])
        break  # a real backtest ran for this variant either way -- this cycle's attempt is done
    else:
        outcome, reason = "rejected", (
            f"every variant of combo {dna_combo} up to {MAX_VARIANT_ATTEMPTS} was already rejected before "
            "-- no new concept variation left to try this cycle"
        )

    attempt_id = uuid.uuid4().hex[:12]
    now_iso = _now_iso()
    memory.record_outcome(
        attempt_id, dna_combo, drawn or [], variant if drawn else 0, outcome, reason, now_iso,
        strategy_id=strategy_id,
        discovery_metrics=gate_result["discovery_metrics"] if gate_result else None,
        validation_metrics=gate_result["validation_metrics"] if gate_result else None,
    )

    report = explainability.build_report(
        dna_combo, drawn or [], chosen, gate_result, outcome, strategy_id=strategy_id,
        early_rejection_reason=reason if gate_result is None else None,
    )
    report["status"] = outcome
    report["cycle_id"] = cycle_id
    storage.save_self_learning_cycle(cycle_id, started_at, _now_iso(), status="completed", report_json=_dump(report))
    return report


def _dump(obj):
    import json
    return json.dumps(obj)
