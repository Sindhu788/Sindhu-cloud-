# SINDHU Backtesting Engine — Progress Summary (A to Z)

**Last updated:** 2026-07-24

## Phase 1 — Trade Execution / PnL / Risk Engine
- All entry types implemented: Market, Limit, Stop, Signal-Candle-High/Low, Next-Candle-Open.
- Partial Take Profit, Trailing Stop, Time Exit, Break-Even.
- Full PnL breakdown per trade: gross PnL, commission, slippage, spread (no double counting).
- Risk Engine: leverage, spread, daily loss limit, max drawdown circuit breaker.

## Phase 2 — Strategy & Backtest Verification Engine
- `strategy_verifier.py`: proves every rule in a strategy JSON is actually reached by the Rule Engine (SKIPPED / NEVER_TRUE / OK).
- `trade_validator.py`: independently re-derives entry/exit/SL/TP/PnL/RR for every trade, catches mismatches.
- `verification_engine.py`: single orchestrator, PASS only if every rule + every trade verifies clean.

## Final Audit
- **Real bug found & fixed:** take-profit exits were getting adverse slippage applied (should fill at exact limit price) — was silently turning real wins into fake losses on some trades. Fixed in `engine.py`.
- `data_engine/data_quality.py`: missing/duplicate candles, invalid timestamps, corrupted OHLC, resampling-correctness checks.
- `tests/test_no_lookahead_bias.py`: proves the engine and all concept functions are causal (no look-ahead/repainting).
- `statistics_verifier.py`: independently re-derives win rate, profit factor, net profit, drawdown — cross-checks against reported metrics.
- `engine_health_report.py`: one unified report combining Strategy / Data / Execution / PnL / Trade / Statistics verification → single Overall Engine Status.
- Exception handling upgraded: every failure now shows Function, File, Line, Reason, full Stack Trace.
- Reviewed engine + multiprocessing worker for infinite loops/deadlocks/memory leaks — clean, no changes needed.
- **Full test suite: 87/87 passing.**

## Real Strategy Tests (on real BTCUSDT data, full history)
- **Liquidity Sweep & FVG Validation Strategy** — ran, found broken (exit rules duplicated entry rules → account wiped to $0 via commission churn, 2.86% win rate). Root-caused as a strategy-authoring bug, not an engine bug.
- **EMA Trend-Pullback Strategy** — built fresh, tested clean: 542 trades, 34% win rate, -77.86% PnL (genuinely unprofitable strategy, but engine behaved correctly — full Engine Health Report PASS).

## Automatic Strategy Safety Check (latest)
- New `strategy_safety_check.py` — 3 automatic checks run on every strategy before it's allowed to backtest:
  1. Duplicate entry/exit clauses.
  2. Exit conditions that give no realistic room to reach SL/TP.
  3. Logically-impossible entry conditions (contradictory AND-gates).
- Wired into: strategy save (library), every backtest entry point (`mtf_worker`, `verification_engine`), and the Strategies page UI ("Needs Review" status).
- Backfilled across all 16 existing library strategies: **11 passed, 5 flagged "Needs Review"** with exact reasons.
- Fully tested or (unit + integration tests proving backtests actually get refused).

## Status: All of the above is committed to git and working. Engine is verified, deterministic, and now self-guards against the 3 known real bug patterns automatically.
