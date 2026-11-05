# SINDHU — GRAND MASTER PLAN (Parts A + B + C)

> Owner: Sindhu · Written: 2026-11-06 · Executor: Claude Code (on owner's laptop)
> Place this file at `docs/MASTER_PLAN.md` in the SINDHU repo.
> Start command for Claude Code:
> **"Read docs/MASTER_PLAN.md fully, then start (or resume) exactly as its Section 1 says."**

---

## 0. What this plan does (one paragraph)

Three parts, one plan. **Part A** fixes the system from the inside: a single real-like $100 wallet, the server-load and stall bugs seen in Render logs, settings reliability (50-cycle test), safety, security and self-running operations. **Part B** pre-registers and backtests two new daily strategies (Donchian trend ensemble, volatility-scaled time-series momentum) on the LOCAL backtest pipeline, running in the background in parallel. **Part C** redesigns the dashboard UI/UX to a professional, light, mobile-first standard. Everything is resumable: if the laptop shuts down, limits are hit or Claude Code crashes, work continues from the last checkpoint, never from zero. The final report lists every point by ID and name with status and evidence.

---

## 1. RESUME PROTOCOL (read first, every time)

### 1.1 State file
- State lives in `docs/MASTER_PLAN_STATE.md` (create it on first run). Do **not** reuse `PROGRESS_CHECKPOINT.md` for this plan; leave it as is.
- Format:

```
# MASTER_PLAN_STATE
plan_version: 1
started_at: <UTC>
last_update: <UTC>
current_step: <step id or NONE>
next_action: <one line>
background_jobs:
  - id: BT-DATA   status: RUNNING|DONE|FAILED  marker_dir: <path>  done: n/N
  - id: BT-RUN    status: ...
| step | status (TODO/IN_PROGRESS/DONE/BLOCKED/SKIPPED) | commit | evidence | notes |
```

### 1.2 Rules
1. **Before** starting a step: mark it `IN_PROGRESS`, save the file.
2. **After** finishing a step: run its verification, mark it `DONE` with commit hash + evidence (test name, log line, file path, screenshot), then `git commit` (code + state file together). One step = at least one commit.
3. Every step must be **idempotent**: running it twice must not break anything or duplicate data (check before create; migrations guarded; "if exists skip").
4. **On resume** (new session, after crash, after laptop restart):
   - Read this plan + `MASTER_PLAN_STATE.md` + `git log -15` + `git status`.
   - `DONE` steps are **never** redone.
   - For the step that is `IN_PROGRESS`: inspect uncommitted changes. If they are coherent, finish and verify. If unclear, `git stash` them (name: `resume-<step>-<UTC>`), and redo **only that step**.
   - Check background jobs (Section 1.3) and restart any that are not running, from their markers.
   - Print: `RESUMED at step <id> — <n>/<N> done — previous session ended at <UTC>`.
5. Never start from zero unless the owner literally writes "restart plan from zero".
6. If a step is blocked by something only the owner can do, mark `BLOCKED`, write the exact owner action in `docs/OWNER_TODO.md`, and **continue with the next step**. Do not wait.

### 1.3 Background jobs (resumable)
- Long jobs (data download, backtests) run as separate background processes with low priority, max workers = (CPU cores − 2), minimum 1.
- Each unit of work (one coin, one strategy×coin×parameter set) writes a result file + a `.done` marker into `D:\sindhu_runtime\bt_jobs\<job_id>\`. On restart the job skips units that have a `.done` marker and verifies the result file's hash.
- Job logs: `D:\sindhu_runtime\bt_jobs\<job_id>\job.log`. A `heartbeat.txt` is updated every 60 s.
- Claude Code checks heartbeats between steps. If stale > 5 min, it restarts the job from markers.

### 1.4 Progress line (mandatory in EVERY message)
```
[PROGRESS xx% | steps n/N done | now: <step id + short name> | status: OK/WARN/BLOCKED | elapsed: hh:mm | bg: BT-DATA n/N, BT-RUN n/N | blockers: <none or list>]
```
Percentage = DONE steps / total steps (SKIPPED counts as done, BLOCKED does not).

---

## 2. GLOBAL RULES (never break these)

1. **No real money. Paper trading only.** No real order endpoints, no API keys with trade permission.
2. **Safety gates are never weakened**: Wilson 25, Evolution 100, confluence, drawdown breaker, freshness (15 min / 0.5% / 60 s sweep), kill-switch, risk manager, same-coin cap 5, Telegram Profitable+Challenge-only. New limits may only **add** safety.
3. **Evidence for every claim**: tests, log lines, measurements, file paths. No "should work". If something was not verified, say "NOT VERIFIED".
4. **Candles never go into Postgres.** Backtest data stays in `D:\sindhu_data` (outside git).
5. **Secrets**: never print, log, commit or paste tokens, passwords or DB URLs. Redact in all output.
6. **Render**: changing an env var restarts the service, so change **one at a time**, and only the owner changes Render env unless the owner explicitly says otherwise. Claude Code writes the exact steps in `OWNER_TODO.md`.
7. **Deploy policy**: commit per step locally, push/deploy only at the deploy gates (Section 7) with all tests green and CI green. After every deploy watch `/health` + logs for 10 min and record memory and errors.
8. **Docs updated after every part** (RUNBOOK, PIPELINE, SECURITY_REVIEW, OWNER_TODO, OWNER_DECISIONS, PARITY, BACKTEST_RESULTS, etc. as relevant).
9. **Do not touch** Windows Smart App Control or system security settings.
10. **Point 7 is EXCLUDED by the owner**: 1m/5m strategies **stay on Cloud**. Do not move them to research-only. Solve their load with P3, P26, P27 instead.
11. **Final summary in Hinglish bullet points** + the full point table (Section 8).
12. If time runs short, follow the **priority tiers** in Section 6 — never leave the system in a broken half-state; finish the current step or revert it.

---

## 3. KNOWN FACTS (context)

- Repo deploy branch: `codex/trading-intelligence` (Render autoDeploy on commit). Live commit at plan time: `c035ca3`.
- Render service: `Sindhu-cloud--1`, id `srv-dabhrd8jo6nc739e08k0`, free plan, Oregon, URL `https://sindhu-cloud-1.onrender.com`, start `python -m uvicorn cloud_runtime.app:app`. No Render healthCheckPath set.
- Free plan: 512 MB RAM (hard guard 450 MB), ~0.15 CPU, sleeps after 15 min without inbound HTTP.
- Pinger: UptimeRobot **Keyword** monitor (GET) on `/health`, keyword `ok`, every 5 min. Old HTTP monitor sent `HEAD /health` → **405**.
- DB: Neon Postgres (pooler, us-east-2). Local: SQLite. Local app: `D:\sindhu_venv_stable`, supervisor, `127.0.0.1:8420` (LAN `192.168.1.111:8420`), `D:\sindhu_runtime\start_local.cmd`.
- Dataset: Binance 1m, 50 coins, 748 files, 24,587,700 rows, hashed, `D:\sindhu_data` (+ C: copy).
- Validation so far: 0 ROBUST, 1 FRAGILE (Ichimoku 1d), 36 FAILED, 5 INSUFFICIENT_DATA. Forward test started 2026-11-06; verdict not before 2027-01-05.
- 12 public signals were sent, all from FAILED strategies, none with disclaimer. Confidence AUC 0.463.
- **Render log evidence (2026-11-05 20:09–20:22 UTC):**
  - `[live-candles] slow download LTC/USDT 1m: 28806 rows, 97 pages, 49s, window 20 days` (and similar for ENA, TRX, ONDO, ARB, AAVE): the full 20-day 1m history is re-downloaded per coin. `REFETCH ... needs 20.0d, cache starts 3.0d ago` for 15m/1h.
  - `[exchange-retry] okx ... RateLimitExceeded 50011 Too Many Requests`.
  - `[paper-trading] scan shows no progress for 190s; engine thread is at ... engine.py line 412 in _prefetch_candles`.
  - Neon: `OperationalError ... timeout expired` and `SSL SYSCALL error: EOF detected` in telegram-commands poll, challenge-lifecycle sweep, Telegram hourly/retry sweeps.
  - `HEAD /health 405`, bot probes `HEAD /order 307`, `HEAD /contact 307`.
  - `[exchange-breaker] bybit OPEN for 900s: geo-block 403`.
  - After 20:22:29 UTC the log went silent (instance asleep or stuck).

---

## 4. POINT REGISTRY (use these IDs everywhere)

| ID | Name |
|---|---|
| P1 | Automatic public Telegram signals OFF by default |
| P2 | Single real-like $100 wallet + research books kept |
| P3 | Incremental candle fetch (no 20-day re-download) |
| P4 | Neon pool pre-ping + auto-reconnect |
| P5 | Scanner timeouts, no stalls |
| P6 | `/health` supports HEAD |
| P7 | ~~Cloud only 1h/4h/1d~~ — **EXCLUDED by owner** |
| P8 | Bybit fully disabled on Cloud |
| P9 | Settings 50-cycle test |
| P10 | Dashboard cache + light home page |
| P11 | Memory target ~350 MB |
| P12 | Local/Cloud parity |
| P13 | Disclaimer on every signal |
| P14 | Remove false "Strong 2/2" confidence |
| P15 | Private owner alerts (owner chat id) |
| P16 | Old Render services check + suspend (owner) |
| P17 | Secrets rotation guide, one at a time (owner) |
| P18 | Daily candle update, automatic (local) |
| P19 | Daily health report to owner chat |
| P20 | Weekly scorecard, automatic |
| P21 | Two new strategies backtest (= Part B) |
| P22 | Forward-test record kept safe |
| P23 | Weekly backup restore test |
| P24 | `OWNER_ONE_PAGE_HINGLISH.md` |
| P25 | Honest README / CV / LinkedIn story |
| S1 | OKX rate-limit handling |
| S2 | Bot probe paths return light 404 |
| P26 | WebSocket 1m candle feed |
| P27 | Fetch budget per scan |
| P28 | Candle age on dashboard |
| P29 | Log noise reduction |
| P30 | Daily loss limit −5% on wallet |
| P31 | Real fees, slippage, min notional |
| P32 | Duplicate entry guard |
| P33 | Strategy auto-pause |
| P34 | Trade journal |
| P35 | Dashboard password |
| P36 | Telegram commands owner-only |
| P37 | Kill-switch button on dashboard |
| P38 | Startup self-check + `/health/details` |
| P39 | Config validation at startup |
| P40 | Error alert dedup |
| P41 | Neon storage check + cleanup |
| P42 | Weekly Postgres local backup |
| P43 | Rollback guide |
| P44 | Local app autostart on Windows + sleep guide |
| P45 | Monthly trade CSV export |
| P46 | UI/UX professional redesign (= Part C) |
| U1–U10 | UI/UX sub-points (Part C) |

---

## 5. STEPS

Total steps: **N = 44** (Phase 0: 3, Part A: 26, Part B: 7, Part C: 6, Final: 2). Background jobs start at B1/B2 and run in parallel with Part A and C.

### PHASE 0 — Preflight

**F1. Confirm nothing else is running.** Check that the previous Final Master Prompt is finished (its final report exists). If it is still mid-way, finish its current step, write its report, then start this plan. Clean `git status` (commit or stash with a clear name). Create `docs/MASTER_PLAN_STATE.md` with all 44 steps as TODO.

**F2. Baseline measurements (before any change)** → `docs/MASTER_PLAN_BASELINE.md`:
scan duration (cold/warm), scans completed per hour, memory (min/avg/max), errors per hour by type (from Render logs, last 24 h), `/health` latency (10 samples), dashboard home load time + payload size + number of requests, number of DB queries per home-page load, 1m download volume per scan (rows/pages/seconds). Same metrics are measured again in X1.

**F3. Start Part B background jobs early.** Do B1 (pre-registration) and B2 (data download) now, so they run during Part A. Then continue with A1.

### PART A — System fix, $100 wallet, light server

**A1. P6 + S2 — Health and bot probes.**
- `/health` answers both GET and HEAD with 200, no DB access, < 50 ms in-process.
- Unknown paths (`/order`, `/contact`, `/wp-admin`, etc.) return a tiny 404 (no redirect, no template render, no DB).
- Tests: GET/HEAD `/health` 200; HEAD unknown path 404; `/health` works while the scanner is busy (existing deterministic load test).

**A2. P3 — Incremental candle fetch.**
- Keep a per-(coin, timeframe) in-memory/disk cache with `last_closed_ts`. Each scan fetches only candles after `last_closed_ts` (normally 1–2 pages), never the full 20-day window.
- Full refetch only when: cache empty, gap detected, or data hash mismatch, and then **at most K coins per scan** (see P27).
- Fix the `REFETCH needs 20.0d, cache starts 3.0d ago` loop: if the strategy needs 20 d but the cache has 3 d, backfill once in the background, then stay incremental.
- Freshness rules (15 min / 0.5% / 60 s) unchanged.
- Tests: second scan downloads ≤ 2 pages per coin per timeframe; gap triggers backfill; no lookahead (last candle must be closed).
- Measure: rows/pages/seconds per scan before vs after.

**A3. P26 — WebSocket 1m feed (shared cache).**
- One Binance (or the exchange actually reachable from Render) WebSocket connection with combined streams for 1m klines of all scanned coins, feeding the same cache as A2. REST becomes fallback only.
- Auto-reconnect with backoff, heartbeat check, gap-fill via REST after reconnect.
- Memory budget: cache only what strategies need (max lookback + margin), as compact arrays, not DataFrames per coin.
- Feature flag `SINDHU_WS_CANDLES` (default ON locally after tests; Cloud ON only at deploy gate D1 with owner OK in OWNER_TODO). If WS is unreachable from Render, it falls back to A2 cleanly and logs once.
- Tests: simulated disconnect → reconnect → gap filled; cache values equal REST values for a sample window.

**A4. P27 + S1 — Fetch budget and rate limits.**
- Per scan: max K full refetches (default 3), max parallel requests per exchange (default 2–3), token-bucket rate limiter per exchange respecting its documented weights.
- OKX `50011`: back off with jitter, reduce concurrency automatically for 10 min, log once per minute (not per request).
- Tests: rate limiter never exceeds configured rate in a burst test.

**A5. P5 — No scanner stalls.**
- Every network call has connect + read timeouts. `_prefetch_candles` futures use `wait(timeout=…)`; a coin that times out is **skipped for this scan** and marked stale, the scan continues.
- Watchdog: if no progress for 120 s, log the stuck stage once and cancel/skip it, not the whole engine.
- Per-stage timing (prefetch, indicators, strategy eval, gates, DB write, Telegram) logged once per scan in one line.
- Tests: injected slow exchange → scan finishes within budget and reports skipped coins.

**A6. P4 — Neon reliability.**
- SQLAlchemy/psycopg pool: `pool_pre_ping=True`, `pool_recycle` < Neon idle timeout (e.g. 240 s), small pool (size 2–3, overflow 2), connect timeout 10 s, TCP keepalives on.
- Retry once on `OperationalError` for idempotent reads; writes use transactions and retry only when safe.
- Background loops (telegram-commands poll, challenge sweep, hourly/retry sweeps) survive DB errors and back off (30 s → 5 min), logging once per error type per 10 min.
- Tests: simulated dropped connection → next query succeeds; loop keeps running.

**A7. P8 — Bybit off on Cloud.**
- When `cloud_mode=true`, Bybit is not instantiated at all (no breaker spam, no 403 calls). Any code path that read Bybit (confluence/regime) uses the position's own exchange. Local can still use Bybit if reachable.
- Tests: cloud-mode config creates no Bybit client.

**A8. P14 — Honest confidence.**
- If regime/confluence data is unavailable, the value is `UNKNOWN`, never "Strong". `UNKNOWN` follows the stricter path (withhold public send), not the looser one.
- Signal text never shows "Strong, 2/2" unless both inputs were really computed from fresh data. Add the inputs' sources + timestamps to the trade journal (P34).
- Tests: missing regime input → `UNKNOWN` + withheld.

**A9. P2 + P31 — Single real-like $100 wallet.**
- New wallet entity `MAIN_WALLET`: starting balance **$100.00**, one shared balance for all strategies, like a real human account.
- Rules: risk per trade ≤ 1% of equity (stop-distance based sizing), max 4 open positions, same-coin cap still applies, Binance min notional $5 (smaller → reject with reason), fee 0.1% per side + slippage 0.05% (configurable), no leverage, no shorting unless the strategy is spot-short-safe in paper (default: long-only for the wallet).
- Priority when several signals compete: only signals that passed **all** existing gates; then highest validation class (ROBUST > FRAGILE > others); ties → first come. Record rejected candidates with reason ("wallet full", "below min notional", "daily loss limit").
- **Research books stay** (one per strategy, as now) and are labeled "Research" everywhere. They keep feeding the learning statistics.
- Migration: archive current wallet/books state to `archive/<UTC>/` (DB export + JSON summary), create `MAIN_WALLET` once (idempotent), write the start time in `docs/FORWARD_TEST_LOG.md`.
- Dashboard home shows `MAIN_WALLET` as the main balance; combined research total is shown only on the Research page, clearly labeled.
- Tests: sizing math, min-notional reject, fee deduction, max-positions, reconciliation (wallet cash + open positions value = equity, to the cent).

**A10. P30 — Daily loss limit.**
- If `MAIN_WALLET` equity falls 5% below the day's start (UTC 00:00), no new entries for the rest of that UTC day; open positions keep their stops/targets. Owner alert (P15). Configurable but cannot be raised above 10% without editing config + a log line.
- Tests: crossing −5% blocks entries; next day resets.

**A11. P32 — Duplicate entry guard.**
- Same coin + same direction within 60 min (configurable) → no second entry in `MAIN_WALLET` (research books unaffected unless already guarded). Reason logged.
- Tests included.

**A12. P33 — Strategy auto-pause.**
- For `MAIN_WALLET`: after ≥ 20 closed paper trades, if a strategy's profit factor < 0.9 **or** its drawdown contribution > 3% of wallet, it is auto-paused for the wallet (research book continues). Owner alert. Un-pause is manual only.
- Tests with synthetic trade series.

**A13. P34 — Trade journal.**
- Every wallet decision (entry, exit, rejection) gets one row: time, strategy, coin, timeframe, side, price, size, fees, stop, target, every gate name + pass/fail + value, data sources + candle timestamps, reason text. Viewable on the Trades page and exportable (P45).

**A14. P1 + P13 — Public signals.**
- Code default for automatic public Telegram signals = **OFF** (Cloud and local). Paper trading continues.
- If the owner turns them ON later, every public message must include a disclaimer line: "Paper-trading research signal. Not financial advice. Past results do not predict future results." plus the strategy's validation class.
- Owner step in OWNER_TODO: confirm the Render env value matches (one env change).
- Tests: default config sends nothing public; when ON, disclaimer always present.

**A15. P15 + P36 + P40 — Owner channel and Telegram security.**
- Support `OWNER_CHAT_ID` (private chat). All owner alerts go there, never to public groups.
- Commands (`/status`, `/stop`, `/resume`, `/wallet`, `/health`) accepted **only** from `OWNER_CHAT_ID`; all others are ignored and logged once per hour.
- Alert dedup: same alert type at most once per hour, with a counter ("x12 in last hour").
- Owner step: how to get the private chat id (send `/start` to the bot, read id from a helper command or log), written in Hinglish in OWNER_TODO.

**A16. P35 + P37 — Dashboard password and kill-switch button.**
- Dashboard protected by a password (env `DASHBOARD_PASSWORD`, hashed compare, session cookie, HttpOnly, Secure on Cloud, SameSite=Lax, login rate limit 5/min/IP). **`/health` and `/health/details` stay public** (pinger needs them; `/health/details` shows no secrets).
- If `DASHBOARD_PASSWORD` is not set: local stays open on 127.0.0.1/LAN; Cloud shows a read-only page "Set DASHBOARD_PASSWORD" (no data) — and the owner step is in OWNER_TODO.
- Kill-switch button (big, red, with a confirm dialog that is an in-page modal, not a browser alert): stops all new entries immediately; shows state on every page; resume needs confirm too.
- Tests: protected routes 401/redirect without login; health public; kill-switch blocks entries.

**A17. P38 + P39 — Startup self-check and config validation.**
- On startup: validate config (types, ranges, required secrets present, wallet risk ≤ limits, freshness values sane). Invalid → clear error message, refuse to start trading (web still serves `/health` with `"trading":"disabled_config_error"`).
- Self-check: DB reachable, exchange reachable, Telegram token valid (no message sent), disk/cache dirs writable, clock skew < 2 s vs exchange time. Results on `/health/details` and on the dashboard System card.

**A18. P29 — Log noise.**
- Repeating info messages (slow download, refetch, retry) are aggregated into one summary line per scan. Errors stay individual but deduped (P40 logic). Target: ≥ 60% fewer log lines per hour vs baseline, with no lost error information.

**A19. P10 + P11 — Light dashboard API and memory.**
- Home page data from one cached summary endpoint (refreshed every 30–60 s in the background), not many DB queries per request. Heavy pages (backtests, history) lazy-loaded and paginated.
- Memory: profile with tracemalloc; remove per-coin DataFrame copies, cap caches, release backtest objects on Cloud. Target ~350 MB steady, never > 450 MB. Record before/after.

**A20. P28 — Candle age.**
- Per coin×timeframe: last candle close time and age. Stale (beyond freshness rule) → red badge "Data purana" on dashboard; included in `/health/details` as counts (fresh/stale), not per-coin lists.

**A21. P9 — Settings 50-cycle test.**
- Automated test suite: for every user-changeable setting: set valid value → save → read back → restart app (in-process restart in test) → read back → verify effect (e.g. risk change changes size). Also invalid values (negative, too big, wrong type, empty) must be rejected with a clear message and leave the old value.
- Run **50 cycles** with random valid/invalid sequences (fixed seed, recorded). Run on local SQLite and on a Postgres test DB (local Docker or a throwaway Neon branch if available; if not available, mark Postgres part BLOCKED with reason).
- Report table in `docs/SETTINGS_TEST_REPORT.md`: setting | cycles | pass | fail | notes. Any fail → fix → rerun all 50.

**A22. P12 — Parity.**
- Script compares effective config local vs Cloud (via `/health/details` config hash + a safe non-secret config summary). Resolve `auto_send_high_confidence_only` (True local / False Cloud): code default = True (stricter) everywhere; owner confirms Render env in OWNER_TODO.
- The seven flags (`SINDHU_RESEARCH_ONLY_TIMEFRAMES`, `SINDHU_BLOCK_OPPOSITE_SIGNAL`, `SINDHU_MAX_TARGET_STOP_RATIO`, `SINDHU_HIDE_CONFIDENCE`, `SINDHU_CANDLE_FINGERPRINT`, `SINDHU_GATE_USE_POSITION_EXCHANGE`, disclaimer flag): do not flip on Cloud. Document each in OWNER_DECISIONS with a one-line recommendation; note that `SINDHU_RESEARCH_ONLY_TIMEFRAMES` stays OFF because P7 is excluded. Update `docs/PARITY.md`.

**A23. P18 + P19 + P20 + P45 — Scheduled automation (local).**
- Windows Task Scheduler jobs (scripts in `D:\sindhu_runtime\tasks\`, each logs to its own file, each idempotent):
  - Daily 02:10 PKT: candle update for all 50 coins (append only, hashes updated, verify).
  - Daily 09:10 PKT: health report to owner chat: Cloud up %, scans/day, errors/day, memory max, wallet equity + day P&L, open positions, stale coins count.
  - Weekly Monday 10:10 PKT: weekly scorecard (`WEEKLY_SCORECARD.md` updated + short Telegram owner summary).
  - Monthly 1st 10:20 PKT: trade CSV export (wallet + research) to `D:\sindhu_runtime\exports\YYYY-MM\`.
- Provide `install_tasks.cmd` and `remove_tasks.cmd`. Owner runs install once (written in OWNER_TODO).

**A24. P41 + P42 + P23 — Storage and backups.**
- Neon: report DB size vs 0.5 GB free limit; warning at 70%; retention cleanup for old logs/telemetry tables (never trades or journal) with dry-run first.
- Weekly Postgres backup to `D:\sindhu_backups\pg\YYYY-WW\` (pg_dump, compressed, hash) + keep last 8.
- Weekly restore test into a local scratch DB: row counts match, wallet reconciliation passes. Result in `docs/BACKUP_LOG.md`. (Scheduled via A23 tooling.)

**A25. P44 + P43 + P22 — Local autostart, rollback, forward test.**
- Local app starts at Windows logon via Task Scheduler (supervisor), restarts on crash. Hinglish guide: laptop sleep settings (plugged-in: never sleep while SINDHU runs; lid close action), how to check it is running.
- `docs/ROLLBACK.md`: Render dashboard → Deploys → pick last good deploy → "Rollback"; and git way (`git revert`). Keep list of known-good commits with dates.
- `docs/FORWARD_TEST_LOG.md`: forward test since 2026-11-06, wallet start time, any config changes with timestamps (so results stay interpretable). Forward-test data is never deleted or reset.

**A26. P16 + P17 + P24 + P25 — Owner guides and honest story.**
- P25: `docs/PORTFOLIO_STORY.md` with an honest README section, 5 CV bullet points and a short LinkedIn post: what was built (architecture, gates, pipeline, $100 wallet, resumable backtests), what was learned (0 ROBUST so far, counting bug found and fixed, geo-block found), **no profit claims**. Update the repo README "About" section to match.
- OWNER_TODO (Hinglish, numbered, one action per line): check old Render services (`Sindhu-cloud-`, `Trading-best` ×3) for `TELEGRAM_BOT_TOKEN` → suspend them; secrets rotation one at a time (Telegram bot token via BotFather, Neon password, dashboard password) with "update Render env, wait for restart, check /health" after each.
- `docs/OWNER_ONE_PAGE_HINGLISH.md`: one page — "Claude ke bina SINDHU kaise chalao": daily 2-minute check, weekly check, what each alert means, what to do if Cloud is down, how to restart local app, how to rollback, how to use the kill-switch. Simple words.

### PART B — Two new strategies (P21, LOCAL backtest pipeline only)

All of Part B runs locally. Nothing is synced to Cloud unless the verdict is **ROBUST** and the owner approves in OWNER_DECISIONS — and even then paper only.

**B1. Pre-registration (before any result is seen).** Write `docs/BENCHMARK_PREREGISTRATION_V2.md` and commit it (record hash) **before** running B4. It fixes:

*Strategy 1 — Donchian Trend Ensemble (daily, long-only)*
- Universe: fixed list of the 20 most liquid coins in the dataset that have daily history; list frozen in the file. Survivorship bias is noted as a limitation.
- For each lookback L ∈ {20, 55, 100}: sub-signal = 1 when close > highest high of the previous L days; back to 0 when close < lowest low of the previous L/2 days. Position signal = average of the 3 sub-signals (0, ⅓, ⅔, 1).
- Sizing: per-coin weight = signal × min(1, target_vol / realized_vol_30d) / N_coins, target_vol = 2% daily (frozen).
- Execution: signal on daily close, trade at **next day open** (no lookahead). Daily rebalance with a 10% no-trade band.

*Strategy 2 — Volatility-scaled Time-Series Momentum (daily, long-only)*
- Same frozen universe.
- Signal: 28-day return > 0 → long, else flat. Rebalance weekly (Monday 00:00 UTC close → Monday open execution).
- Sizing: same vol scaling as Strategy 1.

*Common*
- Costs: 0.1% fee per side + 0.05% slippage per side. Starting capital $100 equivalent (results also in %).
- Periods: in-sample 2018-01-01 → 2023-12-31; out-of-sample 2024-01-01 → 2026-10-31 (no tuning on OOS); plus walk-forward (3-year train / 1-year test, rolling).
- Benchmarks: BTC buy-and-hold, equal-weight buy-and-hold of the universe.
- Robustness: parameter neighbours ±10% and ±20% (lookbacks, momentum window, target vol); bootstrap of trade returns (1,000 resamples); per-year results; correct trade counting (one entry = one trade, the fixed counting rule).
- Metrics: CAGR, Sharpe, Sortino, max drawdown, profit factor, trades, win rate, exposure %, t-stat, turnover, cost drag.
- Verdict rules = existing `BACKTEST_PROTOCOL.md` classes (ROBUST / FRAGILE / FAILED / INSUFFICIENT_DATA). A strategy is ROBUST only if OOS and walk-forward are positive after costs, it beats or matches the benchmark on risk-adjusted terms, and neighbours do not flip to loss.
- These are adaptations inspired by published trend-following research, not the papers' exact rules; published claims are not assumed true.

**B2. Data (background job `BT-DATA`).**
- Download **native** Binance spot daily klines (not resampled) from 2018-01-01 (or listing date) to the last closed day, for the frozen universe + BTC. Store in `D:\sindhu_data\daily\`, one file per coin, with SHA-256 hashes in a manifest. Resumable with `.done` markers.
- Quality checks (`docs/DATA_QUALITY.md` new section): gaps, duplicates, zero volume, OHLC sanity, timezone (UTC 00:00 open), last candle closed. Cross-check overlap with daily bars resampled from the existing 1m data; differences > 0.1% are listed.

**B3. Implementation.** Implement both strategies in the existing local backtest engine as plug-ins, plus unit tests: signal on known synthetic series, no lookahead (shifting future data does not change past signals), cost application, vol sizing math, weekly rebalance timing.

**B4. Run (background job `BT-RUN`).** In-sample, OOS, walk-forward, neighbours, bootstrap — each unit resumable with markers. Runs in parallel with Parts A/C at low priority.

**B5. Results.** `docs/BACKTEST_RESULTS.md` new section + `docs/STRATEGY_V2_REPORT.md`: tables, equity/drawdown charts (PNG), benchmark comparison, verdict per strategy with reasons, limitations (survivorship, short crypto history, regime dependence).

**B6. Pipeline integration (local).** Register both as research strategies in the local pipeline (import → backtest → gates). They appear on the Backtests page with their verdict. **No Cloud sync** unless ROBUST + owner approval (write the decision request in OWNER_DECISIONS).

**B7. How-to.** `docs/NEW_STRATEGY_HOWTO.md` (Hinglish + English): how the owner adds and tests a new strategy later without Claude, step by step, using this pipeline.

### PART C — UI/UX professional redesign (P46, U1–U10)

Keep the existing frontend stack (no heavy new framework unless already present). No external CDN that can break; bundle what is needed. Before/after screenshots with Playwright at phone 390×844 and laptop 1440×900 for every page, saved in `docs/ui/before/` and `docs/ui/after/`.

**C1. U1 — Design system.** One design-token file: colors (dark theme default + light theme; neutral greys; green only for profit, red only for loss/danger, amber for warning, one accent color), one font (Inter or system UI stack), type scale, spacing scale (4/8 px), radius, shadows (subtle). Remove gradients, glows, emoji clutter, random colors and mixed icon styles — one icon set. Contrast WCAG AA.

**C2. U2 + U3 + U4 — Layout and navigation.**
- Five sections only: **Home, Trades, Strategies, Backtests, Settings** (Research books inside Strategies).
- Laptop: left sidebar. Phone: bottom tab bar. Mobile-first: no horizontal page scroll, touch targets ≥ 44 px.
- Permanent top banner: **"PAPER TRADING — real paisa nahi"** + kill-switch state + data freshness dot.
- Home = 4 cards: MAIN_WALLET balance, today's P&L, open trades, system health (Cloud up, last scan, stale coins). Below: small equity curve + last 5 journal events.

**C3. U5 + U6 — Tables and status.**
- Tables: sticky header, sort, filter, 20 rows/page, numbers right-aligned with tabular digits, $ and % formatted consistently.
- Status badges always with text: ROBUST / FRAGILE / FAILED / INSUFFICIENT, PAPER, RESEARCH, PAUSED, "Data purana".

**C4. U7 + U8 — Loading and charts.**
- Skeleton placeholders, no blank screens or endless spinners. "Last updated 30 sec pehle". Partial data refresh (polling the cached summary every 30–60 s, paused when the tab is hidden), no full page reloads.
- One lightweight chart library; charts (wallet equity, drawdown) load only when visible.

**C5. U9 + U10 — Empty/error states and Settings page.**
- Human messages: "Abhi koi open trade nahi", "Exchange slow hai, data 5 min purana", "Cloud so raha hai, 1 min mein jaagega". No raw stack traces to the user.
- Settings: grouped (Wallet & Risk, Signals, Data, Notifications, Security), one-line explanation under each, validation inline, "Saved ✓" toast, confirm modal for dangerous actions (kill-switch, wallet reset, signals ON). Settings use the same validation as A17/A21.

**C6. UI verification.**
- Playwright: every page loads without console errors at both sizes; navigation works; login works; kill-switch modal works.
- Performance: home page payload and requests vs baseline (F2); target: home load < 1.5 s on local, ≥ 50% fewer requests, no request > 300 KB.
- Accessibility quick check (contrast, labels, keyboard focus).
- Add a before/after gallery to `docs/ui/README.md`.

### FINAL

**X1. Full verification + deploy.** All tests green, CI green. Deploy at gates (Section 7). Re-measure every F2 metric after 60 min of Cloud running → `docs/MASTER_PLAN_RESULTS.md` (before vs after table). Watch Render logs: no `HEAD /health 405`, no 20-day refetch loops, no scanner stall > 120 s, Neon errors recovered automatically. Check UptimeRobot monitor is Up.

**X2. Final report** (Section 8) + Hinglish summary + docs updated + state file shows all steps.

---

## 6. PRIORITY TIERS (if time or limits run out)

Work in step order, but if the session must stop early, the system must be safe at every commit. Importance order:

- **Tier 1 (must):** F1, F2, A1, A2, A5, A6, A7, A14, A9, A16, A17, A21.
- **Tier 2 (should):** A3, A4, A8, A10–A13, A15, A18–A20, A22, B1, B2, B3, B4.
- **Tier 3 (nice):** A23–A26, B5–B7, C1–C6.

Never deploy a half-finished step. If a step cannot be finished, revert it to the last good commit, mark it BLOCKED with the reason, and move on.

---

## 7. DEPLOY GATES

- **D1** after A1–A8 (load + stability fixes). Watch 10 min. Owner turns on `SINDHU_WS_CANDLES` on Render only after D1 is stable (OWNER_TODO).
- **D2** after A9–A22 (wallet, safety, security, settings). Before D2: owner must have set `DASHBOARD_PASSWORD` on Render, or the Cloud dashboard shows the "set password" page (acceptable).
- **D3** after Part C.
- Every gate: tests + CI green → push → wait for Render "live" → check `/health` (GET and HEAD) → watch logs 10 min → record memory, errors, scan time in the state file. If anything is worse than baseline in a dangerous way (memory > 450 MB, crash loop, health failing), roll back immediately (ROLLBACK.md) and mark the step BLOCKED.

---

## 8. FINAL REPORT FORMAT (mandatory)

### 8.1 Point table — every ID, nothing skipped
| ID | Name | Status (✅ Done / ⚠️ Partial / ❌ Not done / ⛔ Blocked-owner / ➖ Excluded) | Evidence (test / log / commit / file) | Owner action needed |
|---|---|---|---|---|
| P1 | Automatic public Telegram signals OFF by default | | | |
| … all of P1–P46, S1, S2, U1–U10 … | | | | |
| P7 | Cloud only 1h/4h/1d | ➖ Excluded by owner | — | — |

### 8.2 Before vs after metrics
Scan time cold/warm, scans/hour, memory min/avg/max, errors/hour by type, log lines/hour, `/health` latency, 1m download rows/pages per scan, home page load time/payload/requests.

### 8.3 Part B verdicts
Strategy | in-sample | OOS | walk-forward | neighbours | vs benchmark | verdict | why.

### 8.4 What changed for the owner
New pages, new buttons, new alerts, new scheduled tasks, new settings, in plain words.

### 8.5 Owner TODO (numbered, Hinglish, one action per line)
Render env changes one at a time, password, chat id, install tasks, old services, secrets rotation.

### 8.6 Hinglish summary (bullets)
- Kya hua, kya nahi hua, kyun.
- System ab kitna halka/tez hai (numbers).
- $100 wallet kaise kaam karta hai.
- Nayi strategies ka natija (imaandaar).
- Agla sabse zaroori kaam.

### 8.7 Honesty check
List anything claimed but not verified, any test skipped, any metric estimated instead of measured.

---

## 9. ONE-LINE COMMANDS FOR THE OWNER

- Start: `Read docs/MASTER_PLAN.md fully, then start (or resume) exactly as its Section 1 says.`
- Resume after laptop off / limit / crash: `Resume docs/MASTER_PLAN.md from docs/MASTER_PLAN_STATE.md. Do not restart from zero.`
- Status only: `Read docs/MASTER_PLAN_STATE.md and give me the progress line + what is left, in Hinglish. Do not change anything.`
