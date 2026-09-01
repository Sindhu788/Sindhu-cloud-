# MASTER AUDIT CHECKPOINT

**Resume rule:** Read this file FIRST on any resume. Find the last COMPLETE
sub-step, continue from the NEXT one. Never restart. Never redo completed work.

**Started:** 2026-08-29
**Active Part:** PART 3 — End-to-End Verification (Parts 1 & 2 COMPLETE)

## STATUS SUMMARY
- **PART 1 — COMPLETE.** 18 strategies activated, engine proven opening real trades.
- **PART 2 — COMPLETE.** All 12 modules audited. **7 real bugs found and fixed**, all with
  before/after evidence. `pytest 896 passed` after every single fix (final run: 118.95s).
- **PART 3 — COMPLETE.** All 5 links of the chain PASS, unbroken, on one real strategy.
- **PART 4 — COMPLETE.** 7 UI fixes (CSS/layout/structure only), verified in the real
  browser at desktop + mobile + both themes. 4 items flagged as needing data/logic changes.
- **PART 5 — COMPLETE.** 4 CEO-approved actions applied (batch fix, Gemini, EMA/RSI rule,
  Evolution Engine ON).
- **PART 6 — COMPLETE.** DB cleanup, Paper Trading ON, plus 2 fixes for problems those
  activations exposed. **Final `pytest`: 896 passed** (797s — slow only because both
  engines were competing for CPU; normally ~110s).

### Everything changed in this task
`paper_trading/coin_filter.py` · `paper_trading/engine.py` · `paper_trading/telegram_bot.py` ·
`backtest_engine/configured_strategy.py` · `backtest_engine/validator.py` ·
`ai_integration/deep_understanding.py` · `ai_integration/multi_pass_extraction.py` ·
`sindhu_strategy/deterministic_builder.py` · `sindhu_web/static/css/app.css` ·
`sindhu_web/static/js/app.js` · `sindhu_web/static/concepts.html`
(+ `MASTER_AUDIT_CHECKPOINT.md`, `CLEANUP_RECORD.md`)

## PART 5 — CEO-APPROVED ACTIONS ✅ ALL 4 APPLIED

| # | Action | Result | Evidence |
|---|---|---|---|
| A1 | **Restore the real leaderboard number** | DONE | My Part 3 verification batch `20260830_003129_6a3c79` set to `status='stopped'` + labelled *"Part 3 end-to-end verification run (3 coins) -- NOT a strategy evaluation"*. Leaderboard batch moved **`20260830_003129_6a3c79` → `20260825_045513_c3948b`**, restoring **50 coins, 4,159 trades, 39.72% win rate, PF 1.1939** (was showing 3 coins / 457 trades / PF 1.0197). **Nothing deleted** — verified after the write: 457 trade rows + 3 per-coin results still present. |
| A2 | **Enable Gemini as a real AI fallback** | DONE | Provider chain **`['groq'] → ['groq', 'gemini']`**. `active_provider` deliberately left as `groq`, so Groq is still tried first and normal behaviour is unchanged; Gemini is now a genuine second line instead of dropping straight to offline. Script refuses to enable a provider with no stored key (it had one). No key read, printed or modified. |
| A3 | **Apply the CEO's EMA/RSI rule** | DONE | See below — this is the second half of bug M9-1. |
| A4 | **Turn the Evolution Engine ON** | DONE | Started through the **live server's own HTTP API** (not a throwaway thread), so it runs inside the process serving the dashboard and its job row survives a restart via `resume_evolution_jobs_on_startup()`. Job `evo_1788039735952`, `status=running`. Governor confirmed live and unchanged: CPU limit 60%, RAM 80%, queue cap 20, 5 experiments/run, 25 generations/strategy. `UNTESTED_CANDIDATES_PER_TICK` left at its deliberate value of **1** so the 132 waiting candidates are worked through slowly rather than flooding the machine. |

### A3 — the EMA/RSI rule, as instructed
**CEO's rule:** *price above EMA = bullish/buy-side bias, price below EMA = bearish/sell-side.*

`deterministic_builder` no longer drops numeric indicators (the conservative half-fix from
Part 2); each is now emitted as the condition type it actually needs:

| Drawn name | Emitted as | Why |
|---|---|---|
| `ema`, `sma`, `vwap` | `price_compare` — **`close > indicator`** | Exactly the CEO's rule. These are price-LEVEL indicators, so comparing price against them is meaningful. |
| `rsi` | `indicator_compare` — **`rsi < 30`** | RSI is not a price level, so the price-vs-level rule cannot apply. Its own universal standard default is 30/70; the buy-side half is "oversold", matching the bullish bias the builder already produces. |
| `macd` | `concept` — **`macd_signal_cross`** (bullish) | Also not a price level, but the engine already has a real, implemented boolean event concept for it (verified firing 6,393 / 17,281 bars). Reused rather than inventing a comparison. |
| `atr`, `volume` | *(excluded)* | Volatility and participation carry no direction at all — there is no standard bullish/bearish default, so these are still left out rather than guessed at. |

`dna._CONCEPT_DNA` deliberately untouched: a strategy holding an EMA genuinely has "trend"
DNA, so `extract_dna()` must keep seeing those names.

**Evidence:** 12 freshly generated candidates → **0 dead conditions, 0 invalid**. Sample
output: `close > sma` (indicators `['sma']`), `rsi < 30.0` (`['rsi']`),
`aggression + macd_signal_cross` (`['macd']`), `close > vwap` (`['vwap']`).
Fired on real BTCUSDT 5m data over 8,441 bars: **`close > sma` 4,346**, **`close > vwap`
4,596**, **`rsi < 30` 304**, **`macd_signal_cross` 3,180**, **`aggression` 4,164**.

> One scare investigated and dismissed: `close > sma` first measured **0** hits. Cause was my
> test harness skipping `ConfiguredStrategy.prepare()`, which is what aliases `entry_close`
> to `close`. Re-run with `prepare()` (as a real backtest does) → 4,346 hits. Test artifact,
> not a bug.

`pytest 896 passed` after the builder change.

### A4 — proof the Evolution Engine is genuinely working (not just "started")
Left running and observed: untested candidates went **132 → 131 → 130** on its own, and the
job's stage advanced `starting → analyzing → completed` while `status` stayed `running` for
the next tick. `evolution_jobs` had **0 rows for the life of this project before today**.
Tick interval is the built-in 300s with jitter and `UNTESTED_CANDIDATES_PER_TICK = 1`, so the
remaining 130 candidates will be worked through slowly over roughly half a day — that pacing
is deliberate (the module's own comment: it must not compete with real user backtests).

### ⚠️ REAL SIDE EFFECT OF TURNING EVOLUTION ON (measured, not weakened)
While a candidate backtest is mid-flight, the dashboard becomes slow enough to **time out**.
Measured on `/api/compare-strategies`: **44.9s**, then **52.3s**, then **0.5s** once the
engine's backtest finished. The frontend gives up at 15s, so the Compare page showed
*"Failed to load page — GET /api/compare-strategies timed out after 15000ms"*.

Deliberately NOT "fixed", because every available fix is worse than the problem:
weakening the Governor's CPU limit is a safety gate and is forbidden; raising the frontend
timeout to 60s just replaces an error with a one-minute blank page. It is fully reversible —
stopping the Evolution Engine restores instant page loads. Raised for the CEO.

---

## FINAL VERIFICATION (after every change in this session)

| Gate / property | Value | Proof |
|---|---|---|
| Wilson Score | `MIN_SAMPLE_SIZE = 25` | 24/24 → `reliable=False`; 20/25 → `reliable=True` |
| Evolution gate | `MIN_TRADES_FOR_COMPARISON = 100` | unchanged |
| Rollback | `win_rate↑ total_pnl↑ avg_profit_factor↑ max_drawdown_pct↓` | unchanged |
| Confluence | `>= 0.75` Strong, `>= 0.5` Moderate, pattern `win_rate >= 50.0` | unchanged |
| Signal Freshness | 15 min | 15 min fresh, 16 min stale |
| Incomplete Lock | — | 18 activated checked, **0 locked** |
| Per-strategy coin cap | `max_open_trades = 5` | Part 1 tightening still in force |
| Governor | CPU 60% · RAM 80% · queue 20 · 5 exp/run · 25 gen/strategy | unchanged |
| Paper Trading loop | **still OFF** | `engine_enabled = False` — never turned on, as instructed |
| Activated strategies | **18** | unchanged |

**`pytest 896 passed` (final run). Nothing weakened. Nothing deleted.**

---

## PART 6 — SECOND ROUND OF CEO-APPROVED ACTIONS

### A5 — Database cleanup ✅ DONE (full detail in `CLEANUP_RECORD.md`)

| | before | after |
|---|---|---|
| `backtest_batches` rows | 193 | **193** — none removed |
| batches stuck at `running` | 6 | **0** |
| `backtest_results` | 6,757 | **6,305** |
| `backtest_trades` | 2,025,514 | **1,974,290** |
| `confluence_score_log` | 82 | **26** |
| orphaned results / trades / confluence | 452 / 51,224 / 56 | **0 / 0 / 0** |

Stuck batches were only **re-statused**, never deleted — their partial results
stay queryable. Orphans (rows whose parent batch no longer exists) were deleted;
Part 2 had already proved these are unreachable by every read path, so no
displayed number changes. A pre-delete audit was written to `CLEANUP_RECORD.md`
first, so what was removed is permanently traceable.

### ⚠️ MISTAKE I MADE DURING THE CLEANUP — recorded, not hidden
The stuck-batch step used a blanket `WHERE status='running'` instead of the five
specific stale ids, so it also caught `20260830_030009_504b78`
(*SINDHU Deterministic Candidate #4*) — a batch the Evolution Engine was
**actively running at that moment** — and marked it `stopped` mid-flight.

Checked rather than assumed: its data is intact (1 result saved, 0 trades), the
candidate was still recorded as tested (untested 130 → 129), and the evolution
job stayed `running` so it resumed normally. Left as `stopped` because that is
now the accurate state. **Lesson: never filter live state by status alone.**

### ⚠️ STILL OPEN — orphan rows are being created again
The cleanup is not permanent. New orphans appeared during this session
(`20260830_024927_431b99` — a BTCUSDT 5m result with 928 trades and no parent
batch); the pattern runs back to at least 2026-08-19. Bounded investigation
found **no cause**: `runner.py` always creates the batch before any
`save_result()`, every `save_result` caller lives in `runner.py`, and there is
no `DELETE FROM backtest_batches` or retention job anywhere in the project.
Hypothesis (not a finding): an interrupted/rolled-back `create_batch` whose
per-symbol writes, on their own connections, still committed. Needs a dedicated
follow-up with write-level tracing.

### A6 — Paper Trading engine ✅ ON

`paper_trading_settings.json` → `engine_enabled: False → True` (only that field
changed, verified programmatically). This is the persisted "CEO's last explicit
choice" that `resume_engine_on_startup()` reads on every launch, so the setting
survives restarts rather than living only in memory.

**Verified live after a server restart:**
- Paper Trading — `running: True`, `dry_run: False`, started 2026-08-29T22:38:19Z,
  **26 open trades across 7 books** (the per-strategy panel populating at all is
  bug-fix B2 working).
- Evolution — `running: True`, resumed the **same** job `evo_1788039735952`.

`max_open_trades` still **5** and every safety gate untouched.

### Server restart note
The server that had been running all session was gone (nothing listening on
8420) by the time I checked after the cleanup. No crash log exists — today's
process wrote to a terminal, and `server_err.log` / `web_server_err.log` are
stale from 25–26 Aug — so **I cannot say why it stopped** and will not guess.
Restarted it via the project's own `launch.json` config; both engines came back
through their own documented resume paths, which is exactly what those paths
are for.

Evolution's first stage after restart was `skipped_over_resource_limit` — the
Governor correctly refusing to start work while CPU/RAM were busy, not a fault.

### A6 PROOF — the Paper Trading engine is genuinely trading, not just "on"
The engine **closed 3 positions by itself** at 22:43 while I was watching
(open trades went 26 → 24 → 24 with 3 closed):

| coin | side | entry | exit | pnl | reason | book |
|---|---|---|---|---|---|---|
| PUMPUSDT | long | 0.005011 | 0.004966 | **-0.5631** | `stop_loss` | HTF Key Level Engulfing |
| PUMPUSDT | long | 0.005011 | 0.004926 | **-0.5311** | `stop_loss` | Support/Resistance Breakout |
| PUMPUSDT | long | 0.005011 | 0.004949 | **-0.5437** | `stop_loss` | Candle Range Theory 2.0 |

**These are the first real closed paper trades in this project's history.** Three
*different* strategies each independently held PUMPUSDT and each independently
stopped out — per-strategy independent accounting proven end to end. Each loss is
~0.53% of a $100 book, matching `risk_pct_default = 0.5` exactly.

`paper_account_state` now has real rows: `b4caef4ee47d` −0.5300, `b9884b3e5e5d`
−0.5600, `8d527d2e0861` −0.5400 (1 closed / 0 wins each).

### FIX P6-1 — `/api/paper-trading/status` was timing out (a regression I caused)
With both engines running, the Paper Trading page failed with
*"GET /api/paper-trading/status timed out after 15000ms"*.

**Root cause was my own bug-fix B2.** Making every actively-trading book visible
also meant `status()` ran `storage.get_open_paper_position_symbols(book)` once
**per book** — 1 + N round trips, each opening its own connection
(`storage.get_conn()`), all contending with two engines' writes.

**Fix:** derive each book's distinct-coin count from the `open_positions` list
`status()` had *already* fetched. Same numbers, same semantics, one query.

**Measured:** `engine.status()` **0.35s** direct; over HTTP **0.42s then 0.20s**
(was >15s). Correctness re-checked: 24 open trades, 7 books, per-book counts
5/5/5/4/2/2/1 summing to exactly 24. `/api/compare-strategies` is 11.2s — inside
the timeout but still slow under Evolution contention (flagged below).

### FIX P6-2 — dangling "last at" label + zero spacing (Part 4 scope)
The Control Center line read *"Started … — tick #0, last at "* with nothing after
it: `(last_tick_at||"-").slice(11,19)` yields an empty string before the first
tick completes, and a full 50-coin × 18-strategy pass takes many minutes, so that
half-sentence is what the CEO sees the whole time. It also sat flush against the
next heading (measured gap: **0px**).

Now renders *"Started 2026-08-29T23:06:47 — tick #0 (first tick still running)"*
with proper spacing. Verified in the live browser.

---

## ✅ SERVER NOW RUNNING INDEPENDENTLY (not tied to my session)

Relaunched with `python web_main.py` as its own detached process, writing to
`sindhu_server.log`. Both engines restored themselves through their own
documented paths — captured verbatim from the launch log:

```
[evolution-engine] started
[paper-trading] Restoring to ON -- it was running when the server last stopped.
[paper-trading] engine started
[evolution-engine] CPU/RAM over limit (cpu=92.0%, ram=73.4%) -- skipping this tick entirely
[telegram] Sending is currently ON (restored from the last saved setting).
```

That fourth line is the Governor working correctly, not a fault — it refused a
tick while pytest was saturating the CPU.

## ⚠️ ORIGINAL WARNING (kept for the record) — the engines only run while the SERVER runs

Both engines are background threads **inside the web server process**. I started
the server with the preview tooling, which is tied to my session, so it stops
when my session ends. Observed three times.

**What is durable (survives everything, already set):**
- `paper_trading_settings.json` → `engine_enabled: True` — `resume_engine_on_startup()`
  starts Paper Trading automatically on **every** server launch.
- `evolution_jobs` row `evo_1788039735952` still `status='running'` —
  `resume_evolution_jobs_on_startup()` picks Evolution back up the same way.
- 18 activated strategies, `max_open_trades: 5`, `dry_run: False`.

**What is NOT durable:** the server process itself. Nothing trades while it is
down. To actually run 24/7 the CEO must start the server independently, e.g.:

```
python web_main.py
```

Final durable state confirmed straight from the database (no server needed):
`engine_enabled True` · 18 activated · **26 open + 3 closed** paper positions ·
129 untested candidates remaining · evolution job `running` · realized PnL per
book −0.5437 / −0.5311 / −0.5631.

---

## PART 7 — PROFESSIONAL DASHBOARD REDESIGN (CEO: *"expert nai banayi hai"*)

The Overview was rendering **eight identical `.card`s in one flat grid**, so a
headline number (`Balance $297.82`) carried exactly the same visual weight as a
one-word status (`System Health OK`). Everything competed; nothing led the eye.
That flatness is what read as amateur, not the colour palette.

### What changed

**1. Two deliberate tiers instead of one flat grid**
- `.kpi-grid` — the four numbers the CEO actually judges the system by
  (Balance / PnL / Win Rate / Total Trades). 30px tabular-figure values, a
  2px accent hairline along the top edge, and a **context sub-line** under each
  ("across 4 closed trades", "Realized, live account") so a number never sits
  alone without meaning.
- `.status-strip` — Knowledge / Evolution / Database / System Health, compact
  key-value chips on one row, clearly subordinate. Good states render green.

**2. The accent line carries meaning**
`.kpi.is-positive` / `.is-negative` turn that hairline green or red, so PnL
being negative is visible from across the room without reading the number.

**3. System Maturity: a text wall became a component**
Was a 28px heading over three prose paragraphs and a run-on `·`-separated
metrics line. Now: level + name, a real **5-step progress bar** (`Step 1 / 5`),
the criteria as body text, the next-level target called out in bold, and the
four metrics as proper labelled tiles instead of one dense sentence.

**4. Consistency — the aggregate row now matches**
"All Strategies — Aggregate Performance" was still using the old flat cards, so
it clashed with the new Overview. It now uses the same `.kpi` treatment with its
own captions ("profit factor above 1.0", "weighted by trade count").

**5. `.section-head`** — section titles can now carry a right-aligned note,
which is where the data-source line moved to (it used to float awkwardly under
the grid with a negative top margin).

**6. Empty states** — an empty table rendered as a bare left-aligned sentence
jammed against the header row, reading like a broken table. `td.empty-cell` now
centres it with real padding and points at the next action.

### FIXED A STALE CLAIM THE REDESIGN EXPOSED
The Overview hardcoded *"there is no live Paper Trading yet, so this reflects
the most recent backtest, not a live account."* That became **false** the moment
Paper Trading started closing trades — `/api/home` now returns
`latest_batch.strategy = "Paper Trading (live account)"`. The note is now
**derived** from that field, so it reads *"Live Paper Trading account — realized
results only"* and switches back automatically if the source ever does. This was
one of the four items flagged as "needs data/logic changes" in Part 4; the data
to do it properly now exists.

### Verified
Desktop and light theme both re-checked in the live browser after every change;
**0 console errors**. Layout measured rather than eyeballed: `pageOverflows:
false`, no element wider than its container, `.kpi-grid` correctly collapsing
columns as width drops (`auto-fit` + `minmax(215px, 1fr)` yields a single column
below ~460px, so a phone gets one card per row by construction).

**`pytest`: 896 passed in 601.41s** — zero regressions from the redesign.

### The redesign is showing LIVE data, and it is moving
Across the verification window the Overview updated on its own as the engine
traded: Balance **$297.82 → $596.90**, Total Trades **4 → 7**, Win Rate
**0% → 14.29%** (the first winning trade landed: book `59978271c6ce`,
**+0.1376**). Final state at handover: **31 open / 7 closed** positions across
**6 books**, both engines `running`.

## ⚠️ STILL SLOW — `/api/compare-strategies` under Evolution contention
11.2s (inside the 15s frontend timeout, but close to it). `_compute_strategy_summary`
reads every strategy's batch results and is only cached 30s, so on a cold cache
while Evolution is backtesting it nearly times out. Not "fixed": the honest
options are weakening the Governor (a safety gate — forbidden) or raising the
frontend timeout (replaces an error with a long blank wait). Fully reversible by
stopping the Evolution Engine. Flagged for a follow-up that would make that
endpoint cheaper.

### The 7 bugs fixed (files changed)
| # | Bug | File |
|---|---|---|
| B1 | silent `coin_filter` failure (engine idled with no explanation) | `paper_trading/coin_filter.py` |
| B2 | per-strategy panel blind to open trades | `paper_trading/engine.py` |
| B3 | wrong docstring on strategy-enable default | `paper_trading/engine.py` |
| M2-1 | `macd` comparison read a column that never existed | `backtest_engine/configured_strategy.py` |
| M2-2 | 5 candlestick patterns dead unless an umbrella name was declared | `backtest_engine/configured_strategy.py` |
| M7-1 | validator drifted out of sync with the engine (50/104 strategies wrongly invalid) | `backtest_engine/validator.py` |
| M5-1 | AI fell back to Offline Mode silently | `ai_integration/deep_understanding.py`, `multi_pass_extraction.py` |
| M9-1 | candidate generator produced can-never-fire strategies (102 of 132) | `sindhu_strategy/deterministic_builder.py` |

**No safety gate was weakened. No data was deleted.**

---

## PART 1 — Paper Trading Activation (ACTIVE)

| Sub-step | Status | Evidence |
|---|---|---|
| 1.1 Discover paper trading engine architecture | **COMPLETE** | Activation switch = `paper_strategy_config` table (`storage.save_paper_strategy_config`). `strategy_matcher.relevant_strategies()` reads it; opt-in default (`enabled: False` when no row). Engine runs ONE background thread; every enabled strategy competes each tick with its OWN book (`guards.book_key`) — independent balance/PnL/positions/guards confirmed in `risk_manager.evaluate()` + `account_balance(book_key)`. |
| 1.2 List every strategy + win rate, mark >=30% | **COMPLETE** | 31 non-archived strategies with a completed backtest. **18 qualify (>=30% WR)**, 13 do not. Full table below. Source: `sindhu_web.api.home._compute_strategy_summary()` (same data as Home + Compare pages). |
| 1.3 Activate qualifying strategies | **COMPLETE** | All 18 written to `paper_strategy_config` with `enabled=1, priority=5, supported_coins=[], supported_market_types=[]` (no artificial narrowing). Verified: DB has 18 rows, 18 enabled. Zero safety gates touched. |
| 1.4 Prove engine actually running with them loaded | **COMPLETE** | Real `engine.run_single_tick_now()` **opened 26 real paper positions across 7 independent strategy books**. Independence proven concretely: PEPE held LONG by Daily Liquidity Scalping and SHORT by HTF Key Level Engulfing *simultaneously* (same for WLD and ADA) — impossible with a shared book. 5-coin cap respected on every book (4 books hit exactly 5). Matcher returns 18/18. |
| 1.5 pytest full suite, zero regressions | **COMPLETE** | `896 passed in 578.18s` — exactly the expected 896, zero failures, zero regressions. |

### 1.2 — Full win-rate table (real numbers, not estimates)

QUALIFYING (>=30% win rate) — all 18 now ACTIVATED:

| WR% | PF | Trades | Strategy ID | Name |
|---|---|---|---|---|
| 58.55 | 0.9483 | 14993 | 872544b77a57 | Liquidity Sweep + CISD (Pure Swing Variant) |
| 46.07 | 0.7853 | 48947 | b36687e8401a | Daily Liquidity Scalping Strategy |
| 40.43 | 1.0117 | 20253 | 1e0a42397286 | OTE Liquidity Sweep Reversal |
| 39.72 | 1.1939 | 4159 | 59978271c6ce | Liquidity Sweep Reversal Strategy |
| 39.68 | 0.6691 | 18925 | 62e44ad0fa92 | Previous High/Low Reversal |
| 39.65 | 1.0245 | 14761 | bddde91aee6d | Liquidity Sweep Multi-Confirmation |
| 39.03 | 1.0548 | 4479 | b4caef4ee47d | Support/Resistance Breakout |
| 37.91 | 0.8386 | 3287 | 99fbf2454f8a | SMA-Alignment Strategy (Approximate) |
| 37.31 | 0.8626 | 193 | 4334392c8c67 | Supply/Demand Zone Strategy |
| 36.19 | 0.8171 | 771 | 86ceac60820b | 9-20 EMA SMC Hybrid |
| 34.25 | 0.8316 | 3688 | 480cc42075a4 | Asian Range London Sweep |
| 33.74 | 0.7329 | 42013 | 8d527d2e0861 | Candle Range Theory (CRT) 2.0 |
| 33.33 | 0.8097 | 15361 | 0897eb126593 | 4-Hour Range Breakout-Retest |
| 33.27 | 0.6832 | 98556 | b9884b3e5e5d | HTF Key Level Engulfing Reversal |
| 32.82 | 0.6611 | 34221 | 53c80e6c5b6a | 4H Fractal Sweep Reversal |
| 32.74 | 0.7694 | 14248 | d62e5015a93b | Lower TF Liquidity Reversal |
| 31.19 | 1.1435 | 3755 | 1be394d92302 | Candlestick Pattern Reversal |
| 31.00 | 0.1890 | 571 | f4bfea4e22e0 | SAR + SMC (CISD Entry) |

NOT QUALIFYING (<30% win rate) — left OFF, untouched:
Sniper Headshot 29.30 | DMC Confirmation Entry 29.15 | DMC Combined 28.76 |
Double Confirmation CHoCH 26.26 | PDH/PDL MTF Reversal 25.50 | Equal Highs/Lows 25.38 |
DMC Blind Entry 23.67 | Kotegawa Bear Market 23.13 | Laxman Rekha 5-EMA 22.58 |
Market Structure Shift 22.13 | **Fair Value Gap Reversal 19.85 (PF 1.3735)** |
**Order Block Reversal 15.94 (PF 1.1686)** | **Richard Dennis Turtle Trader 6.83 (PF 1.2596)**

> HONEST FLAG: the >=30% win-rate rule excludes the three HIGHEST profit-factor
> strategies in the whole library (Turtle Trader PF 1.2596, FVG Reversal PF 1.3735,
> Order Block Reversal PF 1.1686). These are low-win-rate/high-reward designs — they
> lose often but win big. Rule followed exactly as instructed; flagged, not changed.

### Config change made (a TIGHTENING, not a weakening)
`paper_trading_settings.json` → `max_open_trades`: **50 → 5**. The task specifies a
5-coin limit per strategy; the saved live value was 50 (code default is 5). With 18
strategies now active, 50 each was unreasonable. Every other setting untouched
(verified programmatically). No safety gate modified.

Live settings of note (pre-existing, NOT changed by me): `dry_run=False`,
`initial_balance=100.0`, `risk_pct_default=0.5`, `coin_filter_top_n=50`,
`engine_enabled=False`.

---

## BLOCKERS

### Blocker 1 — Market data was 21.2 days stale — **RESOLVED**
FIX APPLIED: `downloader.download_all()` filled the gap for all 50 symbols
(~31,000 candles each, 24.1 min total, "Download pass complete"). Verified after:
BTCUSDT newest candle moved from 2026-08-08 09:34 → 2026-08-29 22:14 UTC, and
`coin_filter.shortlist()` went from **0 → 50 coins**. Original diagnosis below.

### NEW FINDING (Part 2, module 1 — data_engine): candle timestamps in the FUTURE
After the download, BTCUSDT's newest candle reads **2026-08-29 22:14 UTC** while
`time.gmtime()` says **14:50 UTC** — i.e. the newest stored candle is ~7.4 hours
AHEAD of UTC now. Either the exchange timestamps are being stored in a non-UTC
frame, or the local system clock is behind. Not yet investigated — deferred to
Part 2 module 1 (data_engine) where it belongs. Flagged, not silently ignored.

### Blocker 1 (original diagnosis, kept for the record)
- Newest 1m candle in `sindhu.db`: **2026-08-08 09:34 UTC**. Today: 2026-08-29.
- `coin_filter._coin_activity_score()` looks back only 72 hours → `get_ohlcv()`
  returns **0 rows** for every symbol → `len(df) < 10` → score `None` →
  `shortlist()` returns `[]` → engine tick does nothing. Verified directly:
  `storage.load_symbols` = 50 symbols, `coin_filter.shortlist` = 0.
- Network/exchange is FINE: live Binance ticker fetch returned 735 symbols
  (BTCUSDT 78050.93). So this is purely a stale-database problem.
- ACTION IN PROGRESS: running `downloader.download_all()` to fill the gap
  (resumable — `download_symbol` resumes from last saved candle per symbol).
- SEPARATE BUG FOUND (to fix in Part 2, module 6): `coin_filter.shortlist()` has a
  bare `except Exception: s = None` that swallows ALL per-symbol errors silently —
  a total shortlist failure is indistinguishable from "no coin qualified". This is
  why the engine looked healthy while doing nothing.

### Blocker 2 — stale docstring (cosmetic, fix in Part 2)
`paper_trading/engine.py` `start()` docstring says strategies are "default enabled
when a strategy has no config row yet". That is WRONG — both
`storage.get_paper_strategy_config()` and `strategy_matcher` default to
`enabled: False` (opt-in). Doc-only mismatch, no behavior impact.

---

### 1.4 — Real engine tick evidence (the actual proof)

`engine.run_single_tick_now()` with all 18 activated, `dry_run=False`:

```
OPEN PAPER POSITIONS: 26, across 7 independent strategy books
  STRATEGY                                       COINS  SYMBOLS (direction)
  Daily Liquidity Scalping Strategy                  5  WLD L, PEPE L, POL L, ADA L, ONDO L
  HTF Key Level Engulfing Reversal                   5  WLD S, DEXE L, PEPE S, PUMP L, ADA S
  Support/Resistance Breakout                        5  PUMP L, ARB L, SUI S, ICP L, ASTER S
  Candlestick Pattern Reversal Strategy              5  SHIB S, ARB S, NEAR S, DOGE S, XLM S
  Candle Range Theory (CRT) Strategy 2.0             3  POL S, PUMP L, ASTER S
  Previous High/Low Reversal                         2  ENA L, JST S
  Liquidity Sweep Reversal Strategy                  1  ENA L
  5-coin cap per strategy respected: True
```

Only 7 of the 18 opened trades on this ONE tick — the other 11 are active and
were evaluated, they simply had no qualifying signal on these 50 coins in this
single 60-second window. That is normal, not a failure.

Dynamic Risk Sizing also observed firing correctly in the same tick:
"DEXEUSDT is in a high-volatility market condition (ATR 4.556% of price) --
risk automatically reduced from 0.50% to 0.25% for this trade."

### NEW FINDING (Part 2, module 6 / Part 4 UI): per-strategy panel blind to open trades
`engine.status()["per_strategy"]` is built purely from
`storage.list_paper_account_states()`, which only has a row once a book has
**closed** a trade. With 26 positions open across 7 books, the per-strategy
breakdown returned an EMPTY list and `open_trades` showed 0 per strategy. A
freshly-activated strategy is therefore invisible on the dashboard until its
first trade closes. Flagged; fix belongs in Part 2/4, not Part 1.

---

## PART 2 — Full A-to-Z Audit (ACTIVE)

### Bug fixes applied BEFORE starting the audit (all 3 verified, pytest 896 passed)

| # | Bug | File | Fix | Proof |
|---|---|---|---|---|
| B1 | `coin_filter.shortlist()` swallowed every per-symbol error via bare `except Exception: s = None`. A total failure looked identical to a healthy "no coin qualified" — the engine ticked forever doing nothing with no explanation anywhere. | `paper_trading/coin_filter.py` (+ call site in `engine.py`) | Count + log errors; an empty shortlist now logs why (errored vs under-10-candles) and names the likely cause. Ranking logic byte-for-byte unchanged. | BEFORE: silent `[]`. AFTER: `EMPTY SHORTLIST -- 0 of 3 symbols could be scored (0 errored, 3 had under 10 candles in the last 72h)...`. Healthy case: 5 coins returned, **0 log lines** (correctly quiet). |
| B2 | `engine.status()["per_strategy"]` built only from `paper_account_state`, which gets a row only after a book CLOSES its first trade → a strategy trading right now was invisible. | `paper_trading/engine.py` `status()` | Merge in books that hold open positions at their true state; `combined_balance` now counts their real starting capital too. | BEFORE: 26 open trades, `per_strategy` = **0 entries**, balance 0. AFTER: **7 entries**, balance 700.00, correct per-book open counts (5/5/5/5/3/2/1). |
| B3 | `engine.py` `start()` docstring claimed strategies "default enabled when a strategy has no config row" — the opposite of the real opt-in behaviour. | `paper_trading/engine.py` | Docstring corrected to state the real `enabled=False` default and name both sources. | Doc-only; no behaviour change. |

`pytest -q` after all three: **896 passed in 131.97s**, zero failures, zero regressions.

### Module 1 — `data_engine/` ✅ CLEAN (no bugs found)

| Check | Method | Result |
|---|---|---|
| DB table integrity | `sqlite_master` enumeration | **59 tables**, all present and named coherently |
| Candle volume | `COUNT(*) klines_1m` | **28,459,639 rows**, 50 distinct symbols |
| Duplicate candles | `GROUP BY exchange,symbol,open_time HAVING COUNT(*)>1` | **0 duplicate groups** |
| OHLC validity | `WHERE high<low OR high<open OR high<close OR low>open OR low>close` | **0 invalid rows** |
| Value sanity | `WHERE close<=0 OR volume<0` | **0 bad rows** |
| Candle continuity | per-symbol `(max-min)/60000+1` vs stored count, all 50 symbols | **0 missing of 28,459,639 expected (0.000%)** — no gaps anywhere |
| Download progress | `download_progress` status counts | **50/50 `up_to_date`** |
| Resampling correctness (1m→1h) | resampled bar compared field-by-field against a raw 60×1m aggregation for BTCUSDT | open/high/low/close/volume **all exact matches** |
| **Zero look-ahead** | bucket boundary inspection | bucket is half-open `[start, end)`; the next 1m bar (1788040800000) falls **outside** the bucket it must not influence ✅ |

**FLAGGED, NOT A CODE BUG — environmental clock skew.** Binance itself returns
candles stamped `2026-08-30 07:56 UTC` while this machine's `time.gmtime()` reads
`2026-08-29 17:39 UTC` — the exchange is ~14h ahead of the local clock. The storage
layer faithfully stores what the exchange sends, so this is a machine-clock/timezone
issue, not a defect in `data_engine`. Not "fixed": changing a system clock is a
system setting and is the CEO's call. Practical consequence worth knowing:
`downloader._now_ms()` uses the LOCAL clock as its end cursor, so the downloader can
believe it is "up to date" while genuinely newer exchange data exists.

### Module 2 — `backtest_engine/` ⚠️ 2 REAL BUGS FOUND AND FIXED

#### BUG M2-1 — `macd` used as a comparable indicator read a column that never existed
- **Class:** identical to the historic VWAP (tracker #1) and MACD-wiring (#4) gaps — *declared usable, silently always False*.
- **Detail:** `prepare_context()` writes MACD as **suffixed** columns (`macd_line_12_26_9`, `macd_signal_…`, `macd_hist_…`, 4 cross columns), but `_indicator_column("macd")` returned a bare `entry_macd` that no frame ever contains. `macd` IS in `validator._PARAMETERIZED_INDICATORS`, so the Strategy Wizard openly offers it as a comparable indicator.
- **Evidence BEFORE:** condition `macd > 0` over **8,441 real BTCUSDT 5m bars → fired 0 times**, while the real MACD line was above zero on **4,516** of them.
- **Fix:** `configured_strategy._indicator_column()` now resolves `macd` to `{role}_macd_line_{fast}_{slow}_{signal}`, reusing the same params-lookup and the same 12/26/9 defaults `prepare_context()` applies.
- **Evidence AFTER:** same condition → **fired 4,408 times** (the 108 difference vs 4,516 is exactly the 200-bar warmup the test skips).

#### BUG M2-2 — 5 candlestick patterns were advertised but dead unless an umbrella name was also declared
- **Class:** same declared-but-dead class again (third instance in this codebase).
- **Detail:** `doji_confirm`, `hammer_confirm`, `shooting_star_confirm`, `morning_star`, `evening_star` are all returned by `validator.known_indicator_names()` (so the Wizard offers them and the AI importer can emit them), but their columns were computed **only** behind `if "candlestick_patterns" in used:` — the umbrella name. Declaring just the pattern's own name produced no column, and the `event_colmap` entries then read a non-existent column → silently False forever.
- **Evidence BEFORE** (17,181 real BTCUSDT 5m bars), own-name-only vs umbrella-also-declared:
  `doji_confirm` **0 → 9,528** · `hammer_confirm` **0 → 11,152** · `shooting_star_confirm` **0 → 11,289** · `morning_star` **0 → 5,643** · `evening_star` **0 → 5,563**
- **Fix:** new `_CANDLESTICK_PATTERN_CONCEPTS` set; the gate is now `if used & _CANDLESTICK_PATTERN_CONCEPTS:`. Purely widening — every strategy already declaring the umbrella still matches.
- **Evidence AFTER:** own-name-only now returns **identical** counts to the umbrella case (9,528 / 11,152 / 11,289 / 5,643 / 5,563), and the umbrella path is **byte-identical to before**, so the existing Candlestick Pattern Reversal Strategy is unaffected.

#### Module 2 — everything else CHECKED AND CLEAN

| Check | Method | Result |
|---|---|---|
| Indicator wiring (all 9 parameterized) | built each on real BTCUSDT data, confirmed the merged column exists AND is non-NaN | **9/9 wired** after M2-1 fix (atr, ema, highest_high, lowest_low, macd, rsi, sma, volume, vwap) |
| Structural concept coverage | drove each of 52 advertised concepts through the engine's OWN `_eval()` on 60 days of real data | 30 fire directly; 5 were bug M2-2 (now fire); MACD crosses fire (6,393 / 3,145) once a macd indicator is declared; the rest are **level** concepts (support/resistance/pdh/pdl/poc/value_area/session levels/zones), which are numeric levels not boolean events — correctly not firing as bare boolean conditions |
| SL/TP same-bar conflict | `_check_forced_exit` with a bar touching BOTH | **stop_loss wins** for long and short — pessimistic, no optimistic bias ✅ |
| SL/TP individual touches | 3 cases (TP only / SL only / neither) | all 3 correct |
| Position sizing | 3 balance/entry/stop/risk% combinations | `$risk` matches `balance × risk%` **exactly** in all 3 (100.0000/100.0000/0.5000) |
| Divide-by-zero safety | `stop_loss == entry` and `stop_loss is None` | no crash; falls back to `position_size_pct` (documented behaviour) |
| `metrics.py` correctness | 14 fields against hand-computed values | **all 14 exact** (win_rate 60.0, PF 3.0, expectancy 40.0, risk_reward 2.0, …) |
| `metrics.py` max drawdown | 4 curves incl. empty | all exact (50.00% / 30.00% / 0.00% / 0.00%) |
| `metrics.py` edge cases | zero trades, no losses, pnl exactly 0 | PF returns **`None`, not a fake 0** (honest); `pnl == 0` counted as a LOSS (conservative) |
| `mtf_context` zero look-ahead | code + boundary inspection | higher-TF frames are `df.shift(1)` before `merge_asof(direction="backward")` — an entry bar can only ever see the **previously CLOSED** HTF bar ✅ |
| Resample look-ahead (module 1 cross-check) | bucket boundary | half-open `[start, end)`, next bar excluded ✅ |

#### Module 2 — FLAGGED, NOT FIXED
- **Sharpe ratio is NOT in `backtest_engine/metrics.py`.** The audit brief listed it there; it does not exist in the backtest metrics at all. Sharpe only appears in `paper_trading/capital_allocation.py` (to size capital multipliers). Not a bug — just absent. Adding it would be a new feature, out of audit scope.
- **Ungraceful `KeyError` on a composite concept missing its prerequisite.** Declaring `sweep_invalidation_state` without `liquidity_sweep`, or `double_choch_confirmation` without `choch`+`liquidity_sweep`, raises a raw `KeyError('bull_liquidity_sweep')` mid-run instead of a clear message. With prerequisites declared, `sweep_invalidation_state` works fine (fired 7,809/17,281). Left alone: turning this into a friendly validator error is a behaviour change to shared validation, and no saved strategy currently trips it. Flagged for a future pass.

### Module 7 — `strategies/` ⚠️ 1 REAL BUG FOUND AND FIXED (validator/engine drift)

#### BUG M7-1 — the validator had drifted out of sync with the engine
- **Detail:** 17 composite concept names are fully implemented in `configured_strategy.py` (compute block + dispatch route) and are used by strategies that have already produced real 50-coin backtests — but they were never added to `validator._KNOWN_INDICATORS`. Separately, `_STRUCTURE_SL_SOURCES` (which gates the "structure" stop-loss check) never learned the 6 composites that compute their own structural levels.
- **Why it mattered (not cosmetic):** `paper_trading/strategy_profile.py:55` computes `safety_passed = run_safety_check(cfg)["passed"] and not validator.validate(cfg)`, and `scripts/deploy_ready_strategies_to_paper_trading.py` gates "Ready" status the same way. So working strategies were being reported as unsafe/not-ready.
- **Evidence BEFORE:** **100** unknown-concept errors + **19** structure-SL errors across the library; **50 of 104** strategies reported invalid; **7 of the 18 strategies I activated in Part 1** failing validation.
- **Verification before changing anything** (deliberately did NOT just silence the validator):
  - each of the 17 names confirmed to have a real compute block AND a real dispatch route in the engine;
  - the 6 structure-SL composites checked against **real saved backtest trades** — `dmc_blind_entry` 5047/5047, `dmc_combined` 1867/1867, `dmc_confirmation` 1602/1602, `fractal_sweep_reversal` 34221/34221, `laxman_trigger` 11353/11353, `ote_liquidity_sweep_reversal` 20253/20253 → **74,343 trades, every one with a non-NULL stop_loss, zero NULL**. The old check was a false positive.
- **Fix:** added the 17 verified names to `_KNOWN_INDICATORS` and the 6 verified names to `_STRUCTURE_SL_SOURCES`, each with the evidence recorded in-code.
- **Evidence AFTER:** **0** unknown-concept errors, **0** structure-SL errors, **104/104 strategies valid**, **0 of 18** activated strategies failing. `pytest 896 passed`.

#### Module 7 — other checks
| Check | Result |
|---|---|
| Library entries | **104** (31 active, 73 archived) |
| `strategy_library.load()` on every entry | **104/104 load, 0 failures** |
| `validator.validate()` on every entry | **104/104 valid** (after M7-1 fix) |

### Module 6 — `paper_trading/` guards ✅ ALL 7 VERIFIED CORRECT

| Guard | Test | Result |
|---|---|---|
| **Trade Reservation** | reserve same book+coin twice; reserve from a *different* book; then `release_all()` | 1st `True`, 2nd `False` (blocked), other book `True` (independent), after release `True` ✅ |
| **Duplicate Protection** | fingerprint stability; same signal twice; then a genuinely changed price | fingerprint stable; 1st `False`, 2nd `True` (blocked); changed price `False` (correctly allowed through) ✅ |
| **Signal Priority** | `rank_candidates` over confidences 40/90/65 | picks `high` (90) ✅ |
| **Book Key** (strategy isolation) | strategy candidate vs lesson-only candidate | `abc123` vs `__lessons__` ✅ |
| **Position Lock** | against a REAL open ENAUSDT long | same book+coin+side `True` (blocked); opposite side `False`; untraded coin `False`; a book that does NOT hold ENA → `False` ✅ |
| **Opposite Signal Protection** | all 3 policies | `block`→`block`, `allow`→`proceed`, `close_and_reverse`→`close_and_reverse` (returns the position id to close) ✅ |
| **Cooldown** | 0 / 15 / 100000 minute windows | all `False` — **correct**, because `cooldown_active()` reads `last_closed_paper_position` and there are currently **0 closed positions** (all 26 still open). `cooldown_minutes <= 0` also correctly short-circuits ✅ |

> A first reading of Position Lock looked wrong (a "different book" returned `True`).
> Investigated rather than assumed: **two** books genuinely hold ENAUSDT long
> (Previous High/Low Reversal and Liquidity Sweep Reversal), so `True` was correct.
> Re-tested against a book that does not hold it → `False`. Not a bug.

### Module 11 — Database (`sindhu.db`) ⚠️ CLEAN CORE, 2 THINGS FLAGGED

| Check | Result |
|---|---|
| File size | **11.15 GB** |
| `PRAGMA quick_check` (authoritative corruption test) | **ok** — no corruption |
| `PRAGMA foreign_key_check` | **0 violations** |
| `paper_positions` with null/empty symbol | 0 |
| `paper_strategy_config` orphans | 0 |
| `paper_positions` with an unknown strategy | 0 |
| Row counts | klines_1m 28,459,639 · backtest_trades 2,017,633 · backtest_results 6,723 · paper_decision_log 50 · paper_positions 26 · activity_log 500 |

**FLAGGED (not changed — the "never delete data" rule):**
1. **5 backtest batches stuck in `status='running'`** since 2026-08-23/24 (5–6 days), from sessions that never finished: `20260823_112357_48deb2` (Deliberately Contradictory RSI), `20260823_152326_9c8498`, `20260823_180309_2f39a4`, `20260824_105841_c70f3f` (all Lower TF Liquidity Reversal), `20260824_195434_cf2313` (4-Hour Range Breakout-Retest). Other statuses are healthy: 172 completed, 11 stopped.
2. **Orphaned child records** whose parent batch no longer exists: **444** `backtest_results`, **43,800** `backtest_trades`, **56** `confluence_score_log`. Confirmed **inert** — every read path looks results up by an explicit `batch_id` (`latest_completed_batch_for_strategy_name` → `get_batch_results`), so orphans cannot leak into any aggregate or leaderboard. They are dead weight only.

Both are data-state issues, not code defects. Cleaning either means writing to / removing
rows, which the global constraints forbid without the CEO's say-so — raised at the end.

### Module 5 — `ai_integration/` ⚠️ 1 SILENT FAILURE FOUND AND FIXED

#### BUG M5-1 — an unusable provider chain fell back to Offline Mode SILENTLY
- **Exactly the failure mode the audit brief named** ("a 404 falling back to offline mode without telling the user").
- **Detail:** both `deep_understanding.understand_document_structured()` and `multi_pass_extraction.run_multi_pass_extraction()` returned `"error": None` when `provider_fallback_chain()` came back empty. Callers cannot tell that apart from "the AI ran and genuinely found nothing", so a missing/expired API key silently degraded every import to offline rule-based parsing with nothing anywhere saying why.
- **Fix:** new shared `deep_understanding.NO_PROVIDER_ERROR` returned from both paths. `if not use_ai:` deliberately stays silent — that is the CEO switching AI off on purpose, not a failure.
- **Evidence AFTER** (chain forced empty): both entry points now return *"No usable AI provider is configured (a provider must be both enabled AND have an API key) — falling back to offline rule-based parsing. Check the AI provider settings."* This flows straight into existing handling — `sindhu_web/api/ai_integration.py` raises `HTTPException(422, result["error"])` and `import_queue` marks the item failed with it.

#### Module 5 — everything else CHECKED
| Check | Result |
|---|---|
| `call_provider_chain_generic` (the ONE shared fallback loop) | **Clean, no silent failures.** Tries each provider in order; logs EVERY attempt to `ai_usage_log` including errors and exceptions; accumulates per-provider reasons and returns a joined summary; returns `"no provider attempted"` for an empty chain; documented never to raise. |
| Provider chain ordering | `active_provider` first if usable, then the rest of `SUPPORTED_PROVIDERS` in priority order; only providers that are **enabled AND have a key** are included ✅ |
| Import cache | content-hash dedup (`get_ai_import_cache`) checked in `importer.py` **before** entering the chain, so an unchanged re-import never re-runs ~5 AI calls ✅ |

**FLAGGED — the "6-provider fallback chain" is really a 1-provider chain today.**
Live state: `claude` disabled/no key · **`groq` enabled + key (the only usable one)** ·
`openai` disabled/no key · `gemini` **has a key but is disabled** · `deepseek` disabled/no key.
Resulting chain: `['groq']`. There is no actual fallback — if Groq fails, extraction
degrades to offline immediately. Enabling Gemini would cost nothing (its key is already
there). Not changed: enabling an AI provider is the CEO's decision.

### Module 9 — `evolution_engine/` ⚠️ 1 MAJOR BUG FOUND AND FIXED

#### Governor + rollback — verified working
| Check | Result |
|---|---|
| Concrete limits | `MAX_EXPERIMENTS_PER_RUN=5`, `MAX_GENERATIONS_PER_STRATEGY=25`, `MAX_QUEUE_SIZE=20`, `CPU_LIMIT_PERCENT=60.0`, `RAM_LIMIT_PERCENT=80.0`, `BACKOFF_SECONDS=5.0` |
| Queue cap actually enforced | enqueued past the cap → **blocked at item 20 with `QueueFullError("experiment queue full (20 items)")`**, `queue_size` stayed at 20 ✅ (raises rather than returning False — explicit, good) |
| Live resource check | `check_resources()` → `(14.6 CPU%, 64.2 RAM%)`, `resource_ok()` → `True` ✅ |
| Evolution gate / rollback | `MIN_TRADES_FOR_COMPARISON = 100`, `TRADE_THRESHOLD_STEP = 100`, core metrics `win_rate↑ / total_pnl↑ / avg_profit_factor↑ / max_drawdown_pct↓` ✅ unchanged |

#### "Do candidates actually get backtested?" — the brief's specific question
**The wiring is REAL and WORKS — but it has never once run.**
- Code path verified: `engine._tick()` → `_backtest_untested_candidates()` → `sindhu_lifecycle.validate_and_backtest()` (the genuine backtest pipeline). No silent skip — an empty symbol list logs a clear reason.
- **Proved end-to-end on a real candidate**: ran Candidate #1 through `validate_and_backtest` on AAVEUSDT+ADAUSDT → `validated: True`, a real batch (`20260829_230548_2a1156`) executed over **120,650 + 120,685 bars** and saved results in 47.7s.
- **BUT the live DB says it has never executed:** `bot_strategies` = **132 candidates, 132 still untested, 0 ever backtested**; `evolution_jobs` = **0 rows**. Candidate *generation* has run 12 times (`daily_generation_log` = 12), but generation and backtesting sit on different paths — backtesting only happens inside an Evolution Engine tick, and the Evolution Engine has never been started. Candidates accumulate forever, untested.

#### BUG M9-1 — the candidate generator produces structurally dead strategies
- **Detail:** `evolution_engine/dna.py::_CONCEPT_DNA` tags two different kinds of name in one pool — numeric indicators (`ema`, `sma`, `vwap`, `macd`, `rsi`, `atr`, `volume`) and boolean event concepts (`bos`, `choch`, `order_block`, …). `deterministic_builder.build_candidate()` wrapped **every** drawn name in `Condition(type="concept", name=...)`. A concept condition reads a boolean event column, which numeric indicators do not have → the condition can never be True → that candidate can never trade, ever.
- **Evidence:** **102 of the 132** saved candidates contain at least one such dead condition. Confirmed on the real backtest above — its own condition report read `aggression (within 10 bars)=60474, ema (within 10 bars)=0`: the boolean concept fired 60,474 times, the EMA "concept" **literally never**, across 120,650 bars.
- **Fix:** new `_boolean_concepts_only()` filter in `deterministic_builder.py`, using the existing `validator.parameterized_indicator_names()` as the exclusion set. Deliberately **not** removed from `_CONCEPT_DNA` — `extract_dna()` legitimately needs those names to tag a strategy's DNA (a strategy holding an EMA really does have "trend" DNA).
- **Evidence AFTER:** 12 freshly generated candidates → **0 contain a can-never-fire condition** (was ~77%).
- **Deliberately NOT done, raised for the CEO instead:** making numeric indicators genuinely *usable* here (e.g. emitting `close > ema20` as a `price_compare`) requires choosing an operator and threshold — inventing strategy semantics, not fixing a defect. Existing 132 saved candidates left untouched (never delete data).

### Module 10 — `telegram_bot.py` ✅ CLEAN (logic verified offline, nothing sent)

| Check | Result |
|---|---|
| Signal Freshness Gate | 15 min → fresh, **16 min → stale** (boundary `age > limit`, correct). Missing `entry_time` → never stale (documented "can't judge what isn't recorded") ✅ |
| **Is the gate actually live on real data?** | **all 26 open positions carry `entry_time`** — 0 without. The gate is not silently dead. Sample position aged 255 min → correctly `stale=True` ✅ |
| Price-drift gate | entry 100 → live 100.0/100.4 `False`; 100.6/101.0/99.0 `True` (0.5% threshold, both directions) ✅ |
| Dual-tier decision | `evaluate_auto_send_tier` on a real position → `tier=None`, reason *"confluence Weak -- 1/3 factors aligned below the required bar"* — gate correctly **refusing** to send, with a real reason ✅ |
| High-Confidence marker | absent on a normal message, present only when `high_confidence=True` — never cosmetic ✅ |
| Message formatting | 460-char message generated offline from a real position: direction, strategy, entry/SL/TP, live price, reason, age, and a "not financial advice" disclaimer ✅ |
| Bilingual templates | `ur` → "Abhi Ka Price", `en` → "Current Price" — deterministic templates, no AI translation call ✅ |
| Hourly catch-up sweep | throttled in `engine._tick()` via `TELEGRAM_SWEEP_INTERVAL_SECONDS = 3600`, piggy-backed on the existing tick rather than a second thread; documented never to bypass gating ✅ |

**FLAGGED:** `auto_send_enabled` is **live=True** (default is False) while `_master_enabled()`
is also True — Telegram auto-send is switched ON, even though the network is blocked in
this region. Nothing is reaching Telegram; sends will simply fail. Not changed (a CEO setting).

**FLAGGED:** **5 of the 26 open paper positions have no take-profit** (all 26 DO have a
stop-loss — the critical safety property holds). Affected: Candlestick Pattern Reversal ×3,
Liquidity Sweep Reversal ×1, Support/Resistance Breakout ×1. These use a `structure` TP and
no structural target existed at entry, so those trades ride until their stop-loss or a manual
close. Pre-existing behaviour, consistent with the `structure`-TP notes already in
`NEW_STRATEGIES_CHECKPOINT.md`; not introduced by this audit.

### Module 8 — `sindhu_web/` ✅ CLEAN (no bugs found)

| Check | Method | Result |
|---|---|---|
| Router registration | walked the real `create_app()` route tree (FastAPI wraps included routers in `_IncludedRouter`, so a naive `app.routes` count reads 7 — the true tree was walked) | **246 routes, 239 `/api` endpoints across 30 routers** |
| Duplicate endpoints | `(path, method)` collision count | **0 duplicates** |
| WebSocket | route scan | `/ws/logs` present ✅ |
| Middleware | stack inspection | token guard (`BaseHTTPMiddleware`) + `CORSMiddleware` ✅ |
| Global exception handler | registered? | yes — logs and returns 500 instead of leaking a stack trace ✅ |
| **Security: LAN gate** | 10 addresses incl. loopback, all 3 private ranges, and genuinely routable public IPs | loopback/`::1`/192.168/10.x/172.16-31 **allowed**; `8.8.8.8`, `1.1.1.1`, `172.32.0.1` **refused**; `None` and a malformed string refused ✅ |
| Security: token | generated + persisted | 32-char hex, stable across calls ✅. GET/HEAD/OPTIONS intentionally open (documented, so phones can view dashboards); every state-changing method requires `X-Sindhu-Token` |
| Caching layer | TTL probe with a counting function | within TTL the function ran **once**; after expiry it re-ran ✅ |

> One apparent security finding investigated and **dismissed with evidence**: `203.0.113.9`
> was allowed. That is RFC-5737 TEST-NET-3, and Python's `is_private` covers documentation
> ranges — confirmed `is_global=False` for `203.0.113.9`, `192.0.2.1`, `198.51.100.5`.
> Such addresses are never routed on the real internet, so they cannot reach this server.
> Not a vulnerability; my test's expectation was wrong, not the code.

> Cache behaviour note (by design, not a bug): `cached()` is **stale-while-revalidate** —
> on expiry it returns the stale value immediately and refreshes on a background thread, so
> a dashboard request never blocks. A value can therefore be served up to one TTL stale.

### Modules 3 & 4 — `knowledge_engine/` + `knowledge_compiler/` ✅ CLEAN

| Check | Result |
|---|---|
| Lesson data | 29 lessons (**10 active**, 19 draft); `lesson_applications` = **12,985,309** rows |
| **Both application paths** (the brief's specific ask) | `KnowledgeEngine.for_backtesting()` **and** `.for_paper_trading()` both exist and both load the **same 10 active lessons** ✅ |
| Classifier | real strategy doc → `doc_type='STRATEGY'`, confidence 0.615, sensible score spread (`strategy_rules: 8` dominant) ✅ |
| Section detection | correctly split `entry_rules` and `exit_rules` out of the body ✅ |
| `extract_title` | returned `None` for a bare first line — **correct**: it only matches an explicit `"Title:"`/`"Strategy Name:"` declaration, exactly as its docstring states. Not a bug |
| Dedup | 3 entry conditions with one exact duplicate → **2** (duplicate removed, distinct rule kept) ✅ |
| Conflict detection | RSI `<30` and `>30` together → *"Conflicting conditions in entry conditions: 'rsi' required both above and below in the same rule set."* ✅ |

### Module 12 — ALL SAFETY GATES ✅ RE-VERIFIED **AFTER** EVERY CODE CHANGE

Deliberately re-run at the very end, so this proves none of the 7 fixes weakened anything.

| # | Gate | Verified value | Functional proof |
|---|---|---|---|
| 1 | **Wilson Score (25-trade)** | `MIN_SAMPLE_SIZE = 25` | 24/24 (a perfect 100% record) → `reliable=False, insufficient_data`; 20/25 → `reliable=True`; 5/5 → rejected ✅ |
| 2 | **Evolution gate (100-trade)** | `MIN_TRADES_FOR_COMPARISON = 100` | unchanged ✅ |
| 3 | **Rollback** | `win_rate↑, total_pnl↑, avg_profit_factor↑, max_drawdown_pct↓` | unchanged ✅ |
| 4 | **Confluence threshold** | `>= 0.75` Strong / `>= 0.5` Moderate; pattern `win_rate >= 50.0` | unchanged ✅ |
| 5 | **Signal Freshness** | default 15, live 15 | 15 min fresh, 16 min stale ✅ |
| 6 | **Incomplete Lock** | — | checked across all 18 activated strategies → **0 locked** ✅ |
| 7 | Per-strategy coin cap | `max_open_trades = 5` | my Part 1 tightening still in force ✅ |

**Conclusion: nothing was weakened, bypassed, or removed. `pytest 896 passed` after every fix.**

## PART 3 — End-to-End Verification ✅ COMPLETE — CHAIN UNBROKEN

**Strategy chosen:** `59978271c6ce` — *Liquidity Sweep Reversal Strategy [Manual Build]*
(activated in Part 1, genuinely profitable at PF 1.1939, and holding a live paper position —
so every link could be tested against real state rather than a fixture).

| Link | Check | Evidence | Verdict |
|---|---|---|---|
| **1. Exists in library** | `strategy_library.list_all()` + on-disk file | id `59978271c6ce`, `archived=False`, `strategies/library/59978271c6ce/meta.json` present on disk | ✅ PASS |
| **2. Loads correctly** | `strategy_library.load()` + `validator.validate()` | Returns a real `StrategyConfig`: timeframes `{bias: 1h, entry: 15m}`, concepts `[liquidity_sweep_reclaim, valid_structure_trend, support, resistance]`, 2 long + 2 short entry conditions, SL `signal_candle` (1.5), TP `structure`. **Validator errors: NONE** | ✅ PASS |
| **3. Backtest runs, valid results** | FRESH `run_mtf_batch` over 3 coins (not a cached result) | batch `20260830_003129_6a3c79` in 32.5s → **457 real trades, 241 wins, 52.74% win rate, PF 1.0197**. Per coin: AAVEUSDT 253 trades/PF 0.984, ADAUSDT 94/PF 1.3612 (+1500.64), ALGOUSDT 110/PF 0.8344 | ✅ PASS |
| **4. Appears in paper trading** | 4 independent checks | (a) `paper_strategy_config`: `enabled=True, priority=5`, no coin/market narrowing; (b) the **engine's own matcher** picks it (1 of 18 active); (c) holds a real open position — ENAUSDT long, entry 0.15717855, SL 0.15277350; (d) `engine.status()` per-strategy row present: `balance 100.0, open_trades 1` (this row only exists because of bug-fix B2) | ✅ PASS |
| **5. Valid Telegram payload** | generated offline, **nothing sent** | 460-char / 18-line message with symbol, LONG direction, strategy name, entry, stop-loss, live price, plain-language reason, signal age, and a "not financial advice" disclaimer. All 7 payload sanity checks pass incl. **balanced HTML tags** | ✅ PASS |

### The gates were doing their job — and were NOT bypassed to make this pass
Two gates correctly **refused** to send this particular signal, which is the right outcome:
- `evaluate_auto_send_tier` → `tier=None`, *"confluence Weak -- 1/3 factors aligned below the required bar"*
- `freshness_check` → *"signal is 278 minutes old (limit 15 minutes) -- too stale to send"*

Proved this is the gate and not a broken link: the **same** position, with its timestamp set
to 2 minutes old, returns `stale=False`. The freshness setting was re-read afterwards and is
still **15** — nothing was loosened to obtain a passing result.

**Conclusion: the full chain — library → load → backtest → paper trading → Telegram payload —
works end to end with no broken link.** This is the first time it has been verified in one pass.

Known cosmetic gap seen in the payload: `Take-Profit: -` (this position has no TP — the
`structure`-TP case already flagged in Module 10; 5 of 26 open positions are affected).

## PART 4 — System-Wide Quality Upgrade ✅ COMPLETE

Scope respected: **CSS / layout / structure only.** Everything that would have
needed a data or logic change to look right is flagged below, not changed.
Every fix verified in the real browser at desktop (1440), mobile (375) and in
both light and dark themes. `pytest 896 passed` afterwards; **0 console errors**.

### FIX P4-1 — table cells overlapped each other (the worst visual bug found)
- **Where:** global `table` / `th, td` rules in `app.css`; worst on **Strategy Lifecycle**, but it affected every wide table.
- **Root cause:** `table { width: 100%; overflow: hidden; }` + `th, td { white-space: nowrap; }`. Content could neither wrap (nowrap) nor scroll (`width:100%` caps the table, and `overflow:hidden` clipped instead of letting `.table-wrap`'s `overflow-x:auto` engage). So text simply spilled across neighbouring columns.
- **Measured BEFORE:** Strategy Lifecycle table content wanted **5286px** inside a **1161px** wrapper; `.table-wrap` reported `scrollWidth === clientWidth`, i.e. **it never scrolled at all**. Strategy names, PF values, prose and buttons visibly overlapped; the "Move to paper trading" buttons were cut off.
- **Fix:** removed `overflow: hidden` from `table` (rounding now handled by `.table-wrap`, whose `overflow-x:auto` already clips), added `min-width: min-content`, added `vertical-align: top`, and added `td[style*="max-width"] { white-space: normal; }` — cells that set their own max-width are explicitly asking to wrap, and the global nowrap was silently defeating them.
- **Measured AFTER:** table content **5286px → 1160px**, exactly matching its box. No overlap anywhere. Page body still does **not** scroll horizontally (`docW 1440 == winW 1440`). On Compare, the two tables now genuinely **scroll** (`scrollWidth 1323 > clientWidth 1115`) instead of clipping the Net PNL column — `overflowsCells: false` on both.

### FIX P4-2 — mobile view of any table with sized cells was unusable
- **Where:** the `max-width: 768px` stacked-card table block in `app.css`.
- **Root cause:** cells carry inline `max-width` values sized for **desktop columns** (Strategy Lifecycle uses 220/320/150px). In the mobile layout a `td` is a full-width flex row, so those desktop widths crushed the content.
- **Measured BEFORE (375px):** the "Show more" button rendered **one letter per line vertically** (S-h-o-w-m-o-r-e); the Optimizer values broke into single-character columns (`Lo/os/e:/0./81/0`); strategy names wrapped one word per line; only **one** table row rendered before the page ran out.
- **Fix:** `.content table td[style*="max-width"] { max-width: none !important; }` (`!important` is required precisely because the overridden value is an inline style), plus `flex-wrap: wrap` on the cell and `white-space: nowrap` on buttons inside it.
- **Measured AFTER:** names on one line, Optimizer on one line (`Loose: 0.810 ★ Medium: 0.810 ★ Strict: 0.810 ★`), "Show more" a normal horizontal button on its own line, all rows rendering, full-width action button.

### FIX P4-3 — Concepts Library was a dead end (missing link between related pages)
- **Where:** `sindhu_web/static/concepts.html`.
- **Detail:** it is a standalone static page outside the SPA, so it has none of the app's sidebar or top bar. A reader arriving from *Project → Concepts* had **no way back** except the browser's own back button.
- **Fix:** added a plain `← Back to Dashboard` link (`href="/"`) above the title, with a small scoped style. No new component invented.
- **Verified:** link found in the accessibility tree and **clicked** — it navigates back to the Dashboard.

### FIX P4-4 — Concepts Library strategy pills were clipped mid-word
- **Detail:** the global `.pill { white-space: nowrap; }` is right for short status words, but these pills hold **full strategy names**, which were being cut against the card edge (*"Candlestick Pattern Reversal Strategy [Manual B"*).
- **Fix:** `white-space: normal; max-width: 100%` scoped to `.concept-usage .cu-list .pill` only — every status pill elsewhere keeps `nowrap`.
- **Verified:** names now wrap onto two lines and read in full.

### FIX P4-5 — confusing dashboard label ("752 hours")
- **Detail:** the no-signal alert read *"No signals have been sent to Telegram in the last 752 hours"* — a number nobody converts to "about a month" at a glance.
- **Fix:** new `_humanize_hours()` helper in `telegram_bot.py`, bilingual. **Presentation only** — the payload's `hours_since` field keeps its exact raw value (`752.1`), so nothing that reads the number is affected.
- **Verified:** EN *"No signals have been sent to Telegram for about 4 weeks."* · UR *"Pichle takreeban 4 hafton mein Telegram par koi signal nahi bheja gaya."* Scale checked at 3h/25h/47h/49h/120h/336h/752h/1500h.

### Consistency review — checked, already coherent, deliberately left alone
The design system is already sound and applying it further would have been churn:
- One token set drives both themes (`--green/--red/--yellow/--accent` + `-dim` variants), redefined under `[data-theme]`; status colour meaning is identical across Dashboard, Compare and Strategy Lifecycle (green = profitable, red = losing, yellow = pending).
- Card, pill, table and `.period-tab` components are shared, not re-invented per page.
- **Light theme verified** on Strategy Lifecycle after the table fix — renders correctly, colours consistent, no contrast problems.
- Compare page (recently improved) was polished, **not rebuilt**, exactly as instructed — it inherited the table scroll fix and needed nothing else.

### FLAGGED — needs data/logic changes, so NOT touched in Part 4
1. **Dashboard caption is now inaccurate.** It reads *"there is no live Paper Trading yet, so this reflects the most recent backtest, not a live account."* There are now **26 open paper positions** (0 closed). Correcting this needs logic that distinguishes "no paper trading" from "paper trading with no closed trades yet".
2. **Dashboard headline numbers come from a backtest, not the live account.** Balance $10,129.95 / Win Rate 52.74% / Total Trades 457 are the latest *backtest*, which is confusing beside a live-looking "BALANCE" label. A presentation-only rename would be misleading; this needs a real source decision.
3. **Wide-table scroll affordance.** Compare's tables now scroll correctly, but the cut-off right edge gives no visual hint that scrolling is possible. A fade/shadow affordance would need JS to detect scrollability per table — beyond CSS-only scope.
4. **Uneven KPI card content weight.** The Overview grid mixes big numbers (`$10,129.95`) with a small pill (`Connected`) in identically-sized cards. Harmonising them means changing what those cards render, not just their styling.
