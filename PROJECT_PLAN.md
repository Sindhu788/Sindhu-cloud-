# SINDHU Trading Bot — Project Plan

## Vision
SINDHU ek AI trading company jaisa system hai:
- **CEO** — User (Sindhu) khud.
- **Manager Agent** — CEO se seedha baat karta hai (status updates, reports, decisions).
- **Worker Agents** — Alag-alag specialized kaam karte hain (data, backtesting, strategy evolution, news, execution, telegram alerts, etc.) aur Manager ko report karte hain.

## Core Features

### 1. Dashboard
- Advanced dashboard — web-based, responsive design.
- Mobile aur laptop/PC dono par sahi se chale (single responsive web app, no separate native app needed).

### 2. Data System
- Source: Binance free public API (initial phase).
- Future: Bybit, OKX add honge (multi-exchange abstraction rakhni hogi).
- Coverage: 50 coins, 1 saal ki history, saare timeframes (1m se lekar top timeframes tak).
- Future option: aur purana historical data extend karne ka option rahega.

### 3. Backtesting Engine
- Strategy input karo → backtest chale.
- Multi-timeframe support.

### 4. Learning & Evolution
- CEO bot ko manual trading lessons dega.
- Bot khud bhi har trade ke baad apne aap se lessons seekhega (self-review loop).
- Evolution engine: strategy parameters khud test karke best combination dhoondhega.
- Naye/novel strategies bhi khud try karega (exploration).

### 5. News Monitoring
- Relevant crypto/market news check karna, trading decisions mein factor karna.

### 6. Persistence
- Saara data (market data, trades, learnings, strategy state, evolution progress) permanently save rahe.
- App band karke dobara kholo to wahin se continue ho — koi progress loss nahi.

### 7. Risk & Performance Targets
- Accha win ratio target.
- Minimum 1:2 risk-reward ratio per trade.

### 8. Telegram Alerts
- Jab kisi strategy/signal ka win ratio 60% cross kare, uske best signals Telegram par bhejna.

### 9. Paper Trading
- Shuruaat $100 virtual capital se, live/paper mode mein.

## Working Method (Rules)
1. Project **phase-by-phase** banega — ek phase complete hote hi ruk jayenge.
2. Agla phase **tabhi shuru hoga jab CEO (user) explicitly bole**.
3. Har phase ke baad status/report Manager ke through diya jayega.

## Phase Roadmap
- **Phase 1 — Data System**: 50 coins, 1 saal history, Binance API, saare timeframes, storage design jo baad mein extend ho sake.
- **Phase 2 — Backtesting Engine** *(planned)*
- **Phase 3 — Strategy & Evolution Engine** *(planned)*
- **Phase 4 — Learning/Lessons System** *(planned)*
- **Phase 5 — News Monitoring** *(planned)*
- **Phase 6 — Dashboard (Web, responsive)** *(planned)*
- **Phase 7 — Telegram Alerts** *(planned)*
- **Phase 8 — Paper Trading Execution ($100 capital)** *(planned)*
- **Phase 9 — Manager/Agent orchestration layer** *(planned)*

> Exact phase order/scope may adjust as we go — this is the current plan, confirmed with CEO before each phase starts.

## Status
- Current phase: **None started yet.**
- Waiting for CEO approval to begin **Phase 1**.
