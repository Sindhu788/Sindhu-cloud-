# Performance reconciliation (read-only, local DB backup, 2026-11-03)

Source: `paper_positions` closed trades in the local `sindhu.db` copy (entries 2026-08-29 .. 2026-09-11, exits to 2026-09-16), joined with `paper_strategy_groups`.

## Why -87.96 on 100 (1,132 trades, 36.1% win, PF 0.75)
| Group | Trades | Win % | Avg win | Avg loss | Expectancy/trade | PnL | PF |
|---|---|---|---|---|---|---|---|
| Losing | 822 | 36.0 | 0.373 | -0.477 | -0.171 | -140.68 | 0.44 |
| Profitable | 208 | 32.7 | 1.443 | -0.509 | +0.129 | +26.91 | 1.38 |
| Challenge | 102 | 44.1 | 1.254 | -0.537 | +0.253 | +25.81 | 1.84 |
| **Profitable + Challenge** | **310** | 36.5 | 1.368 | -0.517 | **+0.170** | **+52.72** | **1.52** |
| All | 1,132 | 36.1 | 0.648 | -0.488 | -0.078 | -87.96 | 0.75 |

* The whole-book loss is produced by the **Losing group** (72.6% of trades, PnL -140.68). Telegram only forwards Profitable + Challenge, so the signals the owner actually follows were net positive (+52.72, PF 1.52) in this sample.
* By direction: long 580 trades 31.0% win PnL -81.29 (PF 0.58); short 552 trades 41.5% win PnL -6.67 (PF 0.96). Longs lose most.
* Worst coins: POLUSDT -9.39, XRPUSDT -8.31, ASTERUSDT -7.12, FILUSDT -6.66, PEPEUSDT -6.50. Best: ENAUSDT +12.18, PUMPUSDT +8.91, ARBUSDT +7.28, AVAXUSDT +6.00.
* Daily PnL is dominated by a few bad days (2026-09-01 -25.00, 09-07 -23.47, 09-08 -44.67) against good days (09-06 +15.11, 09-09 +15.12, 09-14 +21.47).

## The "+$270.05 over 1,856 trades, 40-43% win" claim
It does **not** match this database: this DB holds 1,132 closed trades (1,197 incl. 65 open), over 2.5 weeks, and no group or combination reproduces +270.05 (best subset: Profitable+Challenge = +52.72 on 310 trades). The claim most likely comes from a different data set - the Cloud (Neon) journal, a longer period, or backtest numbers. Cloud data is **BLOCKED-USER** (needs Neon/Render access) so this cannot be confirmed here. Do not treat +270.05 as verified.

## Confidence calibration
* Pre-fix data (this DB): AUC 0.463; buckets 50-60: 40.3% (n=129), 60-70: 35.6% (539), 70-80: 37.1% (167), >80: 33.7% (291).
* **Post-17-Sep trades: none exist in this local DB** (last entry 2026-09-11), so the post-recalibration check cannot be run locally. BLOCKED-USER: needs Cloud trades after 2026-09-17.

## RECOMMENDED pauses (not applied automatically)
18 strategies with >= 20 closed trades have negative PnL and PF < 1. Worst 12 (all `[Manual Build]`):
Market Structure Shift Reversal (37 trades, PF 0.15), Fibonacci Golden Zone Retracement (27, 0.24), Liquidity Sweep + CISD Pure Swing (44, 0.47), HTF Key Level Engulfing Reversal (53, 0.68), HTF-LTF FVG/OB Confluence Entry (35, 0.24), FVG 50% Equilibrium Entry (21, 0.46), Equal Highs/Lows Reversal (28, 0.28), Order Block Trading Strict (29, 0.43), Fair Value Gap Reversal (25, 0.28), FVG Pure + Inverse FVG (33, 0.49), Candlestick Pattern Reversal (44, 0.71), Support/Resistance + Liquidity Sweep Fixed-RR (34, 0.57).
Only 4 strategies with >= 20 trades are positive: Laxman Rekha 5-EMA (+8.15, PF 1.80), Daily Liquidity Scalping (+4.73), Liquidity Sweep Multi-Confirmation (+2.43), Previous High/Low Reversal (+0.75). Ichimoku trailing-SL variants had 0% wins (n 5-8, too small to conclude).
Note: these strategies are already auto-grouped "Losing" (trade, no Telegram signal), so pausing them mainly stops paper-balance drag.
