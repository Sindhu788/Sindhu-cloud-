# MASTER_PLAN_STATE
plan_version: 1
started_at: 2026-11-05 ~20:55 UTC (the laptop clock said 5 Nov UTC; the session header said 6 Nov)
last_update: 2026-11-05 23:00 UTC
current_step: A23 (scripts being written)
next_action: finish ops/windows_tasks (daily_health_report.py written; monthly_export, weekly_backup, install/remove cmd NOT yet written), A25-A26 docs, B6-B7, wallet.ensure at startup, full suite, D3 push of e7f4201+, X1 measure, X2 report
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
| A3 | DEFERRED (after D2) | | | WebSocket feed; would only help warm scans, not the cold 20-day 1m download; Cloud ON needs owner OK anyway |
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
| A16 | PARTIAL | 759cb5b | tests/test_dashboard_password.py (5 passed) | kill-switch button + modal: Part C |
| A17 | DONE | 69e74e0 | tests/test_self_check.py (6 passed); local + Cloud saved settings validate clean | |
| A18 | DONE | 6c803ad | per-series lines counted in [scan-stages] | log lines/hour before vs after: X1 |
| A19 | PARTIAL | (A19 commit) | /api/summary cached; tests/test_summary_api.py | home page uses it in Part C; memory: D1 instance 217-361 MB during cold prefetch vs 535 MB before (single instance, NOT a steady-state number) |
| A20 | DONE (API) | 6c803ad | freshness_counts on /health/details | 'Data purana' badge: Part C |
| A21 | DONE (SQLite) / BLOCKED (Postgres) | 61de22f | docs/SETTINGS_TEST_REPORT.md 50/50 | no throwaway Postgres |
| A22 | DONE (local) | 46b1656 | tools/parity_check.py, docs/PARITY.md, OWNER_DECISIONS flags | Cloud hash after D2 |
| A23 | TODO | | | |
| A24 | TODO | | | |
| A25 | TODO | | | |
| A26 | TODO | | | |
| B1 | DONE | 7388c1b | docs/BENCHMARK_PREREGISTRATION_V2.md committed before data; hash 6abba148; Amendment 1 (universe + delisting rule) before any code/result | |
| B2 | DONE | (this commit) | D:\sindhu_data\daily 20 files + manifest_daily.json; docs/DATA_QUALITY.md B2 section PASS | |
| B3 | DONE | 0195031 | tests/test_benchmark_v2.py (12 passed) | |
| B4 | DONE | (B4 commits) | D:\sindhu_runtime\bt_jobs\BT-RUN-v2 (23 units + verdicts.json); run 1 kept | amendment 2: simulator bug |
| B5 | DONE | 7f46b03 | docs/STRATEGY_V2_REPORT.md: both FRAGILE (fail FDR only) | SVG charts (no plotting library) |
| B6 | TODO | | | |
| B7 | TODO | | | |
| C1 | TODO | | | |
| C2 | TODO | | | |
| C3 | TODO | | | |
| C4 | TODO | | | |
| C5 | TODO | | | |
| C6 | TODO | | | |
| X1 | TODO | | | |
| X2 | TODO | | | |


## Deploys
- D1: 6390321 pushed 22:37:27 UTC, live 22:38:49 (/health commit 6390321, HEAD 200, /wp-admin 404). Suite before: 2,568 passed / 0 failed.
- D2: 02d12c3 pushed 23:07:43 UTC, live 23:09:21; /health/details: trading enabled, self-check 4/4 OK, 54/54 candles fresh. Suite before: 2,596 passed / 0 failed.
- Part C committed e7f4201 (NOT deployed yet; needs D3).
