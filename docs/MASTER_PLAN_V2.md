# SINDHU — MASTER PLAN V2 (Leftovers + 3D Login + Full Website Redesign)

> Owner: Sindhu · Written: 2026-11-06 · Executor: Claude Code (owner's laptop)
> Place this file at `docs/MASTER_PLAN_V2.md`.
> Start command: **"Read docs/MASTER_PLAN_V2.md fully, then start (or resume) exactly as its Section 1 says."**
> Predecessor: `docs/MASTER_PLAN.md` (V1, finished 37/44, report `docs/MASTER_PLAN_FINAL_REPORT.md`).

---

## 0. What this plan does

1. **Finish V1's unfinished work** (P5, P9, P11, P26, P27, P29, P34, P35, P46, U5–U10) and fix the risks found in the V1 review (position cap, memory headroom, unverified DB-latency claim, short soak).
2. **Rebuild the login page** to a professional, hand-crafted look with a **live 3D scene** that is light on the server and safe.
3. **Redesign the whole website** (every page) with one coherent design system, so it looks designed by a careful human product designer, not generated.
4. Everything is **resumable** (Section 1) and ends with a report that lists every point by ID and name.

**Why the V1 design did not look different (context for Claude Code):** V1 Part C was only partial: tokens, banner, new Home and the 5-section menu were done; tables (U5), charts (U8), Settings (U10) and all old pages were not reworked, and the old pages are still reachable below the new menu. Browsers may also be showing cached old CSS/JS because assets are not fingerprinted. V2 fixes both (DS3 cache-busting + PG steps).

---

## 1. RESUME PROTOCOL (read first, every time)

- State file: `docs/MASTER_PLAN_V2_STATE.md` (create on first run; do not edit V1's state file except to read it).
- Format: header (`plan_version: 2`, `started_at`, `last_update`, `current_step`, `next_action`, `background_jobs`) + table `| step | status TODO/IN_PROGRESS/DONE/BLOCKED/SKIPPED | commit | evidence | notes |`.
- Before a step: mark `IN_PROGRESS` and save. After: verify, mark `DONE` with commit hash + evidence, then `git commit` (code + state together). One step ≥ one commit.
- Every step is **idempotent** (safe to run twice).
- **On resume** (new session, laptop restart, limit hit, crash): read this plan + state + `git log -15` + `git status`. `DONE` steps are never redone. For the `IN_PROGRESS` step: finish it if the uncommitted changes are coherent; otherwise `git stash push -m "resume-<step>-<UTC>"` and redo only that step. Restart stale background jobs from their markers (`D:\sindhu_runtime\bt_jobs\<job>\*.done`, `heartbeat.txt`). Print `RESUMED at step <id> — <n>/<N> done`.
- Never restart from zero unless the owner writes "restart plan V2 from zero".
- Owner-only blockers → mark `BLOCKED`, add exact Hinglish steps to `docs/OWNER_TODO.md`, **continue with the next step**.

**Progress line in EVERY message:**
```
[PROGRESS xx% | steps n/N done | now: <step id + name> | status: OK/WARN/BLOCKED | elapsed: hh:mm | bg: <jobs> | blockers: <none/list>]
```
xx% = (DONE + SKIPPED) / N.

---

## 2. GLOBAL RULES (unchanged from V1, plus design rules)

1. Paper trading only. No real orders, no trade-permission keys.
2. Safety gates are never weakened (Wilson 25, Evolution 100, confluence, drawdown breaker, freshness 15 min / 0.5% / 60 s, kill-switch, risk manager, same-coin cap 5, Telegram Profitable+Challenge-only, public signals OFF unless `SINDHU_PUBLIC_SIGNALS=1`). New limits may only add safety.
3. Evidence for every claim; write **NOT VERIFIED** when not verified.
4. Candles never in Postgres. Secrets never printed, logged, committed or screenshotted.
5. Render env vars: only the owner changes them, one at a time (each change restarts the service). Claude Code writes the exact steps in OWNER_TODO.
6. Deploy only at gates (Section 7), full test suite + CI green, then watch `/health` (GET+HEAD) and logs 10 min, record memory.
7. **Point P7 stays EXCLUDED** (1m/5m strategies stay on Cloud).
8. **Do not move the Cloud service to another region/new service** in this plan (owner has not decided; a new service changes the URL, pinger, Telegram polling and can conflict with the running bot). Only measure (R5).
9. **Never lock the owner out**: every login change must keep the existing account login and the env login (`owner` + `DASHBOARD_PASSWORD`) working; tested before each deploy (LG5).
10. **Server load must not grow because of design work**: all visuals render in the browser; the server only serves static, fingerprinted, compressed files and cached JSON. Server memory may not rise more than 5 MB from UI work.
11. Final summary in **Hinglish bullets** + full point table (Section 8).

---

## 3. DESIGN DIRECTION (the "human-made" brief)

**Concept: "Trading desk, not a template."** Calm, dense, precise — like a professional terminal crossed with a well-edited report. Confidence comes from typography, alignment and restraint, not effects.

**Identity**
- Base: deep graphite/ink (dark default) and warm paper white (light theme). Neutral grey scale with 9 steps.
- One brand accent (choose one: warm amber or teal; document the choice and the reason). Green = profit only, red = loss/danger only, amber = warning only. Never use green/red decoratively.
- Type: **Inter** (UI) + **JetBrains Mono** or **IBM Plex Mono** (numbers, prices, IDs) with tabular digits. Self-host fonts (woff2, subset Latin), `font-display: swap`. Clear type scale (12/13/14/16/20/24/32).
- Grid: 4/8 px spacing, 12-column layout on desktop, consistent radii (6 px controls, 10 px cards), at most 2 shadow levels.
- Icons: one set only (Lucide, vendored SVG sprite). No emoji in UI.
- Motion: 150–250 ms, ease-out, purposeful (state change, reveal). Respect `prefers-reduced-motion` everywhere.

**Anti-"AI look" checklist (every page must pass; record pass/fail per page):**
- No purple→blue gradients, no glassmorphism panels everywhere, no neon glow, no rainbow charts.
- No generic marketing copy ("Unlock the power of…", "Welcome back, trader!"). Copy is short, specific, Hinglish/English as today.
- Not everything centered; real hierarchy with left-aligned content and asymmetric layouts where useful.
- No random colors, mixed icon sets, inconsistent radii, or more than 2 font families.
- Numbers right-aligned with tabular digits; units always shown ($, %, UTC).
- "Squint test": the most important thing on each page is visible first.

**Quality bars**
- WCAG AA contrast, visible keyboard focus, labels on every input, works with screen reader basics.
- Mobile-first: 360–430 px phones without horizontal scroll, touch targets ≥ 44 px; desktop 1280–1920 px uses space well.
- Performance budgets: app pages ≤ 150 KB JS gzip each (shared vendor chunk counted once); login 3D bundle ≤ 300 KB gzip **lazy-loaded after the form is usable**; LCP < 2.0 s on a mid phone profile; CLS < 0.05.

---

## 4. KNOWN FACTS

- Cloud: Render free, `Sindhu-cloud--1` (`srv-dabhrd8jo6nc739e08k0`), Oregon, `https://sindhu-cloud-1.onrender.com`, live commit `3eabeac` (V1 D3). Neon Postgres in Ohio (us-east-2).
- After V1: 5 complete 50-coin scans in a row, memory 428–435 MB (guard 450, limit 512), `/health` 0.70 s, 0 Neon error lines in the measured hour. One instance, ~4 h of data only.
- Login today: Cloud first-account setup needs `DASHBOARD_PASSWORD`; env login user `owner`; an earlier account still works. The owner currently **does not remember** the earlier account's username/password.
- MAIN_WALLET live since 2026-11-05 23:20:33 UTC; position cap 25%, max 4 positions, risk 1%, fee 0.1% + slippage 0.05%, min $5, daily loss limit −5%.
- Part B: Donchian 1d and TSMOM 1d both **FRAGILE** (fail FDR over 44 tests). Not in the wallet.
- Pinger: UptimeRobot Keyword monitor on `/health`, keyword `ok`, every 5 min.

---

## 5. POINT REGISTRY (IDs used everywhere)

**V1 leftovers**
| ID | Name |
|---|---|
| P5 | No scanner stalls (CoinGecko top-coins deadline) |
| P9 | Settings 50-cycle test on Postgres |
| P11 | Memory headroom (target ≤ 400 MB steady) |
| P26 | WebSocket 1m feed (local, flag OFF on Cloud) |
| P27 | Fetch budget: max K full refetches per scan |
| P29 | Log lines per hour measured and reduced |
| P34 | Full trade journal view on Trades page |
| P35 | Dashboard password / login done properly |
| P46 | UI/UX redesign completed |
| U5 | Professional tables |
| U6 | Text status badges everywhere |
| U7 | Loading states everywhere |
| U8 | Charts |
| U9 | Human empty/error states everywhere |
| U10 | Settings page regrouped |

**Review fixes (new)**
| ID | Name |
|---|---|
| N1 | Position cap 25% → 15% (stricter) |
| N2 | DB round-trip share of scan time measured (verify or reject the Ohio claim) |
| N3 | 48-hour soak monitor + report |
| N4 | Asset fingerprinting + cache headers (designs actually show up) |
| N5 | Owner login recovery guide (no lockout) |

**Login page (new)**
| ID | Name |
|---|---|
| L1 | Hand-crafted login layout and copy |
| L2 | Live 3D market scene |
| L3 | Public, safe, cached data for the scene |
| L4 | Fallbacks: no WebGL, reduced motion, low-end devices, hidden tab |
| L5 | Login security hardening |
| L6 | Login UX details (password managers, show password, caps lock, errors) |
| L7 | Optional TOTP two-factor (off by default) |
| L8 | Login tests + no-lockout guarantee |

**Website redesign (new)**
| ID | Name |
|---|---|
| W1 | Design system v2 (tokens, type, icons, motion) |
| W2 | Component library |
| W3 | App shell: sidebar, bottom tabs, banner, theme toggle |
| W4 | Home v2 (wallet, equity curve, drawdown, events) |
| W5 | Trades page (positions + full journal) |
| W6 | Strategies page (wallet + research books, badges, auto-pause) |
| W7 | Backtests page (results, charts, verdict explanations) |
| W8 | Settings page v2 |
| W9 | System page (health, scans, data freshness, jobs) |
| W10 | Legacy pages migrated; nothing lost (feature map) |
| W11 | 404 / error / offline pages |
| W12 | Command palette (Ctrl/⌘+K) and keyboard shortcuts |
| W13 | Visual QA: screenshots, anti-AI checklist, accessibility, performance |

---

## 6. STEPS (N = 36)

Order: Phase 0 → R (leftovers/fixes) → DS (design system) → LG (login) → PG (pages) → X (final). Priority tiers in Section 6.9.

### 6.1 Phase 0 — Preflight (3)

**F1. Close V1 cleanly.** Read V1 state; if any V1 step is still IN_PROGRESS, finish or revert it. Clean `git status`. Create V2 state with all 36 steps TODO.

**F2. Baseline.** Record in `docs/MASTER_PLAN_V2_BASELINE.md`: Cloud memory min/avg/max, scan time cold/warm, errors/hour, log lines/hour (P29: count it this time), `/health` latency; for every page: Playwright screenshots at 390×844 and 1440×900 (`docs/ui/v2/before/`), JS/CSS bytes (gzip), number of requests, LCP/CLS (Lighthouse CLI if installable, otherwise Playwright + PerformanceObserver; say which).

**F3. Route and feature map (W10).** List every route/page/button/form/API the dashboard has today in `docs/ui/FEATURE_MAP.md`: `old location → new location (W4–W9) → status`. Rule: **no feature may disappear**. Anything not placed in the new sections goes to a clearly labeled "More / Legacy" area until migrated.

### 6.2 Part R — V1 leftovers and review fixes (10)

**R1. P5 — CoinGecko deadline.** Connect + read timeout and an overall deadline (e.g. 20 s) on the top-coins call; on timeout use the last good list (cached on disk with timestamp) and log once. Test with an injected slow server.

**R2. P27 — Full-refetch budget.** Counter: max K (default 3) full refetches per scan; the rest queued for later scans; visible in `/health/details` as `refetch_queue`. Tests.

**R3. P11 — Memory headroom.** Profile (tracemalloc + RSS sampling during a full scan). Target ≤ 400 MB steady, never > 450 MB. Typical wins: drop duplicate DataFrames, use float32 arrays for cached candles, cap caches per timeframe by max lookback, free backtest objects on Cloud, lazy-import heavy modules not needed on Cloud. Before/after table.

**R4. N1 — Position cap 15%.** Default per-position cap 25% → **15%** of equity (stricter). Config validation allows 5–25%. Record the change with UTC time in `docs/FORWARD_TEST_LOG.md`. Tests updated deliberately (note it in the report).

**R5. N2 — Verify the DB-latency claim.** Per-stage timing per scan (already partly there): count DB round trips per scan, measure p50/p95 latency of a trivial `SELECT 1` from the Cloud instance to Neon, multiply out. Write `docs/DB_LATENCY_FINDINGS.md`: share of warm scan time spent in DB, with numbers. Then list the cheapest fixes that do **not** move regions (batching writes, one transaction per scan, caching reads, fewer round trips) and implement the safe ones. Conclusion on the Ohio idea: VERIFIED / NOT SUPPORTED, with numbers. No region move.

**R6. P29 — Log lines/hour.** Measure total lines/hour on Cloud (Render logs over ≥ 1 h) before/after; aggregate remaining repetitive info lines. Target ≥ 60% fewer than F2 without losing any error.

**R7. P9 — Postgres settings test.** Run the existing 50-cycle settings test against a **throwaway Postgres**: preferred a Neon **branch** of the project (owner creates it in the Neon console and puts its URL only in the local, git-ignored `.env` as `TEST_DATABASE_URL`); alternative local Postgres (Docker or portable) if installed. Never run it against the production database. If neither exists → BLOCKED with Hinglish owner steps. Update `docs/SETTINGS_TEST_REPORT.md`.

**R8. P26 — WebSocket 1m feed (local first).** Implement as designed in V1 A3 behind `SINDHU_WS_CANDLES` (default **OFF** on Cloud). Run locally for ≥ 30 min: compare WS cache vs REST for a sample window (must match), reconnect test, memory impact. Cloud enabling = owner decision in OWNER_DECISIONS with the measured numbers.

**R9. N3 — 48-hour soak monitor.** Script `ops/soak/soak_monitor.py`: every 10 min fetch `/health` and `/health/details` (public, no secrets), append to `D:\sindhu_runtime\soak\soak.csv` (time, up, latency, memory if exposed, scans completed, stale coins, errors). Windows task to run it for 48 h (owner installs; also runnable manually). `ops/soak/soak_report.py` builds `docs/SOAK_REPORT.md` (uptime %, worst latency, memory max, restarts detected). Start a manual run now in the background so data exists by the end of this plan.

**R10. N5 + P35 — Login recovery (no lockout).** Document in `docs/OWNER_TODO.md` and the one-pager (Hinglish): how to log in today (`owner` + `DASHBOARD_PASSWORD` set on Render), how to set/reset it (one env change, service restarts, wait for `/health` ok), and how the earlier account can be reset: add a local admin command `python -m tools.reset_dashboard_user --list` (shows usernames only) and `--reset <username>` (prompts for a new password, hashes it, writes it) that works against the local DB and, when the owner explicitly passes `--cloud` with `DATABASE_URL` from their local `.env`, against the Cloud DB. Never print passwords or hashes. Tests on SQLite.

### 6.3 Part DS — Design system v2 (3)

**DS1. W1 — Tokens, type, icons, motion.** Implement Section 3 as `static/css/tokens.css` v2 (dark + light, CSS variables), self-hosted fonts, Lucide SVG sprite, motion tokens, `prefers-reduced-motion` handling. Write `docs/ui/DESIGN_SYSTEM.md` (what each token is for, do/don't examples, the accent choice and why).

**DS2. W2 — Component library.** Buttons (primary/secondary/ghost/danger, sizes, loading), inputs (text, number with unit, select, toggle, segmented), form field with help + error, cards, stat card, badges (ROBUST/FRAGILE/FAILED/INSUFFICIENT/PAPER/RESEARCH/PAUSED/Data purana/LIVE), tables (U5: sticky header, sort, filter, pagination 20, tabular digits, right-aligned numbers, density toggle, CSV export, empty state), tabs, modal (in-page, focus-trapped), toast, tooltip, skeleton (U7), empty/error blocks (U9), chart wrapper (U8). One vendored, pinned, lightweight chart library (e.g. uPlot or TradingView Lightweight Charts; respect its license and attribution requirements; record version + SHA-256). A static `/ui-kit` page (behind login) shows every component in both themes.

**DS3. N4 — Asset pipeline and caching.** Fingerprinted filenames (content hash) for CSS/JS/fonts, `Cache-Control: public, max-age=31536000, immutable` for fingerprinted assets, `no-cache` for HTML, gzip (and brotli if available) pre-compressed at build, one shared vendor chunk. No CDN at runtime. Verify on Cloud: second load transfers only HTML + JSON. Add a visible build/version tag in the footer so the owner can see a new design is live.

### 6.4 Part LG — Login page (6)

**LG1. L1 + L6 — Layout and UX.**
- Desktop: asymmetric split — left 40%: brand mark "SINDHU", one-line purpose ("Paper-trading research desk"), the login form; right 60%: the live 3D scene. Phone: scene as a calm header band (or static poster on low-end), form below; no scroll needed on a 390×844 screen.
- Small, real details that make it feel built by a person: UTC clock, "Paper trading — real paisa nahi" note, build tag, "Market data: BTC/USDT 15m, updated N min ago".
- Form: username + password with correct `autocomplete` (`username`, `current-password`), show/hide password, Caps Lock hint, Enter submits, clear inline error ("Username ya password galat hai") that never reveals which one was wrong, disabled + spinner while submitting, focus on first field, "Password bhool gaye?" opens an in-page panel explaining the owner reset (R10).
- Copy is short and specific; no marketing phrases.

**LG2. L2 + L3 — Live 3D scene ("Market terrain").**
- Three.js vendored locally (exact pinned version, SHA-256 recorded), loaded **after** the form is interactive (dynamic import on idle).
- Scene: a field of instanced 3D candlesticks (InstancedMesh, ≤ 300 instances) forming a slow, flowing ribbon built from the last 96 BTC/USDT 15m candles; muted profit/loss tones, the brand accent as a single rim light, soft fog, slow camera drift, gentle parallax with the pointer (desktop only). New candle → a subtle rise animation. Feels alive, never busy.
- Data: new public endpoint `GET /api/public/login-scene` returning **only** normalized OHLC shape values (0–1) + the last close time, from candles the engine already caches (no extra exchange calls), cached 5 min server-side, ≤ 4 KB JSON, no wallet/strategy/account data. If no fresh data: a deterministic generated series and the label "Demo data".
- Must not affect server: zero server rendering, no extra DB queries (served from in-memory cache).

**LG3. L4 — Fallbacks and performance.**
- No WebGL → static poster image (pre-rendered from the same scene at build time, WebP, ≤ 80 KB).
- `prefers-reduced-motion` → static poster, no animation.
- Low-end detection (`navigator.hardwareConcurrency ≤ 4` or `deviceMemory ≤ 4` or measured frame time > 33 ms for 2 s) → fewer instances, 30 fps cap, or poster.
- Pause rendering when the tab is hidden or the scene is off-screen; stop after login.
- Budgets: 3D chunk ≤ 300 KB gzip; form interactive < 1.0 s on mid phone; LCP < 2.0 s; GPU memory released on navigation.

**LG4. L5 — Security hardening.**
- CSRF token on the login form; session cookie `HttpOnly`, `Secure` (Cloud), `SameSite=Lax`; session rotation on login; idle timeout (e.g. 12 h) and logout button everywhere.
- Rate limit (existing 5/min/IP) + exponential backoff per username; generic errors; constant-time compare; no user enumeration.
- Security headers on all HTML: Content-Security-Policy (`default-src 'self'`; no inline scripts; `img-src 'self' data:`), `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, `frame-ancestors 'none'`.
- Login attempts logged without passwords (time, IP hash, result). Write `docs/SECURITY_REVIEW.md` login section.

**LG5. L8 — Tests and no-lockout guarantee.** Tests: env login (`owner` + `DASHBOARD_PASSWORD`) works; existing DB account works; wrong password → generic error; rate limit triggers; CSRF missing → rejected; `/health` + `/health/details` + `/api/public/login-scene` stay public; all other routes require login. Playwright: login page at both sizes, with WebGL on/off and reduced motion on/off, no console errors. Before deploy gate G2: run the full login suite locally against SQLite **and** the Postgres test DB (if R7 available).

**LG6. L7 — Optional TOTP 2FA (Tier 3).** Off by default. If enabled by the owner from Settings: QR setup, 6-digit code step after password, 10 one-time recovery codes (shown once), works with Google Authenticator/Aegis. Tests. Owner guide in Hinglish. Never forced; never enabled automatically.

### 6.5 Part PG — Pages (11)

All pages use the shell (PG1), the components (DS2), real loading/empty/error states, and pass the anti-AI checklist.

**PG1. W3 — App shell.** Desktop: left sidebar (Home, Trades, Strategies, Backtests, Settings, System; "More/Legacy" at the bottom), collapsible. Phone: bottom tab bar (5 items) + "More". Top banner: "PAPER TRADING — real paisa nahi", kill-switch state + button (existing), data-freshness dot, theme toggle (dark/light, remembered), user menu with logout. Breadcrumb/page title consistent.

**PG2. W4 — Home v2.** 4 stat cards (wallet equity, today P&L, open positions, system health) + **equity curve** and **drawdown** chart for MAIN_WALLET (U8), last 10 wallet events, "next scan in" countdown, stale-coin count. Data from the cached `/api/summary`; charts lazy-load.

**PG3. W5 + P34 — Trades.** Tabs: Open positions (live P&L, stop/target, age) · Closed trades · **Journal** (every wallet decision with all gates, values, data sources, reasons; filter by strategy/coin/decision; row expands to full detail) · Rejected (why). Tables per DS2, CSV export.

**PG4. W6 — Strategies.** Cards/table with validation badge, wallet status (eligible/paused + reason, manual un-pause with confirm), research-book stats (trades, PF, drawdown), timeframe, last signal. Research books clearly labeled "Research — not the wallet". Part B strategies shown with FRAGILE badge and a one-line why.

**PG5. W7 — Backtests.** Results table (filters by verdict/timeframe), detail view with equity + drawdown charts, metrics grid, verdict explanation in plain words (what ROBUST/FRAGILE/FAILED mean), pre-registration link, data hash. Heavy data paginated and lazy.

**PG6. W8 + U10 — Settings v2.** Groups: Wallet & Risk · Signals · Data · Notifications · Security (password info, 2FA if LG6) · Appearance. Each setting: label, one-line help, unit, valid range, inline validation (same rules as server), "Saved ✓" toast, confirm modal for dangerous changes (kill-switch, wallet reset, public signals ON, risk increase). Shows which settings differ between local and Cloud (from PARITY data).

**PG7. W9 — System.** Cloud health (from `/health/details`), last scans with per-stage timing (R5), memory trend, data freshness per timeframe (counts; drill-down list), background jobs/tasks status, soak summary (R9), versions/commit, links to Render logs and UptimeRobot (plain links).

**PG8. W10 — Legacy migration.** Move or rebuild every remaining old page per `FEATURE_MAP.md`. Anything not rebuilt stays reachable under "More/Legacy" with the new shell and styles applied. Update the map with final status. Nothing removed without a mapping row.

**PG9. W11 — 404, error and offline pages.** Friendly, on-brand, with a way back; the 500 page never shows stack traces; "Cloud jaag raha hai (free plan), 1 minute" message when the API is slow on first load.

**PG10. W12 — Command palette and shortcuts (Tier 3).** Ctrl/⌘+K: jump to any page, coin or strategy; `g h` Home, `g t` Trades, `?` shows shortcuts. Fully keyboard-accessible; no effect on phone UI.

**PG11. W13 + U6/U7/U9 — Visual QA.** For every page: Playwright screenshots (390×844, 1440×900, dark + light) into `docs/ui/v2/after/`; no console errors; no horizontal scroll; anti-AI checklist table per page; axe-core (or equivalent) accessibility scan with zero serious issues; performance numbers vs budgets; before/after gallery in `docs/ui/v2/README.md`. Fix and re-run until all pages pass or list the exact remaining issues.

### 6.6 Final (3)

**X1. Deploy + verify.** Gates G1–G3 (Section 7). After G3: Cloud memory not higher than after R3 by more than 5 MB from UI work; `/health` latency ≤ F2; login page loads on Cloud with the 3D scene on desktop and the right fallback on phone.

**X2. Docs.** Update RUNBOOK, OWNER_ONE_PAGE_HINGLISH (new login, new pages, how to reset the password, how to read the System page), OWNER_TODO, SECURITY_REVIEW, PARITY, FORWARD_TEST_LOG, DESIGN_SYSTEM, FEATURE_MAP.

**X3. Final report** `docs/MASTER_PLAN_V2_FINAL_REPORT.md` (Section 8).

### 6.9 Priority tiers (if time/limits run out)
- **Tier 1:** F1–F3, R1, R3, R4, R10, DS1, DS2, DS3, LG1, LG2, LG3, LG4, LG5, PG1, PG2, PG6.
- **Tier 2:** R2, R5, R6, R7, R9, PG3, PG4, PG5, PG7, PG8, PG9, PG11.
- **Tier 3:** R8, LG6, PG10.
- Never deploy a half-finished step; revert it, mark BLOCKED, move on.

---

## 7. DEPLOY GATES

- **G1** after R1–R6 + R10 (stability, memory, cap, measurements). Watch 10 min + memory.
- **G2** after DS1–DS3 + LG1–LG5 (design system + login). Before G2: LG5 suite green. After G2: open the Cloud login page, verify generic error on a wrong password, verify `/health` public. Add to OWNER_TODO: "Login karke confirm karo ke andar ja sakte ho." If the owner reports a lockout → immediate rollback per `docs/ROLLBACK.md`.
- **G3** after PG1–PG11 (all pages) + any Tier 3 done.
- Every gate: tests + CI green → push → wait for Render live → `/health` GET+HEAD → logs 10 min → record memory/errors in the state file. Memory > 450 MB, crash loop or failing health → roll back immediately and mark BLOCKED.

---

## 8. FINAL REPORT FORMAT (mandatory)

### 8.1 Point table — every ID from Section 5, none skipped
| ID | Name | Status (✅ Done / ⚠️ Partial / ❌ Not done / ⛔ Blocked-owner / ➖ Excluded) | Evidence (test / log / commit / file / screenshot) | Owner action |
|---|---|---|---|---|

Include: P5, P9, P11, P26, P27, P29, P34, P35, P46, U5–U10, N1–N5, L1–L8, W1–W13, and P7 as ➖ Excluded.

### 8.2 Before vs after
Cloud: memory, scan times, errors/hour, log lines/hour, `/health` latency, DB share of scan time. UI per page: JS/CSS bytes, requests, LCP, CLS, accessibility issues, anti-AI checklist result. Links to before/after screenshots.

### 8.3 What changed for the owner (plain words)
New login, new pages, where each old feature went (short), new settings, password reset steps.

### 8.4 Owner TODO (Hinglish, numbered, one action per line)

### 8.5 Hinglish summary (bullets)
Kya hua, kya nahi hua aur kyun, design mein kya badla, server par asar (numbers), agla sabse zaroori kaam.

### 8.6 Honesty check
Anything NOT VERIFIED, tests changed on purpose, measurements estimated, sample sizes.

---

## 9. ONE-LINE COMMANDS FOR THE OWNER

- Start: `Read docs/MASTER_PLAN_V2.md fully, then start (or resume) exactly as its Section 1 says.`
- Resume: `Resume docs/MASTER_PLAN_V2.md from docs/MASTER_PLAN_V2_STATE.md. Do not restart from zero.`
- Status only: `Read docs/MASTER_PLAN_V2_STATE.md and give me the progress line + what is left, in Hinglish. Do not change anything.`
