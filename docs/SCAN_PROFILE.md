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
