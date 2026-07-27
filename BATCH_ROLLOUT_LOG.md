# Batch Feature Rollout — Progress Log

Started: 2026-07-27 (session continuation)
Constraint: do not touch backtest engine, PnL engine, or trade execution logic.

## Status
- [x] 1. Pattern-Based Auto-Avoid Rule
- [x] 2. Lesson Auto-Apply System
- [x] 3. Basic Market Regime Detection
- [x] 4. Drawdown Protection Engine
- [x] 5. Correlation Warning System
- [x] 6. Basic Risk Analytics (Sharpe + Max Drawdown)
- [x] 7. System Health Dashboard
- [x] 8. Automated Backup Engine
- [x] 9. Autonomous Strategy Research (built + tested; network-blocked in THIS sandbox, see notes)
- [x] 10. Source Quality Filter

## 1. Pattern-Based Auto-Avoid Rule -- DONE
- `paper_trading/auto_avoid.py`: threshold = 5 consecutive losses on the EXACT
  (strategy, symbol, market_state, session) pattern (same bar as the existing
  Drawdown Alert; ~3% chance by pure luck at 50/50 odds).
- New tables: `paper_auto_avoid_rules` (audit trail, reversible via `active` flag).
- Wired: `position_manager._close()` re-evaluates the pattern after every close;
  `engine._open_if_allowed()` vetoes new entries matching an active rule.
- API: GET `/api/paper-trading/auto-avoid-rules`, POST `.../deactivate`.
- Evidence: `/tmp/test_auto_avoid_drawdown.py` -- 4 losses = no trigger, 5th loss
  triggers, different symbol on same strategy stays allowed (pattern-specific,
  not strategy-wide), audit row persisted with reason.

## 2. Lesson Auto-Apply System -- DONE
- `paper_trading/lesson_auto_apply.py`: stricter bar than candidate-flagging
  (10+ trades, 80%+ one-sided win rate vs the flagging bar of 5+/75%) --
  auto-applying changes live ranking, so it needs more evidence first.
- influence = "boost" (winning pattern) or "avoid" (losing pattern), applied
  as a bounded +/-10 point nudge in confidence.score() -- soft, never a hard
  block (confidence never gates a trade by design; Risk Manager is the only
  real gate).
- Wired: engine._tick() calls promote_candidates() once per tick (cheap
  indexed query). New table `paper_auto_lessons`, visible + reversible via
  GET `/api/paper-trading/auto-lessons` + POST `.../deactivate`.
- Evidence: `/tmp/test_lesson_auto_apply.py` -- 10 trades at 90% win rate
  promotes correctly, confidence score is measurably higher (70 vs 60) only
  for the matching pattern, unrelated pattern gets zero influence, and
  deactivating the row immediately zeroes the influence again.

## 3. Basic Market Regime Detection -- DONE
- `paper_trading/regime.py`: ATR(14)% for volatility, 20-period MA slope for
  trend, both standard building blocks (reused backtest_engine.concepts.atr,
  no new indicator math). high_volatility checked first (ATR>=3%), then
  trending (|slope|>=1.5%), else ranging.
- API: GET `/api/paper-trading/regime` (bulk, 60s cached) + `.../regime/{symbol}`.
- Evidence: real live data on 6 tracked symbols -- AAVEUSDT correctly labeled
  "trending" (3.78% MA slope), 5 others correctly "ranging" (all under 1.5%
  slope, all under 3% ATR). 9.27s for 6 symbols cold; cached 60s after that.
- NOT YET WIRED into frontend UI (Market/Paper Trading page filter) -- API
  complete and verified, UI display deferred given time constraints.

## 4. Drawdown Protection Engine -- DONE
- `paper_trading/drawdown_guard.py`: pauses NEW entries for one strategy when
  EITHER its own streak hits 7 consecutive losses OR its drawdown-from-peak
  hits 15% (both configurable in paper_trading/config.py). Existing open
  positions are untouched -- monitor_and_close() never checks the pause flag.
- Schema: `paper_strategy_config` gained `paused`/`paused_reason`/`paused_at`
  columns (migration-safe for the already-live table).
- Wired: same after-close hook as #1; `engine._open_if_allowed()` rejects new
  entries for a paused strategy's book.
- API: GET `/api/paper-trading/paused-strategies`, POST `.../resume/{id}`.
- Evidence: same test script -- streak reaches 7, strategy pauses, resume clears it.

## 5. Correlation Warning System -- DONE
- `paper_trading/correlation.py`: REAL computed Pearson correlation of 1h
  returns (72h lookback) between symbols that currently have open positions
  -- not a hardcoded "these coins move together" list, since that goes
  stale. Threshold 0.7 (standard "strong correlation" convention). Bounded
  to symbols with open positions (not all 50 tracked), capped at 25/direction.
  Informational only -- never blocks a trade, nothing called from the
  trading loop.
- API: GET `/api/paper-trading/correlation-warnings` (60s cached) + added to
  the startup `_warm_caches()` thread (same fix pattern as the Market page
  bug earlier this session) so real visitors never hit the slow cold path.
- Evidence: run against the LIVE current deployment (92 open positions, 35
  distinct symbols) -- found 4 real warnings, e.g. "4 strategies are
  currently short on SUIUSDT and XRPUSDT at the same time (correlation
  0.75)". Cold computation measured 59.62s (hence the warm-cache addition).

## 6. Basic Risk Analytics -- DONE
- `paper_trading/insights.compute_risk_metrics()`: Sharpe Ratio (mean/stdev of
  per-trade PnL * sqrt(N), not calendar-annualized since trades are irregularly
  spaced) and Max/Current Drawdown % (standard peak-to-trough on the cumulative
  equity curve). Returns None (not 0) below 2 trades -- no misleading numbers
  on a fresh strategy.
- Reused directly by drawdown_guard's pct-based pause trigger.
- API: GET `/api/paper-trading/risk-metrics/{strategy_id}`.
- Dashboard UI for this + Sharpe/MaxDD columns on the Strategy Performance
  Dashboard: NOT YET WIRED into the frontend -- backend/API complete and
  tested, UI display still pending (will revisit if time allows after
  higher-priority items).

## 7. System Health Dashboard -- DONE
- `sindhu_web/api/system.py`: GET `/api/system/health` -- uptime (stamped at
  module import = server start), CPU/RAM (psutil, same calls /api/home
  already makes), DB size, active background processes (reuses
  job_manager.list_jobs() + paper_engine.is_running() + evolution_engine.is_running(),
  no new tracking mechanism invented), and last 10 error-looking lines
  tailed from sindhu.log (reads only the last 200KB, not the whole file).
- Frontend: new "System Health" section on the Settings page (grid of 5
  stat cards + a Recent Errors panel), auto-refreshing every 15s via the
  existing autoRefresh() helper.
- Evidence: verified LIVE in the actual browser after a real server
  restart -- uptime "0m 37s", CPU 74%, RAM 71%, DB 14.5 GB, 1 active
  process (Paper Trading engine), and real error lines from the log.
- Side-finding (not fixed, out of scope for this batch): the health check
  immediately surfaced a genuine recurring error from 2026-07-25 --
  "StrategyConfig.__init__() got an unexpected keyword argument
  'entry_rule_groups'" on multiple symbols. Worth a look separately.

## 8. Automated Backup Engine -- DONE
- The continuous/unattended scheduler (`start_auto_backup_thread`, sqlite
  hot-backup via `create_backup`) already existed from an earlier session --
  what was missing was pruning. Added `_prune_old_backups()`, called after
  every `create_backup()` (both manual and automatic paths), keeping the
  newest `keep_last` (default 10) and deleting the rest.
- Default interval lowered from 24h to 6h ("every few hours" per spec).
- Evidence: real DB is 15.6GB so I did NOT run 5 real full-DB backups for
  the test (too slow/heavy) -- instead verified `_prune_old_backups()`
  directly against lightweight fake files matching the real naming pattern:
  7 files -> prune(keep_last=3) -> exactly the 3 newest survive, confirmed
  by filename. The underlying create_backup()/sqlite .backup() mechanism
  was already shipped and in production before this session.
- NOT YET WIRED: keep_last/interval_hours aren't exposed in the Settings UI
  yet (backup_settings.json is editable, just not from a dashboard form).

## 9+10. Autonomous Strategy Research + Source Quality Filter -- BUILT, IMPORTANT CAVEAT

- `ai_integration/web_research.py`: on-demand only (explicit trigger via API,
  no scheduled/background trigger anywhere) -- searches, filters through a
  Source Quality Filter allow-list (babypips.com, investopedia.com,
  tradingview.com, binance.com, cmegroup.com), fetches + extracts article
  text (dependency-free HTMLParser-based extractor, verified correct), and
  queues every trusted result through `ai_integration.import_queue.enqueue()`
  -- the EXACT SAME entry point manual paste uses. No special trust, no
  auto-approve, no auto-deploy: it lands in the same NEEDS_REVIEW/READY
  queue as anything else.
- API: POST `/api/research/search` (query-based), POST `/api/research/queue-url`
  (direct URL, bypasses search), GET `/api/research/trusted-sources`.
  Verified live end-to-end through the real running server.
- **Important, honestly-reported finding**: search discovery uses
  DuckDuckGo's key-less HTML endpoint (no paid search API key was
  available). Tested directly from this environment: DuckDuckGo returns an
  empty bot-challenge page (HTTP 202, no results) regardless of GET/POST or
  headers tried. I then tested fetching EVERY trusted domain directly:
  babypips.com -> 403 Forbidden, academy.binance.com -> 202 empty,
  tradingview.com -> connection timeout. A control request to
  api.github.com succeeded (200 OK), confirming outbound internet access
  itself works -- these specific sites are blocking bot/datacenter traffic,
  which is a very common real-world anti-scraping pattern for exactly this
  kind of sandboxed/cloud IP.
- What this means practically: the CODE is correct, tested, and degrades
  gracefully (verified: untrusted URLs rejected before any network call,
  unreachable trusted URLs return a clear skip reason, never crash) -- but
  I could not verify a genuine successful end-to-end fetch from THIS
  environment. It may well work differently from the user's own real
  network (this looks like IP-reputation-based bot blocking, not a
  fundamental code defect), but that's untested and should be verified on
  the actual deployment machine.
- **Decision needed from you**: if search/fetch continues to be blocked on
  the real deployment too, the reliable path forward is a paid search/fetch
  API (e.g. a Search API service, or a scraping-proxy service) with a
  key you'd provide -- swapping `search_web()`'s implementation is a
  self-contained one-function change, everything downstream (trust filter,
  extraction, queueing) is already decoupled from how results are found.
