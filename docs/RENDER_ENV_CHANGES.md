# Render environment changes for service "Sindhu-cloud--1" (srv-dabhrd8jo6nc739e08k0)

Apply AFTER the `recovery/clean` merge has deployed (or before - these are safe either way). Values below contain no secrets. Secret values (bot token, channel id, DATABASE_URL, sync secret) must already be set and are NOT changed here.

## Evidence for why these changes are needed
Render logs for this service show the Codex shared scanner running (`{"scanner":"RUNNING","cycle":N,"results":[BTCUSDT,ETHUSDT]}`): only two symbols, nothing opened, no Telegram. That mode requires `SINDHU_TELEGRAM_DRY_RUN=1` and `SINDHU_PUBLIC_SIGNAL_OWNER=disabled`, which switch off all public delivery.

## Set / change
| Variable | Value | Why |
|---|---|---|
| `SINDHU_SHARED_PAPER_ENABLED` | **remove** (or `0`) | shared scanner mode was removed; the flag is ignored and only logs a WARNING |
| `SINDHU_TELEGRAM_DRY_RUN` | **`0`** (or remove) | `1` blocks every Telegram network send |
| `SINDHU_PUBLIC_SIGNAL_OWNER` | **`cloud`** (or remove; default is cloud) | `disabled` blocks all public signals; `main` would block Cloud |
| `SINDHU_SAFE_START` | **remove** (or `0`) | `1` disables scanning and delivery |
| `SINDHU_CLOUD_MODE` | `1` (already in render.yaml) | marks this process as the Cloud publisher |
| `SINDHU_LIVE_CANDLES` | `1` (already in render.yaml) | fetch live candles instead of storing them (keeps the DB small) |

## Must already exist (names only)
`DATABASE_URL` (Neon, keep as is), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`, optional `GROQ_API_KEY` (import-time AI only; never used in backtest/paper/signals).

## Optional
| Variable | Default | Meaning |
|---|---|---|
| `SINDHU_DB_SIZE_LIMIT_MB` | 500 on Postgres | capacity for the size warning (Neon free tier is ~512 MB; DB is currently ~19 MB) |
| `SINDHU_DB_WARN_PCT` | 80 | warn at this usage |
| `SINDHU_SCAN_LOG_RETENTION_DAYS` / `SINDHU_SCAN_LOG_MAX_ROWS` | 7 / 20000 | pruning of the scan-receipt log |

## Telegram settings (stored in the DB, not env) that must be true for signals to go out
`master_send_enabled=true`, `auto_send_enabled=true`, bot token and channel id set, `channel_group_filter` = Profitable+Challenge only (currently the key is absent => default "all"; check the Telegram settings page), `auto_send_high_confidence_only` as desired, silent hours off or acceptable. Per signal the gates still apply: confluence threshold, Wilson 25-trade, freshness 15 min, price drift 0.5 %, 60 s missed-signal sweep, rate limit.

## How to verify after applying
Startup log contains `[telegram] Public signal delivery: READY` (otherwise it lists every blocker). Health page "Public signal delivery" check is green. `GET /health` returns `{"status":"ok","cloud_mode":true,...}`.

## Free plan
The service sleeps after ~15 min without requests (log: Shutting down 03:09Z, restart on next request 04:07Z). The engine and signals are stopped while asleep. Use an external pinger on `/health` every 5-10 minutes or a paid plan.
