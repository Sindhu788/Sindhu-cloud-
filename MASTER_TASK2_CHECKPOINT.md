# Master Task 2 — Checkpoint

Resume point if interrupted (power loss / session end / usage limit). Update
after each real sub-step.

## GLOBAL RULES (must hold throughout)
- Never weaken/bypass Wilson 25-trade, Evolution 100-trade, rollback,
  Confluence, Freshness, Incomplete Lock.
- Never delete real data — archive instead.
- Full test suite after each part (expect ~896/896, same baseline as
  New Batch 4).
- Any genuinely critical decision that needs CEO input: skip it, keep going,
  ask at the very end in one simple English summary.

## Fact-check done before starting (recorded honestly)
- Task says "33 strategies (8 profitable + 25 losing)". Live count today is
  **39 real (non-variant) strategies: 10 profitable (PF>=1.0) + 29 losing**.
  The "33" figure is stale (from before New Batch 4 added 5 more strategies
  today). Proceeding with the real live count of 39. There are also 10
  "[Medium]"/"[Strict]" variant strategies in the library (built purely for
  the Optimizer/Lifecycle comparison tool in prior batches) — these are
  EXCLUDED from paper-trading activation; they are not independent trading
  ideas, just filter-strictness comparisons of the same 5 base strategies.
  This is a judgment call, not a critical blocker — flagged in final report.

## PART 1 — Activate all strategies in paper trading
- [x] Enable all 39 base (non-variant) strategies via
      storage.save_paper_strategy_config(enabled=True) for any not already
      enabled (18 already were, 21 newly activated -> 39 total).
- [x] Verified with real evidence: storage.list_paper_strategy_configs()
      shows 39/39 enabled=True, AND strategy_matcher.relevant_strategies()
      (the exact function the live engine tick calls every cycle) returns
      all 39 for BTCUSDT across every market_state (trending_up,
      trending_down, ranging, volatile) — real engine-level confirmation,
      not just a config flag.
STATUS: DONE

## PART 2 — Two dashboard sections (Strategy Lifecycle / Paper Trading page)
- [x] "Profitable Strategies" section (PF > 1.0 baseline backtest, 10 today)
- [x] "Under Evaluation" section (the other 29) — honest label, not "losing"
      as a header (individual cards still show real losing PF/PnL)
- [x] Identical fields both sections: Backtest PF, Trades, Wins, Losses,
      Win Ratio, PnL($), Current Balance, Confidence, Streak — same row
      renderer function for both, so neither can ever get less detail
- [x] Pill-tab toggle ("Profitable Strategies (10)" / "Under Evaluation (29)")
      on the Paper Trading page's Analytics tab, both tables in the DOM,
      instant client-side switch (no re-fetch)
- Location: Paper Trading page -> Analytics tab -> "Strategy Comparison"
  section (replaced the old single side-by-side table). Verified live in
  browser: toggle switches correctly, both tables show real per-strategy
  numbers (e.g. Under Evaluation: "4H Fractal Sweep Reversal" PF 0.6611,
  3 trades, 2 wins, 1 loss, 66.7%, +$1.30, $101.30 balance).
- Bug found + fixed during verification: /api/strategy-lifecycle (the data
  source for the Profitable/Evaluation split) was taking 45s to respond --
  far past the frontend's 15s fetch timeout -- so the split silently fell
  back to "0 profitable / all under evaluation" every time. Root cause and
  fix recorded under Part 4.2 below (this bug and Part 4.2 turned out to be
  the same underlying issue).
STATUS: DONE

## PART 3 — Advanced per-strategy controls
- [x] ON/OFF toggle — existing /api/paper-trading/strategy-config/{id}
      endpoint, now also wired into the new "Strategy Controls" modal
- [x] Balance/stats reset per strategy, archived not deleted (new table
      paper_strategy_stat_archives + storage.reset_strategy_stats(), mirrors
      existing system-wide reset_paper_balance()/paper_balance_resets).
      New endpoints: GET .../reset-stats/preview, POST .../reset-stats,
      GET .../reset-history (shows the archived record in the modal)
- [x] Pause/Resume manual — new POST .../pause (reuses
      storage.set_strategy_paused, same flag Drawdown Protection's
      automatic pause already uses) + POST .../resume
- [x] Per-strategy risk % override — new nullable column risk_pct_override
      on paper_strategy_config (own dedicated setter
      set_strategy_risk_overrides, never touched by the plain enable/
      disable save, same pattern as paused/capital_multiplier already use)
      + risk_manager.evaluate() reads it before the global default
- [x] Per-strategy max-open-positions override — new nullable column
      max_open_trades_override, same setter; bounded 1-20 at the API layer
      (rejects 0/negative/unbounded); risk_manager.evaluate() reads it first
- [x] Tested live in browser (4H Fractal Sweep Reversal, 53c80e6c5b6a):
      set risk override to 0.5% (saved, confirmed via GET), paused it
      manually (banner + reason shown correctly), resumed it (confirmed
      cleared from /api/paper-trading/paused-strategies), cleared the test
      override back to null afterwards -- strategy left in its original
      state, zero residue.
- New UI: "Controls" button per row in both Profitable/Under Evaluation
  tables opens a modal with all 5 controls + reset history.
STATUS: DONE

## PART 4 — Backend fixes
### 4.1 Orphan rows (root cause investigation)
Traced thoroughly (not just re-cleaned):
- No FOREIGN KEY exists between backtest_results/backtest_trades and
  backtest_batches (confirmed from CREATE TABLE statements) — nothing stops
  a child row from being written/surviving without its parent.
- Every save_result/save_trades call site lives in backtest_engine/runner.py
  (confirmed by grep across whole repo), and in both run_batch and
  run_mtf_batch, create_batch() always executes-before, in the same
  synchronous call chain, before any worker is spawned (workers never touch
  storage directly — confirmed mtf_worker.py has zero storage references).
  No in-code race found that lets a child write happen before/without its
  parent committing, matching the prior audit's own "bounded investigation,
  cause not found" conclusion — this needs to be closed at the DB layer
  instead of chased further at the application layer.
- PERMANENT FIX: add a real FOREIGN KEY (batch_id) constraint on
  backtest_results and backtest_trades + turn on PRAGMA foreign_keys=ON on
  every connection. Going forward this makes it structurally IMPOSSIBLE for
  a child row to be written/survive without a parent row — SQLite itself
  rejects the write, loudly, instead of silently creating an orphan.
  Existing orphans (created before this fix) are NOT deleted — each unique
  orphaned batch_id gets one synthesized recovery row inserted into
  backtest_batches (status='orphan_recovered', strategy_name=
  '[Recovered orphan -- original batch record lost]') so old data stays
  reachable/archived rather than being silently dropped by the migration.
- [x] Implemented `_migrate_backtest_fk_constraints()` in data_engine/
      storage.py (idempotent, runs once via init_db()); reads each table's
      REAL current columns via PRAGMA table_info rather than a hardcoded
      schema string (backtest_trades had grown to 24 real columns vs the
      6-column base schema I first assumed -- caught by a failed first
      attempt that SQLite's transactional DDL rolled back cleanly with zero
      data loss, verified before retrying with the fixed, column-preserving
      version). Base `_SCHEMA` also updated so a brand-new database gets
      the FK immediately. `PRAGMA foreign_keys=ON` added to every
      connection in get_conn() (SQLite doesn't enforce FKs by default even
      when declared).
- [x] Took a full hot backup first via the existing backup.create_backup()
      (sqlite3 .backup() API, safe on a live DB) before touching anything --
      sindhu_20260831_132540.db
- [x] Ran the migration with the server fully stopped (no concurrent
      writers): 268 batches after (259 + 9 recovered), 7,950 results,
      2,316,553 trades -- same row counts as before, zero data lost.
      9 real orphaned batch_ids found and given a synthesized
      `backtest_batches` row each (status 'orphan_recovered', clearly
      labeled "[Recovered orphan -- original batch record lost]") so their
      119 result rows / 4,645 trade rows are archived and reachable, not
      dropped. `PRAGMA foreign_key_check` -> zero violations after.
- [x] Verified end-to-end: (1) normal create_batch -> save_result ->
      save_trades still works with no regression; (2) attempting
      save_result() for a batch_id that was never created now correctly
      raises `IntegrityError: FOREIGN KEY constraint failed` instead of
      silently creating a new orphan; (3) ran one real full backtest via
      runner.run_mtf_batch (BTCUSDT, real strategy, real data) end-to-end
      after the migration -- completed normally, 64 trades, saved and
      cleaned up fine.
- Honest note on root cause: extensive tracing (this session, on top of two
  prior audits) found no reproducible in-code race -- every write path
  already creates the batch before any child row, synchronously, and
  workers never touch storage directly. The exact original trigger (likely
  an interrupted process or OS-level crash during a multi-hour concurrent
  run) could not be reproduced. What's fixed permanently is the STRUCTURAL
  gap that let it happen invisibly: it is now enforced at the database
  layer, so it cannot recur silently regardless of the original cause.
STATUS: DONE

### 4.2 Compare page speed (~11.2s baseline; measured 82.6s today)
Root cause found (query-level, not just Evolution CPU): `/api/compare-
strategies` called `_compute_strategy_summary()` DIRECTLY, bypassing the
exact 30s cache `/api/strategy-summary` already uses for the identical
computation, THEN did a SECOND, fully redundant `storage.get_batch_results()`
per strategy just to get worst_drawdown_pct (info the first pass already
had all the data for). `/api/strategy-lifecycle` (Strategy Lifecycle page,
also feeding Part 2's new dashboard split) had its OWN third independent
reimplementation of the same per-strategy aggregation, plus 49 separate
`get_paper_strategy_config()` DB round trips in a loop instead of one
`list_paper_strategy_configs()` call. None of this touched the Governor or
any safety gate -- purely redundant application-level work compounding
under the real (and untouched) background load from the Paper Trading/
Evolution engines.
- [x] Folded worst_drawdown_pct into `_compute_strategy_summary()`'s
      existing per-strategy loop (home.py) -- reuses data already fetched,
      zero new queries
- [x] `/api/compare-strategies` now reads the SHARED cached summary
      (`cache.cached("strategy_aggregate_summary", 30, ...)`) instead of
      recomputing/re-fetching per strategy
- [x] `/api/strategy-lifecycle` now reads the same shared cached summary
      instead of its own from-scratch per-strategy DB pass, and batches
      paper-config lookups into one `list_paper_strategy_configs()` call
- [x] Pre-warm added to server.py's startup `_warm_caches()` so the FIRST
      visitor after a restart gets the fast path too, not just the second
      visitor within the 30s window
- [x] Measured before/after (same running server, same DB, same live
      background engine load):
      - `/api/compare-strategies`: 82.6s -> 0.05-0.3s steady state (one
        22-23s cold-cache computation right after a restart, matching the
        cache's documented "only the true first call blocks" behavior)
      - `/api/strategy-lifecycle`: 44.9s -> ~2.25s steady state
- Governor/Evolution safety logic: untouched. The remaining ~2.25s on
  strategy-lifecycle and occasional multi-second spikes under heavy live
  engine ticks are genuine concurrent background-engine load (exactly what
  the task named), not fixable without touching that logic -- left alone
  per the global rule.
STATUS: DONE

### 4.3 Challenge Mode per-strategy/per-coin breakdown
FOUND ALREADY BUILT (stale task description, not a real current gap):
`paper_trading/challenge_analysis.py` already implements exactly this --
granular_breakdown() (per-strategy, per-coin, AND per-strategy-coin
combination, each ranked by real total_pnl), recommend_paths() (ranked
achievable/not-achievable real combinations with confidence + consistency
checks, plus an honest fallback realistic-target when nothing clears the
bar), and check_drift(). Wired end-to-end: GET /api/paper-trading/
challenge/breakdown, POST .../challenge/recommend, and a full "See Real
Recommendations" / What-If flow already live on the Paper Trading page's
Challenge Mode box, including one-click "Start This Challenge" scoped to
one real combination. Built in an earlier session/batch -- verified live
instead of duplicating it.
- [x] Verified GET .../challenge/breakdown with real data (e.g. Candlestick
      Pattern Reversal Strategy: 9 trades, 88.89% win rate, PF 9.24, +$4.31)
- [x] Verified POST .../challenge/recommend with a real example: $100 ->
      $200 over 30 days (required pace 2.34%/day, 52 real combinations
      considered) correctly picked "Candlestick Pattern Reversal Strategy
      on JSTUSDT" (demonstrated pace 3.66%/day, 4 real trades) as an
      achievable real combination -- the single best-performing real
      combination clearing the required pace
STATUS: DONE (pre-existing, verified)

## PART 5 — Login page
- [x] Username/password login gates EVERY dashboard page and API route,
      GET included -- new sindhu_web/auth.py (credentials + sessions) +
      sindhu_web/api/auth.py (status/setup/login/logout/change-password) +
      security.py's middleware extended with a session check that runs
      before (not instead of) the existing LAN-only + state-changing-
      request token guard. server.py's `/` route redirects to `/login`
      when there's no valid session; `/login` redirects back to `/` if
      already logged in.
- [x] Zero trading-related words anywhere on the login screen -- grepped
      login.html for trad/strateg/crypto/signal/backtest/coin/profit/paper:
      zero matches. Only "SINDHU" + a generic private-access message.
- [x] Real design craft, not a generic centered-box-on-gradient template --
      asymmetric layout (large wordmark top-left, glass panel lower-right),
      two soft slowly-drifting blurred gradient orbs, a fine dot-grid
      texture, gradient-text tagline, glassmorphism card with backdrop
      blur. Verified live at both desktop and mobile (375px) widths --
      mobile collapses to a clean centered single column.
- [x] Password stored hashed: PBKDF2-HMAC-SHA256, 200,000 iterations,
      random 16-byte salt per account, via the existing
      data_engine.config.load_or_seed/save_config JSON pattern
      (auth_credentials.json) -- never plaintext.
- [x] Session-based gate in security.py, layered on top of (not replacing)
      the existing LAN-only check and X-Sindhu-Token guard.
- [x] Tested live end-to-end: first visit -> redirected to /login -> shows
      "Set up access" (no account yet) -> created a TEST account -> landed
      on the real dashboard -> confirmed GET /api/home returns 401 with no
      session and 200 with one -> logout correctly clears the session
      (verified /api/home goes back to 401 immediately after) -> found and
      fixed a real bug during testing: logout/change-password were
      wrongly blocked by the OLD token guard (which only a logged-in
      dashboard page would normally send) since they weren't exempted --
      fixed by recognizing a valid session as sufficient proof for those
      two endpoints specifically.
- [x] Test credentials deleted afterward (auth_credentials.json +
      auth_sessions.json removed) so the CEO sees a clean "Set up access"
      screen and chooses their own real username/password on first visit --
      confirmed via /api/auth/status -> {"configured": false} again.
- Recovery note (for the final report): if the password is ever forgotten,
  deleting data/config/auth_credentials.json (and auth_sessions.json)
  resets it to a fresh "Set up access" state -- same manual-reset
  convention this project already uses for api_token.json.
STATUS: DONE

## FINAL DELIVERABLE
- [x] Part 1 evidence (39/39 real strategies enabled, confirmed at the
      strategy_matcher level the live engine actually uses)
- [x] Part 2 description (Profitable/Under Evaluation split, live-verified)
- [x] Part 3 confirmation + live test (risk override, pause, resume, all
      tested live and cleaned up afterward)
- [x] Part 4 root cause (orphan rows -- FK constraint, permanent) +
      before/after numbers (Compare 82.6s->0.05-0.3s, Lifecycle 45s->2.25s)
      + Challenge Mode example (found pre-existing, verified with real data)
- [x] Part 5 confirmation (login gate live-tested end-to-end, test account
      deleted afterward for a clean CEO-facing setup screen)
- [x] Full test suite result: **896 passed, 0 failed** (699.17s) -- run
      fresh after every change in this task, zero regressions
- [x] This file updated to COMPLETE
- [x] Report delivered to user in Roman Urdu/Hinglish

## STATUS: COMPLETE

## One thing worth the CEO's attention (not a blocker, just noted honestly)
No genuinely critical decision had to be skipped. Two informational notes:
1. "33 strategies" in the task vs. 39 real ones live today -- New Batch 4
   added 5 that weren't accounted for yet. Proceeded with the real number.
2. The exact original trigger for the orphan-rows bug (Part 4.1) could not
   be reproduced despite deep tracing (this is the third such investigation
   across this project's history) -- the fix closes the door permanently
   at the database layer regardless of cause, which is the strongest
   guarantee achievable without a live repro.
