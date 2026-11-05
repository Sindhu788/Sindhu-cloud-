# Strategy forensics (Day 4, 4 Nov 2026) - ANALYSIS ONLY, nothing was changed

No strategy, parameter, group, pause or setting was touched. Sources: closed paper trades in Neon (`scripts/strategy_forensics.py`), 4-window backtests on a throwaway copy of the candle database (`scripts/robustness_check.py`, coins BTC/ETH/SOL, costs 0.1 % commission + 0.05 % slippage, balance 1000), code reading. Sample sizes are printed everywhere; "too small" means fewer than 100 trades.

## 17. Backtest realism audit: backtest engine vs paper engine
| Topic | Backtest (`backtest_engine/engine.py`) | Paper (`paper_trading/position_manager.py`, `engine.py`) | Discrepancy / risk |
|---|---|---|---|
| Stop/target test | bar HIGH/LOW, stop checked first (`_check_forced_exit`) | same rule on the latest CLOSED candle high/low (`_check_exit`), stop first | none (copied on purpose) |
| Exit fill price | at the stop/target level | at the stop/target level (`monitor_and_close`), then slippage/spread | none |
| Entry fill | signal on a closed bar; `entry_type` market / next candle open / limit / stop (default market = signal bar close) | signal on the latest closed candle, then entry at the candidate price + 0.05 % slippage | similar; both assume a fill at the signal bar close - optimistic in fast moves (medium) |
| Slippage | `slippage_pct` setting (0 unless the run sets it; the dashboard run uses 0.05 %) | hard-coded 0.05 % each side (`_apply_slippage(..., 0.0005)`) | a backtest started with engine defaults has NO slippage (high if such a number is read as real) |
| Spread | `spread_pct` setting (default 0) | `_SPREAD_PCT` constant | same issue |
| Commission | `commission_pct` (default 0 in `run_backtest`; UI passes 0.1) | `_DEFAULT_COMMISSION_PCT = 0.001` per side | consistent only if the backtest is run with 0.1 |
| Funding / borrow | none | none | spot-style model; shorts have no borrow/funding cost (medium for shorts) |
| Position sizing | risk % of the FIXED start capital | risk % of current balance per strategy book | compounding differs (documented in the engine) |
| Same-bar entry and exit | only on later bars | monitor runs before new entries in the tick | low |
| Candle data | local database 1m candles resampled (Binance) | live OKX candles; closed-only guard `market_data_guard.closed_recent_frame`, freshness window one period | different venues -> different prices and gaps (medium) |
| Look-ahead | indicators on full frames, conditions per bar on past data; swing points confirmed `lookback` bars late (`concepts.swing_points` shifts) | last candle excluded unless closed | none found in the audited functions; NOT VERIFIED for all 85 concept functions |
| Coin list | coins present in the candle database today (delisted pairs absent = survivorship) | now: top-10 liquid coins; old 29 Aug - 16 Sep trades: 50 coins by "activity" including thin tokens (DEX, JST, GRAM ...) | the old paper PF 0.75 includes illiquid coins with unrealistic fills (high) |
| Data gaps | missing bars | gap -> frame rejected as stale/empty (58 + 77 rejections in the sample) | by design |


## 18. Per-strategy forensic table (closed paper trades; PF = profit factor; R = P&L / risk amount)
Window: 29 Aug - 16 Sep 2026 (1,132 trades) plus 10 trades on 4 Nov. **There are no paper trades in October** (the engine was off), so a September-vs-October split of paper trades is not possible; the September/October question is answered by the backtest windows in section 19.

Closed trades with P&L: 1142; first 2026-08-29, last 2026-11-04
By month of entry: 2026-08: 236, 2026-09: 896, 2026-11: 10

## Overall splits (trades | win % | PF | net | avg R | max DD)
| Split | Value | n | win % | PF | net | avg R | max DD |
|---|---|---|---|---|---|---|---|
| grp | losing | 827 | 35.8 | 0.44 | -143.30 | -0.37 | 142.78 |
| grp | profitable | 213 | 31.9 | 1.31 | +23.27 | +0.22 | 11.69 |
| grp | challenge | 102 | 44.1 | 1.84 | +25.81 | +0.51 | 4.69 |
| side | long | 586 | 30.7 | 0.57 | -85.62 | -0.32 | 97.09 |
| side | short | 556 | 41.2 | 0.95 | -8.60 | -0.04 | 68.31 |
| state | trending_up | 388 | 30.7 | 0.58 | -55.13 | -0.30 | 54.76 |
| state | ranging | 374 | 43.3 | 0.77 | -24.26 | -0.13 | 30.26 |
| state | trending_down | 342 | 32.7 | 0.86 | -15.28 | -0.12 | 29.46 |
| state | volatile | 20 | 30.0 | 0.38 | -4.21 | -0.48 | 4.00 |
| state | breakout | 18 | 55.6 | 2.12 | +4.66 | +0.47 | 2.60 |
| session | ny | 557 | 33.6 | 0.71 | -53.46 | -0.21 | 61.41 |
| session | asian | 209 | 39.2 | 0.99 | -0.69 | -0.02 | 11.62 |
| session | london | 204 | 43.1 | 0.77 | -13.10 | -0.15 | 17.60 |
| session | off_hours | 172 | 30.2 | 0.54 | -26.96 | -0.33 | 29.71 |
| tf | 5m | 362 | 36.5 | 0.90 | -12.02 | -0.07 | 22.62 |
| tf | 1h | 359 | 32.0 | 0.72 | -33.67 | -0.21 | 43.23 |
| tf | 15m | 350 | 40.3 | 0.55 | -42.81 | -0.28 | 42.57 |
| tf | 1m | 38 | 34.2 | 1.36 | +4.73 | +0.30 | 3.19 |
| tf | 4h | 33 | 24.2 | 0.12 | -10.45 | -0.70 | 10.70 |
| UTC hours | 00-05 | 183 | 34.4 | 0.84 | -9.25 | -0.12 | 12.75 |
| UTC hours | 06-11 | 187 | 44.9 | 0.81 | -9.84 | -0.11 | 15.91 |
| UTC hours | 12-17 | 213 | 39.0 | 1.06 | +3.62 | +0.02 | 19.51 |
| UTC hours | 18-23 | 559 | 32.0 | 0.58 | -78.76 | -0.30 | 78.66 |

## Per strategy with at least 25 closed trades
| Strategy | Group | n | win % | PF | net | avg R | max DD | long n / net | short n / net | top coin share | worst hour block (n,net) | Trust |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Laxman Rekha 5-EMA Trigger-Candle Strategy [ | challenge | 29 | 41.4 | 1.80 | +8.15 | +0.58 | 3.16 | 23 / +6.71 | 6 / +1.44 | 10 % (POLUSDT) | 12-17 (10, +0.62) | too small for firm conclusions |
| Daily Liquidity Scalping Strategy [Manual Bu | profitable | 38 | 34.2 | 1.36 | +4.73 | +0.30 | 3.19 | 24 / -0.53 | 14 / +5.26 | 11 % (DEXEUSDT) | 12-17 (9, -2.63) | too small for firm conclusions |
| Liquidity Sweep Multi-Confirmation [Manual B | profitable | 43 | 41.9 | 1.13 | +1.63 | +0.08 | 3.41 | 19 / -3.07 | 24 / +4.70 | 9 % (NIGHTUSDT) | 18-23 (16, -0.82) | too small for firm conclusions |
| Previous High/Low Reversal [Manual Build] | profitable | 51 | 37.3 | 1.05 | +0.75 | +0.01 | 4.93 | 24 / -0.94 | 27 / +1.69 | 6 % (JSTUSDT) | 00-05 (13, -3.37) | small |
| Sniper Headshot Entry [Manual Build] | challenge | 47 | 48.9 | 0.95 | -0.55 | +0.04 | 3.47 | 25 / +3.64 | 22 / -4.20 | 11 % (FILUSDT) | 06-11 (6, -2.43) | too small for firm conclusions |
| FRVP POC Reversal [Manual Build] | losing | 30 | 53.3 | 0.73 | -1.93 | -0.12 | 3.26 | 9 / +0.24 | 21 / -2.17 | 10 % (INJUSDT) | 18-23 (11, -2.76) | too small for firm conclusions |
| Range Breakout Volume Confirmation [Manual B | losing | 28 | 46.4 | 0.61 | -2.51 | -0.17 | 2.91 | 12 / -1.81 | 16 / -0.70 | 29 % (DEXEUSDT) | 18-23 (14, -2.26) | too small for firm conclusions |
| Candle Range Theory (Loose) [Manual Build] | losing | 35 | 31.4 | 0.76 | -2.81 | -0.18 | 3.05 | 19 / -6.98 | 16 / +4.17 | 9 % (DEXEUSDT) | 18-23 (23, -2.40) | too small for firm conclusions |
| Liquidity Sweep Reversal Strategy [Manual Bu | losing | 29 | 51.7 | 0.53 | -3.20 | -0.23 | 3.21 | 19 / -2.47 | 10 / -0.74 | 10 % (POLUSDT) | 18-23 (7, -1.08) | too small for firm conclusions |
| Support/Resistance + Liquidity Sweep (Fixed- | losing | 34 | 47.1 | 0.57 | -3.48 | -0.24 | 3.86 | 25 / -4.64 | 9 / +1.15 | 9 % (ARBUSDT) | 12-17 (6, -1.84) | too small for firm conclusions |
| Candlestick Pattern Reversal Strategy [Manua | losing | 44 | 47.7 | 0.71 | -3.56 | -0.16 | 6.25 | 15 / -3.40 | 29 / -0.16 | 14 % (JSTUSDT) | 18-23 (19, -5.52) | too small for firm conclusions |
| FVG Pure + Inverse FVG (Structure) [Manual B | losing | 33 | 48.5 | 0.49 | -3.66 | -0.25 | 3.96 | 16 / -4.95 | 17 / +1.30 | 12 % (CAKEUSDT) | 18-23 (19, -3.55) | too small for firm conclusions |
| Fair Value Gap Reversal [Manual Build] | losing | 25 | 60.0 | 0.28 | -3.82 | -0.31 | 3.90 | 13 / -2.66 | 12 / -1.16 | 12 % (DEXEUSDT) | 18-23 (11, -2.41) | too small for firm conclusions |
| Order Block Trading (Strict) [Manual Build] | losing | 29 | 41.4 | 0.43 | -4.35 | -0.33 | 5.10 | 13 / -3.50 | 16 / -0.85 | 10 % (JSTUSDT) | 18-23 (22, -2.52) | too small for firm conclusions |
| Equal Highs/Lows Reversal [Manual Build] | losing | 28 | 46.4 | 0.28 | -4.55 | -0.34 | 5.61 | 14 / -2.88 | 14 / -1.67 | 11 % (XRPUSDT) | 18-23 (16, -2.69) | too small for firm conclusions |
| HTF Key Level Engulfing Reversal [Manual Bui | losing | 53 | 30.2 | 0.68 | -5.78 | -0.22 | 6.00 | 24 / -1.81 | 29 / -3.97 | 6 % (WLDUSDT) | 06-11 (25, -3.11) | small |
| Liquidity Sweep + CISD (Pure Swing Variant)  | losing | 44 | 47.7 | 0.47 | -5.81 | -0.30 | 7.29 | 20 / -3.34 | 24 / -2.47 | 14 % (UNIUSDT) | 00-05 (6, -2.29) | too small for firm conclusions |
| HTF-LTF FVG/OB Confluence Entry [Manual Buil | losing | 36 | 47.2 | 0.22 | -5.84 | -0.40 | 6.31 | 20 / -3.39 | 16 / -2.45 | 11 % (POLUSDT) | 18-23 (22, -3.91) | too small for firm conclusions |
| Fibonacci Golden Zone Retracement [Manual Bu | losing | 27 | 37.0 | 0.24 | -6.00 | -0.54 | 5.62 | 14 / -2.93 | 13 / -3.07 | 11 % (GRAMUSDT) | 18-23 (7, -2.18) | too small for firm conclusions |
| Market Structure Shift Reversal [Manual Buil | losing | 37 | 32.4 | 0.15 | -7.36 | -0.52 | 7.48 | 19 / -4.01 | 18 / -3.34 | 8 % (ICPUSDT) | 18-23 (20, -3.88) | too small for firm conclusions |

20 strategies have >= 25 trades; 38 have fewer (no conclusion possible).

## Regime (market_state at entry) per strategy, strategies with >= 50 trades: net P&L in each state (n)
| Strategy | breakout | ranging | trending_down | trending_up | volatile |
|---|---|---|---|---|---|
| HTF Key Level Engulfing Reversal [Manual | - | -5.4 (21) | -1.1 (8) | +1.3 (23) | -0.5 (1) |
| Previous High/Low Reversal [Manual Build | - | -0.1 (16) | +4.0 (16) | -2.0 (17) | -1.1 (2) |

## Redundancy: do strategies fire on the same coin, side and 15-minute slot?
Distinct (coin, side, 15-min slot) events: 915 from 1142 trades -> 1.25 trades per independent event; events where >= 2 strategies fired together: 161 (17.6 %).
| Overlap (Jaccard of events) | shared events | Strategy A | Strategy B |
|---|---|---|---|

Strategies with >= 25 trades: 20; clusters when overlap >= 0.30: 20 (largest cluster 1).


## 19. Overfitting tests (read-only): four rolling windows and parameter sensitivity
Windows (17 days each, 3 coins): 24 Aug-11 Sep, 11-28 Sep, 28 Sep-15 Oct, 15 Oct-1 Nov. Sensitivity = one parameter moved to the nearest grid value around +-10 % / +-20 % (`optimizer.tunable_dimensions`) on BTC over the whole 69 days; only strategies with numeric parameters on the grid produced variants (0-6 each), so the sensitivity part is thin - a stated limit.

| Strategy | trades (4 windows x 3 coins) | PF per window (pooled mean of 3 coins) | cells PF>1 (of 12) | BTC 69d PF | variants run | variants PF>1 | variant PF range | Verdict |
|---|---|---|---|---|---|---|---|---|
| HTF Key Level Engulfing Reversal [Ma | 615 | 0.28 / 0.63 / 0.69 / 0.45 | 0/12 | 0.43 | 0 | 0 | - | loses almost everywhere |
| Previous High/Low Reversal [Manual B | 214 | 1.74 / 0.51 / 0.52 / 0.77 | 2/12 | 1.20 | 2 | 2 | 1.20-1.28 | loses almost everywhere |
| Sniper Headshot Entry [Manual Build] | 156 | 0.13 / 1.04 / 0.76 / 0.72 | 4/12 | 0.37 | 2 | 0 | 0.36-0.37 | inconsistent / fragile |
| Candlestick Pattern Reversal Strateg | 268 | 0.71 / 0.31 / 0.71 / 0.42 | 2/12 | 0.65 | 2 | 0 | 0.64-0.65 | loses almost everywhere |
| Liquidity Sweep + CISD (Pure Swing V | 138 | 0.57 / 0.15 / 0.48 / 0.56 | 0/12 | 0.30 | 2 | 0 | 0.27-0.30 | loses almost everywhere |
| Liquidity Sweep Multi-Confirmation [ | 104 | 1.02 / 0.62 / 0.42 / 0.34 | 1/12 | 1.24 | 2 | 2 | 1.23-1.29 | loses almost everywhere |
| Daily Liquidity Scalping Strategy [M | 180 | 2.86 / 0.90 / 0.76 / 1.23 | 6/12 | 1.39 | 6 | 6 | 1.16-1.64 | inconsistent / fragile |
| Market Structure Shift Reversal [Man | 216 | 0.54 / 0.51 / 0.50 / 0.53 | 0/12 | 0.48 | 2 | 0 | 0.47-0.50 | loses almost everywhere |
| HTF-LTF FVG/OB Confluence Entry [Man | 323 | 0.24 / 1.05 / 0.75 / 0.27 | 2/12 | 0.19 | 2 | 0 | 0.17-0.20 | loses almost everywhere |
| Candle Range Theory (Loose) [Manual  | 226 | 0.50 / 0.40 / 0.78 / 1.36 | 4/12 | 0.76 | 6 | 0 | 0.75-0.79 | inconsistent / fragile |
windows: 24 Aug-11 Sep, 11-28 Sep, 28 Sep-15 Oct, 15 Oct-1 Nov


Reading: **no strategy is profitable in most windows and coins.** The closest are Daily Liquidity Scalping (6 of 12 cells above PF 1, all 6 variants above PF 1, but window PFs 2.86 / 0.90 / 0.76 / 1.23 - the first window dominates) and Previous High/Low Reversal (BTC 69-day PF 1.20 but only 2 of 12 cells). Liquidity Sweep Multi-Confirmation falls window by window (1.02, 0.62, 0.42, 0.34): the walk-forward collapse seen on Day 2 repeats. Seven of ten strategies lose in nearly every window (HTF Key Level Engulfing 0/12, Liquidity Sweep + CISD 0/12, Market Structure Shift 0/12). The BTC-only 69-day PF of a few strategies is above 1 while their 3-coin windows are below 1, so BTC alone flatters them.

## 20-21. Redundancy, correlation and regimes (the redundancy and regime tables are in section 18's output above)
Redundancy: 1,142 trades are 915 independent (coin, side, 15-minute) events, i.e. 1.25 trades per event; only 17.6 % of events had two or more strategies firing together; no pair among the 20 strategies with at least 25 trades shares 5 or more events. So the strategies are **not** near-duplicates of each other and the effective number of independent bets is close to the number of strategies - the problem is that each bet loses, not that they repeat. Pruning near-duplicates is NOT recommended on this evidence (only the 20 strategies with enough trades could be checked; the other 38 are unknown).
Regimes: by market state at entry, trending-up trades lose most (388 trades, PF 0.58, net -55) and **long trades lose far more than short** (586 long PF 0.57, net -85.6; 556 short PF 0.95, net -8.6). The UTC 18-23 block holds 559 of 1,142 trades (49 %) with PF 0.58 and net -78.8, while 12-17 UTC is the only block above 1 (PF 1.06, 213 trades). Timeframe 4h has PF 0.12 (33 trades), 1m PF 1.36 (38 trades, one strategy). Breakouts (18 trades, PF 2.1) are too few. Only two strategies have 50 or more trades, so a per-strategy regime filter cannot be justified; at portfolio level the evening-hours and long-side weakness is the one pattern backed by hundreds of trades.

## 22. Shortlist and experiment plan (recommendations only)
**Keep (paper only, unproven):** Daily Liquidity Scalping, Previous High/Low Reversal, Laxman Rekha 5-EMA (PF 1.80 on 29 trades, not in the backtest set). "Keep" means keep collecting trades, not "trust".
**Watch (do not pause yet):** Sniper Headshot Entry, Candle Range Theory (Loose), Liquidity Sweep Multi-Confirmation (falling PF), FRVP POC Reversal, Range Breakout Volume Confirmation, Liquidity Sweep Reversal, Support/Resistance + Liquidity Sweep, Candlestick Pattern Reversal, HTF Key Level Engulfing Reversal (0/12 cells: move to Pause if its next 25 trades lose).
**Pause (agrees with the scorecard and the backtest windows):** FVG Pure + Inverse FVG, Fair Value Gap Reversal, Order Block Trading (Strict), Equal Highs/Lows Reversal, HTF-LTF FVG/OB Confluence Entry, Liquidity Sweep + CISD, Fibonacci Golden Zone, Market Structure Shift Reversal. All 8 are already in the Losing group: pausing them changes **no public signal**; it only stops their paper losses and saves CPU and data.
Expected effect on signals: none from pausing; signals come from the 5 profitable + 4 challenge strategies.
**Paper A/B experiment design (proposal, not started):** Question: does skipping new LONG entries between 18:00 and 23:59 UTC improve results? Change: a shadow rule that only LABELS trades "would have been skipped" for 4 weeks (no behaviour change). Metric: net P&L, PF and win rate of labelled vs unlabelled trades of the same strategies, with at least 100 labelled trades. Stop rule: stop early if the labelled group's PF is above 1.0 after 100 trades (rule useless); if it is below 0.6 after 100 trades and the win-rate upper bound is under break-even, propose a real filter to the owner. Second experiment: compare Cloud trades on the 10 liquid coins (since 3 Nov) with the old 50-coin sample after 25 or more closed trades per group.

## Limits
Paper P&L is the old 29 Aug - 16 Sep sample on 50 mostly thin coins; backtests use three major coins on Binance candles with assumed costs; none of this predicts live results. No strategy parameter was changed.


## Day 6: corrected validation of the 42 enabled strategies (Step 8)

Unit = position, corrected metrics (docs/BACKTEST_PROTOCOL.md section 10). Coins: up to 50 (coins with no data in the window are skipped, see the coin column). Development window 1 Nov 2025 - 31 Aug 2026, 8 walk-forward windows scored by entry time, costs x1 with exact x1.5 / x2 re-pricing. No parameter changed; the holdout and the forward window were not read.

| Label | Strategy | TF | Coins | Positions | Win % | PF x1 [95 % CI] | PF x1.5 | PF x2 | Expectancy ($) | Avg R | Max DD ($) | Windows ok | Coins ok | Long n / PF | Short n / PF |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| FRAGILE | Ichimoku 1d Indicator-Exit [Manual Build] | 1d | 47 | 576 | 30.4 | 1.09 [0.71-1.61] | 0.98 | 0.89 | 0.569 | 0.055 | 1171 | 2/6 | 0/0 | 85 / 0.83 | 491 / 1.14 |
| FAILED | Supply/Demand Zone Strategy [Manual Build] | 1h | 47 | 494 | 25.3 | 0.78 [0.61-0.96] | 0.67 | 0.58 | -1.962 | -0.196 | 1212 | 1/8 | 0/0 | 275 / 0.69 | 219 / 0.91 |
| FAILED | Laxman Rekha 5-EMA Trigger-Candle Strategy [Manual Build] | 5m | 47 | 13165 | 25.0 | 0.76 [0.71-0.82] | 0.67 | 0.59 | -1.854 | -0.219 | 24836 | 0/8 | 1/47 | 9108 / 0.69 | 4057 / 0.91 |
| FAILED | Dumb Money Concepts -- Confirmation Entry [Manual Build] | 4h | 47 | 1605 | 17.4 | 0.75 [0.56-0.96] | 0.67 | 0.59 | -2.348 | -0.235 | 4451 | 1/8 | 7/28 | 957 / 0.68 | 648 / 0.87 |
| FAILED | Heikin Ashi Trend Reversal [Manual Build] | 15m | 47 | 1313 | 28.9 | 0.75 [0.63-0.89] | 0.61 | 0.50 | -2.157 | -0.229 | 2944 | 0/8 | 1/19 | 706 / 0.76 | 607 / 0.74 |
| FAILED | Kotegawa Bear Market Reversal Strategy [Manual Build] | 15m | 47 | 4288 | 22.1 | 0.73 [0.57-0.95] | 0.68 | 0.63 | -2.304 | -0.230 | 11126 | 3/8 | 1/45 | 4288 / 0.73 | 0 / - |
| FAILED | 4-Hour Range Breakout-Retest [Manual Build] | 5m | 47 | 11813 | 32.4 | 0.73 [0.67-0.79] | 0.64 | 0.56 | -2.016 | -0.214 | 23806 | 0/8 | 1/46 | 6170 / 0.64 | 5643 / 0.83 |
| FAILED | Asian Range London Sweep [Manual Build] | 5m | 47 | 2715 | 32.5 | 0.71 [0.62-0.81] | 0.62 | 0.54 | -2.246 | -0.225 | 6091 | 0/8 | 2/46 | 1381 / 0.60 | 1334 / 0.84 |
| FAILED | Daily Liquidity Scalping Strategy [Manual Build] | 1m | 47 | 28287 | 37.0 | 0.69 [0.63-0.76] | 0.59 | 0.50 | -1.334 | -0.231 | 37917 | 0/8 | 0/47 | 14407 / 0.68 | 13880 / 0.71 |
| FAILED | Liquidity Sweep Reversal Strategy [Manual Build] | 15m | 47 | 23212 | 46.4 | 0.69 [0.63-0.76] | 0.58 | 0.48 | -1.433 | -0.186 | 34454 | 0/8 | 0/46 | 10882 / 0.63 | 12330 / 0.75 |
| FAILED | 9-20 EMA SMC Hybrid [Manual Build] | 15m | 47 | 1766 | 34.6 | 0.67 [0.57-0.77] | 0.54 | 0.44 | -2.713 | -0.271 | 4881 | 0/8 | 0/29 | 1023 / 0.63 | 743 / 0.72 |
| FAILED | Liquidity Sweep Multi-Confirmation [Manual Build] | 5m | 47 | 7424 | 20.9 | 0.67 [0.56-0.79] | 0.57 | 0.50 | -2.548 | -0.341 | 21213 | 0/8 | 2/41 | 4154 / 0.60 | 3270 / 0.76 |
| FAILED | Order Block Trading (Strict) [Manual Build] | 1h | 47 | 4002 | 41.2 | 0.66 [0.51-0.86] | 0.55 | 0.47 | -1.936 | -0.195 | 9584 | 1/8 | 4/43 | 1656 / 0.60 | 2346 / 0.70 |
| FAILED | Dumb Money Concepts -- Combined Confirmation [Manual Build] | 4h | 47 | 1356 | 15.8 | 0.66 [0.46-0.88] | 0.58 | 0.52 | -3.316 | -0.343 | 4948 | 1/8 | 3/25 | 810 / 0.62 | 546 / 0.71 |
| FAILED | Fibonacci Golden Zone Retracement [Manual Build] | 1h | 47 | 17377 | 36.1 | 0.66 [0.61-0.70] | 0.53 | 0.44 | -1.710 | -0.285 | 30842 | 0/8 | 1/47 | 9286 / 0.57 | 8091 / 0.77 |
| FAILED | PDH/PDL Multi-Timeframe Reversal [Manual Build] | 5m | 47 | 8495 | 25.2 | 0.65 [0.58-0.73] | 0.54 | 0.45 | -2.644 | -0.345 | 22943 | 0/8 | 1/47 | 3901 / 0.62 | 4594 / 0.68 |
| FAILED | Market Structure Shift Reversal [Manual Build] | 15m | 47 | 9570 | 48.0 | 0.65 [0.57-0.76] | 0.54 | 0.46 | -1.636 | -0.179 | 17940 | 0/8 | 1/36 | 4669 / 0.54 | 4901 / 0.76 |
| FAILED | Liquidity Sweep + Engulfing Candle (Loose) [Manual Build] | 5m | 47 | 26935 | 32.3 | 0.64 [0.59-0.70] | 0.53 | 0.45 | -1.508 | -0.319 | 40800 | 0/8 | 0/47 | 14741 / 0.60 | 12194 / 0.70 |
| FAILED | OTE Liquidity Sweep Reversal [Manual Build] | 15m | 47 | 13685 | 23.8 | 0.64 [0.58-0.70] | 0.52 | 0.43 | -2.240 | -0.379 | 30829 | 0/8 | 0/47 | 7084 / 0.56 | 6601 / 0.73 |
| FAILED | Candle Range Theory (Loose) [Manual Build] | 1h | 47 | 17679 | 33.9 | 0.63 [0.60-0.67] | 0.51 | 0.41 | -1.936 | -0.329 | 34261 | 0/8 | 0/47 | 9139 / 0.58 | 8540 / 0.70 |
| FAILED | Liquidity Sweep + Engulfing Candle (Strict) [Manual Build] | 5m | 47 | 17647 | 31.5 | 0.63 [0.59-0.67] | 0.52 | 0.43 | -1.954 | -0.331 | 34585 | 0/8 | 0/47 | 9775 / 0.57 | 7872 / 0.72 |
| FAILED | Previous High/Low Reversal [Manual Build] | 15m | 47 | 15035 | 41.3 | 0.61 [0.55-0.69] | 0.50 | 0.42 | -1.822 | -0.242 | 29164 | 0/8 | 1/43 | 8310 / 0.56 | 6725 / 0.68 |
| FAILED | Support/Resistance + Liquidity Sweep (Fixed-RR) [Manual Build] | 1h | 47 | 6983 | 43.3 | 0.61 [0.54-0.70] | 0.49 | 0.39 | -2.468 | -0.265 | 17559 | 0/8 | 0/47 | 5633 / 0.59 | 1350 / 0.73 |
| FAILED | Candle Range Theory (Strict) [Manual Build] | 1h | 47 | 2953 | 33.3 | 0.60 [0.53-0.69] | 0.48 | 0.38 | -3.072 | -0.346 | 9303 | 0/8 | 0/46 | 1112 / 0.55 | 1841 / 0.63 |
| FAILED | Equal Highs/Lows Reversal [Manual Build] | 15m | 47 | 16803 | 44.4 | 0.60 [0.50-0.77] | 0.48 | 0.38 | -1.339 | -0.239 | 26840 | 0/8 | 1/40 | 8637 / 0.48 | 8166 / 0.75 |
| FAILED | Ichimoku 1h Indicator-Exit [Manual Build] | 1h | 47 | 13466 | 25.2 | 0.60 [0.51-0.71] | 0.48 | 0.40 | -1.905 | -0.245 | 26562 | 0/8 | 1/47 | 4833 / 0.70 | 8633 / 0.53 |
| FAILED | Candlestick Pattern Reversal Strategy [Manual Build] | 15m | 47 | 17792 | 41.2 | 0.60 [0.56-0.64] | 0.49 | 0.40 | -1.954 | -0.264 | 35082 | 0/8 | 0/47 | 9439 / 0.53 | 8353 / 0.69 |
| FAILED | Liquidity Sweep + CISD (Pure Swing Variant) [Manual Build] | 5m | 47 | 8967 | 38.9 | 0.60 [0.55-0.64] | 0.47 | 0.37 | -2.414 | -0.306 | 21924 | 0/8 | 0/46 | 4638 / 0.52 | 4329 / 0.69 |
| FAILED | FVG Pure + Inverse FVG (Fixed 1:2) [Manual Build] | 1h | 47 | 18695 | 32.1 | 0.59 [0.56-0.63] | 0.47 | 0.37 | -1.874 | -0.371 | 35034 | 0/8 | 0/47 | 9552 / 0.53 | 9143 / 0.67 |
| FAILED | HTF-LTF FVG/OB Confluence Entry [Manual Build] | 15m | 47 | 12360 | 48.2 | 0.59 [0.43-0.86] | 0.46 | 0.36 | -1.350 | -0.193 | 21609 | 0/8 | 8/42 | 4651 / 0.47 | 7709 / 0.67 |
| FAILED | Fixed Range Volume Profile -- Market Shape [Manual Build] | 1h | 47 | 19966 | 38.1 | 0.58 [0.55-0.62] | 0.46 | 0.37 | -1.744 | -0.337 | 35836 | 0/8 | 2/47 | 10087 / 0.49 | 9879 / 0.69 |
| FAILED | FVG Momentum Pullback (Structure) [Manual Build] | 1h | 47 | 8706 | 31.6 | 0.58 [0.50-0.67] | 0.45 | 0.36 | -2.476 | -0.363 | 23412 | 0/8 | 3/46 | 5162 / 0.51 | 3544 / 0.69 |
| FAILED | Range Breakout Volume Confirmation [Manual Build] | 15m | 47 | 3278 | 42.0 | 0.56 [0.40-0.86] | 0.45 | 0.37 | -2.267 | -0.266 | 9625 | 0/8 | 1/30 | 1473 / 0.35 | 1805 / 0.79 |
| FAILED | FVG Pure + Inverse FVG (Structure) [Manual Build] | 1h | 47 | 17026 | 35.0 | 0.55 [0.47-0.66] | 0.41 | 0.31 | -1.754 | -0.353 | 33234 | 0/8 | 1/45 | 8717 / 0.49 | 8309 / 0.61 |
| FAILED | Donchian LWTI Volume Confluence [Manual Build] | 15m | 47 | 5740 | 53.6 | 0.53 [0.38-0.76] | 0.40 | 0.31 | -1.596 | -0.166 | 11231 | 0/8 | 3/40 | 2505 / 0.43 | 3235 / 0.61 |
| FAILED | Ichimoku 15m Indicator-Exit [Manual Build] | 15m | 47 | 48161 | 20.6 | 0.51 [0.43-0.59] | 0.38 | 0.29 | -0.944 | -0.294 | 45481 | 0/8 | 0/47 | 19155 / 0.56 | 29006 / 0.47 |
| FAILED | Ichimoku 5m Indicator-Exit [Manual Build] | 5m | 47 | 134525 | 15.7 | 0.36 [0.31-0.41] | 0.25 | 0.18 | -0.349 | -0.373 | 46948 | 0/8 | 0/47 | 56063 / 0.35 | 78462 / 0.37 |
| INSUFFICIENT_DATA | Ichimoku 1d Trailing-SL [Manual Build] | 1d | 47 | 121 | 27.3 | 1.79 [0.00-5.80] | 1.67 | 1.56 | 6.176 | 0.616 | 922 | 1/1 | 0/0 | 28 / 0.27 | 93 / 2.30 |
| INSUFFICIENT_DATA | Ichimoku 15m Trailing-SL [Manual Build] | 15m | 47 | 509 | 9.2 | 1.44 [0.00-5.08] | 1.31 | 1.21 | 4.519 | 0.474 | 5157 | 1/4 | 0/3 | 239 / 0.05 | 270 / 2.87 |
| INSUFFICIENT_DATA | Ichimoku 1h Trailing-SL [Manual Build] | 1h | 47 | 299 | 14.0 | 1.28 [0.00-4.12] | 1.19 | 1.11 | 2.578 | 0.257 | 2758 | 1/2 | 0/2 | 115 / 0.11 | 184 / 2.15 |
| INSUFFICIENT_DATA | SMA-Alignment Strategy (Approximate - ZIP Indicator Excluded) [Manual Build] | 1h | 47 | 1696 | 34.9 | 0.74 [0.55-0.98] | 0.64 | 0.57 | -1.675 | -0.168 | 3249 | 0/3 | 3/37 | 405 / 0.75 | 1291 / 0.73 |
| INSUFFICIENT_DATA | SAR + SMC (CISD Entry) [Manual Build] | 5m | 47 | 254 | 39.0 | 0.36 [0.23-0.54] | 0.22 | 0.15 | -3.548 | -0.360 | 908 | 0/4 | 0/0 | 124 / 0.30 | 130 / 0.44 |

**Hour-of-day split (UTC, 6-hour blocks; positions, PF) for the strategies with >= 300 positions:**

| Strategy | 00-05 | 06-11 | 12-17 | 18-23 |
|---|---|---|---|---|
| Ichimoku 5m Indicator-Exit [Manual Build] | 33950 / 0.30 | 33089 / 0.32 | 34650 / 0.54 | 32836 / 0.27 |
| Ichimoku 15m Indicator-Exit [Manual Build] | 11934 / 0.47 | 12192 / 0.58 | 12936 / 0.56 | 11099 / 0.42 |
| Daily Liquidity Scalping Strategy [Manual Build] | 7155 / 0.66 | 5486 / 0.66 | 9129 / 0.62 | 6517 / 0.89 |
| Liquidity Sweep + Engulfing Candle (Loose) [Manual Build] | 6253 / 0.71 | 5809 / 0.64 | 8185 / 0.57 | 6688 / 0.66 |
| Liquidity Sweep Reversal Strategy [Manual Build] | 5662 / 0.68 | 5195 / 0.75 | 6217 / 0.64 | 6138 / 0.70 |
| Fixed Range Volume Profile -- Market Shape [Manual Build] | 4822 / 0.62 | 4716 / 0.56 | 5580 / 0.54 | 4848 / 0.61 |
| FVG Pure + Inverse FVG (Fixed 1:2) [Manual Build] | 4708 / 0.58 | 4400 / 0.63 | 5238 / 0.57 | 4349 / 0.61 |
| Candlestick Pattern Reversal Strategy [Manual Build] | 4348 / 0.59 | 4562 / 0.59 | 3975 / 0.55 | 4907 / 0.65 |
| Candle Range Theory (Loose) [Manual Build] | 4471 / 0.66 | 4249 / 0.63 | 4551 / 0.61 | 4408 / 0.64 |
| Liquidity Sweep + Engulfing Candle (Strict) [Manual Build] | 3893 / 0.69 | 3573 / 0.62 | 5648 / 0.58 | 4533 / 0.65 |
| Fibonacci Golden Zone Retracement [Manual Build] | 4216 / 0.68 | 4007 / 0.62 | 4911 / 0.65 | 4243 / 0.67 |
| FVG Pure + Inverse FVG (Structure) [Manual Build] | 4227 / 0.42 | 4073 / 0.75 | 4816 / 0.48 | 3910 / 0.56 |
| Equal Highs/Lows Reversal [Manual Build] | 4104 / 0.61 | 3647 / 0.53 | 5139 / 0.62 | 3913 / 0.63 |
| Previous High/Low Reversal [Manual Build] | 6625 / 0.65 | 2141 / 0.61 | 3720 / 0.57 | 2549 / 0.61 |
| OTE Liquidity Sweep Reversal [Manual Build] | 3508 / 0.61 | 2931 / 0.68 | 4173 / 0.57 | 3073 / 0.75 |
| Ichimoku 1h Indicator-Exit [Manual Build] | 3240 / 0.57 | 2950 / 0.61 | 3816 / 0.68 | 3460 / 0.55 |
| Laxman Rekha 5-EMA Trigger-Candle Strategy [Manual Build] | 2966 / 0.76 | 2619 / 0.75 | 4288 / 0.70 | 3292 / 0.85 |
| HTF-LTF FVG/OB Confluence Entry [Manual Build] | 2962 / 0.59 | 2469 / 0.55 | 3875 / 0.62 | 3054 / 0.59 |
| 4-Hour Range Breakout-Retest [Manual Build] | 1071 / 0.65 | 4860 / 0.76 | 4405 / 0.74 | 1477 / 0.64 |
| Market Structure Shift Reversal [Manual Build] | 2302 / 0.67 | 1891 / 0.63 | 3222 / 0.67 | 2155 / 0.61 |
| Liquidity Sweep + CISD (Pure Swing Variant) [Manual Build] | 2084 / 0.57 | 1936 / 0.61 | 3117 / 0.63 | 1830 / 0.56 |
| FVG Momentum Pullback (Structure) [Manual Build] | 2292 / 0.53 | 2184 / 0.73 | 2127 / 0.55 | 2103 / 0.52 |
| PDH/PDL Multi-Timeframe Reversal [Manual Build] | 1594 / 0.72 | 1964 / 0.65 | 2856 / 0.66 | 2081 / 0.59 |
| Liquidity Sweep Multi-Confirmation [Manual Build] | 2766 / 0.70 | 1302 / 0.74 | 2143 / 0.57 | 1213 / 0.70 |
| Support/Resistance + Liquidity Sweep (Fixed-RR) [Manual Build] | 1783 / 0.54 | 1627 / 0.54 | 2036 / 0.57 | 1537 / 0.85 |
| Donchian LWTI Volume Confluence [Manual Build] | 1109 / 0.45 | 1159 / 0.77 | 1848 / 0.52 | 1624 / 0.42 |
| Kotegawa Bear Market Reversal Strategy [Manual Build] | 1063 / 0.73 | 1072 / 0.75 | 987 / 0.69 | 1166 / 0.74 |
| Order Block Trading (Strict) [Manual Build] | 955 / 0.72 | 893 / 0.63 | 1195 / 0.70 | 959 / 0.58 |
| Range Breakout Volume Confirmation [Manual Build] | 813 / 0.45 | 694 / 0.63 | 1121 / 0.63 | 650 / 0.55 |
| Candle Range Theory (Strict) [Manual Build] | 775 / 0.65 | 721 / 0.64 | 800 / 0.65 | 657 / 0.47 |
| Asian Range London Sweep [Manual Build] | 0 / - | 2286 / 0.75 | 429 / 0.54 | 0 / - |
| 9-20 EMA SMC Hybrid [Manual Build] | 424 / 0.77 | 332 / 0.74 | 560 / 0.63 | 450 / 0.56 |
| SMA-Alignment Strategy (Approximate - ZIP Indicator Excluded) [Manual Build] | 0 / - | 0 / - | 1446 / 0.75 | 250 / 0.64 |
| Dumb Money Concepts -- Confirmation Entry [Manual Build] | 513 / 0.80 | 193 / 0.56 | 613 / 0.64 | 286 / 1.03 |
| Dumb Money Concepts -- Combined Confirmation [Manual Build] | 431 / 0.82 | 189 / 0.40 | 493 / 0.53 | 243 / 0.84 |
| Heikin Ashi Trend Reversal [Manual Build] | 370 / 0.66 | 280 / 0.54 | 398 / 0.97 | 265 / 0.82 |
| Ichimoku 1d Indicator-Exit [Manual Build] | 576 / 1.09 | 0 / - | 0 / - | 0 / - |
| Ichimoku 15m Trailing-SL [Manual Build] | 134 / 1.38 | 95 / 2.63 | 117 / 0.69 | 163 / 1.36 |
| Supply/Demand Zone Strategy [Manual Build] | 122 / 0.92 | 103 / 0.80 | 137 / 0.71 | 132 / 0.72 |

**Why 5 strategies are INSUFFICIENT_DATA:**

| Strategy | TF | Positions | Reason |
|---|---|---|---|
| Ichimoku 1d Trailing-SL [Manual Build] | 1d | 121 | timeframe problem: slow timeframe, few signals in 10 months |
| SAR + SMC (CISD Entry) [Manual Build] | 5m | 254 | too few trades (254 < 300) |
| Ichimoku 1h Trailing-SL [Manual Build] | 1h | 299 | too few trades (299 < 300) |
| Ichimoku 15m Trailing-SL [Manual Build] | 15m | 509 | trades bunched in too few windows (4 of 8 with >= 30) |
| SMA-Alignment Strategy (Approximate - ZIP Indicator Excluded) [Manual Build] | 1h | 1696 | trades bunched in too few windows (3 of 8 with >= 30) |

## Day 6: comparison with luck and with simple baselines (Step 9)

Net return per position as % of notional, same costs. Null = random entries with the same side mix, holding times and costs (500 simulated books). p = share of simulated books at least as good (smaller = stronger evidence). FDR = survives Benjamini-Hochberg at 5 % across all strategies.

| Strategy | TF | Positions | Strategy % | Random-entry % (95th pct) | p | FDR | SMA-4h % | RSI-1h % | Beats luck | Beats both baselines |
|---|---|---|---|---|---|---|---|---|---|---|
| Ichimoku 1d Trailing-SL [Manual Build] | 1d | 121 | +1.396 | +12.543 (+15.291) | 1.000 | no | -1.441 | -0.360 | no | yes |
| Ichimoku 1d Indicator-Exit [Manual Build] | 1d | 576 | +0.185 | +1.060 (+1.856) | 0.964 | no | -1.441 | -0.360 | no | yes |
| Heikin Ashi Trend Reversal [Manual Build] | 15m | 1313 | -0.261 | -0.439 (-0.307) | 0.016 | no | -1.441 | -0.360 | no | yes |
| Ichimoku 15m Trailing-SL [Manual Build] | 15m | 509 | -0.304 | +3.255 (+3.990) | 1.000 | no | -1.441 | -0.360 | no | yes |
| Laxman Rekha 5-EMA Trigger-Candle Strategy [Manual Build] | 5m | 13165 | -0.327 | -0.403 (-0.337) | 0.038 | no | -1.441 | -0.360 | no | yes |
| Supply/Demand Zone Strategy [Manual Build] | 1h | 494 | -0.340 | -0.444 (-0.190) | 0.291 | no | -1.441 | -0.360 | no | yes |
| HTF-LTF FVG/OB Confluence Entry [Manual Build] | 15m | 12360 | -0.346 | -0.292 (-0.248) | 0.968 | no | -1.441 | -0.360 | no | yes |
| Fibonacci Golden Zone Retracement [Manual Build] | 1h | 17377 | -0.360 | -0.399 (-0.357) | 0.070 | no | -1.441 | -0.360 | no | yes |
| FVG Pure + Inverse FVG (Structure) [Manual Build] | 1h | 17026 | -0.360 | -0.406 (-0.377) | 0.014 | no | -1.441 | -0.360 | no | no |
| 9-20 EMA SMC Hybrid [Manual Build] | 15m | 1766 | -0.364 | -0.443 (-0.357) | 0.074 | no | -1.441 | -0.360 | no | no |
| FVG Momentum Pullback (Structure) [Manual Build] | 1h | 8706 | -0.372 | -0.407 (-0.361) | 0.114 | no | -1.441 | -0.360 | no | no |
| Candle Range Theory (Loose) [Manual Build] | 1h | 17679 | -0.375 | -0.432 (-0.406) | 0.002 | yes | -1.441 | -0.360 | YES | no |
| FVG Pure + Inverse FVG (Fixed 1:2) [Manual Build] | 1h | 18695 | -0.378 | -0.435 (-0.410) | 0.002 | yes | -1.441 | -0.360 | YES | no |
| Liquidity Sweep Reversal Strategy [Manual Build] | 15m | 23212 | -0.383 | -0.417 (-0.387) | 0.040 | no | -1.441 | -0.360 | no | no |
| Candle Range Theory (Strict) [Manual Build] | 1h | 2953 | -0.383 | -0.418 (-0.351) | 0.200 | no | -1.441 | -0.360 | no | no |
| Equal Highs/Lows Reversal [Manual Build] | 15m | 16803 | -0.387 | -0.350 (-0.316) | 0.962 | no | -1.441 | -0.360 | no | no |
| OTE Liquidity Sweep Reversal [Manual Build] | 15m | 13685 | -0.387 | -0.432 (-0.399) | 0.008 | no | -1.441 | -0.360 | no | no |
| Donchian LWTI Volume Confluence [Manual Build] | 15m | 5740 | -0.389 | -0.219 (-0.147) | 1.000 | no | -1.441 | -0.360 | no | no |
| PDH/PDL Multi-Timeframe Reversal [Manual Build] | 5m | 8495 | -0.396 | -0.426 (-0.385) | 0.126 | no | -1.441 | -0.360 | no | no |
| Liquidity Sweep + CISD (Pure Swing Variant) [Manual Build] | 5m | 8967 | -0.397 | -0.425 (-0.384) | 0.138 | no | -1.441 | -0.360 | no | no |
| SAR + SMC (CISD Entry) [Manual Build] | 5m | 254 | -0.397 | -0.426 (-0.270) | 0.405 | no | -1.441 | -0.360 | no | no |
| Ichimoku 1h Indicator-Exit [Manual Build] | 1h | 13466 | -0.405 | -0.413 (-0.362) | 0.399 | no | -1.441 | -0.360 | no | no |
| Range Breakout Volume Confirmation [Manual Build] | 15m | 3278 | -0.410 | -0.284 (-0.200) | 0.986 | no | -1.441 | -0.360 | no | no |
| Support/Resistance + Liquidity Sweep (Fixed-RR) [Manual Build] | 1h | 6983 | -0.420 | -0.469 (-0.418) | 0.062 | no | -1.441 | -0.360 | no | no |
| Fixed Range Volume Profile -- Market Shape [Manual Build] | 1h | 19966 | -0.423 | -0.417 (-0.382) | 0.599 | no | -1.441 | -0.360 | no | no |
| Daily Liquidity Scalping Strategy [Manual Build] | 1m | 28287 | -0.425 | -0.450 (-0.421) | 0.076 | no | -1.441 | -0.360 | no | no |
| Ichimoku 15m Indicator-Exit [Manual Build] | 15m | 48161 | -0.430 | -0.427 (-0.413) | 0.647 | no | -1.441 | -0.360 | no | no |
| Candlestick Pattern Reversal Strategy [Manual Build] | 15m | 17792 | -0.435 | -0.433 (-0.393) | 0.533 | no | -1.441 | -0.360 | no | no |
| Market Structure Shift Reversal [Manual Build] | 15m | 9570 | -0.438 | -0.313 (-0.249) | 1.000 | no | -1.441 | -0.360 | no | no |
| Liquidity Sweep + Engulfing Candle (Strict) [Manual Build] | 5m | 17647 | -0.439 | -0.427 (-0.389) | 0.689 | no | -1.441 | -0.360 | no | no |
| Ichimoku 5m Indicator-Exit [Manual Build] | 5m | 134525 | -0.450 | -0.428 (-0.423) | 1.000 | no | -1.441 | -0.360 | no | no |
| Liquidity Sweep + Engulfing Candle (Loose) [Manual Build] | 5m | 26935 | -0.451 | -0.428 (-0.397) | 0.914 | no | -1.441 | -0.360 | no | no |
| Asian Range London Sweep [Manual Build] | 5m | 2715 | -0.456 | -0.423 (-0.320) | 0.677 | no | -1.441 | -0.360 | no | no |
| Liquidity Sweep Multi-Confirmation [Manual Build] | 5m | 7424 | -0.468 | -0.388 (-0.309) | 0.932 | no | -1.441 | -0.360 | no | no |
| Order Block Trading (Strict) [Manual Build] | 1h | 4002 | -0.470 | -0.259 (-0.151) | 1.000 | no | -1.441 | -0.360 | no | no |
| Previous High/Low Reversal [Manual Build] | 15m | 15035 | -0.477 | -0.397 (-0.352) | 0.998 | no | -1.441 | -0.360 | no | no |
| 4-Hour Range Breakout-Retest [Manual Build] | 5m | 11813 | -0.482 | -0.431 (-0.374) | 0.940 | no | -1.441 | -0.360 | no | no |
| SMA-Alignment Strategy (Approximate - ZIP Indicator Excluded) [Manual Build] | 1h | 1696 | -0.537 | -0.331 (-0.169) | 0.974 | no | -1.441 | -0.360 | no | no |
| Dumb Money Concepts -- Confirmation Entry [Manual Build] | 4h | 1605 | -0.570 | -0.661 (-0.294) | 0.339 | no | -1.441 | -0.360 | no | no |
| Dumb Money Concepts -- Combined Confirmation [Manual Build] | 4h | 1356 | -0.635 | -0.606 (-0.232) | 0.541 | no | -1.441 | -0.360 | no | no |
| Kotegawa Bear Market Reversal Strategy [Manual Build] | 15m | 4288 | -0.834 | -0.718 (-0.532) | 0.854 | no | -1.441 | -0.360 | no | no |
| Ichimoku 1h Trailing-SL [Manual Build] | 1h | 299 | -1.919 | +5.904 (+7.111) | 1.000 | no | -1.441 | -0.360 | no | no |

**Result: 2 of 42 strategies beat random entries significantly (FDR-controlled); 8 of 42 beat both trade-based baselines on mean return per position.** See the YES rows; each still has to pass the PF-interval and window/coin rules.
Buy-and-hold context: the average coin lost about 43 % over the window (mean of per-strategy coin sets, one round trip of costs included).

## Day 6: results by timeframe and live eligibility (Step 10)

Live rule used here (stated, measured input): the Cloud scan of 10 coins took **865 s (14.4 min)** on commit 8185853 (Step 12/14 may lower it). A strategy on timeframe T is evaluated once per scan, so a new candle can wait up to one scan before it is seen, and a signal older than the 15-minute freshness window is rejected. So: T <= 5m cannot be served (a candle every 1-5 min vs one look per ~14 min); 15m is borderline (the scan is almost one full candle long); T >= 30m can be served.

| Entry TF | Strategies | Positions | Strategies with PF x1 > 1 | Best PF x1 | Median PF x1 | ROBUST | FAILED | INSUFFICIENT | Can Cloud serve it live today? |
|---|---|---|---|---|---|---|---|---|---|
| 1m | 1 | 28287 | 0 | 0.69 | 0.69 | 0 | 1 | 0 | no (scan too slow for the candle period) |
| 5m | 10 | 231940 | 0 | 0.76 | 0.65 | 0 | 9 | 1 | no (scan too slow for the candle period) |
| 15m | 14 | 173512 | 1 | 1.44 | 0.64 | 0 | 13 | 1 | borderline |
| 1h | 13 | 129342 | 1 | 1.28 | 0.61 | 0 | 11 | 2 | yes |
| 4h | 2 | 2961 | 0 | 0.75 | 0.75 | 0 | 2 | 0 | yes |
| 1d | 2 | 697 | 2 | 1.79 | 1.79 | 0 | 0 | 1 | yes |

**Which strategies could be live today?** None is validated, so none should be promoted. Servable by timeframe (30m and slower): Candle Range Theory (Loose) [Manual Build], Candle Range Theory (Strict) [Manual Build], Dumb Money Concepts -- Combined Confirmation [Manual Build], Dumb Money Concepts -- Confirmation Entry [Manual Build], FVG Momentum Pullback (Structure) [Manual Build], FVG Pure + Inverse FVG (Fixed 1:2) [Manual Build], FVG Pure + Inverse FVG (Structure) [Manual Build], Fibonacci Golden Zone Retracement [Manual Build], Fixed Range Volume Profile -- Market Shape [Manual Build], Ichimoku 1d Indicator-Exit [Manual Build], Ichimoku 1d Trailing-SL [Manual Build], Ichimoku 1h Indicator-Exit [Manual Build] ... (see table); but servable is not the same as good.
Count on 1m-5m (research-only candidates for `SINDHU_RESEARCH_ONLY_TIMEFRAMES`): 11 of 42 strategies.

**Reading of the Day 6 corrected 50-coin validation (47 coins had data; 3 of the 50 listed coins have none in the window):**
- **0 ROBUST, 1 FRAGILE, 36 FAILED, 5 INSUFFICIENT_DATA.** The earlier 10-coin result (32 FAILED / 10 INSUFFICIENT) holds in substance: widening to 47 coins gave 5 more strategies enough trades to be judged, and all of those failed.
- The only strategy with a pooled PF above 1 is **Ichimoku 1d Indicator-Exit** (576 positions, PF 1.09, 95 % interval 0.71-1.61, PF 0.98 at 1.5x costs, 2 of 6 qualifying windows): that is indistinguishable from 1.0 and disappears with slightly higher costs.
- **Two strategies (Candle Range Theory Loose; FVG Pure + Inverse FVG Fixed 1:2) beat random entries significantly** (p = 0.002, survives false-discovery control): their entries are slightly better than luck (-0.37 % vs -0.43 % per position). **Both still lose money after costs** (PF interval 0.56-0.67). Better than random is not the same as profitable; the cost of roughly 0.3 % per round trip is larger than the edge.
- The entries of the other 40 strategies are not distinguishable from random entries with the same holding times.


---
## Day 7 dossier: Ichimoku 1d Indicator-Exit (sid d781b37694ef) - FRAGILE stays FRAGILE (Step 12)
Analysis only. Nothing was promoted or changed: the variants live in a scratch library (`D:\sindhu_data\candidates\ichimoku_sensitivity`), the Ichimoku periods were changed only inside the test process. Tool: `tools/ichimoku_sensitivity.py` (47 coins, 1 Nov 2025 - 31 Aug 2026, same costs as the main protocol, positions as the unit). 13 variants x 50 coins = 650 runs.

**Rules (from the stored file):** daily timeframe; long when the Ichimoku system is bullish, short when bearish; exit when the Ichimoku cross turns; stop = structure + 0.65 buffer; take-profit 10 R; 1 % risk. The only numbers in the file are the stop buffer (0.65), the take-profit multiple (10) and the risk; the Ichimoku periods (9 / 26 / 52 / 26) are fixed inside the indicator code, so they were perturbed through the indicator's defaults.

### 1. Sensitivity (one parameter at a time, x0.8 / x0.9 / x1.1 / x1.2; sample 445-661 positions per variant)
| Parameter | Scale | Value | Positions | PF x1 [95 % CI] | PF x1.5 | PF x2 | PF gross | Win % | Windows ok | Label |
|---|---|---|---|---|---|---|---|---|---|---|
| base | x1.0 | base | 576 | 1.09 [0.72-1.57] | 0.98 | 0.89 | 1.37 | 30.4 | 2/6 | FRAGILE |
| ichimoku periods (9/26/52/26) | x0.8 | (7, 21, 42, 21) | 661 | 1.23 [0.85-1.65] | 1.11 | 1.01 | 1.54 | 34.0 | 3/6 | FRAGILE |
| ichimoku periods (9/26/52/26) | x0.9 | (8, 23, 47, 23) | 614 | 0.94 [0.60-1.34] | 0.84 | 0.76 | 1.19 | 30.8 | 1/6 | FAILED |
| ichimoku periods (9/26/52/26) | x1.1 | (10, 29, 57, 29) | 506 | 0.79 [0.54-1.10] | 0.70 | 0.63 | 1.01 | 27.9 | 3/6 | FAILED |
| ichimoku periods (9/26/52/26) | x1.2 | (11, 31, 62, 31) | 445 | 0.65 [0.40-0.96] | 0.58 | 0.52 | 0.84 | 27.9 | 2/6 | FAILED |
| stop buffer (0.65) | x0.8 | 0.52 | 582 | 1.06 [0.70-1.53] | 0.96 | 0.87 | 1.34 | 29.9 | 2/6 | FRAGILE |
| stop buffer (0.65) | x0.9 | 0.585 | 580 | 1.09 [0.72-1.53] | 0.98 | 0.89 | 1.36 | 30.0 | 2/6 | FRAGILE |
| stop buffer (0.65) | x1.1 | 0.715 | 574 | 1.10 [0.72-1.61] | 1.00 | 0.90 | 1.38 | 30.7 | 2/6 | FRAGILE |
| stop buffer (0.65) | x1.2 | 0.78 | 572 | 1.11 [0.72-1.61] | 1.00 | 0.91 | 1.38 | 30.8 | 2/6 | FRAGILE |
| take-profit multiple (10 R) | x0.8 | 8.0 | 582 | 1.00 [0.66-1.41] | 0.90 | 0.82 | 1.26 | 30.2 | 2/6 | FRAGILE |
| take-profit multiple (10 R) | x0.9 | 9.0 | 579 | 1.03 [0.66-1.52] | 0.93 | 0.85 | 1.30 | 30.2 | 2/6 | FRAGILE |
| take-profit multiple (10 R) | x1.1 | 11.0 | 574 | 1.13 [0.75-1.67] | 1.02 | 0.93 | 1.41 | 30.5 | 2/6 | FRAGILE |
| take-profit multiple (10 R) | x1.2 | 12.0 | 571 | 1.16 [0.80-1.68] | 1.04 | 0.95 | 1.45 | 30.8 | 2/6 | FRAGILE |

**Reading:** the stop buffer and the take-profit multiple hardly matter (PF 1.00-1.16). **The Ichimoku periods matter a lot: -10 % periods gives PF 0.94 (FAILED), +10 % gives 0.79, +20 % 0.65, while -20 % gives 1.23.** An edge that flips sign for a 10 % change of the central parameter is a sign of luck in the choice of (9, 26, 52), not of a robust idea. No variant is ROBUST; every variant interval contains 1 except +20 % periods (0.40-0.96, a clear loser).

### 2. Base case in detail (576 positions, 46 coins with trades, net +327.6 on the test account)
- **Cost sensitivity:** PF 1.37 before costs, 1.09 at x1, 0.98 at x1.5, 0.89 at x2: the profit disappears with 50 % higher costs.
- **Interval:** profit factor 95 % interval 0.71-1.61 (days as clusters, 189 day-clusters); mean per position +0.57 with interval -1.90 to +3.58: not different from zero.
- **Per period (8 windows by entry time):** windows 1-2 have 0 positions (the indicator needs about 78 daily candles to warm up, so the first signals appear in January 2026); **window 3 (16 Jan - 23 Feb 2026): 62 positions, PF 22.3, net +1,700**; windows 4-8: PF 0.49, 0.10, 1.45, 0.77, 0.56, net -516, -730, +256, -127, -256 (sum -1,373). **The whole profit comes from one 5-week episode**; outside it the strategy loses.
- **Per coin:** 25 of 46 coins with trades have positive net; the five best coins (UNI, ERA, SOL, NEAR, LTC, 11-18 positions each) account for 182 % of the total net (the other coins together are negative). Leave-one-coin-out PF: 1.05 / 1.09 / 1.12 (min / median / max): not driven by a single coin, but by a small group.
- **Long / short:** 85 long positions PF 0.83 (net -98.7); **491 short positions PF 1.14** (net +426). The average coin fell 43 % over the window, so a short bias paid.
- **Trade size:** median holding 1.0 day, mean 8.7 days, longest 94 days; average win 22.5, average loss -9.0, largest win 98 (2 % of gross profit): no single trade decides the result.
- **Comparison with luck and baselines (same costs):** strategy +0.18 % net per position; **random entries with the same side mix and holding times: +1.06 % (95th percentile +1.86 %), p = 0.96**: the strategy is no better than random shorts held for the same time in a falling market. Baselines: SMA-4h crossover -1.44 % per trade (951 trades), RSI-1h reversion -0.36 % (2,430 trades); buy-and-hold lost 42.7 % on average. So the strategy beats two long-only baselines in a bear market, which a short bias explains.

### 3. Verdict
**FRAGILE, and I would not trust it.** The pooled profit factor is above 1 only at the base cost level; the interval includes 1; the gain comes from one 5-week window and from shorting a falling market; the central parameter is unstable (a 10 % change makes it lose); random entries do better. It cannot be called ROBUST, and the 8-window rule is not met (2 of 6 qualifying windows). **Not promoted, nothing changed.** To learn more: more history (a second market regime), the forward test from 6 Nov 2026 (it must be registered first), and a long/short symmetric test on a rising period.

---
## Day 7: why the 5 INSUFFICIENT_DATA strategies cannot be judged, and what each needs (Step 13)
Rule: a strategy needs at least 300 positions AND at least 6 of the 8 walk-forward windows with at least 30 positions each. "Windows" below are the 8 windows of about 38 days from 1 Nov 2025 to 31 Aug 2026 (positions per window, profit factor per window). 47 coins were run for each. Sample sizes are the positions shown.
| Strategy | TF | Positions | PF x1 | Positions per window (1 -> 8) | Windows with >= 30 | Why it is INSUFFICIENT_DATA | What it needs |
|---|---|---|---|---|---|---|---|
| Ichimoku 1d Trailing-SL | 1d | 121 | 1.79 | 0, 0, 47, 11, 13, 26, 16, 8 | 1 | **Timeframe + warm-up:** a daily system needs about 78 daily candles before its first signal (windows 1-2 are empty) and then trades about 12 times a month over 47 coins; the only strong window is window 3 (PF 6.0, 47 positions), the later windows are below 1 | about 2 years more history (to reach 300 positions in 6 windows), or about 120 coins; the PF > 1 is carried by one window and cannot be trusted |
| SAR + SMC (CISD Entry) | 5m | 254 | 0.36 | 27, 38, 14, 22, 47, 24, 32, 50 | 4 | **Too few trades**, but every window is a loss (PF 0.15-0.60) | 46 more positions would already label it FAILED; about 12 months of the same rate; nothing suggests an edge |
| Ichimoku 1h Trailing-SL | 1h | 299 | 1.28 | 155, 57, 26, 20, 15, 12, 4, 10 | 2 | **Too few trades, and bunched at the start:** 52 % of all positions are in window 1 (PF 1.66), then PF 0.6 and falling; one position short of 300 | months of new data (the recent months show only 4-12 positions per window); the early profit looks like one episode |
| Ichimoku 15m Trailing-SL | 15m | 509 | 1.44 | 294, 56, 54, 3, 5, 46, 24, 27 | 4 | **Bunched in too few windows:** 58 % in window 1 (PF 2.02); windows 4-8 are PF 12.6 (3 positions), 0.5, 0.35, 0.17, 0.33 | a longer history with trades in other periods; the PF of 1.44 is one early episode, recent windows lose |
| SMA-Alignment (approximate, ZIP indicator excluded) | 1h | 1,696 | 0.74 | 0, 0, 0, 0, 0, 585, 553, 558 | 3 | **Warm-up gap, not lack of signals:** zero positions in the first five windows, then about 560 per window from window 6 (10 May 2026). That is what a long-timeframe indicator (about 26 weeks) produces when the data starts in Nov 2025; this reading is an inference, I did not open its indicator list | about 2 more years of history BEFORE Nov 2025 for the first window to be usable; in the three windows it can trade it loses (PF 0.90, 0.61, 0.70) |
**Common need:** more history than 12 months. The Binance archive reaches back years; extending the 20 most liquid coins by 24 months would cost about 0.8 GB and the existing downloader (`python -m data_platform.run_download --months 36` after a decision; it only adds files, never deletes). It would also add a second market regime (the 10 months tested are a falling market: the average coin lost 43 %). I did not download anything for this today.
**Do not conclude anything either way from these five.** Three of the five (the two Ichimoku trailing variants and the 1d one) show PF above 1 only because of one early window.
