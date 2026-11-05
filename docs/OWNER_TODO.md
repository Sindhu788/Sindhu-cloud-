# OWNER / MANAGER TODO (only what truly needs a person) - updated 4 Nov 2026

**Live state:** Cloud (Render `Sindhu-cloud--1`) runs the legacy engine on 10 liquid coins (OKX feed), Telegram delivery READY, and has already sent live signals (first: 3 Nov 21:33 UTC). Local is safe-mode only and can never send. Rollback: docs/RUNBOOK.md section 7.

## DAY 3 ORDER (4 Nov 2026) - do these first, each takes minutes
1. **Pinger** (5 min) - docs/PINGER_SETUP.md. Without it the free Render instance sleeps, restarts, and every restart costs a 15-17 minute cold scan (measured). After 10 minutes open `/api/ops/pinger` while logged in: `pinger_active` must be true.
2. **Owner alerts** (5 min) - docs/OWNER_ALERTS_SETUP.md: get your chat id, paste it in Settings > Telegram > Private Alerts, Save, then click "Send test alert to my chat" yourself (I never clicked it).
3. **Three decisions** (10 min) - docs/OWNER_DECISIONS.md: (a) `auto_send_high_confidence_only`, (b) strategy pauses (8 recommended), (c) opposite-direction signal policy (needs a small code change if you say yes).
4. **Secrets rotation** (30 min, one secret at a time) - docs/SECRETS_ROTATION.md: Groq key, proxy login, sync secret, Neon password.
5. **Authenticated Cloud page check** (10 min, I could NOT do it: no login available to me) - log in to https://sindhu-cloud-1.onrender.com and check, read-only: (a) the yellow/red warning bar at the top reads sensibly (it should mention the missing pinger/chat id until you do 1-2); (b) Paper Trading page: positions list loads, balances start near 100, no red error toast; (c) Settings > Telegram: chat id field present and the new "Send test alert" button; (d) CEO page loads in under ~60 s after a sleep; (e) Live Logs shows `scan finished: complete` lines; (f) `/api/ops/warnings`, `/api/ops/pinger`, `/api/ops/why-summary` return JSON, not an error.
6. **Local app on your PC:** it now runs from the permanent venv `D:\sindhu_venv_stable`; start it supervised with `D:\sindhu_runtime\start_supervised.cmd` (docs/RUNBOOK.md section 11). No Windows security setting was changed. Item 14 below is therefore only needed if you want a freshly built venv.

Do these in order (most important first):
1. **Set your private chat id** (Dashboard -> Settings -> Telegram -> "Personal chat id"). Until then the watchdog alerts, the daily health summary and the reconciliation alert are SILENT (the dashboard shows a yellow "Owner alerts are OFF" bar).
2. **Keep Cloud awake** - section K: sign up for the free 1-minute pinger (cron-job.org). The GitHub keep-alive workflow cannot run from this branch. Decide on a paid plan if you want signals 24/7 (free plan: sleeps after 15 min, 750 shared hours/month).
3. **Rotate secrets** - section N: Neon password, proxy login, Groq key, sync secret/API token; keep them only in Render env vars.
4. **Old Render services** - section L: open each non-Sindhu service and check whether it holds `TELEGRAM_BOT_TOKEN`; suspend the ones you do not use (none showed activity in 30 days, but env vars cannot be read from outside).
5. **Make a red test block a deploy** - section M (Render "Auto-Deploy: After CI Checks Pass").
6. **Decide `auto_send_high_confidence_only`** (Cloud = OFF, your old local file = ON). OFF means signals also go out at the "low tier" (confluence strong but the 25-trade Wilson gate not yet met) - the three signals sent so far were low tier. ON is stricter and will probably mean no signals until patterns reach 25 trades. See docs/PARITY.md.
7. **Opposite signals on the same coin:** on 3 Nov Cloud sent BTC/USDT LONG at 21:33 and SHORT at 21:38 (different strategies/timeframes; the duplicate guard only blocks the same direction). Decide whether subscribers should get both.
8. **Strategy pauses** - docs/PERFORMANCE_RECONCILIATION.md (Step 15): 8 recommended pauses, 8 on watch, 38 with too few trades. Nothing is paused automatically. Backtests of the 10 most-traded strategies (Step 14) are all below PF 1 over 60 days.
9. **Real-world checks only you can do:** look at the Telegram channel for the signal format, send `/menu` once in the group, open the dashboard on your phone, open Windows Firewall for TCP port 8420 if you want `http://192.168.1.111:8420` to work from the phone.
10. **The "+$270.05 over 1,856 trades, 40-43 % win" figure** could not be reproduced: both databases hold the same 1,132 trades (-87.96). Where did it come from?
11. **Balance reset to $100** - DONE 4 Nov on Cloud and Local (archive kept; docs/FIX_LOG.md). Nothing for you to do.
12. **Daily report in the channel:** the existing "Roz Ki Report" scheduler sends one message per UTC day to the Telegram channel (first check after each restart, e.g. 03:13 UTC on 4 Nov). It is not a signal; decide whether you want it public or private.
13. **Go-live:** `docs/GO_LIVE_CRITERIA.md` - 1 of 11 gates met. Paper only; not financial advice.


## K. Keep Cloud awake (no signals while it sleeps)
**Why the GitHub workflow does nothing:** GitHub runs scheduled workflows only from the repo's *default branch* (`main`). The workflow file lives on `codex/trading-intelligence`, and the GitHub API shows 0 workflows and 0 runs for the repo. Pushing it to `main` is NOT done because the old Render service `Sindhu-cloud-` auto-deploys from `main`. (Alternative: GitHub -> Settings -> Branches -> change the default branch to `codex/trading-intelligence`; then the workflow starts working within ~10 minutes. Note GitHub pauses schedules after 60 days without repo activity.)

**A. cron-job.org (recommended, free, 1-minute interval)**
1. Create a free account at cron-job.org -> Create cronjob.
2. URL: `https://sindhu-cloud-1.onrender.com/health` (GET). Schedule: every 1 minute (every 5 minutes is enough). Request timeout 60 s (a cold start takes 30-60 s).
3. Enable "Notify me when the job fails" so you get an email if Cloud is down.
4. Do NOT use 1-second pings: it adds load on the 0.1 CPU instance and gives nothing over 1 minute (Render sleeps after 15 minutes idle).

**B. Cloudflare Worker cron (optional second pinger)**
1. dash.cloudflare.com -> Workers & Pages -> Create Worker, paste:
```js
export default { async scheduled(event, env, ctx) { ctx.waitUntil(fetch("https://sindhu-cloud-1.onrender.com/health", {cf: {cacheTtl: 0}})); } };
```
2. Worker -> Settings -> Triggers -> Cron Triggers -> add `*/5 * * * *`.

**C. Free-hours warning:** Render gives 750 free instance-hours per month for the whole workspace. A service that never sleeps uses ~744 h, so keeping Sindhu-cloud--1 awake 24/7 leaves almost nothing for the other free services (Trading-best x3, alpha-signal-bot, sindhu-agency, ...): Render suspends them all when the hours run out. Suspend the services you do not use (section 2) or move to the paid Starter plan.

**D. Optional in-app self-ping:** set env `SINDHU_KEEPALIVE_URL=https://sindhu-cloud-1.onrender.com` on Render. It only keeps an already-awake instance awake; it cannot wake a sleeping one.

## L. Telegram token-conflict review of the other Render services (read-only, 4 Nov 2026)
Method: Render API (list services, last deploy, logs since 5 Oct). **Environment variable names/values cannot be listed with the connector, so "shares our bot token" is NOT VERIFIED for every row.** Nothing was changed, suspended or deleted.

| Service | Type / start | Last deploy (status, date) | Logs in last 30 days | Could it use our bot? | Risk |
|---|---|---|---|---|---|
| Sindhu-cloud--1 (ours) | web, uvicorn cloud_runtime.app | live, 3 Nov | yes | it IS the publisher | - |
| Sindhu-cloud- (old, tracks `main`) | web, `python cloud_runtime/app.py` | update_failed, 16 Sep (previous deploy may still be serving) | none | same code family and same repo: YES if it still runs and has TELEGRAM_* env | MEDIUM (check once in dashboard; suspend if unused) |
| Trading-best-, -1, -2 | web, `python bot.py` (repo Trading-best-) | update_failed, 13 Jun | none | a `bot.py` is a Telegram-style bot: possible | LOW-MEDIUM |
| alpha-signal-bot | web, gunicorn your_application.wsgi | build_failed, 8 May | none | cannot run (build failed) | LOW |
| Trading-main future | web, repo Trading-main | not checked in detail | none | unknown | LOW |
| sindhu-agency | web, agency_cloud.main | auto-deploy off, 14 Oct | none | separate app | LOW |
| zaiqa-royale-portfolio | static site | n/a | n/a | no | NONE |

Recommendation: in the Render dashboard open each non-Sindhu service -> Environment -> look for `TELEGRAM_BOT_TOKEN` / `BOT_TOKEN`; if the same bot appears, suspend that service (Render allows resume later). Two processes calling `getUpdates` for one bot cause HTTP 409 and lost commands; two senders cause duplicate messages. Also remember the 750 free instance-hours/month are shared by every free service.

## M. CI and branch protection (Step 19)
`.github/workflows/tests.yml` runs the whole test suite on every push and pull request (GitHub -> Actions tab; the `push` trigger works from this branch, unlike the scheduled keep-alive). Check the green/red mark after each push.
Render deploys every push to `codex/trading-intelligence` **without waiting for CI**. To make a red test block a deploy, do ONE of:
1. Render dashboard -> Sindhu-cloud--1 -> Settings -> Build & Deploy -> **Auto-Deploy: "After CI Checks Pass"** (recommended; no GitHub setting needed).
2. GitHub -> Settings -> Branches -> Add rule for `codex/trading-intelligence` -> "Require status checks to pass" -> select `pytest` (then push through pull requests instead of directly).

## N. Secrets and safety scan (Step 25, 4 Nov 2026, report only - nothing changed)
Method: regex scan (Telegram bot tokens, database URLs with passwords, URL credentials, Groq/OpenAI/Google/AWS keys, private keys, key/secret/password assignments) over every git-tracked file, the git history (git log -S / -G) and the local data/config, data/logs and root files. All values masked.

| Where | Finding | Real secret? | Action |
|---|---|---|---|
| Git-tracked files (13 hits) | tests/test_telegram_proxy.py, test_telegram_env_var_fallback_fix.py, test_phase4_coin_event_caution.py, tests/frontend_harness/*.mjs, paper_trading/telegram_bot.py L85, app.js L11479/L11890: 21-27 character placeholders such as http://user:pass@host and fake tokens | NO | none |
| Git history | no gsk_ key, no Neon host (@ep-), no credentialed Postgres URL, no bot-token pattern in any commit | NO | none |
| .gitignore | data/ (config, database, logs), .env, .env.*, *.key, *.pem are ignored; git check-ignore confirms data/config/telegram_settings.json, data/database/sindhu.db and .env | - | none |
| data/config/ai_settings.json (ignored, on this PC) | Groq API key gsk_***(56 chars) and a second key field | YES | rotate; prefer env var GROQ_API_KEY |
| data/config/neon_runtime_connection.json | full Neon connection string with password, post***(43 chars) | YES | rotate the Neon password; keep it only in Render env DATABASE_URL |
| data/config/telegram_settings.json | proxy URL with user:password, http***(41 chars) | YES | rotate the proxy login |
| data/config/api_token.json, strategy_sync_secret.json | API token and sync secret | YES | rotate (regenerated when deleted; the Cloud copy is in Neon cloud_settings) |
| D:\sindhu_backup_* | copies of the config above | YES | keep private, never upload; delete old copies after rotation |
| data/git_publish_tree.json | 21-24 character URL-like strings only | NO | none |
| Logs (server_*.log, data/logs) | no tokens found | NO | none |

Rotation needs the provider dashboards (owner task). After rotating Neon, update DATABASE_URL on Render, then edit or delete neon_runtime_connection.json.

14. **(Resolved by a copy on 4 Nov, see Day 3 item 6) Local app venv blocked by Windows (Smart App Control):** newly installed pandas DLLs are rejected ("Application Control policy has blocked this file"). Turn Smart App Control off or allow Python packages, then recreate the venv (docs/RUNBOOK.md section 11). Until then the local app runs from a temporary-folder venv that may disappear.


## DAY 4 ADDITIONS (4 Nov 2026)
**Top priority (unchanged, now backed by numbers):** 1. Pinger (docs/PINGER_SETUP.md). Without it a complete scan is impossible on the free plan (docs/SCAN_PROFILE.md section 9). 2. Owner chat id (docs/OWNER_ALERTS_SETUP.md): still not set on Cloud (settings read 4 Nov: personal chat id NOT set). 3. Decisions (docs/OWNER_DECISIONS.md, updated with Day 4 evidence).

### Token/service conflict check (Step 15) - read-only, partly NOT VERIFIED
The Render API lists 9 services in your workspace and does not show environment variable values, so token fingerprints could NOT be compared and the bot's webhook state could not be read (the token is not available to me). What can be seen:
| Service | Branch / start command | Auto-deploy | Risk |
|---|---|---|---|
| Sindhu-cloud--1 (the live one) | codex/trading-intelligence, `cloud_runtime.app` | yes | the only one that should hold the bot token |
| **Sindhu-cloud-** | **main**, `python cloud_runtime/app.py`, same GitHub repo | yes, not suspended | **medium**: an older SINDHU build on the same repo. If it still has `TELEGRAM_BOT_TOKEN` and the legacy engine ON, it could send duplicate or old-style signals when it wakes. Its last deploy was 1 Sep. |
| Trading-best, Trading-best-1, Trading-best-2 | main, `python bot.py` | yes | unknown: older bots; if one polls Telegram with the same token you would see 409 Conflict; none showed 409 in the Sindhu-cloud--1 log |
| Trading-main future, alpha-signal-bot, sindhu-agency | main | mixed | unknown / low |
| zaiqa-royale-portfolio | static site | - | none |
Render log search on Sindhu-cloud--1 for "409", "Conflict" and "getUpdates" over 4 Nov found nothing (log service was partly unavailable for the other services: their logs could not be read). **Owner action (5 min):** in the Render dashboard open Sindhu-cloud- and each Trading-best service > Environment: if `TELEGRAM_BOT_TOKEN` exists, either delete that variable there or suspend the service you do not use. I did not suspend anything.

### Owner readiness table (Step 24)
| Item | State on 4 Nov ~17:30 UTC |
|---|---|
| External pinger | not seen in the log |
| Private chat id / owner alerts | not set (Cloud settings read) -> alerts, daily summary and the memory alert stay silent |
| `auto_send_high_confidence_only` | not stored = default OFF (unchanged) |
| Strategy pauses | none applied (8 recommended, see docs/STRATEGY_FORENSICS.md) |
| Opposite-direction policy | none (2 opposite pairs in the 6 sent signals) |
| False alerts after my changes | none possible: no owner chat is configured, so nothing was sent; alert log empty |

### Backup and restore (Step 25) - done on 4 Nov
New backup folder `D:\sindhu_backup_day4\cloud_export_20261104_222811` (51 tables exported, 0 mismatched). Throwaway restore to `D:\sindhu_runtime\restore_test\restored_day4.db`: **49 tables restored OK, 0 mismatched, 2 skipped (login tables, deliberately), 11,909 rows**; e.g. paper_trade_history_archive 1,132 = 1,132, paper_scan_log 95 = 95. Commands: docs/RUNBOOK.md section 13.

### Other owner items from Day 4
- Security: docs/SECURITY_REVIEW.md items 5, 11, 12 (CORS origin, rate limit at Cloudflare, Content-Security-Policy).
- The dashboard CEO page load time (Step 23) was NOT worked on this run.
## DAY 5 ADDITIONS TO THE OWNER LIST (5 Nov 2026)
1. **Local app:** double-click `D:\sindhu_runtime\OPEN_SINDHU.cmd`. To start it at Windows login put a shortcut to it in the folder opened by Win+R `shell:startup` (not done by me: persistent setting). The laptop's WiFi address changes (it was .111, now .113): use http://127.0.0.1:8420 on the laptop.
2. **Keep the data fresh (daily, 1 minute):** run `cd D:\sindhu_clean` then `D:\sindhu_venv_data\Scripts\python.exe -m data_platform.run_download --detach --no-expand` ... (it adds yesterday's closed day for every coin; finished files are skipped). To schedule it daily use Windows Task Scheduler (Create Basic Task, daily, action = that command) - a persistent change, so left to you. Check progress with `type D:\sindhu_data\manifest\progress.json`.
3. **Back up `D:\sindhu_data`:** it is the only copy of the rebuilt dataset (about 1.0 GB). Copy the folder to another drive or cloud storage once a month; it was lost once before. The downloader can rebuild it in about 30 minutes from Binance's public archive if needed.
4. **Cloud memory / gate exchange:** after the next deploy check the Render log line `[memory-guard]`; and decide `SINDHU_GATE_USE_POSITION_EXCHANGE=1` (docs/SCAN_PROFILE.md section 10, D41).
5. **Read docs/BACKTEST_RESULTS.md** when the 42-strategy run finishes; the sealed holdout (Sep-Oct 2026) must be opened only once, for strategies that pass.

## DAY 6 ADDITIONS (5 Nov 2026) - short list
1. **Keep Cloud awake** (external pinger): without it the free instance sleeps, scans stop, and signals are irregular (it restarted three times overnight).
2. **Read docs/WEEKLY_SCORECARD.md and docs/OWNER_DECISIONS.md** (pause recommendation list; nothing was paused).
3. **Decide the prepared switches** (all OFF, set on Render): `SINDHU_RESEARCH_ONLY_TIMEFRAMES=1m,3m,5m` (cuts exchange pages 87 %), `SINDHU_MAX_TARGET_STOP_RATIO=5` and `SINDHU_BLOCK_OPPOSITE_SIGNAL=1` (would have withheld 3 of the first 6 signals), `SINDHU_HIDE_CONFIDENCE=1` (the confidence number carries no information), `SINDHU_GATE_USE_POSITION_EXCHANGE=1` (docs/SIGNAL_QUALITY.md D6-1).
4. **Memory:** Cloud now reads 439-444 MB (hard guard 450 MB). If you see restarts, enabling the research-only flag lowers memory about 46 MB in the local test.
5. **Do not open forward data** before 5 Jan 2027; new strategies go through `python -m data_platform.candidate_eval` with a filled claim (docs/templates/CANDIDATE_CLAIM_TEMPLATE.md).
6. **Backup** `D:\sindhu_data` (not in git) to another drive or cloud storage monthly.
7. Still yours from before: chat id, old Render services that may hold the bot token, secrets rotation, hosting decision, daily candle update schedule.

## DAY 7 OWNER READINESS (5 Nov 2026) - what is ready, what is not
| Item | Status today | Evidence |
|---|---|---|
| Keep-alive pinger for Cloud | **NOT DONE**: the free instance still sleeps; 4 wake-ups and ~6 deploy restarts in 11 hours (4-5 Nov) | Render logs "Started server process" (10 starts) |
| Pinger status endpoint (`/api/ops/pinger`) | NOT VERIFIED - answers 401 "login required"; I do not use your login | HTTP 401 |
| Owner chat id (private alerts) | **NOT configured on Cloud** - "status-ping skipped -- personal_chat_id not configured yet" at 05:37 UTC today; so there is no owner alert routing: stalls, failures and the daily status ping never reach you | Render log |
| Bot token / chat id on this laptop | none (by design the laptop never holds the token) | local settings file: token, chat id and channel id empty |
| Telegram sending on Cloud | ON ("Telegram sending is currently ON (restored from the last saved setting)"); the laptop copy is OFF | Render log; local `master_send_enabled=False` |
| Other Render services (9 in total, all running, none suspended) | Sindhu-cloud--1 is the live one. `Sindhu-cloud-` (old, branch `main`, free) and `Trading-best-`, `-1`, `-2` (`python bot.py`), `alpha-signal-bot`, `sindhu-agency`, `Trading-main future`, `zaiqa-royale-portfolio` have no log lines since 1-3 Nov (they are asleep or idle) | `list_services`, `list_logs` |
| Whether those old services define a Telegram token variable | **NOT VERIFIED**: the Render connector cannot list environment variable names or values; only you can look at the dashboard | connector limit |
**Do these (order, plain steps):**
1. **Pinger:** create a free account at an uptime service (for example UptimeRobot or cron-job.org), add a check of type "HTTP" to `https://sindhu-cloud-1.onrender.com/health` every 5 minutes. Note: the Render free plan has 750 free hours a month for ALL your free services together; keeping Sindhu-cloud--1 awake uses about 744, so first suspend services you do not use (step 3).
2. **Owner chat id:** open Telegram, start a chat with the bot, send `/start`, then open the dashboard's Telegram settings and enter your personal chat id (the dashboard shows how to find it). This is what turns on the private status ping and failure alerts. I did not test it (no test messages are sent by me).
3. **Old services:** on dashboard.render.com open each service listed above except `Sindhu-cloud--1` -> `Environment`. If you see a variable whose name contains `TELEGRAM` or `BOT_TOKEN`, that service can talk as your bot: suspend it (button `Suspend`) if you do not use it. Do not delete anything.
4. **Who is in the Telegram groups (you do this in the Telegram app, nothing is sent):** open the group -> tap the group name at the top -> `Members` (a group) or `Subscribers` (a channel; only admins see the list). The number at the top is the member count; write down the count and any name you do not recognise. Tap `Administrators` to see which bots and people can post. To remove someone: open the member list, swipe left (phone) or right-click (computer) on the name -> `Remove`. Do this before deciding whether public signals should continue (docs/OWNER_DECISIONS.md).
