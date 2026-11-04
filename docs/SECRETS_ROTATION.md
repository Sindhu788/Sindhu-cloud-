# Secrets rotation guide (nothing has been rotated by Claude - this is a guide only)

Rule 1: **rotate ONE secret at a time, verify, then do the next.** Rule 2: never paste a secret into chat, a document, a URL or a commit. Rule 3: take a backup first (docs/RUNBOOK.md section 9, `scripts/backup_cloud_export.py`). Rule 4: do it when no trade is open that you care about; each Render change redeploys the service (about 2-4 min, no scans and no signals meanwhile; the free instance also cold-starts afterwards).

Env var NAMES below were read from the code (`grep environ`) on 4 Nov 2026; Render env var names of OTHER services are NOT VERIFIED.

## Safe order (lowest risk first)
1. Groq API key  ->  2. Telegram proxy login  ->  3. Sync secret  ->  4. Neon database password  ->  (5. Telegram bot token, only if it leaked)
After each: run the verification block at the bottom. If it fails, roll back that step before touching the next.

---
## 1. Groq API key (AI import-time helper only; trading never calls it)
- Where used: env `GROQ_API_KEY` (read by `ai_integration/config.py`; it seeds `ai_settings.json` on the first save). On the Cloud free plan the file is rebuilt after each restart, so a new env value should be picked up after the redeploy (NOT VERIFIED - check Settings > AI after the redeploy). Locally the key is stored in `D:\sindhu\data\config\ai_settings.json` (change it in the dashboard Settings > AI provider).
- Steps: create a NEW key in the Groq console -> Render > Sindhu-cloud--1 > Environment > edit `GROQ_API_KEY` > Save (redeploys) -> update the local Settings -> delete the OLD key in the Groq console.
- Downtime: one redeploy. Rollback: put the old key back (only if you have not deleted it yet).

## 2. Telegram proxy login (only if a proxy is configured; Cloud normally needs none)
- Where used: Telegram setting `proxy_url` (write-only, e.g. `socks5://user:pass@host:1080`), stored in the app's Telegram settings (Cloud: database table `cloud_settings`; Local: the Telegram settings file). Not an env var. The dashboard shows only `proxy_configured: true/false`.
- Steps: get the new proxy login from the provider -> dashboard Settings > Telegram > proxy -> paste the new URL -> Save -> (Local too if used) -> ask the provider to disable the old login.
- Downtime: none (no redeploy). Rollback: paste the old URL back.

## 3. Sync secret (Local -> Cloud strategy sync, also used by `/api/ops/settings-snapshot-sync`)
- Where used: Cloud: database `cloud_settings` key `strategy_sync_secret` (created automatically by `get_or_create_sync_secret()` when missing). Local: `data/config/strategy_sync_secret.json` and the copy in `data/config/cloud_sync_target.json` (`sync_secret`). The header name is `X-Sindhu-Sync-Secret`.
- Steps: (a) pick a time with no sync running; (b) on the Cloud, delete the `strategy_sync_secret` row in `cloud_settings` (Neon SQL editor: `DELETE FROM cloud_settings WHERE key='strategy_sync_secret'`) - the next call generates a new one; (c) read the new value from the Cloud dashboard (Settings > Cloud Sync, NOT VERIFIED exact label) and put it into the local `cloud_sync_target.json`; (d) test a sync.
- Downtime: none for trading. Sync fails between (b) and (c). Rollback: re-insert the old value (keep a copy until the test passes).

## 4. Neon database password (highest impact: everything on Cloud depends on it)
- Where used: Render env `DATABASE_URL` (read by `data_engine/db_backend.py`); also any local helper that stores the Neon URL, e.g. `data/config/neon_runtime_connection.json` and scripts that read it. If the repo/CI ever received it, also GitHub Actions secrets (none known: NOT VERIFIED).
- Steps: (a) Neon console > project `snowy-hall-06890228` > Roles > the app role > **Reset password** (copy the new connection string; do not close the page); (b) Render > Environment > edit `DATABASE_URL` with the new string > Save (redeploy starts); (c) while it redeploys update the local `neon_runtime_connection.json`; (d) verify (below); (e) only then delete the old string from wherever you saved it.
- Downtime: from the moment the password is reset until the redeploy is live (~2-4 min): no scans, no signals, dashboard errors. Do (a) and (b) back-to-back.
- Rollback: Neon lets you reset the password again to a value you choose; put that into `DATABASE_URL`.

## 5. Telegram bot token (only if it leaked)
- Where used: Render env `TELEGRAM_BOT_TOKEN` (and `TELEGRAM_CHANNEL_ID`), stored in the Telegram settings after first start; Local token must stay EMPTY (local never sends).
- Steps: BotFather > `/revoke` for the bot (new token is shown once) -> Render env `TELEGRAM_BOT_TOKEN` -> Save -> check that the bot is still an admin of the channel -> check the old Render services do not still hold the old token (docs/OWNER_TODO.md section L).
- Downtime: one redeploy; signals stop meanwhile. Rollback: BotFather can only issue another new token; there is no way back to the revoked one.

## Dashboard login password / API token
Login passwords live in the `auth_*` tables (change them in the dashboard). The API token (`api_token` row in `cloud_settings`) is regenerated automatically if you delete that row; browsers fetch the new one from `/api/token` on reload.

---
## Verification block (after EACH rotation)
1. `curl https://sindhu-cloud-1.onrender.com/health` -> `status ok`, new `commit`/`started_at`, `engine_running true`, `db_backend postgres`.
2. Render > Logs: `Restoring to ON`, `engine started`, `Public signal delivery: READY`, no `password authentication failed`.
3. Wait for one scan: log line `scan finished: complete ...` or a new row in `paper_scan_log` (docs/RUNBOOK.md section 12).
4. Dashboard: log in, open Paper Trading (data loads = database connection works). `GET /api/ops/warnings` shows nothing new.
5. After the Telegram steps: the owner chat shows no "send failed" alert in the next hour (owner alerts must be set up first: docs/OWNER_ALERTS_SETUP.md).
