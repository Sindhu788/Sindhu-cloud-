# MASTER PLAN RESULTS (X1): before vs after

Before: docs/MASTER_PLAN_BASELINE.md (Cloud on c035ca3, 5 Nov ~20:07-21:10 UTC; local dashboard on 7388c1b).
After: Cloud on **02d12c3** (deploy D2, live 2026-11-05 23:09 UTC), measured 6 Nov 00:16-03:20 UTC from Render logs, `/health` and
the database (read-only); local dashboard on this branch (Part C). Sample: ONE instance over ~4 hours, 5 complete scans. Not a
long-term average.

| Metric | Before | After | Source |
|---|---|---|---|
| Complete scans | 1 in 24 h (10 coins only) | **5 in a row, all 50 coins, 0 errors** (00:16, 00:55, 01:40, 02:18, 02:54 UTC) | Render logs "scan finished" |
| Scan time, cold start | 1,000-1,941 s (older history); prefetch alone 3,828 s on 5 Nov | 4,038 s (prefetch capped at 600 s) | [scan-stages] |
| Scan time, warm | 655-865 s (10-coin scans, older history) | 2,128-2,616 s for 50 coins (~43-52 s per coin) | [scan-stages] |
| Candle download per warm scan | full 20-day 1m re-download per coin (97 pages, ~49 s per coin) | **159-254 requests, 2,446-3,706 rows, 59-94 s** (cold scan: 2,342 requests, 651,156 rows) | [scan-stages] "candles:" |
| Memory | 517-536 MB (over the 512 MB plan) | **428-435 MB steady** (cold scan peak 439 MB) | [memory-guard], [scan-stages] rss |
| Error lines per hour | ~60 (Neon connect errors) | **0** (00:30-01:30 UTC) | Render logs level=error |
| Scanner stalls (>120 s without progress) | 523 s and 190 s in `_prefetch_candles` | 139 s once in the wallet settle (fixed in 754199e) and 139 s once in the CoinGecko top-coins call (not yet covered by a deadline) | Render logs |
| `HEAD /health` | 405 | 200 (no 405 in the logs since D1) | curl -I, Render logs |
| Bot probes (/wp-admin ...) | 307 redirect + database session lookup | tiny 404, no database | curl |
| `/health` latency from the laptop (Pakistan) | 3 of 3 timed out after 60 s | **avg 0.70 s, max 1.07 s, 10 of 10 OK** | curl, 10 samples |
| Database per warm scan | not measured before | 8,701-11,135 statements (929-1,240 s) + 8,473-10,742 commits (435-580 s) = about 60-65 % of the scan | [scan-stages] "db:" |
| Database size | 26.8 MB | 30.0 MB (5.9 % of 0.5 GB) | weekly_backup.py --check-only |
| Home page (local) | 3.04 s, 30 requests, 25 API calls, 1.1 MB | 0.40-0.46 s, 16 requests, 10 API calls, 261 KB | tools/dashboard_baseline.py |
| Log lines per hour | NOT MEASURED as a total | per-series candle lines removed (were 100+ per cold scan) | - |

## What this means
- The stability problems are fixed on this sample: no Neon errors, memory under the plan limit, every scan complete.
- Warm scans still take ~36-44 minutes for 50 coins. The biggest remaining cost is the **database round trip**: Render runs in
  Oregon, Neon in us-east-2 (Ohio). The measured ~107 ms per statement and ~52 ms per commit fit that distance (NOT VERIFIED as the
  only cause). Two ways forward:
  1. (owner, biggest effect) Run the Cloud service in Render's **Ohio** region next to Neon. A Render service cannot change region,
     so this means a new free service in Ohio with the same env vars, then pointing UptimeRobot at it.
  2. (code, later) Group each coin's database writes into one transaction (about 1 commit per coin instead of ~190).
- Memory is steady at ~430 MB: under the 450 MB guard, but NOT at the ~350 MB target (P11 partial).

## After D3 (3eabeac, live 2026-11-06 03:39 UTC)
| Scan finished (UTC) | Duration | Coins / errors | DB statements + commits | Candle requests | RSS |
|---|---|---|---|---|---|
| 04:36 (cold start) | 3,450 s | 50 / 0 | 7,428 (830 s) + 7,185 (387 s) | 2,398 | 423 MB |
| 05:10 | 1,948 s | 50 / 0 | 8,633 (975 s) + 8,272 (459 s) | 198 | 409 MB |
| 05:43 | 1,964 s | 50 / 0 | 8,002 (867 s) + 7,745 (404 s) | 166 | 415 MB |

Warm scans dropped from 2,128-2,616 s (D2) to ~1,950 s after the wallet settle cache. No stalls in these three scans.
The CoinGecko retry cap (P5 follow-up, commit 20736c4) is committed but NOT deployed: a push restarts Cloud into a ~57-minute cold
scan, so it waits for the next deploy that is needed anyway.
