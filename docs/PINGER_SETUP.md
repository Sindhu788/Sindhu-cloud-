# Keep SINDHU Cloud awake: external pinger setup (about 5 minutes)

**Why:** the free Render plan stops the service after ~15 minutes without a visitor and starts a fresh process on the next request. Every restart empties the candle cache, so the first scan is slow, and while the service sleeps NO scans and NO signals happen. A free external service that opens `/health` every minute prevents this. (The GitHub keep-alive workflow in this repo does NOT work - GitHub only runs scheduled jobs from the default branch `main`.)

**The URL to ping (exactly this, no `#`, no extra path, no password, no token):**
`https://sindhu-cloud-1.onrender.com/health`

## A. cron-job.org (main choice, free, 1-minute interval)
1. Go to https://cron-job.org and click **Sign up** (email + password, confirm the email).
2. After login click **CREATE CRONJOB**.
3. **Title:** `SINDHU keep-alive`. **URL:** `https://sindhu-cloud-1.onrender.com/health`
4. **Execution schedule:** choose **Every 1 minutes** (the "user-defined" option with all minutes ticked, or the "every minute" preset).
5. Open **ADVANCED**: request method **GET**, **Request timeout 30 seconds**, tick **Treat redirects as success** off (not needed), leave headers empty, do NOT add any password or token anywhere.
6. Under notifications you can tick "notify me when the execution fails" (optional).
7. Click **CREATE**, then **TEST RUN**. Expected: status **200 OK** (the first call after a sleep can take up to ~40 s: that is normal, the test window waits for it).
8. After 10 minutes open the job's **History**: you should see a row every minute, all 200. A few slow rows (2-4 s) are normal on the free plan.

## B. UptimeRobot (backup, free, 5-minute interval)
1. https://uptimerobot.com -> **Register** -> verify email.
2. **+ Add New Monitor**: type **HTTP(s)**, name `SINDHU`, URL `https://sindhu-cloud-1.onrender.com/health`, interval **5 minutes** (the free minimum), save.
5 minutes is shorter than the 15-minute sleep timer, so it is enough on its own; the 1-minute job gives faster wake-up and recovery.

## Do NOT
- Do not ping every second (or faster than once a minute): it wastes the 750 free instance-hours and can get the pinger banned.
- Do not put secrets in the URL (no `?token=`, no passwords). `/health` needs none.
- Do not ping other paths such as `/` or `/api/...`: they need a login, run database queries and can be slow.

## Prove that the pinger works (Step 4 indicator)
Log in to the dashboard and open `https://sindhu-cloud-1.onrender.com/api/ops/pinger` (or look for the warning on the dashboard). Good output:
`"pinger_active": true`, `"seconds_since_last_external_ping"` under ~120, `"average_gap_seconds"` about 60 (cron-job.org) or ~300 (UptimeRobot).
If it says `"pinger_active": false` after the process has run 15 minutes, the dashboard shows the warning "No external pinger seen on /health" (code `no_pinger`). The counters live in memory, so they start from zero after each restart; wait ~5 minutes after a restart before judging. Render's own health probe is shown separately (`seconds_since_last_render_probe`) and does NOT keep the service awake.

## What `/health` costs (measured 4 Nov 2026 from this PC, awake instance)
- Does no database query and no exchange call (test `tests/test_health_light.py`, p95 < 200 ms in-process).
- 30 requests over the internet: median ~0.7 s, most answers in 0.6-1 s, 29 of 30 within 4 s (numbers in docs/DAY3_BASELINE.md); **1 of 30 timed out at 60 s** (cause NOT VERIFIED - could be the shared 0.1 CPU while a scan was running, or the network). Use a 30 s request timeout in the pinger so one slow reply is not treated as an outage.
- The response contains only status, version, commit, engine flag, mode flags and start time - no secrets.

## If the pinger shows failures
1. Open the URL in a browser: 200 and JSON = service is fine, the pinger had a hiccup.
2. Timeouts for many minutes = Render is deploying/restarting or down: see docs/RUNBOOK.md sections 3 and 7.
