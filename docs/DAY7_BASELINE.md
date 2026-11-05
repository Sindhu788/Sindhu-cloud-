# Day 7 baseline (5 Nov 2026) - independent re-check of the Day 6 claims

| Claim (Day 6 report) | How verified today | Result |
|---|---|---|
| Metric bug fixed (legs counted as trades); no label changed | tests `test_metrics.py` (10) green; labels recomputed from the stored runs | **VERIFIED** |
| 47 coins, 10 months, costs: 0 ROBUST, 1 FRAGILE, 36 FAILED, 5 INSUFFICIENT_DATA | recomputed final labels from `protocol_results.json` + `protocol_rigor.json` | **VERIFIED** (FAILED 36, INSUFFICIENT_DATA 5, FRAGILE 1) |
| Ichimoku 1d Indicator-Exit FRAGILE, PF 1.09, interval 0.71-1.61 | table in docs/STRATEGY_FORENSICS.md generated from the same files | **VERIFIED** (re-examined in Step 12) |
| Sep-Oct 2026 holdout NOT clean | docs/BACKTEST_PROTOCOL.md section 8; `manifest/holdout_access.log` does not exist (the loader was never asked) | **VERIFIED** (not clean because of Day 4 analyses, not because of the loader) |
| Forward test pre-registered from 6 Nov 2026, evaluation not before 5 Jan 2027 | `manifest/forward_registry.json` exists, candidates list empty | **VERIFIED** (no candidate is registered yet) |
| Cloud build 8ac219f: scans 1,046 s (cold) and 702 s (warm), 0 errors | Render logs "scan finished" | **VERIFIED**; plus a third complete scan **1,047 s** (cold, 05:54 UTC on the docs-only build 37859e2) |
| Cloud now runs | `/health` | commit **37859e2** (docs push after 8ac219f), `engine_running true`, `started_at` 05:37 UTC |
| Memory 439-444 MB vs 407-411 MB on Day 5, "not tied to any code change" | Render logs "memory-guard" for 4 instances | **VERIFIED as a range, CONTRADICTED as a regression**: a fresh instance on identical code read **415-416 MB** (05:47-05:54 UTC); readings across builds: 407-411, 439-444, 415-416 MB (see Step 8) |
| Hard guard 450 MB of 512 MB | log text "RSS 441 MB >= 400 MB (soft)" | soft guard 400 MB confirmed in the log text; hard 450 MB per Day 5 notes (not re-read in code today) |
| 72 % of fetched pages are 1-minute candles | local profile JSON (`pages_by_interval`) | **VERIFIED**: 961 of 1,331 pages = 72.2 % (local mock exchange, 10 coins) |
| At least 11 public signals sent, 5 more on 4 Nov 20:21-20:42 UTC | Cloud database export (`telegram_message_log`, trigger automatic, success) | **CONTRADICTED**: **12** automatic signals sent in total. Six after the Day 4 audit: 19:44, 20:21, 20:27, 20:29, 20:32, 20:41 UTC on 4 Nov |
| All labelled "Strong, 2/2 factors" | `explanation_text` of the 12 messages | **VERIFIED**: 12 of 12 say "2/2 confluence factors", the two being "Strategy not paused" and "No other strategy crowding"; the regime and pattern-history factors are not counted in any of them |
| Stored confidence does not predict wins (AUC 0.463) | re-ran `tools/confidence_analysis.py` | **VERIFIED**: AUC 0.463, interval 0.428-0.497, 1,132 trades |
| Free instance slept and restarted 3 times overnight | Render logs "Started server process" | **VERIFIED, understated**: 10 process starts between 19:34 UTC 4 Nov and 05:37 UTC 5 Nov = about 5-6 deploys + 4 wake-ups from sleep (20:12, 02:57, 03:42, 04:59 UTC) |
| Paper P&L since the $100 reset NOT VERIFIED | Cloud database export: `paper_balance_resets` (reset 3 Nov 22:49 UTC), `paper_positions`, `paper_account_state` | **NOW VERIFIED**: 34 closed trades since the reset, 7 wins (20.6 %), net **-$11.26**, profit factor 0.17; 61 positions open. Very small sample (2.3 days) |
| /api/ops/pinger status | `GET /api/ops/pinger` | **NOT VERIFIED**: HTTP 401 "login required"; I do not use your login |
| OKX global unreachable from this PC | `curl https://www.okx.com/...` | still unreachable on 5 Nov (Day 6); not re-run |
| Local app health at 127.0.0.1:8420 | health check | **CONTRADICTED at start**: not running at the start of Day 7 (it never survives a session end, see docs/RUNBOOK.md 11e); restarted |
| Git state | local `recovery/clean` HEAD vs `origin/codex/trading-intelligence` | origin = **37859e2** = Cloud; local branch has the same content plus Day 7 commits |
| Free disk | `df` / PowerShell | D: 51 GB free of 100 GB; C: 62.8 GB free |
| Fast test subset | 13 test files | **78 passed** |
| Day 6 dataset claim 24.52 M rows, 748-file | full re-hash of ALL files (Step 3) | **VERIFIED**: 748 files (after the incremental update of 4 Nov), **24,587,700 rows**, 0 hash mismatches, 0 row mismatches |

**Day 6 claim corrections to carry forward:** public signals sent = 12 (not 11); all 12 came from strategies labelled FAILED (details in Step 10); memory is a 407-444 MB range, not a regression; paper P&L since reset is now known.
