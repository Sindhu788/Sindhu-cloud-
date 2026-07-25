"""Runs the Self-Correcting Import Pipeline (ai_integration/
self_correction.py) over every strategy already sitting in the Strategy
Library, not just newly imported ones.

Every strategy currently failing the automatic safety check is put through
the same three levels a fresh import now gets:
  Level 1 -- deterministic structural repairs, zero AI calls
  Level 2 -- one small targeted AI call, scoped to what Level 1 left
  Level 3 -- flagged for the user in plain language (last resort)

A repaired strategy is saved as a NEW VERSION (never an overwrite -- the
original stays in the version history and can be inspected or restored).

Usage:
  python scripts/self_correct_library.py            # report only, changes nothing
  python scripts/self_correct_library.py --apply    # save repairs as new versions
  python scripts/self_correct_library.py --apply --no-ai   # Level 1 only
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtest_engine import strategy_library, validator
from backtest_engine.strategy_safety_check import run_safety_check
from ai_integration import self_correction


def main():
    apply_changes = "--apply" in sys.argv
    use_ai = "--no-ai" not in sys.argv

    metas = strategy_library.list_all()
    print(f"Scanning {len(metas)} strategies in the library "
          f"({'APPLYING repairs' if apply_changes else 'DRY RUN -- nothing will be saved'}, "
          f"Level 2 AI {'enabled' if use_ai else 'disabled'})\n")

    already_clean, results = [], []
    for meta in metas:
        try:
            cfg = strategy_library.load(meta["id"])
        except Exception as exc:
            print(f"  ! could not load {meta['name']}: {exc!r}")
            continue
        if run_safety_check(cfg)["passed"]:
            already_clean.append(meta["name"])
            continue

        before_reasons = run_safety_check(cfg)["reasons"]
        outcome = self_correction.self_correct(cfg, use_ai=use_ai)
        results.append({
            "id": meta["id"], "name": meta["name"], "before_issue_count": len(before_reasons),
            "level": outcome["level"], "status": outcome["status"],
            "repairs": outcome["repairs"], "remaining": outcome["remaining_issues"],
            "user_message": outcome["user_message"],
            "validator_errors": validator.validate(cfg),
        })
        if apply_changes and outcome["status"] == "ready":
            strategy_library.save_version(meta["id"], cfg)

    by_level = {1: [], 2: [], 3: []}
    for r in results:
        by_level.setdefault(r["level"], []).append(r)

    print("=" * 78)
    print("PER-STRATEGY RESULT")
    print("=" * 78)
    for r in results:
        print(f"\n{r['name']}  ({r['id']})")
        print(f"  before: needs_review ({r['before_issue_count']} issue(s))")
        print(f"  after:  {r['status']}   [resolved at LEVEL {r['level']}]")
        for fix in r["repairs"]:
            print(f"    fixed:   {fix}")
        for rem in r["remaining"]:
            print(f"    REMAINS: {rem}")
        if r["user_message"]:
            print(f"    message to user: {r['user_message']}")

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print(f"  Already clean (no action needed): {len(already_clean)}")
    print(f"  Needed correction:               {len(results)}")
    print(f"    fixed at LEVEL 1 (no AI call): {len(by_level.get(1, []))}")
    print(f"    fixed at LEVEL 2 (1 AI call):  {len(by_level.get(2, []))}")
    print(f"    LEVEL 3 (flagged for user):    {len(by_level.get(3, []))}")
    for r in by_level.get(3, []):
        print(f"      - {r['name']}: {r['user_message']}")

    tel = self_correction.get_telemetry()
    print(f"\n  Lifetime telemetry: level1={tel['level_1_auto_fixed']} "
          f"level2={tel['level_2_targeted_ai']} level3={tel['level_3_flagged']} "
          f"clean={tel['level_0_clean']}  (Level 2 rate: {tel['level_2_rate_pct']}%)")
    if not apply_changes:
        print("\n  DRY RUN -- nothing was saved. Re-run with --apply to save these repairs.")


if __name__ == "__main__":
    main()
