"""Phase 2 (BACKTESTING_MASTER_SPEC.md Requirement 13, Strategy
Verification Engine): confirms every rule stored in a strategy's saved
JSON is actually REACHED and evaluated by the Rule Engine during a real
backtest -- not just that it theoretically could be, but that it WAS, at
least once. Uses ConfiguredStrategy's optional `_trace` hook
(configured_strategy.py) rather than re-implementing any evaluation logic
of its own, so this can never disagree with what the real engine did.
"""

_BUCKETS = ("entry_conditions", "long_entry_conditions", "short_entry_conditions",
            "exit_conditions", "confirmation_conditions")


def describe_condition(cond):
    if cond.type == "concept":
        return f"concept:{cond.name}" + (f"({cond.direction})" if cond.direction else "")
    if cond.type == "indicator_compare":
        return f"indicator_compare:{cond.indicator} {cond.op} {cond.value}"
    if cond.type == "price_compare":
        return f"price_compare:price {cond.op} {cond.indicator}"
    if cond.type == "indicator_vs_indicator":
        return f"indicator_vs_indicator:{cond.indicator} {cond.op} {cond.indicator2}"
    if cond.type == "session":
        return f"session:{cond.name}"
    if cond.type == "trend":
        return f"trend:{cond.direction}"
    if cond.type == "raw":
        return f"raw:{cond.text}"
    return f"{cond.type}:?"


def install_coverage_trace(strategy):
    """Wires up strategy._trace to record per-condition evaluation counts,
    keyed by Python object identity -- the SAME Condition instances the
    strategy's own config already holds, so results map back to exactly
    the rules in the saved JSON with no re-matching/guessing involved.
    Returns the counts dict: {id(cond): {"evals": int, "true": int}},
    live-updated as the backtest runs -- read it AFTER run_backtest()
    returns."""
    counts = {}

    def _record(cond, result):
        c = counts.setdefault(id(cond), {"evals": 0, "true": 0})
        c["evals"] += 1
        if result:
            c["true"] += 1

    strategy._trace = _record
    return counts


def verify_rule_coverage(config, counts):
    """Cross-references every condition actually stored in `config`
    against what `counts` recorded during a real run. Returns one finding
    dict per rule: {bucket, index, condition, status, reason}.

    status is one of:
    - "SKIPPED": never reached at all during the run -- always reported,
      this is the "if any rule is skipped, report it" case. A type="raw"
      condition is SKIPPED unconditionally and by construction: _eval()
      returns False for it immediately, without the Rule Engine doing any
      real evaluation, so it can never be anything else.
    - "NEVER_TRUE": the Rule Engine did reach and evaluate it, but it was
      never once true across the whole run -- informational, not
      necessarily a bug (a rare structural event, or a rule guarded by an
      earlier AND-condition that's usually false), but worth surfacing.
    - "OK": evaluated and true at least once -- genuinely exercised."""
    findings = []
    for bucket in _BUCKETS:
        for idx, cond in enumerate(getattr(config, bucket, []) or []):
            desc = describe_condition(cond)
            if cond.type == "raw":
                findings.append({
                    "bucket": bucket, "index": idx, "condition": desc, "status": "SKIPPED",
                    "reason": "type=\"raw\" -- not executable; the Rule Engine always treats "
                              "this as False without ever really evaluating it",
                })
                continue
            c = counts.get(id(cond))
            if c is None or c["evals"] == 0:
                findings.append({
                    "bucket": bucket, "index": idx, "condition": desc, "status": "SKIPPED",
                    "reason": "never reached during the backtest -- likely short-circuited by an "
                              "earlier always-false condition in the same AND-gated rule set, or "
                              "this bucket was never reached at all (e.g. exit_conditions with a "
                              "position that never opened)",
                })
            elif c["true"] == 0:
                findings.append({
                    "bucket": bucket, "index": idx, "condition": desc, "status": "NEVER_TRUE",
                    "reason": f"evaluated {c['evals']} times, never once true",
                })
            else:
                findings.append({
                    "bucket": bucket, "index": idx, "condition": desc, "status": "OK",
                    "reason": f"evaluated {c['evals']} times, true {c['true']} times",
                })
    return findings
