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
