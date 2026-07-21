"""One-time backfill: populate Condition.role on every already-saved
strategy's conditions, without calling AI again.

Context: Condition.role tells the backtest engine which declared timeframe
(bias/trend/analysis/entry) a concept condition belongs to -- without it,
every concept silently evaluates on the entry timeframe only, no matter
what the strategy's own text says. The engine and both import pipelines
(deterministic parser, AI-native) now populate role going forward, but
every strategy saved BEFORE that fix still has role=None on every
condition. This script re-derives it deterministically from each
strategy's own stored raw_text (backtest_engine.strategy_parser.
repair_condition_roles -- the exact same logic the AI-native import path
now runs on every fresh import), and saves a new version only for
strategies where something actually changed.

Usage:
    python scripts/backfill_condition_roles.py            # dry run (report only)
    python scripts/backfill_condition_roles.py --apply     # actually save new versions
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest_engine import strategy_library
from backtest_engine.strategy_parser import repair_condition_roles


def _describe_roles(config):
    out = []
    for bucket in ("entry_conditions", "exit_conditions", "confirmation_conditions"):
        for cond in getattr(config, bucket):
            if cond.type == "concept":
                out.append(f"{bucket}:{cond.name}={cond.role or 'entry(default)'}")
    return out


def main():
    apply = "--apply" in sys.argv
    metas = strategy_library.list_all()
    print(f"Scanning {len(metas)} saved strategies...\n")

    changed_count = 0
    for meta in metas:
        strategy_id = meta["id"]
        config = strategy_library.load(strategy_id)
        before = _describe_roles(config)
        changed = repair_condition_roles(config)
        after = _describe_roles(config)

        if not changed:
            print(f"[no change] {config.name} ({strategy_id})")
            continue

        changed_count += 1
        print(f"[CHANGED]   {config.name} ({strategy_id})")
        print(f"            before: {before}")
        print(f"            after:  {after}")
        if apply:
            new_version = strategy_library.save_version(strategy_id, config)
            print(f"            -> saved as version {new_version}")
        else:
            print("            -> dry run, not saved (pass --apply to save)")
        print()

    print(f"\n{changed_count}/{len(metas)} strategies had at least one condition's role backfilled.")
    if not apply and changed_count:
        print("Re-run with --apply to save these as new versions.")


if __name__ == "__main__":
    main()
