# MASTER_PLAN_V2_STATE
plan_version: 2
started_at: 2026-11-06 06:20 UTC
last_update: 2026-11-07 09:24 UTC
current_step: LG5
next_action: G2
background_jobs: none

Working copy: D:\sindhu_wtA (branch masterplan/partA); D:\sindhu_clean (recovery/clean) is fast-forwarded to it; pushes go through
D:\sindhu_merge to origin codex/trading-intelligence (fast-forward only). V1 state (read-only): docs/MASTER_PLAN_STATE.md.

| step | status | commit | evidence | notes |
|---|---|---|---|---|
| F1 | DONE | (this commit) | V1 state: no step IN_PROGRESS (current_step NONE); git status clean in D:\sindhu_wtA and D:\sindhu_clean at dfa9b84 | V1 leftovers carried into V2 (P5 etc.); 20736c4 not deployed yet, rides with G1 |
| F2 | DONE | (this commit) | docs/MASTER_PLAN_V2_BASELINE.md; docs/ui/v2/before (76 screenshots + audit.json) | log lines/hour is an estimate from one 25-min window; LCP/CLS lab numbers without throttling |
| F3 | DONE | (this commit) | docs/ui/FEATURE_MAP.md: 38 SPA pages, 36 menu entries, 461 route decorators, 3 static HTML pages, 6 global controls; every row has a new location | status per row TODO until PG8 |
| R1 | DONE | (this commit) | tests/test_coingecko_deadline.py (5 passed, real slow local HTTP server) + test_coingecko_cache + test_coin_selection_fallback: 16 passed | deadline 20 s for the whole fetch, connect 5 s / read 10 s, last good list on disk (config/coingecko_top_coins_cache.json, atomic, timestamp), fallback logged once per 30 min; includes 20736c4 |
| R2 | DONE | (this commit) | tests/test_refetch_budget.py; G1 logs: budget 3 kept 6-14 coins waiting per scan -> fixed: 8 per scan, first 2 scans unlimited, deferral = no_trade 'candle history still loading', not an error | default changed after Cloud evidence |
| R3 | DONE | (this commit) | docs/MEMORY_PROFILE_V2.md: import RSS 141 -> 106 MiB (lazy ccxt), ~-11 MiB candle cache; tests/test_lazy_ccxt.py 3 passed, candle tests 34 passed | Cloud RSS after: measured at G1 (target <= 400 MB) |
| R4 | DONE | (this commit) | tests/test_wallet.py 17 passed (cap test changed on purpose 25 -> 15; risk test stop 95 -> 92); FORWARD_TEST_LOG entry | max_position_pct 15, range 5-25, self-check error outside |
| R5 | DONE | (this commit) | docs/DB_LATENCY_FINDINGS.md: SELECT 1 p50 47.2 ms; DB = 56-62 % of 10 warm scans (scan thread only); cloud_settings read 3,700x/scan cached (tests/test_db_round_trip_fixes.py 5 passed) | Ohio claim VERIFIED as main cost (gain estimated); effect of the cache measured after G2 |
| R6 | DONE | (this commit) | tests/test_log_volume.py 5 passed; /health/details log_lines (hourly counter) | per-coin line only >= 60 s; memory-guard on change / 30 min; 2xx GET/HEAD access + websocket open/close not printed (errors, 4xx/5xx, non-GET kept); after-number from the counter at G1 |
| R7 | BLOCKED | (this commit) | tools/settings_cycles.py --postgres (refuses production host+db); tests/test_settings_cycles_pg_guard.py 3 passed | no Neon branch / local Postgres / Docker / psycopg2 on the laptop; owner steps in OWNER_TODO (V2 R7) |
| R8 | SKIPPED |  |  | Tier 3. Not built: the measured warm-scan cost is the database (56-62 %, R5), candle downloads are 45-80 s per warm scan, so a WebSocket feed would save little; it also needs a long-running local test and an owner decision for Cloud. Kept for a later plan. |
| R9 | IN_PROGRESS | (this commit) | tests/test_soak.py 3 passed; manual run started 07:00 UTC -> D:\sindhu_runtime\soak\soak.csv (48 h) | ops/soak/soak_monitor.py, soak_report.py, install_soak_task.cmd (owner); /health/details memory + scans_finished; report built at X1 |
| R10 | DONE | (this commit) | tests/test_reset_dashboard_user.py 4 passed (SQLite/JSON); OWNER_TODO + one-pager Hinglish steps | tools.reset_dashboard_user --list/--reset [--cloud]; never prints passwords or hashes; signs out old sessions; env login untouched |
| DS1 | DONE | (this commit) | tokens.css v2 (dark+light, AA contrast computed: min 4.5 light accent, 4.8 dark loss), self-hosted Inter + JetBrains Mono, Lucide sprite 52 icons, motion + reduced-motion; docs/ui/DESIGN_SYSTEM.md; static/vendor/VENDOR.md (versions + SHA-256) | accent teal (amber = warning) |
| DS2 | DONE | (this commit) | ds.css + ds.js components; /ui-kit page; tests/test_v2_login_and_assets.py | uPlot 1.6.31 vendored (MIT, SHA-256 in static/vendor/VENDOR.md) |
| DS3 | DONE | (this commit) | sindhu_web/assets.py; tests test_assets_are_fingerprinted_immutable_and_compressed, test_asset_memory_stays_small, build tag | gzip at first request (no build step on Render); brotli only if installed (not installed); Cloud check at G2 |
| LG1 | DONE | (this commit) | static/login.html + login.css + js/v2/login.js; docs/ui/v2/after/login_*.png; no scroll at 390x844, focus on username, 0 console errors |  |
| LG2 | DONE | (this commit) | js/v2/login_scene.js (three 0.160.1, 288 instances, 3 draw calls); /api/public/login-scene 3.1 KB, 96 candles 0-1 | live data on Cloud, demo locally (labelled) |
| LG3 | DONE | (this commit) | fallbacks: reduced-motion, no WebGL, low-end (192 instances, 30 fps), frame watchdog >33 ms over 2 s -> poster (seen in headless + pane), pause hidden/off-screen, GPU freed on stop; poster 5.9 KB WebP (tools/login_poster.py) | LCP/form-interactive on a mid phone: NOT VERIFIED (lab only) |
| LG4 | DONE | (this commit) | docs/SECURITY_REVIEW.md login section; CSRF, backoff, rotation, 12 h idle, headers, attempt log |  |
| LG5 | IN_PROGRESS |  | tests/test_v2_login_and_assets.py 20 passed; test_security_hardening + test_cloud_runtime changed on purpose | full suite running; Postgres login test BLOCKED with R7 |
| LG6 | SKIPPED |  |  | Tier 3, off by default. Not built: needs a QR library (not vendored) and recovery-code storage on Postgres; login already has CSRF, backoff, 12 h idle sessions and two no-lockout paths. Kept for a later plan. |
| PG1 | TODO | | | |
| PG2 | TODO | | | |
| PG3 | TODO | | | |
| PG4 | TODO | | | |
| PG5 | TODO | | | |
| PG6 | TODO | | | |
| PG7 | TODO | | | |
| PG8 | DONE | (this commit) | docs/ui/FEATURE_MAP.md: 0 TODO, 8 NEW, 15 MERGED, 24 LEGACY; /legacy keeps every old page; old hash links redirect | research tools stay in the old layout (LEGACY), with v2 tokens |
| PG9 | DONE | (this commit) | static/error.html; browser 404 page vs tiny bot 404; HTML 500 page without traceback; offline + 'Cloud jaag raha hai' messages; tests test_browser_404..., test_html_500... |  |
| PG10 | DONE | (earlier commits) | js/v2/palette.js: Ctrl/Cmd+K palette (pages, strategies, coins), g h / g t / g s / g b / g y / g , and ? shortcut list; keyboard only | checked in PG11 |
| PG11 | TODO | | | |
| X1 | TODO | | | |
| X2 | TODO | | | |
| X3 | TODO | | | |

## Deploys
- G1: merge ab38f58 (code b61a34c) pushed 07:39:01 UTC, live 07:40:41; HEAD /health 200, /wp-admin 404, self-check 4/4 ok, trading enabled.
  Suite before: 2,637 passed / 0 failed (D:\sindhu_clean at b61a34c). After 44 min: 0 error lines, RSS 377.5 MB during the cold scan
  (D3 cold scan: 423 MB), log lines 22 in 07:40-08:00 + 13 in 08:00-08:24 (about 33/h vs ~240/h at F2), db SELECT 1 p50 47.2 ms / p95 94.2 ms.
- After G1 (10 warm scans 11:59-17:08 UTC): 1,808-2,179 s, RSS 359-392 MB (<= 400 MB target met), 0 crash; outcome "partial" with 6-14
  errors each = RefetchDeferred from the new R2 budget (not data errors). Fixed in the next commit (budget 8, not counted as errors).
