# New Batch 4 (5 Strategies) — Checkpoint (FINAL — ALL 5 COMPLETE)

## STATUS: COMPLETE.

Process: build -> backtest (50 coins) -> Lifecycle flow (Optimizer/Why-Win-Loss/
Confirmation-Strictness), ONE STRATEGY AT A TIME, fully complete before starting
the next. Update this file after each real step so work resumes exactly here if
interrupted (power loss / session end / usage limit).

## Global rules (unchanged from New Batch 3)
- Never touch existing strategies/engine logic/safety gates (Wilson, Evolution,
  rollback, Confluence, Freshness, Incomplete Lock).
- Risk 1% default. Standard 50-coin universe. Honest results, no adjustment.
- SL buffer 0.65% for every new structure SL (2x+ the 0.6% cost_model minimum).

## Strategy IDs (saved, library)
| # | Strategy | Strategy ID |
|---|----------|--------------|
| 1 | Heikin Ashi Trend Reversal | `e25028146948` |
| 2 | Fibonacci Golden Zone Retracement | `e2d090ed4ff4` |
| 3 | FRVP POC Reversal | `3fef95339b15` |
| 4 | FVG 50% Equilibrium Entry | `143a732de079` |
| 5 | Donchian LWTI Volume Confluence | `0113516effdb` |

## Shared engine work (done BEFORE any strategy's backtest, to avoid validator/
## engine drift -- see New Batch 3's own lesson)
- [x] concepts.py: `heikin_ashi()`, `fibonacci_retracement_zone()`,
      `fixed_range_volume_profile()`, `lwti()` -- 3 genuinely new reusable
      concepts + 1 new standard indicator.
- [x] validator.py: 5 composite concept names registered in
      `_KNOWN_INDICATORS`/`_CONCEPT_REQUIRES_ANY_OF`/`_STRUCTURE_SL_SOURCES`
      BEFORE any strategy was built (done this time, not after).
- [x] configured_strategy.py: pre-merge (prepare_context/_compute_concept_columns)
      + post-merge (prepare()) composite blocks for all 5, event_colmap entries,
      SL candidate-column insertions for all 5.
- [x] All 5 strategies saved to library (see table above). No validator errors
      at save/safety-check time.

## Design notes / own defaults (flagged, not blocking)
- Strategy 1: HA flip computed on the BIAS(1H) role (source didn't specify which
  TF the flip itself fires on); short side is a mirrored builder default.
- Strategy 5: LWTI is a builder's own deterministic reconstruction (WMA momentum,
  ATR-normalized, EMA-smoothed) -- multiple community LWTI variants exist and the
  source gives no exact formula matching its own "+50/-50" banding.
- Strategy 5: SL uses the Donchian mid-line (own choice, cost_model-verified)
  rather than swing-low/high (source said "whichever is safer").
- None of these required CEO input -- resolved via clearly-flagged own defaults,
  consistent with prior batches' convention.

## Per-strategy status
| # | Strategy | Build | Smoke test | 50-coin baseline | Medium | Strict | Lifecycle (Why-Win/Loss + Optimizer) |
|---|----------|-------|------------|-------------------|--------|--------|----------------------------------------|
| 1 | Heikin Ashi Trend Reversal | done | done (41 trades, PF 0.77) | done: PF 0.6799, 2232 trades, 40.14% WR, net -$4774 (batch 20260831_105336_9a6f7f) | done: byte-identical to baseline (batch 20260831_110452_538b75) | done: PF 0.6604, 2094 trades (batch 20260831_111452_0d324e) | **DONE -- verified live via get_strategy_lifecycle()** |
| 2 | Fibonacci Golden Zone Retracement | done | done (93 trades, PF 0.39) | done: PF 0.7384, 5146 trades, 30.51% WR, net -$7744 (batch 20260831_112601_3d663b) | done: PF 0.7465, 5151 trades (batch 20260831_112812_efd07f) -- best variant | done: PF 0.6124, 19523 trades (batch 20260831_112953_fb12af) | **DONE** |
| 3 | FRVP POC Reversal | done | done (156 trades, PF 0.65) | done: PF 0.9939 (near break-even!), 7921 trades, 36.45% WR, net -$282 (batch 20260831_113140_214d2d) | done: byte-identical to baseline (batch 20260831_113230_5460c2) | done: PF 0.7918, worse (batch 20260831_113248_46ecea) | **DONE** |
| 4 | FVG 50% Equilibrium Entry | done | done (465 trades, PF 0.49) | done: PF 0.6354, 27543 trades, 39.01% WR, net -$35018 (batch 20260831_113357_d48f38) | done: byte-identical to baseline (batch 20260831_113453_8ba1af) | done: PF 0.6325, worse (batch 20260831_113524_ebe965) | **DONE** |
| 5 | Donchian LWTI Volume Confluence | done | done (36 trades after LWTI recalibration fix, PF 0.73) | done: PF 0.9312, 2387 trades, 32.89% WR, net -$1000 (batch 20260831_113644_1e703e) | running | running | pending |

## Bug found + fixed during smoke testing
- Strategy 5's LWTI was originally normalized against ATR directly (clip(-1,1)*100)
  -- measured: a 25-period WMA's bar-to-bar momentum is naturally far smaller than
  raw ATR, so +/-100 was reachable only 0.03% of the time (11/40335 bars on real
  BTCUSDT 15m data) -- the +50/-50 filter was silently near-dead (2 trades on
  BTCUSDT). Fixed by normalizing against momentum's OWN rolling std dev instead
  (1 std = +/-50, 2 std caps at +/-100) -- now 15.7% of bars cross +/-50, 36 real
  trades on the same BTCUSDT smoke test. concepts.lwti() updated, all-BTCUSDT
  smoke tests re-verified after the fix.

## Strategy 1 FINAL: Losing. PF 0.6799 (baseline=Medium, best variant), Strict PF 0.6604
(worse). Best variant = Loose/Medium (tied). Verdict: Losing.

## Strategy 2 FINAL: Losing. PF 0.7384 baseline, Medium PF 0.7465 (best, real
improvement not byte-identical -- Medium's sl_distance filter genuinely discarded
a handful of very-tight-zone trades), Strict PF 0.6124 (much worse -- classic
"discard-frees-position-slot" effect, 19523 trades vs baseline's 5146). Verdict:
Losing.

## Strategy 3 FINAL: Essentially break-even (PF 0.9939, closest to profitable in this
batch). Baseline=Medium tied as best variant, Strict worse (0.7918). Verdict:
Losing (technically, PF<1.0) but by a razor-thin margin -- net -$282 on 7921 trades.

## Strategy 4 FINAL: Losing. PF 0.6354 baseline=Medium tied (best), Strict 0.6325
(worse). Verdict: Losing.

## Strategy 5 FINAL: Unprofitable but close to break-even (PF 0.9312). Baseline=Medium
tied as best, Strict worse (0.6965, genuine trade-count drop this time, not the
discard-frees-slot effect). Verdict: Losing (marginal).

## Final pytest verification
Full suite: 895 passed, 1 error ("database is locked" -- transient, isolated
tmp_path test DB, same class of I/O strain seen in New Batch 3 from this
session's heavy concurrent backtest DB writes). Re-ran the 1 failing test
alone: passed cleanly in 7.46s. Effective result: 896/896 passed, zero
regressions from any change in this batch.

## FINAL SUMMARY TABLE

| Strategy | Trades | Win Rate | PF | Verdict | Best variant |
|---|---|---|---|---|---|
| Heikin Ashi Trend Reversal | 2,232 | 40.14% | 0.6799 | Losing | Loose/Medium (tied) |
| Fibonacci Golden Zone Retracement | 5,146 | 30.51% | 0.7384 (Medium 0.7465 best) | Losing | Medium |
| FRVP POC Reversal | 7,921 | 36.45% | 0.9939 | Losing (razor-thin, essentially break-even) | Loose/Medium (tied) |
| FVG 50% Equilibrium Entry | 27,543 | 39.01% | 0.6354 | Losing | Loose/Medium (tied) |
| Donchian LWTI Volume Confluence | 2,387 | 32.89% | 0.9312 | Losing (close to break-even) | Loose/Medium (tied) |

All 5 are honest losses (or essentially break-even) -- no adjustment made to any
result. Every Strict variant underperformed baseline/Medium (same well-documented
"discard-frees-position-slot" mechanism observed in prior batches). No genuinely
critical CEO-level decision was skipped in this batch -- every ambiguity (HA flip
TF, LWTI formula, Donchian SL choice, Fibonacci short-side zone) was resolved via
a clearly-flagged own default consistent with established project convention.

## STATUS: COMPLETE. All 5 strategies built, backtested (baseline + Medium +
Strict, 50 coins each), integrated into the existing Strategy Lifecycle page
(verified live via get_strategy_lifecycle(), zero code changes needed to that
page), and reported. Scratch files cleaned up.
