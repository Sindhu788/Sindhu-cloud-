# Backtest protocol (Day 5, 5 Nov 2026)

Purpose: give the owner a test of the 42 enabled strategies that is hard to fool. No strategy parameter is changed anywhere in this protocol.

## 1. Data (docs/DATA_PLAN.md, docs/DATA_QUALITY.md)
Binance spot 1-minute candles, 50 liquid coins, Nov 2025 - Oct 2026 (+ Nov 2026 closed days), protected folder `D:\sindhu_data`. Every timeframe is resampled from the verified 1-minute data (exact rules, windows with a missing minute dropped). The loader (`data_platform/loader.py`) serves CLOSED candles only and stamps each frame with a `data_version` hash of the files read.

## 2. Splits
| Part | Dates | Used for |
|---|---|---|
| Development | 1 Nov 2025 - 31 Aug 2026 (10 months) | all results in docs/BACKTEST_RESULTS.md; split into **8 equal walk-forward windows** (about 38 days each) |
| **Sealed holdout** | 1 Sep 2026 - end of data (the last 2 complete months) | one single "final exam" at the very end, never used for choosing anything |
The boundary is written once to `manifest/protocol.json` and never changes. The loader REFUSES any request that reaches into the holdout (`HoldoutAccessError`) unless `allow_final_exam=True` AND the environment variable `SINDHU_FINAL_EXAM=I_ACCEPT_ONE_LOOK` is set; every such look is appended to `manifest/holdout_access.log` and counted (tests: `tests/test_data_loader.py`). Default window end = the holdout boundary, so ordinary code cannot touch it by accident.
**Walk-forward without training:** nothing is optimised, so "walk-forward" means scoring the same fixed strategy window by window (each trade belongs to the window of its entry time). Each (strategy, coin) is backtested once over the whole development period and sliced afterwards, which is equivalent and much faster.

## 3. Costs (`data_platform/cost_model.py`)
Per side: commission 0.10 % (Binance spot taker; no discount assumed); spread 0.01 / 0.02 / 0.05 % by liquidity tier (coin rank <= 5 / <= 20 / rest); slippage = tier part (0.02 / 0.04 / 0.08 %) + 0.10 x the coin's median 1-minute range. No funding or borrow (spot; shorts therefore slightly optimistic). **Sensitivity x1.5 and x2** is computed exactly from the x1 trades (`reprice`: `pnl + (1 - m) x (commission + slippage + spread)`, because slippage and spread are inside the fill prices and the trade path does not depend on costs).
Compared with the paper engine: paper uses commission 0.1 % and a constant 0.05 % slippage per side; the backtest slippage varies with coin liquidity and volatility. Both ignore market impact and partial fills; both fill at the signal-bar close. Remaining discrepancies are listed in docs/STRATEGY_FORENSICS.md (section 17).

## 4. Labels (`data_platform/protocol_analyze.py`)
Minimum sample: a strategy needs **>= 300 trades** and **>= 6 walk-forward windows with >= 30 trades each**, else `INSUFFICIENT_DATA`.
- `FAILED`: pooled profit factor after costs <= 1.0.
- `FRAGILE`: pooled PF > 1.0 but a robustness rule fails.
- `ROBUST`: ALL of: PF >= 1.1 in >= 60 % of the qualifying windows; PF >= 1.1 in >= 60 % of the coins that have >= 30 trades (and at least 3 such coins); pooled PF >= 1.1 at cost x1 AND > 1.0 at cost x1.5.
**Multiple testing warning:** 42 strategies are tested; at a 5 % level about two will look good by luck. Each strategy therefore also gets the t-statistic of its mean net R per trade and a `bonferroni_ok` flag (t >= 3.24, the two-sided 5 %/42 level). A ROBUST label without `bonferroni_ok` is a CANDIDATE that still has to survive the sealed holdout and months of paper trading; it is not proof. Trades of different coins/strategies on the same day are correlated, so the t-statistic is optimistic; treat it as a screening aid.

## 5. Reproducibility and tracking
Every run is stored in `D:\sindhu_data\experiments\experiments.db` with config hash, code commit, data_version, universe, symbol, window, cost model, number of trades and a result hash of the trade list (`data_platform/experiments.py`). **Test on real data (5 Nov 2026):** the same strategy (62e44ad0fa92) on ETHUSDT run twice into two empty folders gave 342 trades and the identical result hash `082b961eaa052e8f` both times; data_version `a2ee06c5b5a31dca`, commit `15fb5ca`.

## 6. Engine speed (Step 14)
Profile of one run (strategy 62e44ad0fa92, BTCUSDT, 10 months of 15m entries = 29,184 bars; cProfile, 20.1 s): loading the Parquet data 1.0 s (0.7 s of it reading), indicator preparation about 1 s, **the bar loop 18.5 s**: strategy condition evaluation `on_bar` 12.1 s (own time 6 s in `_eval`, 2.08 million `_rcol` string builds 3 s), and **pandas Timestamp boxing for the day-change check 4.5 s (22 %)**.
Changes: (1) the day-change check now uses precomputed integer UTC days instead of `times[i].date()` for every bar (`backtest_engine/engine.py`); (2) the concept memo was tried for backtests and gives nothing (10 strategies on BTC: 104.6 s without, 102.8 s with, 16 hits) so it stays scan-only. **Golden output:** the ten-strategy BTC run (trade count + result hash per strategy) is identical before and after: TRUE. Speed numbers before/after are in section 7 (measured on a quiet machine).
The Parquet loader reads a coin-month in about 0.06 s; a 10-month frame loads in about 1 s (the old SQLite path needed the 10 GB database).

## 7. Run record
See docs/BACKTEST_RESULTS.md (written; 420 runs, 0 ROBUST) for the per-strategy table, the command that produced it and the elapsed time.

## 8. Holdout contamination audit (Day 6 Step 7, 5 Nov 2026)
The sealed window is 1 Sep 2026 onward (`manifest/protocol.json`: holdout_first_month 2026-09, last 2026-10, plus every later day). Everything below was read in this session from the repository documents and the file system.
| Earlier analysis | Where | Looked inside Sep-Oct 2026? | Effect |
|---|---|---|---|
| Day 4 backtest of the 10 most-traded strategies on BTC/ETH/SOL, 1 Sep - 1 Nov 2026 | docs/PERFORMANCE_RECONCILIATION.md (tree comparison) | **YES, the whole window** | those 10 strategies x 3 coins have been seen in the holdout |
| Day 4 "walk-forward" IS = Sep 2026, OOS = Oct 2026 (same 10 strategies, 3 coins) | PERFORMANCE_RECONCILIATION.md Step 22 | **YES** (both months) | used to describe collapse of Liquidity Sweep Multi-Confirmation and Daily Liquidity Scalping |
| Day 4 strategy forensics on paper trades 29 Aug - 16 Sep (1,132 trades) and the keep/watch/pause notes | docs/STRATEGY_FORENSICS.md, docs/SCORECARD_2026-11-03.md | **YES (live paper results of 1-16 Sep)** | keep/watch/pause opinions already use September outcomes |
| Day 5 exchange comparison (Binance vs Bybit candles, October 2026, top-10 coins) | data_platform/compare_exchanges.py | **YES, October prices were read** directly through `store` (not through the loader, so it is NOT in the access log) | prices only, no strategy result was computed, but the guard did not see it |
| Day 5 data quality / integrity audit | docs/DATA_QUALITY.md | opened all files to check hashes and OHLC rules | no performance computed |
| Day 5 42-strategy protocol run | docs/BACKTEST_RESULTS.md | **NO**: development window ends 31 Aug 2026 | clean |
| Loader access log | `manifest/holdout_access.log` | the file does not exist: **0 logged accesses** through the loader | the loader was never asked for the final exam |
**Conclusion: the Sep-Oct 2026 holdout is NOT clean.** For the 10 most-traded strategies it has been used for analysis (3 coins), and the September paper results influenced the keep/watch/pause opinions. For the other 32 strategies and the other 47 coins it was not examined for performance, but the window can no longer be called a sealed final exam for the system as a whole. No result from it may be used as confirmation. (It is kept sealed in the loader anyway; it remains a legitimate EXTRA sanity check for strategies never looked at, only with that caveat stated.)

## 9. Replacement: pre-registered FORWARD test (written 5 Nov 2026, before any forward data is examined)
- **Forward data** = candles that close at or after **2026-11-06 00:00 UTC** (the day after this registration), plus live paper trades opened after that moment. Nothing from this window may be looked at for performance until the evaluation date. (Downloading it is allowed; analysing it is not.)
- **Who can be tested:** a strategy registered BEFORE the window, with its id, config hash and code commit written to `D:\sindhu_data\manifest\forward_registry.json`. No parameter change after registration; a changed strategy is a new candidate with a new window.
- **Evaluation date:** not before **2027-01-05** (60 days) and not before 100 closed positions per candidate; one single look, recorded in the registry. If fewer than 100 positions exist by then, the answer is INSUFFICIENT_DATA, not a pass.
- **Measured (position level, net of costs, corrected metrics of data_platform/metrics.py):** profit factor at cost x1 and x1.5, cluster-bootstrap 95 % interval of the profit factor (clusters = days), expectancy, max drawdown, random-entry null-model p-value, comparison with the three baselines.
- **Pass criteria (all):** >= 100 positions; PF >= 1.2 at x1; PF > 1.0 at x1.5; lower end of the 95 % PF interval > 1.0; null-model p < 0.05; beats the best baseline's mean net return per position; false-discovery-rate controlled if several candidates are evaluated together.
- **Secondary evidence, not a pass criterion:** live paper results since the paper balance reset (reset date NOT VERIFIED by me; owner statement only). Paper results are execution-realistic but are a few weeks of one regime.
- **If the forward test fails:** the strategy stays out of the promotion path; nothing is retuned on the forward data.

## 10. Statistical rigour layer (Day 6 Step 6)
Code: `data_platform/metrics.py` (definitions), `data_platform/rigor.py` (tools, numpy only, 8 tests in tests/test_rigor.py), `data_platform/protocol_rigor.py` (applies it to the stored runs; writes `experiments/protocol_rigor.json`).
- **Unit = position** (all legs of one entry together), R = position pnl / position risk, everything net of costs.
- **Minimum sample (unchanged, stated):** INSUFFICIENT_DATA unless >= 300 positions overall AND >= 6 of 8 walk-forward windows with >= 30 positions. (Stricter than the "30 per window / 100 overall" minimum suggested in the Day 6 prompt, kept because 100 trades cannot separate a profit factor of 1.1 from 1.0.)
- **Confidence intervals:** 95 % cluster bootstrap (1,000 draws, resampling whole exit DAYS across all coins) for profit factor and mean money per position. Clustering matters: trades on the same day are correlated (lag-1 autocorrelation of R is 0.12-0.28 in the strategies checked), so a per-trade interval would be far too narrow.
- **Multiple testing:** Benjamini-Hochberg false-discovery-rate control (q = 0.05) over the one-sided null-model p-values of all strategies (the older Bonferroni t-flag stays in the table as `bonferroni_ok`, but per-trade t-statistics are optimistic, see docs/BACKTEST_RESULTS.md).
- **Random-entry null model:** for every strategy and coin, the same number of positions, side mix and holding times, entries drawn uniformly at random inside the development window, same round-trip costs (2 x (commission + spread + slippage) of that coin), 500 simulated books per strategy (seeded by a stable hash, so reruns are identical). The strategy's mean net return per position (fill prices, minus 2 x commission) is compared with the null distribution; p = share of simulated books at least as good (+1 correction). **Limitation:** the null copies the holding TIME, not the stop/target path, so it asks "does the entry timing beat luck, with exits held fixed".
- **Baselines under the same costs:** SMA(20/50) crossover on 4h (long only), RSI(14) < 30 buy / > 50 sell on 1h (long only), buy-and-hold per coin (one round trip). A strategy must beat both trade-based baselines' mean net return per trade.
- **ROBUST requires everything:** the Day 5 rules (PF >= 1.1 in >= 60 % of qualifying windows and coins, PF >= 1.1 at x1 and > 1 at x1.5) AND PF interval lower bound > 1 AND null p < 0.05 AND FDR pass AND above both baselines. Otherwise a would-be ROBUST is downgraded to FRAGILE (`protocol_rigor.final_label`).
Worked example (Daily Liquidity Scalping, 10 coins, 200 simulations): net return per position -0.348 % vs -0.330 % for random entries with the same holding times (p = 0.66): its entries add nothing over luck; the PF interval 0.647-0.844 excludes 1, so the loss is real, and it is mostly the cost of about 0.3 % per round trip.

## 11. Forward-test reporting (Day 7 Step 15)
**Report:** `python tools/forward_report.py [--export <Cloud export folder>]` (data venv; export first with `scripts/backup_cloud_export.py`). It counts only positions OPENED on or after the window start (6 Nov 2026 00:00 UTC) that are closed, per strategy, and prints data-quality notes (duplicate ids, missing pnl, positions open more than 7 days, scan coverage and the longest gap between scans). **Before 5 Jan 2027 it prints counts only: no profit, win rate, profit factor or verdict, and the command line has no option to change the date or to force a verdict** (the computer's clock decides; 10 tests in `tests/test_forward_report.py`). After that date a verdict is computed only for strategies registered beforehand, only from criteria computable from paper trades (positions >= 100, profit factor >= 1.2, lower end of the 95 % interval > 1); the criteria that need candles (costs x1.5 re-pricing, random-entry null model, baselines) are shown as NOT COMPUTED, so the verdict can be FAILED, INSUFFICIENT_DATA or "CANNOT CONCLUDE" but never PASSED until those are added. Every verdict report is logged in `manifest/forward_looks.log` (append-only).
**Register a candidate (before it trades):** `python tools/forward_register.py --strategy-id <id>`. Append-only (a `.bak` copy of the registry is kept), stores the config hash and code commit, and gives the candidate its OWN window start = the next UTC midnight, so nothing already seen can count. A strategy that is changed, paused or re-tuned after registration must be registered again with a new window.
**State on 5 Nov 2026:** 0 candidates registered (none passed the backtest), 0 forward positions; first report: `D:\sindhu_data\forward_reports\forward_20261105.md`. Registering the one FRAGILE strategy was NOT done on purpose: at its trade rate (about 12 positions a month over 47 coins, fewer on the 10 coins Cloud scans) it cannot reach 100 positions in 60 days, so its forward test would end INSUFFICIENT_DATA by design.
