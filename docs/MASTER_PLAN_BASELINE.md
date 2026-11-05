# MASTER PLAN BASELINE (F2): measured BEFORE any Master Plan change

Deployed commit on Cloud: `c035ca3` (Day 7). Measured 2026-11-05 20:07-21:10 UTC, mostly from Render logs and metrics (read-only), the laptop and the Neon database.
Sample size: one Render instance (`kddpt`) over about one hour, plus the Day 6/7 scan history. Treat these as a snapshot, not an average.

## Cloud
| Metric | Baseline | Source |
|---|---|---|
| Complete scans, last 24 h | 1 (19:35:57 UTC, 897 s, **only 10 coins**) | Render logs, text "scan finished" since 2026-11-05 12:00 |
| Scan duration, earlier history | cold 1,000-1,941 s, warm 655-865 s (6 complete scans) | docs/SCAN_PROFILE.md sections 12-14 |
| Prefetch phase, current instance | **3,828 s** for 50 coins (4 workers), finished 21:06:06 | log `scan phase prefetch: 50 coins warmed with 4 workers in 3828s` |
| Scanner stalls | "no progress for 523 s" (20:46) and "190 s" (21:00), both in `_prefetch_candles` engine.py:412 | Render logs |
| Memory (Render metric) | 536 MB at 20:30 and 21:00 (30-min points) | get_metrics memory_usage |
| Memory (app memory guard) | RSS 517-518 MB at 20:36, 20:47, 20:55, 21:01 (hard guard 450 MB active the whole time) | `[memory-guard]` lines |
| Errors per hour, 20:07-21:07 | **about 60 error lines** (one page of 100 was not full). All except one were Neon `OperationalError` (`SSL SYSCALL error: EOF detected` / `timeout expired`). By source: telegram-commands poll ~40, Telegram hourly sweep ~6, Telegram retry sweep ~6, watchdog ~5, challenge-lifecycle ~4, daily-report 1, cloud-sync 1, status-ping 1, auto-downgrade 1 | Render logs level=error |
| Other noise | `[exchange-breaker] okx OPEN for 120s` about 6 times in 15 min (15m candle pages); bot probes `HEAD /search`, `/admin`, `/pricing`, `/wp-admin` -> 307 | Render logs |
| housekeeping(light) | 305-487 s per run (should be seconds) | Render logs |
| `/health` latency from the laptop | **3 of 3 attempts timed out after 60 s** (21:06 UTC), while the app logged one `GET /health 200` at 21:07 | curl `--max-time 60` |
| Neon itself | reachable from the laptop: connect + 2 queries 2.7 s, 13 connections, database size 26.8 MB | scratchpad neon_ping.py (password masked) |

**Reading (careful):** the Cloud instance is over its memory budget (517-536 MB on a 512 MB plan). Every database call fails while the same database is fine from the laptop, so the problem is on the instance side: memory pressure plus slow or broken new SSL connections on 0.15 CPU. That is NOT VERIFIED as the single cause. The 20-day 1m re-download (master plan section 3) and the 3,828 s prefetch match this picture.

## Local (F2 part 2, measured 2026-11-05 ~22:25 UTC on the UNCHANGED code, D:\sindhu_clean at 7388c1b)
Isolated QA server on port 8422 with a fresh empty data folder `D:\sindhu_runtime\smoke_data_f2`, logged in with a throwaway QA test
account (credentials only in that folder). `python tools/dashboard_baseline.py --base http://127.0.0.1:8422 --runs 3`.
The full test suite was running at the same time, so the timings are indicative (CPU shared).

| Metric | Baseline | Source |
|---|---|---|
| Home page time until the network is quiet | 6.44 s first load, then 3.04 s and 2.91 s (median 3.04 s) | tools/dashboard_baseline.py |
| Requests per home load | 29-30, of which 24-25 API calls | same |
| Transferred per home load | 1.0-1.1 MB; biggest: app.js 943 KB, /api/backtesting/strategies 104 KB, app.css 62 KB | same |
| Console errors | 0 | same |
| DB queries per home-page load | NOT MEASURED: local runs on SQLite (no counters); the Postgres counters exist only in the Cloud scan logs ([scan-stages]) | - |
| 1m download volume per scan | Cloud logs 5 Nov: 20 days = 28,806 rows / 97 pages / 49 s per coin (LTC example); now also counted per scan in [scan-stages] "candles: ..." (master plan A2) | Render logs |
