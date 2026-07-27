# Batch Feature Rollout — Progress Log

Started: 2026-07-27 (session continuation)
Constraint: do not touch backtest engine, PnL engine, or trade execution logic.

## Status
- [x] 1. Pattern-Based Auto-Avoid Rule
- [ ] 2. Lesson Auto-Apply System
- [ ] 3. Basic Market Regime Detection
- [x] 4. Drawdown Protection Engine
- [ ] 5. Correlation Warning System
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
