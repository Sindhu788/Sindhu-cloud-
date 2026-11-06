# Portfolio story (master plan A26 / P25): honest, no profit claims

## README "About" section (also in README.md)
SINDHU is a crypto **paper-trading research system**: no real money, no real orders. It imports trading strategies, backtests them
on 24.6 million Binance 1-minute candles with costs, a sealed holdout and multiple-testing checks, and paper-trades them live on a free
cloud instance with strict safety gates (statistical gate, confluence, freshness, drawdown breaker, kill switch). A single $100
"real-like" paper wallet applies the rules of a real small account: 1 % risk per trade, $5 minimum order, fees and slippage, a daily
loss limit. So far **no strategy has shown a robust edge** (0 ROBUST, 1 FRAGILE, 36 FAILED, 5 INSUFFICIENT_DATA; two new trend
strategies FRAGILE). Finding that out honestly is the point of the project.

## 5 CV bullet points
- Built a Python/FastAPI paper-trading platform (local SQLite + cloud Postgres on a 512 MB free instance) with a resumable research
  pipeline over 24.6 M market-data rows and SHA-256-verified, read-only data files.
- Designed a backtest protocol with pre-registration, a sealed holdout, walk-forward windows, a random-entry null model and
  Benjamini–Hochberg control over 44 tests. Found and fixed a trade-counting bug (legs vs positions) that had inflated sample sizes.
- Diagnosed production problems from logs and per-stage timing: exchange geo-blocks (HTTP 451/403), a 20-day re-download loop,
  database connection storms, and memory at 517–536 MB on a 512 MB plan. Fixed them with incremental fetching, deadlines, rate
  limiting and a connection breaker (memory 386–406 MB on the first measured scan afterwards).
- Implemented safety-first automation: public signals off by default, owner-only bot commands, config validation that refuses
  only new entries, a kill switch with an in-page confirmation, and 2,596 automated tests with deterministic replacements for flaky ones.
- Reported negative results openly: 0 robust strategies so far, and new strategies labelled FRAGILE rather than tuned until they looked good.

## Short LinkedIn post
> I spent the last weeks building SINDHU, a crypto **paper-trading** research system: no real money.
> The surprising part was not the code but the honesty: on 10 months of 1-minute data for 47 coins, with fees and a sealed holdout,
> **none** of 42 imported strategies held up. Two new trend-following strategies did better than buy-and-hold on risk, but not well
> enough to rule out luck across 44 tests.
> I also learned more about production than about trading: exchange geo-blocks, a 512 MB server at 530 MB, and database connection
> storms, all visible only through careful logging.
> Next: a 2-month forward test before anyone trusts any number. #python #backtesting #datascience
