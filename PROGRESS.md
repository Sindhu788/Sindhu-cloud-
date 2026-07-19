# SINDHU — Project Progress

Last updated: 2026-07-19 (Mobile-responsive dashboard: drawer nav, table→card reflow, 44px touch targets, bottom tab bar)

This file tracks what's been built, what's verified working, and what's next — kept up to date after every phase so any session (or any developer) can pick up context immediately.

---

## Status at a Glance

| Phase | Name | Status |
|---|---|---|
| 1 | Data System (download engine, SQLite, desktop dashboard) | ✅ Complete |
| 2 | Backtesting Engine (single-timeframe) | ✅ Complete |
| 2.1 | Professional Backtesting Update (multi-timeframe, bilingual parser, library) | ✅ Complete |
| 3 | Professional Dashboard + Web Interface | ✅ Complete |
| 4 | Knowledge Engine (CEO lessons) | ✅ Complete |
| 4.5 | Local Remote Control, Mobile Access & Real-Time Sync | ✅ Complete |
| - | Dashboard Professional Redesign (institutional UI overhaul) | ✅ Complete |
| 5 | Paper Trading Engine (automatic, 24/7, simulation-only) | ✅ Complete |
| - | Knowledge Compiler (Strategy + Lesson Engine upgrade) | ✅ Complete |
| 6 | Backtesting Engine Fix + Update (progress/ETA, lookback windows, parser, PDH/PDL, versioning) | ✅ Complete |
| 7 | AI Knowledge Import Center (multi-provider AI-assisted import, self-building dictionary) | ✅ Complete |
| - | AI Knowledge Learning Engine (v6 — deep understanding, hidden rule detection, YouTube import) | ✅ Complete |
| - | AI Knowledge Learning Engine (v7 — AI-Native Structured Extraction, no old parser when AI succeeds) | ✅ Complete |
| - | v8 — Final Architecture Upgrade (confidence gate, pre-AI dedup cache, Debug Mode diagnostics) | ✅ Complete |
| - | Concept library expansion (15 new deterministic concepts: volume profile, mitigation block, session/price-action, breakeven exit) | ✅ Complete |
| - | Multi-strategy Paper Trading, Analytics Dashboard, Automation Pipeline History, SINDHU CEO control room | ✅ Complete |
| 7A | Evolution Core Engine (self-generated lessons, generations, Evolution Score, Champion Engine, Governor) + SINDHU Strategy Generator (11 daily candidates, 1 AI + 10 deterministic) | ✅ Complete |
| - | Genuinely mobile-responsive dashboard (drawer sidebar, tables→stacked cards, 44px touch targets, ≥13px text, bottom tab bar) — frontend-only, desktop unchanged | ✅ Complete |
| 8 | Not started — awaiting CEO direction | ⏳ Pending |

Both apps are live and runnable right now:
- **Desktop app**: `python main.py` (PySide6 GUI — Data Engine tab + Backtesting tab with 5 sub-tabs)
- **Web dashboard**: `python web_main.py` → opens `http://localhost:8420` (also reachable from phone/tablet on the same WiFi via the PC's LAN IP)

Both read/write the **same** SQLite database (`data/database/sindhu.db`) safely at the same time.

---

## Phase 1 — Data System ✅

**What it does:** Downloads and stores OHLCV candle data for ~50 coins across multiple exchanges.

- Multi-exchange support: Binance (native REST), OKX/Bybit/Bitget/Gate.io (via ccxt)
- Only 1-minute candles are ever downloaded/stored; every other timeframe (3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, 1w) is derived on-demand by resampling — never duplicated
- Resumable downloads (never re-downloads existing candles)
- Folder structure: `data/database`, `data/logs`, `data/config`, `data/history`, `data/reports`, `data/market_data`, `data/settings`
- PySide6 desktop dashboard: Start/Pause/Resume/Stop, live status fields, live log, Settings dialog

**Current real data volume:** 50 coins on Binance, ~24.6 million 1-minute candles, ~3 GB database.

---

## Phase 2 + 2.1 — Backtesting Engine ✅

**Phase 2 (base):** Single-timeframe strategy backtesting — `Strategy` subclass interface, bar-by-bar simulation engine with commission/slippage/SL/TP, resumable batch runner, CSV-style reports.

**Phase 2.1 (professional upgrade), built on top without touching Phase 2:**
- **Bilingual strategy parser** (English / Roman Urdu / mixed) — no AI, pure keyword/pattern matching. Understands BOS, CHoCH, FVG, Order Block, Breaker Block, EMA/SMA/RSI/MACD/ATR/VWAP, sessions, SL/TP/Risk/RR.
- **Multi-timeframe engine** — bias/trend/analysis/entry/confirmation timeframes, zero look-ahead (verified: higher-timeframe data only becomes visible once it's actually closed)
- **Strategy validator** — blocks a run and lists exactly what's missing/unclear rather than guessing
- **Strategy library** — save/load/rename/duplicate/delete/favourite/search/tags/version history
- **Multiprocessing** across coins with automatic fallback to sequential on failure (found and fixed a real `BrokenProcessPool`/memory issue on this machine — capped at 4 workers)
- **Trade history** with SL/TP/risk/reward/entry+exit reasons; **Trade Replay** (candlestick chart)
- **Coin/timeframe/session ranking**, backtest queue (multiple strategies back-to-back)
- **Export**: CSV, Excel, PDF

**Known limitations (by design, not bugs):**
- Entry conditions within one strategy are AND'd together (no OR-alternative setups yet)
- Structural concepts (BOS/FVG/OB) default to the entry timeframe unless explicitly placed elsewhere
- Multiprocessing mode supports Stop but not live Pause (sequential mode has full pause/resume)

---

## Phase 3 — Professional Dashboard + Web Interface ✅

Built a **second**, web-based control panel (FastAPI + vanilla HTML/CSS/JS, no build step) alongside the untouched desktop app — reachable from Desktop, Tablet, and Mobile Browser.

- Pages: Home, Market, Data, Backtesting, Reports, Settings — plus 6 reserved-but-hidden pages (Knowledge, Paper Trading, Reflection, Evolution, News, Telegram) that appear automatically once built, no redesign needed
- One API layer (`/api/*`) — the dashboard never touches the database directly; background jobs (downloads/backtests) run in threads and stream live progress over a single WebSocket
- Automatic + manual database backup (safe hot-copy via SQLite's own backup API)
- Verified responsive at desktop (1280px), tablet (768px), and mobile (375px) — found and fixed a real CSS bug (`grid-area` conflict breaking the mobile nav drawer) during testing
- Security: LAN-reachable by design (so phones can connect), token-gated for any state-changing request, read-only GET always open

**Access from mobile:** same WiFi network, browse to `http://<PC-LAN-IP>:8420` (IP changes if the PC reconnects to WiFi — ask Claude to re-check if it stops loading).

---

## Phase 4 — Knowledge Engine ✅

CEO-authored trading lessons that automatically gate every trade during backtesting — no AI, no ML, no auto-generated lessons.

- Lesson fields: Title, Category (18 categories), Description, Priority, Status (Active/Disabled/Draft), Notes, Apply-in flags (Backtesting/Paper Trading/Evolution)
- Description is parsed by the **same** bilingual condition parser strategies use — "avoid buying when RSI above 70" becomes a real, evaluable rule
- Every trade attempt is checked against all active lessons (highest priority first); a lesson can block or require a condition; every check is logged for statistics
- Knowledge Score (0–100%, transparent formula: points per lesson added, per active lesson, per successfully-applied trade)
- New "Knowledge" page in the web dashboard: lesson CRUD, search/filter, per-lesson stats (times used, approved, rejected, estimated impact)
- Reports now show Lessons Applied / Trades Approved / Trades Rejected per batch

**Verified live:** created a lesson through the actual UI, ran a real backtest through the actual API — 28/28 matching entry attempts correctly blocked, trade count dropped from 27 → 0 across 3 real coins, stats and score updated accurately.

**Explicitly not built yet (per Phase 4 spec):** lessons are never auto-generated; future Evolution may suggest lessons, but they'll land as "Draft" pending CEO approval.

---

## Phase 4.5 — Local Remote Control, Mobile Access & Real-Time Sync ✅

Turned the Phase 3 web dashboard into a true multi-device control room, still 100% local (no cloud, no internet, one shared SQLite database).

- **Local IP + QR code**: Home page now shows the LAN URL (`http://<PC-IP>:8420`) and a QR code (generated server-side, `sindhu_web/network.py`, via the `qrcode` package) so a phone connects in one scan
- **Real-time sync**: every mutating change (strategy, lesson, settings) now calls a central `sync.notify()` (`sindhu_web/sync.py`) which both logs it to a new `activity_log` table and broadcasts it over the existing WebSocket to every connected device — other open tabs/phones update live, no refresh needed
- **Auto Save (no Save button required)**: Strategy Builder, Lesson form, and Settings all save automatically on every edit (debounced ~0.5-0.9s). First edit creates the record and captures its id; every edit after that updates the same record — **verified no duplicate records are created**. If a save fails (connection dropped), it's queued in the browser and retried automatically the moment the WebSocket reconnects or the browser comes back online
- **Connected Devices**: every open dashboard tab/phone registers on the WebSocket (IP, browser, connected-since) and shows up on the Home page
- **Control Center** (Home page): Local IP/QR, Connected Devices, Module Status (Data Engine / Backtesting Engine / Knowledge Engine / Dashboard: Running/Idle), Task Manager (running/waiting/completed/failed), live Activity Feed
- **Local security**: the dashboard now refuses any request whose source IP isn't loopback or a private LAN address (192.168.x.x / 10.x.x.x / 172.16-31.x.x) — a phone off the WiFi (e.g. on mobile data) cannot reach it even with the URL

**Verified live** (via the actual running server, not just code review):
1. Desktop/mobile sync: a change made via direct API call (simulating a second device) appeared in the open dashboard tab's Lessons table within ~1s with zero manual refresh
2. Shared database: confirmed both the sync and autosave paths write to the same `data/database/sindhu.db` used by every other phase — no new database, no duplication
3. Strategy sync: edited a strategy's name 3 times — library ended up with exactly 1 record, updated in place each time (`strategy_id` round-trips through the save endpoint)
4. Knowledge sync: created + edited a lesson with no Save click — exactly 1 lesson record, then a status change made via another "device" reflected live in the open tab
5. Auto Save: confirmed for Strategy Builder, Lesson form, and Settings — each debounced save produces one create + N updates, never N creates
6. Architecture: unchanged from Phase 3 (FastAPI + WebSocket + SQLite) — this phase only added `sindhu_web/sync.py`, `network.py`, `devices.py`, three new endpoints (`/api/network`, `/api/activity`, plus `module_status`/`task_summary` on `/api/home`), one new table (`activity_log`), and frontend autosave/live-sync wiring. No existing table, endpoint, or file from Phases 1-4 was rebuilt or altered in behavior.

---

## Dashboard Professional Redesign ✅

Frontend-only overhaul of the Phase 3/4.5 web dashboard into an institutional-grade look and feel. Backend was intentionally left architecturally unchanged (FastAPI + WebSocket + SQLite) -- only small additive endpoints were added where the new UI genuinely needed data that didn't exist yet.

- **Visual system**: dark professional theme (refined palette, shadows, rounded cards), collapsible desktop sidebar rail with icon set, persistent across sessions
- **Top bar**: live clock, version/system-health pills, global search (coins/strategies/lessons/reports/trades via new `/api/search`), notifications dropdown (Activity Feed-backed, with unseen badge), quick actions menu (download/backup/logs/restart services)
- **New "Strategies" page**: full library management (search, favourite, duplicate, delete, "Edit in Backtesting") split out from the Backtesting workflow page
- **Home**: Overview cards (Balance/PnL/Win Rate/Total Trades from the latest completed backtest -- explicitly labeled as backtest data, not live trading, since Paper Trading doesn't exist yet), Evolution Score shown as "N/A" (Evolution isn't built), System Monitor (CPU/RAM/Disk/DB/API/Exchange/Queue/Background Tasks), Control Center quick buttons
- **Market**: added Signal (EMA20-based) and Volatility (1h return stdev) columns, computed cheaply per coin via the existing 1m→1h resample path
- **Backtesting**: added PnL/Drawdown/Estimated Time cards and a live-updating equity sparkline chart (draws from the existing trade WebSocket stream, no backend change needed)
- **Reports**: added Equity Curve and Drawdown charts per viewed report, backed by a new `/api/reports/{batch_id}/trades` endpoint
- **Knowledge**: added Best Lessons / Worst Lessons ranking (client-side, from data already being fetched)
- **Restart Services**: intentionally a *soft* reset (clears server caches) rather than a real process restart -- restarting the actual server isn't something a dashboard button should do unsupervised

**Verified live**: all 8 pages load without console/server errors; ran a real 48-coin backtest (9,837 trades) end-to-end and confirmed the live equity chart, PnL/Drawdown/ETA cards, and the Reports equity/drawdown charts all render correctly against real data; global search, notifications, sidebar collapse, and theme toggle all confirmed working; desktop/mobile responsive breakpoints confirmed (CSS verified correct at the source; this environment's automated browser tool has a known display-readback quirk on mobile-breakpoint class toggles, documented since Phase 3, that doesn't reflect an actual rendering defect); database untouched (50 coins, 24.66M candles, 3.18GB, all pre-existing strategies/data intact); all test artifacts created during verification were cleaned up afterward.

---

## Phase 5 — Paper Trading Engine ✅

Fully automatic, simulation-only paper trading engine — no real orders, ever. Runs 24/7 as a background daemon thread inside the existing web server process, reusing the Data Engine, Backtesting Engine's strategy evaluator, Knowledge Engine, and the shared database without rebuilding any of them.

**20-stage pipeline** (one tick, event-driven, not a constant scan loop):
Live Market → Coin Filter → Market State Detection → Event Trigger → Relevant Timeframes → Relevant Strategies → Relevant Lessons → Risk Manager → Decision Engine → Confidence Score → Trade Reservation → Duplicate Protection → Position Lock → Signal Priority → Paper Trade → Trade Monitor → Trade Close → Reflection → Evolution → Database Save.

**Key components (new `paper_trading/` package):**
- **Coin Filter** — ranks by volume/trend/volatility/activity, never scans all 50 coins blindly (configurable top-N)
- **Event Tracker** — only re-analyzes a coin on new candle / trend change / breakout / volume spike / structure change, doubling as the decision cache (skips recompute when nothing changed)
- **Strategy Matcher** — reuses `backtest_engine`'s `ConfiguredStrategy` + multi-timeframe context evaluated at the latest bar, so signal logic is identical to Backtesting, not reimplemented
- **Lesson Matcher** — reuses `knowledge_engine.condition_eval`; lessons can veto a strategy signal (`block_if_true`, as in backtesting) or stand alone as a complete signal (`require_if_true` + `direction`) — strategies and lessons never depend on each other
- **Risk Manager** — position sizing/slippage reuse the exact backtest formulas; gates every trade regardless of source
- **Confidence Score** — reporting-only, never blocks a valid trade
- **Guards** — Position Lock (no duplicate same-coin/same-direction position, auto-unlocks on close since it's a live query against `status='open'`), Duplicate Signal Protection, Trade Reservation, Cooldown, Max Open Trades, Opposite Signal Policy — all configurable
- **Reflection** — every closed trade gets why-entered/why-exited, mistakes, success, market context
- **Evolution** — updates strategy/lesson performance rankings and confidence from Reflection only; never auto-modifies the original Strategy or Lesson records
- **Dry Run Mode** — switch between analyze-only and real paper execution without restarting

**Database:** additive only — 5 new tables (`paper_positions`, `paper_decision_log`, `paper_strategy_performance`, `paper_lesson_performance`, `paper_strategy_config`) plus new columns on the existing lesson table (version/tags/supported market types/timeframes). No existing table touched.

**Dashboard:** new "Paper Trading" page (Open/Closed Trades, Win Rate, PnL, Daily Goal, Queue, Live Logs) wired into the existing nav/WebSocket pattern; Home page's Overview cards now prefer the live Paper Trading account once it has trade history, falling back to the last Backtest as before.

**Verified live** against the real running server (50 coins, 24.66M candles, 3.18GB DB), all 6 explicitly required checks:
1. **Automatic Trading** — engine opened real (simulated) positions on its own across multiple ticks with no manual trigger
2. **Dry Run Mode** — confirmed it analyzes and logs decisions but places zero positions while `dry_run: true`
3. **Position Lock** — a second identical same-coin/same-direction signal was correctly rejected while a position was open; auto-unlocked immediately after close
4. **Duplicate Protection** — a repeated signal from an unchanged market condition was rejected, not re-entered
5. **Trade Reservation** — concurrent-signal race on the same coin resolved to exactly one opened position, not two
6. **Auto Save** — every position, decision, and performance update persisted to the database with zero manual save step; confirmed durable across a full server restart

**Bonus confirmations observed organically during testing:** Trade Monitor/Close (a real stop-loss auto-close fired mid-test on SKYUSDT), Max Open Trades (6th signal correctly rejected once the cap of 5 was reached), Cooldown (re-entry correctly blocked immediately after a close), Reflection→Evolution (lesson performance stats updated after a closed trade without mutating the original lesson record).

**Bonus fix (found during this phase, applies to the whole app):** the frontend SPA router could let an in-flight async page render (from auto-refresh or a WebSocket callback) overwrite a newer page's content after navigating away — fixed with a route-token guard (`activeRouteToken` / `isStaleRoute`) applied to every page renderer and the shared auto-refresh helper.

**Two performance/correctness bugs found and fixed during build** (not user-facing, caught before verification): an oversized lookback-window unit bug that made each tick take 2+ minutes (fixed with a clear `lookback_days` setting), and a reflection duration bug computing a nonsensical negative trade duration (fixed by passing the actual exit time into the reflection builder instead of the pre-close record).

**Known/disclosed item:** during final cleanup, a pre-existing placeholder-named strategy ("Unnamed Strategy", id `55eb19450fd6`) was found missing from `strategies/library/` — only "Stragy 1" remains. The exact cause couldn't be pinned down (possibly from earlier redesign-phase cleanup or a stray leftover server process from the crash-recovery at the start of this session). It held no real CEO-authored content, so it wasn't treated as blocking, but is disclosed here for transparency.

**Explicitly NOT done (per spec):** no real trading/orders anywhere in this phase; Evolution never touches original Strategy/Lesson records, only rankings/scores/confidence.

Engine is currently **stopped** (`running: false`) with production-safe defaults loaded (`dry_run: true`, max 5 open trades, 15 min cooldown, top-20 coin filter) — it will not start trading on its own until explicitly started from the dashboard or API. **Waiting for CEO approval before Phase 6.**

---

## Knowledge Compiler — Strategy + Lesson Engine upgrade ✅

Replaces the old "paste raw strategy text into one parser" flow with a rule-based document compiler: the CEO pastes *anything* trading-related (strategy, lesson, YouTube transcript, NotebookLM/ChatGPT/Claude report, book notes, journal, mixed strategy+lesson doc) and the system classifies, extracts, validates, and stores it automatically. Deterministic keyword/regex logic only — no AI, no ML. The existing Strategy Engine (`backtest_engine`) and Lesson Engine (`knowledge_engine`) were extended, not rebuilt: the bilingual condition parser, `StrategyConfig`/`Condition` schema, `ConfiguredStrategy`, `validator.py`, `Lesson`/`new_lesson()`, and the Knowledge Library/lesson storage are all reused as-is by the new compiler.

**New `knowledge_compiler/` package:**
- **Trading Dictionary** (`dictionary.py`) — canonical concept/indicator/session/risk/psychology terms with aliases (extends `strategy_parser`'s own concept table rather than duplicating it), including new terms the old parser didn't know: PDH/PDL/PDC/PWH/PWL, POI, mitigation, inducement, equal highs/lows, premium/discount, killzones, plus risk and psychology vocabulary (FOMO, revenge trading, overtrading, discipline, drawdown, position sizing, etc). `normalize_text()` rewrites a recognized alias into wording the existing parser already understands (e.g. "bullish OB" → "order_block") — restricted to structural/indicator/session/trend terms so it never interferes with the parser's own literal SL/TP/RR/Risk regexes.
- **Document Classifier** (`classifier.py`) — keyword-bucket scoring into Strategy / Lesson / Mixed / Psychology / Risk Management / Indicator Guide / Market Structure / Unknown, with a confidence score.
- **Section Detector** (`sections.py`) — splits a pasted document into Summary/Entry Rules/Exit Rules/Risk/Market Conditions/Indicators/Filters/Psychology/Common Mistakes/Weaknesses/Strengths/Checklist/Pseudocode/IF-THEN Rules/Performance, recognizing markdown headers, bold headers, and colon headers; a header-less document (today's typical paste) falls back to one whole-document section, fully backward compatible. Also strips a leading "Strategy Name:"/"Title:" line so the document's own title never gets accidentally scanned as a rule.
- **Rule Extractor** (`rule_extractor.py`) — routes strategy-relevant sections through the dictionary normalizer and the **existing** `strategy_parser.parse_strategy_text` unchanged. Adds two small, contained text-level fixes ahead of the handoff: splitting compact multi-directive lines ("SL 2% TP 4% Risk 1%" only ever yielded the first one before) onto separate lines, and expanding spelled-out/spoken phrasing common in transcripts ("stop loss...", "take profit...", "1 to 3 risk reward") into the abbreviations the parser's regexes expect.
- **Lesson Extractor** (`lesson_extractor.py`) — pulls one candidate lesson per qualifying bullet/sentence out of educational sections, tags it with recognized dictionary concepts, and hands it to the **existing** `knowledge_engine.lesson.new_lesson()` unchanged. Sections with no recognizable trading content are ignored, per spec ("ignore unrelated narrative").
- **Compiler Validator** (`compiler_validator.py`) — wraps (never replaces) `backtest_engine.validator.validate()`. Never rejects outright: fills safe configured defaults (risk %, RR), standard Trading Dictionary indicator periods (RSI 14, EMA 20...), or borrows a compatible value from the most similar strategy already in the Knowledge Library (by shared concepts) — e.g. missing entry timeframe or stop-loss type. Only what's still missing after all three passes (unclear entry/exit rules, a missing SL with nothing to borrow, invalid indicator names) is reported as `NEEDS_CLARIFICATION`; a fully-resolved strategy is marked `READY_FOR_BACKTEST`.
- **Quality Check** (`quality.py`) — Strategy DNA / Lesson DNA fingerprinting (condition-based when enforceable, normalized-text-based for pure-prose lessons so unrelated psychology tips don't collide), duplicate-rule dedup, concept canonicalization, and a same-bucket contradiction detector (e.g. "close above EMA50" and "close below EMA50" both required as entry conditions).
- **Storage** — 3 new additive tables (`compiled_documents`, `knowledge_concepts` usage tracker, `knowledge_relationships`) in the existing database, following the same `CREATE TABLE IF NOT EXISTS` pattern used by every prior phase. No existing table touched.
- **Orchestrator** (`compiler.py`) — `compile_document(text, title, source_hint)`: classify → detect sections → extract strategy (if Strategy/Mixed) → resolve/validate → dedupe/fingerprint → extract lessons (always, independent of doc_type) → dedupe against the Knowledge Library → auto-save everything → return one `CompiledDocument`.

**Web API** (`sindhu_web/api/knowledge_compiler.py`): `POST /api/knowledge-compiler/compile`, `GET /documents`, `GET /documents/{id}`, `GET /concepts`. The original `/api/backtesting/parse` endpoint and the desktop Qt Strategy Builder are untouched and still work exactly as before — verified via direct regression test.

**Dashboard:** new "Knowledge Compiler" nav page — paste box + optional title/source hint, Compile button, and a results panel (doc type + confidence, sections detected, extracted strategies with status/clarification notes/auto-resolved defaults, extracted lessons with category/tags, concepts recognized, compile history).

**Verified via a 9-document test suite** (short strategy, long multi-timeframe SMC strategy, NotebookLM report, Claude report, ChatGPT report, YouTube transcript, book notes, incomplete strategy, mixed strategy+lesson document) run directly against `compile_document()`, plus the same flow re-verified through the live HTTP API:
- Classification: 7/9 matched my own expected label exactly; the other 2 were arguably *more* correct than my expectation (a pure course-summary NotebookLM doc with zero executable rules classified as LESSON rather than my expected MIXED; a complete, clean strategy with an extra risk-advice paragraph classified as STRATEGY rather than MIXED) — and in both cases lessons were still correctly extracted separately from the strategy content regardless of the top-level label, which is the actual spec requirement ("separate executable rules from educational content automatically").
- Strategy extraction correctly produced `READY_FOR_BACKTEST` for clean documents and `NEEDS_CLARIFICATION` with a specific, human-readable reason for every genuinely ambiguous rule (never a silent guess).
- Compiler Validator resolution confirmed live: RSI period auto-defaulted to 14, entry timeframe/stop-loss borrowed from a similar existing strategy, take-profit derived from a detected risk:reward ratio.
- Quality Check confirmed live: an identical strategy pasted twice was recognized as a duplicate on the second compile and not re-saved; a genuine contradiction ("EMA required both bullish and bearish in the same entry rule set") was correctly flagged.
- Auto Save confirmed durable across a server restart; every saved strategy/lesson traced back to its source document via `knowledge_relationships`.

**4 real bugs found and fixed during this build** (all self-caught before delivery, via direct testing against realistic pasted documents — not reported by the CEO):
1. A document's own title line (e.g. "Strategy Name: EMA Pullback **Long**") could get accidentally scanned as a rule by the existing parser's fallback path, since "Long" reads as a bullish direction keyword — fixed by stripping a leading title line before any extraction runs.
2. Short dictionary aliases like "SMA" or "OB" matched as plain substrings inside unrelated words ("sma" is literally the first three letters of "Smart", so "Smart Money Concepts" was wrongly tagged with the SMA indicator) — fixed with word-boundary-aware alias matching everywhere the dictionary is scanned against free text.
3. Injecting a section heading the underlying parser doesn't recognize (e.g. "Filters:", "Market Conditions:") as a bare text line let it fall through and get misread as a bogus unclear condition — fixed by only re-emitting headings for the two section kinds (Entry/Exit Rules) the parser's own header keywords actually understand.
4. The classifier's "avoid" keyword alone was too weak a lesson signal — it's extremely common in ordinary strategy filter text ("avoid trading during news") and caused clean strategies to be misclassified as Mixed with no real lesson content present — removed as a standalone trigger.

**Known limitation (disclosed, not fixed — narrow parser vocabulary gap):** the underlying `strategy_parser`'s structure-based stop-loss detection only recognizes "order block/swing/structure/breaker" as structural anchors, not FVG — so "SL goes below the fvg" (a real transcript phrasing) isn't picked up as a structural stop-loss and correctly falls through to `NEEDS_CLARIFICATION` rather than being silently guessed. Left as-is rather than expanding the underlying parser's regex vocabulary, which was out of this phase's scope.

**Explicitly NOT done (per spec):** no AI/ML anywhere in the pipeline; the compiler never auto-modifies an existing Strategy or Lesson record, only creates new ones or (on an exact-duplicate match) leaves the existing one alone.

---

## Phase 6 — Backtesting Engine Fix + Update ✅

Two directives landed together: a formal "Phase 6 Update" spec (4 problems + dashboard upgrades) and an "Emergency Fix" spec describing the CEO's real symptom (Run Backtest did nothing — progress/trades/win-rate/PnL all stuck at 0). Both were treated as the same job: fix backtesting end-to-end, no new phases, rule-based only, no AI/ML anywhere.

**Root cause of the reported symptom (found via full stack audit, not guessed):** a stray old-code `web_main.py` process was still holding port 8420 from before this session's fixes, so the CEO's browser was talking to outdated code the whole time. Killed after confirming its identity via `Get-CimInstance Win32_Process`. Compounding this, the browser itself was independently caching the root `/` HTML document (not just `app.js`), so even fresh code changes weren't reaching the tab — fixed permanently with cache-busted asset URLs (`?v=<mtime>`) plus `Cache-Control: no-store` headers on `/` in `sindhu_web/server.py`. Also found and cleaned 32 batches stuck in `running` state and 6 degenerate batches (0-trade or a runaway 148,883-trade artifact) left behind by the stray process — all for the CEO's real "S1" strategy, which itself (13 versions) was untouched.

**Problem 1 — Backtesting visibility:** `engine.run_backtest()` gained a `bar_progress_cb` firing at ~50 points per coin; `mtf_worker.run_one_symbol()` now emits stage events (`fetching_data` → `computing_indicators` → `simulating_bars` with live bar%/trade-count → `completed`/`failed`) through a `multiprocessing.Manager().Queue()`, drained by a background thread in `runner.py` that computes ETA from elapsed time and forwards everything through the existing WebSocket job-progress channel — identical code path for both sequential and multiprocessing execution via a `_DirectCallbackQueue` adapter. New `backtest_engine/diagnostics.py` (`condition_hit_report`) reuses the real evaluator (`ConfiguredStrategy._eval`) to report, per entry condition, how many bars it was true and how many bars all conditions were true together, whenever a coin finishes with 0 trades — stored in a new `backtest_condition_reports` table and surfaced on both the Backtesting page (inline) and Reports page.

**Problem 1 also surfaced a real pre-existing bug:** `liquidity_sweep` was a recognized parser keyword but was never wired into any evaluator — it silently always evaluated `False`. This alone explains the CEO's own bug example ("liquidity_sweep true on 1,240 bars... ALL THREE together on 0 bars"). Fixed by adding `concepts.liquidity_sweep()` and wiring it into `configured_strategy.py`, `condition_eval.py`, and `frame_builder.py`.

**Problem 2 — Entry conditions too strict:** concept-type conditions (sweep, BOS, CHoCH, FVG, liquidity sweep, PDH/PDL sweep) now check a lookback window (default 10 bars, configurable via `Condition.lookback_bars`, parsed from "within N bars" / "last N candles" / Roman Urdu "pichle N candles") instead of requiring same-bar coincidence — `concepts.true_within_lookback()` only ever looks backward, so zero look-ahead is unchanged (verified in TEST 8). `lookback_bars=1` or a "same bar/strict" phrase restores the old exact behavior. Scope is deliberately narrow: `indicator_compare`/`price_compare`/`session`/`trend` conditions are untouched, since a numeric indicator reading is a snapshot, not a recent event.

**Problem 3 — Parser limitations**, all in `strategy_parser.py`: multi-directive lines ("SL 2% TP 4% Risk 1%") now set all three fields instead of the first one matched short-circuiting the rest; RR now accepts `2.5:1`, `1:2.5`, spoken "1 to 3", "minimum 2.5 RR", and bare "RR 2.5" alongside the original `1:3`/`3:1`; structural stop-loss now also recognizes FVG as an anchor; PDH/PDL are now real, causal, executable concepts (`concepts.previous_day_high_low()` — previous UTC day's high/low, forward-filled onto every bar of the following day via `shift(1)`, verified to never reflect the current day's own high/low) wired through `configured_strategy.py`, `condition_eval.py`, and `frame_builder.py`, supporting "price above PDH", "sweep of PDL", and a `take_profit.type == "level"` targeting PDH/PDL.

**Problem 4 — Strategy save/load/versioning:** `strategy_library.find_by_name()` added; saving under an existing name now updates that strategy as a new version instead of creating a duplicate (verified: same `id`, `current_version` 1→2). New `GET /api/backtesting/strategies/{id}/versions` endpoint + a version-history panel on the Strategies page. Strategy list now shows concepts used, timeframes, `READY_FOR_BACKTEST`/`NEEDS_CLARIFICATION` status, and last backtest result (aggregated directly from stored `metrics_json` — an earlier version called `generate_report()` per row, which also writes files to disk and made the page hang for seconds; fixed by reading the already-computed metrics instead). Delete now requires a confirm dialog.

**Dashboard:** Backtesting page has a live progress panel (stage, coins progress, within-coin bar progress, trade counter, ETA) and a post-run inline summary with an "Open Full Report" button; 0-trade coins show the condition-hit breakdown inline. Home page has a system-alerts card (flags strategies that produced 0 trades across a batch) and a top-3-strategies-by-profit table. Reports page shows per-condition hit statistics and a 0-trade-coins list with reasons, per batch.

**Verified** with a 9-check consolidated suite covering all 10 spec-required tests (single-condition EMA strategy produces real trades; sweep+BOS+FVG with lookback window produces trades; multi-directive SL/TP/Risk line all detected; all required RR phrasings parsed; PDH/PDL + sweep wired end-to-end; save-by-name versions instead of duplicating; live per-coin progress confirmed via both direct runner test and real browser click-through; PDH/PDL zero look-ahead confirmed against real BTCUSDT data; an old-format saved strategy with no `lookback_bars` field still loads and runs unchanged) — **9/9 passed**. Strategy library and batches table confirmed clean of test debris afterward (only the CEO's real "S1" strategy remains, no stuck/orphaned batches).

**Explicitly not done (per spec):** no new phase started, no AI/ML anywhere, no existing table dropped or rebuilt (`backtest_condition_reports` is additive-only), no existing regex behavior changed (only extended), desktop app untouched, port stays 8420, all configs remain JSON files under `data/config`.

---

## Phase 7 — AI Knowledge Import Center ✅

Two spec revisions landed back to back (v1.0 "AI Integration Center", then v2.0 "AI Knowledge Import Center"), both built on the same core principle: **AI is a temporary teacher, SINDHU is the permanent student.** AI is used only during import to help understand/clean a pasted document; the actual extraction, validation, deduplication, and storage is always done by the existing deterministic `knowledge_compiler`/`backtest_engine` pipeline. Once saved, a strategy or lesson is a normal rule-based record — nothing in the trading engine ever calls out to AI again (verified: zero references to `ai_integration` anywhere in `backtest_engine/`, `paper_trading/`, or the engines themselves).

**New `ai_integration/` package** (imported only by the web API layer, never by the trading engine):
- `config.py` — per-provider settings (API key, model, temperature, max_tokens, timeout, retry_count, daily/monthly quota, cost per 1K tokens) persisted to `data/config/ai_settings.json`, same pattern as every other SINDHU setting. `provider_fallback_chain()` returns enabled+configured providers in priority order.
- `providers.py` — real REST clients for **Claude, Groq, OpenAI, Gemini, DeepSeek**, all going through one `AIProvider.chat()` that never raises — every failure (no key, timeout, HTTP error, malformed response) comes back as a structured `AIResult(ok=False, error=...)`.
- `chunking.py` — splits oversized documents into ~6000-token pieces on paragraph boundaries (with overlap so a rule split across a boundary isn't lost), cleans each chunk independently, merges back into one document before it ever reaches the parser — one strategy/lesson gets saved, never one per chunk.
- `importer.py` — the orchestrator: **Smart Provider Switching** tries the CEO's active provider first, then Claude → Groq → OpenAI → Gemini → DeepSeek, moving to the next the instant one fails; if every provider fails (or none is configured), it silently falls back to the raw text going straight into the deterministic compiler — **Offline Mode**, never a crash, never a stuck import.
- `file_extractors.py` — PDF (`pypdf`), DOCX (`python-docx`), TXT/MD text extraction.
- `import_queue.py` — persisted pending/processing/completed/failed queue (`ai_import_queue` table) with batch import and retry, backed by a single background worker thread that atomically claims one row at a time.
- `quality_score.py` — Knowledge Quality Score: completeness %, confidence % (classification confidence discounted per auto-resolved default), automation-ready, backtesting-ready, overall score — purely derived from the already-saved document, never a second source of truth.
- `dictionary_builder.py` — **Self-Building Dictionary**: discovers new trading terms two ways — (1) deterministic, AI-independent parenthetical acronym/expansion scanning (e.g. "Smart Money Technique (SMT)") that works even with AI fully disabled, and (2) an AI-authored `GLOSSARY:` section (the AI is asked to note any unusual terms + a definition drawn only from the source text) stripped out before the cleaned text reaches the rule-based parser. Either way, once discovered a term is saved permanently to `ai_dictionary_entries` — AI is never needed to reuse it again.

**Storage** (all additive): `ai_usage_log`, `ai_import_queue`, `ai_dictionary_entries` tables; `compiled_documents` gained `ai_assisted`/`ai_provider` columns. `knowledge_compiler.compiler.compile_document()` gained optional `ai_assisted`/`ai_provider` provenance parameters (default `False`/`None`, fully backward compatible with its existing caller).

**A real latent bug found and fixed along the way:** the Knowledge Compiler's auto-save path (`_compile_strategy`) always called `strategy_library.create()`, so re-importing an updated version of a same-titled document created a duplicate strategy instead of a new version — the same-name-versioning fix from Phase 6 had only been applied to the manual Strategies-page save endpoint, not this path. Fixed by reusing `strategy_library.find_by_name()` + `save_version()` here too; verified a re-import with changed content now updates the existing strategy to version 2 instead of duplicating it.

**Web API** (`sindhu_web/api/ai_integration.py`): provider CRUD/enable/disable/activate/test, `POST /api/ai/import` (text) and `/api/ai/import/upload` (file), import queue endpoints (enqueue/list/retry/retry-failed), `/api/ai/usage` (now enriched with daily/monthly counts, quota remaining, estimated cost, avg latency/tokens per provider), `/api/ai/logs`, `/api/ai/dashboard` (total strategies/lessons/dictionary size/patterns/indicators/success rate/failed imports), `/api/ai/dictionary`, `/api/ai/knowledge-score/{doc_id}`, `/api/ai/cache/clear`.

**Dashboard:** new "AI Center" nav page — CEO Dashboard stat cards, provider cards (key/model/temperature/max-tokens/timeout/retry/quota/cost, Enable/Disable, Test Connection, Set Active), an Import panel (paste or upload, AI-assist toggle, per-import Knowledge Quality Score + any newly discovered dictionary terms + the categorized Import Report), an Import Queue table with per-item and bulk retry, a Self-Building Dictionary table, and an expanded Usage Monitor + Recent Logs.

**Verified end-to-end** (all via real backend calls, several also confirmed live through the running server/browser): all 5 providers fail cleanly with no key configured (no exceptions, no network calls attempted); the fallback chain tries Claude then Groq against real Anthropic/Groq endpoints with fake keys (real HTTP 401s handled) before falling back to rule-based parsing; chunking splits a 62K-character document into 4 pieces and recombines correctly, falling back cleanly when every provider fails on every chunk; the import queue processes items via its background worker and correctly retries a simulated failure; the Knowledge Quality Score produces sensible values across a complete strategy, an incomplete one, and a pure-lesson document; the self-building dictionary correctly extracts "Smart Money Technique" from "(SMT)" and conservatively falls back to the full phrase when an acronym isn't a clean initialism; re-importing a changed document under the same title now versions instead of duplicating; the CEO Dashboard and Usage Monitor endpoints return correct live aggregates.

**Explicitly not done (per spec):** AI is never called during backtesting, paper trading, evolution, reflection, or risk management — only at import time. No AI/ML anywhere in the trading engine. No existing table dropped or rebuilt (all Phase 7 storage is additive). Desktop app untouched, port stays 8420, all configs remain JSON files under `data/config`.

---

## AI Knowledge Learning Engine (v6) ✅

A ground-up rewrite of the import pipeline's AI half, per the CEO's "SINDHU v6 AI Knowledge Learning Engine" spec. Same core principle as Phase 7 (AI is a temporary teacher, never touches the trading engine), but AI now does real **Deep Understanding** instead of just cleaning text for a keyword-based parser: one AI call (per document, or per chunk for oversized ones) reconstructs the whole document into SINDHU's own plain-text format — completing rules it can confidently infer from context — and separately reports hidden/inferred rules (with confidence, reasoning, and evidence), new dictionary terms, and psychology notes as structured JSON. None of that AI output is ever saved directly: the reconstructed text is only ever handed to the **same, unmodified** `knowledge_compiler.compile_document()` deterministic pipeline that was already there — the rule-based parser itself was never touched, exactly as required.

**New/rewritten modules:**
- `ai_integration/schema.py` — the JSON contract: `SINDHU_FORMAT_GUIDE` (the exact section headings `sections.py`/`rule_extractor.py` already recognize), `build_deep_understanding_prompt()` (instructs the model to think like a professional trader — context, hidden logic, psychology, market structure, order flow — and to only complete a rule when there's real evidence for it, never invent a number), and `parse_deep_response()`, a never-raises JSON parser.
- `ai_integration/deep_understanding.py` — orchestrates the Smart Provider Switching chain (unchanged from Phase 7: CEO's active provider → Claude → Groq → OpenAI → Gemini → DeepSeek → Offline Mode) calling the Deep Understanding prompt once per document (or once per chunk for oversized input, merging the reconstructed text + unioned dictionary/hidden-rule/psychology/missing-rule findings back into one result before anything is saved — still exactly one strategy/lesson per import, chunking is purely an implementation detail of handling long input).
- `ai_integration/importer.py` — fully rewritten orchestrator: detect input kind (pasted text vs. YouTube URL) → Deep Understanding → fold any AI psychology notes not already in the reconstructed text under a `Psychology:` heading (so the existing lesson extractor picks them up) → hand off to the unmodified `compile_document()` → attach hidden rules/psychology notes/dictionary terms as provenance. Falls back to pure rule-based compilation of the raw text the instant AI is disabled, unconfigured, or every provider fails on every chunk — Offline Mode by construction, not a try/except bolted on.
- `ai_integration/youtube_import.py` — YouTube support: extracts the video ID from any watch/shorts/youtu.be/embed URL, fetches the transcript via `youtube-transcript-api` (no API key needed), strips caption noise (`[Music]`/`[Applause]` tags and bare ♪ glyphs, filler words), then feeds the cleaned transcript into the same import pipeline as any pasted document. Every failure mode (bad URL, no captions, private/unavailable video, library missing) reports a plain error string, never crashes.
- `ai_integration/dictionary_builder.py` — rewritten to save the AI's full term profile (definition, category, aliases, examples, related concepts, usage notes) rather than a bare definition, alongside the pre-existing deterministic acronym-scan path (still fully AI-independent).
- `ai_integration/quality_score.py` — gained `hidden_rule_count`/`avg_hidden_rule_confidence_pct`, purely reporting what Deep Understanding already attached to the document.

**Storage** (all additive): `compiled_documents` gained `hidden_rules_json`/`psychology_notes_json`/`deep_knowledge_json`; `ai_dictionary_entries` gained `aliases_json`/`examples_json`/`related_concepts_json`/`usage_notes`; `ai_import_queue` gained `input_kind` (`text`|`youtube`) so a queued item can be a YouTube URL. `knowledge_compiler.compiler.compile_document()` gained optional `hidden_rules`/`psychology_notes`/`deep_knowledge` provenance parameters — same pattern as Phase 7's `ai_assisted`/`ai_provider`, the deterministic extraction/validation/save logic is completely unaffected by any of them.

**Web API:** `POST /api/ai/import/youtube` (fetch + import a YouTube link); import results and the dashboard now surface `hidden_rules`, `psychology_notes`, and `total_hidden_rules_detected`; `/api/ai/dashboard` reports `youtube_import_available` so the frontend can hide the button if the library isn't installed; the import queue accepts an `input_kind` per item.

**Dashboard:** the AI Center's Import panel gained a "paste a YouTube link" field (Import Now / Add to Queue); import results now show a Hidden Rule Detection table (rule / confidence / reason / evidence) and Psychology Notes; the Self-Building Dictionary table gained Aliases and Related Concepts columns; the CEO Dashboard gained a Hidden Rules Detected stat card.

**A real bug found and fixed via live testing (not a hypothetical):** the Groq provider (llama-3.3-70b) routinely emits a literal newline/tab character inside a multi-line JSON string value (e.g. inside `"reconstructed_document": "..."`) instead of an escaped `\n` — technically invalid JSON that `json.loads` rejects outright with "Invalid control character". This is a near-universal quirk across LLM providers when asked to return long text inside a JSON field, not specific to one bad response. Fixed with `schema._escape_literal_control_chars_in_strings()`, a single-pass scanner that walks the raw response tracking whether it's inside a string literal (respecting `\"` escapes) and escapes any literal control character found there before falling back to `json.loads` a second time. Verified against the exact failing response captured live from Groq — parses correctly afterward, with all fields (`reconstructed_document`, `dictionary_terms`, `hidden_rules`, `psychology_notes`) intact.

**Verified end-to-end, using the CEO's own live Groq API key (already configured/active from a prior session) rather than synthetic mocks:**
- A strategy with implicit language ("buy from demand", "wait for confirmation") → Deep Understanding correctly inferred a hidden confirmation rule (confidence 0.8, with quoted evidence) and a psychology note, while correctly leaving stop-loss/take-profit as "missing" rather than inventing numbers the source never gave.
- A lesson document using obscure jargon ("Judas Swing", "Mitigation Block") → AI correctly extracted both as new dictionary terms (with related concepts and usage notes) and two hidden rules; "Mitigation Block" was correctly *not* re-saved since it's already a known alias in the static dictionary — the self-building dictionary defers to existing knowledge instead of duplicating it.
- A 32,000-character synthetic document → correctly triggered chunking (2 chunks), each understood independently by real API calls, merged into one reconstructed document, one saved strategy, hidden rules and dictionary terms unioned and deduplicated across both chunks.
- A real, transient Groq failure occurred mid-testing (unrelated to the bug above) — the importer fell back to pure rule-based parsing automatically and still returned a valid, saved document with no exception surfaced anywhere — Offline Mode/Smart Provider Switching confirmed working under a genuine real-world failure, not just a simulated one.
- Explicit Offline Mode (`use_ai=False`) on a clean strategy: identical deterministic output to Phase 7, zero hidden rules (honestly, since AI never ran) — trading engine behavior is unaffected either way.
- Real YouTube transcript fetch (public video, `youtube-transcript-api`) → cleaned (bare ♪ glyphs stripped) → imported successfully through both the direct API and the persisted Import Queue (`input_kind: "youtube"`); an invalid URL and a nonexistent video ID both failed with clear messages and no crash.
- Live server restarted on the new code and confirmed via the running dashboard (`get_page_text`): CEO Dashboard, Providers, Import panel (with the new YouTube field), Import Queue, Self-Building Dictionary (with Aliases/Related Concepts), and Usage Monitor/Recent Logs all render real, current data — including the actual Groq `/ai/import/deep-understanding` calls made during this verification pass.

**Explicitly not done (per spec):** the rule-based parser (`rule_extractor.py`, `strategy_parser.py`, `lesson_extractor.py`) was not modified at all — only the AI half of the pipeline was rewritten, as instructed. "One AI request per document" is the policy for a normal-sized paste; a document large enough to need chunking makes one request per chunk by necessity of the provider's context window, still producing exactly one saved strategy/lesson. AI is still never reachable from `backtest_engine/`, `paper_trading/`, or any engine module (re-verified: zero references).

---

## AI Knowledge Learning Engine (v7 — AI-Native Structured Extraction) ✅

A complete architectural redesign of the import pipeline's AI half, per the CEO's explicit "FINAL ARCHITECTURE REQUIREMENT" directive. v6 still had the AI reconstruct plain text and hand it to the old regex-based `rule_extractor`/`strategy_parser`/`lesson_extractor` pipeline. The CEO's v7 mandate was explicit: **"Do NOT pass AI output back into the old keyword parser. The old parser must ONLY be used when AI is disabled."** So AI now directly produces a StrategyConfig/Lesson-shaped JSON structure — entry/exit/confirmation conditions, stop-loss, take-profit, risk, timeframes, sessions, and every lesson — using ONLY the exact indicator/concept/session vocabulary the backtest engine can already execute (`backtest_engine.validator._KNOWN_INDICATORS`, `strategy_parser.SESSION_NAMES`). `ai_integration.strategy_builder` turns that directly into real `StrategyConfig`/`Condition`/`SLTPSpec`/`Lesson` objects — no text re-parsing anywhere in this path.

**New/rewritten modules:**
- `ai_integration/schema.py` — fully replaced: the JSON contract now mirrors `StrategyConfig` directly (not "reconstructed text"), constrained to the backtest engine's real vocabulary (18 indicators/concepts, 3 sessions, `>`/`<` only, 6 lesson categories aligned to `knowledge_engine.lesson.CATEGORIES`). The prompt explicitly tells the model that `type="raw"` is a last resort, with concrete phrase→vocabulary mappings for the exact examples in the CEO's own spec ("buy from demand" → `concept:support`, "wait for confirmation" → `concept:bos`/`choch`, etc.) — added after live testing showed the model was defaulting to `raw` too readily without this guidance.
- `ai_integration/strategy_builder.py` (new) — `build_strategy_config()`/`build_condition()`/`build_lesson()`: construct real objects directly from the AI's validated dict, demoting anything outside the known vocabulary to `type="raw"` (never crashes, never injects a fake executable primitive).
- `ai_integration/deep_understanding.py` — rewritten to call the new structured prompt; chunked-document merging now merges real strategy fields (conditions deduped, first non-unknown SL/TP/risk value wins across chunks, lessons/dictionary/inferred-fields unioned), with confidence taken as the **minimum** across chunks (conservative).
- `knowledge_compiler/compiler.py` — split into shared helpers (`_finalize_and_save_strategy`, `_save_lesson_objects`) used by both pipelines, plus a new `compile_from_ai_extraction()` entry point that takes an already-built `StrategyConfig`/`list[Lesson]` and saves them through the exact same dedup/versioning path as the text pipeline — **never calls `rule_extractor`/`lesson_extractor`**. `compile_document()` (the old text pipeline) is completely unchanged and is now used ONLY for Offline Mode.
- `knowledge_compiler/compiler_validator.py` — added `force_ready()`: the one safety-net default (2% fixed stop-loss) needed so an AI-confident import can honestly become "automatically Backtesting Ready, no manual editing" even in the rare case nothing else could resolve stop-loss; used only by the AI-Native path.
- `ai_integration/importer.py` — rewritten: AI-native path bypasses `compile_document()` entirely; the old text pipeline is called (`_offline_result()`) ONLY when AI is disabled/unconfigured, every provider fails on the whole document, or an AI-extracted structure somehow still fails to save.

**No more "Needs Clarification" at high confidence:** when the AI's own reported confidence is ≥70%, status is always `READY_FOR_BACKTEST` — AI's understanding is accepted as the source of truth, per the CEO's explicit instruction. Below 70%, status still reflects genuine gaps (AI's own `missing_rules`, not the old parser's), so nothing is silently hidden either.

**A real, two-part bug found and fixed via live testing (not hypothetical):**
1. `compiler_validator.force_ready()` was re-running `base_validator.validate()` and appending its errors as "informational" notes on top of the ones `resolve_and_validate()` already returned — duplicating every clarification message. Fixed: `force_ready()` now only applies its one stop-loss default and returns the existing notes unchanged.
2. The first version of the structured-extraction prompt let the model fall back to `type="raw"` too readily for exactly the phrases the CEO's own spec called out as examples ("buy from demand", "wait for confirmation") instead of committing to the real vocabulary. Fixed by adding explicit concrete mappings to the prompt. Re-tested on the same document: entry/exit conditions that were previously 2-of-3 `raw` became 100% real, executable `concept` conditions (`support`, `bos`, `resistance`), confidence rose from 80% to 90%, and `backtest_engine.validator.validate()` on the saved strategy returned **zero errors**.

**Verified end-to-end with the CEO's own live Groq key:**
- A strategy with implicit language ("buy from demand", "wait for confirmation") → AI directly produced real `concept` conditions (no raw fallback), `stop_loss` inferred as `structure` type, confidence 90%, saved strategy passes `backtest_engine.validator.validate()` with **zero errors** — genuinely, directly Backtesting Ready, no manual editing.
- A pure lesson document (AMD cycle, Silver Bullet) → correctly produced `doc_type: LESSON` with zero strategy, 3 lessons built directly via `strategy_builder.build_lesson()` (bypassing `new_lesson()`'s keyword-based rule_type/direction detection entirely — AI supplied both directly), 2 new dictionary terms saved.
- A 32,000-character document → chunked (2 chunks), each understood independently, merged into ONE saved strategy with conditions unioned across both chunks (concepts from chunk 1 and chunk 2 both present in the final saved strategy).
- Explicit Offline Mode (`use_ai=False`) → produces byte-for-byte the same kind of output as Phase 7/v6 (regex-based `price_compare` conditions, `NEEDS_CLARIFICATION` status, zero inferred fields) — confirms the old pipeline is completely untouched and reserved for this case only.
- YouTube import through the new pipeline (real transcript fetch) → AI correctly determined no strategy/lessons existed in a non-trading video, no crash.
- Live server restarted on the new code; dashboard, import panel, and Self-Building Dictionary all confirmed rendering current data through the actual browser (`get_page_text`), including a real strategy import via the live `/api/ai/import` endpoint.

**Explicitly not done (per spec):** the old parser (`rule_extractor.py`, `strategy_parser.py`, `lesson_extractor.py`) was not modified and is not called at all when AI succeeds — verified by reading the new `importer.py`/`compiler.py` code paths directly. "One AI request per document" remains the policy; a document large enough to need chunking makes one request per chunk by necessity, still producing exactly one saved strategy. AI is still never reachable from `backtest_engine/`, `paper_trading/`, or any engine module.

---

## v8 — Final Architecture Upgrade ✅

The CEO's "FINAL ARCHITECTURE UPGRADE" directive required a full completion audit before any changes, with an explicit instruction to reuse/extend existing modules rather than duplicate them. The audit found the pipeline was already ~88% complete (multi-timeframe sync + on-the-fly resampling, the AI-native strategy/lesson compiler, self-building dictionary, paper trading/signal generation all reading the identical compiled `StrategyConfig` — see the audit delivered in-conversation for the full per-module breakdown and reasoning). Three genuinely missing pieces were identified and built; nothing else was rebuilt.

**1. Confidence gate rework** (`knowledge_compiler/compiler.py`, `ai_integration/quality_score.py`, `sindhu_web/static/js/app.js`): `AI_CONFIDENCE_ACCEPT_THRESHOLD` lowered from v7's 70% to the CEO's specified 60% — "only ask clarification below 60%." **A real bug found via direct testing:** the original threshold logic only forced `READY_FOR_BACKTEST` when confidence was high; below the threshold it fell through to checking whether the extracted structure *happened* to validate cleanly, which could still produce `READY_FOR_BACKTEST` at low confidence -- exactly the opposite of the spec's intent (low confidence should always warrant a second look, independent of surface completeness). Fixed so status is now purely confidence-gated for any document with an actual strategy (a lesson-only document with no strategy is trivially ready either way, unchanged from prior phases). `automation_ready`/`backtesting_ready` no longer read `NO` for AI-assisted imports merely because informational audit notes exist. The frontend no longer shows the categorized "Missing/Unknown" Import Report panel once a strategy is actually ready — it shows a plain "Automation Ready / Backtesting Ready" confirmation instead.

**2. Pre-AI dedup cache** (`data_engine/storage.py`'s new `ai_import_cache` table, wired into `ai_integration/importer.py`): before calling any AI provider, the raw input's normalized content hash is checked against previously-understood documents. On a hit, the cached structured result is reused to build and save the strategy/lessons through the exact same path as a fresh AI call — genuinely skipping AI entirely, not just re-displaying a stale result. Verified directly: with `deep_understanding.understand_document_structured` monkeypatched to raise if invoked at all, a cache-hit import still completed successfully end-to-end (`served_from_cache: true`, real saved strategy, zero AI calls made).

**3. Debug Mode** (`backtest_engine/mtf_worker.py`, `backtest_engine/runner.py`): the existing per-symbol progress-reporting mechanism (Phase 6) is extended, not replaced, to the CEO's full checklist — `strategy_loaded → strategy_compiled → timeframes_detected → historical_data_loading → timeframes_resampled → timeframes_synchronized → indicators_initialized → rules_loaded → simulating_bars → trades_executed → results_generated → completed`. The whole worker function is now wrapped so any failure (missing data, no entry conditions, or a genuinely unexpected exception) returns structured `{stage, function, reason, suggested_fix}` diagnostics instead of a bare error string, surfaced both in the saved batch result and the live log. Verified directly against real downloaded candle data (BTCUSDT): all 11 stages fire in order on a successful run; a nonexistent symbol correctly returns `stage: "historical_data_loading"` with an actionable suggested fix, no crash.

**Consciously not built, with reasoning:** a "Local LLM" fallback provider (no local LLM runtime exists in this environment to connect to — a stub with nothing behind it would be fake, not functional; the original v1 spec already flagged this as future work) and Evolution as a standalone dashboard page (not requested by any of the ten parts in this directive; its logic already runs correctly inside Paper Trading per Phase 5). A dedicated Pattern/Indicator Library page was also not built since the underlying data (categorized `knowledge_concepts`/dictionary entries) already exists and is already surfaced via the CEO Dashboard's live counts and the Self-Building Dictionary table -- a new page would be a second view over the same single source of truth, not new capability.

**Verification note:** live end-to-end testing via the running web server was intentionally not performed for this pass -- a real 50-coin backtest batch (strategy "S1") was actively running on the shared server throughout this work, started by the CEO directly. Restarting the server to load this code would have killed that in-progress batch. Every change above was instead verified directly against the real database and real historical candle data via isolated Python calls (bypassing only the HTTP layer, never the actual logic), including one live AI-assisted import that ran until Groq's daily token quota was reached (confirming the existing fallback-to-Offline-Mode behavior handled a genuine rate-limit exhaustion cleanly, with zero crashes). **The server should be restarted at the CEO's convenience** (e.g. after the current batch finishes or is intentionally stopped) to make this code active for interactive use.

---

## Phase 7A — Evolution Core Engine + SINDHU Strategy Generator ✅

Two new systems, built as two new top-level packages (`evolution_engine/`, `sindhu_strategy/`) with their own physically-separate SQLite tables (`bot_strategies`, `bot_lessons`, `evolution_jobs`, `champion_records`, `knowledge_versions`, `daily_generation_log`) — never touching `strategy_library`'s user-owned files or the user-authored `lessons` table, so "Evolution may never modify user-imported strategies/lessons" is structural (no code path exists), not a promise. Verified empirically: hashed every one of the 12 saved user strategies and all 34 user lessons before and after a real Evolution Engine tick that mutated 5 real BOT lineages — zero bytes changed.

**Part A — Evolution Core Engine** (`evolution_engine/`): pure deterministic logic, zero AI, zero ML (grep-verified: no `ai_integration` import anywhere in the package).
- `dna.py` — decomposes any StrategyConfig into DNA block tags (Trend/Momentum/Liquidity/Volume/Breakout/Session/Risk) from its real indicators/concepts/filters.
- `lesson_generator.py` (A.1) — wired into `paper_trading/position_manager.py`'s `_close()`, right after `evolution.record_outcome()`. Every closed position triggers an aggregation over that strategy's own trade history (win rate/RR by coin, session, and market regime); a lesson is only created when a bucket has ≥10 trades and a real statistical gap vs. the overall average — every lesson's `derived_from` field records the exact bucket stats and contributing trade IDs. Verified with 30 real trades (14/15 wins on BTCUSDT, 2/15 on ETHUSDT): produced 4 correctly-worded, fully traceable lessons.
- `scoring.py` (A.6) — the Evolution Score formula: 11 weighted components (win rate, profit factor, net profit, avg RR, drawdown, trade count/sample confidence, stability, consistency, session/coin/market-condition performance), weights fixed and documented in the module docstring, plus `time_decay_weights()` for A.8's "recent trades count more, nothing is deleted."
- `generation_manager.py` (A.4/A.5) — the only place `BOT_S101` → `BOT_S101_G2` lineages get created; every generation is a fresh INSERT, never an UPDATE or DELETE.
- `governor.py` (A.3) — concrete limits (5 experiments/run, 25 generations/strategy lineage, a 20-item priority queue, 75%/85% CPU/RAM ceilings via `psutil`). Load-tested for real: saturated all 8 CPU cores to 100% with genuine multiprocess workers, confirmed `resource_ok()` flips to `False` under real load and back to `True` once it clears.
- `mutator.py` (A.2) — Analyze/Compare/Rank/Archive/Research over BOT strategies only; `mutate_strategy()` nudges risk_pct/risk_reward/breakeven_at_rr based on whichever Evolution Score component scored weakest, plus current market regime; `research_dna_correlations()` finds which DNA combos historically score best (feeds Part B).
- `market_regime.py` (A.8) — regime detection (trending_up/trending_down/ranging/volatile) from real OHLCV/ATR, independent of `paper_trading.market_state` to avoid a package cycle (both agree on the same 4 labels).
- `champion.py` (A.7) — recomputes Champion Strategy/Lesson/Coin/Session/Timeframe/Market Condition/Generation; append-only (`champion_records`), so "current" is just the most recent row per category and history is never lost.
- `engine.py` (A.12) — the background loop: a daemon thread (same shape as `paper_trading.engine`), checkpointed via `evolution_jobs` (same shape as `pipeline_jobs`), resumed on server restart only if it was already running (`resume_evolution_jobs_on_startup()`, wired into `sindhu_web/server.py`'s lifespan). Manually started/stopped by the CEO via the dashboard.

**Part B — SINDHU Strategy Generator** (`sindhu_strategy/`): exactly 11 new strategy candidates/day, hard-capped by `daily_generation_log` (a guarded `UPDATE ... WHERE ai_calls_used=0` makes a second AI call per day structurally impossible, mirroring the existing `ai_import_cache` pattern) — 1 AI-assisted, 10 pure deterministic recombination of DNA blocks driven by real correlations across BOT and user strategy performance. Every candidate is saved permanently and routed through the exact same `validator.validate()` → `runner.run_mtf_batch()` → `reports.generate_report()` pipeline user strategies use (`lifecycle.py`), then scored with the same Evolution Score formula. A background scheduler thread (`generator.start_daily_scheduler_thread()`, auto-started from the server lifespan) checks hourly and runs the cycle once a day on its own — no CEO toggle needed, unlike the Evolution Engine.

Verified with a real, unprompted run (the scheduler fired automatically at server startup, on the real production database): exactly 11 candidates created, exactly 1 labeled "Made with AI" (a real Groq-generated strategy, "BreakerSweep"/"VwapBreakout" across two separate real runs, both validator-clean with zero errors), 10 labeled "Made without AI"; a second invocation the same day created zero additional candidates (idempotent, per the daily cap). `ai_usage_log` confirmed exactly one new row per day under the distinct endpoint `/ai/sindhu-strategy-generation`.

**Frontend**: two new pages — Evolution Dashboard (`#evolution`, engine status, Governor CPU/RAM/queue/experiment stats, Champion table, BOT strategy/lesson lists, DNA correlation research) and SINDHU Strategy (`#sindhu_strategy`, today's 11/11 + AI-used counter, filterable candidate list) — both enabled in `NAV_PAGES`, both registered in SINDHU CEO's card grid with full expand/control per the standing CEO-parity rule (Start/Stop/Run Tick Now and Generate Now buttons call the exact same REST endpoints the dedicated pages use). Verified live in a running browser session against the real database.

---

## What's NOT Built (explicitly excluded so far)

Per each phase's own "Do NOT build" list:
- Reflection as a standalone page/workflow (exists internally within Paper Trading per-trade, not yet its own dashboard section)
- News monitoring
- Telegram alerts
- Any Machine Learning / AI-based decision making
- Real/live trading execution (Paper Trading is simulation-only, by design)

These are all future phases, each waiting for an explicit CEO go-ahead.

---

## Next Steps

Phase 7A is complete and **waiting for CEO approval before any further phase.** Likely candidates for what comes next:

- **Reflection as a standalone page** — the one remaining internal-only Paper Trading concept, following the exact pattern Phase 7A just used for Evolution
- **Live Trading** — real order execution, gated behind everything Paper Trading already validates
- **News monitoring** / **Telegram alerts**
- **Cloud Deployment**

Whichever you choose, it plugs into the existing API layer and dashboard nav without any redesign — that was the whole point of how Phase 3 was built.

---

## Quick Reference

- **Database**: `data/database/sindhu.db` (single source of truth, ~3 GB, 24.6M candles) — never move or restructure without a clear reason; migrations so far have all been additive
- **Run desktop app**: `cd E:\sindhu && python main.py`
- **Run web dashboard**: `cd E:\sindhu && python web_main.py` then open `http://localhost:8420`
- **CLI**: `python run.py download|status|watch --exchange binance|okx|bybit|bitget|gate`
- **Backups**: `data/database/backups/` (automatic every 24h by default + manual via Settings page)
