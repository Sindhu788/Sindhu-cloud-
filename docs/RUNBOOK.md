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
