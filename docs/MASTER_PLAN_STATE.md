# MASTER_PLAN_STATE
plan_version: 1
started_at: 2026-11-05 ~20:55 UTC (the laptop clock said 5 Nov UTC; the session header said 6 Nov)
last_update: 2026-11-05 22:05 UTC
current_step: A3/A9 (next)
next_action: A3 decision (WebSocket), then A9 wallet; D1 deploy after A1-A8 + full suite
background_jobs:
  - id: SUITE3   status: DONE  marker_dir: /tmp/full_runs.log  done: 3/3
  - id: BT-DATA  status: DONE  marker_dir: D:\sindhu_runtime\bt_jobs\BT-DATA  done: 20/20
  - id: BT-RUN   status: NOT STARTED  marker_dir: D:\sindhu_runtime\bt_jobs\BT-RUN  done: 0/N

Working copy: D:\sindhu_clean (branch recovery/clean); pushes go through D:\sindhu_merge to origin codex/trading-intelligence (fast-forward only).

| step | status | commit | evidence | notes |
|---|---|---|---|---|
| F1 | DONE | 4e9b5ff | 3 consecutive green full runs (2,509 passed, 0 failed each, 21:22/21:39/21:56 UTC); docs/FINAL_MASTER_PROMPT_CLOSEOUT.md | previous prompt closed; worktree D:\sindhu_wtA branch masterplan/partA |
| F2 | IN_PROGRESS | 7388c1b | docs/MASTER_PLAN_BASELINE.md (Cloud part: RSS 517-536 MB, ~60 Neon errors/h, prefetch 3,828 s, /health >60 s) | local dashboard part pending |
| F3 | DONE | | B1 + B2 done (below) | |
| A1 | DONE | ee8b342 | tests/test_health_head_and_probes.py (6 passed) | |
| A2 | DONE | 3cf0dd9 | tests/test_live_candles_incremental.py (5 passed); frozen golden identical | Cloud before/after rows/pages measured at D1 |
| A3 | TODO | | | |
| A4 | DONE | (this commit) | tests/test_rate_limit.py (5 passed) | token bucket okx 8/s, 3 parallel, halve 10 min after 50011 |
| A5 | DONE | 3cf0dd9 | tests/test_fetch_deadline.py (6 passed) | per-coin 180 s, prefetch 600 s, stall report 120 s |
| A6 | DONE | 3cf0dd9 | tests/test_db_breaker_and_log_dedup.py (8 passed), pool tests | keepalives, 1 retry, breaker 30->300 s, loop dedup |
| A7 | DONE | 6b1b1eb | tests/test_gate_exchange.py (+4) | cloud default okx; gate reads position exchange on Cloud |
| A8 | DONE | (this commit) | tests/test_confluence_unknown.py (3 passed) | regime missing -> UNKNOWN -> withheld |
| A9 | TODO | | | |
| A10 | TODO | | | |
| A11 | TODO | | | |
| A12 | TODO | | | |
| A13 | TODO | | | |
| A14 | DONE | (this commit) | tests/test_public_signals_default_off.py (10 passed) | SINDHU_PUBLIC_SIGNALS default off; disclaimer + validation class always |
| A15 | TODO | | | |
| A16 | TODO | | | |
| A17 | TODO | | | |
| A18 | TODO | | | |
| A19 | TODO | | | |
| A20 | TODO | | | |
| A21 | TODO | | | |
| A22 | TODO | | | |
| A23 | TODO | | | |
| A24 | TODO | | | |
| A25 | TODO | | | |
| A26 | TODO | | | |
| B1 | DONE | 7388c1b | docs/BENCHMARK_PREREGISTRATION_V2.md committed before data; hash 6abba148; Amendment 1 (universe + delisting rule) before any code/result | |
| B2 | DONE | (this commit) | D:\sindhu_data\daily 20 files + manifest_daily.json; docs/DATA_QUALITY.md B2 section PASS | |
| B3 | TODO | | | |
| B4 | TODO | | | |
| B5 | TODO | | | |
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
