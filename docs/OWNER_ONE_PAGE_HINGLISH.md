# SINDHU: Claude ke bina kaise chalao (ek page)

**Yaad rakho:** yeh sirf PAPER TRADING hai. Koi real paisa nahi lagta, koi real order nahi jata.

## Roz 2 minute
1. Phone par kholo: https://sindhu-cloud-1.onrender.com/health. `"status":"ok"` aur `"engine_running":true` dikhe to theek hai.
2. Detail chahiye: https://sindhu-cloud-1.onrender.com/health/details.
   - `trading` = `enabled` hona chahiye.
   - `self_check.ok` = `true`.
   - `candles.stale` = 0 ya chhota number.
3. Dashboard (login) → **Home** = MAIN_WALLET: balance, aaj ka P&L, open trades, system health.
4. UptimeRobot app/website: monitor **Up** (green) ho.

## Hafte mein ek baar (Monday)
- Dashboard → Home → "Last 5 wallet events" padho.
- Laptop par `D:\sindhu_backups\BACKUP_LOG.md` kholo: is hafte ki line mein `restore exit 0` ho.
- Agar tasks install kiye hain: `D:\sindhu_runtime\tasks\logs\` mein koi "error" to nahi.

## Alert ka matlab
| Alert / dikhe | Matlab | Kya karo |
|---|---|---|
| Banner: **KILL SWITCH ON** | Naye trade band (purane trade apne stop/target ke saath chalte rahenge) | Theek lage to banner mein **Resume** → confirm |
| Home: "Daily loss limit hit" | Wallet aaj 5% se zyada neeche gaya, aaj naya trade nahi | Kuch nahi; agle UTC din khud reset |
| "Data purana" (laal dot) | Exchange se taaza candle nahi aayi | 15 min ruko; zyada der rahe to Render logs dekho |
| `trading: disabled_config_error` | Koi setting galat save hui, naye trade band | Dashboard → Settings mein galat value theek karo |
| "strategy auto-paused for the wallet" | Strategy 20+ trade ke baad lagatar haar rahi thi | Kuch nahi zaroori; research book chalta rahega |

## Cloud band / so raha ho
1. `/health` 1 minute tak jawab na de → free plan so gaya. 1–2 minute mein jaag jata hai (UptimeRobot har 5 min jagata hai).
2. 10 minute tak bhi nahi → https://dashboard.render.com → Sindhu-cloud--1 → **Logs** → laal "Error" lines dekho.
3. Deploy ke baad kharab hua → `docs/ROLLBACK.md` (Render → Events → pichla Live deploy → Rollback).

## Laptop wala app (local)
- Chalao: `D:\sindhu_runtime\start_local.cmd` (double-click). Band: `D:\sindhu_runtime\stop_local.cmd`.
- Browser: http://127.0.0.1:8420.
- Laptop on hote hi khud chale: `ops\windows_tasks\install_tasks.cmd` ek baar chalao (task "Local app at logon").
- Sleep: Settings → System → Power → "When plugged in, put my device to sleep after" = **Never** (jab SINDHU chalana ho).
  Lid band karne par bhi chale: Control Panel → Power Options → "Choose what closing the lid does" → plugged in = **Do nothing**.

## Login nahi ho raha
- Username `owner` + Render par set `DASHBOARD_PASSWORD` se login karo (Render -> Environment se set/badlo, phir 2-3 min ruko).
- Purana account bhool gaye: `python -m tools.reset_dashboard_user --list` (username), `--reset <naam>` (naya password). Cloud ke
  liye `.env` mein `DATABASE_URL` daal kar `--cloud` lagao. Poori steps: docs/OWNER_TODO.md "Login bhool gaye?".

## Kill switch (emergency)
Dashboard ke upar banner mein laal **Kill switch** button → "Stop new entries" → confirm. Wapas: **Resume** → confirm.
Telegram se bhi (sirf tumhari private chat se, agar `OWNER_CHAT_ID` set hai): `/pause` aur `/resume`.

## Kabhi mat karo
- Real exchange ki trading API key kahin mat daalo.
- `SINDHU_PUBLIC_SIGNALS` tab tak mat lagao jab tak koi strategy ROBUST na ho aur forward test pass na kare.
- Tokens ya password kisi chat ya screenshot mein mat bhejo.
