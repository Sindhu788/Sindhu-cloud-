# OWNER / MANAGER TODO (after the recovery deploy)

Deployed: commit `4d7e31b` (merge of `recovery/clean`) on `codex/trading-intelligence` -> Render service "Sindhu-cloud--1". Rollback: redeploy tag `pre-recovery-backup` (= c223070, the previous live commit) or `git revert -m 1 4d7e31b` and push.

## 1. Render environment (manager, via Render dashboard / connector) - REQUIRED for signals
See `docs/RENDER_ENV_CHANGES.md`. Until this is done the app starts the legacy engine but still sends NO public signals, because the old values are still set:
- remove `SINDHU_SHARED_PAPER_ENABLED` (or 0)
- `SINDHU_TELEGRAM_DRY_RUN` -> `0` (or remove)
- `SINDHU_PUBLIC_SIGNAL_OWNER` -> `cloud` (or remove)
- remove `SINDHU_SAFE_START` if present
Then check the service log for `[telegram] Public signal delivery: READY`. If it says BLOCKED it lists every reason.

## 2. Telegram settings (Settings page on the Cloud app)
`master_send_enabled` ON, `auto_send_enabled` ON, bot token + channel id set, **channel_group_filter = Profitable + Challenge only** (the key was missing = "all", which would also send Losing-group signals), decide `auto_send_high_confidence_only`.

## 3. Security - rotate (I could not and must not do this)
Proxy credentials (telegram_settings.json), Neon database password (connection string is stored in plain text in `data/config/neon_runtime_connection.json`), strategy-sync secret, Telegram bot token if it was ever pasted anywhere. Move secrets to Render env vars.

## 4. Keep the free Render plan awake
The free plan sleeps after ~15 minutes without requests (logs: shut down 03:09Z, restarted on next request 04:07Z); the engine and signals stop while asleep. Either upgrade to a paid plan, or point an external pinger (UptimeRobot / cron-job.org) at `https://sindhu-cloud-1.onrender.com/health` every 5-10 minutes.

## 5. Other Render services (possible Telegram conflicts)
`Trading-best`, `Trading-best--1`, `Trading-best--2` (all `python bot.py`, repo Trading-best-), `alpha-signal-bot`, `Trading-main future`, `sindhu-agency`, and the old `Sindhu-cloud-` (tracks main). If any of them uses the same Telegram bot token, two processes polling one bot cause "409 Conflict" and lost commands/messages. Suspend the ones you do not use.

## 6. Cloud balance reset to 100 (not run on Cloud)
Tool is ready: `python scripts/reset_paper_balance_to_target.py` (dry-run by default; `--apply` to run; `--allow-cloud` required for Postgres). It archives closed trades into `paper_trade_history_archive`, keeps Wilson/Evolution counters, deletes nothing. Proven on the local DB copy (58 books -> exactly 100, 1,132 trades archived, counters unchanged). Run it on Cloud only after you have confirmed signals flow, and take a Neon backup first (a verified export is at `D:\sindhu_backup_phase0\cloud_export_2026-11-03`).

## 7. Decisions
- Pause the 18 consistently losing strategies? List in `docs/PERFORMANCE_RECONCILIATION.md` (they are all in the "Losing" group already: they trade on paper but send no signals).
- The "+$270.05 over 1,856 trades" figure could not be reproduced from the local or Neon data (both contain the same 1,132 trades). Where did it come from?
- Strategies that use support/resistance or break-of-structure behave differently after the `concepts.py` fix (BOS events about 43% fewer; levels now equal the real pivot). Re-run their backtests before trusting old numbers.
- Real-phone check and one real `/menu` in the Telegram group after step 1.

## 8. Not done in this recovery (honest list)
Full Playwright click-through of every page at desktop and 375 px, an end-to-end import->backtest->paper->signal run with per-stage counts, and real-engine old-vs-new backtests of the top strategies (only a concept-level before/after on BTC/ETH/BNB/XRP 1h was run). Node.js is not installed (no longer needed after the cleanup). Post-17-Sep confidence calibration needs Cloud trades.
