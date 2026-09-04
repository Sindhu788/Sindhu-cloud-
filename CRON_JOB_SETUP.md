# Cron-Job.org Setup — Keep SINDHU Awake on Render's Free Tier

Render's free tier puts a web service to sleep after ~15 minutes with no
traffic, and the next real visit then waits ~30-60 seconds for it to wake
back up. Pinging the app every few minutes from an outside service stops it
from ever going to sleep in the first place.

This is a one-time setup on a website (cron-job.org), not something that
needs any code change — SINDHU's `/health` endpoint already exists
specifically for this purpose (confirmed working, requires no login,
touches no database).

## Step 1 — Find your SINDHU cloud URL

It looks like: `https://<your-service-name>.onrender.com`

You can find this on your Render dashboard, under your web service's name.

## Step 2 — Confirm your health check URL

Add `/health` to the end of your URL:

```
https://<your-service-name>.onrender.com/health
```

Open this in any browser. You should see a small block of text like:

```json
{"status": "ok", "cloud_mode": true, "live_candles_only": true, "db_backend": "postgres"}
```

If `db_backend` says `"local_file (ephemeral on most hosts)"` instead of
`"postgres"`, that's a separate issue (your database isn't connected) —
worth checking, but it won't stop the steps below from working.

## Step 3 — Create a free cron-job.org account

1. Go to **https://cron-job.org**
2. Click **Sign up** (top right)
3. Enter your email and a password, confirm your email if asked
4. Log in

## Step 4 — Create the cronjob

1. Once logged in, click **Create cronjob** (usually a button on the
   dashboard)
2. Fill in:
   - **Title**: `SINDHU Keep-Alive` (or anything you'll recognize)
   - **URL**: your health check URL from Step 2
     (`https://<your-service-name>.onrender.com/health`)
   - **Execution schedule**: choose **Every 10 minutes**
     (cron-job.org may show this as "Every X minutes" with a dropdown —
     pick 10)
3. Leave everything else at its default
4. Click **Create** / **Save**

## Step 5 — Confirm it's working

1. On cron-job.org's dashboard, click into the cronjob you just created
2. After it has run once (wait up to 10 minutes, or use the **Run now** /
   **Test run** button if the site offers one), you should see a green
   "success" status and a response time
3. Click on that execution to see the raw response — it should match the
   same JSON from Step 2

That's it. As long as this cronjob keeps running every 10 minutes, Render
should never put SINDHU to sleep, and the dashboard should always load
without that ~30-60 second cold-start wait.

## Notes

- This pings `/health` only — it never touches your trading data, never
  logs in, and never affects Paper Trading, Telegram, or any strategy.
- If you ever change your Render service's URL (e.g. renamed the service),
  come back to cron-job.org and update the URL on this cronjob.
- cron-job.org's free tier is enough for this — no paid plan needed.
