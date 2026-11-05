# Scan profile (Day 4, 4 Nov 2026) - why a Cloud scan takes 15+ minutes

**Method.** `scripts/profile_scan.py` runs the real engine tick (real strategies: 62 enabled, real indicators, real DB code) against a mock exchange: deterministic synthetic candles, OKX-style 300-row pages, no network, no Telegram, isolated data folder `D:\sindhu_runtime\prof_data`, coin mode liquidity / 10 coins like Cloud. OKX is blocked from this PC, so network time is NOT measured locally; it is modelled as pages x latency. CPU time, call counts and memory are real. cProfile numbers are inflated about 1.7x versus a clean run (185 s clean vs 320 s profiled); shares are still valid. Render numbers come from the Render log lines and the heartbeat table.

## 1. Local cold scan, no network time (this PC, full CPU core)
| Run | Wall | CPU | Pages | Rows | Peak RSS |
|---|---|---|---|---|---|
| Cold scan, memo OFF | 185 s | 181 s | 1,334 | 376,524 | 187 MB |
| Cold scan, concept memo ON | 166 s | 162 s | 1,333 | 376,523 | 200 MB |
| Warm scan (same process, caches full) | 2.5 s | 2.4 s | 0 | 0 | - |
The warm scan proves the work is not in the strategy logic itself but in building the data frames and indicators after a restart.

## 2. Where the CPU goes (cProfile, memo OFF, cumulative, 10 coins)
| Stage | Seconds (of 320 profiled) | Share |
|---|---|---|
| `strategy_candidates` = all strategies on all coins | 230 | 72 % |
| - `prepare_context` (indicator/concept columns per strategy) | 174 | 54 % |
| - - `_compute_concept_columns` | 129 | 40 % |
| - - - `support_resistance` + `swing_points` | 35 | 11 % |
| - MTF frame build (`MultiTimeframeContext.__init__` + `.build`) | 46 + 27 | 23 % |
| - `closed_recent_frame` (freshness guard, 990 calls, 23 ms each) | 23 | 7 % |
| - `prepare` | 26 | 8 % |
| `_open_if_allowed` + risk manager (dry-run, 125 candidates) | 26 | 8 % |
| candle paging + parsing (1,334 pages) | 25 | 8 % (of which mock generation 5 s) |
| `coin_filter.shortlist` (50 coins) | 4 | 1 % |
Finding: every one of the 62 strategies recomputes swing points, support/resistance, BOS, order blocks, ATR ... on its own copy of the same candles (620 strategy-coin contexts per scan).

## 3. Database traffic (counted)
Per cold scan: **3,310 database connections opened and closed** (every `storage.get_conn()` call) and **8,307 queries**. Locally on SQLite this is 26 s. On Postgres each connection was a brand-new TCP+TLS+login to Neon (the code opened a fresh psycopg2 connection per call, no pool). Measured from this PC to Neon (far away, so only an upper bound): new connection + query median 2,576 ms, query on a reused connection median 276 ms. From Render the latency is NOT VERIFIED (no way to measure from here before a deploy).

## 4. What Render showed (log lines, 4 Nov)
| Phase | Render |
|---|---|
| exchange + symbol list | 11 s, 31 s, 40 s, 56 s, 72 s, 120 s (CoinGecko 429 retries then OKX) |
| shortlist (50 coins, 1h each) | 20-21 s |
| prefetch of 10 coins, 4 workers | 263 s (each 1m series: 96-97 pages in 38-45 s, i.e. 0.43 s per page = 0.25 s fixed pause + ~0.18 s round trip) |
| coin loop | coin 1 did not finish in 9 min; the 10:33 scan reached coin 2 after 29 min; stall sample showed the engine thread inside a candle download |
| CPU / memory | CPU 0.006-0.009 of 0.15 while waiting, up to 0.10 while downloading; RSS 190 -> 360 MB after the prefetch |

## 5. Attribution (how sure am I)
- **CPU-bound Python on a throttled CPU is the largest measured piece.** Locally 85 % of the time is strategy evaluation (pandas). One scan = about 18 s of full-core CPU per coin. The Render instance has 0.15 CPU, so the same work needs roughly 18 s / 0.15 = 2 min per coin = 20 min per scan, which matches the 15-17 min that completed on 3 Nov. Confidence: medium-high (the arithmetic fits, but the exact Render CPU speed vs this PC was not measured).
- **Database connection churn is the second suspect** (3,310 connections). On Render it would add 3,310 x (connect time). At 0.1 s that is 5.5 min, at 0.3 s 16 min. Confidence: medium that it is significant, NOT VERIFIED how large.
- **Network candle download is smaller after the Day 3 prefetch** (263 s with 4 workers, mostly the 1m series, fixed 0.25 s pause is 58 % of each page).
- The idea "the same series is re-requested hundreds of times" (15-second throttle) is **rejected**: 121 `_fetch_range` calls for 1,334 pages in a whole scan (about one download per series). See section 7.

## 6. Changes made on Day 4 (outputs identical, gates untouched)
| Change | Effect (measured locally) |
|---|---|
| Postgres connection pool (`db_backend`, max 4 idle, rollback on return, health check after 30 s idle, 4-min max age, `SINDHU_PG_POOL=0` = off) | 3,310 connections per scan -> about 4 (tests with a fake driver; real Neon effect NOT VERIFIED until deployed) |
| Concept memo (`concepts.memo_enable`, on only during a scan; 16 pure functions; copy on return; 48 MB budget) | cold scan 185 s -> 166 s (-10 %); 2,085 hits / 327 misses |
| No-op trim skipped in `live_candles` | about 5 s per scan |
| `/health` is `async def`, session/token DB lookups moved to the thread pool | /health no longer blocked by slow sessions (test fails on the old code) |
| Memory guard | soft 400 MB: drops memo and skips prefetch; hard 450 MB: owner-chat alert (rate limited) |
**Golden-output proof:** `python scripts/profile_scan.py --fresh --golden 4` (frozen clock, same candles): BTC, ETH, SOL, XRP, 62 strategies each, 13 + 14 + 13 + 9 = 49 candidates, memo OFF == memo ON (first call) == memo ON (second call, cache hit): **PASS**. Unit tests: `tests/test_concepts_memo.py` (each memoized function equals the plain function on every call; mutation of a returned series cannot corrupt the cache; different data never shares an entry; AST audit that memoized functions read only OHLCV).

## 7. Throttle A/B (Step 5)
The Day 3 idea (do not ask the exchange for newer candles again within 15 s) was tested by counting calls: a full cold scan made 121 `_fetch_range` calls for 1,334 pages; every series is downloaded once and the incremental path sends no request while the newest candle is current. So there is nothing to throttle. **Decision: removed** (D32). It could also have served a candle up to 15 s old, which is why it was never worth the risk.

## 8. Not done / limits
- Render-side numbers after these changes: see "Cloud measurement" below (filled after the deploy).
- Further CPU savings that were not attempted (risk of changing outputs): share the merged frame between strategies with the same timeframes; avoid object-dtype `~` inversions (13 s per scan); cache `closed_recent_frame`.

## 9. Cloud measurement after the Day 4 changes (Step 9) - STILL NOT COMPLETING
Builds measured: `06d2051` (pool + memo + memory guard + health fix) and `ab5b297` (adds diagnostics). Evidence is the Render log and the Neon heartbeat/receipt tables, 4 Nov 16:24-17:08 UTC.
| What | Measured |
|---|---|
| exchange + symbols | 81 s (16:26), 120 s earlier (CoinGecko/OKX retries) |
| shortlist of 50 coins | 21-28 s |
| prefetch of 10 coins, 4 workers | **197 s** (was 263 s) |
| coin loop | **coin 1 took about 20 minutes**: scan started 16:43, reached coin 2 of 10 at about 17:07, then the instance stopped; CPU was 0.003-0.005 of 0.15 the whole time (idle: waiting), RSS flat at 322-338 MB |
| complete scans | **0** (receipts since the pool push: all `interrupted`) |
| /health | 29 of 30 answers within 4 s on Day 3; after the fix NOT re-measured under a live scan (the wake-up request at 17:25 took longer than 60 s because the instance was asleep) |
What the diagnostics found: the engine thread sits inside ONE small candle request (stall sample 16:50:39: "downloading PEPE/USDT 1h page 1 window 3.0d", inside `ccxt_client._retry`) for minutes while the CPU is idle. Every long wait seen so far is a wait on the exchange, not computation. It happens after the burst of the prefetch (about 5 requests/s from 4 threads sharing one ccxt client). Possible causes, **not yet distinguished**: OKX rate-limit back-off (`_retry` sleeps 5 s x attempt on a rate-limit error and 2 s x attempt on network errors, up to `max_retries`), slow responses from OKX to Render, or an unsafe shared ccxt session across threads. The next deployment (Day 4 push 3) logs every retry (`[exchange-retry] okx attempt n/N <ErrorType>`) and names the exact stuck call in the stall report (`retry attempt n last_error <type>`), so the next measurement can decide.
Free-plan limits as measured (numbers only): 0.15 CPU share, 512 MB RAM (322-338 MB in use with 10 coins warmed, soft guard at 400 MB), instance stopped after ~15 min without a request, restart on every wake (cold caches). A scan needs about 3.5 min of prefetch + 1.5 min of symbol/shortlist work before any coin is evaluated, plus local-equivalent CPU of ~18 s per coin (about 2 min per coin at 0.15 CPU) = roughly 25-30 minutes for 10 coins on this plan even if the exchange waits disappear. That is longer than the 15-minute idle limit, so without an external pinger a complete scan will never finish; with a pinger the process stays warm (cache kept) and later scans take seconds (warm scan 2.5 s locally). A plan with at least 0.5 CPU would cut the CPU part by 3x; NOT bought, NOT recommended before the pinger is tested. I did not tune further because the remaining wait is on the exchange side and could not be reproduced locally (OKX is blocked from this PC).


## 10. ROOT CAUSE of the Cloud scan stalls (Day 5, 4-5 Nov 2026) - found with log evidence
**Cause:** Bybit blocks Render. Every request to Bybit from the Cloud instance is answered with HTTP 403 "The Amazon CloudFront distribution is configured to block access from your country". The Cloud runs with `exchanges.json default = "bybit"` (the cloud-mode default in `data_engine/config.py`), while all positions and candles are on OKX. The confluence gate in `telegram_bot.py` (4 places: `evaluate_auto_send`, low tier, sweep, send) asks for the regime of the coin on the DEFAULT exchange, i.e. Bybit. ccxt turns the 403 into `RateLimitExceeded`, which is a subclass of `NetworkError`, so the retry loop took its first branch and slept 2 + 4 + 6 + 8 + 10 = **30 s per call** before giving up. The signal sweep (once a minute, inside the coin loop since Day 3) and every send attempt repeat this for each open/unsent position, one after the other, on the engine thread. The scan therefore "waits for minutes with idle CPU" - exactly what the metrics showed.
**Evidence (Render log, instance `...-cm24m`, 4 Nov 18:02-18:08 UTC; the log has about 60 such lines per 6 minutes):**
```
[exchange-retry] bybit attempt 1/5 RateLimitExceeded: 'bybit GET https://api.bybit.com/v5/market/instruments-info?category=spot 403 Forbidden { error:The Amazon CloudFront distribution is configured to block access from your country }' - sleeping 2s
... attempt 2/5 ... sleeping 4s ... attempt 3/5 ... sleeping 6s ... attempt 4/5 ... sleeping 8s ... attempt 5/5 ... sleeping 10s
(next burst starts about 31 s later: 18:02:19, 18:02:51, 18:03:23, 18:03:54, 18:04:27, 18:04:58, 18:05:30, 18:06:02, 18:06:35, 18:07:06, 18:07:39, 18:08:10)
```
Matching stall sample (Day 4): `scan shows no progress for 187s; engine thread is at: ccxt_client._retry <- get_ohlcv <- ... | downloading PEPE/USDT 1h page 1 window 3.0d` = `regime.classify_regime` (1h candles, 72 h = 3.0 days) called from `confluence.score_confluence`. A direct check from this PC: `https://api.bybit.com/v5/market/time` answers 200 here, so the block is specific to the Render address range (country block at Bybit's CDN).
**Hypotheses checked (Step 4):**
| Hypothesis | Verdict | Evidence |
|---|---|---|
| (a) one ccxt client shared across threads | not the cause of the stall; real risk, fixed anyway | the stuck thread is the single engine thread; no concurrent-access errors in the log; per-thread ccxt instances added |
| (b) back-off sleeping too long / stacking | **YES (the cause)**, but triggered by a permanent geo-block, not by real rate limiting | log: 5 attempts, 30 s, repeated every ~31 s for the whole observed window; ccxt `RateLimitExceeded` is a `NetworkError` subclass so branch 1 (2 x attempt) ran for every error |
| (c) missing connect/read timeouts | no: ccxt default 10 s applies; now explicit (`SINDHU_EXCHANGE_TIMEOUT_MS`) | requests failed fast with 403, they did not hang |
| (d) proxy / DNS / TLS delays | no | responses arrive immediately (403 body in the log) |
| (e) event-loop / thread-pool starvation | no for the scan; separate bug for /health fixed on Day 4 | CPU 0.003-0.005, engine thread blocked in `time.sleep` inside `_retry` |
Confidence: high for the mechanism (log lines + code path read), medium for the exact share of the 20-minute coin-1 time (some of it is the real data work). It is NOT possible to prove from here that no other blocked exchange call exists; the new `[exchange-breaker]` lines will show any.
**Second finding (silent, serious): the confluence gate reads the wrong exchange on Cloud.** Because the gate uses Bybit, (1) the "market condition" factor (regime) can never be computed (exception -> factor skipped), so confluence shows "2 of 2 factors" and the required 3 can never be met - this is why every near miss since 3 Nov says "2/2 need 3"; (2) the "no other strategy crowding this coin" factor looks for open positions on Bybit, finds none, and always passes. Fix is available but OFF by default because it changes gate inputs (owner decision): environment variable `SINDHU_GATE_USE_POSITION_EXCHANGE=1` on Render (`telegram_bot._gate_exchange`, test `test_gate_exchange.py`).
**Fix shipped (Step 5), signals unchanged:** `data_engine/exchanges/ccxt_client.py`: geo-block detected from the error text -> immediate `ExchangeUnavailable`, no sleeping, circuit open for 15 min (`SINDHU_BREAKER_GEO_SECONDS`); 3 failed calls in a row open the circuit for 2 min; total time per call capped at 45 s (`SINDHU_EXCHANGE_CALL_BUDGET_S`); back-off now has jitter (0-25 %); real HTTP 429 now waits 5 s x attempt (was effectively 2 s x attempt); one ccxt instance per thread with shared market data; explicit request timeout. Behaviour for the gate is the same as before (exception -> factor skipped) but takes milliseconds instead of 30 s, so output signals are identical; proof: `tests/test_exchange_breaker.py` (7 tests: geo-block fails in 0 s instead of 30 s, circuit stays open then closes, other exchanges unaffected, real 429 retries with jitter and recovers, hanging exchange bounded by the budget, thread-safety) and the existing gate/sweep tests (28 passed).

## 11. Day 6 measurements (5 Nov 2026) - Step 12
Same tool (`scripts/profile_scan.py`, mock exchange, no network, isolated data folder, quiet machine, 62 strategies in the local database copy x 10 coins):
| Run | Wall | CPU | Pages | Rows | Peak RSS |
|---|---|---|---|---|---|
| Cold scan, commit 2c3882c (the deployed code) | 27.6 s | 27.2 s | 1,330 | 376,520 | 193 MB |
| Cold scan, HEAD with all Day 6 flags OFF | 29.2 s | 28.6 s | 1,331 | 376,521 | 192 MB |
| Warm scan (same process) | 0.4 s | 0.3 s | 0 | 0 | - |
| HEAD with `SINDHU_RESEARCH_ONLY_TIMEFRAMES=1m` | 26.1 s | 25.7 s | **370** | 88,520 | 160 MB |
| HEAD with `SINDHU_RESEARCH_ONLY_TIMEFRAMES=1m,3m,5m` | 15.4 s | 15.1 s | **170** | 30,920 | 146 MB |
**Contradiction with Day 4:** the Day 4 table (section 1) says 185 s wall for the same cold scan; today it is **28-29 s** with the same page count. I did not find out why (a loaded machine on Day 4 is the most likely reason, NOT VERIFIED). Consequence: on a full local core the CPU work of a scan is about **29 s**, and on the 0.15-CPU Cloud instance it is at most about 190 s of the measured 865 s. **The rest of the Cloud time is waiting** (1,331 exchange pages one after another, plus database round trips to Neon), not computation. [CORRECTED on Day 7 (5 Nov 2026): wrong for warm scans, see section 12.]
**Where the pages come from:** 961 of the 1,331 pages (72 %) are 1-minute candles (20 days x 10 coins) fetched for the 1m strategy; 200 are 5m, 80 15m, 70 1h. With the research-only flag set to `1m` the scan fetches 72 % fewer pages; with `1m,3m,5m` 87 % fewer, CPU halves and memory drops by about 46 MB. **That flag is OFF** (it removes the live signals of the strategies on those timeframes: an owner decision, docs/PIPELINE.md). Effect on the real Cloud scan time: **NOT VERIFIED** (not measured on Cloud; flag stays OFF).
**CPU profile (cProfile, 48 s with profiling overhead):** `strategy_candidates` 39.3 s of 48.3 (81 %); `prepare_context` 22.8 s over 620 strategy-coin contexts (47 %), of which `_compute_concept_columns` 16.2 s (34 %; the memo already serves 2,102 hits against 344 misses); candle access `get_ohlcv_live` 8.3 s (17 %) over 1,166 calls; `MultiTimeframeContext.build` 5.1 s; `prepare` 4.8 s; `closed_recent_frame` 4.4 s; database connections 5.2 s (3,188 opens).
**What I changed for speed: nothing in the evaluation path.** The remaining safe CPU savings (sharing concept columns between strategies beyond the existing memo, avoiding frame copies) need a deeper change to code that decides every signal; with 29 s of CPU against 865 s of waiting, the possible gain on Cloud (at most a few percent of the scan) did not justify the risk in this run. Step 12 is therefore only PARTIAL: measured, explained, levers quantified, no speedup delivered without owner approval of the flag.
**Golden-output proof (frozen clock, `--golden 4`, BTC/ETH/SOL/XRP, 62 strategies each):** the deployed commit 2c3882c and HEAD (all Day 6 flags OFF) give identical candidates: 12 / 12 / 12 / 11 on both, memo OFF == memo ON on both, result PASS on both. The Day 6 hooks (research-only check, fingerprint note) therefore do not change any signal when OFF.

## 12. Day 7: scan time with the 1m timeframe excluded, and where the Cloud time really goes (Step 7)
**Method.** Local sandbox only (`scripts/profile_scan.py`, mock exchange with deterministic candles, isolated data folder, 62 strategies in the local copy x 10 coins). The flag `SINDHU_RESEARCH_ONLY_TIMEFRAMES` was set only inside this local process; no Render variable was touched.
**A. Identical-candidates proof (new mode `--ro-golden`, frozen clock, 6 coins BTC/ETH/SOL/XRP/DOGE/PEPE):** for every coin the candidate list with the 1m exclusion is byte-identical to the full list with its 1m-timeframe candidates removed. Result: **PASS**; 61 candidates kept, 6 removed (exactly one per coin, all from the single 1m strategy). Command: `python scripts/profile_scan.py --fresh --ro-golden 6`.
**B. Before / after (cold scan, same mock inputs; Day 6 measurements, 5 Nov 2026):**
| Setting | Wall | CPU | Pages | 1m | 5m | 15m | 1h | 4h | 1d | Peak RSS |
|---|---|---|---|---|---|---|---|---|---|---|
| Current behaviour | 29.2 s | 28.6 s | 1,331 | 961 | 200 | 80 | 70 | 10 | 10 | 192 MB |
| 1m excluded | 26.1 s | 25.7 s | 370 | 0 | 200 | 80 | 70 | 10 | 10 | 160 MB |
| 1m, 3m and 5m excluded | 15.4 s | 15.1 s | 170 | 0 | 0 | 80 | 70 | 10 | 10 | 146 MB |
Excluding 1m removes 72 % of the pages, 10 % of the CPU and 32 MB of memory locally. (Page counts differ by 1 between runs because the mock candles follow the clock; same code and data otherwise.)
**C. Where the Cloud time goes (Render logs of the warm scan 05:17-05:28 UTC on 5 Nov, total 702 s, and the cold scan 04:59-05:16, total 1,046 s):**
| Phase | Warm scan | Cold scan |
|---|---|---|
| exchange + symbols | 22 s | 96 s |
| shortlist reached at | 30 s | 115 s |
| prefetch of candles (4 workers) | skipped by the memory guard | 199 s |
| coin loop (strategy evaluation, risk, database) | about **670 s** (about 67 s per coin) | about 700 s |
**Correction of a Day 6 statement:** Day 6 said the rest of the Cloud time "is waiting for exchange pages". For WARM scans this is wrong: a warm scan fetches only the newest candles (a handful of pages), yet its coin loop still takes about 670 s. The page count explains the cold start (prefetch 199 s, memory) but not the coin loop. The local CPU work of the whole scan is about 29 s; at the free plan's 0.15 CPU that is at most about 190 s. **The remaining roughly 480 s of the coin loop are not explained by CPU or candles.**
**Hypothesis, NOT VERIFIED (not measured on Cloud):** database round trips. The Neon database is in `us-east-2` (Ohio, via the pooler) and the service runs in Oregon. Day 4 counted about 8,300 queries and 3,300 connections per cold scan; at a typical 50-70 ms per cross-country round trip that is roughly 415-580 s, the size of the missing time. A cross-check: one commit stalled for 182 s at 03:57 UTC on 5 Nov (log: "scan shows no progress for 182s ... db_backend.commit").
**What to log on Cloud next (to turn the hypothesis into a measurement, Day 8):** per scan, the number of database calls and the total seconds spent in them, and the seconds spent in strategy evaluation per coin. Both are a few counters and one log line; not added today (they would change the deployed code path).
**Effect of the 1m flag on the Cloud scan, honestly:** it removes 1 of 62 strategy evaluations per coin (1.6 %), about 72 % of the cold-start pages and about 30 MB; it does not change the 670 s coin loop much. Expected: a faster cold start and lower memory, NOT a faster warm scan. It still removes the 3 signals of the 1m strategy from the public groups, which is the stronger reason to consider it (docs/OWNER_DECISIONS.md).

## 13. Day 7: the memory "regression" (Step 8) - answer: there is none; memory varies by about 70 MB between instances running identical code
**A. Local, identical mock inputs, peak RSS in MB (build x prefetch workers):**
| Build | workers 0 | workers 2 | workers 4 |
|---|---|---|---|
| Day 5 build `8185853` | 198 | 196 | 199 |
| Current build (Day 7) | 200 | 192 | 202 |
| Current build with 1m excluded (Day 6 run) | 160 | - | - |
Differences between builds and between 2 and 4 workers are 2-10 MB, inside run-to-run noise: **no build and no worker setting explains a 30 MB rise**. (Timings of these runs were 158-178 s each, against 28 s on Day 6 for the same code: absolute local times depend on the machine's state, memory does not.)
**B. Largest allocations (tracemalloc, current build, end of a local scan; 119 MB traced of about 196 MB RSS; `tools/mem_top.py`):** imported code objects 45 MB + 7.5 MB (pandas, numpy, ccxt and project modules); pandas candle frames 27 MB (400 blocks) + 3 MB of datetime arrays; ccxt market structures 5.9 MB (78,000 small objects, one set per exchange client); everything else under 1.2 MB per line. The rest of the RSS is native libraries.
**C. Cloud, from Render's own memory metric (`get_metrics`, 5-minute view), peak per instance:**
| Instance (start UTC) | Build | Peak MB |
|---|---|---|
| rck4s (before 19:35 on 4 Nov) | before 5ad081b | 421 |
| kntmw (19:35) | 5ad081b | 470 |
| bl9kl (20:12) | 5ad081b | 470 |
| n76sr (21:13) | 8185853 | 391 |
| nldr8 (02:58, 5 Nov) | 8185853 | 389 |
| 9w8jn (03:11) | 2c3882c (code identical to 8185853, docs only) | 437 |
| msjqj (03:42) | 2c3882c | 459 |
| hqbfg (04:30) | 8ac219f | 404 |
| zmc4k (04:59) | 8ac219f | 427 |
| b6c6g (05:37) | 37859e2 (docs only after 8ac219f) | 403 |
**Reading:** the Day 5 fix did lower memory (470 MB peaks before, 389-459 MB after). But the four instances that ran the SAME code (8185853 / 2c3882c) peaked at 391, 389, 437 and 459 MB: a 70 MB spread from run to run. Day 6's "439-444 MB vs 407-411 MB" is inside that spread. The memory-guard log (soft level 400 MB) and Render's metric agree within about 15 MB.
**Root cause: cannot determine.** What differs between a 389 MB and a 459 MB run of identical code is not visible in the logs (the shortlist of coins changes with the market, the order of work and Python's memory fragmentation differ). **What to log on Cloud next** (Day 8, a few lines, no behaviour change): RSS at the end of each scan phase, the list of the 10 shortlisted coins, the number of cached candle rows per timeframe, and the count of live exchange clients.
**Smallest safe fixes, NOT applied (default behaviour unchanged):** (1) `SINDHU_RESEARCH_ONLY_TIMEFRAMES=1m` removes about 32 MB locally (the 1m candle frames), the largest single lever; (2) a shorter candle retention (`_MAX_RETENTION_DAYS`, 25 days) would cut cached frames but changes the data every strategy sees: a behaviour change, not recommended without an owner decision. The hard guard (450 MB) drops optional work and prefetch, it does not crash the service; no memory restart was seen in the logs.

## 14. Day 8: Cloud uptime study - how much scanning does the free plan lose without a pinger? (read-only; no extra requests were sent for this)
**Window:** 4 Nov 2026 19:00 UTC to 5 Nov 18:32 UTC = 23.5 h = 1,412 min. **Sources:** Render memory metric (an instance has samples only while it is awake; the samples end about 15 minutes after its last request, which is Render's free-plan idle rule), Render deploy events (`list_events`), and the log lines "Started server process", "scan finished" and "previous scan was interrupted". Render's event list contains deploys but no sleep/wake events, so wake-ups are the process starts that have no deploy at that time.
| Instance (last 4 letters) | Awake from - to (UTC) | Minutes awake | Started by | Scans completed | Scan cut when it ended |
|---|---|---|---|---|---|
| ..rck4s | before 19:00 - 19:35 | 36 | (earlier) | 0 | ended by deploy 5ad081b |
| ..kntmw | 19:35 - 19:50 | 16 | deploy 5ad081b | 0 | coin 2/10 |
| ..bl9kl | 20:13 - 21:13 | 61 | wake-up | 1 (20:45, 1,941 s) | coin 6/10 at start of the next |
| ..n76sr | 21:13 - 21:37 | 25 | deploy 8185853 | 1 (21:27, 865 s) | coin 9/10 |
| ..nldr8 | 02:58 - 03:11 | 14 | wake-up | 0 | finishing phase |
| ..9w8jn | 03:11 - 03:26 | 16 | deploy 2c3882c | 0 | coin 10/10 |
| ..msjqj | 03:43 - 03:59 | 17 | wake-up | 0 | finishing phase (182 s database stall at 03:57) |
| ..gd6cv | 04:29 - 04:30 | 2 | deploy 8ac219f | 0 | finishing phase |
| ..hqbfg | 04:30 - 04:45 | 16 | deploy 8ac219f (second instance) | 0 | exchange phase |
| ..zmc4k | 04:59 - 05:37 | 39 | wake-up (my first request) | 2 (05:16, 1,046 s; 05:28, 702 s) | coin 9/10 |
| ..b6c6g | 05:37 - 06:12 | 36 | deploy 37859e2 | 2 (05:54, 1,047 s; 06:06, 655 s) | idle: spun down |
| ..bwm5c | 13:30 | 1 | deploy c035ca3 | 0 | coin 7/10 |
| ..xv9gp | 13:31 - 13:54 | 24 | deploy c035ca3 (new instance) | 0 | shortlist phase |
| ..s864r | 18:22 - now | 11 so far | wake-up (my request) | 0 so far | - |
**Totals:** 314 minutes awake of 1,412 = **22 %**; 6 deploys and 5 wake-ups started processes; **6 scans completed** (total scan time 6,256 s = 104 min = **7.4 % of the 23.5 hours**, 33 % of the awake time); **13 scans were cut** (an instance stopped, slept or redeployed mid-scan). After 06:12 UTC the engine did nothing for 7 hours 18 minutes (until a deploy at 13:29 woke it), and nothing again from 13:54 to 18:22.
**What this means:** a warm scan takes about 12 minutes (865 / 702 / 655 s). An always-on instance could have completed about 120 scans in this window; it completed 6 (**about 5 %**). Everything that depends on the scanner (new paper trades, signals, stop/target handling of open positions, the freshness window) ran for about a fifth of the time, and in bursts after each wake-up. 1 minute of the 15-minute idle tail per instance is counted as awake. Statistics from different days are therefore not comparable (cold starts and warm scans are mixed), and open paper positions can sit unmanaged for hours while the instance sleeps (61 positions were open at the 5 Nov export). **An external pinger (every 5 minutes) is the single largest improvement available**, before any speed work. Note the free plan's 750 free hours a month for all free services together (docs/OWNER_TODO.md): keeping this service awake all month uses about 744.
