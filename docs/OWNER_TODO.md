# OWNER / MANAGER TODO (only what truly needs a person) - updated 4 Nov 2026

**Live state:** Cloud (Render `Sindhu-cloud--1`) runs the legacy engine on 10 liquid coins (OKX feed), Telegram delivery READY, and has already sent live signals (first: 3 Nov 21:33 UTC). Local is safe-mode only and can never send. Rollback: docs/RUNBOOK.md section 7.

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
11. **Balance reset to $100** - see the Step 26 note in docs/FIX_LOG.md (done or skipped, with the reason).
12. **Go-live:** `docs/GO_LIVE_CRITERIA.md` - 1 of 11 gates met. Paper only; not financial advice.


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
