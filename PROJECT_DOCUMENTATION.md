# SINDHU — Project Documentation (A to Z)

> **Version 3 — 2026-09-04.** Ye document sirf real code, files aur folders scan karke banaya gaya hai. Koi bhi cheez guess nahi ki gayi — agar kuch clear nahi tha to "TBD" likha hai. (V1 sirf architecture/modules tak thi, "Extraction Reliability Crisis" era tak. V2 mein Sections 14-19 add hue jo us waqt ke baad ka kaam cover karte hain. **V3 mein Section 20 naya add hua hai — "Grand Feature Expansion" jo ~110 features, 7 phases mein, ek hi lambe session mein add kiye gaye: Safety & Reliability, Telegram, Analytics & Visibility, Strategy Management & UX, Profitability Optimization, Evolution & Self-Learning, aur Infrastructure & Sync. Poori honest report `GRAND_EXPANSION_REPORT.md` mein hai — ye section sirf architectural summary deta hai.**)

---

## 1. Project ka Naam

**SINDHU** — ek institutional-grade, self-learning crypto trading system jo strategy import se lekar backtesting, paper trading aur (future mein) live signals tak sab kuch khud sambhalta hai.

One-line: *"CEO sirf ek strategy ya YouTube link paste kare — baaki sab (samajhna, extract karna, save karna, backtest-ready banana) SINDHU khud kare."*

---

## 2. Vision & Mission

Project `PROJECT_PLAN.md` (original planning doc) ke mutabiq shuruaati vision ye tha:

> "SINDHU ek AI trading company jaisa system hai — CEO (user) khud manager hai, aur alag-alag 'worker' modules (data, backtesting, strategy evolution, news, execution, telegram) specialized kaam karte hain aur report karte hain."

Jo problem ye solve karta hai:
- Trading strategies aksar kaagaz/PDF/YouTube video mein hoti hain — unhe manually code karna time-consuming aur error-prone hai.
- SINDHU chahta hai CEO sirf strategy paste kare, aur system khud:
  - Poori strategy samjhe (rules, indicators, risk, sessions, hidden logic)
  - Usse ek executable format mein convert kare
  - Backtest chalaye
  - Paper trading mein test kare
  - (Future) Live signals de

**Core mission (AI Knowledge Learning Engine se, jo `ai_integration/__init__.py` mein likha hai):**
> "AI is only a temporary teacher. SINDHU must become independent after learning. Trading Engine must never depend on AI."

Matlab: AI sirf **import ke waqt ek dafa** use hota hai. Uske baad backtesting, paper trading, aur signals kabhi AI call nahi karte — sab kuch already-saved, structured data se chalta hai.

---

## 3. Big Picture (Simple Flow)

```
CEO paste karta hai:
  Strategy TEXT  |  Lesson TEXT  |  PDF/DOCX/TXT/MD  |  YouTube Link
                    │
                    ▼
        AI Knowledge Learning Engine (ai_integration/)
        (AI ek dafa poori tarah samajhta hai — entry/exit/SL/TP/
         risk/sessions/hidden rules/lessons/dictionary terms)
                    │
                    ▼
   Directly StrategyConfig + Lesson objects bante hain
   (koi purana keyword/regex parser dobara nahi chalta —
    wo sirf tab chalta hai jab AI disabled/unavailable ho)
                    │
                    ▼
      Knowledge Compiler save karta hai:
      Strategy Library • Lesson Library • Dictionary •
      Knowledge Concepts • Knowledge Graph
                    │
                    ▼
        Backtesting Engine (multi-timeframe, resampling,
        PDH/PDL, FVG, order blocks, live progress)
                    │
                    ▼
        Paper Trading Engine (SAME compiled strategy,
        24/7 simulation, risk manager, guards)
                    │
                    ▼
        (Future) Live Signal Engine + Telegram Alerts
```

Sab kuch ek hi **Web Dashboard** (`http://localhost:8420`) se control hota hai, jo mobile aur laptop dono par chalta hai.

---

## 4. Architecture — Modules Overview

| # | Module (folder) | Kaam ek line mein |
|---|---|---|
| 1 | `data_engine/` | Multi-exchange candle data download, storage, resampling |
| 2 | `backtest_engine/` | Strategy parser, validator, multi-timeframe backtest engine, strategy library |
| 3 | `knowledge_engine/` | CEO ke manually diye gaye "Lessons" ko evaluate/apply karta hai |
| 4 | `knowledge_compiler/` | Pasted document ko samajh kar Strategy + Lessons + Dictionary mein compile karta hai (deterministic, regex/keyword based) |
| 5 | `ai_integration/` | AI Knowledge Learning Engine — AI-native structured extraction, self-building dictionary, YouTube import, provider fallback |
| 6 | `paper_trading/` | 24/7 simulated live trading engine (decision engine, risk manager, guards) |
| 7 | `strategies/` | Base `Strategy`/`Signal` interface + JSON-file-based Strategy Library storage |
| 8 | `sindhu_web/` | FastAPI web server, REST API, WebSocket, static frontend (HTML/CSS/JS) |
| 9 | `dashboard/` | Purana PySide6 desktop GUI (2 tabs: Data Engine, Backtesting) |
| 10 | `data/` | Saara persistent data — SQLite DB, config JSON files, logs, reports |

Diagram (dependency direction, upar se neeche):

```
sindhu_web (Web API + Frontend)
        │
        ├── ai_integration ───────► knowledge_compiler
        │                                  │
        ├── knowledge_compiler ────────────┤
        │                                  ▼
        ├── knowledge_engine        backtest_engine ◄── strategies
        │                                  │
        └── paper_trading ─────────────────┘
                                            │
                                     data_engine (sabse neeche — sabki base)
```

**Hard rule (code mein verified):** `ai_integration` package `backtest_engine/` ya `paper_trading/` mein KABHI import nahi hota — grep se confirm kiya gaya hai. Matlab AI trading engine ko kabhi touch nahi karta.

---

## 5. Har Module ki Detail

### 5.1 `data_engine/` — Data Layer

**Kaam kya hai:** Crypto exchanges se candle (OHLCV) data download karna, SQLite mein store karna, aur kisi bhi timeframe par resample karke dena.

**Kaise kaam karta hai:**
- **Input:** Exchange name (binance/okx/bybit/bitget/gate), symbol list, date range
- **Process:** `downloader.py` → exchange client (`exchanges/binance.py` ya `exchanges/ccxt_client.py`) se 1-minute candles fetch karta hai → `storage.py` mein `klines_1m` table mein save karta hai
- **Output:** Koi bhi timeframe (5m/15m/1h/4h/1d...) `resample.py:get_ohlcv()` se turant ban jata hai — 1-minute data hi "source of truth" hai, baaki sab on-the-fly resample hota hai

**Files involved:**
- `binance_client.py`, `coingecko_client.py` — direct API clients
- `exchanges/base.py` — abstract `ExchangeClient` interface
- `exchanges/binance.py`, `exchanges/ccxt_client.py` — actual implementations
- `exchanges/registry.py` — supported exchanges: `binance` + ccxt ke through `okx`, `bybit`, `bitget`, `gate`
- `downloader.py`, `symbols.py` — top-N coin selection + bulk download
- `storage.py` — poora SQLite schema (24 tables — neeche list hai)
- `resample.py` — on-the-fly resampling (1m → koi bhi timeframe)
- `config.py` — saari settings JSON files se load karta hai
- `paths.py`, `control.py`, `logging_setup.py` — helper utilities

**Verified defaults (runtime se check kiya):**
- `DEFAULT_EXCHANGE = "binance"`
- `NUM_COINS = 50`
- `HISTORY_DAYS = 364`
- `SUPPORTED_INTERVALS = ['1m','3m','5m','15m','30m','1h','2h','4h','6h','12h','1d','1w']`

---

### 5.2 `backtest_engine/` — Backtesting Engine

**Kaam kya hai:** Ek structured `StrategyConfig` ko lekar historical data par simulate karna aur trades/metrics nikalna.

**Kaise kaam karta hai:**
- **Input:** `StrategyConfig` (structured, kabhi raw text/JSON nahi — ye hard rule hai)
- **Process:**
  1. `strategy_parser.py` — bilingual (English + Roman Urdu) regex/keyword parser jo raw text ko `StrategyConfig` mein todta hai (sirf tab chalta hai jab AI use nahi ho raha)
  2. `validator.py` — check karta hai ke config safe hai ya nahi (missing SL/TP/risk/entry/exit)
  3. `mtf_context.py` (`MultiTimeframeContext`) — multiple timeframes (bias/trend/analysis/entry/confirmation) ko ek entry-timeframe index par sync karta hai, zero look-ahead ke saath
  4. `configured_strategy.py` (`ConfiguredStrategy`) — config ko concepts.py ke indicators/patterns se jod kar executable bana deta hai
  5. `engine.py` — bar-by-bar simulation chalata hai, trades generate karta hai
  6. `metrics.py` — win rate, profit factor, drawdown, Sharpe ratio, etc. calculate karta hai
  7. `mtf_worker.py` + `runner.py` — ek symbol/multiple symbols ke liye poora pipeline chalate hain, live progress report karte hain
- **Output:** Trades list, equity curve, metrics, condition-hit report (agar 0 trades aayen to kaunsa rule fail hua wo batata hai)

**Files involved:** `strategy_config.py` (schema), `strategy_parser.py`, `validator.py`, `concepts.py` (indicators: EMA/SMA/RSI/MACD/ATR/Volume + patterns: BOS/CHoCH/FVG/Order Block/Breaker/Liquidity Sweep/PDH-PDL), `configured_strategy.py`, `engine.py`, `metrics.py`, `mtf_context.py`, `mtf_worker.py`, `runner.py`, `queue_runner.py`, `strategy_library.py` (JSON-file storage), `strategy_loader.py`, `diagnostics.py`, `export.py`, `reports.py`

**Important detail:** Strategy Library **SQLite mein nahi, JSON files mein** save hoti hai — `strategies/library/<strategy_id>/meta.json` + `versions/` folder (version history ke liye).

**v8 Debug Mode (naya):** Har backtest ab 11 named stages emit karta hai (`strategy_loaded → strategy_compiled → timeframes_detected → historical_data_loading → timeframes_resampled → timeframes_synchronized → indicators_initialized → rules_loaded → simulating_bars → trades_executed → results_generated → completed`), aur koi bhi failure `{stage, function, reason, suggested_fix}` ke saath report hoti hai — kabhi silent crash nahi.

---

### 5.3 `knowledge_engine/` — CEO Lessons Engine

**Kaam kya hai:** CEO khud jo "Lessons" (trading tips/rules) type karta hai, unhe backtesting/paper trading mein automatically apply karna.

**Kaise kaam karta hai:** Lesson ka description text `strategy_parser.parse_conditions()` se ek real condition mein convert hota hai (agar possible ho). Phir har trade se pehle check hota hai ke koi active lesson us trade ko veto/require to nahi karti.

**Files:** `lesson.py` (Lesson model), `engine.py` (`KnowledgeEngine.for_backtesting()`/`for_paper_trading()`), `condition_eval.py`, `scoring.py` (Knowledge Score)

---

### 5.4 `knowledge_compiler/` — Deterministic Document Compiler

**Kaam kya hai:** Ek pasted document (strategy/lesson/mixed) ko classify, section-detect, aur extract karke Strategy + Lessons mein compile karna — **bina AI ke, pure keyword/regex logic se**.

**Kaise kaam karta hai:**
1. `classifier.py` — doc_type decide karta hai (STRATEGY/LESSON/MIXED/PSYCHOLOGY/RISK/etc.) keyword scoring se
2. `sections.py` — headers detect karta hai (Entry Rules, Exit Rules, Risk, Psychology, etc.)
3. `dictionary.py` — built-in trading terms ka canonical dictionary (BOS, CHoCH, FVG, Order Block, PDH/PDL, sessions, etc.)
4. `rule_extractor.py` → `backtest_engine.strategy_parser` ko call karta hai
5. `lesson_extractor.py` — lesson-worthy bullets nikalta hai
6. `compiler_validator.py` — safe defaults fill karta hai (missing risk% → 1%, missing entry timeframe → similar strategy se borrow, etc.) — lekin **stop-loss kabhi khud se invent nahi karta** (safety-critical)
7. `quality.py` — duplicate detection (DNA fingerprint), conflict detection, tags
8. `compiler.py` — sab kuch orchestrate karta hai, do entry points hain:
   - `compile_document()` — text-based (old) pipeline — **sirf Offline Mode mein chalta hai** (jab AI disabled ho)
   - `compile_from_ai_extraction()` — AI se already-built `StrategyConfig`/`Lesson` objects ko save karta hai — **AI ka output kabhi wapas is old parser mein nahi jaata**

**Ye module purane aur naye (AI) dono pipelines ke liye "save/dedupe/version" ka shared logic hai.**

---

### 5.5 `ai_integration/` — AI Knowledge Learning Engine (v6→v7→v8)

**Kaam kya hai:** AI ko **sirf import ke waqt** use karke strategy/lesson ko poori tarah samajhna aur directly executable structure mein convert karna.

**Kaise kaam karta hai (poora pipeline):**
1. User paste karta hai text, file (PDF/DOCX/TXT/MD) upload karta hai, ya YouTube link deta hai
2. `youtube_import.py` — YouTube URL se transcript nikalta hai (via `youtube-transcript-api`), noise (filler words, ♪ symbols) clean karta hai
3. `file_extractors.py` — PDF (`pypdf`)/DOCX (`python-docx`) se text nikalta hai
4. **Pre-AI Dedup Cache (v8, naya):** Content ka hash check hota hai `ai_import_cache` table mein — agar same document pehle already AI se samjha ja chuka hai, to AI **dobara call hi nahi hoti**, cached structured result reuse hota hai
5. `chunking.py` — bade documents ko ~6000-token chunks mein todta hai (overlap ke saath)
6. `deep_understanding.py` — Smart Provider Switching chain chalata hai: CEO ka active provider → Claude → Groq → OpenAI → Gemini → DeepSeek → sab fail ho jayen to Offline Mode
7. `schema.py` — AI ko exact JSON contract deta hai (sirf backtest engine ki known vocabulary use karne ko kaha jata hai: 18 indicators/concepts, 3 sessions, etc.) — invalid JSON repair bhi karta hai (control-character escaping)
8. `strategy_builder.py` — AI ke JSON output ko directly real `StrategyConfig`/`Condition`/`Lesson` objects mein banata hai — koi unknown vocabulary condition ko `type="raw"` (safe fallback) mein demote kar deta hai
9. `dictionary_builder.py` — naye trading terms (BOS, CHoCH, SMT, AMD, etc.) `ai_dictionary_entries` table mein permanently save karta hai (definition, aliases, examples, related concepts, usage, source ke saath)
10. `importer.py` — sab kuch orchestrate karta hai, aur `knowledge_compiler.compile_from_ai_extraction()` ko call karke save karta hai

**Confidence Gate (v8):** Agar AI ka confidence **60% ya usse zyada** hai, to "Needs Clarification" kabhi nahi dikhaya jata — strategy directly Automation Ready + Backtesting Ready ban jaati hai. 60% se kam confidence par hi clarification dikhti hai.

**Files:** `config.py` (provider settings — API key/model/temperature/etc., `data/config/ai_settings.json` mein persist), `providers.py` (5 provider clients: Claude, Groq, OpenAI, Gemini, DeepSeek), `schema.py`, `strategy_builder.py`, `deep_understanding.py`, `chunking.py`, `dictionary_builder.py`, `file_extractors.py`, `youtube_import.py`, `import_queue.py` (background queue worker), `quality_score.py`, `importer.py`

**Important:** `ai_integration/__init__.py` mein explicitly likha hai: is package ko `backtest_engine`, `paper_trading`, ya kisi bhi engine module mein import nahi hona chahiye — is baat ko is poore session mein baar-baar grep se verify kiya gaya hai (zero matches).

---

### 5.6 `paper_trading/` — 24/7 Simulated Trading Engine

**Kaam kya hai:** Saved strategies ko real-time (simulated) market data par chalana, bina AI ke, bina text-parsing ke — **wahi compiled `StrategyConfig`/`ConfiguredStrategy` use karta hai jo Backtesting use karta hai**.

**Kaise kaam karta hai:**
1. `coin_filter.py` — relevant coins shortlist karta hai
2. `live_feed.py` — fresh candles fetch karta hai
3. `market_state.py` — market state/event triggers detect karta hai
4. `strategy_matcher.py` + `lesson_matcher.py` — kaunsi strategy/lesson is market state par apply hoti hai
5. `signal_generator.py` — Decision Engine (`ConfiguredStrategy(cfg)` seedha strategy_library se load karke banata hai)
6. `confidence.py` + `risk_manager.py` — position sizing, risk checks
7. `guards.py` — Position Lock, Duplicate Protection, Trade Reservation, Cooldown, Opposite Signal Protection
8. `position_manager.py` — positions open/monitor/close karta hai
9. `reflection.py` + `evolution.py` — har trade ke baad seekhna (internal, standalone page nahi hai abhi)
10. `engine.py` — sab kuch orchestrate karta hai, 24/7 background loop

**Verified fact:** `signal_generator.py` mein seedha `ConfiguredStrategy(cfg)` banaya jata hai — koi AI ya text-parser call nahi hota runtime par.

---

### 5.7 `strategies/` — Base Framework

**Kaam:** `base.py` mein `Strategy` aur `Signal` ka abstract interface hai jise `ConfiguredStrategy` implement karta hai. `library/` folder mein actual saved strategies JSON files ke roop mein hain (per-strategy `meta.json` + `versions/`).

---

### 5.8 `sindhu_web/` — Web Server + Dashboard

**Kaam kya hai:** FastAPI based web server jo pura dashboard serve karta hai — `http://localhost:8420` par.

**Kaise kaam karta hai:**
- `server.py` — FastAPI app banata hai, saare `api/*.py` routers ko `include_router()` se register karta hai, security middleware lagata hai, browser auto-open karta hai
- `security.py` — LAN-only token guard (`X-Sindhu-Token` header) — GET requests free hain, POST/state-changing requests token maangte hain
- `api/` folder — 15+ router files, har ek ek page/feature ke liye (home, market, data, backtesting, reports, knowledge, knowledge_compiler, ai_integration, paper_trading, settings, backup, system, search, activity, network, jobs, ws)
- `sync.py` + `broadcast.py` — WebSocket ke through real-time activity notify karta hai (`sync.notify(...)`)
- `jobs/job_manager.py` — background jobs (in-memory) track karta hai
- `cache.py` — server-side caching + clear-all
- `static/` — poora frontend: `index.html` (shell), `app.js` (single-page-app logic, saare pages), `app.css` (design system)

**Frontend pages (nav se, verified):** Dashboard (Home), Market, Data, Strategies, Knowledge, Knowledge Compiler, AI Center, Backtesting, Paper Trading, Reports, Settings — **enabled**. Reflection, Evolution, News, Telegram — **disabled** (nav mein hain but pages nahi banaye gaye).

---

### 5.9 `dashboard/` — Desktop App (PySide6)

**Kaam:** Purana desktop GUI, `main.py` se chalta hai. Sirf **2 tabs** hain: "Data Engine" aur "Backtesting" (`main_window.py` se verified). Web dashboard hi actively develop ho raha hai — desktop app basic/legacy hai.

**Files:** `main_window.py`, `backtest_tab.py`, `backtest_worker.py`, `mtf_backtest_worker.py`, `queue_worker.py`, `rankings_tab.py`, `settings_dialog.py`, `strategy_builder_tab.py`, `strategy_library_tab.py`, `trade_history_tab.py`, `trade_replay_dialog.py`, `candlestick_item.py`, `worker.py`

---

## 6. Tech Stack

| Category | Kya use hua |
|---|---|
| Language | Python (backend + desktop GUI), JavaScript (frontend, vanilla — koi framework nahi) |
| Web Framework | FastAPI + `uvicorn[standard]` |
| Desktop GUI | PySide6 (Qt) |
| Database | SQLite (`data/database/sindhu.db`) — single file, WAL mode |
| Data/Charts | pandas, pyqtgraph (desktop candlestick charts) |
| Exchange Data | `ccxt` (multi-exchange) + direct Binance client |
| Documents | `pypdf` (PDF), `python-docx` (DOCX), `python-multipart` (file upload) |
| YouTube | `youtube-transcript-api` |
| Export | `openpyxl` (Excel), `reportlab` (PDF reports) |
| AI Providers | Claude (Anthropic), Groq, OpenAI, Gemini, DeepSeek — sab REST API calls (`requests` library se, koi official SDK nahi) |
| Frontend | Plain HTML/CSS/JS, WebSocket for live updates, no build step |
| Other | `qrcode` (mobile QR access), `psutil` (system stats) |

**Note:** `requirements.txt` mein koi version pin nahi hai (sirf package names) — TBD ke liye ye ek gap hai agar reproducible builds chahiye.

---

## 7. Data Flow

```
Candle Data:
Exchange API → downloader.py → storage.klines_1m (SQLite, 1-minute only)
                                        │
                          resample.py:get_ohlcv() → koi bhi timeframe (on the fly)

Strategy Data:
Pasted text/YouTube/File → ai_integration (ya rule-based parser)
                                        │
                          knowledge_compiler.compiler
                                        │
                    ┌───────────────────┼──────────────────────┐
                    ▼                   ▼                      ▼
          strategies/library/*.json   lessons table (SQLite)   ai_dictionary_entries,
          (Strategy Library)                                    knowledge_concepts,
                                                                  compiled_documents (SQLite)

Backtest Data:
Strategy Library (JSON) + klines_1m (SQLite) → backtest_engine
                                        │
                        backtest_results, backtest_trades,
                        backtest_condition_reports (SQLite)

Paper Trading Data:
Strategy Library (JSON) → paper_trading engine
                                        │
                    paper_positions, paper_decision_log,
                    paper_strategy_performance (SQLite)

Settings/Config:
data/config/*.json (ai_settings, app_settings, exchanges, coins,
timeframes, paper_trading_settings, backup_settings, web_settings, api_token)
```

**Database:** ek hi SQLite file — `data/database/sindhu.db` (24 tables, verified: `activity_log`, `ai_dictionary_entries`, `ai_import_cache`, `ai_import_queue`, `ai_usage_log`, `backtest_batches`, `backtest_condition_reports`, `backtest_results`, `backtest_trades`, `compiled_documents`, `download_progress`, `klines_1m`, `knowledge_concepts`, `knowledge_relationships`, `lesson_applications`, `lessons`, `paper_decision_log`, `paper_lesson_performance`, `paper_positions`, `paper_strategy_config`, `paper_strategy_performance`, `sqlite_sequence`, `strategies`, `symbols`).

Desktop app aur Web app **dono same database** safely share karte hain (WAL mode ki wajah se).

---

## 8. Phases Status

| Phase | Naam | Status | Kya complete hua |
|---|---|---|---|
| 1 | Data System | ✅ Complete | Multi-exchange download engine, SQLite storage, desktop dashboard |
| 2 | Backtesting Engine (single-timeframe) | ✅ Complete | Basic backtest engine + metrics |
| 2.1 | Professional Backtesting Update | ✅ Complete | Multi-timeframe, bilingual parser, Strategy Library |
| 3 | Professional Dashboard + Web Interface | ✅ Complete | FastAPI web server, responsive frontend |
| 4 | Knowledge Engine | ✅ Complete | CEO lessons system, backtesting mein wired |
| 4.5 | Remote Control, Mobile Access, Real-Time Sync | ✅ Complete | LAN security, WebSocket sync, mobile QR access |
| - | Dashboard Professional Redesign | ✅ Complete | Poora UI/UX overhaul |
| 5 | Paper Trading Engine | ✅ Complete | 24/7 simulation engine, risk manager, guards |
| - | Knowledge Compiler | ✅ Complete | Deterministic strategy/lesson compiler |
| 6 | Backtesting Fix + Update | ✅ Complete | Live progress, PDH/PDL, FVG, versioning |
| 7 | AI Knowledge Import Center (v1+v2) | ✅ Complete | Multi-provider AI import, self-building dictionary |
| v6 | AI Knowledge Learning Engine | ✅ Complete | Deep understanding, hidden rule detection, YouTube import |
| v7 | AI-Native Structured Extraction | ✅ Complete | AI seedha StrategyConfig banata hai, old parser sirf offline mode mein |
| v8 | Final Architecture Upgrade | ✅ Complete | Confidence gate (60%), pre-AI dedup cache, Debug Mode diagnostics |
| 7A | Evolution Core Engine + SINDHU Strategy Generator | ✅ Complete | `evolution_engine/` (Governor, Champion Engine, 100-trade gate + auto-rollback), `sindhu_strategy/` (11 daily candidates) |
| 8 | **Grand Feature Expansion (~110 features, 7 phases)** | ✅ Complete | Safety & Reliability, Telegram, Analytics & Visibility, Strategy Management & UX, Profitability Optimization, Evolution & Self-Learning, Infrastructure & Sync — poori detail Section 20 mein |

**Agla milestone:** Grand Feature Expansion ke andar hi 4 items CEO ke faisle par rukay hue hain (Section 20.8 dekhein — Emergency Contact Alert, Chart Attachment, Mobile Push Notifications, aur 3 execution-gate items jo ek grouped decision hain). In sab ka jawab milte hi wo bhi build ho sakte hain. Uske baad agla phase abhi define nahi hua.

---

## 9. How to Run

```bash
# Dependencies install karo
pip install -r requirements.txt

# Desktop app (PySide6 GUI)
python main.py

# Web dashboard (asli/main interface) — browser khud khul jayega
python web_main.py
# → http://localhost:8420

# CLI (headless data download)
python run.py download --exchange binance
python run.py status
python run.py watch --exchange binance
```

Web aur Desktop dono ek hi database (`data/database/sindhu.db`) use karte hain — dono ek saath chal sakte hain.

---

## 10. Folder Structure

```
E:\sindhu\
├── main.py                    # Desktop app entry point
├── web_main.py                 # Web dashboard entry point
├── run.py                      # CLI entry point
├── requirements.txt
├── PROGRESS.md                 # Phase-by-phase build log (maintained through session)
├── PROJECT_PLAN.md             # Original vision/roadmap (Phase 1 se pehle likha gaya)
├── PROJECT_FULL_DOCUMENTATION.md  # Purani English documentation (AI Center se pehle ki, ab outdated)
├── PROJECT_DOCUMENTATION.md    # Ye document
│
├── data_engine/                # Data layer
│   └── exchanges/              # Multi-exchange clients
├── backtest_engine/             # Backtesting + Strategy Library + parser
├── knowledge_engine/            # CEO Lessons engine
├── knowledge_compiler/          # Deterministic document compiler
├── ai_integration/               # AI Knowledge Learning Engine
├── paper_trading/                # 24/7 simulation engine
├── automation_pipeline/          # Auto backtest -> optimize -> compare -> paper trading handoff
├── evolution_engine/              # Phase 7A Part A -- Evolution Core Engine (BOT strategy/lesson generations, Governor, Champion Engine; zero AI)
├── sindhu_strategy/                # Phase 7A Part B -- SINDHU Strategy Generator (11 daily candidates, 1 AI + 10 deterministic)
├── strategies/
│   └── library/                 # Saved strategies (JSON files, per-ID folders) -- USER-owned only; BOT-owned strategies live in SQLite (bot_strategies table), never here
├── sindhu_web/                   # Web server + frontend
│   ├── api/                      # REST API routers
│   ├── jobs/
│   └── static/                   # index.html, app.js, app.css
├── dashboard/                     # Desktop PySide6 GUI
│
└── data/                          # Saara persistent data
    ├── database/sindhu.db          # Main SQLite DB (single source of truth)
    ├── config/                     # Settings JSON files (ai_settings, exchanges, coins, etc.)
    ├── logs/                       # sindhu.log, download_console.log
    ├── reports/                    # Exported batch reports (per batch-id folder)
    ├── history/                    # sessions.jsonl
    ├── settings/                   # (currently empty)
    └── market_data/                # (currently empty)
```

---

## 11. Future Roadmap

**Update (Grand Feature Expansion ke baad, Section 20 dekhein):** Neeche ki list mein se **Telegram Alerts ab fully bana hua hai** (real-time signals, weekly/monthly/evolution/infra digests, incoming bot commands, multi-channel routing, silent hours — Section 20.2/20.7 dekhein) — is item ko is list se hata diya gaya hai. Baaki sab abhi bhi waisi hi hai jaisi thi:

- **Reflection** — standalone dashboard page (abhi Paper Trading ke andar internal hai; Evolution ab standalone hai, Phase 7A mein bana)
- **News Monitoring** — bilkul nahi bana (nav mein disabled entry hai)
- **Live/Real Trading Execution** — Paper Trading simulation-only hai, real order execution nahi
- **Local LLM Provider** — `ai_integration/config.py` mein sirf mention hai, koi actual local LLM runtime connect nahi hai
- **Manager/Agent orchestration layer** — original `PROJECT_PLAN.md` ka Phase 9 idea, abhi tak nahi bana
- **Mobile Push Notifications** — CEO ke faisle par ruka hua (Section 20.8 dekhein: naya Python dependency ya third-party service, dono options)

---

## 12. Known Issues / TODO

**Current reality (2026-08-26 se, Grand Feature Expansion ke baad updates saath mein):**

1. Paper Trading ka activation status yahan assert nahi kiya ja raha (ye CEO ka apna operational decision hai, code se guess nahi kiya ja sakta) — lekin Grand Feature Expansion mein Paper Trading ke upar bohot saara naya safety/risk infrastructure bana hai (Kill Switch, Account-Wide Drawdown Circuit-Breaker, Coin Blacklist, Time-of-Day Filter, Slippage-Aware Filter, Profit-Lock Trailing Stop, Ensemble Voting — Section 20.1/20.5 dekhein), jo isay real trading ke zyada qareeb le aata hai.
2. **DCA / multi-entry averaging engine gap** — abhi tak fix nahi hua, jaan-boojh kar excluded (Section 16, gap #14 dekhein). Engine ek trade mein sirf EK entry support karta hai; kisi bhi strategy ka "DCA entry" wala hissa isliye represent nahi ho sakta.
3. **Concepts Library abhi 12 of 22 (55%) complete hai** — 10 concepts abhi "not yet defined" hain (Equal Highs/Lows, Previous High/Low, Premium & Discount, aur Candlestick Patterns category ke 7 baaki: Inverted Hammer, Hanging Man, Spinning Top, Tweezer Top/Bottom, Three White Soldiers, Three Black Crows).
4. **Telegram Alerts ab fully bana hua hai** (real-time signals, weekly/monthly/evolution/infra digests, incoming commands, multi-channel routing — Section 20.2/20.7 dekhein), lekin **VPS deployment abhi bhi nahi hui** — poora system sirf local machine (`localhost:8420`) par chalta hai (ek separate `cloud_runtime/app.py` cloud entrypoint zaroor bana hai, Section 20.7 dekhein, lekin poore system ka permanent 24/7 VPS move abhi nahi hua).
5. `requirements.txt` mein package versions pin nahi hain — reproducibility ke liye risk.
6. Project ab **git repository hai** (ye Section pehle "git nahi hai" kehta tha — ab commit history available hai).
7. `data/settings/` aur `data/market_data/` folders bane hue hain lekin currently empty/unused (TBD — future use ke liye reserved lagte hain).
8. Strategy Library do jagah track hoti hai: `strategies/library/*.json` (asli USER-owned config) aur SQLite ka `bot_strategies` table (BOT-owned lineages, `evolution_engine`/`sindhu_strategy` se) — dono completely separate systems hain, dono ka scope ab clear hai (Section 20.6 dekhein).
9. Desktop app (`dashboard/`) sirf 2 tabs tak limited hai — poori tarah web dashboard ke feature-parity mein nahi hai (jaan-boojh kar, kyunki web hi primary interface hai).
10. **Mobile Push Notifications** — CEO ke faisle par ruka hua, do options hain (Section 20.8 dekhein).
11. **3 execution-gate items** (Correlation-Aware Position Limiting, Dynamic Confidence Threshold, Regime-Aware Strategy Switching) — code mein pehle se likha hua hai ke ye teeno "kabhi trade block nahi karte" (ek jaan-boojh kar liya gaya design decision), isay palatna CEO ka faisla hai, khud-ba-khud nahi kiya gaya (Section 20.8 dekhein).

---

## 14. Strategy Library — Current State (18 Strategies)

Sab 18 strategies **direct-manual-construction** se banayi gayi hain (koi `strategy_parser.py`/`ai_integration/` use nahi hua — seedha Python mein `StrategyConfig` objects banaye gaye), aur sab ka real 50-coin backtest ho chuka hai. Sirf **4 genuinely profitable** hain (Profit Factor > 1.0) — baaki 14 losing hain. Neeche PF ke hisaab se descending order mein, jaisa Compare page par bhi dikhta hai:

| Strategy | Trades | Win Rate | Net PnL | Profit Factor | Worst Drawdown | Verdict |
|---|---|---|---|---|---|---|
| Richard Dennis Turtle Trader | 1,376 | 6.83% | +$57,909.27 | **1.2596** | 83.46% | ✅ Profitable |
| Liquidity Sweep Reversal | 4,159 | 39.72% | +$39,901.06 | **1.1939** | 91.54% | ✅ Profitable |
| Candlestick Pattern Reversal | 3,755 | 31.19% | +$28,415.73 | **1.1435** | 93.88% | ✅ Profitable |
| Support/Resistance Breakout | 4,479 | 39.03% | +$14,333.28 | **1.0548** | 89.33% | ✅ Profitable |
| Dumb Money Concepts — Confirmation Entry | 1,602 | 29.15% | -$619.33 | 0.9501 | 53.80% | Losing |
| Dumb Money Concepts — Combined Confirmation | 1,867 | 28.76% | -$1,807.51 | 0.8764 | 64.44% | Losing |
| Double Confirmation CHoCH with Liquidity Trap | 8,011 | 26.26% | -$34,526.92 | 0.8726 | 98.88% | Losing |
| Supply/Demand Zone | 193 | 37.31% | -$1,879.05 | 0.8626 | 7.43% | Losing |
| SMA-Alignment (Approximate) | 3,287 | 37.91% | -$32,557.38 | 0.8386 | 27.75% | Losing |
| Asian Range London Sweep | 3,688 | 34.25% | -$46,220.23 | 0.8316 | 39.40% | Losing |
| 9-20 EMA SMC Hybrid | 771 | 36.19% | -$10,749.76 | 0.8171 | 27.54% | Losing |
| 4-Hour Range Breakout-Retest | 15,361 | 33.33% | -$210,781.99 | 0.8097 | 92.67% | Losing |
| Dumb Money Concepts — Blind Entry | 2,632 | 23.67% | -$4,153.17 | 0.8064 | 72.75% | Losing |
| Laxman Rekha 5-EMA Trigger-Candle | 11,353 | 22.58% | -$16,599.74 | 0.8059 | 94.21% | Losing |
| Kotegawa Bear Market Reversal | 5,581 | 23.13% | -$92,069.01 | 0.7988 | 57.99% | Losing |
| Daily Liquidity Scalping | 48,947 | 46.07% | -$350,200.55 | 0.7853 | 99.93% | Losing |
| Lower TF Liquidity Reversal | 14,248 | 32.74% | -$231,294.03 | 0.7694 | 89.65% | Losing |
| Candle Range Theory (CRT) 2.0 | 42,013 | 33.74% | -$421,921.95 | 0.7329 | 98.29% | Losing |

**Aggregate**: 172,323 total trades, trade-weighted win rate 35.81%, aggregate net PnL -$1,308,861. Yeh sab `/api/strategy-summary` (Home dashboard) aur `/api/compare-strategies` (Compare page) dono live compute karte hain — kahin bhi hardcode nahi.

---

## 15. Dual Take-Profit Experiment (Fixed 1:2 TP Test)

**Kya test kiya gaya:** Upar wali 16 ORIGINAL strategies (2 DMC variants — Blind Entry aur Combined — is experiment mein shamil nahi thin, wo khud baad mein alag se banayi gayin) ka ek-ek "draft" copy banaya gaya jismein SIRF take-profit rule badla gaya — fixed 1:2 risk-reward se — baaki sab (entries, stop-loss, filters, timeframes) bilkul wahi rakha gaya. Har draft ka real 50-coin backtest chalaya gaya aur original ke saath compare kiya gaya.

**Sabse zaroori finding:** Jo 4 strategies pehle se genuinely profitable thin, **un SAB ki performance 1:2 TP ke saath gir gayi** — Turtle Trader 1.2596→0.8265, Liquidity Sweep Reversal 1.1939→0.8213, Candlestick Pattern Reversal 1.1435→0.7493, Support/Resistance Breakout 1.0548→0.8202. Matlab: unka original TP logic (structure-based ya wider fixed RR) **already achhe se tuned tha** — usse chhota/generic 1:2 kar dene se winners jald cut ho gaye. Sirf 2 pehle-se-losing strategies 1:2 TP ke saath profitable ban paayin (DMC Confirmation Entry 0.9501→1.1349, Supply/Demand Zone 0.8626→1.0153 — yeh dusri wali sirf 70 trades ke saath, bharosemand nahi). 5 strategies ka original TP already 1:2 tha, isliye unka "variant" mathematically identical raha.

**Yeh drafts kahan milte hain:** Sab 16 draft variants `archived` strategy entries ke tor par save hain (naam ke aakhir mein "— Fixed 1:2 TP variant"). Ye **main Compare/Dashboard totals mein count NAHI hote** (dono jagah `archived` flag check karke exclude kiya jata hai) — sirf Compare page ke apne dedicated "Take-Profit Comparison" section mein dikhte hain, taake original aur 1:2 version dono independently viewable rahein bina main leaderboard ko confuse kiye.

---

## 16. Engine Gaps Found & Fixed (Poore Session Mein)

`ENGINE_GAP_TRACKER.md` (root folder mein) is sab ka permanent, append-only record hai. Summary:

| # | Gap | Status |
|---|---|---|
| 1 | VWAP indicator declared tha lekin kabhi wire nahi hua tha (0 trades hamesha) | ✅ Fixed |
| 2 | `take_profit.type == "structure"` ka koi implementation hi nahi tha (TP hamesha NULL) | ✅ Fixed |
| 3 | Bare PDH/PDL condition sirf "level defined hai ya nahi" check karta tha, "price uske upar/neeche hai ya nahi" nahi | ✅ Fixed |
| 4 | MACD listed tha lekin indicator loop mein kabhi call nahi hota tha | ✅ Fixed |
| 5 | Koi sequential/event-ordering primitive nahi tha ("A ke BAAD B hua" — sirf "dono kabhi hue" check hota tha) | ✅ Fixed — `sequential_event()` naya primitive bana |
| 6 | Stop-loss buffer default (0.15%) real transaction cost se bhi chhota tha — stops sirf fees/slippage se hit ho jaate the | ✅ Fixed (policy) — naya minimum 2-3x real cost |
| 7 | Exit conditions mein direction-awareness nahi thi (long/short dono ke liye same exit rule) | ✅ Fixed — `exit_direction` field add hua |
| 8 | ATR-based SL/TP hamesha hardcoded ATR(14) read karta tha, chahe strategy ne ATR(20) maanga ho | ✅ Fixed — `atr_period` field add hua |
| 9 | `candle_body_pct` sirf minimum threshold support karta tha, maximum (exhaustion candle) nahi | ✅ Fixed |
| 10 | 1-minute timeframe hardcoding — check kiya gaya, koi real gap nahi mila | Not a real gap |
| 12 | Structural trailing stop-loss (swing-level tak trail karna) — sirf %/ATR-distance trailing hi supported hai | **Not fixed — excluded** (core execution loop change chahiye, scope se bahar) |
| 11 | Per-day categorical trade-outcome counter ("max 2 full SL per din") | **Not fixed — excluded** (cross-trade state chahiye, scope se bahar) |
| 13 | `_within()` helper `NaN` ko truthy treat karta tha role-merged columns par — backtest ke shuruaati bars mein galat trades khol sakta tha | ✅ Fixed — kam se kam 9 purani strategies ke liye bhi genuine correctness improvement |
| 14 | DCA/multi-entry position averaging — engine sirf single-entry-per-trade support karta hai | **Not fixed — excluded**, abhi bhi khula gap (Section 12 dekhein) |

**Sirf gap #14 (DCA) abhi bhi genuinely open hai** — baaki sab ya to fix ho chuke hain, ya jaan-boojh kar scope-se-bahar excluded hain (documented, fake approximation nahi banaya gaya).

---

## 17. Naye Pages/Features (Is Session Mein Bane)

- **Concepts Library** (`/concepts` — abhi tak sidebar mein direct link nahi hai, sirf URL se pahunch) — 12 of 22 concepts (55%) fully detailed hain, Learning Score aur "What's Next" roadmap dono live data se compute hote hain.
- **Compare page** (`/#compare`) — sab strategies ek saath, original vs current PF, aur ab ek dedicated "Take-Profit Comparison — Original vs Fixed 1:2" section bhi.
- **Live Logs page** (`/#live_logs`) — running/queued/recently-completed jobs, real-time activity log.
- **Project Status page** (`/#project_status`) — changelog, pending items, engine-gap counts, sab live-computed.
- **Automation Pipeline / Optimizer work** — auto backtest → optimize → compare → paper trading handoff (`automation_pipeline/`), 9 strategies ka tuning pass already chal chuka hai (Compare page par "Tuning change" notes dikhte hain).
- **Aggregate Dashboard section** (Home page ka hissa, `/api/strategy-summary` se) — Total Strategies, Genuinely Profitable count, trade-weighted Aggregate Win Rate, Aggregate Net PnL, Best/Worst Performer — sab Compare page ke sath exact same data source share karte hain.

---

## 18. Storage / Infrastructure Work

- **Backup cleanup**: 4 purane backup `.db` files delete kiye gaye, sirf sabse latest (`sindhu_20260824_233936.db`) rakha gaya — E: drive par **~46.58GB free space wapas mili**.
- **Current database size**: `data/database/sindhu.db` = **10.38 GB** (live verified). Backups folder bhi ab sirf 10.38 GB (1 file).
- **E: drive free space**: ~126 GB (live verified).

---

## 20. Grand Feature Expansion (~110 Features, 7 Phases)

Ek lamba, single continuous session mein SINDHU ke upar ~110 candidate features ki ek list check ki gayi — 7 phases mein organize ki gayi, ek phase poora khatam karke agle par jaana. Har phase se pehle ek dedicated audit (Explore-agent se) chalayi gayi taake koi bhi cheez jo pehle se maujood ho, dobara na banai jaye — is discipline ki wajah se **33 items "already exists" nikle aur dobara nahi banaye gaye**, sirf unka reason record kiya gaya. Poori honest, evidence-based report `GRAND_EXPANSION_REPORT.md` mein hai (har feature ka status, evidence, test count) — ye section sirf ek architectural overview deta hai.

**Overall tally: 110 candidate items → 71 genuinely naye banaye, 33 pehle se maujood the (dobara nahi banaye), 6 CEO ke faisle par rukay hue hain.**

Non-negotiable rules jo poore session mein follow ki gayin: koi bhi existing safety gate (Wilson 25-trade, Evolution 100-trade, rollback, Confluence, Signal Freshness, Incomplete Lock, per-strategy 5-coin cap, Governor limits) kabhi weaken/bypass nahi kiya gaya; koi data delete nahi hui (sirf archive); har naye feature ke baad **poori test suite chalayi gayi** (start ~1037 tests → end **1458 tests, sab pass**); har badi behavior-changing cheez ka apna dedicated test file bana.

### 20.1 Phase 1 — Safety & Reliability (10 items, 6 naye)
Kill Switch (ek button se sab trading rok do), permanent Audit Trail (kabhi prune nahi hota, activity_log se alag), Incident Management System, Account-Wide Drawdown Circuit-Breaker (poore account ka combined balance apne peak se 20%+ girne par sab strategies ke naye trades rok deta hai), Backtest-vs-Paper Divergence Alert, AI provider rate-limit retry/backoff. 4 already existed (disaster recovery backup, consecutive-loss auto-pause, data freshness indicator, multi-language Telegram support). Emergency Contact Alert CEO ke faisle par ruka (Section 20.8).

### 20.2 Phase 2 — Telegram (15 items, 6 naye)
Delivery Retry Queue, Weekly Performance Digest (ab Telegram par bhi jata hai, text sparkline ke saath), `/status`/`/pause`/`/resume` incoming bot commands (pehli baar koi Telegram command SINDHU mein AATI hai, sirf bheji nahi jaati), Multi-Channel Routing (per-strategy alag channel), Silent Hours DND. 9 already existed (confidence-filtered sending, profitability labeling, risk disclaimer, challenge-mode tags, min-latency delivery, analytics, daily summary, multi-language). Chart Attachment CEO ke faisle par ruka (Section 20.8).

### 20.3 Phase 3 — Analytics & Visibility (20 items, 16 naye)
Strategy Health Score (0-100, documented weighted formula), Coin Performance Heatmap, Strategy Correlation Matrix, Portfolio Heat Map, Sortino Ratio, Value at Risk, MAE/MFE tracking, Time-of-Day Performance Breakdown, Win-Rate Decay Detection, Strategy Aging Analysis, Monthly Auto-Report, Backtest Duration Tracker, What-Changed-Today diff view, Coin Deep-Dive Page, Slippage Sensitivity Test, Sanity Check Alert. 4 already existed (regime detection, API rate-limit dashboard, walk-forward analysis, Monte Carlo simulation).

### 20.4 Phase 4 — Strategy Management & UX (27 items, 20 naye)
Strategy Tagging, Comments, Last-Changed Timestamp, Health Badge, Trade Annotation, Voice Alert (browser speech synthesis, sirf kill switch/drawdown jaisi safety-critical events ke liye), Custom Alert Rules (bounded, fixed metric choices — kabhi arbitrary expression nahi), Strategy Family Tree, Similarity Detector, Auto-Retirement Suggestion, Compare 2 Strategies View, Comparison Snapshot (copy-as-text), Beginner Mode, Onboarding Tour, Today's Focus Widget, Session Checklist, Quick Note Box, Session Handoff Summary, Undo/Rollback for strategy versions, Trade Journal PDF export. 7 already existed (retirement/archive workflow, quick search, glossary tooltips, explain-this-number, dark/light theme, PDF export, similarity — dedup check). Mobile Push Notifications CEO ke faisle par ruka (Section 20.8).

### 20.5 Phase 5 — Profitability Optimization (15 items, 10 naye)
Coin Blacklist (genuine deny-list, allowlist ranker se alag), Time-of-Day Trading Filter, Optimal Risk % Per Strategy (Sharpe-based suggestion), Slippage-Aware Entry Filter, Profit-Lock Trailing Stop, Ensemble Voting Confirmation (multiple independent strategies ka agreement chahiye), Best Combination Auto-Suggest (multi-strategy portfolio), Position Size Calculator, Historical What-If Simulator, Backtest Replay Visualizer (bar-by-bar candlestick step-through). 2 already existed (volatility-based sizing, multi-timeframe confirmation). **3 items CEO ke faisle par rukay hain** — Correlation-Aware Position Limiting, Dynamic Confidence Threshold, Regime-Aware Strategy Switching (Section 20.8 dekhein, sabse zaroori deferred group).

### 20.6 Phase 6 — Evolution & Self-Learning (13 items, 8 naye)
Failed Hypothesis Memory (ek pehle se likha function jo kabhi call nahi hota tha, ab wire ho gaya — naye BOT candidates ab past-regressed lineages se apna DNA compare karte hain), Strategy Lineage Explainability (plain-language narrative), Evolution Confidence Score, Automated Weekly Strategy Review, **Regime-Aware Evolution — ek real, pehle se maujood dead-code bug fix kiya gaya** (regime-adaptation ka code likha hua tha lekin `engine.py` kabhi zaroori parameters pass nahi karta tha, isliye kabhi chalta nahi tha), Feature Importance Ranking, Cross-Coin Group Validation, Self-Generated Strategy Variants. 4 already existed (automatic hypothesis generation, genetic parameter tuning, adaptive position sizing, confidence-weighted signals), 1 already correctly integrated (out-of-sample validation gate).

### 20.7 Phase 7 — Infrastructure & Sync (10 items, 3 naye is session mein + 2 pehle se complete)
Duplicate Exposure Warning (2+ strategies ek hi coin par), Weekly Auto-Snapshot (rolling 6-hourly backup se alag, apni khud ki 2-mahine ki retention), Automated Weekly Digest (system health — backups, incidents, database size — trading/evolution digests se alag content). Cloud-to-Local 24h Sync aur Missing Dashboard Section Audit pehle hi ek separate cloud-focused session mein complete ho chuke the. 5 items ya to pehle se maujood the (Signal Explainer, Strategy Health Score, Failed Hypothesis Memory ka duplicate) ya double-check karne par pata chala **poora page pehle se bana hua tha** (Strategy Lifecycle page — pehli audit pass ne isay miss kiya tha, dobara check karne se ek wasted rebuild bach gaya).

### 20.8 CEO Ke Faisle Par Rukay Hue Items (6)
Ye sab **technically buildable hain** — sirf isliye ruke hain kyunki inka faisla CEO ka apna hona chahiye, khud-ba-khud nahi kiya gaya:

1. **Emergency Contact Alert** (Phase 1) — agar SINDHU down ho jaye to kise, kaise batayen? Ek non-Telegram channel chahiye (email/SMS/doosra Telegram bot) + ek external uptime pinger (UptimeRobot jaisa).
2. **Chart Attachment with Signals** (Phase 2) — Telegram signals mein real chart IMAGE (naya Python dependency chahiye, abhi kahin nahi installed) ya text-based visual (bina dependency ke, abhi jaisa Weekly Report ka sparkline hai)?
3. **Mobile Push Notifications** (Phase 4) — native browser Web Push (naya dependency + VAPID setup) ya third-party relay jaisa ntfy.sh/Pushover (koi naya Python dependency nahi, lekin ek external service account chahiye)?
4. **Correlation-Aware Position Limiting**, **Dynamic Confidence Threshold**, **Regime-Aware Strategy Switching** (Phase 5) — teeno ka code mein pehle se explicitly likha hai ke "yeh kabhi trade block/influence nahi karta" — ek jaan-boojh kar liya gaya design decision. Isay palatna (asal trade-execution ko affect karna shuru karna) ek genuinely bara faisla hai, isliye khud-ba-khud nahi kiya gaya.

---

*(Known Gaps / Pending ka updated version Section 12 mein hai.)*

---

## 19. Quick Summary (5 Lines)

SINDHU ek self-learning crypto trading system hai jahan CEO sirf ek strategy ya YouTube link paste karta hai, aur AI (sirf import ke waqt, ek dafa) use hoke poori strategy ko samajh kar directly executable structure mein badal deta hai — uske baad AI ki zaroorat kabhi nahi padti. Ye structured data phir Backtesting Engine aur Paper Trading Engine dono mein bilkul same tarah chalta hai (multi-timeframe, auto-resampling, real indicators/patterns), aur sab kuch ek single SQLite database + JSON files mein permanently save hota hai. Poora system ek FastAPI web dashboard (`localhost:8420`) se control hota hai jo mobile aur laptop dono par chalta hai. Data/Backtesting/Knowledge/Paper Trading ke phases, AI Knowledge Learning Engine ke 3 versions (v6/v7/v8), Evolution Core Engine + SINDHU Strategy Generator (Phase 7A), aur sabse aakhir mein ek **Grand Feature Expansion (~110 features, 7 phases — Safety, Telegram, Analytics, Strategy Management, Profitability, Evolution, Infrastructure)** — sab complete hain (Section 20). Library mein **18 direct-manual-construction strategies** hain, jinme se **4 genuinely profitable** hain (Section 14), plus ab BOT-generated strategies ka poora separate ecosystem bhi hai (`evolution_engine`/`sindhu_strategy`). Live/real trading execution, News monitoring, Reflection ko standalone page banana, aur 6 CEO-decision-pending items (Section 20.8) — ye sab abhi baaki hain (Section 11/12).
