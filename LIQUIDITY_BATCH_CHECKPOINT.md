# Liquidity Sweep Batch (3 New Strategies) — Checkpoint (FINAL — PART A + PART B COMPLETE)

Resume rule: read this file first. Skip any strategy marked DONE. Continue
exactly at the strategy marked IN_PROGRESS (or the first PENDING one if
none is IN_PROGRESS). Never re-run a DONE strategy's backtest.

Part A must fully complete (all 3 strategies through backtest -> Optimizer
-> Why-Win/Loss -> Confirmation-Strictness -> Lifecycle Page) before Part B
(Concepts Library cross-reference) starts.

| # | Strategy | Status | Strategy ID | Backtest | Lifecycle flow |
|---|----------|--------|-------------|----------|-----------------|
| 1 | Liquidity Sweep Multi-Confirmation | DONE | bddde91aee6d | 14761 trades, PF 1.0245, PROFITABLE (barely; concentrated in JSTUSDT) | why-win/loss done; Medium PF 1.0245 (byte-identical to baseline -- the 0.65% SL buffer already exceeds Medium's 0.6% min filter, so it never discards anything); Strict PF 1.0027 (min_rr=2.0, win rate dropped to 25.81% but trade count paradoxically INCREASED to 19277 -- same discard-frees-position-slot mechanism documented in the prior batch's Equal Highs/Lows and Sniper Headshot anomalies) |
| 2 | Liquidity Sweep + CISD (Pure Swing Variant) | DONE | 872544b77a57 | 14993 trades, PF 0.9483, LOSING (high 58.55% win rate, reward too small) | why-win/loss done; Medium PF 0.9483 (byte-identical to baseline, same reason as Strategy 1); Strict PF 1.0412, net +23019.79, win rate 48.6% -- FLIPS TO PROFITABLE (min_rr=1.5 filters out the smallest-reward trades that were dragging PF below 1.0; this is the batch's standout result) |
| 3 | OTE Liquidity Sweep Reversal | DONE | 1e0a42397286 | 20253 trades, PF 1.0117, PROFITABLE (broadly distributed, not one-coin outlier) | why-win/loss done; Medium PF 1.0117 (byte-identical to baseline, same reason as Strategy 1); Strict (min_rr raised 3.0->4.0) PF 1.0098, net +10205.78 -- marginally WORSE than baseline/Medium, so Loose=Medium is this strategy's best variant |

Part A verification: pytest 896 passed (zero regressions) after all 3 strategies +
optimizer variants built. Strategy Lifecycle page verified live in-browser for
Strategy 1 (profitable-confirm dialog) and Strategy 2 (losing-warning dialog),
both cancelled with no side effect. All 3 strategies' real backtest/why-loss/
optimizer numbers confirmed via /api/strategy-lifecycle to match the table above.

Part B (Concepts Library cross-reference): DONE.
- New file sindhu_web/api/concepts_usage.py: GET /api/concepts/usage, joins
  every active (non-archived) strategy's real concepts_used list against a
  documented alias map (Concepts Library display name -> concepts_used
  key(s)) covering all 22 concept entries in concepts_reference.json. Pure
  literal-match, no name-guessing (a strategy whose composite concept is
  built ON TOP OF a primitive without that primitive's own key also present
  in concepts_used is honestly NOT counted -- flagged in the module's own
  docstring, e.g. PDH/PDL Multi-Timeframe Reversal's concepts_used is just
  ['pdhl_mtf_reversal', ...], no literal 'pdh'/'pdl', so it does not count
  toward the "Previous High/Low" card despite the obvious semantic link).
- sindhu_web/static/concepts.html: additive "N strategies using this
  concept" section + strategy-name pill list on every card (both defined
  and not-yet-defined show a real, sometimes-0 count), fetched alongside
  the existing concepts_reference.json via Promise.all. No existing concept
  content/definitions or strategy data modified; no new page/nav entry.
- Found and fixed (during Part B's own browser verification) a PRE-EXISTING
  bug in concepts.html's renderDetail(): 3 concept detail objects (Support
  & Resistance, Previous High/Low, Premium & Discount) are missing one or
  more optional sections (why_location_matters, golden_rule, long_setup/
  short_setup, cases) that renderDetail() accessed unconditionally --
  crashed and wiped the ENTIRE #categories render (including the new
  cross-reference section) via the outer .catch(). Fixed with null-guards
  only (no content added/changed) so a missing optional section is simply
  skipped instead of crashing the whole page.
- Verified live in-browser: all 22 concept cards show correct real counts
  (e.g. Liquidity Sweep=4, Support & Resistance=18, Fair Value Gap=2,
  Premium & Discount=0 plainly shown, Inverted Hammer/Hanging Man/Spinning
  Top/Tweezer Top/Tweezer Bottom/Three White Soldiers/Three Black Crows=0),
  matching /api/concepts/usage exactly; card click-to-expand still works
  including for the 3 previously-broken concepts; clicking inside the new
  usage pill list does not also toggle the detail box.
- pytest: 896 passed after Part B (zero regressions), same as after Part A.

## Engine changes made (backtest_engine/configured_strategy.py)
- New pre-merge block (prepare_context): computes bias-role support/
  resistance for all 3 strategies, plus per-strategy sweep detection
  (level_sweep_reclaim+sequential_event for Strategy 1, liquidity_sweep for
  Strategy 2, valid_structure_trend for Strategy 3) -- gated behind
  `if "<concept_name>" in used:` checks, zero effect on existing strategies.
- New post-merge composite blocks (prepare): one each for
  liquidity_sweep_multi_confirm, liquidity_sweep_cisd_swing,
  ote_liquidity_sweep_reversal.
- New event_colmap entries for all 3 concept names.
- Additive-only: "bias_support"/"bias_resistance" appended to the END of
  the existing "structure" SL and "structure"/"structure_or_rr" TP
  candidate lists (same pattern as h4_support/h4_resistance added for the
  previous 4H Fractal Sweep Reversal strategy) -- byte-for-byte unchanged
  for every strategy that doesn't reach that fallback.
- pytest: 896 passed after these changes, before building any of the 3
  strategies (confirmed zero regressions from the engine-code step alone).

## Design decisions (all 3 use role name "bias" for their HTF)
- Strategy 1 (Liquidity Sweep Multi-Confirmation): bias=4H (source allowed
  Daily/4H/1H; 4H picked as the single own-default bias TF -- "high/low of
  a large HTF candle (4H or Daily)" per the task's own wording), entry=5m.
  CISD path only (default/primary); FVG path explicitly out of scope for
  v1 per the task's own instruction.
- Strategy 2 (Liquidity Sweep + CISD, Pure Swing): bias=1H, entry=5m (the
  task's own default pairing). The alternative 4H bias -> 15m entry pairing
  is architecturally identical (same code, different timeframes_by_role)
  but was NOT separately backtested for v1, to keep this batch's scope to
  3 base strategies -- flagged, not silently skipped. Reuses the existing
  SAR+SMC CISD entry's exact stage-3/4/5 code shape (last opposite candle
  -> line -> confirm close -> retrace touch), just re-anchored to a
  bias-role liquidity sweep trigger instead of "sharp move in zone."
  Conservative TP only (nearest visible high/low); extended-target
  secondary mode explicitly out of scope for v1.
- Strategy 3 (OTE Liquidity Sweep Reversal): bias=1H, entry=15m. OTE zone =
  62%-79% Fib retracement from bias role's most recent confirmed swing
  high/low (bias_support/bias_resistance). Long-side (uptrend) logic is a
  mirrored default since the source only detailed shorts explicitly --
  flagged per the task's own instruction. Hard 3R-or-skip filter
  implemented via the EXISTING generic min_risk_reward_filter +
  risk_reward_filter_uses_take_profit=True mechanism (already used by
  SAR+SMC's own baseline config), set directly in the base config rather
  than as an optimizer-only variant, since the task requires it as a v1
  rule. Mean Reversion/distribution-channel concept and FVG-retest
  alternative entry excluded per the task's own explicit instruction.
- Risk 1% default (own default, not source-derived) for all 3, standard
  50-coin universe, 24/7 no session restriction, per the task's global
  rules.
