# MASTER PLAN FINAL REPORT (X2), 2026-11-06

Plan: docs/MASTER_PLAN.md. State: docs/MASTER_PLAN_STATE.md. Before/after numbers: docs/MASTER_PLAN_RESULTS.md.
Deploys: D1 6390321 (2026-11-05 22:37 UTC), D2 02d12c3 (23:07), D3 3eabeac (2026-11-06 03:37 UTC; live 03:39, self-check 4/4 OK). All three were pushed fast-forward only after a green full suite.

## 8.1 Point table
| ID | Name | Status | Evidence | Owner action |
|---|---|---|---|---|
| P1 | Public Telegram signals OFF by default | ✅ Done | `SINDHU_PUBLIC_SIGNALS` gate, tests/test_public_signals_default_off.py; /health/details `public_signals_allowed: false` | keep it unset |
| P2 | Single $100 wallet + research books | ✅ Done | paper_trading/wallet.py, tests/test_wallet.py (17); MAIN_WALLET live on Cloud since 2026-11-05 23:20:33 UTC | - |
| P3 | Incremental candle fetch | ✅ Done | warm scans 159-254 requests / ~3k rows vs 20-day re-download; tests/test_live_candles_incremental.py | - |
| P4 | Neon pre-ping + reconnect | ✅ Done | keepalives, retry, breaker; 0 error lines 00:30-01:30 UTC (was ~60/h) | - |
| P5 | No scanner stalls | ⚠️ Partial | per-coin/prefetch deadlines, 5/5 scans complete; one 139 s stall in the CoinGecko top-coins call is not covered by a deadline yet | - |
| P6 | /health HEAD | ✅ Done | HEAD 200 on Cloud; tests/test_health_head_and_probes.py | - |
| P7 | Cloud only 1h/4h/1d | ➖ Excluded by owner | — | — |
| P8 | Bybit off on Cloud | ✅ Done | cloud_safe_exchange, gate uses position exchange; tests/test_gate_exchange.py | - |
| P9 | Settings 50-cycle test | ⚠️ Partial | docs/SETTINGS_TEST_REPORT.md 50/50 on SQLite; Postgres BLOCKED (no throwaway database) | - |
| P10 | Dashboard cache + light home | ✅ Done | /api/summary (30 s cache); home 3.04 s -> 0.40 s, 30 -> 16 requests | - |
| P11 | Memory ~350 MB | ⚠️ Partial | 428-435 MB steady (was 517-536); target 350 not reached | - |
| P12 | Local/Cloud parity | ✅ Done | tools/parity_check.py; 5 differences listed in docs/PARITY.md | decide the 5 settings |
| P13 | Disclaimer on every signal | ✅ Done | format_signal_message always adds validation class + disclaimer | - |
| P14 | No false "Strong 2/2" | ✅ Done | confluence UNKNOWN + withheld; tests/test_confluence_unknown.py | - |
| P15 | Private owner alerts | ⚠️ Partial | code reads OWNER_CHAT_ID; not set on Render yet | ⛔ set OWNER_CHAT_ID |
| P16 | Old Render services | ⛔ Blocked-owner | guide in OWNER_TODO | ⛔ check + suspend |
| P17 | Secrets rotation guide | ⛔ Blocked-owner | step-by-step in OWNER_TODO (one at a time) | ⛔ rotate |
| P18 | Daily candle update | ⚠️ Partial | task in ops/windows_tasks/install_tasks.cmd (uses data_platform.run_download) | ⛔ run install_tasks.cmd |
| P19 | Daily health report | ⚠️ Partial | ops/windows_tasks/daily_health_report.py (dry run verified) | ⛔ env vars + install |
| P20 | Weekly scorecard | ⚠️ Partial | task wraps scripts/weekly_scorecard.py | ⛔ install |
| P21 | Two new strategies | ✅ Done | docs/STRATEGY_V2_REPORT.md: both FRAGILE (fail FDR over 44 tests) | decision in OWNER_DECISIONS (no action needed) |
| P22 | Forward-test record safe | ✅ Done | docs/FORWARD_TEST_LOG.md | - |
| P23 | Weekly backup restore test | ✅ Done | D:\sindhu_backups\BACKUP_LOG.md: 2026-W45, restore exit 0 | install for weekly runs |
| P24 | OWNER_ONE_PAGE_HINGLISH | ✅ Done | docs/OWNER_ONE_PAGE_HINGLISH.md | read it |
| P25 | Honest README/CV/LinkedIn | ✅ Done | README.md, docs/PORTFOLIO_STORY.md | - |
| S1 | OKX rate-limit handling | ✅ Done | data_engine/exchanges/rate_limit.py, tests/test_rate_limit.py | - |
| S2 | Bot probes -> light 404 | ✅ Done | /wp-admin 404 on Cloud | - |
| P26 | WebSocket 1m feed | ❌ Not done | deferred: would not help the cold start; Cloud ON needs owner OK | - |
| P27 | Fetch budget per scan | ⚠️ Partial | prefetch budget 600 s + per-coin 180 s + rate limiter; no "max K full refetches" counter | - |
| P28 | Candle age on dashboard | ✅ Done | /health/details candles counts; banner dot + "Data purana" (D3) | - |
| P29 | Log noise | ⚠️ Partial | per-series lines counted per scan; error dedup; total lines/hour NOT MEASURED | - |
| P30 | Daily loss limit -5 % | ✅ Done | test_daily_loss_limit_*; capped at 10 % in code | - |
| P31 | Fees, slippage, min notional | ✅ Done | 0.1 % + 0.05 % per side, $5 minimum; cap 25 % per position (D3) | - |
| P32 | Duplicate entry guard | ✅ Done | 60 min, test_duplicate_entry_guard_* | - |
| P33 | Strategy auto-pause | ✅ Done | test_strategy_auto_paused_*; un-pause manual (/api/wallet/unpause) | - |
| P34 | Trade journal | ⚠️ Partial | wallet_journal (gates, sizes, fees, sources); Home shows last 5; no full Trades-page view yet; CSV via monthly export | - |
| P35 | Dashboard password | ⚠️ Partial | Cloud first-account setup needs DASHBOARD_PASSWORD; env login `owner`; existing account keeps working | optional: set DASHBOARD_PASSWORD |
| P36 | Telegram commands owner-only | ✅ Done | public group no longer authorized; tests | set OWNER_CHAT_ID to use commands |
| P37 | Kill-switch button | ✅ Done (D3) | banner button + in-page confirm, close_positions false; tools/ui_killswitch_check.py PASS | - |
| P38 | Startup self-check + /health/details | ✅ Done | Cloud: 4/4 OK, clock skew 0.108 s | - |
| P39 | Config validation | ✅ Done | refuses only new entries; local + Cloud settings validate clean | - |
| P40 | Error alert dedup | ✅ Done | paper_trading/log_dedup.py | - |
| P41 | Neon storage check | ✅ Done | 30.0 MB = 5.9 % of 0.5 GB; retention dry run: nothing older than 90 days | - |
| P42 | Weekly Postgres backup | ⚠️ Partial | Python export + zip + SHA-256 (no pg_dump installed); older backups never auto-deleted (keep rule) | install |
| P43 | Rollback guide | ✅ Done | docs/ROLLBACK.md with known-good commits | - |
| P44 | Local autostart + sleep guide | ⚠️ Partial | task "Local app at logon" + guide in the one-pager | ⛔ install |
| P45 | Monthly CSV export | ✅ Done | ops/windows_tasks/monthly_export.py (tested on 2026-10) | install |
| P46 | UI/UX redesign | ⚠️ Partial | docs/ui/README.md: tokens, banner, new Home, 5 sections, gzip; old tables/settings not reworked | - |
| U1 | Design system | ✅ Done | static/css/tokens.css | - |
| U2 | Five sections | ✅ Done | Main group + bottom tabs; old pages still reachable below | - |
| U3 | Mobile-first, no horizontal scroll | ✅ Done | 7 pages x 2 sizes: no horizontal scroll | - |
| U4 | Banner + home cards | ✅ Done | banner + 4 cards + last 5 events (no equity curve) | - |
| U5 | Tables | ❌ Not done | existing tables unchanged | - |
| U6 | Status badges with text | ⚠️ Partial | on new Home/banner only | - |
| U7 | Loading states | ⚠️ Partial | skeletons + "N sec pehle" on new Home | - |
| U8 | Charts | ❌ Not done | no chart library added | - |
| U9 | Human empty/error states | ⚠️ Partial | new Home + banner | - |
| U10 | Settings page | ❌ Not done | not regrouped | - |

## 8.2 Before vs after
See docs/MASTER_PLAN_RESULTS.md. In short:
- 1 complete scan a day became 5 complete 50-coin scans in a row.
- Memory 517-536 MB became 428-435 MB.
- About 60 error lines an hour became 0.
- `/health` timing out after 60 s became 0.70 s.
- Warm candle downloads are about 200 requests per scan.
- Local home page 3.0 s became 0.4 s.

## 8.3 Part B verdicts
| Strategy | In-sample | OOS | Walk-forward | Neighbours | vs benchmark | Verdict | Why |
|---|---|---|---|---|---|---|---|
| Donchian ensemble 1d | +156.7 %, Sharpe 1.41 | +33.9 %, Sharpe 0.78 | 4/6 years positive | 8/8 positive | Sharpe above BTC/EW B&H (0.69), return below (+84-89 %) | FRAGILE | fails FDR (p = 0.17 over 44 tests) |
| Vol-scaled TSMOM 1d | +306.7 %, Sharpe 1.51 | +58.3 %, Sharpe 0.98 | 4/6 years positive | 8/8 positive | same | FRAGILE | fails FDR (p = 0.12) |

## 8.4 What changed for the owner
- **Home:** the new MAIN_WALLET page ($100 paper account: balance, today's P&L, open trades, health, last 5 events).
- **Banner on every page:** "PAPER TRADING -- real paisa nahi", kill-switch state, data dot, and a red **Kill switch** button with a confirmation.
- **Menu:** five main sections first (Home, Trades, Strategies, Backtests, Settings); all old pages are still there below.
- **Signals:** public Telegram signals stay off until `SINDHU_PUBLIC_SIGNALS=1`. Every message (when on) carries the validation class and a disclaimer.
- **Telegram commands:** accepted only from your private chat (OWNER_CHAT_ID).
- **New public page:** /health/details.
- **New scripts:** ops/windows_tasks (daily report, daily candles, weekly scorecard, weekly backup, monthly export, autostart).

## 8.5 Owner TODO (Hinglish, one per line)
See docs/OWNER_TODO.md "Master plan: owner steps":
1. OWNER_CHAT_ID set karo.
2. (optional) DASHBOARD_PASSWORD.
3. install_tasks.cmd chalao.
4. Purane Render services check karke suspend karo.
5. Secrets ek ek karke rotate karo.
6. Settings ke 5 farq ka faisla karo.
7. Sochna: Cloud ko Ohio region mein naye free service par le jaana (database ke paas, scans tez honge).

## 8.6 Hinglish summary
- **Kya hua:**
  - Cloud ab stable hai: 5 scan lagatar poore (50 coin, 0 error), memory 430 MB ke aas paas, Neon errors khatam, `/health` 0.7 s mein.
  - $100 wallet chal raha hai.
  - Public signals band hain.
  - Dashboard ka naya Home hai, aur kill switch button.
- **Kya nahi hua:** WebSocket feed, purani tables aur Settings page ka redesign, charts, Postgres par settings test, aur memory ka 350 MB target.
- **$100 wallet:**
  - Har strategy ka trade jo saare gates paar kare, wallet ko offer hota hai.
  - Wallet 1 % risk leta hai, ek trade mein zyada se zyada 25 %, max 4 trade, fees + slippage.
  - Din mein 5 % girne par us din naye trade band.
- **Nayi strategies:** dono FRAGILE. Munafa dikha, par 44 tests mein yeh luck bhi ho sakta hai; buy-and-hold se kam kamaya. Koi edge sabit nahi.
- **Agla sabse zaroori kaam:**
  - Database ki doori: scan ka ~60 % waqt database round trip mein jata hai. Cloud ko Ohio mein le jaana sabse bada sudhaar hoga.
  - Phir OWNER_CHAT_ID.

## 8.7 Honesty check
- **Sample size:** the "after" Cloud numbers come from ONE instance over ~4 hours (5 scans).
- **NOT VERIFIED:**
  - the database round trip as the only cause of slow scans;
  - log lines per hour (not measured as a total);
  - rate-limit (50011) behaviour on Cloud after the change (no count was taken);
  - the Postgres part of the settings test (blocked).
- **Process issues:**
  - The Part B simulator had a bug in run 1 (outage day). It was fixed and re-run, and both runs are reported (Amendment 2).
  - Two existing tests were changed on purpose where the owner's plan changed the behaviour:
    - Cloud default exchange bybit -> okx;
    - high-confidence-only default False -> True.
    - Others got data so they still test their original gate.
- **Not done by me (owner rules):** no Windows tasks were installed and no Render env var was changed.
