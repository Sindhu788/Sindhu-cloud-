# OWNER / MANAGER TODO (only what truly needs a person) - updated 2026-11-04

Live state: Cloud (Render Sindhu-cloud--1) runs the legacy engine with Telegram delivery READY (log: `Public signal delivery: READY`, which also proves bot token + channel id + master/auto send are set). Local is safe-mode only. Rollback: redeploy tag `pre-recovery-backup` (c223070) or `git revert -m 1 <merge commit>`.

1. **Rotate secrets** (only you can): proxy user/password, Neon database password, strategy-sync secret, Telegram bot token if it was ever shared. Keep them in Render env vars, not in `data/config/*.json`.
2. **Old Render services**: `Trading-best`, `Trading-best--1`, `Trading-best--2` (all `python bot.py`), `alpha-signal-bot`, `Trading-main future`, `sindhu-agency`, old `Sindhu-cloud-` (tracks main). If any uses the same Telegram bot token you get 409 conflicts / duplicate messages, and the free instance-hours (750/month) are shared by all free services. Suspend the ones you do not use.
3. **Keep Cloud awake**: the free plan sleeps after ~15 min. The workflow `.github/workflows/keepalive.yml` is in the repo - open GitHub -> Actions -> enable workflows for the repo (and keep the cron). Or use a paid plan. While asleep there are no scans and no signals.
4. **Check the first real signal** in the Telegram channel and send `/menu` once in the group; check the dashboard on a real phone. (I never send to the public channel.)
5. **Decide on pauses**: see `docs/SCORECARD_2026-11-03.md` and `docs/PERFORMANCE_RECONCILIATION.md` (Wilson-aware list; nothing is paused automatically).
6. **Settings page**: manually try a negative / empty number in Settings (my browser test could not exercise numeric validation).
7. **Where did "+$270.05 over 1,856 trades" come from?** Local and Neon both contain the same 1,132 trades (-87.96); the figure could not be reproduced.
8. **Balance reset to 100 on Cloud** (tool ready, archive-not-delete, `scripts/reset_paper_balance_to_target.py --allow-cloud --apply`): run only after you see signals flowing; take a Neon backup first.
9. **Stale-candle problem on Cloud** - status in `docs/DECISIONS.md` (D6/D7): if the log still shows `candle frame rejected (...)` lines after the latest deploy, send me/the manager those lines (they now name exchange:symbol, last candle and age).
