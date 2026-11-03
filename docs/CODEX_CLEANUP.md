# Codex cleanup (branch recovery/clean, from recovery/stable; pre-cleanup tag = recovery/stable tip)

Owner decision: most of Codex's work is useless -> remove; keep only what has proven value. Everything removed is still in git (tag `pre-cleanup`, branches `codex/*`), so the cleanup is reversible by `git revert`/checkout. Cloud Postgres already contains the Codex tables (`shared_events`, `shared_sessions`, `paper_scan_log`, `intelligence_*`...). They are left in place and nothing in this branch drops them.

## Decision per Codex commit
| # | Commit | What it added | Decision | Reason |
|---|---|---|---|---|
| 1 | 5fa95f3 educational trading intelligence + virtual sessions | `trading_intelligence/`, How-to-Trade page, intelligence API, `signal_ownership.py`, Telegram dry-run flag, `concepts.py` S/R+RSI fixes | **REMOVE** package/page/API; **KEEP** `concepts.py`, `signal_ownership.py`, dry-run flag | education/exams do not help signals/backtest/paper; the kept parts are proven (see below) |
| 2 | 4a68d85 resumable public candle archives + offline research | `market_history/` (Node+parquet downloader) | **REMOVE** | needs Node (not installed), off the signal path |
| 3 | 3caae19 scan diagnostics + harden isolated paper controls | `market_data_guard.py`, `scan_telemetry.py`, engine scan lock, SAFE_START refusal | **KEEP** | closed-candle validation, per-scan receipts (pruned by `db_size_guard`) and a duplicate-scan lock all help diagnose missing signals; stale-candle skips now log WARNING + health metric |
| 4 | 328f405 verified historical research + cloud safety diagnostics | `historical_lab`, quality API, Signal Control Room, `risk_department` cloud fallbacks | **REMOVE** lab/API/control room; **KEEP** the `risk_department.py` UNAVAILABLE fallbacks | fallbacks stop the risk page crashing on the curated cloud schema |
| 5 | f45d14f isolated costed shared paper wallet | shared wallet, engine `_shared_execution` hook | **REMOVE** modules; inert hook (`getattr(..., None)`) left in `paper_trading/engine.py` | removing the hook means re-testing the engine core for no gain; it is never installed |
| 6 | 67a6f29 PostgreSQL shared journal handover | shared journal/transfer SQL | **REMOVE** | owner decision 3 (legacy engine on Cloud) |
| 7 | db741ba fix mixed-resolution timeframe joins | `mtf_context.py` `as_unit("ns")` | **KEEP** | real bug fix (join key dtype mismatch on newer pandas), test kept |
| 8 | 2d08572 remove frozen-replay overhead | `configured_strategy.py` event-column refactor | **REMOVE** (restored from main) | pure performance refactor of the strategy hot path, unproven, adds risk |
| 9 | 77cfdbd bounded recovery of interrupted research | research retry | **REMOVE** | research only |
| 10 | e972a12 recover dashboard startup, gate fresh shared sessions | `app.js` token timeout/error text, Neon "no 30-day expiry" in settings, shared gating | **KEEP** app.js + settings tweak; **REMOVE** shared gating | token fetch no longer hangs when the free Render service is asleep; Neon DB must not show a Render 30-day expiry |
| 11 | 5f6bffb opt-in Cloud shared paper scanner | `cloud_shared_scanner`, lifespan branch that skipped ALL delivery | **REMOVE** | this branch (with `SINDHU_TELEGRAM_DRY_RUN=1`, owner=`disabled`) is the most likely reason Cloud sent no signals |
| 12 | 00d8f0a stable strategy hashes across line endings | paper allowlist hashing | **REMOVE** | belongs to the shared scanner allowlist |
| 13 | c223070 Combined Balance + engine controls on shared wallet | shared wallet wiring in paper_trading API | **REMOVE** (API restored from main) | owner decision 3 |

## Recovery additions kept (all on recovery/stable, proven by tests)
hermetic test config + library isolation; `/preview` anonymous bypass removed (and its link on the login page); stale-candle WARNING + health metric; `SINDHU_PUBLIC_SIGNAL_OWNER` (main|cloud|any|disabled) with logged reason and startup delivery banner (`delivery_report`) + health check "Public signal delivery"; DB size guard + scan-log pruning; no klines to Postgres; archive-based reset-to-100; one-connection read handlers (speed).

## Result for Cloud
`SINDHU_SHARED_PAPER_ENABLED` now has no effect (a WARNING is logged if it is set). The Cloud app always starts the legacy engine, Telegram commands, daily reports, challenge schedulers and every delivery scheduler.

## concepts.py before/after (strategy logic)
See the "Backtest comparison" section below (filled after the run).
