# Local vs Cloud parity (4 Nov 2026, read-only comparison; Cloud = Neon + code defaults, Local = D:\sindhu data)

Method: `scripts`-style comparison of Neon tables/settings with the local SQLite DB and config files (secrets reported as booleans only; Cloud token/channel come from Render env vars and cannot be read from outside = NOT VERIFIED as values, "READY" banner proves they are set).

| Item | Local | Cloud | Match? | Action |
|---|---|---|---|---|
| Enabled strategies | 62 | 62 | yes | - |
| Enabled and not paused | 42 | 42 | yes | - |
| Groups profitable / losing / challenge | 12 / 46 / 4 | 12 / 46 / 4 | yes | - |
| Closed trades | 1,132 | 1,132 | yes | - |
| Realized PnL (58 books) | -87.96 | -87.96 | yes | balance reset not yet done (Step 26) |
| Open positions | 65 (stale, September) | 14 (live) | NO - expected | local engine is off; those 65 would be managed if the local engine were ever started; archive/close them first |
| Engine | config says enabled, runs in safe mode = NOT running | enabled and running | by design | - |
| coin_filter_mode / coin_filter_top_n | was activity / 50 | liquidity / 10 | FIXED | local config aligned (backup `D:\sindhu_backup_config_*`) |
| channel_group_filter | was all | profitable_challenge | FIXED | local config aligned (local never sends anyway) |
| auto_send_high_confidence_only | TRUE | FALSE | **NO - owner decision** | Cloud sends "low tier" signals (confluence ok, 25-trade Wilson gate NOT yet met); local config (owner's earlier choice) only allows tier "high". NOT changed: turning it ON is stricter and would likely mean zero signals for now. See OWNER_TODO. |
| master_send_enabled | false | true | by design | Cloud is the single publisher |
| bot token / channel id | not set | set via Render env (banner READY) | by design | - |
| signal_freshness_minutes / drift / confluence / rate limit | 15 / 0.5 / 3 / 10 per hour | same | yes | - |
| SINDHU_PUBLIC_SIGNAL_OWNER | disabled | unset = cloud | by design | prevents double sends |
| personal_chat_id (owner alerts) | not set | not set | yes | **owner alerts and daily summary are silent until set** |
| Candles | DB (10 coins fresh to 3 Nov, 40 coins stale to 11 Sep) | live from OKX (not stored) | by design | - |
