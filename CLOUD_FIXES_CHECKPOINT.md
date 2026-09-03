# CLOUD FIXES (Sept 2026) -- CHECKPOINT

Resume rule: read this file FIRST. Continue from the first part not marked
DONE. Never restart from the beginning.

## GLOBAL RULES
- Do NOT touch the local laptop's full system, backtest engine, or any
  safety gate. Only work within cloud_runtime/ and related cloud-deployment
  code (sindhu_web/auth.py, data_engine/db_backend.py, the paper_trading
  API router, the shared static dashboard files).
- Run the full test suite after each part.
- Critical decisions -> skip, continue everything else, ask at the end.

## PART 1 -- LOGIN CREDENTIALS PERSISTENCE BUG -- [x] DONE

BUG: on Render, a CEO who set a username/password saw "first-time setup"
again after the host restarted/redeployed/slept-and-woke, as if the
account had never been created.

ROOT CAUSE (confirmed by reading the code, not guessed): sindhu_web/
auth.py stored credentials and sessions via data_engine.config.save_config
-- a JSON file under data/config/. That's fine on the local laptop (the
disk is permanent there), but Render's free-tier filesystem is EPHEMERAL:
wiped on every restart/redeploy/sleep-wake cycle. The already-connected
Postgres database (DATABASE_URL, data_engine/db_backend.py) was NOT being
used for this -- it already backs paper_positions etc. and genuinely
survives restarts, being a separate managed service.

FIX:
- data_engine/db_backend.py: added two tables to POSTGRES_SCHEMA --
  auth_credentials (single row, id=1) and auth_sessions (token primary
  key). Documented inline why they exist.
- sindhu_web/auth.py: every function (has_credentials, set_credentials,
  verify_password, change_password, create_session, is_valid_session,
  invalidate_session) now branches on db_backend.IS_POSTGRES. When true,
  reads/writes the two tables above via storage.get_conn() (the same
  dual-backend connection every other cloud table already uses). When
  false (every local laptop run, DATABASE_URL unset), behavior is
  byte-for-byte unchanged -- still the local JSON file.
- Password hashing (PBKDF2-HMAC-SHA256, 200,000 iterations, per-account
  random salt) is completely untouched -- only WHERE the hash is stored
  changed, never how it's computed or compared.

TEST (real, not simulated login flow, but a real proof of the actual
mechanism): tests/test_auth_cloud_persistence.py. No real Postgres server
is available in this environment (same stated, honest limitation as
tests/test_db_backend.py) -- these tests substitute a real sqlite3 file
connection everywhere auth.py calls storage.get_conn() under
db_backend.IS_POSTGRES. Sqlite's placeholder syntax and UPSERT
(`ON CONFLICT ... DO UPDATE ... EXCLUDED`) are close enough to Postgres's
to run auth.py's *exact* SQL text, proving genuine INSERT/UPDATE/SELECT
round-trips. "Restart" is simulated the honest way: rebinding
storage.get_conn to a BRAND NEW connection function pointed at the SAME
on-disk file between phases -- never one held-open connection, never
:memory: -- so nothing from phase one's Python objects can leak through;
credentials set before "the restart" must come back from the file itself
afterward. Covers: set -> verify after simulated restart, wrong password
rejected, change-password persists the new hash, sessions survive a
simulated restart, an expired session is rejected, invalidate_session
removes it, and (test_local_laptop_mode_is_completely_unaffected) the
local JSON-file path is untouched when DATABASE_URL is unset.
Also extended tests/test_db_backend.py's schema-completeness test to
require the two new tables.
22/22 new tests pass; full suite re-run clean after this change.

REMAINING CEO-SIDE ACTION for Part 1 to actually take effect on Render:
DATABASE_URL must be a real Postgres connection string set on the live
Render service (Environment tab) -- this fix only changes WHERE
credentials are stored when a Postgres database is genuinely connected. If
DATABASE_URL is unset on Render, auth.py silently keeps using the (still
ephemeral there) local JSON file, exactly as before -- there is no way to
detect "Postgres is connected but I forgot to migrate" from inside the app
alone, since the local-file branch is the ordinary, valid behavior on a
laptop. Confirmed DATABASE_URL is a real requirement, not new: db_backend.
py already required it for every other Paper Trading table.

## PART 2 -- "STRATEGIES" NAVIGATION TABLE -- [x] DONE (pending live click-test)

Added a new cloud-only dashboard page listing every strategy in the
library with real win rate / net PnL / risk:reward / Paper Trading status,
plus a gated "Move to Paper Trading" action.

BACKEND (sindhu_web/api/paper_trading.py, new endpoint, zero new imports
needed -- lib/validator/run_safety_check were already imported in this
file):
  GET /api/paper-trading/strategy-overview
  One row per backtest_engine.strategy_library.list_all() entry:
  - win_rate / total_pnl / closed_trades: from storage.
    list_paper_strategy_stats() -- REAL Paper Trading history, not
    backtest results. This runner's Postgres schema deliberately excludes
    the backtest_* tables (see db_backend.py's own docstring), so there is
    no backtest data to show here even locally-equivalent info would be
    unavailable on the cloud database -- a strategy with 0 paper trades
    honestly shows 0 trades / $0.00, never a placeholder or a backtest
    number mislabeled as live.
  - risk_reward / risk_reward_is_fixed: prefers the strategy's own FIXED
    configured ratio (take_profit.type == "rr", or the legacy risk_reward
    field) when one exists; falls back to the average R:R actually
    realized across live trades (paper_strategy_performance.avg_rr) only
    for structure-based SL/TP strategies that have no single fixed ratio
    to state. None (shown as "Not enough data yet") when neither is
    available.
  - in_paper_trading: storage.list_paper_strategy_configs()'s `enabled`
    flag -- the exact same field the existing per-strategy toggle already
    uses.
  - can_activate / activation_blocked_reason: reuses the EXACT combined
    gate /api/paper-trading/readiness/{id} already uses -- run_safety_check
    (the Strategy Safety Check: catches duplicate entry/exit clauses, exit
    gates with no realistic room, contradictory AND-gates, dead entry
    buckets) AND validator.validate() (structural correctness -- e.g. a
    missing entry timeframe) both live-recomputed, not read from a
    possibly-stale cached meta.json field. A strategy failing either is
    blocked, with the real reason text surfaced.
  - paper_config: the strategy's CURRENT priority/supported_coins/
    supported_market_types, so the frontend's activation call can resubmit
    them unchanged alongside enabled:true -- the existing
    update_strategy_config endpoint fully overwrites all four fields on
    every call (it has no partial-update/merge behavior), so activating a
    strategy without first reading its current config back would silently
    wipe any priority or coin restriction someone had already set.
  Deliberately reuses the EXISTING POST /api/paper-trading/strategy-config/
  {id} endpoint for the actual write (enabled:true) -- no new write
  endpoint, no changes to that endpoint, per the "do not rebuild any
  existing... paper trading... logic" instruction. The Safety-Check gate
  is enforced by the frontend disabling the button, exactly as the task
  asked ("if a strategy hasn't met required conditions... disable the
  button and show why") -- this mirrors the existing Strategy Lifecycle
  page's own pattern (openPaperTradingConfirm), which is also a
  frontend-level gate on top of the same unguarded write endpoint.

FRONTEND (sindhu_web/static/js/app.js):
  - New renderStrategyOverview() function + "strategy_overview" PAGES{}
    entry. Deliberately a NEW id, not a reuse of "strategies" -- that id
    already belongs to the local app's full Strategy Library page
    (renderStrategies, backed by /api/backtesting/strategies and other
    routers this cloud runner never mounts). Reusing it would route the
    cloud nav's click at a page that calls endpoints returning 404 here.
  - Reuses the existing visual language (.pill/.pill-up/.pill-muted,
    .table-wrap, .section-title, .btn/.btn-ghost, pnlSpan() for green/red
    PnL) -- no new CSS.
  - Clickable column headers do a simple client-side re-sort (no new
    endpoint needed -- the whole table is already fetched in one call).
  - Move-to-Paper-Trading button: a plain confirm() dialog (consistent
    with this file's other irreversible-ish actions, e.g. the Strategies
    page's archive action), then POSTs enabled:true plus the row's
    preserved paper_config, then re-renders the table.
  - cloud_runtime/app.py: added {"id": "strategy_overview", "label":
    "Strategies", "icon": "layers", "group": "Paper Trading"} to
    _CLOUD_NAV_PAGES (unmodified _CLOUD_NAV_GROUPS -- reuses the existing
    "Paper Trading" group).

TESTS:
  - tests/test_strategy_overview.py (8 tests, calls the endpoint function
    directly -- same convention as test_clarification_page.py, this
    environment has no httpx for a real TestClient): zero-trade strategy
    shows real zeros not placeholders; a fixed-RR strategy shows its
    configured ratio even after trades exist (never an average); a
    structure-based strategy with no fixed ratio falls back to the live
    average; a structure-based strategy with zero trades yet shows no R:R
    at all (None, not a fake 0); an already-active strategy is flagged
    correctly; a valid strategy is activatable; a strategy missing an
    entry timeframe is correctly blocked with the real validator reason
    text surfaced; a strategy's existing priority/coins/market-types
    round-trip through paper_config unchanged.
  - tests/test_cloud_runtime.py: updated the exact-equality nav-page-id
    assertion to include "strategy_overview", and added a route-path
    sample assertion for the new endpoint.
  8/8 new tests pass; full suite re-run clean after this change.

REAL-DATA VERIFICATION PERFORMED (read-only, against the CEO's actual
local database): started the local server via the existing sindhu-web
launch config, confirmed it came up clean (evolution engine, paper trading
engine, Telegram all started normally), then confirmed the login gate
correctly blocked an unauthenticated session (/api/auth/status ->
configured:true, logged_in:false) -- I do not have and did not attempt to
guess the CEO's password, so the browser click-test itself could not be
completed this session. Instead called get_strategy_overview() directly
(read-only) against the real running database and confirmed:
  - 154 real strategies returned, real names, real numbers.
  - Cross-checked one active strategy (id 0113516effdb) against the live
    engine's own engine.status() output at the same moment: both reported
    realized_pnl_total 0.82 -- the new endpoint's PnL genuinely matches
    the live engine's own bookkeeping, not a separate/stale calculation.
  - 115 of 154 not yet in Paper Trading; of those, 115 currently pass the
    Safety Check + validator gate (0 blocked) -- confirms the gate runs
    cleanly across the CEO's entire real library with no crashes, though
    it means the "disabled button" path itself was only proven against a
    deliberately-broken strategy in the automated test, not a real one
    (there happens to be no currently-blocked real strategy to show).
  - Fixed-ratio and average-ratio R:R both appeared correctly across real
    rows (e.g. a fresh Batch-5 strategy showing its fixed "rr" ratio; an
    already-active strategy showing its live average).
Server was stopped again afterward (confirmed http://127.0.0.1:8420/health
unreachable again), restoring the exact pre-session state.

DELIBERATELY NOT DONE: actually clicking Move-to-Paper-Trading against a
real strategy on the live server. The local paper trading engine auto-
resumed as soon as the server started (it persists "was it running"
across restarts) and was actively ticking live strategies with real open
positions. Flipping a real strategy's `enabled` flag while that engine is
live risks it opening a genuine (simulated) position on the very next tick
for a strategy the CEO did not decide to activate in this moment -- unlike
a pure config toggle, an opened position cannot be cleanly un-done by
flipping the flag back. That crosses from "verifying my own code" into
"changing live trading behavior," which needs the CEO present, not an
autonomous test. The write path itself IS fully proven, just not against
the live server: it is the exact same function (storage.
save_paper_strategy_config) 8 passing automated tests already exercise
end-to-end (test_strategy_overview.py's activation/config-preservation
tests), and it is the SAME pre-existing, unmodified endpoint the Strategy
Lifecycle page already uses today for the identical action.

RESOLVED -- the CEO asked me to test it myself. Confirmed the server was
NOT running (no live engine anywhere: `engine.status()['running'] is
False`), which removes the earlier risk entirely -- with no ticking loop
in existence, a plain config write cannot trigger a real trade. Ran the
exact same call chain the Move-to-Paper-Trading button makes, directly
against the real production database:
  1. Picked a real, currently-inactive, activatable strategy: "Asian Range
     London Sweep -- Confirmation Strict variant" (id 00749e40c3ca).
     Captured its exact original config first: enabled=False, priority=5,
     supported_coins=[], supported_market_types=[].
  2. Called update_strategy_config(sid, enabled=True, ...same values...)
     -- the SAME function the HTTP endpoint wraps. Logged exactly like a
     real click would: "[paper-trading] 00749e40c3ca activated by a
     person". storage.get_paper_strategy_config confirmed enabled=True.
  3. Re-fetched GET strategy-overview (the exact endpoint the page calls)
     and confirmed that same strategy's row now shows
     in_paper_trading=True -- the read side and the write side agree.
  4. Reverted with the exact original values (enabled=False, priority=5,
     [], []). Logged "...deactivated (manual override) by a person".
     Confirmed via both get_paper_strategy_config and strategy-overview
     that the strategy is back to byte-for-byte its original state.
Real end-to-end proof: the button's action genuinely activates a real
strategy, the table genuinely reflects it live, and it was left exactly
as found. Server was never started for this, so no engine tick, no risk,
no real (simulated) trade was ever at stake.

## STATUS
Both parts' code and automated tests are complete and passing locally as
of this session, plus a real-data (read-only) verification against the
CEO's actual production database (above). NOT YET committed/pushed to
GitHub. Full local test suite: 1006/1006 PASSED (clean re-run, confirmed).
One real regression was found and fixed along the way: scripts/
migrate_to_postgres.py's CURATED_TABLES list had drifted out of sync with
the new auth_credentials/auth_sessions schema tables (caught by test_
curated_table_list_matches_db_backend_schema_exactly) -- fixed by adding
both to CURATED_TABLES with a note explaining they're listed for that
parity guarantee but never actually migrated (no local-SQLite source
table exists for them; migrate_table() already handles an absent source
table gracefully).

Also completed: a real, live, end-to-end proof of the Move-to-Paper-
Trading action against the CEO's actual production database (see above)
-- activated a real strategy, confirmed it live in the exact endpoint the
page calls, then reverted it to its exact original state. The CEO
explicitly asked me to run this myself rather than click-testing through
the browser (I have no login credentials and did not ask for or guess
one).

BOTH PARTS OF THIS TASK ARE NOW FULLY COMPLETE AND VERIFIED. Not yet
committed/pushed -- ask the user before doing either.

DEFERRED QUESTIONS FOR THE CEO (per GLOBAL RULES -- skip, don't block):
1. Part 1 only takes effect once DATABASE_URL (a real Postgres connection
   string) is actually set on the live Render service's Environment tab.
   If it isn't set yet, please confirm whether Postgres has already been
   provisioned on Render, or whether that's still needed -- the code fix
   alone cannot fix a local-file bug on a host with no Postgres attached.
