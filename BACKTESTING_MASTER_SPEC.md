> **This is the permanent standard for the Backtesting Engine. Any future backtesting work must reference this document and must not violate any requirement in it.**

# SINDHU Backtesting Engine — Master Specification

## Mission

The Backtesting Engine's only objective is to execute every imported strategy **exactly as written**, with **scientifically correct, repeatable results**. Not to maximize win rate. No assumptions, no shortcuts, no hidden decisions during execution.

---

## Requirements Checklist

### 1. Strategy Understanding
- [ ] AI understands a strategy **exactly once**, at import time.
- [ ] Output is structured JSON (a directly machine-readable `StrategyConfig`).
- [ ] Raw text is **never re-parsed again** after import — every later read (backtest, paper trading, re-run) uses the saved structured config only.

### 2. Strategy Validation
- [ ] Before any backtest, verify entry, exit, SL, TP, RR, risk, sessions, timeframes, filters, and indicators are all complete.
- [ ] If something is missing, first try to **infer it from the strategy's own existing rules**.
- [ ] If it truly cannot be inferred, **report only the missing piece** — never guess silently and never invent a value with no basis.

### 3. Strategy Library
- [ ] Permanent storage (survives restarts) for every imported strategy.
- [ ] Full version history — every edit/re-import is a new version, nothing is overwritten or lost.

### 4. Automatic Timeframe Detection
- [ ] Bias / trend / analysis / setup / entry / confirmation / exit timeframes are detected automatically from the strategy's own text.
- [ ] Never hardcoded (e.g. never assumes entry is always 1-minute).

### 5. Data Engine
- [ ] Uses local data only where already present.
- [ ] Missing data is downloaded automatically.
- [ ] Downloaded/stored data is validated for: missing candles, duplicate candles, timezone correctness, corrupted OHLCV values.

### 6. Auto Resampling
- [ ] Any timeframe a strategy needs, that isn't natively stored, is built automatically from 1-minute data.
- [ ] No timeframe is ever downloaded/stored redundantly if it can be derived.

### 7. Multi-Timeframe Engine
- [ ] Every timeframe a strategy uses is synchronized to a single evaluation index.
- [ ] A higher timeframe's bar must be **fully closed** before its value becomes visible to a lower-timeframe evaluation at that point in time.
- [ ] Zero look-ahead bias, provable and testable.

### 8. Indicator Engine
- [ ] Only the indicators actually required by the specific strategy under test are computed/loaded — no wasted computation, no unused columns.

### 9. Rule Engine
- [ ] Every rule is executed exactly as written, on every candle, in the correct order: trend → filters → confirmation → entry → risk → trade.

### 10. Trade Execution Engine
- [ ] Market entry — genuinely implemented.
- [ ] Limit entry — genuinely implemented.
- [ ] Stop entry — genuinely implemented.
- [ ] Signal Candle High/Low entry — genuinely implemented.
- [ ] Next Candle Open entry — genuinely implemented.
- [ ] Partial Take-Profit — genuinely implemented.
- [ ] Trailing Stop — genuinely implemented.
- [ ] Break-Even stop move — genuinely implemented.
- [ ] Time-based exit — genuinely implemented.
- [ ] Every one of the above actually changes trade behavior when configured — never silently accepted and ignored.

### 11. Risk Engine
- [ ] Risk % per trade.
- [ ] Position sizing derived from risk % + stop distance.
- [ ] Commission.
- [ ] Slippage.
- [ ] Spread.
- [ ] Leverage.
- [ ] Max drawdown limit (halts trading when breached).
- [ ] Daily loss limit (halts trading when breached).
- [ ] Max open trades limit.

### 12. Backtest Validation Engine
- [ ] For every trade, verify entry price, exit price, SL, TP, RR, result (win/loss), direction, and reason are internally consistent.
- [ ] On any mismatch, print the exact reason — never a silent bad trade record.

### 13. Strategy Verification Engine
- [ ] Confirm the chain Imported Strategy → JSON → Rule Engine → Trade Execution → Trade Result all match exactly, with no divergence introduced at any step.

### 14. Reference Verification Mode
- [ ] Support comparing SINDHU's results against an external reference implementation (e.g. a Colab backtest of the same strategy/data).
- [ ] Compares: entry/exit timestamp, entry/exit price, SL, TP, trade count, win rate, PnL.
- [ ] On the first mismatch, **stop and report it** rather than continuing silently.

### 15. Trade-by-Trade Audit
- [ ] Support randomly sampling multiple trades and manually verifying each against raw candle data: signal, entry, SL, TP, exit, and outcome.

### 16. Debug Mode
- [ ] Every backtest logs each stage: Strategy Loaded → JSON Loaded → Rules Loaded → Indicators Loaded → Data Loaded → Signals Generated → Trades Executed → Results Generated.
- [ ] No silent failures — every failure surfaces at the stage it happened, with a reason.

### 17. Performance Analytics
- [ ] Win Rate
- [ ] Net Profit / Gross Profit / Gross Loss
- [ ] Profit Factor
- [ ] Expectancy
- [ ] Sharpe Ratio
- [ ] Sortino Ratio
- [ ] Calmar Ratio
- [ ] Recovery Factor
- [ ] Max Drawdown
- [ ] Equity Curve
- [ ] Monthly Returns
- [ ] Trade Duration
- [ ] MAE (Maximum Adverse Excursion)
- [ ] MFE (Maximum Favorable Excursion)

### 18. Data Quality Report
- [ ] Missing candles
- [ ] Duplicate candles
- [ ] Bad/misaligned timestamps
- [ ] Invalid OHLC (e.g. high < low, close outside high/low range)
- [ ] Resampled-candle provenance (which candles were derived, not native)

### 19. Engine Health Report
- [ ] Strategy Confidence score
- [ ] Execution Confidence score
- [ ] Engine Confidence score
- [ ] Data Confidence score
- [ ] Validation Confidence score
- [ ] Overall Reliability Score

### 20. Reliability Rules
- [ ] No look-ahead bias.
- [ ] No repainting (a signal, once generated at bar N, never changes retroactively).
- [ ] No duplicate trades.
- [ ] No impossible position sizes (negative, infinite, or exceeding available balance).
- [ ] Correct SL/TP execution (right side of entry, correct trigger price).
- [ ] Correct entry/exit price logic.
- [ ] Correct compounding behavior (matches what was configured, backtest vs. live).
- [ ] Correct fees/slippage application.
- [ ] Correct timeframe synchronization (see Requirement 7).

---

## Final Acceptance Standard

The Backtesting Engine is **not considered complete** until every one of the following is true:

🟢 Same strategy + same data = same result, every time (fully deterministic/repeatable).
🟢 Colab (or any reference implementation) and SINDHU results closely match.
🟢 Every trade can be manually verified against raw historical candles.
🟢 No hidden bug or silent failure anywhere in the engine.
🟢 Paper Trading signals closely match Backtesting signals for the same strategy and conditions.

**If there is any mismatch, the engine must report the exact point of divergence instead of silently continuing.**
