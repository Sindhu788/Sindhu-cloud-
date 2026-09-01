# Deploying the SINDHU lightweight cloud runner to Railway

This deploys `cloud_runtime/app.py` -- Paper Trading + Telegram signals +
a login-gated dashboard, running 24/7. It does NOT deploy the backtest
engine, the optimizer, the Evolution Engine, or the 45.7 GB local
database -- those stay on the laptop only. See `DEPLOYMENT_CHECKPOINT.md`
for the full technical record of how this was built and verified.

## What gets deployed

- `Procfile` tells Railway to run `uvicorn cloud_runtime.app:app --host 0.0.0.0 --port $PORT`.
- `nixpacks.toml` tells Railway to install only `requirements-cloud.txt`
  (not the full local `requirements.txt`, which includes a desktop GUI
  toolkit and other packages the cloud runner never uses).
- `strategies/library/` (the strategy JSON files) ships as part of the
  code -- these are files, not database rows, so they just need to be in
  the git repo.
- A Postgres database (Railway provides one) holds only the 17 tables
  the paper trading + Telegram code path actually uses (positions,
  account state, strategy config/overrides, decision log, Telegram
  message log, and a few small support tables) -- never the historical
  candle data or backtest results.

## Environment variables

Set these in Railway's dashboard under the service's **Variables** tab.
None of them are ever written into the code or committed to git.

| Variable | Required | Value |
|---|---|---|
| `SINDHU_CLOUD_MODE` | Yes | `1` -- without this, the app refuses every visitor (the LAN-only check meant for the local laptop). The login page becomes the only gate once this is set. |
| `SINDHU_LIVE_CANDLES` | Yes | `1` -- fetches candles directly from the exchange instead of needing the local historical database. |
| `DATABASE_URL` | Yes | Don't type this by hand -- see "Adding Postgres" below; Railway fills it in automatically once you link the Postgres service to this one. |
| `GROQ_API_KEY` | Recommended | The value already sitting in `data/config/ai_settings.json` on this laptop, under `providers.groq.api_key`. Open that file, copy the value, paste it here. Powers AI Trade Review on the cloud instance the same way it already works locally. |
| `TELEGRAM_BOT_TOKEN` | Recommended | The bot token from @BotFather. Can also be entered later from the dashboard's Telegram settings screen instead -- but see the note below about why an env var is more reliable here. |
| `TELEGRAM_CHANNEL_ID` | Recommended | The channel/chat id the bot posts to. Same note as above. |

**Why `TELEGRAM_BOT_TOKEN` as an env var, not just the dashboard form:**
Railway's filesystem resets on every redeploy unless a Volume is attached
(see below). Anything typed into the dashboard's settings forms is lost
on the next redeploy unless a Volume is attached. Setting it as an
environment variable means the bot token survives redeploys with zero
extra setup. Once a Volume is attached, either method works and stays
saved.

**Optional but recommended -- a Volume for persistent storage.** Without
one, `data/config/*.json` (settings saved from the dashboard) and the
local fallback SQLite file are wiped on every redeploy; with `DATABASE_URL`
set, actual trading data always lives safely in Postgres regardless, so a
Volume mainly protects settings changes made from the dashboard. In
Railway: **Service -> Settings -> Volumes -> New Volume**, mount path
`/app/data`.

## Step-by-step: what to do on Railway's website

You've already got a Railway account, so start from step 1 below. The
code is already committed locally (git repository confirmed to exist,
everything the cloud runner needs is in this commit) -- creating the
GitHub repo and pushing is the one part that needs your own login.

1. **Push the already-committed code to GitHub** (from this laptop, in a terminal, from the `E:\sindhu` folder):
   - Go to [github.com/new](https://github.com/new), create a new repository (leave it empty -- do NOT check "Add a README"), and copy the repository URL it gives you.
   - Then, back in the terminal:
   ```
   git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPO-NAME.git
   git branch -M main
   git push -u origin main
   ```
   (If `git remote add origin` says one already exists, run `git remote set-url origin https://github.com/YOUR-USERNAME/YOUR-REPO-NAME.git` instead.)

2. **Go to [railway.app](https://railway.app) and log in.**

3. Click **New Project** -> **Deploy from GitHub repo** -> pick the repository you just pushed.
   Railway will start a build automatically -- let it fail for now (it needs the database and variables first, both added next).

4. **Add the database.** In the same project, click **+ New** -> **Database** -> **Add PostgreSQL**. Railway creates it and automatically makes `DATABASE_URL` available to link.

5. **Link the database to your app.** Click on your app service (not the database) -> **Variables** tab -> **+ New Variable** -> choose **Add Reference** -> select the Postgres service's `DATABASE_URL`. This is what makes `DATABASE_URL` appear in your app's environment automatically -- you never type the connection string by hand for this part.

6. **Add the rest of the variables.** Still on the app service's **Variables** tab, add each one from the table above one at a time (**+ New Variable**, type the name, paste the value, Add):
   - `SINDHU_CLOUD_MODE` = `1`
   - `SINDHU_LIVE_CANDLES` = `1`
   - `GROQ_API_KEY` = (copied from your local `ai_settings.json`)
   - `TELEGRAM_BOT_TOKEN` = (from BotFather)
   - `TELEGRAM_CHANNEL_ID` = (your channel/chat id)

7. Railway redeploys automatically every time you add/change a variable. Watch the **Deployments** tab; when it says the deploy succeeded, click **Settings** -> **Networking** -> **Generate Domain** to get a public URL.

8. **Open that URL.** You should see the SINDHU login screen (no trading words visible, exactly like the local one). Set your username and password there -- this is a brand-new account, separate from your local laptop's login.

9. **(Optional, recommended) Bring your real trading history over.** From this laptop, in a terminal:
   ```
   DATABASE_URL="<paste the Postgres PUBLIC connection string here>" python scripts/migrate_to_postgres.py
   ```
   Get that connection string from Railway: click the **Postgres** service -> **Connect** tab -> copy the connection string labeled for external/public connections (not the internal one, which only works from inside Railway). This copies your real strategy settings, open positions, and trading history into the cloud database -- safe to run more than once, it never duplicates or deletes anything.

10. **(Optional) Add a Volume** so dashboard-saved settings survive redeploys (see above): **Settings** -> **Volumes** -> **New Volume** -> mount path `/app/data`.

That's the whole setup. After this, the cloud instance runs Paper Trading and Telegram 24/7 on its own, independent of whether the laptop is on.

## Verifying it worked

- Visiting the Railway URL with no session shows the login page, not the dashboard.
- After logging in, the sidebar shows only "Paper Trading" and "Telegram Signals" -- that's expected; the heavier local-only pages are not part of this deployment.
- `/api/paper-trading/status` (visible from inside the dashboard) shows the engine's real state.
