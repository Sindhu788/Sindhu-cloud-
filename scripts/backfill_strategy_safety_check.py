"""One-time backfill (not part of the app): re-runs the Automatic Strategy
Safety Check against every strategy currently in the library and updates
each one's meta.json safety_status/safety_reasons in place (no new
version is created -- this only refreshes the cached status field so it
matches strategy_library.recheck_safety()'s live result; strategy_library
.create()/save_version() run the check automatically on every future
save, so this script never needs to be re-run except after a code change
to the check itself).

Usage: python scripts/backfill_strategy_safety_check.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest_engine import strategy_library


def main():
    metas = strategy_library.list_all()
    print(f"Re-checking {len(metas)} existing strategies in the library...\n")

    passed, failed = [], []
    for meta in metas:
        result = strategy_library.recheck_safety(meta["id"])
        if result["passed"]:
            passed.append(meta["name"])
        else:
            failed.append((meta["name"], meta["id"], result["reasons"]))

    print(f"{'=' * 70}\nRESULT\n{'=' * 70}")
    print(f"Re-checked: {len(metas)}")
    print(f"Passed (Ready):        {len(passed)}")
    print(f"Failed (Needs Review): {len(failed)}\n")

    if passed:
        print("PASSED:")
        for name in passed:
            print(f"  - {name}")
        print()

    if failed:
        print("FAILED (exact reasons):")
        for name, sid, reasons in failed:
            print(f"\n  {name} ({sid})")
            for r in reasons:
                print(f"    - {r}")

    print(f"\n{'=' * 70}")
    print("meta.json updated for every strategy above -- this status is now "
          "permanent and will stay current automatically: strategy_library."
          "create()/save_version() run this same check on every future save, "
          "and mtf_worker.run_one_symbol()/verification_engine.run_verification() "
          "independently re-check and REFUSE to backtest any strategy that fails, "
          "regardless of what meta.json says.")


if __name__ == "__main__":
    main()
