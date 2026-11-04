# Day 4 baseline (4 Nov 2026, 12:50-13:00 UTC) and inventory of local-only work

| Item | Value | Source |
|---|---|---|
| Cloud `/health` | commit `d5aee63`, engine_running true, postgres, started_at 12:48:40Z | curl |
| External pinger | **not seen**: the only `GET /health` in the Render app log for the 80 minutes before was my own request (12:52:59 from my PC's address); `/api/ops/pinger` needs a login, so the log was used | Render log search |
| Local app | `127.0.0.1:8420` was DOWN at the start (the supervisor died with the earlier session). Relaunched with `D:\sindhu_runtime\start_supervised.cmd`; health `{"status":"ok","safe_start":true}` after ~45 s; one "health check failed (1/3)" line during start-up, then stable | supervisor.log |
| Git | local `recovery/clean` HEAD `ec2ceae`; deployed `d5aee63` (merge); origin = `d5aee63`. Local-only commit at the start: `ec2ceae` (D31 refresh throttle, supervisor lock, final Day 3 checkpoint) | git |
| Render services in the workspace (8) | Sindhu-cloud--1 (main service, branch codex/trading-intelligence), **Sindhu-cloud- (branch main, `python cloud_runtime/app.py`, auto-deploy, not suspended)**, Trading-best, Trading-best-1, Trading-best-2 (`python bot.py`), Trading-main future, alpha-signal-bot, sindhu-agency, zaiqa-royale-portfolio (static) | Render API |
| Scans on Cloud at the start | newest complete receipt still 3 Nov 20:33; every receipt since is `interrupted` | Neon `paper_scan_log` |
| CPU / memory (instance after the 08:18 start) | CPU 0.007-0.075 of 0.15; RSS 245-295 MB | Render metrics |

## Inventory of local-only work (Step 2)
| What | Where | State |
|---|---|---|
| Day 3 closeout docs (checkpoint, decisions D31, fix log, runbook 11b) | commit `ec2ceae` and earlier docs commits | now deployed (pushed with Day 4 push 1, `06d2051`) |
| 15-second refetch throttle (D31) | `data_engine/live_candles.py`, `tests/test_live_candles.py` in `ec2ceae` | **removed on Day 4** after the A/B showed nothing to throttle (docs/SCAN_PROFILE.md section 7); its related tests were run first: 15 passed |
| Supervisor lock fix and scripts | `scripts/local_runtime/*`, `D:\sindhu_runtime\*` | deployed copies in the repo; runtime copies in use |
