# STRATEGY V2 REPORT: two pre-registered daily trend strategies (master plan B5)

Generated 2026-11-05 22:17 UTC from `D:\sindhu_runtime\bt_jobs\BT-RUN-v2` (run 2, see the pre-registration's Amendment 2). Rules, universe, costs and verdict criteria: docs/BENCHMARK_PREREGISTRATION_V2.md (committed 7388c1b before any data or result). Local backtest only: nothing was synced to Cloud, and nothing trades with these strategies.

## Verdicts

| Strategy | Verdict (run 2) | Run 1 verdict | Failed rule(s) | OOS p (block bootstrap) |
|---|---|---|---|---|
| Donchian ensemble | **FRAGILE** | FRAGILE | 7 BH q=0.05 over 44 tests | 0.168 |
| Vol-scaled TSMOM | **FRAGILE** | FRAGILE | 7 BH q=0.05 over 44 tests | 0.117 |

**In plain words.**
- Both strategies made money after costs in-sample (2018–2023) and out-of-sample (2024 to Oct 2026).
- Both did so in 4 of 6 walk-forward years, and all 8 parameter neighbours of each stayed positive.
- Their out-of-sample Sharpe beat both buy-and-hold benchmarks, with much smaller drawdowns.
- But neither is statistically strong enough. Among 44 tested strategies (the 42 earlier ones plus these 2), a result this good can still be luck (p = 0.17 and 0.12; Benjamini–Hochberg can never accept a p above 0.05, whatever the rank).
- They also made LESS absolute money than simply holding BTC or an equal-weight basket out-of-sample: they sit in cash 74–80 % of the time (exposure 26 % and 20 %).
- Verdict: **FRAGILE, no proven edge**. Not a candidate for live use; at most a forward-test candidate (owner decision).

## Results by period (after costs, $100 start; daily Sharpe annualised with √365)

### In-sample 2018-01-01 → 2023-12-31

| Metric | Donchian ensemble | Vol-scaled TSMOM | BTC buy & hold | Equal-weight buy & hold |
|---|---|---|---|---|
| Total return % | 156.68 | 306.74 | 215.82 | 1,324.05 |
| CAGR % | 17.00 | 26.33 | 21.12 | 55.66 |
| Sharpe | 1.41 | 1.51 | 0.63 | 0.95 |
| Sortino | 2.06 | 2.22 | 0.91 | 1.34 |
| Max drawdown % | -17.63 | -21.55 | -81.28 | -86.43 |
| Profit factor (positions) | 4.04 | 2.83 | inf | 7.76 |
| Positions | 279 | 456 | 1 | 20 |
| Win rate % | 34.10 | 42.30 | 100.00 | 70.00 |
| Exposure % | 11.50 | 16.70 | 100.10 | 100.00 |
| t-stat (daily) | 3.45 | 3.70 | 1.55 | 2.34 |

### Out-of-sample 2024-01-01 → 2026-10-31

| Metric | Donchian ensemble | Vol-scaled TSMOM | BTC buy & hold | Equal-weight buy & hold |
|---|---|---|---|---|
| Total return % | 33.93 | 58.29 | 83.52 | 89.35 |
| CAGR % | 10.85 | 17.58 | 23.88 | 25.25 |
| Sharpe | 0.78 | 0.97 | 0.69 | 0.67 |
| Sortino | 1.14 | 1.49 | 1.04 | 0.97 |
| Max drawdown % | -14.36 | -16.86 | -52.98 | -58.97 |
| Profit factor (positions) | 1.74 | 1.84 | - | - |
| Positions | 192 | 323 | 0 | 0 |
| Win rate % | 27.10 | 39.90 | - | - |
| Exposure % | 19.90 | 26.00 | 100.00 | 100.00 |
| t-stat (daily) | 1.32 | 1.64 | 1.16 | 1.13 |

### Walk-forward test years (total return %, Sharpe)

| Year | Donchian | TSMOM | BTC B&H | EW B&H |
|---|---|---|---|---|
| 2021 | +64.8 (2.92) | +109.2 (3.60) | +59.8 (0.98) | +1020.2 (2.79) |
| 2022 | -11.0 (-1.63) | -16.5 (-0.87) | -64.2 (-1.29) | -72.4 (-1.11) |
| 2023 | +32.2 (1.83) | +59.5 (2.31) | +155.8 (2.35) | +218.3 (2.31) |
| 2024 | +33.5 (1.68) | +43.2 (1.80) | +121.4 (1.76) | +99.8 (1.36) |
| 2025 | -3.3 (-0.20) | +10.6 (0.70) | -6.3 (0.05) | -20.6 (0.06) |
| 2026 (Jan–Oct) | +3.7 (0.45) | -0.1 (0.08) | -11.5 (-0.11) | +19.3 (0.65) |

### Robustness

| Check | Donchian | TSMOM |
|---|---|---|
| Neighbours, OOS total return % | lookbacks x0.8: +34.6, target_vol x0.8: +27.1, lookbacks x0.9: +32.6, target_vol x0.9: +30.8, lookbacks x1.1: +34.1, target_vol x1.1: +36.9, lookbacks x1.2: +35.8, target_vol x1.2: +40.0 | window x0.8: +77.2, target_vol x0.8: +47.9, window x0.9: +72.3, target_vol x0.9: +53.3, window x1.1: +84.4, target_vol x1.1: +62.3, window x1.2: +70.9, target_vol x1.2: +65.7 |
| Pooled profit factor x1 / x1.5 costs | 2.80 / 2.74 | 2.18 / 2.14 |
| OOS total return at 1.5x costs | +32.8 % | +55.6 % |
| Cost drag (CAGR gross − net), IS / OOS | 0.45 / 0.69 pts | 0.87 / 1.41 pts |
| Mean net return per position, 95 % bootstrap CI (IS+OOS) | [21.698, 56.248] % | [7.736, 15.396] % |
| Positions IS+OOS / OOS | 471 / 192 | 779 / 323 |
| Turnover (x starting capital per year, approximate) | 7.26 | 21.38 |

![equity](strategy_v2/equity.svg)

![drawdown](strategy_v2/drawdown.svg)

## Limitations (read before believing any number)
- **Survivorship bias:** the universe is today's top coins that already existed in 2023. Coins that died are missing, so the results are optimistic.
- **Short history, one regime family:** crypto spot from 2018 has only a few bull/bear cycles. 2022 was negative for both strategies.
- **Multiple testing:** 44 strategies have now been tried on this market; the FDR rule is what failed here.
- **Small account:** fractional sizes are assumed. At $100 the 1/20 weights hit Binance's $5 minimum notional, so real fills would differ.
- **Not perfectly untouched OOS:** Sep–Oct 2026 was looked at earlier for other strategies.
- **Run 1 bug:** the first run mis-valued the benchmarks on the 8 Feb 2018 outage day; fixed and re-run (Amendment 2). Strategy numbers did not change.
- Charts are SVG, not PNG: no plotting library is installed and none was added.

## What to try next (ranked, each needs its own pre-registration)
1. Put both into the **forward test** as paper-only candidates (owner decision). At their out-of-sample rates (5.6 and 9.5 new positions a month over 20 coins), reaching the protocol's 100 positions takes about 18 and 11 months, so a verdict on 5 Jan 2027 would be INSUFFICIENT_DATA for both.
2. A **combined** trend portfolio (the two signals averaged): may lower variance, but it is a NEW test and counts as #45.
3. A survivorship-free universe (top-20 re-ranked each year from that year's data) to measure how much of the result is survivorship.
