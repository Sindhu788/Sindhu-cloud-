# Phase 8 — Paper Trading Execution ($100 capital) — A-to-Z Verification (COMPLETE)

Per `PROJECT_PLAN.md`'s original 9-phase roadmap, Phase 8 = "Paper Trading Execution
($100 capital)". This is a read-only audit of the real, already-live paper trading pipeline
(built and extended over many sessions under PROGRESS.md's own numbering as "Phase 5 — Paper
Trading Engine" plus every later batch that touched it, most recently Grand Master Batch #2).
No behavior was assumed -- every claim below was traced against the current source, file:line.

## A-to-Z pipeline (candidate generated -> closed trade on dashboard)

1. **Tick fires** -- `engine._loop()` (`paper_trading/engine.py:336-338`), 60s default cadence
   (`tick_interval_seconds`), re-read from settings every iteration (live-reloadable, no restart).
2. **Kill switch / universe build** -- resolves exchange + tradeable symbol list (engine.py:357-387).
3. **Coin filtering** -- blacklist -> demoted-coin filter -> `coin_filter.shortlist()` (top N) ->
   pinned coins re-added (engine.py:393-403).
4. **Candle warm-up** -- `live_feed.refresh_coins()` (local mode only, engine.py:405).
5. **Market classification** -- `market_state.classify()` per symbol (engine.py:416).
6. **Existing positions monitored FIRST** -- `position_manager.monitor_and_close()`
   (engine.py:423-426) checks every open position's stop/target against this tick's candle
   high/low, before any new-signal logic runs for that symbol.
7. **Event gate** -- `self._event_tracker.check(snapshot)` (engine.py:428); no new event means no
   candidate generation this tick for that symbol.
8. **Candidate generation** -- `strategy_matcher` + `lesson_matcher` -> `signal_generator
   .generate_candidates()` (engine.py:579-586).
9. **Per-candidate approval + dedupe** -- veto flags, `guards.signal_fingerprint()` dedup,
   `confidence.score()` (engine.py:590-601).
10. **Grouped by book, ranked** -- one winner per book via `priority_rule` (default
    `confidence_and_win_rate`) (engine.py:614-632).
11. **Ensemble Voting Confirmation** (opt-in) -- requires N agreeing strategies (engine.py:638-646).
12. **`_open_if_allowed()` gate chain** (engine.py:654-712): Trade Reservation -> strategy-paused
    -> Auto-Avoid -> HTF Confluence (opt-in) -> Volume-Spike (opt-in) -> Position Lock ->
    Cooldown -> Opposite-Signal policy -> **`risk_manager.evaluate()`** (10 gates, table below) ->
    Dry-Run check.
13. **Position opened** -- `position_manager.open_position()` (engine.py:719): slippage (0.05%)
    then spread (0.03%, modeled as a separate real-world cost, not folded into slippage) applied
    to entry; stop/take-profit re-validated against the real fill; persisted via
    `storage.open_paper_position()`.
14. **Decision logged** -- buffered, flushed once per tick in one batched write
    (`storage.log_paper_decisions_batch()`, engine.py:769-796).
15. **Post-open side effects** -- confluence-history logging + Sanity Check Alert, both purely
    informational (engine.py:731-749).
16. **Automatic Telegram send** -- confluence/Wilson-reliability tier gate
    (`evaluate_auto_send_tier`, automatic path only) then, if qualified,
    `telegram_bot.send_signal_for_position()`'s 13-gate chain (table below) (engine.py:759-765).
17. **Every subsequent tick** -- `monitor_and_close()` re-checks against fresh data; Profit-Lock
    trailing stop may tighten the stop and fire a break-even Telegram notification.
18. **Orphaned-position safety net** -- `engine._monitor_orphaned_positions()` (engine.py:535-577)
    keeps monitoring a position whose symbol drops out of the shortlist, or raises an alert if the
    symbol vanishes from the exchange entirely.
19. **Exit** -- `_check_exit()` tests stop-loss before take-profit against the candle's high/low
    (matches backtest behavior) -> `position_manager._close()` (position_manager.py:237-306):
    slippage + spread applied to exit, PnL computed, single `storage.close_paper_position()` call
    writes the closed row and updates running account totals.
20. **Post-close cascade** -- `evolution.record_outcome()`, `lesson_generator
    .analyze_and_generate_lessons()`, `auto_avoid.evaluate_pattern()`, conditionally
    `drawdown_guard`/`account_drawdown_guard`, `telegram_bot.send_close_followup()`,
    `ai_trade_review.review_trade()` -- each independently try/excepted so one failure never
    un-records the trade.
21. **Dashboard visibility** -- `GET /api/paper-trading/positions`/`/trades` (closed rows),
    `/decisions` (full accept/reject history), `/telegram/log` (delivery record) -- all read live
    from `paper_positions`/`paper_decision_log`/`telegram_message_log`, no caching layer between.

## `risk_manager.evaluate()` -- exact gate order (first rejection wins)

| # | Gate | Rejects when |
|---|------|--------------|
| 1 | Kill switch | Active -- halts all trading |
| 2 | Account-wide drawdown circuit breaker | Combined balance crossed its pause threshold |
| 3 | Time-of-day filter | Current UTC hour is in the configured blocked window |
| 4 | Max open coins per book | Book already at `max_open_trades` distinct coins |
| 5 | Missing stop-loss | No computable stop -- risk can't be sized |
| 6 | Slippage-aware filter (opt-in) | Realistic slipped entry vs. stop is unfavorable |
| 7 | Account balance depleted | Book balance <= 0 |
| 8 | Dynamic risk sizing (opt-in) | Adjusts risk %, not itself a rejection |
| 9 | Zero position size | Sizing formula computes size <= 0 |
| 10 | Portfolio-wide per-coin risk cap (Batch #2, Phase 3.3) | This coin's total risk across every strategy + this trade > `max_portfolio_risk_pct_per_coin`% of `initial_balance` |

## `telegram_bot.send_signal_for_position()` -- exact gate order

| # | Gate | Notes |
|---|------|-------|
| 1 | Position exists | |
| 2 | Kill switch | |
| 3 | Telegram master switch | |
| 4 | Rate limit | Messages/hour |
| 5 | Signal Freshness Gate | **Live network price fetch** + drift check |
| 6 | Cross-Exchange Sanity Check (Batch #2, Phase 4.7, opt-in) | **2nd live network call** |
| 7 | Minimum Take-Profit Distance | |
| 8 | Duplicate-Signal Protection | Same strategy+coin+direction |
| 9 | Signal Congestion Filter (Batch #2, Phase 2.5) | Different strategies, same coin+direction |
| 10 | Minimum Confidence % (off by default) | |
| 11 | Expected-Value Gate (Batch #2, Phase 1.4, always on) | Strategy's real avg $/trade negative |
| 12 | Strategy Snooze | |
| 13 | Group-Selection Mode filter | |

Everything after gate 13 is message construction/sending -- no further rejection gates.
**Note:** the confluence/25-trade Wilson-reliability gate lives *outside* this function, applied
only by the automatic path (`engine.py:759-765`) before this function is even called -- see
Finding 2 below.

## Real costs modeled

Slippage (0.05%, entry + exit) and spread (0.03%, entry + exit, Batch #2 Phase 1.2) -- modeled as
two separate, additive real-world costs. **No commission/fee is modeled anywhere** -- see
Finding 3.

## "No in-memory position cache" claim -- VERIFIED TRUE

Every open-position read on the hot path (`monitor_and_close`, `_monitor_orphaned_positions`,
`risk_manager.evaluate`, `guards.position_locked`/`cooldown_active`) is a live SQL query against
`paper_positions`, executed fresh every call -- confirmed by direct read, not by trusting existing
comments. Grepped for `lru_cache`/`@cache`/module-level dicts touching position state: none found.
The one exception, `guards.GuardState`'s per-tick trade-reservation/dedup set, is explicitly
documented as a tick-scoped safety net (reset every tick via `release_all()`, engine.py:408) and
never caches position *data* -- it only prevents two candidates opening the same book+symbol
twice within one tick pass.

## Findings

1. **FIXED** (this pass) -- `send_signal_for_position()` ran its two live-network gates (Signal
   Freshness, Cross-Exchange Sanity) *before* six pure in-process/DB gates (TP distance,
   duplicate, congestion, confidence, expected-value, snooze, group-filter). Every gate is
   independent (first-rejection-wins, no gate depends on another's side effect), so reordering
   the cheap gates first changes no outcome -- it just avoids paying for a live network
   round-trip on a signal that a free, deterministic check would have rejected anyway. Reordered;
   full test suite re-run green after the change.
2. **FLAGGED, not changed** -- the confluence/Wilson-reliability gate is only applied on the
   *automatic* Telegram send path, not inside `send_signal_for_position()` itself. A manual send
   (dashboard "Send" button) can dispatch a signal for a pattern with zero trade history behind
   it. This may be intentional (a manual override is a different trust level than an automatic
   send), but it means the "statistically reliable" property this codebase clearly cares about
   does not hold uniformly across every send path. Left as-is pending a CEO decision on whether
   manual sends should also be gated.
3. **FLAGGED, not changed** -- no commission/fee is modeled in paper trading, only slippage and
   spread. Not a bug (it was never in the original spec), but worth naming explicitly: paper PnL
   will run somewhat better than a real funded account would, since every live exchange also
   charges a taker/maker fee on top of spread. Left as a documented simplification, not built,
   since adding fee modeling is a scope decision (which exchange's fee schedule? maker vs taker?
   per-strategy override?) rather than a verification fix.
4. **No issue** -- `guards.GuardState`'s in-memory reservation set is the one piece of tick-scoped
   in-memory state on the hot path; it's correctly bounded and reset every tick, does not
   contradict the "always reads fresh from storage" claim.

No dead code or defined-but-never-called gates were found in `risk_manager.evaluate`,
`telegram_bot.send_signal_for_position`, or `position_manager` -- every function traced is
reachable from the tick loop or a real dashboard API route.

## Conclusion

**Phase 8 (Paper Trading Execution) is complete, correctly wired end-to-end, and verified against
the current source rather than assumed from prior documentation.** One safe, zero-behavior-change
efficiency fix applied (Finding 1). Two items flagged for a CEO decision, not auto-fixed
(Findings 2-3), since both are policy/scope calls rather than defects.
