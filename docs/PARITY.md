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

---
# Day 3 re-check (2026-11-04 09:53 UTC, scripts/parity_check.py, read-only)

| Item | Local | Cloud | Match | Note |
|---|---|---|---|---|
| Enabled strategies | 62 | 62 | yes |  |
| Enabled and not paused | 42 | 42 | yes |  |
| Groups (key:count) | {'challenge': 4, 'losing': 46, 'profitable': 12} | {'challenge': 4, 'losing': 46, 'profitable': 12} | yes |  |
| Closed trades / total P&L (history kept) | (1132, -87.96) | (1140, -93.33) | by design | by design: Cloud keeps trading after the 3 Nov copy, Local is frozen; difference = trades closed on Cloud since |
| Books / realized P&L since reset / closed counter / wins counter | (58, 0.0, 1132, 409) | (58, -5.37, 1140.0, 409.0) | by design | by design: counters (closed, wins) stay across the $100 reset; Cloud has new trades since, Local is frozen |
| Archive of trades before the $100 reset | 1132 | 1132 | yes | archive intact = no data deleted |
| Open positions | 65 | 21 | by design | by design: local engine is off, Cloud trades live |
| paper setting initial_balance | 100.0 | 100.0 | yes |  |
| paper setting coin_filter_mode | liquidity | liquidity | yes |  |
| paper setting coin_filter_top_n | 10 | 10 | yes |  |
| paper setting engine_enabled | True | True | yes | by design: local engine runs in safe mode |
| paper setting dry_run | False | False | yes |  |
| paper setting risk_pct | (default) | (default) | yes |  |
| paper setting lookback_days | 20 | 20 | yes |  |
| paper setting tick_interval_seconds | 30 | 30 | yes |  |
| telegram channel_group_filter | profitable_challenge | profitable_challenge | yes |  |
| telegram auto_send_enabled | True | True | yes |  |
| telegram auto_send_high_confidence_only | True | False | NO | owner decision pending |
| telegram signal_freshness_minutes | 15 | 15 | yes |  |
| telegram signal_price_drift_pct | 0.5 | 0.5 | yes |  |
| telegram auto_send_min_confluence_ratio | 1.0 | 1.0 | yes |  |
| telegram rate_limit_per_hour | 10 | 10 | yes |  |
| telegram silent_hours_enabled | False | False | yes |  |
| telegram master_send_enabled | False | True | by design | by design: Cloud is the single publisher |
| telegram bot_token set? | False | False | yes | by design: Local must NOT have a token (Cloud's comes from the Render env var, not visible here) |
| telegram channel_id set? | False | False | yes | by design: Local must NOT have a channel (Cloud's comes from the Render env var) |
| telegram personal_chat_id set? | False | False | yes |  |
| telegram proxy_url set? | True | False | by design | by design: Local uses a proxy for Telegram tests; Cloud needs none |

Reconciliation (stored P&L vs closed trades, tolerance 0.01):
- Local: Reconciliation OK: 58 books, stored PnL 0.0 == trades PnL 0.0.
- Cloud: Reconciliation OK: 58 books, stored PnL -5.37 == trades PnL -5.37.
- Cloud books: 58, realized since reset min -2.21 / max 0.00; initial balance setting 100.0
- Local books: 58, realized since reset min 0.00 / max 0.00; initial balance setting 100.0

Reading: every difference is by design except `auto_send_high_confidence_only` (Local TRUE, Cloud FALSE = default), which is the owner decision in docs/OWNER_DECISIONS.md section 1. Balances: all 58 books restarted at $100 on 4 Nov (initial_balance 100); Cloud books are between -2.21 and 0.00 realized since then. The archive of 1,132 pre-reset trades is intact on both. Reconciliation is clean on both databases.


# Day 7 re-check (2026-11-05, scripts/parity_check.py, read-only)
Only one setting differs and it is not "by design": **`auto_send_high_confidence_only` is True on Local and False on Cloud**, which is why standard-tier ("tier=low") signals reached the public groups (docs/SIGNAL_QUALITY.md D7-1). Owner decision, not touched. Cloud now holds 1,166 closed trades (34 since the 3 Nov reset, net -11.26) and 61 open positions; the 1,132-trade archive is intact on both sides. Reconciliation is clean on both databases.

| Item | Local | Cloud | Match | Note |
|---|---|---|---|---|
| Enabled strategies | 62 | 62 | yes |  |
| Enabled and not paused | 42 | 42 | yes |  |
| Groups (key:count) | {'challenge': 4, 'losing': 46, 'profitable': 12} | {'challenge': 4, 'losing': 46, 'profitable': 12} | yes |  |
| Closed trades / total P&L (history kept) | (1132, -87.96) | (1166, -99.22) | by design | by design: Cloud keeps trading after the 3 Nov copy, Local is frozen; difference = trades closed on Cloud since |
| Books / realized P&L since reset / closed counter / wins counter | (58, 0.0, 1132, 409) | (58, -11.26, 1166.0, 416.0) | by design | by design: counters (closed, wins) stay across the $100 reset; Cloud has new trades since, Local is frozen |
| Archive of trades before the $100 reset | 1132 | 1132 | yes | archive intact = no data deleted |
| Open positions | 65 | 61 | by design | by design: local engine is off, Cloud trades live |
| paper setting initial_balance | 100.0 | 100.0 | yes |  |
| paper setting coin_filter_mode | liquidity | liquidity | yes |  |
| paper setting coin_filter_top_n | 10 | 10 | yes |  |
| paper setting engine_enabled | True | True | yes | by design: local engine runs in safe mode |
| paper setting dry_run | False | False | yes |  |
| paper setting risk_pct | (default) | (default) | yes |  |
| paper setting lookback_days | 20 | 20 | yes |  |
| paper setting tick_interval_seconds | 30 | 30 | yes |  |
| telegram channel_group_filter | profitable_challenge | profitable_challenge | yes |  |
| telegram auto_send_enabled | True | True | yes |  |
| telegram auto_send_high_confidence_only | True | False | NO | owner decision pending |
| telegram signal_freshness_minutes | 15 | 15 | yes |  |
| telegram signal_price_drift_pct | 0.5 | 0.5 | yes |  |
| telegram auto_send_min_confluence_ratio | 1.0 | 1.0 | yes |  |
| telegram rate_limit_per_hour | 10 | 10 | yes |  |
| telegram silent_hours_enabled | False | False | yes |  |
| telegram master_send_enabled | False | True | by design | by design: Cloud is the single publisher |
| telegram bot_token set? | False | False | yes | by design: Local must NOT have a token (Cloud's comes from the Render env var, not visible here) |
| telegram channel_id set? | False | False | yes | by design: Local must NOT have a channel (Cloud's comes from the Render env var) |
| telegram personal_chat_id set? | False | False | yes |  |
| telegram proxy_url set? | True | False | by design | by design: Local uses a proxy for Telegram tests; Cloud needs none |

Reconciliation (stored P&L vs closed trades, tolerance 0.01):
- Local: Reconciliation OK: 58 books, stored PnL 0.0 == trades PnL 0.0.
- Cloud: Reconciliation OK: 58 books, stored PnL -11.26 == trades PnL -11.26.
- Cloud books: 58, realized since reset min -2.21 / max 1.57; initial balance setting 100.0
- Local books: 58, realized since reset min 0.00 / max 0.00; initial balance setting 100.0

## Master plan A22 (2026-11-05): parity by config hash
- `python tools/parity_check.py` compares the SAFE config summary (numbers and on/off flags only, from `paper_trading/self_check.py`) of
  the local data folder with Cloud's public `/health/details` (master plan A17), and prints both hashes and each differing key.
- Local hash on 2026-11-05 22:58 UTC: `c708b9da542afe1e`. Cloud: available after deploy gate D2 (the D1 build has no /health/details).
- `auto_send_high_confidence_only`: the **code default is now True** (stricter) everywhere. Local was already True. Cloud has False
  SAVED in its settings, and a saved value wins over the default: owner step in OWNER_TODO (Settings page or Telegram settings).
- The seven Day 6/7 flags stay OFF on Cloud. `SINDHU_RESEARCH_ONLY_TIMEFRAMES` stays OFF on purpose, because the owner excluded P7
  (1m/5m strategies stay on Cloud).
