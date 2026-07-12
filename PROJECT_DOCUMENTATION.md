# SINDHU — Project Documentation (A to Z)

> Ye document sirf real code, files aur folders scan karke banaya gaya hai. Koi bhi cheez guess nahi ki gayi — agar kuch clear nahi tha to "TBD" likha hai.

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
| 8 | (Next phase) | ⏳ Pending | CEO ka decision baaki hai |

**Agla milestone:** Phase 8 abhi define nahi hua — CEO ki direction ka wait hai. `PROJECT_PLAN.md` (original roadmap) ke mutabiq possible candidates: News Monitoring, Telegram Alerts, Manager/Agent orchestration layer, ya Reflection/Evolution ko standalone pages banana.

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
├── strategies/
│   └── library/                 # Saved strategies (JSON files, per-ID folders)
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

Code mein disabled nav items aur `PROJECT_PLAN.md`/`PROGRESS.md` ke "What's NOT Built" section se confirmed:

- **Reflection** — standalone dashboard page (abhi Paper Trading ke andar internal hai)
- **Evolution** — standalone dashboard page (abhi Paper Trading ke andar internal hai)
- **News Monitoring** — bilkul nahi bana (nav mein disabled entry hai)
- **Telegram Alerts** — bilkul nahi bana (nav mein disabled entry hai)
- **Live/Real Trading Execution** — Paper Trading simulation-only hai, real order execution nahi
- **Local LLM Provider** — `ai_integration/config.py` mein sirf mention hai, koi actual local LLM runtime connect nahi hai
- **Manager/Agent orchestration layer** — original `PROJECT_PLAN.md` ka Phase 9 idea, abhi tak nahi bana

---

## 12. Known Issues / TODO

- `requirements.txt` mein package versions pin nahi hain — reproducibility ke liye risk
- Project **git repository nahi hai** — koi commit history available nahi, isliye phases ka exact timeline sirf `PROGRESS.md` se pata chalta hai (jo manually maintain kiya gaya)
- `data/settings/` aur `data/market_data/` folders bane hue hain lekin currently empty/unused (TBD — future use ke liye reserved lagte hain)
- Strategy Library do jagah track hoti hai: `strategies/library/*.json` (asli config) aur SQLite ka `strategies` table (sirf naam/module registration, backtest_batches ke liye) — dono ka exact relationship pura clear nahi (TBD)
- Desktop app (`dashboard/`) sirf 2 tabs tak limited hai — poori tarah web dashboard ke feature-parity mein nahi hai (jaan-boojh kar, kyunki web hi primary interface hai)

---

## 13. Quick Summary (5 Lines)

SINDHU ek self-learning crypto trading system hai jahan CEO sirf ek strategy ya YouTube link paste karta hai, aur AI (sirf import ke waqt, ek dafa) use hoke poori strategy ko samajh kar directly executable structure mein badal deta hai — uske baad AI ki zaroorat kabhi nahi padti. Ye structured data phir Backtesting Engine aur Paper Trading Engine dono mein bilkul same tarah chalta hai (multi-timeframe, auto-resampling, real indicators/patterns), aur sab kuch ek single SQLite database + JSON files mein permanently save hota hai. Poora system ek FastAPI web dashboard (`localhost:8420`) se control hota hai jo mobile aur laptop dono par chalta hai. 15+ phases already complete hain (Data, Backtesting, Knowledge, Paper Trading, aur AI Knowledge Learning Engine ke 3 versions v6/v7/v8). Live trading, Telegram alerts, News monitoring, aur Reflection/Evolution ko standalone pages banana — ye sab abhi future roadmap mein hain.
