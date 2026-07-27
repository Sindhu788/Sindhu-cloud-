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
- [ ] 7. System Health Dashboard
- [ ] 8. Automated Backup Engine
- [ ] 9. Autonomous Strategy Research
- [ ] 10. Source Quality Filter

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
