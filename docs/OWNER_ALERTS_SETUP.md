# Owner alerts: get your private chat id and switch the alerts on (about 5 minutes)

**What you get:** private Telegram messages (only to YOU, never to the public channel) when something is wrong with SINDHU Cloud, one "recovered" message when it is fixed, and a short daily health summary at about 23:00 Pakistan time. Until the chat id is set, all of these stay silent (the dashboard shows the warning "Owner alerts are OFF").

## Step 1 - open a chat with the bot
1. Open Telegram on your phone, search for your SINDHU bot (the same bot that posts the signals) and tap **Start** (or send it any message such as `hi`). A bot cannot write to you before you do this.

## Step 2 - find your chat id (pick ONE way)
**Way A (easiest, no token needed):** in Telegram search for the bot `@userinfobot` (or `@RawDataBot`), tap Start. It replies with your numeric **Id** (for example `123456789`). That number is your chat id.

**Way B (uses your own bot, careful with the token):** open `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates` in a browser (replace the placeholder with the real token, which only you have). Find `"chat":{"id":123456789,...}`. Never share that page, and do not paste the token anywhere else (the token is a secret: docs/SECRETS_ROTATION.md).

The id is only digits, 5 to 16 of them, and may start with `-` for group chats (a private chat id is a plain positive number). It is NOT the bot token (that has a colon) and NOT a `@username`.

## Step 3 - enter it in the dashboard
1. Log in to https://sindhu-cloud-1.onrender.com (the first load after a sleep takes up to 40 s).
2. Open **Settings > Telegram** and scroll to **Private Alerts & Reports**.
3. Paste the number into **Your Personal Telegram Chat ID**. The page checks the format (digits only) and refuses anything else.
4. Click **Save** (it says "Saved.").
5. Click **Send test alert to my chat**. You must click it yourself. One test message arrives in your private chat within a few seconds ("SINDHU test alert ..."). The button allows one test every 5 minutes. If it fails the page shows why (for example "personal_chat_id is not configured" or Telegram refused: you forgot Step 1).

## What each alert means
| Message starts with | Meaning | What to do |
|---|---|---|
| `ALERT: Live market data has been stale/empty ... checks in a row` | Candles older than the allowed window; signals are blocked on purpose | Usually the exchange or network. Check Render logs for `exchange-failover` (docs/RUNBOOK.md section 2) |
| `ALERT: The engine is running but showed no scan progress for N min` | The scanner is alive but nothing moved for 20 min. It also says if an external pinger was seen | If it says "no external pinger seen": set up docs/PINGER_SETUP.md. Otherwise look at Render logs |
| `ALERT: Paper trading engine is enabled but NOT running` | Engine crashed or was not restarted | Dashboard > Paper Trading > Start; RUNBOOK section 1 |
| `ALERT: N Telegram sends failed in the last 30 min` | Signals could not be delivered (token, channel, proxy) | RUNBOOK section 5 |
| `ALERT: The last 3 scans all ended with errors` | Coins failing every scan | Render logs: `market state error` |
| `ALERT: The database is unreachable` | Neon down or password changed | RUNBOOK section 4 |
| `ALERT: The Cloud server restarted` | Deploy, crash or wake from sleep (sent at most every 6 h) | Normal on the free plan without a pinger |
| `ALERT: Reconciliation MISMATCH` | Stored balances do not equal the trades (once per day check) | Do not trade real money; send me the message |
| `RECOVERED: ...` | The problem above is gone | Nothing |
| `Daily health (24 h): scans ..., trades opened ..., signals sent ...` | The daily summary | Read it; look at "scan errors" and "Server restarts" |
Alerts are rate limited (the same alert at most once an hour). During the first 10 minutes after a restart the "stale data" and "no scan progress" alerts are held back on purpose (the free instance was asleep and is warming up). Nothing is ever sent to a public channel.
