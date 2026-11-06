# MASTER PLAN V2 BASELINE (F2): measured BEFORE any V2 change

Measured 2026-11-06 06:20-06:35 UTC. Cloud runs **3eabeac** (V1 D3, live since 03:39 UTC). Local: isolated QA server on port 8422 with
a throwaway data folder (`D:\sindhu_runtime\smoke_data_f2`), code at e8dbea6 (same UI as 3eabeac). Small samples: treat as a snapshot.

## Cloud
| Metric | Baseline | Source / sample |
|---|---|---|
| Memory (Render metric, 10-min points 03:50-06:20, after warm-up) | min 357 MB, avg 394 MB, max 431 MB | get_metrics memory_usage, 16 points, MB = 10^6 bytes |
| App RSS during warm scans | 409-415 MB | `[scan-coin] ... rss` lines |
| Scan time | cold 3,450 s; warm 1,948 s and 1,964 s (50 coins, 0 errors) | `scan finished` lines 04:36, 05:10, 05:43 UTC |
| Error lines per hour | 0 (05:15-06:15 UTC, level=error) | Render logs |
| **Log lines per hour (P29)** | **about 240** (100 app lines between 05:15:28 and 05:40:19 = 24.9 min, while the owner had the dashboard open) | one page of Render app logs; ESTIMATE from one 25-min window |
| What the lines are | about 40 % `[scan-coin]` per-coin timing, 10 % `[memory-guard] ... soft` repeats (every ~3 min), about 45 % uvicorn access lines (`GET /api/...`, dashboard polling), the rest trades and websocket | same window |
| `/health` latency from the laptop (Pakistan) | avg 0.77 s, max 1.25 s, 10 of 10 OK; `HEAD /health` 200 | curl, 10 samples at 06:22 UTC |
| Failed logins seen | 5 x `POST /api/auth/login 401` from one IP at 05:34-05:35 UTC | Render request logs (the owner said they do not remember the earlier password: see R10) |

## UI (every page, cold load)
Tool: `tools/ui_v2_audit.py` = **Playwright Chromium + PerformanceObserver** (Lighthouse CLI is not installed: no node on this laptop).
Each page is a fresh browser context, full load of `/#<page>`, 4 s settle. LCP/CLS are lab numbers on a fast laptop CPU with no
throttling: NOT a mid-phone profile. Screenshots: `docs/ui/v2/before/<page>_<phone|laptop>.png` (390x844 and 1440x900). Raw: `audit.json`.

**Shared bundle (every page loads the same files):**
| File | Raw | Gzip |
|---|---|---|
| js/app.js | 953,040 B | 238,085 B |
| js/lite_mode.js | 7,548 B | 3,119 B |
| js/ops_banner.js | 1,933 B | 928 B |
| css/app.css | 61,943 B | 15,655 B |
| css/tokens.css | 5,960 B | 2,075 B |
| **Total JS gzip** | | **242,132 B** (budget in V2: 150 KB per page) |

**Summary over 38 pages:** phone LCP median 2,670 ms (max 5,328); phone CLS median 0.40 (max 1.20); laptop LCP median 2,952 ms
(max 4,988); laptop CLS median 0.10 (max 0.75); requests median 18.5; transferred median 264 KB; 0 console errors; no horizontal
scroll. Budgets in V2: LCP < 2.0 s, CLS < 0.05, so **CLS fails on almost every page** and LCP on most.
Assets are not fingerprinted (`app.js?v=<start time>` and `tokens.css` with no version): a browser may keep old CSS/JS.

| Page | Phone LCP ms | Phone CLS | Laptop LCP ms | Laptop CLS | Requests | Transferred KB | Console errors | H-scroll |
|---|---|---|---|---|---|---|---|---|
| wallet | 2,272 | 0.425 | 2,660 | 0.1 | 16 | 263 | 0 | no |
| home | 1,824 | 0.396 | 4,208 | 0.101 | 31 | 283 | 0 | no |
| market | 2,200 | 0.396 | 864 | 0.055 | 19 | 264 | 0 | no |
| data | 2,872 | 0.396 | 2,536 | 0.101 | 18 | 264 | 0 | no |
| backtesting | 2,132 | 0.702 | 2,476 | 0.226 | 18 | 274 | 0 | no |
| reports | 2,820 | 0.425 | 3,192 | 0.1 | 18 | 263 | 0 | no |
| settings | 3,196 | 0.396 | 3,676 | 0.1 | 36 | 293 | 0 | no |
| knowledge | 2,856 | 0.396 | 2,700 | 0.056 | 19 | 264 | 0 | no |
| strategies | 5,328 | 0.396 | 4,524 | 0.101 | 21 | 278 | 0 | no |
| paper_trading | 1,952 | 0.396 | 2,156 | 0.1 | 32 | 271 | 0 | no |
| knowledge_compiler | 2,252 | 0.396 | 2,284 | 0.1 | 17 | 263 | 0 | no |
| ai_center | 2,404 | 1.197 | 2,268 | 0.751 | 22 | 266 | 0 | no |
| backtest_history | 2,364 | 0.396 | 2,260 | 0.067 | 18 | 263 | 0 | no |
| pipeline_history | 2,256 | 0.396 | 2,168 | 0.134 | 18 | 263 | 0 | no |
| evolution | 3,500 | 0.396 | 3,444 | 0.101 | 26 | 266 | 0 | no |
| evolution_history | 3,924 | 0.425 | 3,240 | 0.1 | 17 | 264 | 0 | no |
| sindhu_strategy | 2,792 | 0.396 | 4,340 | 0.057 | 18 | 263 | 0 | no |
| signal_tracker | 3,020 | 0.425 | 3,172 | 0.055 | 18 | 264 | 0 | no |
| strategy_lab | 3,032 | 0.396 | 2,524 | 0.1 | 17 | 263 | 0 | no |
| self_learning | 3,512 | 0.396 | 3,324 | 0.101 | 21 | 274 | 0 | no |
| challenge_mode | 2,664 | 0.425 | 2,632 | 0.1 | 19 | 274 | 0 | no |
| strategy_wizard | 2,676 | 0.396 | 2,352 | 0.101 | 17 | 264 | 0 | no |
| web_sourced_strategies | 2,468 | 0.396 | 2,896 | 0.055 | 18 | 263 | 0 | no |
| control_center | 3,076 | 0.396 | 3,204 | 0.1 | 22 | 267 | 0 | no |
| telegram_dashboard | 4,248 | 0.396 | 3,376 | 0.135 | 28 | 269 | 0 | no |
| ceo | 2,052 | 0.425 | 840 | 0.1 | 40 | 285 | 0 | no |
| clarification_center | 2,084 | 0.396 | 2,076 | 0.101 | 17 | 263 | 0 | no |
| external_signals | 2,664 | 0.396 | 2,708 | 0.055 | 19 | 264 | 0 | no |
| compare | 2,608 | 0.396 | 3,852 | 0.1 | 19 | 267 | 0 | no |
| live_logs | 2,484 | 0.425 | 3,036 | 0.1 | 19 | 265 | 0 | no |
| project_status | 3,268 | 0.425 | 3,556 | 0.1 | 20 | 265 | 0 | no |
| incidents | 2,428 | 0.396 | 2,432 | 0.1 | 17 | 263 | 0 | no |
| strategy_lifecycle | 3,436 | 0.428 | 4,988 | 0.056 | 17 | 272 | 0 | no |
| strategy_overview | 4,164 | 0.425 | 4,404 | 0.101 | 18 | 273 | 0 | no |
| risk_department | 2,992 | 0.396 | 3,400 | 0.1 | 18 | 264 | 0 | no |
| memory_core | 2,432 | 0.425 | 2,760 | 0.101 | 19 | 265 | 0 | no |
| configuration_panel | 2,660 | 0.396 | 3,008 | 0.1 | 19 | 266 | 0 | no |
| practice_mode | 2,968 | 0.396 | 3,264 | 0.055 | 17 | 274 | 0 | no |