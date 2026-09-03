# New Batch 5 -- 9-Strategy Build Report

Manual construction throughout (no AI extraction, no `strategy_parser.py`, no `ai_integration/` usage). Full 50-coin universe backtests via the existing `backtest_engine.runner.run_mtf_batch` pipeline. Checkpoint: `data/checkpoints/strategy_batch_sept2026.json`.

---

## Strategy 1 -- Liquidity Sweep + Engulfing Candle (4H bias / 5M entry)

**Checkpoint status:** complete.

### StrategyConfig summary (both variants)

| Field | Loose | Strict |
|---|---|---|
| Strategy ID | `96f7cb9100f0` | `594c16205e7f` |
| Timeframes | bias=4h, entry=5m | bias=4h, entry=5m |
| concepts_used | `liquidity_sweep_engulfing_loose`, `engulfing` | `liquidity_sweep_engulfing_strict`, `engulfing` |
| Sweep definition | any wick-or-body-close through the 4H swing level (`low < bias_support` / `high > bias_resistance`) | same-bar wick-beyond-then-close-back-inside (mirrors `concepts.liquidity_sweep()`'s formula) |
| Ordering | `concepts.sequential_event(sweep, engulfing, max_gap=60)` -- sweep must precede the engulfing candle | same |
| Stop-loss | structure (sweep candle's own low/high), buffer 0.65% | same |
| Take-profit | fixed 1:2 RR (source-mandated) | same |
| Risk per trade | 1% | same |
| Entry execution | `next_candle_open` (open of the candle after the engulfing candle closes), `lookback_bars=1` on the Condition so the order queues only on the exact confirming bar | same |

New engine additions (purely additive, no existing strategy touched): two composite concepts `liquidity_sweep_engulfing_loose`/`_strict` in `backtest_engine/configured_strategy.py` (bias-role 4H swing pre-merge, sweep+engulfing ordering post-merge) and `backtest_engine/validator.py` (concept registration + structure-SL source registration). Reused primitives: `concepts.support_resistance` (4H swing), `concepts.engulfing_candle` (body-only, unmodified), `concepts.sequential_event` (ordering), `concepts.liquidity_sweep`'s formula (adapted for the Strict variant against a cross-timeframe level), `cost_model.check_buffer_safety` (0.65% buffer verified >= 2x the real 0.30% round-trip transaction cost).

### Validator

Both variants: **0 errors**, automatic Safety Check status = **ready**.

### Full 50-coin backtest results

BTCUSDT smoke test (Engine Health Report, all 6 dimensions -- Strategy/Data/Execution/PnL/Trade/Statistics): **PASS** for both variants before the full run.

| Metric | Loose (batch `20260902_040509_a31660`) | Strict (batch `20260902_040853_007d14`) |
|---|---|---|
| Symbols tested | 50 / 50 (0 errors, 0 zero-trade coins) | 50 / 50 (0 errors, 0 zero-trade coins) |
| Total trades (pooled) | 43,199 | 4,082 |
| Win rate (pooled) | 32.78% | 15.68% |
| Profit factor (pooled) | 0.7116 | 1.3342 (raw) / **0.7017 excluding one outlier trade** |
| Net profit (pooled, $1000 starting balance per coin) | -$42,912.28 | +$10,088.89 (raw) / **-$8,956.70 excluding one outlier trade** |
| Worst max drawdown (any single coin) | 99.75% | 91.48% |

**Important finding -- do not read the raw Strict numbers as "profitable" without this context:** one single ZECUSDT trade (entry 2026-08-XX, `exit_reason: "end_of_data"`) produced +$19,206.52 profit alone -- 190x the size of a normal winning trade under this strategy's own 1:2 RR / 1% risk design (a normal win is ~$9-10 on a ~$1000 balance). This trade's `take_profit` field was recorded as `null` even though the strategy's take-profit type is a plain fixed 1:2 RR and its own recorded `stop_loss` was a real, correctly-sized number -- so the position never had a target to exit at, and rode a genuine ~24x historical ZEC price move (34.67 -> 829.08) all the way to the end of the available data instead of taking a normal 2R profit.

Investigated (per this batch's own rule 6 -- "suspect a bug before accepting an extreme number") and traced this to a **pre-existing engine behavior, not something introduced by this batch's new code**: sampling other, previously-shipped strategies that also combine `stop_loss.type == "structure"` with `take_profit.type == "rr"` shows the exact same intermittent null-`take_profit` pattern already present in their historical trade data (e.g. "Laxman Rekha 5-EMA ... Fixed 1:2 TP variant": 149/1872 sampled trades null; "Dumb Money Concepts -- Confirmation Entry -- Fixed 1:2 TP variant": 89/200 sampled trades null) -- confirmed present before this session touched anything. Per this task's own rule 8 ("do not modify any existing... engine file... as part of this task"), the underlying cause was not chased further or fixed; it is flagged here as a real, pre-existing issue worth a dedicated follow-up outside this batch's scope. Risk control itself is unaffected by it -- every stop-loss in the sampled trades fired at the correct ~1% risk regardless of whether `take_profit` was populated.

The **"excluding one outlier trade"** figures above are the honest read of this strategy's real performance. Both Confirmation-Strictness variants are net unprofitable pooled across the real 50-coin universe.

### Why-Win/Why-Loss (existing `paper_trading.insights.classify_win_loss`, applied to every real trade)

| Reason | Loose | Strict |
|---|---|---|
| Loss: stop hit as planned | 29,021 | 3,441 |
| Win: target hit | 14,133 | 595 |
| Loss: closed at a loss (other exit, still a loss) | 18 | 1 |
| Win: closed in profit (other exit, still a win) | 27 | 45 |

Reading: the overwhelming majority of both variants' trades resolve exactly as designed (stop hit or target hit) -- the strategy's mechanics work as built. The LOSS comes from win-rate economics: Loose wins 32.78% of the time against a 1:2 RR (breakeven requires ~33.3% before costs), landing almost exactly at breakeven-before-costs and then losing to commission+slippage. Strict's much lower 15.68% win rate (its stricter same-bar wick-reject sweep produces far fewer, and apparently lower-quality, signals -- filtering for "wick only, closed back inside" removes many of the sweeps that would have gone on to reclaim, without a corresponding quality improvement in the ones that remain) is well below the ~33.3% breakeven line.

### Builder defaults used (flagged, not in the source)

- `max_gap=60` 5-minute bars (~5 hours, roughly one 4H bar) between the confirmed sweep and the engulfing candle -- the source mandates the ordering but gives no exact reaction window.
- Stop-loss buffer 0.65% (source only says "slightly below/above" with no number) -- verified via `cost_model.check_buffer_safety()` as >= 2x the real round-trip transaction cost.

### Excluded / not mechanized

- "Deciding whether a setup looks strong or weak" (subjective judgment) -- per the task's own instruction, not mechanized; the strategy trades every sweep-then-engulfing sequence that satisfies its objective rules.

### `ai_integration/` usage check

`grep -rn "ai_integration\|strategy_parser" backtest_engine/configured_strategy.py backtest_engine/validator.py scripts/_tmp_build_strategy1.py` -- **no matches**. Confirmed manual construction only.

---

## Strategy 2 -- Fixed Range Volume Profile (Market Shape Classification)

**Checkpoint status:** complete.

### StrategyConfig summary

| Field | Value |
|---|---|
| Strategy ID | `433942cfbbe0` |
| Timeframe | 1h (single timeframe -- source's own "24-hour session volume profile" crypto convention, same as the existing `frvp_poc_reversal` strategy) |
| concepts_used | `frvp_hvn_reaction`, `frvp_lvn_breakout` |
| Entry structure | 4 `entry_rule_groups` (branching, OR'd): HVN Support (Long), HVN Resistance (Short), LVN Breakout (Long), LVN Breakout (Short) |
| Stop-loss | structure (the HVN zone's own outer edge), buffer 0.65% |
| Take-profit | structure (opposite HVN zone if Capital-B shape, else this leg's own Value Area High/Low) |
| Risk per trade | 1% (not specified in source -- project-standard default) |
| Entry execution | market |

New reusable concept: `concepts.frvp_market_shape()` -- a genuinely new primitive (not a composite of existing pieces), computing POC/VAH/VAL, High/Low Volume Node **zones** (not just a point), and a D/P/b/Thin/Capital-B market-shape classification, anchored to the same swing-to-swing leg construction the existing `fixed_range_volume_profile()` already uses (re-drawn every new confirmed leg). Reused primitives: `swing_points` (leg boundaries), `reaction_at_level` (the source's "wait for a liquidity sweep at the level" entry confirmation), the existing Value-Area-expansion and HVN/LVN-threshold math already established in `volume_profile_previous_day()`/`volume_nodes_previous_day()` (reused at the same 70% / 1.5x / 0.25x settings for consistency, not re-invented).

### Validator

**0 errors**, automatic Safety Check status = **ready**.

### Bug found and fixed during this strategy's own build (not pre-existing)

The first draft placed the new compute block's code as if it ran in the post-merge `prepare()` method (referencing `self.config.concepts_used` and `"entry_"`-prefixed column names), but this logic actually needed to live inside the pre-merge, `@staticmethod` `_compute_concept_columns()` -- causes a `NameError` (`self` undefined in a staticmethod) on every bar. A broad exception boundary elsewhere in the health-report path silently swallowed this and reported a misleading "PASS" with 0 trades instead of surfacing the crash. Caught by this batch's own rule 6 ("0 trades = suspect a bug before accepting the number"): diagnosed with a direct debug script, root-caused, and fixed (unprefixed column names; use the local `used` parameter already available in that method). Re-verified two independent ways -- the BTCUSDT smoke test and a direct `engine.run_backtest()` call -- both now agree on 89 real trades.

### Full 50-coin backtest results

BTCUSDT smoke test (after the fix): 89 trades, Engine Health Report **PASS** on all 6 dimensions.

| Metric | Value (batch `20260902_042813_434f88`) |
|---|---|
| Symbols tested | 50 / 50 (0 errors, 0 zero-trade coins) |
| Total trades (pooled) | 4,374 |
| Win rate (pooled) | 32.60% |
| Profit factor (pooled) | 0.8186 (raw) / **0.6865 excluding one outlier trade** |
| Net profit (pooled, $1000 starting balance per coin) | -$4,917.54 (raw) / **-$8,395.06 excluding one outlier trade** |
| Worst max drawdown (any single coin) | 81.15% |

**Same pre-existing engine observation recurs here, on a different SL/TP type combination:** ZECUSDT's single largest trade (`exit_reason: "end_of_data"`, `take_profit: null`) contributed +$3,741.70 of the +$3,477.52 net profit ZECUSDT itself shows -- again a real historical price move ridden with no take-profit target ever attached, because it never got one (11 of ZECUSDT's 50 trades in this run show `take_profit: null` despite `take_profit.type == "structure"` being a genuinely computable, non-"unknown" spec). This is the SAME null-take_profit phenomenon flagged in Strategy 1 -- now confirmed across two different take_profit types ("rr" and "structure"), reinforcing that it is a general, pre-existing engine behavior and not specific to either strategy's own new code. Not fixed here either, per this task's rule 8. The strategy is net unprofitable pooled across the real 50-coin universe once this single outlier trade is excluded.

### Why-Win/Why-Loss (existing `paper_trading.insights.classify_win_loss`)

| Reason | Count |
|---|---|
| Loss: stop hit as planned | 2,792 |
| Win: target hit | 1,380 |
| Target hit (small loss on fees/slippage) | 154 |
| Win: closed in profit (other exit, still a win) | 46 |
| Loss: closed at a loss (other exit, still a loss) | 2 |

Reading: a 32.6% win rate against structure-based (not fixed-ratio) targets is workable in principle, but "154 target-hit trades that still lost money" points at targets frequently sitting too close to entry relative to real transaction costs (commission+slippage), and the pooled loss confirms the HVN-reaction/LVN-breakout edge itself is not strong enough on the real 50-coin universe to clear that bar.

### Builder defaults used (flagged, not in the source)

- Shape classification thresholds: HVN if a bucket's volume > 1.5x the leg's average bucket volume, LVN if < 0.25x -- reused unchanged from the existing `volume_nodes_previous_day()` for consistency rather than inventing new numbers. P-shape/b-shape trigger at >= 65% / <= 35% of the leg's volume on one side of its own 50% price midpoint; Capital-B requires 2+ separated HVN clusters; Thin requires zero HVN clusters at all; D-shape is everything else.
- **Calibration observation (not a bug, flagged honestly):** on real BTCUSDT 1h data, this classification reads "capital_b" on 10,081 of 10,129 bars (99.5%) -- because Capital-B already permits BOTH long and short setups (same as it permits both in the source's own rules), this heavily reduces how often the shape classification actually RESTRICTS which side can trade in practice, even though the HVN/LVN zone detection and entry mechanics underneath it are functioning correctly. Worth a dedicated recalibration pass outside this batch if Market Shape Classification is meant to be a meaningfully selective filter rather than an almost-always-permissive one.
- Swing-selection for the profile's range endpoints: the existing swing-detection default (same as `fixed_range_volume_profile()`), per the source's own admission that this choice is subjective.
- Stop-loss buffer 0.65%, verified >= 2x round-trip transaction cost (same as Strategy 1).
- Risk 1% of capital per trade (not specified in source).

### Excluded / not mechanized

- "Fast move" exact speed/distance for LVN breakouts -- not defined in source; relied on the LVN/HVN zone logic itself as the operative rule, per the task's own instruction for this strategy.
- "Session Breaks" alternative FRVP application (anchoring to the previous day's full session instead of swing-to-swing) -- documented as a real alternative but not built or backtested, since SINDHU strategies don't use session-anchoring by default (per the task's own instruction).

### `ai_integration/` usage check

`grep -rn "ai_integration\|strategy_parser" backtest_engine/concepts.py backtest_engine/configured_strategy.py backtest_engine/validator.py scripts/_tmp_build_strategy2.py` -- **no matches**. Confirmed manual construction only.

---

## Strategy 3 -- Support/Resistance + Liquidity Sweep (Sideways Market)

**Checkpoint status:** complete.

### StrategyConfig summary (both variants)

| Field | Structure | Fixed-RR |
|---|---|---|
| Strategy ID | `911f386e038c` | `e636f066f17e` |
| Timeframe | 1h (single timeframe, per source) | same |
| concepts_used | `sr_liquidity_sweep_sideways` | `sr_liquidity_sweep_sideways`, `sr_sweep_tp_fixed_rr` (marker) |
| S/R anchor | swing-based `support_resistance()`, approximating "a level reacted to at least twice" | same |
| Long-wick candle | new `concepts.long_wick_candle()`: wick >= 50% of the candle's full range, body-agnostic (source's own default flagged) | same |
| Sequencing | new `concepts.nth_touch_of_level()`: fires from the 3rd touch of the current level onward | same |
| Filter | shorts blocked when `trend_regime()=="up"` (source point 22); longs unaffected | same |
| Stop-loss | structure (the long-wick candle's own low/high), buffer 0.65% | same |
| Take-profit | structure (**reuses the existing generic entry_support/entry_resistance fallback** -- "recent high"/"recent low", no new code needed) | structure, but a precomputed real target price wins first: **+1:2.5 (long) / +1:2 (short)**, two different ratios delivered through the same generic structure-TP mechanism |
| Risk / Entry | 1% / `next_candle_open` both sides (source's explicit short-side wording, applied consistently to longs too, matching Strategy 1's convention) | same |

Two genuinely new reusable primitives added to `concepts.py`: `long_wick_candle()` (also reused unmodified by Strategy 7 below) and `nth_touch_of_level()` (generalizes the existing `first_signal_per_level()`'s "retire once used" idea into a real running touch count).

### Validator

Both variants: **0 errors**, automatic Safety Check status = **ready**.

### Engine observation (pre-existing, not this strategy's own bug)

The BTCUSDT smoke test's Engine Health Report flagged `execution_verification: FAIL` for both variants -- 1 trade each where the recorded `take_profit` exit price fell outside that exit bar's real high/low range. Traced directly to `backtest_engine/trade_validator.py`'s own existing tolerance check (a pre-existing, already-built verification tool designed exactly to catch this) -- the underlying cause is a "price gapped clean through the target within one candle" fill-price edge case in the shared `engine.py` exit mechanics, made more likely here because a "recent swing high/low" target can sit far from current price across a multi-year 1h dataset spanning a huge price range. Same class of issue already flagged for Strategies 1/2 (all three sit on the exit-price/take-profit path), confirmed pre-existing and out of this task's scope to fix (rule 8). Sampled across 15 of the 50 real coins each: **~1.55%** of Structure-variant trades and **~0.51%** of Fixed-RR-variant trades hit this tolerance check -- a real but small minority; every other verification dimension (Strategy/Data/PnL/Trade/Statistics) passed cleanly for both variants.

### Full 50-coin backtest results

No zero-trade coins, no errored coins, and (unlike Strategies 1-2) **no single-coin outlier dominates either pooled result** -- checked directly: the largest individual contributions (ZECUSDT +$4,591/52 trades for Structure, and three coins around -$800 to -$860 each for Fixed-RR) are ordinary, well-distributed results, not one-trade artifacts.

| Metric | Structure (batch `20260902_043952_474327`) | Fixed-RR (batch `20260902_044013_156a8b`) |
|---|---|---|
| Symbols tested | 50 / 50 | 50 / 50 |
| Total trades (pooled) | 12,052 | 14,369 |
| Win rate (pooled) | 40.47% | 44.55% |
| Profit factor (pooled) | 0.6727 | 0.6690 |
| Net profit (pooled, $1000 starting balance per coin) | -$18,105.19 | -$25,541.59 |
| Worst max drawdown (any single coin) | 95.16% | 86.57% |

Both variants are clearly net unprofitable pooled across the real 50-coin universe -- no outlier adjustment needed to see this; the raw numbers already tell the honest story.

### Why-Win/Why-Loss (existing `paper_trading.insights.classify_win_loss`)

| Reason | Structure | Fixed-RR |
|---|---|---|
| Loss: stop hit as planned | 6,097 | 7,885 |
| Win: target hit | 4,849 | 6,395 |
| Target hit (small loss on fees/slippage) | 1,065 | 63 |
| Win: closed in profit (other exit) | 28 | 7 |
| Loss: closed at a loss (other exit) | 13 | 19 |

Reading: Structure's 1,065 "target hit but still a loss" trades (8.8% of all its trades) are the tell -- a "recent swing high/low" target is frequently CLOSE enough to entry that commission+slippage alone erases the nominal win, a direct consequence of using an unconstrained structural distance instead of a minimum-quality target filter. Fixed-RR's much smaller such count (63, 0.4%) confirms a fixed 1:2.5/1:2 minimum distance largely avoids that specific failure mode, yet still loses overall -- both variants' underlying entry edge (long-wick rejection at a 3rd/4th-tested S/R level) is not strong enough on the real 50-coin universe to overcome transaction costs at either exit style.

### Builder defaults used (flagged, not in the source)

- Long-wick threshold: wick >= 50% of the candle's own range (source gives no exact number).
- "3rd or 4th time" touch counting: `n=3` (fires from the 3rd touch onward, matching "3rd OR 4th" as "a few tests", not one exact count).
- "Strongly upward trend" (source point 22): `concepts.trend_regime()`'s existing "up" state (EMA(50) + ATR(14)-based) -- this batch's consistent, reused default for every "trend/sideways" filter across Strategies 3, 4, 7, 9.
- Fixed-RR ratios taken literally from source (1:2.5 long, 1:2 short) -- not builder defaults, but flagged since they required a new delivery mechanism (SLTPSpec has no native per-direction RR field).
- Stop-loss buffer 0.65%, risk 1% -- same as Strategies 1-2.

### Excluded / not mechanized

- "Common sense" judgment about targets being too far / stops too tight (source point 29) -- not mechanized, per the task's own instruction; relies on the structural/fixed-RR rules above instead.
- "Test until you have confidence before real capital" (source point 30) -- not a mechanizable trading rule, ignored for engine purposes per the task's own instruction.

### `ai_integration/` usage check

`grep -rn "ai_integration\|strategy_parser" backtest_engine/concepts.py backtest_engine/configured_strategy.py backtest_engine/validator.py scripts/_tmp_build_strategy3.py` -- **no matches**. Confirmed manual construction only.

---

## Strategy 4 -- FVG Momentum Pullback (Trending Market)

**Checkpoint status:** complete.

### StrategyConfig summary (all 3 TP variants)

| Field | Structure | Fixed 1:2 | Fixed 1:3 |
|---|---|---|---|
| Strategy ID | `df643d86c987` | `5a26c66ffa42` | `54c9f3b67aa6` |
| Timeframe | 1h (single, per source) | same | same |
| concepts_used | `fvg_momentum_pullback` | same | same |
| FVG construction | reuses `fair_value_gap()`/`fvg_zone()` entirely, unmodified (classic 3-candle gap) | same | same |
| Momentum candle | gap-producing candle's own `body_pct >= 50%` (same threshold this batch already uses for "large/momentum candle") | same | same |
| Entry | edge-triggered pullback to the FVG's 50% midpoint | same | same |
| Filter | shorts blocked when `trend_regime()=="up"` (source point 22, shared with Strategy 3) | same | same |
| Stop-loss | structure (FVG zone's own outer edge), buffer 0.65% | same | same |
| Take-profit | structure (reuses the generic entry_resistance/entry_support fallback -- "recent high"/"recent low") | fixed 1:2 RR | fixed 1:3 RR |
| Risk / Entry | 1% / market | same | same |

Unlike Strategy 3, the Fixed-RR variants here use the SAME ratio for both long and short, so the generic `take_profit.type="rr"` mechanism applies directly -- no precomputed columns needed. `first_signal_per_level()` is applied to prevent unlimited re-entries into the same still-open gap -- a builder default (not stated in source) matching the sibling `fvg_equilibrium_entry` strategy's own convention.

### Validator

All 3 variants: **0 errors**, automatic Safety Check status = **ready**.

### Full 50-coin backtest results -- important outlier finding

BTCUSDT smoke test: all 3 variants Engine Health **PASS** on all 6 dimensions, all 3 even profitable on that one coin.

| Metric | Structure (`20260902_044544_27a315`) | Fixed 1:2 (`20260902_044604_8a57e9`) | Fixed 1:3 (`20260902_044618_03829e`) |
|---|---|---|---|
| Symbols tested | 50 / 50 | 50 / 50 | 50 / 50 |
| Total trades (pooled) | 4,417 | 2,903 | 2,881 |
| Win rate (pooled) | 24.95% | 11.64% | 9.27% |
| Profit factor (pooled, **raw**) | **1.0157** | **1.2274** | **1.2091** |
| Net profit (pooled, raw) | **+$415.71** | **+$5,021.13** | **+$4,711.18** |

**On the raw numbers alone, this looks like the first genuinely profitable strategy in this batch. It is not -- checked per this batch's own rule 6, and the check overturns the headline number:** ZECUSDT alone contributes +$10,580.66 (Structure), +$10,052.34 (Fixed 1:2), and +$9,398.06 (Fixed 1:3) -- MORE than the entire pooled net profit in every single variant. Inspecting ZECUSDT's own trades finds the exact same signature already flagged in Strategies 1 and 2: one trade (`exit_reason: "end_of_data"`, `take_profit: null`) rides ZEC's real historical price run all the way to the end of the dataset, contributing +$10,894.02 alone. **25 of ZECUSDT's 50 trades in the Structure variant show `take_profit: null`** -- the highest incidence of this pre-existing engine observation seen anywhere in this batch so far.

| Metric | Structure (excl. ZEC) | Fixed 1:2 (excl. ZEC) | Fixed 1:3 (excl. ZEC) |
|---|---|---|---|
| Symbols | 49 | 49 | 49 |
| Total trades | 4,367 | 2,858 | 2,837 |
| Win rate | 24.94% | 11.65% | 9.34% |
| Profit factor | **0.6099** | **0.768** | **0.7881** |
| Net profit | **-$10,164.95** | **-$5,031.20** | **-$4,686.87** |

All three variants are **net unprofitable** once this single outlier trade is excluded -- the honest number, not the raw one. This is now the FOURTH strategy/variant set in this batch where a single ZECUSDT `end_of_data`/null-`take_profit` trade single-handedly flips the headline verdict from "profitable" to "unprofitable." Given the recurrence rate, **every remaining strategy in this batch will be checked for the same ZECUSDT pattern by default**, not just when a result looks surprising.

### Why-Win/Why-Loss (existing `paper_trading.insights.classify_win_loss`)

| Reason | Structure | Fixed 1:2 | Fixed 1:3 |
|---|---|---|---|
| Loss: stop hit as planned | 3,143 | 2,564 | 2,613 |
| Win: target hit | 1,067 | 298 | 226 |
| Target hit (small loss on fees/slippage) | 171 | 0 | 0 |
| Win: closed in profit (other exit) | 35 | 40 | 41 |
| Loss: closed at a loss (other exit) | 1 | 1 | 1 |

Reading: Fixed-RR's much lower win rate (11.64%/9.27% vs Structure's 24.95%) reflects the wider 1:2/1:3 target sitting further from entry than a typical "recent high/low," rarely reached -- and once ZEC's outlier is removed, neither the tighter Structure target nor the wider Fixed targets clear break-even. The entry edge itself (FVG pullback after a momentum candle, in a non-strongly-up-blocked direction) is not strong enough on the real 50-coin universe.

### Builder defaults used (flagged, not in the source)

- Momentum-candle threshold: `body_pct >= 50%` on the gap-producing candle (source gives no exact number; same convention as Strategy 3/`fractal_sweep_reversal`).
- `first_signal_per_level()` applied to avoid unlimited re-entries into a persistent gap -- not stated in source, matches the sibling `fvg_equilibrium_entry` strategy's own choice.
- "Strongly upward trend" filter: `trend_regime()`'s "up" state, same project-wide default as Strategy 3.
- Stop-loss buffer 0.65%, risk 1% -- same as prior strategies.

### Excluded / not mechanized

- Exact "slightly below/above" SL distance -- standard buffer default, not a new invented number, per the task's own instruction.
- Exact "recent high/low" definition -- the existing swing-detection default, consistent with every other strategy in this codebase.

### `ai_integration/` usage check

`grep -rn "ai_integration\|strategy_parser" backtest_engine/configured_strategy.py backtest_engine/validator.py scripts/_tmp_build_strategy4.py` -- **no matches**. Confirmed manual construction only.

---

## Strategy 5 -- FVG Pure + Inverse FVG

**Checkpoint status:** complete.

### StrategyConfig summary (both variants)

| Field | Structure | Fixed 1:2 |
|---|---|---|
| Strategy ID | `7c8a8f40ce2a` | `edb442d731aa` |
| Timeframe | 1h (single, per source) | same |
| concepts_used | `fvg_pure_inverse` | same |
| Base setup | reuses `fair_value_gap()`/`fvg_zone()` + Strategy 4's exact momentum-candle (`body_pct>=50%`) and midpoint-pullback formulas | same |
| Inverse FVG (new) | a broken bullish FVG (price closes below it) flips into a SHORT trigger at that same zone's midpoint, returned to from below; mirrored for a broken bearish FVG -> LONG (source only detailed the bullish-broken case; mirror is a structural inference, not discretionary) | same |
| Mitigation filter | interpreted as `first_signal_per_level()`'s existing "one trade per zone, ever" mechanism -- **not** `concepts.mitigation_blocks()` (a structurally different, BOS-triggered Order-Block-body zone concept unrelated to "has this specific FVG been touched before") | same |
| Stop-loss | structure: base setup uses its own zone's outer edge; inverse setup uses the SAME (now polarity-flipped) zone's OTHER edge | same |
| Take-profit | structure (generic entry_resistance/entry_support fallback) | fixed 1:2 RR (Strategy 4 already covers 1:3, so 1:2 keeps the two strategies' fixed-RR variants distinct rather than duplicating one) |
| Risk / Entry | 1% / market | same |

### Validator

Both variants: **0 errors**, automatic Safety Check status = **ready**.

### Architectural limitation flagged (not fixed)

Source rule 11 ("FVG Size Priority: if multiple FVGs appear simultaneously, prioritize the larger one") cannot be mechanized as written: the existing `fvg_zone()`/`fair_value_gap()` primitives (reused unmodified, as required) track only the single MOST-RECENTLY-FORMED active zone per direction, not multiple simultaneous overlapping zones -- there is no multi-zone state to compare sizes against without a genuine rework of a primitive several other strategies in this codebase also depend on. Judged out of scope for this batch; not attempted as a one-off hack.

### Full 50-coin backtest results

BTCUSDT smoke test: both variants Engine Health **PASS** on all 6 dimensions.

**Same ZECUSDT outlier pattern recurs a fifth/sixth time** (Structure: 106 ZEC trades, Fixed 1:2: 54 ZEC trades, 35 of which show `take_profit: null`) -- one `end_of_data` trade worth +$10,010.67 alone exceeds the Fixed 1:2 variant's entire pooled net profit.

| Metric | Structure (`20260902_045240_ddf802`) | Fixed 1:2 (`20260902_045257_92a9ef`) |
|---|---|---|
| Symbols tested | 50 / 50 | 50 / 50 |
| Total trades (pooled, raw) | 10,226 | 3,617 |
| Win rate (raw) | 34.45% | 12.28% |
| Profit factor (raw) | 0.8065 | **1.1318** |
| Net profit (raw) | -$7,858.03 | **+$3,306.79** |
| Profit factor (excl. ZEC) | 0.5847 | **0.7429** |
| Net profit (excl. ZEC) | -$16,615.41 | **-$6,334.83** |

Both variants are **net unprofitable** once the outlier is excluded -- the Fixed 1:2 variant's raw "profitable" headline is, again, entirely a single-trade artifact.

### Why-Win/Why-Loss (existing `paper_trading.insights.classify_win_loss`)

| Reason | Structure | Fixed 1:2 |
|---|---|---|
| Loss: stop hit as planned | 5,828 | 3,172 |
| Win: target hit | 3,489 | 397 |
| Target hit (small loss on fees/slippage) | 873 | 0 |
| Win: closed in profit (other exit) | 34 | 47 |
| Loss: closed at a loss (other exit) | 2 | 1 |

Reading: Structure's 873 "target hit but still lost" trades (8.5%) show the same too-close-a-target issue seen in Strategy 3. Fixed 1:2's low 12.28% win rate needs roughly 33% to break even before costs -- neither the base pullback setup nor the Inverse FVG reversal setup produces enough edge on the real 50-coin universe to get there.

### Builder defaults used (flagged, not in the source)

- Momentum-candle threshold: `body_pct >= 50%`, same as Strategy 4.
- Mitigation filter interpretation: `first_signal_per_level()` (see above) -- a deliberate reading of an ambiguous primitive reference, not a guess at a missing number.
- Stop-loss buffer 0.65%, risk 1% -- same as prior strategies.

### Excluded / not mechanized

- "Prioritize Discount FVGs at the start of a new trend over ones after a trend is more than half finished" (source point 10) -- excluded per the task's own explicit instruction (no objective measure of "just started" vs "half finished" exists without inventing a new trend-strength indicator).
- FVG Size Priority (source point 11) -- see architectural limitation above.

### `ai_integration/` usage check

`grep -rn "ai_integration\|strategy_parser" backtest_engine/configured_strategy.py backtest_engine/validator.py scripts/_tmp_build_strategy5.py` -- **no matches**. Confirmed manual construction only.

---

## Strategy 6 -- Order Block Trading

**Checkpoint status:** complete.

### StrategyConfig summary (both variants)

| Field | Loose | Strict |
|---|---|---|
| Strategy ID | `90a2331a3b1c` | `52c6ab43fd4a` |
| Timeframe | 1h (not specified in source -- builder default) | same |
| concepts_used | `order_block_trading_loose`, `support`, `resistance` | `order_block_trading_strict`, `support`, `resistance` |
| Indicators | none | EMA(200), EMA(50) on entry role |
| OB definition | this codebase's own established, BOS-triggered `concepts.order_blocks()` -- the source's "large momentum candle after a correction" trigger is approximated via the SAME operational definition every other Order-Block strategy here already uses, not a second parallel candle-size-triggered detector | same |
| Base filters | no trade without an accompanying FVG (`fair_value_gap()`); no trade on a mitigated OB (`order_block_validity()`); no trade if liquidity was already swept in the 3 bars before OB formation (`liquidity_sweep()`) -- all three reused unmodified, all three explicit in source | same |
| Strict-only filter | price above/below BOTH EMA(200) and EMA(50) in the trade direction | -- |
| Stop-loss | structure (OB zone's own outer edge), buffer 0.65% | same |
| Take-profit | structure -- see bug below | same |
| Risk / Entry | 1% / market | same |

### Validator

Both variants: **0 errors**, automatic Safety Check status = **ready**.

### Bug found and fixed during this strategy's own build (not pre-existing)

BTCUSDT smoke test's first pass showed a suspiciously near-0% win rate (2.86% / 3.85%) -- flagged immediately per this batch's own rule 6. Diagnosed: **0 of 35 trades had ANY take-profit set.** Root cause: the generic `entry_resistance`/`entry_support` structure-TP fallback is structurally unusable for an Order Block continuation trade -- a bullish OB's own swing "resistance" is, by definition, the OLD level price already broke ABOVE to create the very uptrend the OB sits inside, so it always sits BELOW the current entry price and can never pass the generic branch's own "target must be above price" check. Every trade could therefore only ever end via stop-loss -- a guaranteed-loss-by-construction bug, the exact failure mode already documented (and previously fixed for a different case) elsewhere in `configured_strategy.py`'s own comments.

Fixed with a genuinely forward-looking target: a 100-bar rolling high (long) / rolling low (short), standing in for "the next level price needs to clear to keep going." After the fix, BTCUSDT trade count jumped from 35/26 to 306/286 -- a legitimate consequence, not a second bug: under the broken logic, positions with no take-profit sat open for very long stretches waiting for a distant stop-loss, and while a position was open, `first_signal_per_level()`'s one-shot-per-level entries on OTHER Order Blocks silently expired unused. Real take-profits resolve positions far faster, so far more of those one-shot signals actually get taken -- both changes verified together against real trade data.

### Full 50-coin backtest results

No zero-trade coins, no errored coins, **no outlier concentration** (checked directly: the largest single-coin contributions are small, ordinary results on 1-3 trades each, nothing resembling the ZECUSDT pattern).

| Metric | Loose (`20260902_050052_c99526`) | Strict (`20260902_050114_59bc72`) |
|---|---|---|
| Symbols tested | 50 / 50 | 50 / 50 |
| Total trades (pooled) | 13,962 | 11,615 |
| Win rate (pooled) | 29.80% | 36.25% |
| Profit factor (pooled) | 0.6675 | 0.6114 |
| Net profit (pooled, $1000 starting balance per coin) | -$26,056.65 | -$23,930.74 |
| Worst max drawdown (any single coin) | 91.02% | 86.34% |

Both variants clearly net unprofitable pooled across the real 50-coin universe -- the EMA(200)/EMA(50) Strict filter improves win rate (36.25% vs 29.80%) but at a similar overall loss, since it also cuts trade count by ~17% without a matching quality improvement.

### Why-Win/Why-Loss (existing `paper_trading.insights.classify_win_loss`)

| Reason | Loose | Strict |
|---|---|---|
| Loss: stop hit as planned | 9,594 | 7,154 |
| Win: target hit | 4,145 | 4,194 |
| Target hit (small loss on fees/slippage) | 197 | 242 |
| Win: closed in profit (other exit) | 15 | 16 |
| Loss: closed at a loss (other exit) | 11 | 9 |

Reading: both variants' mechanics work exactly as designed (the overwhelming majority resolve via a clean stop or target), but a ~30-36% win rate against a wide (100-bar rolling extreme) target isn't enough edge to clear transaction costs on the real 50-coin universe.

### Builder defaults used (flagged, not in the source)

- Timeframe: 1h (source specifies none).
- OB-accompanying-FVG window: within 3 bars of OB formation (source gives no exact window).
- Pre-OB-sweep exclusion window: 3 bars before OB formation (source gives no exact window).
- Take-profit target: 100-bar rolling high/low (see bug fix above -- not a source-given number, chosen after the generic fallback was found non-functional for this strategy specifically).
- Stop-loss buffer 0.65%, risk 1% -- same as prior strategies.

### Excluded / not mechanized

- "Large" momentum-candle exact threshold and "a little below" SL distance -- both use this batch's established defaults (body_pct convention, standard buffer), per the task's own instruction, since the OB trigger itself is delegated to the existing BOS-based definition rather than a separate candle-size gate.

### `ai_integration/` usage check

`grep -rn "ai_integration\|strategy_parser" backtest_engine/configured_strategy.py backtest_engine/validator.py scripts/_tmp_build_strategy6.py` -- **no matches**. Confirmed manual construction only.

---

## Strategy 7 -- Candle Range Theory (CRT)

**Checkpoint status:** complete.

### StrategyConfig summary (both variants)

| Field | Loose | Strict |
|---|---|---|
| Strategy ID | `2f6ff7755c8f` | `eba4cc77ee31` |
| Timeframe | 1h (source's own stated minimum) | same |
| concepts_used | `crt_loose` | `crt_strict` |
| CRH/CRL | the last "large candle" (`body_pct>=50%`, same convention as Strategies 4-6) own high/low, held until the next qualifying candle -- own simplification of the source's "redraw on sweep failure" nuance (flagged, not built as a separate stateful rule) | same |
| Sweep | `concepts.liquidity_sweep()`'s exact formula, copied against CRL/CRH instead of a same-frame swing (same technique as `fractal_sweep_reversal`), gated by `concepts.long_wick_candle()` (source's own "must be a genuine long-wick candle" requirement, reused unmodified from Strategy 3) | same |
| Filter | no trade when `trend_regime()=="sideways"` (source explicit) | same, plus EMA(200)+EMA(50) alignment (same as Strategy 6) and Fibonacci confirmation (price within 0.25x ATR of the 50% or 61.8% retracement of the most recent swing) |
| Stop-loss | structure (below CRL / above CRH), buffer 0.65% | same |
| Take-profit | fixed 2:1 RR (source-mandated) | same |
| Risk / Entry | 1% / `next_candle_open`, `lookback_bars=1` (source's explicit "execute on the candle immediately following the sweep candle") | same |

`concepts.fibonacci_retracement_zone()` only ever computes the 38.2/50/61.8% levels -- the source's explicit "do NOT enable 78% or 23%" needed no extra code, since those levels were never options to begin with.

### Validator

Both variants: **0 errors**, automatic Safety Check status = **ready**.

### Engine observation (pre-existing, same class as Strategy 3)

BTCUSDT smoke test flagged `execution_verification: FAIL` for both variants (2/419 Loose, 2/84 Strict) -- the identical "price gapped through the fixed 2:1 RR target within one candle" fill-price edge case already confirmed pre-existing in Strategy 3's report. Sampled across 15 of the 50 real coins: **~1.22%** of Loose trades and **~1.64%** of Strict trades hit this tolerance check. All other 5 verification dimensions passed cleanly for both variants.

### Full 50-coin backtest results

No zero-trade coins, no errored coins, **no outlier concentration** (every coin's individual contribution is negative or negligible -- checked directly, nothing resembling the ZECUSDT pattern here).

| Metric | Loose (`20260902_050624_daca3e`) | Strict (`20260902_050652_674090`) |
|---|---|---|
| Symbols tested | 50 / 50 | 50 / 50 |
| Total trades (pooled) | 24,750 | 4,412 |
| Win rate (pooled) | 33.50% | 33.14% |
| Profit factor (pooled) | 0.7016 | 0.6734 |
| Net profit (pooled, $1000 starting balance per coin) | -$35,207.41 | -$10,310.11 |
| Worst max drawdown (any single coin) | 92.14% | 50.16% |

Both variants clearly net unprofitable pooled across the real 50-coin universe. The Strict filter cuts trade count by ~82% and roughly halves the worst drawdown, but win rate barely moves (33.14% vs 33.50%) -- the EMA/Fibonacci confluence filters select for FEWER trades, not meaningfully BETTER ones.

### Why-Win/Why-Loss (existing `paper_trading.insights.classify_win_loss`)

| Reason | Loose | Strict |
|---|---|---|
| Loss: stop hit as planned | 16,445 | 2,949 |
| Win: target hit | 8,287 | 1,460 |
| Win: closed in profit (other exit) | 4 | 2 |
| Loss: closed at a loss (other exit) | 14 | 1 |

Reading: virtually every trade resolves via a clean stop or target (mechanics work as designed) -- a ~33% win rate against a fixed 2:1 RR needs ~33.3% to break even before costs, so both variants sit almost exactly AT the theoretical break-even line and then lose to commission+slippage, the same signature seen in Strategy 1's Loose variant.

### Builder defaults used (flagged, not in the source)

- "Large candle" threshold: `body_pct >= 50%`, same convention as Strategies 4-6.
- CRH/CRL redraw: simplified to "held until the next qualifying large candle" rather than the source's own "redraw on sweep failure" refinement (flagged, not separately mechanized -- see StrategyConfig summary above).
- Fibonacci confirmation band: 0.25x ATR(14) around the 50%/61.8% level (source gives no exact tolerance).
- "Sideways market" / EMA trend alignment: `trend_regime()`, same project-wide default as Strategies 3/4.
- Stop-loss buffer 0.65%, risk 1% -- same as prior strategies.

### Excluded / not mechanized

None beyond the CRH/CRL redraw simplification noted above -- this source was otherwise unusually well-defined (the task's own note).

### `ai_integration/` usage check

`grep -rn "ai_integration\|strategy_parser" backtest_engine/configured_strategy.py backtest_engine/validator.py scripts/_tmp_build_strategy7.py` -- **no matches**. Confirmed manual construction only.

---

## Strategy 8 -- BOS/CHoCH Structure Break + Strong Level Retest

**Checkpoint status:** complete. (Narrowed, mechanical extraction from a much larger discretionary source document -- see Excluded section below for what was deliberately left out.)

### StrategyConfig summary

| Field | Value |
|---|---|
| Strategy ID | `2e4f21179b50` |
| Timeframe | 1h (not specified in source -- consistent default) |
| concepts_used | `bos_choch_retest` |
| Trend / break | `concepts.break_of_structure()` + `concepts.change_of_character()`, reused unmodified -- BOS (continuation) and CHoCH (reversal) both treated as "a break that creates a Strong Level to retest," per the source's own framing |
| Strong Level | the swing support/resistance level that got broken, held until retested -- generalizes the existing `mss_reversal` strategy's own CHoCH-only "broken level -> retest -> `sequential_event()`" composition to BOS\|CHoCH together |
| Retest | `concepts.reaction_at_level()`, unmodified |
| CHoCH confirmation rule | "don't assume valid until the candle is fully closed" -- already guaranteed by construction; every concept here only ever reads fully-closed bars |
| Stop-loss | structure (the broken Strong Level itself), buffer 0.65% |
| Take-profit | structure -- proactively uses the SAME 100-bar rolling high/low forward target invented for Strategy 6's bug fix, not the generic entry_resistance/entry_support fallback (a Strong-Level retest is the same kind of continuation trade where that generic fallback is already known to sit behind price) |
| Risk / Entry | 1% / market |

Applying Strategy 6's fix proactively here avoided a repeat of that exact bug -- confirmed by the smoke test showing a realistic win rate on the first attempt (no 0%-take-profit pattern found).

### Validator

**0 errors**, automatic Safety Check status = **ready**.

### Full 50-coin backtest results

BTCUSDT smoke test: Engine Health **PASS** on all 6 dimensions, realistic win rate (25.45%) on the first attempt.

| Metric | Value (batch `20260902_051221_a086a1`) |
|---|---|
| Symbols tested | 50 / 50 (0 errors, 0 zero-trade coins) |
| Total trades (pooled) | 10,358 |
| Win rate (pooled) | 23.31% |
| Profit factor (pooled) | 0.7081 |
| Net profit (pooled, $1000 starting balance per coin) | -$17,847.29 |
| Worst max drawdown (any single coin) | 96.5% |

ZECUSDT again shows an above-average result (+$1,232.11 / 113 trades) but, checked directly, is a small, ordinary fraction of the total pool this time -- not a dominating outlier. Net unprofitable pooled across the real 50-coin universe.

### Why-Win/Why-Loss (existing `paper_trading.insights.classify_win_loss`)

| Reason | Count |
|---|---|
| Loss: stop hit as planned | 7,725 |
| Win: target hit | 2,377 |
| Target hit (small loss on fees/slippage) | 213 |
| Win: closed in profit (other exit) | 37 |
| Loss: closed at a loss (other exit) | 6 |

Reading: a 23.31% win rate against a wide (100-bar rolling extreme) target is the lowest win rate seen so far in this batch's "structure TP" strategies -- Strong Level retests fire relatively often (10,358 trades pooled) but the retest itself is a weak predictor of a genuine continuation on the real 50-coin universe.

### Builder defaults used (flagged, not in the source)

- Timeframe: 1h (source specifies none).
- Break-to-retest window: `max_gap=30` 1h bars (~5 trading days) -- source requires a retest but gives no exact reaction window.
- Take-profit target: 100-bar rolling high/low, reused directly from Strategy 6's own fix.
- Stop-loss buffer 0.65%, risk 1% -- same as prior strategies.

### Excluded / not mechanized (per the task's own explicit narrowing instruction -- this source document covers far more than what was built)

Trendlines and the "3rd-touch reliability" rule; Supply & Demand zones as a separate entry method; Double Top/Bottom (M/W) chart patterns; a dedicated "All Candlestick Pattern" tool; Liquidity Grab as a separate entry method (already covered by Strategies 1 and 3); FVG as a separate entry trigger (already covered by Strategies 4, 5, 6); a "strong/large candle" breakout filter (not needed -- this strategy's trigger is the structural break itself, not candle size); any Weekly/Monthly/Daily multi-timeframe bias stacking beyond the base HH/HL trend identification.

### `ai_integration/` usage check

`grep -rn "ai_integration\|strategy_parser" backtest_engine/configured_strategy.py backtest_engine/validator.py scripts/_tmp_build_strategy8.py` -- **no matches**. Confirmed manual construction only.

---

## Strategy 9 -- Ichimoku Cloud System

**Checkpoint status:** complete. Final strategy in this batch.

### StrategyConfig summary (all 8 combinations: 4 timeframes x 2 exit modes)

| Field | Value |
|---|---|
| concepts_used | `ichimoku_system` (entry, shared across all 8); `ichimoku_cross` (exit-only, Indicator-Exit variants) |
| New primitive | `concepts.ichimoku_cloud()` -- standard Conversion(9)/Base(26)/SpanA/SpanB(52)/displacement(26). Span A/B use a **positive** `.shift(26)` (pulling past data forward) -- never a lookahead-inducing negative shift. "Lagging Span above/below price" is returned directly as two booleans (current close vs. close 26 bars ago) rather than as a plotted line, since a genuine plotted lagging-span line would require an illegal negative shift for a live trading decision -- documented explicitly in the function's own docstring |
| Entry | all THREE confirmations (Conversion-vs-Base state, Lagging-Span state, Cloud color) combined via AND, then edge-triggered once -- fires on whichever bar all three FIRST align, "may be the crossover candle itself or a subsequent one" (source's own wording) -- deliberately not `sequential_event()` (that orders two distinct events; this is simultaneous state alignment) |
| Filter | no trade when `trend_regime()=="sideways"` (source explicit) |
| Stop-loss | structure (the crossover candle's own low/high), buffer 0.65% |
| Execution asymmetry | LONG uses `long_entry_type="next_candle_open"` override (source: "immediately following"); SHORT uses the base `entry_type="market"` (source states no next-candle delay for shorts) -- StrategyConfig's existing per-direction override field, no new code |
| Exit -- Indicator-Exit | new `ichimoku_cross` exit-only concept (Conversion crossing back over Base), wired via `exit_conditions` with `exit_direction`; a wide 1:10 RR is also set purely to satisfy the validator's "must have a take-profit or trailing_stop" schema rule -- **not** a real intended exit |
| Exit -- Trailing-SL | StrategyConfig's already-existing generic `trailing_stop` field (`atr_multiple`, value 2.0) -- **zero new engine code** for this variant |
| Risk | 1% throughout |

| Timeframe | Indicator-Exit ID | Trailing-SL ID |
|---|---|---|
| 5m | `86a1e5062c20` | `a7be577a2752` |
| 15m | `04598eaca214` | `beab3636067e` |
| 1h | `ca0777badd9f` | `770d68250de1` |
| 1d | `d781b37694ef` | `8d94d5ee403f` |

### Validator

All 8 combinations: **0 errors**, automatic Safety Check status = **ready**.

### Suspicious-result check (rule 6)

BTCUSDT smoke test's **5m Indicator-Exit** showed `-100.0%` profit_pct (near-total account wipeout) -- investigated directly rather than accepted at face value: 4,129 trades, 12.21% win rate, individual trade `pnl_pct` values are small and consistent (roughly -0.3% to -0.8% per loss, no single blow-up trade), and `final_balance` settles at $0.0044, approaching zero smoothly rather than going negative. This is **genuine, not a bug**: a negative-expectancy strategy applied at very high frequency with percentage-of-balance position sizing decays a real account toward zero exactly this way. Reported as-is, per rule 7.

### Full 50-coin backtest results (all 8 combinations)

All 8 Engine Health **PASS** on the BTCUSDT smoke test. No errored coins in any of the 8 full runs; 1d's two variants each had 1 zero-trade coin (GRAMUSDT, likely too little daily history).

| Variant | Trades (pooled) | Win rate | Profit factor (raw) | Net profit (raw) |
|---|---|---|---|---|
| 5m Indicator-Exit | 188,818 | 18.93% | 0.4116 | -$49,744.25 |
| 5m Trailing-SL | 743 | 6.33% | **1.4599** | **+$3,489.17** |
| 15m Indicator-Exit | 66,896 | 24.34% | 0.5972 | -$47,694.13 |
| 15m Trailing-SL | 572 | 8.04% | **1.1865** | **+$1,066.27** |
| 1h Indicator-Exit | 18,318 | 27.18% | 0.7108 | -$24,645.61 |
| 1h Trailing-SL | 517 | 8.70% | **2.2965** | **+$6,596.55** |
| 1d Indicator-Exit | 902 | 28.60% | 0.9361 | -$359.89 |
| 1d Trailing-SL | 126 | 33.33% | **2.0640** | **+$932.94** |

**A striking, fully consistent pattern: every Indicator-Exit variant loses money at every timeframe; every Trailing-SL variant shows a raw profit at every timeframe.** Checked per this batch's now-standard outlier policy before trusting that:

| Trailing-SL variant | ZECUSDT's own net profit | Pooled net (excl. ZEC) | Pooled PF (excl. ZEC) |
|---|---|---|---|
| 5m | +$4,505.98 (16 trades) | **-$1,016.81** | 0.8629 |
| 15m | +$2,214.37 (11 trades) | **-$1,148.09** | 0.7953 |
| 1h | +$7,934.03 (11 trades) | **-$1,337.47** | 0.7314 |
| 1d | +$406.47 (1 trade) | **+$526.47** | **1.6004** |

Three of the four Trailing-SL "wins" are, again, single-coin artifacts -- ZECUSDT alone exceeds the ENTIRE pooled net profit in the 5m/15m/1h variants. Inspecting the 1h case specifically: one trade (`exit_reason: "end_of_data"`, +$8,043.52) rides a real ZEC trend all the way to the end of the available data. **This is a materially different situation from Strategies 1/2/4/5's bug**, though: a trailing-stop strategy is DESIGNED to have no fixed take-profit and let a winning trend run -- riding a genuinely still-open, still-favorable trend to the end of the backtest window is not a malfunction, it's the mechanism working as intended on a real historical move that simply hadn't reversed yet when the data ran out. It is still, however, a single-coin concentration that makes 3 of the 4 "profitable" headlines fragile rather than robust.

**The 1d Trailing-SL variant is the one genuinely, robustly profitable result in this entire 9-strategy batch** -- it stays profitable (+$526.47, profit factor 1.60) even with ZECUSDT completely excluded, on 125 trades pooled across 49 coins.

### Why-Win/Why-Loss (existing `paper_trading.insights.classify_win_loss`)

The Indicator-Exit variants show mostly "closed at a loss"/"closed in profit" (generic exit-condition tags, since `ichimoku_cross` isn't a stop_loss/take_profit exit_reason) rather than "target hit" -- consistent with an indicator-exit mechanism, not a fixed-target one. The Trailing-SL variants show overwhelmingly "stop hit as planned" (the trailing stop itself, tightening as price moves favorably) alongside a small number of "closed in profit" -- exactly the shape expected of a trend-following trailing exit: many small stopped-out attempts, occasional large trend-following wins.

### Builder defaults used (flagged, not in the source)

- Trailing-SL distance: 2x ATR(14) (source offers the trailing-SL alternative but gives no exact distance).
- Indicator-Exit's 1:10 RR safety-net target -- a schema-compliance necessity, not a real intended exit (see above).
- "Sideways market" filter: `trend_regime()`, same project-wide default as Strategies 3/4/7.
- Stop-loss buffer 0.65%, risk 1% -- same as prior strategies.

### Excluded / not mechanized

None -- the task's own note that this source was "unusually well-defined" held true; every rule had an objective, mechanizable reading.

### `ai_integration/` usage check

`grep -rn "ai_integration\|strategy_parser" backtest_engine/concepts.py backtest_engine/configured_strategy.py backtest_engine/validator.py scripts/_tmp_build_strategy9.py` -- **no matches**. Confirmed manual construction only.

---

## Combined Summary -- Every Variant, Every Strategy

All figures: pooled across the real 50-coin universe, $1000 starting balance per coin, 1% risk per trade unless noted. "excl. ZEC" rows only shown where a single ZECUSDT trade materially changed the verdict (Strategies 1, 2, 4, 5, 9-trailing).

| Strategy | Variant | Trades | Win rate | Profit factor | Net profit | Max DD |
|---|---|---|---|---|---|---|
| 1. Liquidity Sweep + Engulfing | Loose | 43,199 | 32.78% | 0.7116 | -$42,912.28 | 99.75% |
| 1. Liquidity Sweep + Engulfing | Strict (raw) | 4,082 | 15.68% | 1.3342 | +$10,088.89 | 91.48% |
| 1. Liquidity Sweep + Engulfing | Strict (excl. ZEC) | 4,067 | 15.71% | 0.7017 | -$8,956.70 | 91.48% |
| 2. FRVP Market Shape | (raw) | 4,374 | 32.60% | 0.8186 | -$4,917.54 | 81.15% |
| 2. FRVP Market Shape | (excl. ZEC) | 4,324 | 32.63% | 0.6865 | -$8,395.06 | 81.15% |
| 3. S/R + Liquidity Sweep | Structure | 12,052 | 40.47% | 0.6727 | -$18,105.19 | 95.16% |
| 3. S/R + Liquidity Sweep | Fixed-RR | 14,369 | 44.55% | 0.6690 | -$25,541.59 | 86.57% |
| 4. FVG Momentum Pullback | Structure (raw) | 4,417 | 24.95% | 1.0157 | +$415.71 | 84.12% |
| 4. FVG Momentum Pullback | Structure (excl. ZEC) | 4,367 | 24.94% | 0.6099 | -$10,164.95 | 84.12% |
| 4. FVG Momentum Pullback | Fixed 1:2 (raw) | 2,903 | 11.64% | 1.2274 | +$5,021.13 | 91.02% |
| 4. FVG Momentum Pullback | Fixed 1:2 (excl. ZEC) | 2,858 | 11.65% | 0.7680 | -$5,031.20 | 91.02% |
| 4. FVG Momentum Pullback | Fixed 1:3 (raw) | 2,881 | 9.27% | 1.2091 | +$4,711.18 | 91.02% |
| 4. FVG Momentum Pullback | Fixed 1:3 (excl. ZEC) | 2,837 | 9.34% | 0.7881 | -$4,686.87 | 91.02% |
| 5. FVG Pure + Inverse | Structure (raw) | 10,226 | 34.45% | 0.8065 | -$7,858.03 | 91.78% |
| 5. FVG Pure + Inverse | Structure (excl. ZEC) | 10,120 | 34.43% | 0.5847 | -$16,615.41 | 91.78% |
| 5. FVG Pure + Inverse | Fixed 1:2 (raw) | 3,617 | 12.28% | 1.1318 | +$3,306.79 | 91.67% |
| 5. FVG Pure + Inverse | Fixed 1:2 (excl. ZEC) | 3,563 | 12.24% | 0.7429 | -$6,334.83 | 91.67% |
| 6. Order Block Trading | Loose | 13,962 | 29.80% | 0.6675 | -$26,056.65 | 91.02% |
| 6. Order Block Trading | Strict | 11,615 | 36.25% | 0.6114 | -$23,930.74 | 86.34% |
| 7. Candle Range Theory | Loose | 24,750 | 33.50% | 0.7016 | -$35,207.41 | 92.14% |
| 7. Candle Range Theory | Strict | 4,412 | 33.14% | 0.6734 | -$10,310.11 | 50.16% |
| 8. BOS/CHoCH Retest | (single variant) | 10,358 | 23.31% | 0.7081 | -$17,847.29 | 96.50% |
| 9. Ichimoku | 5m Indicator-Exit | 188,818 | 18.93% | 0.4116 | -$49,744.25 | 100.00% |
| 9. Ichimoku | 5m Trailing-SL (raw) | 743 | 6.33% | 1.4599 | +$3,489.17 | 75.08% |
| 9. Ichimoku | 5m Trailing-SL (excl. ZEC) | 727 | 6.33% | 0.8629 | -$1,016.81 | 75.08% |
| 9. Ichimoku | 15m Indicator-Exit | 66,896 | 24.34% | 0.5972 | -$47,694.13 | 99.97% |
| 9. Ichimoku | 15m Trailing-SL (raw) | 572 | 8.04% | 1.1865 | +$1,066.27 | 70.27% |
| 9. Ichimoku | 15m Trailing-SL (excl. ZEC) | 561 | 8.02% | 0.7953 | -$1,148.09 | 70.27% |
| 9. Ichimoku | 1h Indicator-Exit | 18,318 | 27.18% | 0.7108 | -$24,645.61 | 93.60% |
| 9. Ichimoku | 1h Trailing-SL (raw) | 517 | 8.70% | 2.2965 | +$6,596.55 | 68.79% |
| 9. Ichimoku | 1h Trailing-SL (excl. ZEC) | 506 | 8.70% | 0.7314 | -$1,337.47 | 68.79% |
| 9. Ichimoku | 1d Indicator-Exit | 902 | 28.60% | 0.9361 | -$359.89 | 22.58% |
| 9. Ichimoku | 1d Trailing-SL (raw) | 126 | 33.33% | 2.0640 | +$932.94 | 19.81% |
| **9. Ichimoku** | **1d Trailing-SL (excl. ZEC)** | **125** | **32.80%** | **1.6004** | **+$526.47** | **19.81%** |

**Bottom line: of 34 variant results across 9 strategies, exactly ONE is genuinely, robustly profitable once every known outlier and bug is accounted for -- Ichimoku 1d, Trailing-SL exit.** Every other variant loses money on the real 50-coin universe once the ZECUSDT single-trade artifact (where one applies) is excluded.

## Cross-Cutting Engine Findings (affect multiple strategies, not fixed per this task's rule 8)

1. **Intermittent null `take_profit`, despite a valid `stop_loss` and a normally-computable TP spec.** First found in Strategy 1, then reproduced in Strategies 2, 4, and 5, and in pre-existing (already-shipped, pre-dating this session) strategies "Laxman Rekha 5-EMA ... Fixed 1:2 TP variant" and "Dumb Money Concepts -- Confirmation Entry -- Fixed 1:2 TP variant." Confirmed pre-existing, not introduced by this batch. Effect: a trade with no take-profit can only exit via stop-loss or ride to `end_of_data` -- when that happens on a coin with a large real historical move (ZECUSDT, repeatedly, in this dataset), one trade can flip a strategy's entire pooled verdict from unprofitable to "profitable."
2. **Rare gap-through-target fill-price mismatch**, caught by the existing `trade_validator.py` tolerance check (`execution_verification`). Found in Strategies 3 and 7 (both use fixed-RR or wide structural targets on volatile, multi-year 1h data) -- roughly 0.5-2.4% of trades in the affected strategies. Confirmed pre-existing.
3. **Generic `entry_resistance`/`entry_support` structure take-profit fallback is structurally unusable for continuation trades** -- a swing-based "resistance" is, by definition, already BEHIND price once a breakout/continuation trade is underway, so it fails the fallback's own "target must be above price" (long) / "below price" (short) check on effectively every trade. Found and fixed for Strategy 6 (Order Block Trading) using a new 100-bar rolling-high/low forward target instead, and applied proactively to Strategy 8 as well. This is a real, reusable fix, not a one-off hack -- worth checking whether any OTHER continuation-style strategy in the existing library quietly has the same defect.

## Deferred Questions for the CEO (asked together, as instructed, in simple English)

1. **The ZECUSDT / missing-take-profit issue (finding #1 above) kept changing whether a strategy "looked" profitable, four separate times in this batch.** Do you want this made into its own dedicated bug-fix task? It sits outside what this batch was allowed to touch (existing engine files), but it's a real, repeatable issue.
2. **Should ZECUSDT get special handling in future 50-coin backtests** (e.g., a report always shows "with ZEC" and "without ZEC" side by side by default), given how often one single ZEC trade swung a whole strategy's headline number in this batch?
3. **Ichimoku on the 1d timeframe with a Trailing Stop-Loss exit is the one strategy in this entire batch that is genuinely profitable even after removing the ZEC outlier** (+$526, profit factor 1.60, 125 trades across 49 coins). Do you want this one fast-tracked for further scrutiny (a Walk-Forward Test, then Paper Trading), separately from the rest of this batch, which are all clearly unprofitable and would otherwise all get archived together?
4. **The "structure take-profit is broken for continuation trades" fix (finding #3 above) was applied to 2 of the 9 new strategies here.** Should the SAME fix be checked against other, older, already-shipped continuation-style strategies in the library that might be quietly losing the same way?
5. **Strategy 5's "prioritize the larger of several simultaneous FVGs" rule could not be mechanized** without reworking the shared `fvg_zone()`/`fair_value_gap()` primitives (they only track one active zone at a time, and several other strategies depend on them as-is). Worth a dedicated follow-up, or leave as a known, documented limitation?

## Final Checkpoint State

All 9 strategies marked `"status": "complete"` in `data/checkpoints/strategy_batch_sept2026.json`, each with its own `sub_stage: "report_written"`, real backtest batch IDs, and evidence (validator output, Engine Health Report results, pooled metrics) -- nothing marked complete without the real numbers backing it, per this batch's own rule 4.
