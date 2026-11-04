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
