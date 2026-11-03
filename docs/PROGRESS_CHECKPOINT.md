
---
# PART 2 RESUME NOTES (2026-11-03, second session)
- Server on 8431 stopped (PID 14716). Worktree `D:\sindhu_recovery` = branch `recovery/stable` (base main b2e790c + all 13 Codex commits cherry-picked cleanly, then fix commits).
- Commit 0504b08: hermetic tests/conftest.py (temp SINDHU_DATA_DIR + init_db), expiry test made date-relative, nav test includes control_room. Fixes 33/35 original "env" failures.
- requirements.lock.txt added (75 pkgs, from scratch venv at scratchpad/venv). Playwright installed into same venv. Node NOT installed (BLOCKED-USER for market_history tests).
- Baseline: orig tree + hermetic conftest running -> scratchpad/pytest_orig2.log.
- Commits so far on recovery/stable (after 13 Codex cherry-picks): hermetic tests; remove /preview bypass; market-data rejection WARNING+health metric; explicit delivery guard (OWNER main|cloud|any|disabled, logged reason); 60s sweep pinned in tests.
- KEY FINDING: 60s sweep (TELEGRAM_SWEEP_INTERVAL_SECONDS=60, paper_trading/engine.py) EXISTS in main and Codex (since 2026-09-14; earlier hourly). Earlier report row F25 "not found" is WRONG - retracted.
- KEY FINDING: cloud_runtime/app.py: if SINDHU_SHARED_PAPER_ENABLED=1 the lifespan runs ONLY the shared scanner subprocess and skips legacy engine, telegram commands, daily reports, challenge schedulers and ALL delivery; cloud_shared_scanner.start() even REQUIRES SINDHU_TELEGRAM_DRY_RUN=1 and SINDHU_PUBLIC_SIGNAL_OWNER=disabled. A Cloud deployed with shared mode on sends zero signals by design.
- concepts.py: KEPT (proof: old S/R level == real pivot only 1-12% of bars, new 100%, both causal; BOS events drop ~43%; RSI gain-only 50->100).

## 2026-11-03 Render facts (via connected Render connector, read-only)
- Service Sindhu-cloud--1 (srv-dabhrd8jo6nc739e08k0) tracks codex/trading-intelligence, autoDeploy on, plan FREE, region oregon. LIVE deploy = c223070 (since 2026-10-16). No Render Postgres (Neon is the DB).
- LOGS PROVE: Cloud runs the Codex shared scanner: lines like {"scanner":"RUNNING","cycle":N,"results":[BTCUSDT,ETHUSDT]} - only 2 symbols, opened 0, no Telegram. One cycle error 'Stale closed market candles rejected.' (ETHUSDT 03:00Z).
- Free plan sleeps: instance shut down 03:09Z, new instance started on request 04:07Z -> signals stop while asleep.
- Other services on the same account: Trading-best / -1 / -2 (python bot.py, repo Trading-best-), alpha-signal-bot, Trading-main future, sindhu-agency, Sindhu-cloud- (main). Several `bot.py` services may poll the same Telegram bot token.
