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

---
# Step 14 - Old (pre-Codex main) vs new (recovery/clean) full-engine backtest (4 Nov 2026)

Same 10 strategies (the 10 most-traded enabled ones), same JSON definitions, same candles (binance 1m resampled by each tree: BTCUSDT, ETHUSDT, SOLUSDT, 2026-09-01 .. 2026-11-01, 60 days), same settings (balance 1000, risk 1 %, commission 0.1 %, slippage 0.05 %, position size 10 %). **No parameter was tuned.** Each tree ran on its own copy of one throwaway candle DB.

| Strategy | Old trades | Old win % | Old PF | Old net | Old max DD % | New trades | New win % | New PF | New net | New max DD % |
|---|---|---|---|---|---|---|---|---|---|---|
| Previous High/Low Reversal [Manual Build] | 130 | 36.2 | 0.55 | -312.29 | 29.99 | 183 | 44.8 | 0.68 | -280.14 | 22.47 |
| Candlestick Pattern Reversal Strategy [Manual  | 240 | 45.8 | 0.58 | -440.0 | 22.51 | 241 | 41.1 | 0.49 | -774.16 | 40.65 |
| Liquidity Sweep + CISD (Pure Swing Variant) [M | 220 | 30.0 | 0.2 | -733.68 | 33.17 | 129 | 38.8 | 0.43 | -462.35 | 23.19 |
| Liquidity Sweep Multi-Confirmation [Manual Bui | 171 | 30.4 | 0.6 | -397.62 | 22.0 | 87 | 31.0 | 0.79 | -131.43 | 19.3 |
| Daily Liquidity Scalping Strategy [Manual Buil | 161 | 51.6 | 0.92 | -63.0 | 13.5 | 161 | 51.6 | 0.92 | -63.0 | 13.5 |
| Market Structure Shift Reversal [Manual Build] | 200 | 44.5 | 0.62 | -369.01 | 20.67 | 178 | 48.9 | 0.57 | -335.27 | 15.54 |
| HTF-LTF FVG/OB Confluence Entry [Manual Build] | 294 | 40.1 | 0.43 | -624.31 | 34.91 | 248 | 37.5 | 0.45 | -576.36 | 39.49 |
| Candle Range Theory (Loose) [Manual Build] | 200 | 35.0 | 0.68 | -417.6 | 29.91 | 200 | 35.0 | 0.68 | -417.6 | 29.91 |
| Support/Resistance + Liquidity Sweep (Fixed-RR | 185 | 52.4 | 0.65 | -357.64 | 20.86 | 76 | 47.4 | 0.49 | -233.83 | 9.98 |
| FVG Pure + Inverse FVG (Structure) [Manual Bui | 183 | 36.6 | 0.45 | -502.12 | 26.06 | 183 | 36.6 | 0.45 | -502.12 | 26.06 |

**Totals:** old 1984 trades, net -4217.27; new 1686 trades, net -3776.26 (net = sum of final balance minus 1000 over 30 strategy x coin accounts).

Findings:
- Three strategies are bit-identical in both trees (Daily Liquidity Scalping, Candle Range Theory Loose, FVG Pure + Inverse FVG): they do not use the changed concepts.
- Strategies using support/resistance or break-of-structure trade fewer times in the new tree (e.g. Support/Resistance + Liquidity Sweep 185 -> 76, Liquidity Sweep Multi-Confirmation 171 -> 87, CISD 220 -> 129), consistent with the ~43 % drop in BOS events measured earlier. The old levels were the confirmation-bar high, not the pivot, so the old numbers were not measuring the written rule.
- **No regression introduced by the Codex-era changes in this sample, but also no profitable strategy: all 10 have PF < 1 in both trees** (0.2-0.92 old, 0.43-0.92 new). With these fee and slippage assumptions the strategies lose over this 60-day window. This is a backtest on 3 coins and one regime; it is NOT proof that live paper results will match.
- Hard limit of this comparison: 10 strategies, 3 coins, 60 days; costs assumed; no walk-forward (see Step 22).

---
# Step 15 - Strategy scorecard (4 Nov 2026, local DB = same 1,132 trades as Cloud)

Data window: trades closed up to 2026-09-16 (no trade has closed since; the engine was off). **"Recent trend" = the last 14 days of that data (since 2026-09-02), not the last 14 days of calendar time.** Drawdown = peak-to-trough of cumulative PnL in paper dollars. Recommendations only; nothing is paused automatically.

## By group

| Group | Trades | Win % | PF | Net | Max DD | Recent 14d net (n) |
|---|---|---|---|---|---|---|
| profitable | 208 | 32.7 | 1.38 | 26.91 | 17.98 | 31.04 (178) |
| challenge | 102 | 44.1 | 1.84 | 25.81 | 5.82 | 28.29 (81) |
| losing | 822 | 36.0 | 0.44 | -140.68 | 140.68 | -114.87 (588) |
| **all** | 1132 | 36.1 | 0.75 | -87.96 | 113.91 | -55.54 (847) |

## Strategies with at least 25 closed trades (sorted by net)

| Strategy | Group | Trades | Win % | PF | Net | Max DD | Recent 14d net | List |
|---|---|---|---|---|---|---|---|---|
| Laxman Rekha 5-EMA Trigger-Candle Strategy [Manual | challenge | 29 | 41.4 | 1.8 | 8.15 | 3.66 | 7.33 | KEEP |
| Daily Liquidity Scalping Strategy [Manual Build] | profitable | 38 | 34.2 | 1.36 | 4.73 | 3.21 | 6.64 | KEEP |
| Liquidity Sweep Multi-Confirmation [Manual Build] | profitable | 42 | 42.9 | 1.2 | 2.43 | 3.19 | 3.0 | KEEP |
| Previous High/Low Reversal [Manual Build] | profitable | 51 | 37.3 | 1.05 | 0.75 | 5.57 | 1.84 | KEEP |
| Sniper Headshot Entry [Manual Build] | challenge | 47 | 48.9 | 0.95 | -0.55 | 4.02 | 1.72 | WATCH |
| FRVP POC Reversal [Manual Build] | losing | 30 | 53.3 | 0.73 | -1.93 | 3.73 | -2.82 | WATCH |
| Candle Range Theory (Loose) [Manual Build] | losing | 34 | 32.4 | 0.8 | -2.17 | 4.81 | -2.17 | WATCH |
| Range Breakout Volume Confirmation [Manual Build] | losing | 28 | 46.4 | 0.61 | -2.51 | 3.23 | -1.26 | WATCH |
| Liquidity Sweep Reversal Strategy [Manual Build] | losing | 29 | 51.7 | 0.53 | -3.2 | 3.42 | -2.38 | WATCH |
| Support/Resistance + Liquidity Sweep (Fixed-RR) [M | losing | 34 | 47.1 | 0.57 | -3.48 | 4.7 | -3.48 | WATCH |
| Candlestick Pattern Reversal Strategy [Manual Buil | losing | 44 | 47.7 | 0.71 | -3.56 | 7.87 | -7.24 | WATCH |
| FVG Pure + Inverse FVG (Structure) [Manual Build] | losing | 33 | 48.5 | 0.49 | -3.66 | 4.8 | -3.66 | PAUSE (recommend) |
| Fair Value Gap Reversal [Manual Build] | losing | 25 | 60.0 | 0.28 | -3.82 | 3.9 | -3.74 | PAUSE (recommend) |
| Order Block Trading (Strict) [Manual Build] | losing | 29 | 41.4 | 0.43 | -4.35 | 5.07 | -4.35 | PAUSE (recommend) |
| Equal Highs/Lows Reversal [Manual Build] | losing | 28 | 46.4 | 0.28 | -4.55 | 5.23 | -2.65 | PAUSE (recommend) |
| HTF-LTF FVG/OB Confluence Entry [Manual Build] | losing | 35 | 48.6 | 0.24 | -5.41 | 5.88 | -2.07 | PAUSE (recommend) |
| HTF Key Level Engulfing Reversal [Manual Build] | losing | 53 | 30.2 | 0.68 | -5.78 | 7.34 | -1.89 | WATCH |
| Liquidity Sweep + CISD (Pure Swing Variant) [Manua | losing | 44 | 47.7 | 0.47 | -5.81 | 6.88 | -4.73 | PAUSE (recommend) |
| Fibonacci Golden Zone Retracement [Manual Build] | losing | 27 | 37.0 | 0.24 | -6.0 | 6.0 | -3.63 | PAUSE (recommend) |
| Market Structure Shift Reversal [Manual Build] | losing | 37 | 32.4 | 0.15 | -7.36 | 7.36 | -6.61 | PAUSE (recommend) |

38 further strategies have fewer than 25 closed trades: no conclusion is possible for them (Wilson 25 rule); they are neither kept nor paused here.

**Recommended pauses (Wilson-aware: n >= 25 and the 95 % upper bound of the win rate is below the break-even win rate): 8.** Watch-list (losing but not yet conclusive): 8.

## Confidence calibration

too few trades after 2026-09-17 (0 < 100) - no calibration claim. All stored closed trades are dated 2026-08-29 .. 2026-09-16, i.e. BEFORE the 17 Sep confidence recalibration; no closed trade newer than 17 Sep exists in either database (Cloud has only open positions since 3 Nov). Calibration on post-fix data is therefore NOT VERIFIED. The pre-fix numbers (AUC 0.463, win 34-40 % in every bucket) stand as documented earlier.

## The unreproducible "+$270.05 over 1,856 trades, 40-43 % win" claim

Both databases hold exactly 1,132 closed trades with net -87.96. No grouping, period or filter of these trades yields +270.05 or 1,856 trades. The figure came from a source that is not in these databases (a different dataset or a backtest). Treat it as unverified.

---
# Step 22 - Walk-forward (in-sample vs out-of-sample), 4 Nov 2026

Same 10 strategies, same 3 coins, same costs, **no re-tuning**. In-sample (IS) = 2026-09-01 .. 2026-10-01, out-of-sample (OOS) = 2026-10-01 .. 2026-11-01, current engine, backtest accounts of 1000. Report only.

| Strategy | IS trades | IS win % | IS PF | IS net | OOS trades | OOS win % | OOS PF | OOS net | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| Previous High/Low Reversal [Manual Build] | 88 | 47.7 | 0.67 | -127.3 | 105 | 42.9 | 0.64 | -184.12 | holds / improves - still PF<1 |
| Candlestick Pattern Reversal Strategy [Manua | 132 | 43.2 | 0.5 | -399.72 | 112 | 40.2 | 0.46 | -389.33 | holds / improves - still PF<1 |
| Liquidity Sweep + CISD (Pure Swing Variant)  | 57 | 33.3 | 0.4 | -239.1 | 70 | 42.9 | 0.45 | -234.29 | holds / improves - still PF<1 |
| Liquidity Sweep Multi-Confirmation [Manual B | 43 | 41.9 | 1.34 | 82.51 | 52 | 25.0 | 0.4 | -261.89 | collapse (PF fell >0.15) - still PF<1 |
| Daily Liquidity Scalping Strategy [Manual Bu | 82 | 54.9 | 1.0 | -0.98 | 82 | 47.6 | 0.72 | -129.16 | collapse (PF fell >0.15) - still PF<1 |
| Market Structure Shift Reversal [Manual Buil | 100 | 49.0 | 0.48 | -210.95 | 87 | 41.4 | 0.57 | -162.83 | holds / improves - still PF<1 |
| HTF-LTF FVG/OB Confluence Entry [Manual Buil | 182 | 37.4 | 0.35 | -492.49 | 107 | 37.4 | 0.51 | -228.81 | holds / improves - still PF<1 |
| Candle Range Theory (Loose) [Manual Build] | 102 | 25.5 | 0.42 | -470.35 | 95 | 46.3 | 1.12 | 64.24 | holds / improves |
| Support/Resistance + Liquidity Sweep (Fixed- | 33 | 51.5 | 0.71 | -49.43 | 42 | 45.2 | 0.37 | -174.2 | collapse (PF fell >0.15) - still PF<1 |
| FVG Pure + Inverse FVG (Structure) [Manual B | 112 | 28.6 | 0.24 | -472.82 | 90 | 48.9 | 1.13 | 49.42 | holds / improves |
TOTAL net IS -2380.63 OOS -1650.97 PF>=1 count IS 2 OOS 2

Reading: **no strategy is profitable in both periods.** Two had PF >= 1 in IS (Liquidity Sweep Multi-Confirmation 1.34, Daily Liquidity Scalping 1.00) and both are below 1 OOS (0.40 and 0.72: collapse, a classic overfitting sign). Two other strategies (Candle Range Theory Loose, FVG Pure + Inverse FVG) are above 1 OOS only after being very poor IS (0.42, 0.24), so neither is evidence of an edge. Total net improved (-2,381 IS vs -1,651 OOS) only because several strategies traded less. Limits: 3 coins, 30-day windows, one regime, assumed costs. Flagged for the owner: Multi-Confirmation and Daily Liquidity Scalping, which the live paper record also lists among the better four, should be watched closely rather than trusted.
