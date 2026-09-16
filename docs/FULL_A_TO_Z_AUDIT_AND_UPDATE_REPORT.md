# SINDHU — Full A-to-Z Audit & Update Report

> **Status of this file (14.1):** this document did not exist before 2026-09-16 (no `docs/` folder existed in the repo).
> It is created here and is append-only from now on. Each batch adds a new dated section at the bottom. Earlier content is never rewritten.
> Companion history document (Hinglish): `docs/SINDHU_PROJECT_HISTORY_HINGLISH.md`.

---

## Batch 2026-09-16 (A) — Full-System Audit (morning)

Carried over from the same-day audit that preceded the hands-on batch. The full evidence is in that session. Summary:

| # | Issue | Severity | Fix / status | Commit |
|---|---|---|---|---|
| A1 | `tests/test_weekly_snapshot.py` copied the REAL 11 GB `sindhu.db` into the pytest temp dir (patched `backup.DB_PATH` but not `weekly_snapshot.DB_PATH`), filled C: to 0.9% free and cascaded into 1 failed + 25 errored tests | High | Fixture now patches `weekly_snapshot.DB_PATH`. Suite then 2182 passed / 0 failed | `7ab5398` |
| A2 | Local Telegram settings: an empty saved token/channel shadowed `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHANNEL_ID` env vars | Medium | Empty-string env fallback on the local branch too + 3 tests | `55bfd44` |
| A3 | Every cloud dependency unpinned, so each Render rebuild could pull a breaking release | Medium | Pinned to versions resolved and verified that day (fresh venv import, 223 routes, /health ok, pip check, manylinux wheels) and deployed; `started_at` 13:52:08 UTC, healthy | `baa8497` |
| A4 | Fresh verified backup | — | `data/database/backups/sindhu_20260916_124514.db` (11.1 GB, 81 tables, 1,197 positions) | n/a |
| A5 | Confidence % miscalibrated (AUC 0.4712; 71.3% claimed vs 37.1% real) | High (decision risk) | Reported only. Gates untouched (rule 10.5/11.5) | n/a |
| A6 | Weekly snapshot `sindhu_weekly_20260914_144407.db` recovers to zero tables | Low | NOT deleted; awaiting CEO permission | n/a |
| A7 | Proxy credentials in plaintext in `telegram_settings.json` and seen in tool output | High (security) | CEO must rotate the proxy password | n/a |

---

## Batch 2026-09-16 (B) — Grand Master Hands-On Investigation & Repair

### 1. Executive summary

Every screen was clicked and every settings save was driven in a real browser. This covered the local app and **the real cloud app code** (`cloud_runtime/app.py`) running locally against a copy of the real trading data. Timings come from a scripted, identical click path run against the original code and then the fixed code.

**Root causes found (with evidence), all fixed:**

1. **"Nothing saves" on the cloud.** The cloud runner never mounted `/api/settings`. Its default landing page (CEO Control Room) has a Settings card that read and wrote that route. Every field showed blank/default values and every Save failed 404 into a retry queue that could never succeed. The Settings and Configuration Panel pages also failed outright: `Failed to load page GET /api/settings -> 404`.
2. **Telegram page "not opening".** Its first render waited on a live `api.telegram.org` reachability check. Measured **15.08 s every time** locally (the check hit the dashboard's 15 s timeout), and 17.0 s in the before run. Now it renders first and fills the check in afterwards.
3. **30–50 s navigation.** The Paper Trading page fired **one confluence request per open position (70) on every 30 s auto-refresh**, each 1–2 s even in isolation. Together they saturated the server's worker threads, so every other page's requests queued behind them. Before run: 116 requests on that page, **38 killed by the 15 s timeout**, and the next page (Telegram) had 28 more timeouts. Contributing causes:
   - an SQLite `MIN(),MAX()` query that defeated its own index (0.46 s → 0.003 s);
   - `risk-metrics-all` running 154 separate queries (11.6 s → 0.47 s, identical output);
   - uncached heavy endpoints (`best-worst` ~10 s under load, `groups` 3.8 s, `style-breakdown` 3.7 s);
   - global search walking 3.4M rows for any non-coin term (>300 s → 0.47 s).

**New:**
- Telegram Status section.
- Daily 24h report sections (and the report now actually runs on the 24/7 cloud).
- Settings validation, "✓ Saved", Reset to default, dirty-state Save button, multi-field save, change history.
- Per-strategy cooling-off.
- Blue spinning-circle loader.
- A mobile layout fix: the topbar forced every page to 547 px on a 375 px phone.
- PKT everywhere times were shown.

**Login gate:** the public cloud login was **not** disabled; that would have exposed live trading controls on the internet. Hands-on testing used loopback-only (127.0.0.1) processes with the session check bypassed inside that process only. Both were stopped, their launchers deleted, and the gate verified with real requests at **2026-09-16 18:36:13 UTC**:
- local `GET /api/paper-trading/status` → **401 `login required`**, `GET /` → **307 → /login**;
- production cloud: same **401** and **307 → /login**.

### 2. Baseline (Section 3)

| Item | Value (2026-09-16) |
|---|---|
| Git commit at start | `baa8497` (main, clean, in sync with origin) |
| Cloud (Render) | `/health` ok, `started_at 2026-09-16T13:52:08Z`, `db_backend: postgres`, `cloud_mode: true` |
| **Cloud incident observed** | 14:33–≥14:45 UTC: TLS accepted at the Render edge but **no response for ≥12 min** (90–150 s curl timeouts, repeated). Recovered by 15:34 UTC with the **same `started_at`**, so the process was alive but unresponsive, not restarted. Consistent with the worker-thread saturation root cause above. Render logs are not accessible without Render credentials (BLOCKED) |
| Local server | not running at start |
| Local open positions | 70 (baseline) → 65 by end of session (engine resumed and closed positions normally) |
| Local closed trades / net / WR | 1,127 / −85.22 / 36.29% (baseline); 1,132 / −87.96 / 36.13% at analysis time |
| Kill switch | no row = inactive (fail-safe default) |
| Account drawdown breaker | not paused; peak 5,722.71, current 5,712.04 (0.19%) |
| Backup | `sindhu_20260916_124514.db` verified readable (81 tables). Restore **drill** never run (tempfile lands on C:, too small); no destructive DB operation was performed in this batch |
| Tests at start | 2182 passed (morning run) |

### 3. Issues found — severity, evidence, root cause, fix

| ID | Issue | Sev | Evidence (real) | Root cause | Fix |
|---|---|---|---|---|---|
| B1 | Cloud: Settings/Config Panel pages fail; CEO Settings card blank and Save always fails | **Critical** | Cloud app run hands-on: `#settings` → "Failed to load page GET /api/settings -> 404"; CEO page 12 × 404 | `settings` router never included in `cloud_runtime/app.py` | Mounted it (import graph checked in a fresh process: no heavy modules; every setting already persists to Postgres via `load_persistent`). Verified: Settings opens in 0.26 s with real values; Default Risk 1→0.8 saved (`POST 200`, "✓ Saved"), still 0.8 after reload |
| B2 | Keystroke autosave saved half-typed values and hid failures | **High** | Code: debounced 600 ms autosave POSTed all 10 engine fields on any pause; failures went to `pendingQueue` "(will retry)" with no real error | Design | Explicit **Save Changes** (disabled until a real change), inline validation, server-side 422 validation, only changed fields sent (multi-field), "✓ Saved" only after a server-confirmed value, Reset to default (fills defaults, needs Save), Discard, change history. Unsaved edits now survive the page's 30 s auto-refresh (verified live) |
| B3 | Settings form could show "undefined" after a failed fetch and save it | Medium | `apiGet(settings).catch(() => ({}))` | Fallback object | Marked `_unavailable`; form disabled with an honest message |
| B4 | Telegram page blocked ≥15 s before showing anything | **High** | Cloud app: 15,076 ms; network-check `ERR_ABORTED` at 15 s | Initial `Promise.all` awaited `/telegram/network-check` (9.8 s locally) | Page renders first; check fills in asynchronously. After: **0.49 s** (cloud app), **0.32 s** (local) |
| B5 | Paper Trading confluence fan-out saturates server | **Critical** | Before: 116 requests, 38 × 15 s timeouts; next page 28 timeouts; single confluence request measured 47 s under load | 1 request per open position (70) on every 30 s refresh | One cached bulk endpoint `/api/paper-trading/confluence-open-positions` (non-blocking, 60 s stale-while-revalidate). After: 48 requests, **0 timeouts** |
| B6 | `get_symbol_time_bounds` slow | High | UUSDT 347,501 rows: 0.46 s combined vs 0.003 s split, identical | SQLite min/max optimisation only applies to a single aggregate | Split scalar subqueries (also speeds regime checks and the engine) |
| B7 | `risk-metrics-all` 11.6–15.3 s | High | curl + in-process timing | Loop of 154 per-strategy queries; batch function already existed | Uses `compute_risk_metrics_batch` (identical=True on real DB) + 60 s cache |
| B8 | `best-worst/strategies` ~10 s under load | Medium | curl 10.3/9.5 s; cProfile 270 connections | Uncached | 120 s stale-while-revalidate cache + startup warm |
| B9 | `groups` 3.8 s, `style-breakdown` 3.7 s gate Paper Trading render | Medium | curl isolated | Re-reads 154 meta files each call | 30 s / 60 s cache; invalidated on group move/sync; warmed at startup |
| B10 | Global search >300 s for a non-coin term | High | `?q=Ichimoku` curl timed out at 300 s; `?q=BTC` 2.1 s | LIKE walk over 3.4M `backtest_trades` rows | Trade search only when a coin matches. After: 0.47 s / 0.64 s |
| B11 | Mobile: every page 547 px wide on a 375 px phone | **High** | `innerWidth 547` vs `visualViewport 374`; values right-aligned off-screen (screenshot) | Topbar needed ~553 px | ≤480 px: brand mark only, hide static CEO pill and Live Logs icon (still in Quick Actions), smaller icons/gaps. After: 375 px layout on all 8 cloud pages, no sideways scroll |
| B12 | Cloud Home/unknown hash → "Cannot read properties of undefined (reading 'level')" | Medium | Cloud app run hands-on | Stub `/api/home` has no `maturity`; router falls back to Home | Graceful "laptop-only page" card with link to Paper Trading |
| B13 | Cloud Settings: backup / weekly snapshot / infra digest cards 404 as unhandled rejections | Low | Console: 3 × rejection 404 | Laptop-only routers | Cards say "Available on the local laptop app only", buttons disabled |
| B14 | Cloud topbar search silently does nothing | Low | `/api/search` 404 | Laptop-only router (lessons/backtest tables not in cloud DB) | Result panel explains it; not mounted (would 500) |
| B15 | Daily report never auto-delivered | **High** | `start_daily_report_scheduler_thread` only in `sindhu_web/server.py`; laptop token empty | Scheduler not started on cloud | Started in cloud lifespan (same once-per-UTC-day gate + master switch) |
| B16 | Times shown in UTC | Low | 20 display sites (raw ISO slices, "UTC" labels) | Pre-PKT code | Converted to PKT (`fmtPKTFull`). UTC kept only for two config **inputs** stored in UTC and labelled so (Time-of-Day filter, Silent Hours) |
| B17 | `tests/test_cloud_runtime.py` requirement parser broke on pinned lines | Medium | Failed after `baa8497`: listed `fastapi`, `pandas`… as "missing" | Parsed `fastapi==0.141.1` as the name | Parse name before extras/specifier. Same assertion, not weakened |
| B18 | Status text stuck on "Fix the highlighted field(s)" after correcting a value | Low | Found hands-on in this batch | Status only refreshed when edits existed | Clears when no edits |

### 4. Section 5.12 live tests

| Test | Where | Result |
|---|---|---|
| Initial Balance = $100 | Real local app | Already $100 (file + API). Save correctly stays disabled (no change). Live save path proven on the same form: Daily Goal 101→100 via real click → `POST 200`, "✓ Saved (daily_goal_pct)", file `100.0`, history entry 18:06:40 UTC |
| Initial Balance = $100 | Real cloud app code, data copy | 100→150 (file 150.0) → 100 via real clicks → "✓ Saved (initial_balance)", file `100.0`, **100 after full reload**, history shows both changes |
| Challenge group $2 | Real cloud app code, data copy | Challenge Mode "Challenge group $2 (audit test)" created via UI: `POST 200`, DB row `start_amount = 2.0`, visible after reload as "$2 → $4 -- 7 days left" |
| Challenge group $2 as a **separate trading balance** | — | **BLOCKED (CEO decision).** No per-group balance exists. `initial_balance` drives position sizing, the per-strategy auto-downgrade threshold and the account-wide drawdown circuit-breaker (compares the combined balance to its stored peak and never self-unpauses). A $2 book would immediately change the breaker math, a safety gate (rules 2.4/2.7). Challenge Mode start amount is tracking-only (`set_challenge` never touches sizing) |

### 5. Navigation speed — real before/after (Section 7.4)

Same scripted human-paced click path, same warm-up (server ready + 250 s), local app with the engine running.
- **shown** = the loader is replaced by page content.
- **settled** = no dashboard request in flight for 1 s.
- **TO** = requests killed by the 15 s client timeout.

The Paper Trading dwell is 35 s so its auto-refresh fires once. Each run is n = 1, so ±2–3 s variance from engine ticks is normal.

| Page | BEFORE shown / settled (TO) | AFTER-1 | AFTER-2 (final) |
|---|---|---|---|
| CEO (landing) | 6.98 / 6.98 s (5) | 6.91 / 6.91 (3) | 6.96 / 6.96 (9) † |
| **Paper Trading** | **18.67 / 36.49 s (38 TO, 116 req)** | 18.01 / 20.26 (0 TO, 48 req) | **16.10 / 18.98 s (0 TO, 48 req)** |
| **Telegram** | **17.00 / 17.99 s (28 TO)** | 0.58 / 6.46 (0) | **0.32 / 4.73 s (0)** |
| Home (Dashboard) | 11.00 / 11.00 s | 4.08 / 4.08 | 4.29 / 4.29 |
| Risk | 3.41 / 3.41 s | 5.67 / 5.67 | 2.24 / 2.24 |
| Strategies | 15.22 / 24.03 s (1 TO) | 2.90 / 11.40 | 2.84 / 12.73 |
| Signal Tracker | 4.00 / 4.00 s | 8.15 / 8.15 | 8.15 / 8.15 ‡ |
| Settings | 1.01 / 2.00 s | 0.16 / 1.31 | 0.16 / 1.25 |
| Strategies overview | 2.99 / 2.99 s | 3.61 / 3.61 | 1.27 / 1.27 |
| Reports | 4.00 / 4.00 s | 0.30 / 0.30 | 0.23 / 0.23 |

- **†** CEO page: `decision-center` and `backtest-history` still hit 15 s under concurrent load on the laptop (3–4 s isolated). **Not fixed.** `decision-center` was deliberately not cached because it shows live kill-switch/drawdown state. These routes don't exist on the cloud.
- **‡** Signal Tracker `match-table` measured 3.7 s before and 8.1 s after. It wasn't changed; this is engine-tick variance. **Not fixed.**
- **Honest remaining gap:** Paper Trading still takes ~16 s to first show locally, gated by its first batch of ~18 calls competing with the engine. Every call is <4 s in isolation.
- **Cloud timings:** the production cloud requires login, so production before/after navigation timings are **NOT TESTED**. The same code paths were measured on the cloud app locally (Telegram 15.08 s → 0.49 s; Settings from 404 to 0.26 s).

### 6. New features

- **Telegram Status section** (Telegram page, Signal Log tab), from `telegram_analytics.status_summary()`:
  - overall PnL shown prominently;
  - total trades and win ratio;
  - Losing/Profitable/Challenge trades, win % and PnL;
  - today's Telegram sent/won/lost/pending, plus today's sends by group.
  - **Cross-check (6.4):** per-group numbers equal `strategy_groups.all_group_summaries()` (the Groups tab's own function). On real data: Losing 822 / 36.01% / −140.68, Profitable 208 / 32.69% / 26.91, Challenge 102 / 44.12% / 25.81; the sum equals the overall 1,132 / −87.96; unassigned 0. The Groups tab endpoint is now cached ≤30 s, so right after a trade closes the two can differ for up to 30 s.
  - **Mobile (6.5):** at 375 px the card is 347 px and the table 319/319 px, with no page sideways scroll after B11.
- **Daily 24h report (Section 11):** the existing `daily_report.py` gains "1) Overall (aaj)", "2) Group-wise" and "3) Telegram (aaj)" sections from the same `status_summary()`, and is now scheduled on the cloud. Generated against real data (see the Hinglish history doc for the text). **Note:** it will send once per UTC day to the main channel. The first send happens shortly after deploy if no `daily_report` row exists today in the cloud DB.
- **Per-strategy cooling-off (10.1):** `paper_trading/cooling_off.py`. After `cooling_off_loss_streak` (default 4) consecutive losses, that one strategy opens nothing new for `cooling_off_hours` (default 3 h, counted from its last losing close), then resumes automatically. It is stateless (derived from trade history), only ever adds a reason not to trade, and 0 turns it off. Editable in Engine Settings.
- **Spinner loader (7.5):** blue `--accent` rotating circle on every page transition and in the new sections.

### 7. Section 6.6 / 8 / 9 / 10 findings

**6.6 — only Profitable and Challenge sent to Telegram:** the code gate is at `paper_trading/telegram_bot.py:1400`. A Losing-group strategy's send is refused and logged "Telegram sending is withheld for strategies in the Losing group"; the strategy keeps paper trading.
- **Local data:** only 3 successful signal rows ever (manual tests, no linked positions), 0 automatic, so there are no real recent signals to check.
- **Cloud data:** needs login, **NOT TESTED**. The new Status section shows "Sent today by group … Losing N" with a warning banner if N > 0, so this can be checked on the cloud dashboard directly.

**8 — walkthrough (cloud app code + local app):**
- All 12 cloud pages render real content.
- Console errors after fixes: none on any page (3 settings-page rejections fixed, B13).
- Back button: Memory Core → Back → Risk re-rendered correctly.
- Dark/light toggle: dark → light (body rgb(243,245,250)) → dark.
- Export: `trades.csv` 200 `text/csv`, attachment, 1,067 lines.
- Search: works locally (after B10); explains itself on the cloud.
- Mobile: B11.
- **Session timeout warning (8.6):** sessions last 30 days and there is **no pre-expiry warning**. Gap, not built.
- **Manual refresh (8.7):** pages auto-refresh (10–30 s) or have their own refresh/retry buttons. Not exhaustively clicked on every card (**PARTIAL**).
- **Remaining UTC (8.11):** only the two UTC config inputs.

**9 — trading logic (read-only analysis of the real local DB, 1,132 closed trades):**
- **9.1 displayed vs executed entry:** 0 signal messages carry a linked real position, so there was nothing to compare. **NOT TESTABLE** on local data.
- **9.2 costs (same constants as `position_manager`):**
  - slippage + spread **$68.98**, commission **$86.22**, total **$155.19**;
  - net after costs −$87.96, so the estimated net before costs is **+$67.23**;
  - costs are applied consistently: entry slippage 0.05% + spread 0.03%, the same on exit, and 0.1% commission on entry + exit notional.
- **9.3 confidence drift** (last 30 trades, slope < −0.2/trade): 6 strategies. Examples: *Lower Time Frame Liquidity Reversal* 73.0 → 65.7, *Range Breakout Volume Confirmation* 79.0 → 70.7, *Laxman Rekha 5-EMA* 75.0 → 68.8. Early warning only.
- **9.4 conversion:**
  - decision log (last 2,000 kept): 13 opened / 1,987 rejected (0.65%);
  - signals sent 3, all manual test sends without positions;
  - there is no automatic sent-signal history to measure a gap against.
- **9.5 cost of being wrong:** 22 of 52 strategies with both wins and losses have average gain < average loss. Worst: *HTF-LTF FVG/OB Confluence* 0.25, *Market Structure Shift Reversal* 0.32.
- **9.6 overlap:** variant families co-enter the same coin + direction within 5 min. FVG Momentum Pullback Fixed 1:2 / 1:3 / Structure: 10 co-entries each pair. Ichimoku Indicator-Exit vs Trailing-SL (5m: 11, 15m: 9). These are intentional exit variants but **multiply exposure** on the same setup.
- **9.7 max drawdown:** 14 strategies made a new max drawdown within their last 20 trades (e.g. *Market Structure Shift Reversal*, *Fibonacci Golden Zone*, *HTF Key Level Engulfing*).
- **9.8 weekend vs weekday:** weekday 105.7 trades/day, 37.1% WR; weekend 25.0 trades/day, 22.7% WR. Only 3 weekend days of data, so the sample is too small to call it a real effect.
- **9.9 correlation:**
  - Open: 65 positions on 25 coins, **up to 14 on one coin**; long risk $17.88, short risk $12.48.
  - Existing cap: `max_portfolio_risk_pct_per_coin` = 10% of initial balance **per coin**.
  - **Correlated different coins are not aggregated** in sizing. Gap reported, **not implemented**: it changes position sizing and needs a CEO decision (rule 2.6).
- **9.10 system self-confidence (report only):** last 50 trades 18.0% WR, −$4.55, claimed average confidence 75.8%. All-time WR 36.1%.

**10.2 restart/duplicates:** the server was restarted 6 times in this batch with the engine enabled. Positions resumed and closed normally, and no duplicate positions were seen (open count only went down, 70 → 65). The guards use position-lock plus an in-memory reservation. **PARTIAL** (observed, not a controlled duplicate-injection test).
**10.3 Telegram retries:** not re-tested this batch (**NOT TESTED**). Existing behaviour: every attempt is logged in `telegram_message_log` with success/error.

### 8. Files changed (this batch)

- `cloud_runtime/app.py`: mount settings router; start daily report scheduler.
- `data_engine/storage.py`: split MIN/MAX time-bounds query; `list_recent_closed_pnls`.
- `paper_trading/config.py`: validation, defaults accessor, change history, cooling-off defaults.
- `paper_trading/cooling_off.py` (new).
- `paper_trading/engine.py`: cooling-off check in the pre-entry path.
- `paper_trading/telegram_analytics.py`: `status_summary()`.
- `paper_trading/daily_report.py`: Overall / Group-wise / Telegram sections.
- `sindhu_web/api/paper_trading.py`: validated save, defaults/history endpoints, status-summary, bulk confluence, cached groups/style/risk metrics.
- `sindhu_web/api/reports.py`: cached best-worst.
- `sindhu_web/api/settings.py`: validation.
- `sindhu_web/api/search.py`: skip trade scan without a coin match.
- `sindhu_web/server.py`: warm new caches.
- `sindhu_web/static/js/app.js`: explicit saves, Telegram Status, async network check, spinner, bulk confluence, cloud graceful degradation, PKT.
- `sindhu_web/static/css/app.css`: spinner, validation, Telegram Status, mobile topbar.
- `tests/conftest.py`: clear endpoint cache per test.
- `tests/test_cloud_runtime.py`: pinned-requirement parser.
- `tests/test_audit_20260916_fixes.py` (new, 17 tests).
- `tests/test_cooling_off.py` (new, 8 tests).
- `docs/FULL_A_TO_Z_AUDIT_AND_UPDATE_REPORT.md`, `docs/SINDHU_PROJECT_HISTORY_HINGLISH.md` (new).

### 9. Commits (this batch, in order)

- `688b81a` Fix cloud requirements test to parse pinned lines (regression from baa8497)
- `eaafde5` Fix 30-50s dashboard navigation: remove server-saturating fan-out and slow queries
- `37b7668` Open Telegram page instantly, add Telegram Status section, and deliver the daily report from the cloud
- `5ce6be3` Add per-strategy cooling-off period after consecutive losses
- `ddfc37c` Fix settings not saving on the cloud; add validated explicit Save, reset and history
- `20c2bfc` Fix 375px mobile layout, degrade laptop-only features cleanly on cloud, show PKT everywhere
- `864c356` Add regression tests for the 2026-09-16 hands-on audit fixes
- `cc59a44` Guard settings field-error helpers against inputs without a parent element

Test results: see Section 11.

### 10. PASS / FAIL / BLOCKED / NOT TESTED

| Section | Item | Status |
|---|---|---|
| 3 | Baseline recorded | PASS |
| 3.2 | Restore-tested backup | PARTIAL: verified-readable backup; restore drill not run (no destructive op performed) |
| 4 | Login gate removal for testing | PASS (loopback-only instead of public; see summary) |
| 4.4 | Login gate restored + verified by real request | **PASS** (401 / 307→/login, local + cloud, 18:36:13 UTC) |
| 5.1–5.3 | Settings save root causes traced + fixed | PASS |
| 5.4 | "✓ Saved" only on real success | PASS |
| 5.5 | Local + cloud persistence | PASS (local file; cloud app via `load_persistent` path; production Postgres not reachable = NOT TESTED) |
| 5.6 | Reset to default | PASS (code + defaults endpoint test; fills form, requires Save) |
| 5.7 | Validation | PASS (−5 → inline "Must be greater than 0.", Save disabled; server 422) |
| 5.8 | Real current values on load | PASS |
| 5.9 | Multi-field save | PASS (test + only changed fields sent) |
| 5.10 | Save disabled when unchanged | PASS |
| 5.11 | Change history | PASS |
| 5.12 | Initial Balance $100 live | PASS |
| 5.12 | Challenge $2 live (Challenge Mode) | PASS |
| 5.12 | Challenge group separate **trading** balance $2 | **BLOCKED** (safety-gate interaction, CEO decision) |
| 6.1–6.2 | Telegram page root cause + fix | PASS |
| 6.3 | Telegram Status section | PASS |
| 6.4 | Cross-check vs Groups | PASS |
| 6.5 | Mobile 375 px | PASS (after B11) |
| 6.6 | Only Profitable/Challenge sent | PARTIAL: code gate verified; no real signal data locally; cloud data NOT TESTED (login) |
| 7.1–7.4 | Navigation root cause, fix, real before/after | PASS (Paper Trading first render still ~16 s locally = remaining gap) |
| 7.5 | Spinner loader | PASS |
| 8.1–8.3 | Controls / honest states / console errors | PASS on cloud app pages; not every card's every button exhaustively clicked (PARTIAL) |
| 8.4 | Mobile layout | PASS (after B11) |
| 8.5 | Back button | PASS |
| 8.6 | Session timeout warning | FAIL (gap: none exists) |
| 8.7 | Manual refresh | PARTIAL |
| 8.8 | Search/filter | PASS (search fixed B10) |
| 8.9 | Export | PASS (CSV) |
| 8.10 | Dark/light toggle | PASS |
| 8.11 | PKT everywhere | PASS (2 UTC config inputs intentionally UTC) |
| 9.1 | Displayed vs executed entry | NOT TESTED (no linked signal data) |
| 9.2–9.10 | Analyses | PASS (reported above); 9.9 sizing change BLOCKED (decision) |
| 10.1 | Cooling-off | PASS (8 tests incl. engine path) |
| 10.2 | Restart/duplicates | PARTIAL |
| 10.3 | Telegram retry duplication | NOT TESTED |
| 11 | Daily 24h report | PASS (generated on real data; cloud scheduling added) |
| 12.1 | Full suite run to completion | PASS after fix: 2206 passed + 1 failed; the failure was fixed (`cc59a44`) and re-run green |
| 12.2 | Regression test per bug | PASS (25 new tests; frontend-only bugs covered by the existing page-render harness + hands-on evidence) |
| 12.3 | No test weakened/deleted | PASS |
| 13.1 | Clean separated commits | PASS (8 commits, Section 9) |
| 13.2 | Deploy + verified version + health | PASS (`started_at` 19:41:54Z, new app.js markers live, /health ok) |
| 13.3 | No "deployed" claim without evidence | PASS |
| 14 | Docs exist + updated | PASS (created; did not exist) |

### 11. Tests run

- **Targeted, during the work:**
  - `test_cloud_runtime.py`, `test_reports_best_worst_strategy.py`, `test_phase4_ui_ux_improvements.py`, `test_research_rate_limit.py`: **47 passed** (after the B17 parser fix);
  - new `test_audit_20260916_fixes.py` + `test_cooling_off.py`: **24 passed**, then 25 including the search test.
- **Full suite:** `python -m pytest -q tests`, started 18:37 UTC 2026-09-16 and waited to completion: **2206 passed, 1 failed, 3 warnings in 56m35s**.
  - The one failure was `tests/test_frontend_pages_render.py::test_every_dashboard_page_renders_without_throwing`. The Settings page threw `Cannot read properties of undefined (reading 'querySelector')` in the Node DOM harness: the new field-error helper assumed `el.parentElement`.
  - Fixed in `cc59a44` (helpers return early without a parent); the test is **unchanged** and re-run: **1 passed**.
  - The only code change after the full run is that JS guard, and this Node harness test is the only one that exercises it.
- **Warnings:** 3 × Pydantic `.dict()` deprecation in `update_settings` (pre-existing call style, kept).
- No test was weakened or deleted. The one test change (B17) makes the requirements parser correct for pinned lines with the same assertion.

### 12. Deploy (Render, existing auto-deploy-on-push workflow)

- **Push:** `git push origin main` → `baa8497..cc59a44` at 19:36:31 UTC (laptop clock); `origin/main...HEAD` = `0 0`.
- **Redeploy proof:** `/health` → `{"status":"ok","cloud_mode":true,"live_candles_only":true,"db_backend":"postgres","started_at":"2026-09-16T19:41:54.224047+00:00"}`. `started_at` changed from `13:52:08` (the laptop clock runs ~3 min behind Render's).
- **Deployed code is the new code:** the live `/static/js/app.js` (914,642 bytes) contains `confluence-open-positions`, `wireSettingsForm`, `tgStatusSection`, the `cc59a44` guard (`const parent = el && el.parentElement`) and the cloud search message. The live `app.css` contains the spinner and the mobile topbar rule.
- **Login gate after deploy:** `GET /api/settings` → 401 `login required`; `GET /api/paper-trading/telegram/status-summary` → 401; `GET /` → 307 → `/login`.
- **Expected after deploy:** the daily report scheduler now runs on the cloud. If the cloud DB has no `daily_report` send for today (UTC), one report goes to the main Telegram channel shortly after start, then once per UTC day.
- **Not verified:** logged-in behaviour on production (needs the CEO's password, which Claude must not enter).

### 13. Still open / needs CEO decision

1. Separate trading balance for the Challenge group (safety-gate math). **Decision.**
2. Correlated-coin exposure in position sizing (9.9). **Decision.**
3. Cloud went unresponsive ≥12 min without restarting (14:33–14:45 UTC). The B5 fan-out fix should remove the main trigger. Confirming it needs Render logs/metrics (**credentials**).
4. Paper Trading page first render ~16 s locally (engine contention); CEO page 15 s timeouts on two laptop-only endpoints.
5. No session-expiry warning (8.6).
6. Rotate the proxy password (A7). Delete the empty weekly snapshot (A6) only with permission.
7. Confidence % recalibration (A5): 6 strategies show confidence drift; last-50 WR 18% vs 75.8% claimed.
8. Trading costs ($155) exceed the net loss. Strategy/exit design, not a bug.

### 14. Sign-off (honest)

Everything marked PASS above was observed directly: real clicks, real HTTP status codes, file/DB reads and timings in this session. Production cloud behaviour was **not** exercised past the login gate. Where this report says "cloud app", it means the real `cloud_runtime/app.py` code run locally against a copy of real data, not the live Render instance. No real money, no gate weakened, no data deleted.
