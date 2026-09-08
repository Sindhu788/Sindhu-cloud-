"""One-time backfill (not part of the app): computes and caches
validator_status/validator_errors/fixed_rr (and refreshes safety_status/
safety_reasons) into every existing strategy's meta.json, via
strategy_library.recheck_safety() -- same pattern as
backfill_strategy_safety_check.py, extended to cover both activation
gates now that both are cached (see strategy_library._compute_activation_gates).

Needed once because every strategy saved before this cache existed has
neither validator_status nor fixed_rr in its meta.json yet; every future
create()/save_version() populates them automatically, so this script
never needs to be re-run except after a code change to either check.

Usage: python scripts/backfill_validator_status.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest_engine import strategy_library


def main():
    metas = strategy_library.list_all()
    print(f"Backfilling activation-gate cache for {len(metas)} existing strategies...\n")

    ready, needs_review, errored = [], [], []
    for meta in metas:
        try:
            strategy_library.recheck_safety(meta["id"])
        except Exception as e:
            errored.append((meta["name"], meta["id"], repr(e)))
            continue
        refreshed = strategy_library.get_meta(meta["id"])
        if refreshed.get("safety_status") == "ready" and refreshed.get("validator_status") == "ready":
            ready.append(meta["name"])
        else:
            needs_review.append((meta["name"], meta["id"],
                                  refreshed.get("safety_reasons") or [], refreshed.get("validator_errors") or []))

    print(f"{'=' * 70}\nRESULT\n{'=' * 70}")
    print(f"Backfilled: {len(metas)}")
    print(f"Ready (both gates pass): {len(ready)}")
    print(f"Needs review/clarification: {len(needs_review)}")
    print(f"Errored (could not load/compute): {len(errored)}\n")

    if needs_review:
        print("NEEDS REVIEW/CLARIFICATION (exact reasons):")
        for name, sid, safety_reasons, validator_errors in needs_review:
            print(f"\n  {name} ({sid})")
            for r in safety_reasons:
                print(f"    [safety] {r}")
            for r in validator_errors:
                print(f"    [validator] {r}")

    if errored:
        print("\nERRORED:")
        for name, sid, err in errored:
            print(f"  {name} ({sid}): {err}")

    print(f"\n{'=' * 70}")
    print("meta.json updated for every strategy above -- validator_status/fixed_rr "
          "are now cached and will stay current automatically: strategy_library."
          "create()/save_version() compute both gates on every future save.")


if __name__ == "__main__":
    main()
