# SINDHU runbook - symptom -> check -> fix (copy-paste)

Facts: Cloud = Render service `Sindhu-cloud--1` (srv-dabhrd8jo6nc739e08k0), URL https://sindhu-cloud-1.onrender.com, deploys on every push to `codex/trading-intelligence`, DB = Neon Postgres. Local = `D:\sindhu_runtime\start_local.cmd` (port 8420, safe mode). Rollback tag: `pre-recovery-backup` (= c223070, OLD Codex scanner - last resort only). Never paste tokens or DB URLs into chats or docs.

## 1. No signals in Telegram
1. `curl https://sindhu-cloud-1.onrender.com/health` must say `"status":"ok"` and `"engine_running":true`. If the first call hangs ~40 s it was asleep (see 3).
2. Render -> Logs, search `Public signal delivery`: `READY` is good; `BLOCKED by:` lists every reason (dry-run, safe-start, owner, token, channel, master/auto send).
3. Search `paper-trading]`: `Restoring to ON` and `engine started` must appear after every restart. If `Staying OFF`: Neon `paper_trading_settings.engine_enabled` is false -> start it again in the dashboard (Paper Trading -> Start).
4. Ask the system why: `GET /api/ops/why?coin=BTC&hours=6` (logged in) shows each decision, the gate that stopped it and the data age; `/api/ops/why-summary` counts by gate. "0 qualified" with reasons such as `No entry rule matched` or the Wilson/confluence gates is NORMAL - the system never forces a signal.
5. Only Profitable and Challenge strategies may send; Losing-group strategies trade but never send.
6. Telegram itself: `telegram_message_log` rows with `success=0` and the `error` text ("already sent a long ... within 15 minutes" = duplicate guard, "too stale" = freshness gate, "Public delivery blocked" = owner guard).

## 2. Stale data (`Stale closed market candles rejected` in the log)
1. The warning names `exchange:symbol:role timeframe`, the last closed candle and its age. Compare with the clock.
2. Cloud uses OKX (Binance and Bybit are blocked from Render). OKX returns at most ~300 candles per request; `data_engine/live_candles.py::_fetch_range` pages until now (fixed 3 Nov). If the last candle is days old for ALL coins the exchange is unreachable (look for `exchange-failover ... unavailable`). If one coin only, that pair may be delisted or illiquid.
3. The guard must never be loosened. The owner chat gets "market data stale" after 5 consecutive bad minutes (needs `personal_chat_id` in Telegram settings).

## 3. Render service asleep (free plan, idle 15 min)
- Symptom: first request ~40 s, dashboard says "Server waking up, retrying...", no scans while asleep.
- Fix: external pinger on `/health` every 1-5 min (docs/OWNER_TODO.md section K) or a paid plan. The GitHub keep-alive workflow does NOT run (default branch is `main`).

## 4. Database unreachable (Neon)
1. `/health` still answers (it does not use the DB). Dashboard pages and scans error; the owner chat gets "database is unreachable".
2. Neon console, project `snowy-hall-06890228`: compute suspended (wakes on connect), storage vs plan limit, password rotated without updating Render `DATABASE_URL`.
3. Size: `GET /api/paper-trading/health-check` shows "Database size"; the app warns at 80 %. Scan receipts and decision traces are pruned to 7 days automatically.

## 5. Telegram not sending although READY
1. Bot token revoked or changed? Render env `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`; the bot must be an admin of the channel.
2. Rate limit (10/hour default), silent hours, `master_send_enabled`, `auto_send_enabled` (dashboard -> Telegram settings).
3. Proxy: Cloud normally needs none. A dead proxy gives "failed after 3 attempts".

## 6. Token conflict (409 Conflict / duplicate messages)
Two processes using one bot token. See docs/OWNER_TODO.md section L. Suspend the old Render services that use the same token. Local must stay `SINDHU_PUBLIC_SIGNAL_OWNER=disabled`.

## 7. Roll back a bad deploy
```bash
git checkout codex/trading-intelligence
git revert -m 1 <bad merge commit>
git push origin codex/trading-intelligence      # auto-deploys the previous tree; never force-push
```
Alternatives: Render dashboard -> Manual Deploy -> choose the previous deploy. Last resort: tag `pre-recovery-backup` (old shared-scanner build: NO signals).

## 8. Local app down
```bat
D:\sindhu_runtime\start_local.cmd
D:\sindhu_runtime\stop_local.cmd
```
Opens http://127.0.0.1:8420 in safe mode. Log: `D:\sindhu_runtime\server.log`. LAN access needs a Windows Firewall inbound rule for TCP 8420. Local never sends Telegram and never scans (by design).

## 9. Backup and restore (tested 4 Nov 2026: 45 tables, 10,377 rows, 0 mismatches)
```bat
rem backup: read-only on Neon, new timestamped folder, auth tables and candles skipped
D:\sindhu_venv\Scripts\python.exe scripts\backup_cloud_export.py D:\sindhu_backup_phase0
rem restore TEST into a throwaway SQLite (refuses to overwrite; exit code 0 only if every table count matches)
D:\sindhu_venv\Scripts\python.exe scripts\restore_export_to_sqlite.py D:\sindhu_backup_phase0\cloud_export_<stamp> D:\sindhu_runtime\restore_test\restored_<stamp>.db
rem local DB + config: stop the app, then copy D:\sindhu\data\database\sindhu.db and D:\sindhu\data\config\*
```
Restoring INTO Neon is deliberately not scripted (needs a human decision). Reset paper balance with `scripts/reset_paper_balance_to_target.py` (dry-run by default, archives trades, never deletes).

## 10. Weekly routine
docs/WEEKLY_REVIEW.md. Quick health: `/api/ops/warnings`, `/api/ops/settings-parity`, `scripts/weekly_scorecard.py`.

## 11. Local app will not start: "DLL load failed ... Application Control policy has blocked this file"
Seen 4 Nov 2026: Windows blocked a pandas DLL inside D:\sindhu_venv (a force-reinstall did not help; a venv under C:\Users\sindh\AppData\Local\Temp worked). Short-term: D:\sindhu_runtime\start_local_tmpvenv.cmd starts the app with the working venv (that venv lives in a temporary folder and may disappear). Permanent fix: create a new venv under C:\Users\sindh\sindhu_venv (python -m venv, then pip install -r requirements.lock.txt) and point start_local.cmd at it, or ask Windows Security > App & browser control (Smart App Control) to allow the folder.

UPDATE 4 Nov: a second fresh venv at C:\Users\sindh\sindhu_venv was blocked the same way ("DLL load failed ... Application Control policy"), so the cause is Windows Smart App Control / App Control reputation blocking newly installed unsigned DLLs, not the folder. Only the venv created earlier in the session temp folder still loads. Owner action: Windows Security > App & browser control > Smart App Control (set to Off or Evaluation) or add an allow rule, then recreate the venv and use start_local.cmd. Until then the local app depends on start_local_tmpvenv.cmd (temporary folder, may vanish after a reboot or cleanup).

## 12. Scans, receipts and the sleep-aware alerts (added 4 Nov 2026, Day 3)
**Where to look when "no scan receipts"**
- Log lines (Render -> Logs): `scan phase exchange+symbols`, `scan phase shortlist`, `scan finished: <outcome>, N coins, E errors, Ns`, and after a cut-off `previous scan was interrupted: ...`.
- DB (Neon): `paper_scan_log` (one row per scan; `outcome` = complete / partial / error / blocked / **interrupted**), `paper_scan_heartbeat` (ONE row `current`: phase, coin i/N, last update; `phase='idle'` means no scan is running). Receipts older than 7 days are pruned.
- `interrupted` = the process was stopped, slept or redeployed in the middle of a scan. It is not an error count and does not trigger the "error spike" alert.

**Housekeeping during long scans.** The 60 s Telegram fresh-signal sweep, the owner watchdog, reconciliation and the DB guard now also run from inside the coin loop (at most once a minute), not only after a whole scan. Their intervals and gates are unchanged.

**Owner alerts are sleep-aware** (owner chat only, rate limited):
| Situation | Behaviour |
|---|---|
| Instance was asleep and just woke (process age < 10 min, or a gap > 3 min between watchdog runs = process was frozen) | `scanner_stalled` and `stale_data` stay quiet during the 10 min grace; cold caches are expected |
| Engine running, no scan progress (no finished scan, no coin progress, no start) for > 20 min (`SINDHU_SCAN_STALL_MIN`) | ALERT "engine is running but showed no scan progress for N min", with "no external pinger seen" or "last external ping N min ago" |
| A long cold scan that is still moving coin by coin | NOT an alert (progress counts) |
| Stale candles for 5 checks in a row after the grace | ALERT, then one RECOVERED message after 2 clean checks |
| "Server restarted" | at most once every 6 h (a free instance restarts on every wake) |
Alerts need `personal_chat_id` (docs/OWNER_ALERTS_SETUP.md); nothing is ever sent to a public channel.

**Is the external pinger working?** `GET /api/ops/pinger` (logged in) shows `pinger_active`, `seconds_since_last_external_ping`, `average_gap_seconds`. Counters live in memory and restart with the process. Render's own health probe is counted separately (it does not keep the service awake). `/api/ops/warnings` shows a `no_pinger` warning when none is seen after the process has been up 15 min.

## 11b. Local app: permanent venv and supervisor (Day 3, 4 Nov 2026)
What was tried, in order: (a) COPY of the working venv to a permanent path -> **works**: `D:\sindhu_venv_stable\Scripts\python.exe` imports pandas/numpy/fastapi without the Application Control block (Windows judged the already-trusted files the same at the new path; a freshly pip-installed venv is still blocked, see section 11). Backup of the original: `D:\sindhu_backup_venv_20261104`. (b) signed Python distribution: not needed. (c) WSL2/Docker: not installed (WSL says "not installed", docker not found) - not used. No Smart App Control / Defender setting was touched. Limits: the copy has no `psycopg2` (not needed for the local SQLite app); `pip install` of NEW packages into it may be blocked again.
Commands (copies of the scripts are in `scripts/local_runtime/`):
```bat
D:\sindhu_runtime\start_supervised.cmd   rem start app under the supervisor (health check every 30 s, restart after 3 failures)
D:\sindhu_runtime\start_local.cmd         rem start without supervisor (foreground)
D:\sindhu_runtime\stop_local.cmd          rem stop supervisor and app
```
Logs: `D:\sindhu_runtime\server.log` (app), `supervisor.log`. Above 20 MB a log is moved to `logs_archive\` (archived, never deleted).
Safety: the local app can never publish public signals - four independent blocks (checked 4 Nov): `SINDHU_PUBLIC_SIGNAL_OWNER=disabled`, `SINDHU_SAFE_START=1`, `SINDHU_TELEGRAM_DRY_RUN=1`, and the local Telegram settings have no bot token, no channel id and master send OFF. The supervisor kills (and does not restart) an app whose /health does not say `safe_start: true`.
Forced-restart test (4 Nov 14:32 local): listener killed -> supervisor log `health check failed (1/3)`, `app exited with code 1`, `started app pid ...` -> /health ok again ~3 min later.

## 13. Backup and restore commands (verified 4 Nov 2026)
```bat
rem 1. read-only export of the Cloud database into a NEW timestamped folder (login tables and candle tables are skipped)
D:\sindhu_venv_stable\Scripts\python.exe scripts\backup_cloud_export.py D:\sindhu_backup_day4
rem 2. throwaway restore test (refuses to overwrite; exit code 0 only if every row count matches)
D:\sindhu_venv_stable\Scripts\python.exe scripts\restore_export_to_sqlite.py D:\sindhu_backup_day4\cloud_export_<stamp> D:\sindhu_runtime\restore_test\restored_<stamp>.db
```
(The scripts need the `psycopg` package; on 4 Nov they were run with the scratch venv, which has it. The Neon connection string is read from `data/config/neon_runtime_connection.json` on this PC; it is never printed or committed.) Result 4 Nov: 51 tables exported, 49 restored, 0 mismatches, 11,909 rows.
**Automating it safely:** a weekly Windows Task Scheduler job (user level, no admin) that runs step 1 into `D:\sindhu_backup_<date>` and then step 2; keep the connection string only in that one local file (never in the task, a script argument or the repo); keep at least the last 4 backups; check that the restore step exits with code 0. Neon also keeps its own point-in-time history (plan limits NOT VERIFIED).

## 14. Day 4 operational notes
- Postgres connections are pooled (max 4 idle, rolled back on return, checked after 30 s idle, retired after 4 min). Switch off with the Render env var `SINDHU_PG_POOL=0`. Counters: `db_backend.pool_stats()`.
- Candle prefetch: `SINDHU_PREFETCH_WORKERS` (default 4; use 2 or 0 if the log shows `[exchange-retry]` lines with RateLimitExceeded).
- Memory guard: `SINDHU_MEM_SOFT_MB` (400) and `SINDHU_MEM_HARD_MB` (450); log lines start with `[memory-guard]`.
- Log lines to read after a deploy: `scan phase ...`, `concept memo this scan: N hits`, `scan finished: ... Ns`, `[exchange-retry] ...`, `[live-candles] REFETCH ...`, `scan shows no progress for Ns; engine thread is at: ...`.


## 11c. Local app "not opening" - plain-language guide (Day 5, 4 Nov 2026)
**Quick fix: double-click `D:\sindhu_runtime\OPEN_SINDHU.cmd`.** It starts SINDHU if it is not running, waits up to 3 minutes (the first start takes 40-80 s because it loads the data libraries) and opens http://127.0.0.1:8420 in your browser. Running it twice is safe: it says "already running".

**Why it stopped opening (found on 4 Nov):**
1. *The app died when the Claude/terminal session that started it ended.* Programs started from a session are closed with it. The new launcher `launch_detached.py` starts the supervisor detached, so closing the terminal no longer stops it. (Verified: the supervisor's parent process is gone and the supervisor keeps running. A computer RESTART still stops it - see "start automatically" below.)
2. *The address you used changed.* The laptop's WiFi address is given out by the router and changed from 192.168.1.111 to 192.168.1.113. Use `http://127.0.0.1:8420` on the laptop itself. From a phone you need the CURRENT address (`ipconfig` -> IPv4) AND a Windows Firewall rule for TCP port 8420 (none exists; I did not add one - it is a security setting).
3. *Slow start looks like "not opening".* Ready after 56 s on 4 Nov; the supervisor now waits for the app instead of counting a failure during start-up.

| Symptom | Check | Fix |
|---|---|---|
| Page does not open | `curl http://127.0.0.1:8420/health` or open it in the browser | double-click OPEN_SINDHU.cmd |
| Still not after 3 minutes | last lines of `D:\sindhu_runtime\supervisor.log` and `server.log` | "another supervisor is already running" = it IS running, wait; "UNSAFE" = the app refused to run (local must stay in safe mode) |
| Port in use by something else | `netstat -ano | findstr :8420` | close that program, or run `D:\sindhu_runtime\stop_local.cmd` and start again |
| Want to stop it | - | `D:\sindhu_runtime\stop_local.cmd` |

**Tested 4 Nov:** normal start 56 s; forced kill of the app -> back in 52 s (supervisor restarts it); starting a second time -> "already running", no duplicate supervisor, one listener; start from the documented command works. **Laptop sleep/wake: NOT VERIFIED** (I cannot suspend the laptop from here; the supervisor only loops on timers, so it should simply carry on after wake - check once yourself by closing the lid for a minute).
**Start automatically at Windows login (owner step, not done by me):** press Win+R, type `shell:startup`, and put a shortcut to `D:\sindhu_runtime\OPEN_SINDHU.cmd` in that folder. This is a normal per-user setting; I left it to you because it is a persistent system change.

## 11d. Local app resilience test (Day 6, 5 Nov 2026) - what was actually tried
| Scenario | Result |
|---|---|
| Normal start with the documented launcher (`OPEN_SINDHU.cmd` = `launch_detached.py --wait`) | ready in **14 s** (app had been dead since the previous work session) |
| Start it a second time while it runs | prints "already running", **no second instance** (process tree: one supervisor, one server) |
| Forced kill of the server process | the supervisor restarted it; healthy again after **22 s** |
| Laptop sleep and wake | **NOT VERIFIED** - not tested unattended (it would suspend this session and the downloads). When the laptop wakes, just double-click `OPEN_SINDHU.cmd`; it starts the app only if it is not running |
| The app after the working session / PC restart | it does NOT start by itself after a PC restart (no scheduled task by design); double-click `OPEN_SINDHU.cmd` |
