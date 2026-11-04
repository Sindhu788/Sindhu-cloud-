[PROGRESS 88% | steps 24/27 done | now: Step 27 closeout (full suite, CI, final push) | status: RUNNING | elapsed ~5h | blockers: Cloud scans still do not complete]

# Day 4 checkpoint (4 Nov 2026, ~17:45 UTC)
Pushes used: 2 of 3 (`06d2051`, `ab5b297`); the third is the closeout push.
| Step | State | Evidence |
|---|---|---|
| 1-2 baseline, inventory | DONE | docs/DAY4_BASELINE.md |
| 3-4 profile, attribution | DONE | docs/SCAN_PROFILE.md sections 1-5 (CPU-bound locally 85 %; Render waits on the exchange) |
| 5 throttle A/B | DONE - removed | SCAN_PROFILE section 7, D32 |
| 6 less work, identical output | DONE | golden check PASS (4 coins, 62 strategies, 49 candidates); pool 3,310 -> ~4 connections; memo -10 % local time |
| 7 memory | PARTIAL (not counted) | guard + 5 tests; local peak 187 -> 200 MB with memo; Render 322-338 MB (target under 300 MB NOT met) |
| 8 /health under load | DONE | tests/test_health_under_load.py fails on the old code, passes now |
| 9 push + Cloud measurement | DONE as "still not completing" | SCAN_PROFILE section 9: prefetch 197 s, coin 1 about 20 min, 0 complete scans |
| 10-14, 16 signal quality | DONE | docs/SIGNAL_QUALITY.md |
| 15 token/service conflict | DONE with NOT VERIFIED parts | OWNER_TODO "Token/service conflict check" |
| 17-22 strategy forensics | DONE | docs/STRATEGY_FORENSICS.md |
| 23 CEO page load | NOT DONE (dropped for time) | - |
| 24 owner readiness | DONE | OWNER_TODO "Owner readiness table" |
| 25 backup + restore | DONE | 51 tables exported, 49 restored, 0 mismatched, 11,909 rows |
| 26 security review | DONE | docs/SECURITY_REVIEW.md; fixes: login throttle, Secure cookie, security headers |
| 27 closeout | IN PROGRESS | |
Test results so far: 2,419 passed / 2 skipped / 0 failed (4 shards) on the tree of push 1; the final full run is in progress.
Open problems: Cloud scans do not complete (waits on the exchange inside one small candle request, cause not yet known; retry logging ships in the final push); no external pinger; owner chat id not set; memory 322-338 MB.
