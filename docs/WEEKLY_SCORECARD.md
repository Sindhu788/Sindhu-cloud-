# Weekly scorecard (week to 5 Nov 2026) - facts only

Every number below was read from a log, a file, a query or a test run in the Day 5-6 sessions. Anything I could not read is written NOT VERIFIED.

## 1. Cloud health and scan speed
| Item | Value | Source |
|---|---|---|
| Deployed commit at the start of Day 6 | 2c3882c, engine running | /health, 5 Nov |
| Complete scans since the circuit-breaker fix | 2: **1,941 s** (cold, 20:45 UTC 4 Nov) and **865 s = 14.4 min** (21:27 UTC); both 10 coins, 0 errors | Render logs "scan finished" |
| Memory (RSS) | **407-411 MB** (soft guard 400 MB, hard 450 MB, limit 512 MB); 487 MB before the memory fix | Render logs "memory-guard" |
| Scans after 21:28 UTC on 4 Nov | **none completed**: the free instance slept and restarted (02:57, 03:11, 03:42 UTC on 5 Nov) because nothing keeps it awake yet (owner's pinger NOT done) | Render logs |
| Incident | at 03:57 UTC a scan made no progress for **182 s inside a database commit** (confluence step, Neon round trip) | Render logs "no progress for 182s" |
| Where scan time goes (local, no network) | about 29 s of CPU per cold scan; 72 % of the 1,331 exchange pages are 1-minute candles for the one 1m strategy | docs/SCAN_PROFILE.md section 11 |
| Cloud measurement of the Day 6 push | see section 8 below | |

## 2. Signals
| Item | Value | Source |
|---|---|---|
| Public signals audited on Day 4 | 6 (3 Nov 19:12 - 4 Nov 08:55 UTC), 0 from the Losing group | docs/SIGNAL_QUALITY.md section 2 |
| Further automatic signals sent | **5 more on 4 Nov between 20:21 and 20:42 UTC** (log lines "auto-signal sent"), so at least 11 in total; the Telegram log table itself was NOT read (needs the Cloud login) | Render logs |
| Withheld in the same window | 14 by the Losing-group rule, 2 because the take-profit was under 1 % away | Render logs |
| Confluence label on every sent signal | "Strong -- 2/2 factors aligned": only 2 of the 4 factors are ever counted on Cloud because the regime factor is not computed (gate reads blocked Bybit) | Render logs, docs/SIGNAL_QUALITY.md D6-1 |
| Confidence figure | does not predict wins out of sample: AUC 0.463 (interval 0.428-0.497), n = 1,132 trades | docs/SIGNAL_QUALITY.md D6-2 |
| Odd signals among the first 6 | 2 with target 9.6-9.9 times the stop, 2 opposite-direction pairs | docs/SIGNAL_QUALITY.md section 2 |

## 3. Paper trading result since the $100 reset
**NOT VERIFIED.** The paper results live in the Cloud database and the Cloud API needs a login I do not use; the reset date is an owner statement I could not check. The only trade history I could read is the local copy (1,132 closed trades, 29 Aug - 11 Sep 2026, base win rate 36.1 %, profit factor about 0.75 in earlier reports).

## 4. Data
- Dataset `D:\sindhu_data`: 700 Parquet files on disk = 700 'ok' manifest entries (+ 50 'absent'), 24,518,580 rows; **60 random files across 34 coins re-hashed today: 0 mismatches**, 0 row-count mismatches.
- 47 of the top-50 coins have data in the development window (3 have none).
- Binance vs OKX US 1h candles (Aug 2026): about 1 bp apart on large coins, up to 15 bps on thin coins. The real Cloud venue (OKX global) is NOT VERIFIED (unreachable from this PC).

## 5. Validation (corrected metrics, 47 coins, 10 months, costs included)
- Day 5's "t = +11.5 vs profit factor 0.75" was a counting error (legs of one entry counted as separate trades, R averaged per leg). Fixed; only one strategy was affected; no label changed.
- **0 ROBUST, 1 FRAGILE (Ichimoku 1d Indicator-Exit, PF 1.09, interval 0.71-1.61), 36 FAILED, 5 INSUFFICIENT_DATA** (42 strategies).
- 2 strategies beat random entries significantly; both still lose money after costs.
- The Sep-Oct 2026 holdout is NOT clean (Day 4 analysed it for 10 strategies on 3 coins). A forward test from 6 Nov 2026 is pre-registered (evaluation not before 5 Jan 2027, >= 100 positions).

## 6. Incidents and fixes this week
| What | Fix | Evidence |
|---|---|---|
| Cloud scans stalled (Bybit blocked from Render, 30 s retries, gate read the wrong exchange) | circuit breaker, per-thread clients, shared markets, housekeeper thread | pushed 5ad081b / 8185853; Render logs |
| Backtest metric defect (legs vs positions) | `data_platform/metrics.py` + tests | docs/BACKTEST_RESULTS.md |
| Local app dead after sessions | documented launcher; start 14 s, recovery after kill 22 s; sleep/wake NOT VERIFIED | docs/RUNBOOK.md 11d |
| I overwrote the Day 4 signal-quality document by mistake | restored from git, new text appended | git history |
| Free instance sleeps; scans cannot finish without keep-alive | owner's external pinger (NOT done) | Render logs |

## 7. Pending owner decisions and risks
**Decisions (everything below is prepared and OFF):** `SINDHU_RESEARCH_ONLY_TIMEFRAMES` (stop evaluating 1m-5m strategies live: pages -72 to -87 %); `SINDHU_BLOCK_OPPOSITE_SIGNAL` and `SINDHU_MAX_TARGET_STOP_RATIO` (would have withheld 3 of the first 6 signals); `SINDHU_HIDE_CONFIDENCE`; `SINDHU_GATE_USE_POSITION_EXCHANGE` (confluence reads the real venue; can only lower labels); `SINDHU_CANDLE_FINGERPRINT` (log what Cloud sees); pause list (docs/OWNER_DECISIONS.md); pinger and hosting; suspending old Render services that may hold the bot token; chat id; secrets.
**Risks:** (1) no strategy has shown an edge after costs, yet public signals go out; (2) the free instance sleeps, so scans and signals are irregular; (3) a database commit stall of 3 minutes inside a scan; (4) memory is within 100 MB of the limit; (5) the holdout is contaminated, so only the forward test can confirm anything.

## 8. Day 7 hand-off - the true, evidence-backed storyline
**What was built (all verified by tests or runs):** a protected, hash-checked Binance candle dataset; a reproducible backtest protocol with a cost model, corrected metrics, bootstrap intervals, a random-entry null model and baselines; a forward-test pre-registration; a credential-free sandbox for evaluating new strategies; prepared (OFF) signal safeguards; the Cloud scan stall root cause and fix.
**What was learned:** none of the 42 enabled strategies is robust after costs; entries of 40 of them are not distinguishable from luck; the costs (about 0.3 % per round trip) exceed the little edge two of them show; confidence figures carry no information; Cloud's wait is network pages, not CPU.
**What is not known:** how the real Cloud venue differs from Binance; paper P&L since the reset; the current Telegram log; what the sleeping instance missed.
**Suggested Day 7 order:** (1) owner decisions above; (2) keep Cloud awake and measure a day of scans; (3) read the Cloud database through an approved path to complete sections 2-3; (4) evaluate any NEW strategy only through `data_platform.candidate_eval`; (5) do not look at forward data before 5 Jan 2027.

## 9. Cloud measurement of push 1 (commit 8ac219f, live 04:30 UTC 5 Nov; Render logs and /health)
| Measure | Day 5 (8185853) | Day 6 (8ac219f) | Verdict |
|---|---|---|---|
| Complete scans measured | 2 (1,941 s cold, 865 s warm) | **2**: 1,046 s (cold start, 04:59-05:16 UTC) and **702 s = 11.7 min** (warm, 05:17-05:28 UTC); a third had started | sample size 2 each |
| Errors per scan | 0 | 0, 0 | same |
| Peak memory (RSS from memory-guard lines) | 407-411 MB | **439-444 MB** | **WORSE by about 30 MB** (hard guard 450 MB; limit 512 MB) |
| Circuit breaker | Bybit opened for 900 s on the 403 | same line at the start of each scan (04:31, 05:00, 05:15), no 30 s retry loops | works |
| OKX rate-limit retries | not counted | several "Too Many Requests" (code 50011) retries of 5-6 s during the 4-worker prefetch at 05:02-05:03 UTC; backed off and recovered; total count NOT VERIFIED (log listing truncated) | note |
| "Stale closed market candles rejected" | - | **none** since 04:30 UTC | clean |
| Stalls ("no progress") | one 182 s stall in a DB commit at 03:57 on the previous version | none since 04:30 UTC | |
| /health latency (5 spaced requests during a scan, from Pakistan) | - | 0.65 / 0.78 / 0.80 / 0.93 / 1.04 s, all HTTP 200 | fine |
**Memory regression, honestly:** memory is higher than on Day 5. I did NOT find the code responsible: the local profile shows the same peak memory for the deployed commit and for this one (193 vs 192 MB), and the Day 6 code that Cloud loads is only a few small hooks (all OFF). The likely difference is run conditions: this process started fresh and ran a 4-worker prefetch (10 coins warmed in 199 s) before the memory guard engaged, and the guard then logged 439-444 MB at the soft level for the rest of the run (memo dropped, prefetch skipped). That explanation is NOT proven. Nothing was reverted because no change was shown to cause it. Risk: 6 MB below the hard guard; the guard only drops optional work, it does not crash the service, and no restart for memory was seen.
**Speed:** the warm scan is faster than Day 5 (702 s vs 865 s) and the cold start much faster than Day 5's cold scan (1,046 s vs 1,941 s), but those two comparisons are single samples and the earlier numbers were taken on a different build; do not read more into them. All three flags that would cut the page count further (docs/SCAN_PROFILE.md section 11) are still OFF.
