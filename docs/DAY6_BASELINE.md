# Day 6 baseline (5 Nov 2026) - independent re-check of the Day 5 claims

| Claim (Day 5 report) | How verified | Result |
|---|---|---|
| Cloud runs commit 2c3882c, engine running | `GET /health` on Cloud | **VERIFIED** (`commit 2c3882c`, `engine_running true`). `started_at` 03:42 UTC = the free instance had slept and restarted since Day 5, i.e. nothing keeps it awake yet (owner's pinger) |
| Cloud complete scan 865 s (10 coins, 0 errors) vs 1,941 s | Render logs, text "scan finished" | **VERIFIED**: 1941 s (20:45 UTC, cold) and 865 s (21:27 UTC, on commit 8185853). Only these two complete scans exist since the change (sample size 2); the 865 s one ran while a keep-alive was pinging |
| Memory about 410 MB, guard hard 450 MB | Render logs "memory-guard" | **VERIFIED**: RSS 407-411 MB (soft 400 MB guard triggers); 487 MB seen on the earlier version |
| /api/ops/pinger status | `GET /api/ops/pinger` | **NOT VERIFIED**: endpoint answers 401 "login required"; no credentials used |
| Local app at 127.0.0.1:8420 | health check | **CONTRADICTED at start**: app was NOT running at the start of Day 6 (dead after the Day 5 session). Restarted with the documented launcher in 14 s (see Step 2) |
| Git: local HEAD vs deployed vs origin | `git log`, `ls-remote`, /health | clean-tree HEAD `7b35e7b` (docs commit, equal content to deployed except docs); origin and deployed = `2c3882c`. **VERIFIED**; working tree clean |
| Free disk | `df` | D: 52 GB free of 100 GB. **VERIFIED** |
| Dataset: 700 files, hashed | file walk + manifest | **VERIFIED**: 700 parquet files on disk, manifest 556 month + 144 day entries 'ok' + 50 entries 'absent' (no file) |
| Dataset: 24.3 M rows | sum of manifest rows | **CONTRADICTED (small)**: manifest sums to 24,518,580 rows |
| Dataset hashes match | re-hashed 60 random 'ok' files (34 coins) and read parquet row counts | **VERIFIED**: 0 hash mismatches, 0 row mismatches, 0 missing (sample 60 of 700) |
| Full suite 2,459 passed | not re-run in full today | **NOT RE-VERIFIED** (full suite re-run at closeout); fast subset today: 38 passed |
| Backtest 0 ROBUST / 32 FAILED / 10 INSUFFICIENT | re-read docs/BACKTEST_RESULTS.md | recorded, **to be re-checked after the metrics audit (Steps 4-5)**: the label depends on a metric that already contradicts itself |

## Work plan: cut Day 5 deliverables mapped to Day 6 steps
| Cut Day 5 deliverable | Day 6 step |
|---|---|
| Timeframe report | Step 10 |
| Shortlist (keep / watch / pause) | Step 11 |
| Pipeline document | Step 18 |
| Confidence investigation | Step 16 |
| Signal-rule flags | Step 17 (and Step 13 for the gate fix) |
| Dashboard page | Step 20 (NICE) |
| Owner readiness / weekly status | Step 21 (and OWNER_TODO) |
| Backups, security review, docs | closeout (Steps 22-28 of this prompt are unknown, see below) |

**The Day 6 prompt text stops in the middle of Step 21. Steps 22-28 and the final-report format were never received; they cannot be done or counted.**
