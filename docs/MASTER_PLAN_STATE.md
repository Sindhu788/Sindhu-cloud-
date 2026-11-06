# MASTER_PLAN_STATE
plan_version: 1
started_at: 2026-11-05 ~20:55 UTC (the laptop clock said 5 Nov UTC; the session header said 6 Nov)
last_update: 2026-11-06 03:45 UTC
current_step: NONE (plan finished; remaining items are owner actions or listed PARTIAL)
next_action: owner actions in docs/OWNER_TODO.md; optional follow-ups: Ohio region, one transaction per coin, CoinGecko deadline
background_jobs:
  - id: SUITE3   status: DONE  marker_dir: /tmp/full_runs.log  done: 3/3
  - id: BT-DATA  status: DONE  marker_dir: D:\sindhu_runtime\bt_jobs\BT-DATA  done: 20/20
  - id: BT-RUN   status: DONE  marker_dir: D:\sindhu_runtime\bt_jobs\BT-RUN-v2  done: 23/23 (run 1 kept in BT-RUN)

Working copy: D:\sindhu_clean (branch recovery/clean); pushes go through D:\sindhu_merge to origin codex/trading-intelligence (fast-forward only).

| step | status | commit | evidence | notes |
|---|---|---|---|---|
| F1 | DONE | 4e9b5ff | 3 consecutive green full runs (2,509 passed, 0 failed each, 21:22/21:39/21:56 UTC); docs/FINAL_MASTER_PROMPT_CLOSEOUT.md | previous prompt closed; worktree D:\sindhu_wtA branch masterplan/partA |
| F2 | DONE | 46b1656 | docs/MASTER_PLAN_BASELINE.md: Cloud (RSS 517-536 MB, ~60 Neon errors/h, prefetch 3,828 s, /health >60 s, 1 complete scan/24 h) + local home (3.0 s, 30 requests, 1.1 MB) | DB queries per home load NOT MEASURED (SQLite) |
| F3 | DONE | | B1 + B2 done (below) | |
| A1 | DONE | ee8b342 | tests/test_health_head_and_probes.py (6 passed) | |
| A2 | DONE | 3cf0dd9 | tests/test_live_candles_incremental.py (5 passed); frozen golden identical | Cloud before/after rows/pages measured at D1 |
| A3 | SKIPPED (deferred) | | | WebSocket would not help the cold start; Cloud ON needs owner OK |
| A4 | DONE | (this commit) | tests/test_rate_limit.py (5 passed) | token bucket okx 8/s, 3 parallel, halve 10 min after 50011 |
| A5 | DONE | 3cf0dd9 | tests/test_fetch_deadline.py (6 passed) | per-coin 180 s, prefetch 600 s, stall report 120 s |
| A6 | DONE | 3cf0dd9 | tests/test_db_breaker_and_log_dedup.py (8 passed), pool tests | keepalives, 1 retry, breaker 30->300 s, loop dedup |
| A7 | DONE | 6b1b1eb | tests/test_gate_exchange.py (+4) | cloud default okx; gate reads position exchange on Cloud |
| A8 | DONE | (this commit) | tests/test_confluence_unknown.py (3 passed) | regime missing -> UNKNOWN -> withheld |
| A9 | DONE | 759cb5b | tests/test_wallet.py (12 passed); /api/wallet | archive before D2: Cloud export (read-only, redacted) |
| A10 | DONE | 759cb5b | test_daily_loss_limit_* | wallet-level; owner alert = dashboard alert (Telegram owner chat needs OWNER_CHAT_ID) |
| A11 | DONE | 759cb5b | test_duplicate_entry_guard_* | |
| A12 | DONE | 759cb5b | test_strategy_auto_paused_* | |
| A13 | DONE | 759cb5b | wallet_journal table; /api/wallet journal | Trades-page view in Part C; CSV export in A23 |
| A14 | DONE | (this commit) | tests/test_public_signals_default_off.py (10 passed) | SINDHU_PUBLIC_SIGNALS default off; disclaimer + validation class always |
| A15 | DONE | a3d838d | tests/test_telegram_commands.py (+1), 64 command tests | /wallet,/health commands not added (existing /status,/pause,/resume,/help) |
| A16 | DONE | 759cb5b + e7f4201 | tests/test_dashboard_password.py; kill-switch button + modal PASS (tools/ui_killswitch_check.py) | DASHBOARD_PASSWORD optional (owner) |
| A17 | DONE | 69e74e0 | tests/test_self_check.py (6 passed); local + Cloud saved settings validate clean | |
| A18 | DONE | 6c803ad | per-series lines counted in [scan-stages] | log lines/hour before vs after: X1 |
| A19 | PARTIAL | e7f4201 | /api/summary; home 3.0 -> 0.4 s; Cloud memory 428-435 MB steady | 350 MB target not reached |
| A20 | DONE | 6c803ad + e7f4201 | /health/details counts + banner dot | |
| A21 | DONE (SQLite) / BLOCKED (Postgres) | 61de22f | docs/SETTINGS_TEST_REPORT.md 50/50 | no throwaway Postgres |
| A22 | DONE (local) | 46b1656 | tools/parity_check.py, docs/PARITY.md, OWNER_DECISIONS flags | Cloud hash after D2 |
| A23 | DONE (scripts) / BLOCKED (install) | 1ef957e | ops/windows_tasks/*; daily report dry run OK; monthly export tested | owner runs install_tasks.cmd |
| A24 | DONE | 1ef957e | BACKUP_LOG 2026-W45 restore exit 0; 30.0 MB = 5.9 %; retention dry run 0 rows | no auto-delete (keep rule) |
| A25 | DONE | a2d1c52 | docs/ROLLBACK.md, docs/FORWARD_TEST_LOG.md, autostart task + sleep guide | install by owner |
| A26 | DONE | a2d1c52 | docs/OWNER_ONE_PAGE_HINGLISH.md, docs/PORTFOLIO_STORY.md, README.md, OWNER_TODO | |
| B1 | DONE | 7388c1b | docs/BENCHMARK_PREREGISTRATION_V2.md committed before data; hash 6abba148; Amendment 1 (universe + delisting rule) before any code/result | |
| B2 | DONE | (this commit) | D:\sindhu_data\daily 20 files + manifest_daily.json; docs/DATA_QUALITY.md B2 section PASS | |
| B3 | DONE | 0195031 | tests/test_benchmark_v2.py (12 passed) | |
| B4 | DONE | (B4 commits) | D:\sindhu_runtime\bt_jobs\BT-RUN-v2 (23 units + verdicts.json); run 1 kept | amendment 2: simulator bug |
| B5 | DONE | 7f46b03 | docs/STRATEGY_V2_REPORT.md: both FRAGILE (fail FDR only) | SVG charts (no plotting library) |
| B6 | PARTIAL | a2d1c52 | decision request in OWNER_DECISIONS; not registered in the live strategy library (portfolio strategies need a new mode) | |
| B7 | DONE | a2d1c52 | docs/NEW_STRATEGY_HOWTO.md daily-portfolio section | |
| C1 | DONE | e7f4201 | sindhu_web/static/css/tokens.css | |
| C2 | DONE | e7f4201 | banner, MAIN_WALLET home, 5 sections, phone tabs; docs/ui | |
| C3 | PARTIAL | e7f4201 | badges + sticky table on new Home only | old tables unchanged |
| C4 | PARTIAL | e7f4201 | skeletons, 'N sec pehle', hidden-tab pause | no charts |
| C5 | PARTIAL | e7f4201 | human messages on new Home/banner | Settings not regrouped |
| C6 | DONE | e7f4201 | 7 pages x 2 sizes 0 console errors, no h-scroll; 16 requests, 261 KB, largest 238 KB | |
| X1 | DONE | 68b0dd0 | docs/MASTER_PLAN_RESULTS.md (5 complete scans, 0 errors/h, 428-435 MB, /health 0.70 s) | one instance, ~4 h |
| X2 | DONE | (this commit) | docs/MASTER_PLAN_FINAL_REPORT.md | |


## Deploys
- D1: 6390321 pushed 22:37:27 UTC, live 22:38:49 (/health commit 6390321, HEAD 200, /wp-admin 404). Suite before: 2,568 passed / 0 failed.
- D2: 02d12c3 pushed 23:07:43 UTC, live 23:09:21; /health/details: trading enabled, self-check 4/4 OK, 54/54 candles fresh. Suite before: 2,596 passed / 0 failed.
- D3: 3eabeac pushed 03:37:47 UTC, live 03:39:34; self-check 4/4 OK, 35/35 fresh, HEAD 200, app.js gzipped 236,854 bytes. Suite before: 2,599 passed / 0 failed. CI on D1 and D2: success.
- After D3: 3 complete scans (3,450 s cold, 1,948 s and 1,964 s warm), 0 errors, 409-423 MB. Committed, NOT deployed: 20736c4 (CoinGecko retry cap) - ride along with the next needed deploy.
