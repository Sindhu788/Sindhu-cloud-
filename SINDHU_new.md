# SINDHU — Poori Project Ki A to Z Summary

**Last updated:** 2026-07-24

---

## 1. SINDHU Kya Hai

Institutional-grade, self-learning crypto trading system. CEO (user) sirf ek strategy/lesson/PDF/YouTube link paste karta hai — SINDHU khud samajhta hai, save karta hai, backtest karta hai, aur (future) paper trading/live signals tak le jaata hai.

**Core rule:** AI sirf strategy IMPORT ke waqt ek dafa use hota hai. Uske baad backtesting/paper trading/live signals kabhi AI call nahi karte — sab already-saved structured data (StrategyConfig) se chalta hai.

---

## 2. Poore Project Ke Modules (A to Z)

| Module | Kaam |
|---|---|
| `data_engine/` | Multi-exchange (binance/okx/bybit/bitget/gate) candle data download, SQLite storage, on-the-fly resampling (1m source of truth → koi bhi timeframe) |
| `backtest_engine/` | Strategy parser, validator, multi-timeframe backtest engine, execution/PnL/risk engine, verification engine, strategy library |
| `knowledge_engine/` | CEO ke manually diye "Lessons" evaluate/apply karta hai |
| `knowledge_compiler/` | Pasted document ko Strategy + Lessons + Dictionary mein compile karta hai (deterministic, AI ke bina) |
| `ai_integration/` | AI Knowledge Learning Engine — strategy text/PDF/YouTube ko structured StrategyConfig mein todta hai |
| `paper_trading/` | 24/7 simulated live trading (decision engine, risk manager, guards) |
| `automation_pipeline/` | Import → backtest → optimize → validate pipeline, deterministic parameter optimizer |
| `evolution_engine/` | Strategy scoring/evolution |
| `strategies/` | Base Strategy/Signal interface + JSON-file Strategy Library storage |
| `sindhu_web/` | FastAPI web server, REST API, WebSocket, frontend dashboard (`localhost:8420`) |
| `dashboard/` | Purana PySide6 desktop GUI |

**Flow:** CEO paste karta hai → AI ek dafa samajhta hai → StrategyConfig banta hai → Backtesting Engine test karta hai → Paper Trading same config chalata hai → (future) Live signals.

---

## 3. Backtesting Engine — Is Session Mein Jo Kaam Hua (A to Z)

### Phase 1 — Trade Execution / PnL / Risk Engine
- Har entry type real: Market, Limit, Stop, Signal-Candle-High/Low, Next-Candle-Open.
- Partial Take Profit, Trailing Stop, Time Exit, Break-Even.
- Har trade ka pura PnL breakdown: gross PnL, commission, slippage, spread — kahin double-count nahi.
- Risk Engine: leverage, spread, daily loss limit, max drawdown circuit breaker.

### Phase 2 — Verification Engine
- `strategy_verifier.py` — proof karta hai ke strategy ka har rule engine mein genuinely use ho raha hai (SKIPPED / NEVER_TRUE / OK).
- `trade_validator.py` — har trade ka entry/exit/SL/TP/PnL/RR independently re-check karta hai.
- `verification_engine.py` — sab combine karke ek PASS/FAIL report deta hai.

### Final Audit
- **Real bug mila aur fix hua:** take-profit exits par galat slippage lag raha tha, jisse asli wins fake losses dikh rahe the. Fix ho gaya.
- Data Quality checks (missing/duplicate candles, corrupted OHLC, resampling correctness).
- Look-ahead bias proof tests (engine future data kabhi nahi dekhta — proven).
- Statistics Verifier (metrics khud se dobara calculate karke cross-check karta hai).
- Engine Health Report — Strategy + Data + Execution + PnL + Trade + Statistics, ek hi Overall Status mein.
- Har error ab Function/File/Line/Reason/Stack Trace ke saath dikhta hai.
- **Poora test suite: 87/87 pass.**

### Real Strategy Tests (Real BTCUSDT Data Par)
- **Liquidity Sweep & FVG Validation Strategy** — test kiya, tootii hui nikli (exit rules entry rules jaisi hi thi → account $0 tak wipe ho gaya). Ye strategy ki authoring mistake thi, engine ki nahi.
- **EMA Trend-Pullback Strategy** — naya banaya, clean test hua: 542 trades, 34% win rate, honest -77.86% PnL. Engine sahi kaam kar raha tha.

### Automatic Strategy Safety Check (Sabse Naya Kaam)
- Har strategy par backtest se PEHLE 3 automatic checks:
  1. Entry/Exit conditions mein duplicate clause to nahi.
  2. Exit conditions SL/TP tak pahunchne ka real chance dete hain ya nahi.
  3. Entry conditions logically impossible (contradictory) to nahi.
- Ye check har jagah wire hua: strategy save hote waqt, har backtest se pehle, aur Strategies page par "Needs Review" status dikhta hai.
- Poori library (16 strategies) re-check hui: **11 pass, 5 "Needs Review"** (exact reason ke saath).

---

## 4. Status

Backtesting Engine ab **deterministic, verified, aur self-guarding** hai — same strategy + same data = same result, har baar. Genuine bugs khud detect ho jaate hain, aur naya galat strategy backtest tak pahunch hi nahi sakta jab tak safety check pass na kare. Sab kuch git mein committed hai.
