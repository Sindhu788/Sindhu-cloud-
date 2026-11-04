# SINDHU Investigation Report (READ-ONLY, 2026-11-03)

Method: nothing fixed, pushed, deployed, deleted, or written to production. All DB work on a byte-identical copy (`D:\sindhu_backup_phase0\sindhu.db`, 11,148,918,784 B) or a second copy in scratch; tests ran from `git archive` exports of `main` and `codex/shared-paper-session` with a scratch venv. Secrets masked. Real Telegram never contacted (token/channel empty locally + `SINDHU_TELEGRAM_DRY_RUN=1`).

Definitions: **Original/golden** = `main` b2e790c (17 Sep). **Codex** = branches `codex/trading-intelligence` 5fa95f3 (checked out in root), `history-intelligence` 4a68d85, `overnight-quality-upgrade` 328f405, `shared-paper-session` c223070 (16 Oct, latest). There is no separate "Codex folder"; the `data/*_workspace` dirs are git worktrees of those branches.

## (a) Executive summary
The system is not "broken" in its core trading gates: Codex did not touch the confidence formula, Wilson 25-trade gate, Evolution 100-trade gate, kill switch, risk manager, drawdown guard or the Telegram group filter. What changed for signals is **who may send them and which candles are accepted**, plus some strategy-logic edits. Root-cause candidates for "signals wrong/not arriving" (evidence-ranked, none proven without Cloud access):

1. Codex `signal_ownership` guard: public Telegram sends are allowed **only from the process whose role equals `SINDHU_PUBLIC_SIGNAL_OWNER` (default `cloud`)**. Local/Main can never publish a signal. If Cloud is not scanning/delivering (restart on 2 Nov, cold start, DB trouble), no signals exist anywhere.
2. Local config cannot send anything: `bot_token`/`channel_id` empty, `master_send_enabled=false`. Local DB has **zero** `signal` rows in `telegram_message_log` (only reports/manual) -> signals were always sent by Cloud.
3. Root checkout runs 5fa95f3, not the latest Codex code (c223070); Cloud commit unknown (BLOCKED-USER). Version skew local vs Cloud is likely.
4. New closed-candle freshness guard rejects data older than 1 period; with a lagging feed whole symbols are silently skipped.
5. Strategy logic edits in `backtest_engine/concepts.py` (S/R, BOS shifted by lookback; RSI gain-only) change which setups fire vs the original; previously validated backtests/frozen hashes no longer apply.

### Top 10 critical findings
| # | Finding | Sev |
|---|---|---|
| 1 | Codex public-delivery guard blocks every non-Cloud send; breaks **~14 existing Telegram tests** (e.g. `test_send_test_signal`: "Public delivery blocked...") | critical |
| 2 | Confidence has no predictive value in stored data: AUC 0.463; win rate 34-40% in every bucket (>80 conf = 33.7%) | critical |
| 3 | Paper performance negative: 1,132 closed, win 36.1%, PF 0.75, expectancy -0.078/trade, net -87.96 on 100 start (balance ~12) | critical |
| 4 | Root checkout (5fa95f3) is 12 commits behind latest Codex branch; owner doc confirms root != recovery code | high |
| 5 | Strategy logic changed (concepts.py S/R, BOS, RSI; configured_strategy refactor) - not "safe"; outputs differ from original | high |
| 6 | Auth bypass added: `GET /preview`, `/api/quality/preview` need no login (security.py, overnight branch) | high |
| 7 | Plaintext secrets in config: proxy user:pass (telegram_settings), full Neon DB URL (neon_runtime_connection.json), strategy_sync_secret; Git-ignored? verify | high |
| 8 | Local DB 10.4 GB: lesson_applications 22.5M rows, klines_1m 29.4M, backtest_trades 3.4M; 24% of file (2.7 GB) is free pages; 83 tables (not ~24). Cloud DB capacity unverifiable | high |
| 9 | Slow pages persist: 44/220 endpoints >3 s (worst /api/backtest-history 26.8 s, backtesting/strategies 15.5 s); first Cloud request 40 s cold start | med |
| 10 | Fresh Windows: system Python has no packages, `python` resolves to MS Store stub; requirements unpinned; Node missing (research tests) | med |

## (b) Findings table
| ID | Phase | Check | Result | Sev | Evidence | Root cause | Suggested fix |
|---|---|---|---|---|---|---|---|
| F01 | 0 | disk/backup | PASS | - | D: 75 GB free; backup size equal | - | - |
| F02 | 1 | Codex = folder? | FAIL (assumption) | med | 4 `codex/*` branches + worktrees | Codex worked in git branches | Decide one canonical branch; merge or retire |
| F03 | 1 | Root vs latest Codex | FAIL | high | root HEAD 5fa95f3 vs c223070 | root not updated | Align after review |
| F04 | 1 | expected modules | PASS | - | all present; extra: 95 MB installers, pytest_* dirs, logs 5 MB+ | clutter | clean later |
| F05 | 2 | Python/deps | FAIL | med | 3 pkgs in system python; Store stub on PATH | Windows reinstall | create venv, pin versions |
| F06 | 2 | Node | BLOCKED/FAIL | low | market_history tests: "Node executable unavailable" | not installed | install or skip |
| F07 | 3 | Telegram config | FAIL | high | token/channel empty, master_send false | reinstall/config loss or Cloud-only | confirm intended |
| F08 | 3 | secrets at rest | FAIL | high | proxy creds, Neon URL in data/config | design | move to env, rotate proxy/Neon creds |
| F09 | 3 | `channel_group_filter` | FAIL | high | key absent -> code default "all" (Losing strategies would be sent) | default not set to Profitable+Challenge | verify Cloud value; set explicitly |
| F10 | 3 | challenge config | WARN | low | start 2026-09-03, 2 days, 10->11 USD, still enabled | stale | review |
| F11 | 4 | integrity | PASS | - | quick_check ok | - | - |
| F12 | 4 | size | WARN | high | 2.72M pages, 653k free (24%); top tables above | no retention on lesson_applications/klines_1m | retention/VACUUM (after backup) |
| F13 | 4 | DB "full" | BLOCKED-USER | high | local not full; Cloud = Neon (free tier small); no access | - | check Neon dashboard storage + Render logs |
| F14 | 4 | data currency | WARN | med | positions 29 Aug-11 Sep entries, last exit 16 Sep; decision_log 10 Sep (capped 2000 rows); telegram log last 7 Sep | local engine idle since mid-Sep | expected if Cloud trades |
| F15 | 4 | balance | INFO | - | initial 100; closed PnL -87.96; 65 open | - | - |
| F16 | 5 | gate files untouched | PASS | - | confidence/pattern_stats/auto_downgrade/risk_manager/kill_switch/strategy_groups absent from diff | - | - |
| F17 | 5 | signal_ownership | RISKY | critical | see exec summary | new guard | make owner explicit per host; document |
| F18 | 5 | market_data_guard | RISKY | high | rejects `age>period`, gaps, 20-bar checks | strict, silent skip | log counts to funnel; tune |
| F19 | 5 | concepts.py | RISKY | high | S/R & BOS shift, RSI | "lookahead fix" | re-validate all strategies; compare backtests orig vs new |
| F20 | 5 | configured_strategy refactor | RISKY | med | 71+/66- lookup table, `window==1` fast path | perf | regression-compare outputs on fixed data |
| F21 | 5 | paper engine scan lock/SAFE_START | SAFE (+risk) | med | `SINDHU_SAFE_START=1` disables scanning entirely; duplicate scan raises | env var left set would stop trading | ensure unset in prod |
| F22 | 5 | strategy_matcher | RISKY | med | skips archived/blocked | filters | confirm intended |
| F23 | 5 | security.py preview bypass | SAFETY-CRITICAL | high | public GET paths | QA preview | remove/guard in prod |
| F24 | 5 | AI at runtime | WARN (pre-existing) | med | paper_trading/ai_trade_review.py, challenge_ai_advisor.py, self_learning_engine/ai_advisor.py import ai_integration; backtest_engine/paper_trading engine core do not | exists in original | confirm these are opt-in/off |
| F25 | 5 | freshness recheck 60 s | FAIL | med | no 60 s recheck constant found; only 15 min freshness + 0.5% drift (telegram_bot) | not implemented / elsewhere | clarify spec |
| F26 | 6 | tests original | FAIL | med | 35 failed / 2221 passed / 2 skipped (prior baseline 2258/0) | see root causes | below |
| F27 | 6 | tests Codex | FAIL | high | 55 failed / 2392 passed / 8 skipped | +20 failures vs original | below |
| F28 | 7 | smoke | PARTIAL | med | 220 endpoints: 3 non-200 (/paper-trading 404, cloud-state 401, shared-wallet 503), 44 >3 s (load from parallel tests inflates) | heavy aggregations on 3.4M-row tables | cache/index later |
| F29 | 10/11 | funnel (local, 10 Sep 00:02-01:18) | INFO | med | 2000 decisions: 13 opened, 1,987 rejected; top reasons: max coins/strategy (5) 1,375; drawdown pause (7 losses) 408; position lock 125; opposite-position block 37 | caps/guards working | consider that >99% reject rate means very few signals |
| F30 | 11 | signal send history | INFO | med | local telegram log: 0 signal rows; failures = proxy ConnectionError (10), ReadTimeout (2), "signal 933 min old, too stale" (1) | proxy instability; staleness gate works | replace proxy or send from Cloud only |
| F31 | 12 | confidence calibration | FAIL | critical | buckets (40-50] n6 83%; (50-60] n129 40%; (60-70] n539 36%; (70-80] n167 37%; >80 n291 34%; AUC 0.463 | data predates 17 Sep recalibration (bd0c96d); not re-measured | collect post-recalibration trades; Cloud DB needed |
| F32 | 12 | weakest strategies | FAIL | high | FVG 50% Eq 21 trades 14% win -5.04; HTF Key Level Engulf 53/30% -5.78; HTF-LTF FVG/OB 35/49% -5.41; Ichimoku 5m/15m/1h Trailing-SL & 1h Indicator-Exit 0% wins (n 5-8); HTF Trendline Breakout 10/0% | weak edge/small n | downgrade logic (100-trade) not reached; manual review |
| F33 | 13 | safety gates | PASS (by suite) | - | gate tests in existing suite pass in both trees; not independently re-triggered | - | - |
| F34 | 14 | Cloud health | PARTIAL | med | /health ok, postgres, started 2026-11-02 19:58 UTC; others 401 | login required | BLOCKED-USER |
| F35 | 15 | correlation | WARN | med | only same-coin cap (5); correlation endpoint is warning-only (6 s) | design | add basket cap later |
| F36 | 8/9 | functional/UI (browser clicks, settings persistence, mobile, console errors) | BLOCKED | med | no headless browser/login on Cloud; local run limited to HTTP GET sweep; Playwright not installed | scope/time | separate session |

### Test failures grouped by root cause
- **Original (35)** - all env-coupled: tests that call real `storage` instead of the `test_db` fixture need `data/database/sindhu.db` (with my relocated data dir they hit "no such table: paper_strategy_groups/activity_log/audit_trail_log"); cloud requirements-import test; strategy_sync (secret/network) ; Postgres expiry date test (date-dependent). Not Codex.
- **Codex extra (~20)**: (1) public-delivery guard -> `phase6_multi_recipient`, `phase6_test_signal`, `phase4_quiet_mode`, `phase4_backup_alert`, `telegram_silent_hours`, `telegram_multi_channel`, signal reactions, daily_missed_opportunity (**real regression**, tests not updated for the guard); (2) `test_market_history` x2: Node missing (env); (3) `test_cloud_runtime` nav test: `control_room` extra page; (4) `test_overnight_quality`, `test_trading_intelligence` (1 each, not diagnosed).
- Caveat: results depend on my relocated data dir; baseline "2258/0" was on the live data layout, so exact counts are not directly comparable.

## (c) Comparison
| Item | Original (main b2e790c) | Codex latest (c223070) | Local root now | Cloud |
|---|---|---|---|---|
| Code version | 17 Sep | 16 Oct | 5fa95f3 (10 Oct) | unknown (BLOCKED-USER); started 2 Nov 19:58Z |
| Confidence formula | calibrated 17 Sep (confidence.py) | unchanged | same | unknown |
| Wilson 25 / Evolution 100 | present | unchanged | same | unknown |
| Telegram | sends from any host | only owner host (default cloud) | token/channel empty; send off | unknown |
| Telegram group filter | code default "all" | same | key absent => "all" | unknown |
| Balance | 100 initial | shared 100 USD wallet added | 100 init; PnL -87.96 | unknown |
| DB | SQLite | + Neon shared journal | 10.4 GB SQLite | Neon Postgres (size unknown) |
| Tests | 2221 pass/35 fail (my env) | 2392/55 | - | - |

## (d) Proposed fix order, rollback, risk
1. (low) Decide canonical code line; put root on it in a new branch; keep main untouched. Rollback: checkout previous branch.
2. (low) Confirm who publishes signals; set `SINDHU_PUBLIC_SIGNAL_OWNER`/`SINDHU_CLOUD_MODE` explicitly on each host; confirm `SINDHU_SAFE_START` unset on Cloud.
3. (low) Get Cloud logs/Neon usage; free space if full (needs owner).
4. (med) Update tests for the guard; reinstall env (venv, pin versions).
5. (med) Set `channel_group_filter` explicitly; rotate proxy and Neon credentials; move to env.
6. (med) Revalidate strategies touched by concepts.py with backtests orig vs new on fixed data before trusting Cloud allowlist strategies.
7. (high) Re-measure confidence calibration on post-17-Sep trades; consider disabling Telegram for negative-expectancy strategies.
8. (med) DB retention/VACUUM for lesson_applications/klines_1m (only after verified backup).
Overall risk: low for 1-5, medium-high for 6-8.

## (e) BLOCKED-USER
Cloud login (settings, logs, 14:33-14:45 UTC downtime, deployed commit, env var names); Neon dashboard (storage used/limit); Render dashboard; confirm whether Telegram proxy works; browser UI testing session; Node install; authority to read `ai_settings.json` (keys; a permission rule blocked it); one local uvicorn test server (port 8431, my test copy) is still running - stop it manually or tell me to; scratch dir contains 11 GB DB copy to delete.

## (f) Open questions
Which host should publish signals (Main or Cloud)? Is Cloud on c223070 or older? What exact symptom (no signals / wrong direction / duplicate)? Was the 14:33-14:45 downtime on 2 Nov? Is `channel_group_filter` set on Cloud? Is the "60 s recheck" a requirement or a memory? Are Codex's strategy-logic changes approved?

## Not covered (honest limits)
Phases 8-9 functional/UI clicking, 13 gate-by-gate triggering, 10 live end-to-end with mocked Telegram, and any post-17-Sep calibration were not executed; funnel is the local 10 Sep sample (1h16m) only.

---
# Final update 2026-11-03 - comparison and corrections

**Correction:** report row F25 ("60 s recheck not found") was wrong. `TELEGRAM_SWEEP_INTERVAL_SECONDS = 60` exists in main (`paper_trading/engine.py`, hourly before 14 Sep) and is pinned by a test.
**Root cause confirmed (Render logs):** Cloud ran the Codex shared scanner (`SINDHU_SHARED_PAPER_ENABLED=1`, requires `SINDHU_TELEGRAM_DRY_RUN=1` and `SINDHU_PUBLIC_SIGNAL_OWNER=disabled`): BTCUSDT/ETHUSDT only, nothing opened, no Telegram, legacy engine and every delivery scheduler skipped. The free plan also sleeps after ~15 min idle.
**"Cloud DB full" was not true:** Neon is 18.6 MB.

| Item | Original (main b2e790c) | Codex (c223070) | Recovery/clean (4d7e31b) | Cloud now |
|---|---|---|---|---|
| Cloud mode | legacy engine + Telegram | shared scanner, delivery disabled | legacy engine + Telegram (flag ignored) | deployed 4d7e31b; env still old until manager applies RENDER_ENV_CHANGES |
| Confidence / Wilson 25 / Evolution 100 / drawdown / kill switch / 5-coin cap | present | unchanged | unchanged, trigger tests added | same code |
| Freshness 15 min, drift 0.5 %, 60 s sweep | present | present | present, pinned by tests | same code |
| concepts.py S/R, BOS, RSI | levels = confirmation bar high (1-12 % real pivots) | fixed (100 % real pivots) | fixed (kept) | same |
| /preview anonymous access | none | open | removed | removed after deploy |
| Telegram public send | any host | only owner host (default cloud) | explicit SINDHU_PUBLIC_SIGNAL_OWNER, logged reason, startup banner | blocked until env changed |
| Tests | 2254 pass / 2 fail | 2392 / 55 (my env) | 2287 / 0 | - |
| Slow endpoints | backtest-history ~24 s | same | ~1 s (others 0.6-1.6 s) | - |
| DB | SQLite 10.4 GB / 83 tables | + Neon shared journal tables | no new schema except archive tables on reset | Neon 18.6 MB, 47 tables |

---
# Final status after the grand master run (4 Nov 2026)
| Item | Original main (17 Sep) | Codex c223070 | Now: recovery/clean 36f619d | Cloud now |
|---|---|---|---|---|
| Signals | sent by legacy engine | none (shared scanner, delivery off, BTC/ETH only) | engine ON, 10 liquid coins, delivery READY | live signals since 3 Nov 21:33Z; Losing-group signals withheld (2 seen) |
| Candle feed | Binance REST (1000/page) | same | OKX paged correctly (fix 3 Nov) | data age ~22 s in the decision trace |
| Safety gates | present | unchanged | unchanged, trigger tests | same code |
| Tests | 2254 pass / 2 fail | 2392 / 55 (my env) | 2346 / 0 | CI green on 36f619d |
| Dashboard | 0.5-26 s endpoints | same | Lite layer, cached slow endpoints | not tested authenticated |
| Balance | $100 start, -87.96 | shared wallet | reset to $100 (archive kept) | 58 books at $100 |
| Monitoring | none | scan receipts | watchdog, daily summary, reconciliation, /api/ops/why | owner alerts need personal_chat_id |
| Backups | none tested | none | export + restore verified | Neon export 4 Nov |
| Performance evidence | PF 0.75 (29 Aug - 16 Sep) | - | all 10 most-traded strategies PF < 1 in 60-day backtest; none profitable in both IS and OOS | no closed trade since 17 Sep |
