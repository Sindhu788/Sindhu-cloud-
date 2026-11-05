# BENCHMARK PRE-REGISTRATION V2 (Master Plan B1)

Written 2026-11-05 ~21:20 UTC, **before any data for these strategies was downloaded and before any result was seen**. Committed to git before B4 runs; the commit hash is recorded in docs/MASTER_PLAN_STATE.md. After commit, nothing in this file may change. A later correction would have to be a new, dated section that says what changed and why. Results would then be reported both ways.

These are adaptations inspired by published trend-following / time-series-momentum research. They are not the papers' exact rules, and the published claims are not assumed to be true here.

## 0. Common rules

**Universe (frozen rule).**
- Take the existing ranking `D:\sindhu_data\universe\universe_2026-11-04_v2.json`: top 50 Binance USDT spot pairs by 30-day quote volume, built 4 Nov 2026, before this plan existed.
- Walk it in rank order and keep the **first 20 symbols whose first native Binance daily candle is on or before 2023-01-01**, so each coin has at least one in-sample year.
- BTCUSDT is always included (rank 1).
- B2 resolves this rule into the actual list, writes it with listing dates into `D:\sindhu_data\daily\universe_v2.json`, and copies it into section 5 of this file as an appendix. Listing dates are not a performance result, so resolving the rule after commit does not leak results.
- Limitation: survivorship bias. Coins that died before 2026 are absent, so results are optimistic.

**Data.** Native Binance spot daily klines (1d interval, `data.binance.vision`, public), from 2018-01-01 or the listing date to the last closed day. Each day's candle opens at 00:00 UTC. No resampling. A coin with no candle yet on a day has weight 0 (cash).

**Timing (no lookahead).** Signals use only data up to and including the close of day t. Trades execute at the open of day t+1. The last candle used must be closed.

**Portfolio.**
- Starting capital $100 (results also in %). Long-only, no leverage. Total gross weight is at most 1; the rest is cash earning 0.
- Holdings are kept in coin units, so weights drift between rebalances.
- Fractional sizes are allowed in the backtest. Limitation: a real $100 account at about $5 per position would hit the Binance $5 minimum notional; this is noted, not modelled.

**Costs.** 0.10 % fee + 0.05 % slippage **per side**, on traded notional (0.15 % per side, 0.30 % round trip). Stress run at 1.5× costs (0.225 % per side).

**Volatility scaling (both strategies).**
- `realized_vol_30d(t)` = sample standard deviation (ddof = 1) of the last 30 daily close-to-close log returns ending at close t. If fewer than 30 returns exist, the coin cannot be held.
- Per-coin target weight = `signal × min(1, target_vol / realized_vol_30d) / N`, with N = 20 (fixed, also while some coins are not listed yet) and target_vol = 0.02 (2 % daily).

**Periods.**
- In-sample (IS): 2018-01-01 → 2023-12-31.
- Out-of-sample (OOS): 2024-01-01 → 2026-10-31. No change of any rule after seeing IS or OOS.
- Walk-forward: rolling test years 2021, 2022, 2023, 2024, 2025 and 2026 (Jan to Oct), each with the preceding 3 years as "train". There are no free parameters, so "train" fits nothing. It is reported only to show whether train-period and test-period behaviour agree.
- Forward-test data (from 2026-11-06) is never used.
- Limitation: Sep–Oct 2026 is inside OOS. That window was already looked at for other strategies (Day 4), so OOS is not perfectly untouched for crypto in general, but it was never used for these two strategies.

**Benchmarks.** BTC buy-and-hold, and an equal-weight buy-and-hold of the universe (coins enter at their listing, monthly rebalance to equal weight). Both are charged the same costs.

**Robustness.**
- Neighbours: one parameter at a time at ±10 % and ±20 %, rounded to whole days. For Strategy 1: all three lookbacks scaled together, and target_vol separately. For Strategy 2: the momentum window, and target_vol separately. That is 8 neighbour runs per strategy.
- Bootstrap: 1,000 resamples (seed 20261105) of (a) per-position net returns and (b) 20-day blocks of OOS daily portfolio returns.
- Results per calendar year.

**Trade counting.** One position = one coin going from weight 0 to weight > 0 and back to 0. Partial rebalances inside a position are not new trades. Position return = net P&L of that coin over the position, including costs, divided by the notional at entry.

**Metrics.** CAGR, Sharpe (daily, annualised with √365, risk-free 0), Sortino, max drawdown, profit factor (over positions), positions, win rate, exposure % (average gross weight), t-statistic of mean daily return, turnover (annual, sum of |Δw|), and cost drag (gross CAGR − net CAGR).

## 1. Strategy 1: Donchian Trend Ensemble (daily, long-only)
- For each L in {20, 55, 100}, sub-signal s_L(t):
  - It becomes 1 when close(t) > max(high of days t−L … t−1).
  - It becomes 0 when close(t) < min(low of days t−⌊L/2⌋ … t−1); ⌊L/2⌋ = 10, 27, 50.
  - Otherwise it keeps its previous value. It starts at 0.
- Signal = mean of the three sub-signals: 0, ⅓, ⅔ or 1.
- Rebalance daily with a 10 % no-trade band. For each coin:
  - trade to the target if the current weight is 0, or the target is 0, or |target − current| > 0.10 × current;
  - otherwise do nothing.

## 2. Strategy 2: Volatility-scaled Time-Series Momentum (daily data, weekly rebalance, long-only)
- Signal at the close of Sunday (the daily candle that closes Monday 00:00 UTC): 1 if close(t) / close(t−28) − 1 > 0, else 0.
- Weights are set with the same volatility scaling and executed at the Monday open. They are not touched again until next Monday, apart from drift. No band.

## 3. Verdict rules (fixed before results)
Classes come from docs/BACKTEST_PROTOCOL.md, adapted to a daily portfolio strategy.

- **INSUFFICIENT_DATA:** fewer than 300 positions over IS + OOS, or fewer than 30 positions in OOS, or fewer than 5 coins with any OOS position.
- **FAILED:** OOS net total return ≤ 0, or pooled profit factor after costs ≤ 1.0 over IS + OOS.
- **ROBUST** requires ALL of:
  1. OOS net total return > 0 and OOS Sharpe > 0.
  2. IS net total return > 0.
  3. Walk-forward: at least 4 of the 6 test years positive, and the combined walk-forward test return > 0.
  4. OOS Sharpe ≥ the Sharpe of the better benchmark (BTC buy-and-hold or equal-weight) minus 0.05 (this is what "matches" means).
  5. None of the 8 neighbours has an OOS net return ≤ 0.
  6. Pooled profit factor ≥ 1.1 at 1× costs and > 1.0 at 1.5× costs.
  7. Bootstrap one-sided p-value (OOS daily-return blocks, H0: mean ≤ 0) passes Benjamini–Hochberg at q = 0.05 over **44 tests**: the 42 strategies already tested plus these 2. The 42 earlier p-values are taken from the existing rigor output where available; otherwise the threshold used is the most conservative one (Bonferroni 0.05/44).
- **FRAGILE:** not FAILED and not INSUFFICIENT_DATA, but at least one ROBUST rule fails.
- Even a ROBUST result is only a candidate: paper only, no Cloud sync without owner approval (master plan B6), and a forward test before any trust.

## 4. What will be reported
Every metric above for IS, OOS, each walk-forward year and each neighbour; benchmark comparison; equity and drawdown PNGs; and the verdict with the rule that decided it. Reported in docs/BACKTEST_RESULTS.md (new section) and docs/STRATEGY_V2_REPORT.md. A negative result is reported as "no edge found", not tuned away.

## 5. Appendix: resolved universe (filled by B2 from the frozen rule; not a result)
(pending B2)
