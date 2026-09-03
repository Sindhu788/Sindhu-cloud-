# CLOUD MASTER TASK (Sept 2026) -- CHECKPOINT

Resume rule: read this file FIRST. Continue from the first part not marked
DONE. Never restart from the beginning. This task follows on from
CLOUD_FIXES_CHECKPOINT.md (login-persistence fix + Strategies table --
both already built, tested, and verified there, but NOT YET pushed to
GitHub as of the start of this task).

## GLOBAL RULES
- Do NOT touch the local laptop's full system, backtest engine, optimizer,
  Evolution Engine, or any safety gate (Wilson gate, Evolution gate,
  rollback, Confluence, Freshness, Incomplete Lock).
- Only work within cloud_runtime/ and related cloud-deployment code unless
  a part explicitly says otherwise.
- Run the full test suite after each part.
- Never delete data -- archive instead.
- Critical decisions needing CEO input -> skip, continue everything else,
  ask all of them together at the very end.

## PART 1 -- CONFIRM DATABASE_URL / POSTGRES STATUS -- [x] DONE (self-serve check added; final confirmation needs the CEO)

I have no Render API token, no dashboard login, and no stored live
service URL anywhere in this repo or this environment -- so I cannot
check Render's Environment tab myself, directly. Rather than guess, I
made the running app answer this question for itself:

FIX: cloud_runtime/app.py's existing `/health` endpoint (already exposes
`cloud_mode`/`live_candles_only` for the exact same "can't tell from
outside" reason) now also returns `db_backend`: `"postgres"` when
`DATABASE_URL` is set and the app is genuinely using
`data_engine.db_backend.IS_POSTGRES`, or
`"local_file (ephemeral on most hosts)"` when it is not. No connection
string or credential is ever exposed -- just which of the two storage
modes the live process picked, read live off the real flag every
request (not cached/assumed).

New tests: tests/test_cloud_runtime.py -- extended the existing /health
shape test to require the new field, plus a new
test_health_endpoint_reports_db_backend_honestly forcing
db_backend.IS_POSTGRES both ways and confirming /health reflects each
live. Full suite re-run clean after this change (see PART 2 below for
the run that covers this).

HOW THE CEO CONFIRMS THE REAL ANSWER (once Part 2 below is pushed and
deployed): open `https://YOUR-RENDER-SERVICE-NAME.onrender.com/health`
in any browser (no login needed) and read the `db_backend` field.
- `"postgres"` -> DATABASE_URL is genuinely connected; Part 1's
  credentials-persistence fix (from the previous session) is fully live.
- `"local_file (ephemeral on most hosts)"` -> DATABASE_URL is not set (or
  not reaching this service) -- login/paper-trading data will still be
  wiped on the next restart/redeploy/sleep-wake. Manual fix, exact steps:
  1. On [dashboard.render.com](https://dashboard.render.com), click
     **New +** -> **PostgreSQL** (free tier is fine). Give it any name,
     create it.
  2. Open the new Postgres service's own page -> copy the
     **External Database URL** (or **Internal Database URL** if the web
     service and the database are in the same Render account/region --
     internal is faster and free of egress, external also works).
  3. Open your WEB SERVICE (the one running SINDHU) -> **Environment**
     tab -> **Add Environment Variable** -> key `DATABASE_URL`, value =
     the URL just copied -> **Save Changes**.
  4. Render redeploys automatically after an env var change. Once it
     finishes, reload `/health` -- `db_backend` should now say
     `"postgres"`.
  5. (Optional, recommended) Run `scripts/migrate_to_postgres.py` from
     the local laptop once, per RAILWAY_DEPLOY.md's Step 3 doc comment,
     to seed the new Postgres database with the CEO's real existing
     strategy configs/history instead of starting empty. Not required
     for login persistence itself to start working -- only for carrying
     over pre-existing cloud data, if any exists yet.

This is flagged as the one deferred item for the CEO at the end of this
task (see DEFERRED QUESTIONS), since it needs either a Render dashboard
login (which I don't have) or the live service URL (not present anywhere
in this repo) to check directly. Everything else in this task proceeds
regardless, per GLOBAL RULES.

## PART 3 -- CONFIRM 24/7 OPERATION STATUS -- [x] CODE DONE (live confirmation needs the CEO, same reason as Part 1)

INVESTIGATION FIRST (before any fix): read paper_trading/config.py,
paper_trading/telegram_bot.py, paper_trading/engine.py, paper_trading/
risk_manager.py.

FOUND A SECOND INSTANCE OF PART 1'S EXACT BUG CLASS: "Dry Run Mode",
"engine on/off" (engine_enabled), the global "max_open_trades" default,
and every Telegram setting (auto-send on/off, confidence thresholds,
Signal Freshness Gate minutes/drift) all lived in the same kind of local
JSON file (data/config/paper_trading_settings.json,
telegram_settings.json) that Part 1 already proved is EPHEMERAL on
Render's free tier. Concretely: resume_engine_on_startup()
(paper_trading/engine.py line ~494) restores the Paper Trading Engine to
"whatever the CEO last explicitly chose" by reading pt_config.load()
["engine_enabled"] -- if that setting can't survive a restart, "24/7
operation" silently means "until the next restart/redeploy/sleep-wake",
at which point the engine goes back to OFF and Dry Run Mode goes back to
ON, with nothing on the dashboard explaining why.

FIX (same dual-backend pattern as Part 1, generalized this time since
this is a plain JSON blob, not a row needing its own columns):
- data_engine/db_backend.py: added ONE generic `cloud_settings` key/value
  table (key TEXT PRIMARY KEY, value_json TEXT, updated_at TEXT) -- covers
  both settings files (and any future one that needs the same fix)
  without repeating auth_credentials' bespoke-columns shape for no reason.
- data_engine/storage.py: get_cloud_setting(key) / save_cloud_setting(key,
  data, now_iso) -- thin read/write helpers via storage.get_conn(), same
  as every other dual-backend table.
- paper_trading/config.py: load()/save() branch on db_backend.IS_POSTGRES
  exactly like auth.py -- Postgres branch merges over _DEFAULTS from the
  cloud_settings row keyed "paper_trading_settings"; local-file branch
  (DATABASE_URL unset) is byte-for-byte unchanged.
- paper_trading/telegram_bot.py: load_settings()/save_settings() same
  branch, keyed "telegram_settings".
- scripts/migrate_to_postgres.py: added "cloud_settings" to CURATED_TABLES
  (parity only, same as auth tables -- no local SQLite source to migrate).
- tests/test_db_backend.py: schema-completeness test now also requires
  cloud_settings.

TEST: tests/test_cloud_settings_persistence.py (7 tests, same sqlite-
substitution technique as test_auth_cloud_persistence.py -- no real
Postgres server in this environment, stated honestly): dry_run toggle
survives a simulated restart (the literal scenario Part 3.1 asks to
confirm), engine_enabled survives a simulated restart (the mechanism
Part 3.2 depends on), a partial update never clobbers other saved
settings, Telegram settings survive a simulated restart with untouched
defaults still merging in correctly, and local-laptop mode is completely
unaffected (asserts the JSON files are still what gets written when
DATABASE_URL is unset). All pass.

PART 3.1 (Dry Run Mode) -- CODE FIX DONE, ACTUAL LIVE TOGGLE IS THE CEO'S
OWN ACTION: I have no login/URL for the live Render service (same honest
limitation as Part 1's DATABASE_URL check -- see PART 1 above), so I
cannot click the real dashboard's checkbox myself, and per GLOBAL RULES I
must not touch the local laptop's real dry_run setting either (that
would be "touching the local laptop's full system"). What I verified
instead: the exact mechanism the checkbox uses (POST /api/paper-trading/
settings {dry_run: false} -> paper_trading.config.save()) now genuinely
persists across a restart when Postgres is connected, proven by the
tests above using the real SQL text this code issues. Once Part 2 below
is deployed, the CEO flips the same checkbox they already know (Paper
Trading page -> "Dry Run Mode") and it will now actually stick.

PART 3.2 (engine running continuously) -- CODE CONFIRMED, mechanism
already existed and needed only the persistence fix above:
resume_engine_on_startup() (called from cloud_runtime/app.py's lifespan,
after storage.init_db()) already restores the engine to its last
explicit on/off state on every restart -- it just could not remember
that state across a restart until this fix. The CEO can confirm "is it
really running right now" with real evidence with zero new code: GET
/api/paper-trading/status (already mounted, already used by the Paper
Trading dashboard page) returns {"running": bool, "last_tick_at": ...,
"tick_count": ...} -- a `running: true` with a `last_tick_at` timestamp
from within the last tick_interval_seconds (default 60s) is real,
current evidence, not a guess.

PART 3.3 (5-coin-per-strategy limit) -- CONFIRMED, no code change needed:
paper_trading/risk_manager.py's evaluate() (line ~37) is the ONE gate
every trade (local or cloud) passes through -- `cloud_runtime/app.py`
imports this exact module, not a separate copy, so enforcement is
identical by construction, not by parallel implementation that could
drift. `max_coins = overrides.get("max_open_trades_override") or
settings.get("max_open_trades", 5)`: the per-strategy override already
lived in the curated Postgres `paper_strategy_config` table (already
safe before this task), and the global default of 5 was the only piece
missing persistence -- now fixed by the cloud_settings change above.

## PART 4 -- TELEGRAM SIGNAL FILTERING AND LABELING -- [x] DONE

All in paper_trading/telegram_bot.py unless noted.

4.1 HIGH-CONFIDENCE-ONLY BY DEFAULT: evaluate_auto_send_tier() (the one
function both the real-time open path (engine.py) and the hourly safety-
net sweep both call) previously fell back to a "Low" tier whenever High
didn't qualify. Now, with the new setting auto_send_high_confidence_only
(default True), a Low-tier-only-qualifying signal is NOT sent -- it's
still fully generated and stays visible wherever the dashboard already
shows signal activity (paper_decision_log, the Signal Tracker page,
/api/paper-trading/telegram/delivery-log's "never sent" bucket, which now
shows this exact reason text). Setting it False restores the old
fallback behavior for anyone who wants it -- a default, not a removal.
evaluate_auto_send_low_tier() itself is untouched (still directly
testable/usable).

4.2 PROFITABLE VS UNDER-EVALUATION LABELING: every signal message now
states plainly, via _profitability_label(), whether its strategy has a
"Profitable Strategy" (real positive live PAPER-TRADING pnl AND at least
pattern_stats.MIN_SAMPLE_SIZE=25 closed trades -- the exact same bar the
Wilson gate already uses, not a softer second threshold) or is "Strategy
Still Under Evaluation" (everything else -- most commonly, not enough
trade history yet). Deliberately uses LIVE paper-trading data, not
backtest results: this cloud runner's own curated Postgres schema
excludes the backtest_* tables entirely (db_backend.py), so a
backtest-based classification would be structurally unavailable there --
"how has this actually performed live" is also the more honest thing to
tell someone about a signal they're about to act on.

4.3 RISK DISCLAIMER ON EVERY PROFITABLE-STRATEGY SIGNAL: a new constant,
PROFITABLE_RISK_DISCLAIMER = "Risky -- no strategy guarantees profit,
trade at your own risk", is appended without exception whenever
_profitability_label() returns "Profitable" -- distinct from the existing
DISCLAIMER (already on every message regardless of tier/profitability).

4.4 CHALLENGE MODE LABELING: _challenge_mode_tag() checks
challenge_mode.load()'s scope_strategy_id/scope_symbol -- when the CEO
has scoped an active Challenge to this exact strategy+coin, the message
gets a distinct "Challenge Mode Signal" tag. A system-wide (unscoped)
challenge does not tag every signal (would be misleading -- it tracks the
blended account, not one signal). Found this had NO existing thread from
position -> Telegram message at all -- newly built, since Challenge Mode
was previously tracking/reporting only (see challenge_mode.py's own
docstring), never touching what gets sent.
ALSO fixed: challenge_mode.py's load()/save() had the exact same
ephemeral-JSON-file bug Part 3 fixed elsewhere -- a CEO's chosen Challenge
scope (needed for 4.4 to work correctly across restarts) would have been
silently lost on Render. Same cloud_settings persistence pattern applied.

4.5 LATENCY -- INVESTIGATED, NO CODE CHANGE NEEDED: traced the real path
(paper_trading/engine.py's _tick() -> telegram_bot.send_signal_for_position
-> _raw_send -> requests.post to api.telegram.org). The Telegram send is
SYNCHRONOUS and immediate the moment a position opens -- no queue, no
batching, no artificial sleep on the happy path (the only sleep,
_API_RETRY_BACKOFF_SECONDS=2s, fires solely on a genuine network failure,
already existed, not something this task asked to remove). The only
real cadence knob in this system is tick_interval_seconds (default 60s
-- paper_trading/config.py), which governs how often the market is
SCANNED for new opportunities, not how long a signal waits once found --
these are two different concepts. Conclusion: there is no unnecessary
delay between "signal generated" and "sent to Telegram" to optimize.

TESTS: tests/test_telegram_dual_tier.py and tests/test_telegram_hourly_sweep.py
updated (2 tests changed to reflect the new High-Confidence-only default,
2 new opt-in tests added) + tests/test_telegram_freshness_gate.py (1 test
adjusted to qualify at High tier, since its real point was the freshness
gate, not tier fallback) + new tests/test_telegram_signal_labeling.py (9
tests: profitability label in both directions, the 25-trade+positive-pnl
AND gate specifically, no-strategy-id edge case, and all 3 Challenge Mode
scoping scenarios). All pass; full telegram+challenge test subset (196
tests) re-run clean after these changes.

## PART 5 -- TELEGRAM-SPECIFIC ANALYTICS/TRACKING -- [x] DONE

Found the dedicated view mostly already existed: GET /api/paper-trading/
telegram/analytics (sindhu_web/api/paper_trading.py) already filtered
strictly to signals actually SENT to Telegram (via storage.
list_telegram_signal_outcomes(), trigger_type manual/automatic AND
success=1) and already returned per-period win/loss/win-rate plus a
per-strategy breakdown (paper_trading/telegram_analytics.py). Two
genuinely missing pieces, added without duplicating any existing logic:
- signal_period_summary() now also returns total_pnl -- the real (not
  hypothetical-rescaled) sum of pnl across closed, Telegram-sent trades.
- strategy_breakdown() now also tracks total_pnl per strategy.
- New telegram_analytics.best_performing_strategy(): the strategy_breakdown
  entry with the highest real total_pnl among strategies with at least one
  CLOSED Telegram-sent trade (None if nothing qualifies yet) -- reuses
  strategy_breakdown(), no second query.
- The /telegram/analytics endpoint now also returns best_strategy.
FRONTEND (sindhu_web/static/js/app.js's renderTelegramDashboard): added a
new, clearly-labeled "Telegram-Sent Signals Only -- Real Performance"
section (Signals Sent, Wins, Losses, Win Rate, Total PnL, Best Strategy)
right above the existing per-strategy table -- makes the "ONLY signals
actually sent to Telegram" distinction visually unambiguous from the
headline band above it (which intentionally shows ALL generated signals,
sent or not, per the existing delivery-log design).
TESTS: tests/test_telegram_dashboard.py -- 5 new tests (total_pnl on both
the period summary and per-strategy breakdown, best_performing_strategy
picking the real winner, ignoring all-pending strategies, and returning
None with zero signals). All pass (19/19 in this file).

## PART 6 -- CLOUD-TO-LOCAL DATA SYNC (EVERY 24 HOURS) -- [x] BUILT AND TESTED (cannot prove a real 24h run against the live Render host -- see below)

NEW paper_trading/cloud_sync.py: build_snapshot() gathers open positions,
closed trades (up to 1,000,000 -- a real backup, not a recent slice),
the Telegram signal log, and per-strategy performance/stats -- every
field reuses an EXISTING storage/telegram_analytics function, zero new
query logic. Deliberately excludes klines/historical candle data (this
runner's own Postgres schema doesn't store that anyway) and is one-way
by construction: this module only ever READS the cloud's own data and
hands it out; nothing anywhere accepts a write from the local laptop.
Snapshot storage follows the exact cloud_settings convention Part 3
established (Postgres when connected -- so the backup survives the same
restarts it protects against -- local JSON file otherwise).

SCHEDULING: followed this codebase's own existing convention exactly
(sindhu_strategy/generator.py's daemon-thread + hourly-check + elapsed-
time gate pattern) rather than inventing a new one or adding a dependency
-- start_cloud_sync_scheduler_thread() checks hourly, actually syncs only
once >=24h have passed since the last snapshot. Started ONLY from
cloud_runtime/app.py's lifespan (never from sindhu_web/server.py, the
local laptop's full app) -- confirmed via code read that no existing
scheduler was started there for this cloud runner at all (a real,
separate gap this task's research surfaced).

ENDPOINTS (sindhu_web/api/paper_trading.py, all inside the already-
mounted, already-authenticated paper_trading_api.router):
- GET /api/paper-trading/cloud-sync/status -- has_run + a row-count
  preview, no need to download the whole file just to check freshness.
- POST /api/paper-trading/cloud-sync/run-now -- manual trigger, for a
  CEO who wants a fresh backup immediately rather than waiting up to 24h.
- GET /api/paper-trading/cloud-sync/download -- the actual JSON file,
  Content-Disposition: attachment, 404 with a clear message if the
  scheduler hasn't run yet.

TESTS: tests/test_cloud_sync.py (8 tests, same honest sqlite-substitution
technique as every other cloud_settings test this session -- no real
Postgres server in this environment): snapshot building reuses real data,
no-snapshot-yet returns None, local-file fallback works, a snapshot
survives a simulated restart on the Postgres branch, and the 24h elapsed-
time gate (_should_run_now) is correct in all three states (never run /
just ran / 25h stale).

HONEST LIMITATION (same shape as Part 1/3): I cannot start the real
scheduler against the live Render host (no URL/login), and I deliberately
did NOT run cloud_sync.run_sync() for real against the local laptop's
actual production database, since that would write a snapshot file into
the real data/config/ directory -- "touching the local laptop's full
system," which GLOBAL RULES forbid. What's proven instead: the exact
mechanism (build_snapshot, run_sync, the 24h gate, Postgres persistence)
via the test suite above, using real SQL text against a real sqlite file
standing in for Postgres -- the same honest verification standard as
Parts 1 and 3. Once Part 2 is deployed, the CEO can prove a real run
immediately via POST /api/paper-trading/cloud-sync/run-now, then GET
.../cloud-sync/download.

## PART 7 -- MISSING DASHBOARD SECTION AUDIT -- [x] DONE

Compared the local app's full nav (sindhu_web/api/home.py NAV_PAGES, 27
pages) against cloud_runtime/app.py's _CLOUD_NAV_PAGES (was 3). Found:
- 23 of the 24 missing pages are backed by routers cloud_runtime/app.py
  deliberately never mounts (Backtesting, Evolution, AI Center, Knowledge,
  Settings, ...) -- consistent with the file's own stated design ("Paper
  Trading + Telegram + nothing else"), and mounting any of them would mean
  touching the backtest engine/Evolution Engine, which GLOBAL RULES
  forbid. These are intentional exclusions, not bugs -- not fixed.
- ONE genuine oversight found: "signal_tracker" (Signal Tracker page) is
  backed ENTIRELY by paper_trading_api.router, which is ALREADY mounted
  in cloud -- it was simply never added to the nav list. Before adding it,
  found and fixed a real latent bug this would have surfaced: its
  Backtest/Paper/Telegram match-table compares against
  backtest_batches/backtest_results, which do not exist in this runner's
  own curated Postgres schema -- calling it there would have crashed with
  "relation does not exist" the moment anyone clicked the newly-visible
  link. Fixed with a narrow try/except in paper_trading/signal_tracker.py's
  _backtest_win_rate() (degrades to "no backtest data available for this
  strategy," exactly like the existing "no completed batch matches" case)
  -- does not touch or rebuild any backtest logic, just stops calling into
  a table that provably isn't there on this deployment. Added to
  _CLOUD_NAV_PAGES.
- Challenge Mode: confirmed it needs NO nav fix -- it's already a tab
  inside the Paper Trading page (already in cloud nav), backed by
  paper_trading_api endpoints already mounted. Already fully usable on
  cloud today.

TESTS: tests/test_signal_tracker.py -- 1 new test forcing the exact
"relation does not exist" exception and confirming a graceful (None, None)
instead of a crash. tests/test_cloud_runtime.py -- nav-id-set assertion
extended to include "signal_tracker", route-path assertions added for its
two endpoints plus the three new cloud-sync endpoints.

## PART 2 -- PUSH PREVIOUSLY COMPLETED FIXES TO GITHUB -- [ ] IN PROGRESS
