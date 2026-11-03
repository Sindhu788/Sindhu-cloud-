# OWNER / MANAGER TODO (only what truly needs a person) - updated 2026-11-04

Live state: Cloud (Render Sindhu-cloud--1) runs the legacy engine with Telegram delivery READY (log: `Public signal delivery: READY`, which also proves bot token + channel id + master/auto send are set). Local is safe-mode only. Rollback: redeploy tag `pre-recovery-backup` (c223070) or `git revert -m 1 <merge commit>`.

1. **Rotate secrets** (only you can): proxy user/password, Neon database password, strategy-sync secret, Telegram bot token if it was ever shared. Keep them in Render env vars, not in `data/config/*.json`.
2. **Old Render services**: `Trading-best`, `Trading-best--1`, `Trading-best--2` (all `python bot.py`), `alpha-signal-bot`, `Trading-main future`, `sindhu-agency`, old `Sindhu-cloud-` (tracks main). If any uses the same Telegram bot token you get 409 conflicts / duplicate messages, and the free instance-hours (750/month) are shared by all free services. Suspend the ones you do not use.
3. **Keep Cloud awake** - see section K below (the GitHub workflow can NOT work from this branch; use cron-job.org).
4. **Check the first real signal** in the Telegram channel and send `/menu` once in the group; check the dashboard on a real phone. (I never send to the public channel.)
5. **Decide on pauses**: see `docs/SCORECARD_2026-11-03.md` and `docs/PERFORMANCE_RECONCILIATION.md` (Wilson-aware list; nothing is paused automatically).
6. **Settings page**: manually try a negative / empty number in Settings (my browser test could not exercise numeric validation).
7. **Where did "+$270.05 over 1,856 trades" come from?** Local and Neon both contain the same 1,132 trades (-87.96); the figure could not be reproduced.
8. **Balance reset to 100 on Cloud** (tool ready, archive-not-delete, `scripts/reset_paper_balance_to_target.py --allow-cloud --apply`): run only after you see signals flowing; take a Neon backup first.
9. **Stale-candle problem on Cloud** - status in `docs/DECISIONS.md` (D6/D7): if the log still shows `candle frame rejected (...)` lines after the latest deploy, send me/the manager those lines (they now name exchange:symbol, last candle and age).


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
