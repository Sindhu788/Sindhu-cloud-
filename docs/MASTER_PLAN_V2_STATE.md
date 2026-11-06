# MASTER_PLAN_V2_STATE
plan_version: 2
started_at: 2026-11-06 06:20 UTC
last_update: 2026-11-06 06:36 UTC
current_step: F2
next_action: F2 baseline
background_jobs: none

Working copy: D:\sindhu_wtA (branch masterplan/partA); D:\sindhu_clean (recovery/clean) is fast-forwarded to it; pushes go through
D:\sindhu_merge to origin codex/trading-intelligence (fast-forward only). V1 state (read-only): docs/MASTER_PLAN_STATE.md.

| step | status | commit | evidence | notes |
|---|---|---|---|---|
| F1 | DONE | (this commit) | V1 state: no step IN_PROGRESS (current_step NONE); git status clean in D:\sindhu_wtA and D:\sindhu_clean at dfa9b84 | V1 leftovers carried into V2 (P5 etc.); 20736c4 not deployed yet, rides with G1 |
| F2 | IN_PROGRESS |  |  |  |
| F3 | DONE | (this commit) | docs/ui/FEATURE_MAP.md: 38 SPA pages, 36 menu entries, 461 route decorators, 3 static HTML pages, 6 global controls; every row has a new location | status per row TODO until PG8 |
| R1 | DONE | (this commit) | tests/test_coingecko_deadline.py (5 passed, real slow local HTTP server) + test_coingecko_cache + test_coin_selection_fallback: 16 passed | deadline 20 s for the whole fetch, connect 5 s / read 10 s, last good list on disk (config/coingecko_top_coins_cache.json, atomic, timestamp), fallback logged once per 30 min; includes 20736c4 |
| R2 | DONE | (this commit) | tests/test_refetch_budget.py (6 passed); live_candles/fetch_deadline/self_check tests 18 passed; /health/details refetch_queue + top_coins_cache | heavy = cold or backfill > 1000 candles; K = SINDHU_REFETCH_BUDGET (3); first scan after a start unlimited (all cold) |
| R3 | TODO | | | |
| R4 | TODO | | | |
| R5 | TODO | | | |
| R6 | TODO | | | |
| R7 | TODO | | | |
| R8 | TODO | | | |
| R9 | TODO | | | |
| R10 | TODO | | | |
| DS1 | TODO | | | |
| DS2 | TODO | | | |
| DS3 | TODO | | | |
| LG1 | TODO | | | |
| LG2 | TODO | | | |
| LG3 | TODO | | | |
| LG4 | TODO | | | |
| LG5 | TODO | | | |
| LG6 | TODO | | | |
| PG1 | TODO | | | |
| PG2 | TODO | | | |
| PG3 | TODO | | | |
| PG4 | TODO | | | |
| PG5 | TODO | | | |
| PG6 | TODO | | | |
| PG7 | TODO | | | |
| PG8 | TODO | | | |
| PG9 | TODO | | | |
| PG10 | TODO | | | |
| PG11 | TODO | | | |
| X1 | TODO | | | |
| X2 | TODO | | | |
| X3 | TODO | | | |

## Deploys
