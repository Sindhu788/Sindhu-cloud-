# SINDHU

## About
SINDHU is a crypto **paper-trading research system**: no real money, no real orders. It imports trading strategies, backtests them
on 24.6 million Binance 1-minute candles with costs, a sealed holdout and multiple-testing checks, and paper-trades them live on a free
cloud instance with strict safety gates (statistical gate, confluence, freshness, drawdown breaker, kill switch). A single $100
"real-like" paper wallet applies the rules of a real small account: 1 % risk per trade, $5 minimum order, fees and slippage, a daily
loss limit. So far **no strategy has shown a robust edge** (0 ROBUST, 1 FRAGILE, 36 FAILED, 5 INSUFFICIENT_DATA; two new trend
strategies FRAGILE). Finding that out honestly is the point of the project.

- Owner guide (Hinglish, one page): docs/OWNER_ONE_PAGE_HINGLISH.md
- Master plan and its state: docs/MASTER_PLAN.md, docs/MASTER_PLAN_STATE.md
- Backtest protocol and results: docs/BACKTEST_PROTOCOL.md, docs/BACKTEST_RESULTS.md, docs/STRATEGY_V2_REPORT.md
- Rollback: docs/ROLLBACK.md

**Paper trading only. Not financial advice. Past results do not predict future results.**
