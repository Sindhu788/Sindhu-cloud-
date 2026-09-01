# Deploying the SINDHU lightweight cloud runner to Render

Same app as RAILWAY_DEPLOY.md describes (`cloud_runtime/app.py` --
Paper Trading + Telegram + a login-gated dashboard, nothing heavier);
this file only covers what's different about Render specifically. Read
RAILWAY_DEPLOY.md first for the "what gets deployed" / environment
variable table / security notes -- all of that applies here unchanged.

## If you already created a Web Service manually (not a Blueprint)

This is almost certainly why the first deploy failed with
`ModuleNotFoundError: No module named 'data_engine'`: Render ran the
start command with the bare `uvicorn` executable, which does not add the
project folder to Python's import path. Fix it directly in the dashboard:

1. Open your service on [dashboard.render.com](https://dashboard.render.com) -> **Settings**.
2. **Build Command** -> set to:
   ```
   pip install -r requirements-cloud.txt
   ```
   (If it currently says `pip install -r requirements.txt`, that's the full local requirements file -- it includes a desktop GUI toolkit that isn't needed here and may itself fail to install on Render's Linux containers.)
3. **Start Command** -> set to:
   ```
   python -m uvicorn cloud_runtime.app:app --host 0.0.0.0 --port $PORT
   ```
   (`python -m uvicorn`, not bare `uvicorn` -- that's the actual fix for the crash.)
4. **Health Check Path** -> set to `/health` (see below).
5. Save, then **Manual Deploy** -> **Deploy latest commit** to pick up both this fix and the pushed code.
6. Add the environment variables from RAILWAY_DEPLOY.md's table under this service's **Environment** tab (same variables, same values -- `SINDHU_CLOUD_MODE`, `SINDHU_LIVE_CANDLES`, `DATABASE_URL`, `GROQ_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`).

## If you create the service fresh as a Blueprint instead

`render.yaml` at the repo root already has the correct build/start
commands baked in. On Render: **New +** -> **Blueprint** -> pick this
repo -> Render reads `render.yaml` automatically. It will still pause
and ask you to fill in the 4 secret values (`DATABASE_URL`,
`GROQ_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`) since those
are marked `sync: false` on purpose -- never committed to the repo.

## Postgres on Render

Render has its own managed Postgres, separate from Railway's -- **New +**
-> **PostgreSQL**, free tier available. Once created, copy its **External
Database URL** (labeled that way on the database's own page) into this
service's `DATABASE_URL` variable.

## Keeping the free tier awake -- the `/health` endpoint

Render's free web services sleep after ~15 minutes with no traffic, and
the next request pays a slow cold-start. `/health` (added to
`cloud_runtime/app.py`) is built exactly for pinging that awake: no
login required, no database read, no exchange call -- it returns
`{"status": "ok"}` and nothing else, so it costs almost nothing to hit
repeatedly.

To use it with [cron-job.org](https://cron-job.org) (free): create an
account, add a new cron job, set the URL to
`https://YOUR-SERVICE-NAME.onrender.com/health`, and set the interval to
every 10 minutes (comfortably under the 15-minute sleep window). Nothing
else to configure -- a plain GET with a 200 response is all it checks for.
