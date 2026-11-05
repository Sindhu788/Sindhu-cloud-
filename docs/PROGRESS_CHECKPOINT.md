[PROGRESS 42% | steps 12/28 done | now: waiting for the 50-coin run (71%), then Steps 8-11, 12, 14 | status: WAITING | elapsed ~3h30m | blockers: none]

# Day 6 checkpoint (5 Nov 2026)
NOTE: the Day 6 prompt is cut off inside Step 21; Steps 22-28 and the final-report format are unknown and cannot be done or counted.
| Step | State | Evidence |
|---|---|---|
| 1 baseline | DONE | docs/DAY6_BASELINE.md (local app was found dead; dataset 24.52 M rows, not 24.3 M; pinger endpoint NOT VERIFIED - login) |
| 2 local app | PARTIAL | normal start 14 s, duplicate refused, kill recovery 22 s; sleep/wake NOT VERIFIED; docs/RUNBOOK.md 11d |
| 3 plan | DONE | mapping table in DAY6_BASELINE.md |
| 4 metrics audit | DONE | cause: legs counted as trades + per-leg R; tools/recompute_metrics.py; docs/BACKTEST_RESULTS.md "Metrics audit" |
| 5 metrics fix | DONE | data_platform/metrics.py, tests/test_metrics.py (9, one fails on old code); labels unchanged |
| 6 rigour layer | DONE | data_platform/rigor.py + protocol_rigor.py, tests/test_rigor.py (8); docs/BACKTEST_PROTOCOL.md section 10 |
| 7 holdout audit | DONE | NOT CLEAN (Day 4 used Sep-Oct for 10 strategies x 3 coins); forward test pre-registered (sections 8-9; manifest/forward_registry.json) |
| 8 50-coin re-run | RUNNING | 2100 runs, 71% at last check; results come from protocol_analyze + protocol_rigor |
| 9-11 reports | WAITING | need the run |
| 12 scan speed | NOT STARTED | needs a quiet machine (run is using 3 workers) |
| 13 gate flag analysis | DONE | docs/SIGNAL_QUALITY.md D6-1 (regime shares measured; past-signal effect NOT VERIFIED) |
| 14 push 1 + Cloud measurement | NOT STARTED | after Step 12 |
| 15 source mismatch | DONE | OKX global unreachable (NOT VERIFIED); OKX US stand-in table; fingerprint logger OFF + tool + 3 tests |
| 16 confidence | DONE | AUC 0.463 out of sample; docs/SIGNAL_QUALITY.md D6-2; SINDHU_HIDE_CONFIDENCE flag OFF + 3 tests |
| 17 signal rules | DONE | paper_trading/signal_rules.py OFF; 3 of 6 sent signals would have been withheld; 6 tests |
| 18 pipeline doc + research-only flag | DONE | docs/PIPELINE.md; SINDHU_RESEARCH_ONLY_TIMEFRAMES OFF + 3 tests |
| 19 candidate tool | DONE | data_platform/candidate_eval.py + sandbox.py; 7 isolation/dossier tests; proof run on one existing strategy |
| 20 health page | NOT STARTED (NICE) | |
| 21 weekly scorecard | NOT STARTED | prompt text cut off in this step; facts-only scorecard planned |
Commits so far (local branch recovery/clean, NOT pushed): see `git log` ; pushes used today: 0 of 3.

---- Day 5 checkpoint (kept below) ----
[PROGRESS 60% | steps 16/30 done (Steps 19-30 unknown: prompt truncated) | now: closeout (full tests, push 3, report) | status: RUNNING | elapsed ~5h | data download: 100% | blockers: none]

# Day 5 checkpoint (5 Nov 2026 ~01:55 PKT / 20:55 UTC)
NOTE: the Day 5 prompt was cut off in the middle of Step 18, so Steps 19-30 are unknown to me and cannot be done or counted.
| Step | State | Evidence |
|---|---|---|
| 1 baseline | DONE | docs/DAY5_BASELINE.md |
| 2 local app | DONE (sleep/wake NOT VERIFIED) | detached launcher, OPEN_SINDHU.cmd, recovery 52 s, no duplicate; docs/RUNBOOK.md 11c |
| 3 inventory | DONE | DAY5_BASELINE.md |
| 4 root cause | DONE | docs/SCAN_PROFILE.md section 10: Bybit geo-block, 30 s retry per call, confluence gate reads the wrong exchange |
| 5 fix | DONE | exchange circuit breaker, per-thread ccxt, tests (8 + 2); pushed `5ad081b` |
| 6 push + Cloud measurement | DONE | first COMPLETE Cloud scan since 3 Nov: 20:12:39 -> 20:45:00 UTC = 32 min 21 s cold, 10 coins, 0 errors. Push 2 (8185853) live: second complete scan 865 s (14.4 min, 10 coins, 0 errors) vs 1941 s before; RSS ~407-411 MB (was 487 MB). Soft memory-guard (400 MB) still triggers; hard (450 MB) no longer |
| 7 data plan | DONE | docs/DATA_PLAN.md, universe v2 (50 coins) |
| 8 downloader | DONE | 12 tests incl. kill/resume, 429 storms, disk guard, checksum |
| 9 launch pilot | DONE | ran independently, pilot PASS (109/110 files ok) then expansion COMPLETE 100% |
| 10 quality pipeline | DONE | docs/DATA_QUALITY.md (700 files re-hashed, 0 mismatches; 552/556 monthly files ok, 0 OHLC violations) |
| 11 resampler + native check | DONE | 5 tests; native vs resampled 99.92-100 % identical OHLC; decision: resample for all timeframes |
| 12 loader | DONE | 7 tests: closed candles only, sealed holdout (Sep-Oct 2026), audited final exam |
| 13 expansion + exchange comparison | PARTIAL | expansion complete; Binance-vs-Bybit comparison running (OKX unreachable from this PC); daily updater = re-run `run_download` (scheduling is an owner step) |
| 14 engine speed | PARTIAL | profile done; day-change boxing fix, golden output identical; before/after timing pending a quiet machine |
| 15 cost model | DONE | data_platform/cost_model.py, 3 tests, x1/x1.5/x2 sensitivity by exact re-pricing |
| 16 experiment tracker | DONE | experiments.db, 4 tests, real-data reproducibility check identical hash |
| 17 protocol doc + enforcement | DONE | docs/BACKTEST_PROTOCOL.md; loader enforces the holdout |
| 18 run 42 strategies | DONE | 420 runs; 32 FAILED, 10 INSUFFICIENT_DATA, 0 ROBUST; docs/BACKTEST_RESULTS.md; holdout untouched |
Open: warm Cloud scans still ~85 s per coin on 0.15 CPU; Daily Liquidity Scalping PF-vs-t discrepancy unreconciled; engine before/after timing not measured; OKX-vs-Binance candle comparison NOT VERIFIED.
