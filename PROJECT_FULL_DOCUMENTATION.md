# SINDHU — Full Project Documentation

This document is a complete technical export of the SINDHU project, written so that
another AI assistant (or a new developer) can understand the entire system without
reading the source code. It reflects the codebase as of the "Knowledge Compiler"
phase (the most recently completed phase; see `PROGRESS.md` for phase history).

No AI/ML is used anywhere in this system's decision-making. Every "engine" described
below (parsing, classification, risk, confidence, reflection) is deterministic,
rule-based Python — regexes, keyword tables, and arithmetic — never a model call.

---

## 1. PROJECT OVERVIEW

### What this project does

SINDHU is a personal, local-first crypto-trading research and automation platform for
a single user ("the CEO"). It has grown in phases into five cooperating subsystems:

1. **Data Engine** — downloads and stores 1-minute OHLCV candles for ~50 coins across
   5 exchanges, and derives every other timeframe from that data on demand.
2. **Backtest Engine** — lets the CEO describe a trading strategy in free-text
   (English, Roman Urdu, or mixed) and backtests it bar-by-bar against real historical
   data, across many coins/timeframes at once, with full metrics/reports/exports.
3. **Knowledge Engine** — CEO-authored "lessons" (trading rules/guardrails) that gate
   every trade attempt during backtesting and paper trading, independent of strategies.
4. **Knowledge Compiler** — a document-understanding layer that lets the CEO paste
   *any* trading document (strategy, lesson, YouTube transcript, AI-generated report,
   book notes, etc.) and have it automatically classified, parsed, validated, and
   filed into the Strategy Engine and/or Knowledge Engine — no manual reformatting.
5. **Paper Trading Engine** — a fully automatic, 24/7, simulation-only trading bot
   that runs the same Strategy + Knowledge Engine logic live against real market data,
   opening/managing/closing simulated positions with a full risk/guard/reflection
   pipeline. **No real money or real orders are ever involved anywhere in this
   project.**

There are two user interfaces, both reading/writing the *same* SQLite database
safely at the same time:
- A **desktop app** (PySide6/Qt) — the original interface, still functional.
- A **web dashboard** (FastAPI + vanilla JS, no build step) — reachable from desktop,
  tablet, or phone on the same WiFi network. This is the actively-developed, primary
  interface as of the most recent phases.

### Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3 (backend, both UIs' business logic) |
| Desktop UI | PySide6 (Qt for Python) |
| Web backend | FastAPI + Uvicorn (ASGI), WebSockets for live updates |
| Web frontend | Vanilla HTML/CSS/JS — no framework, no build step, one `app.js` file |
| Database | SQLite (single file, `data/database/sindhu.db`) |
| Data analysis | pandas, numpy |
| Exchange connectivity | Custom lightweight REST client for Binance; `ccxt` library for OKX/Bybit/Bitget/Gate.io |
| Charting (desktop) | pyqtgraph |
| Export | openpyxl (Excel), reportlab (PDF), csv (stdlib) |
| QR codes | `qrcode` (for the mobile-connect feature) |
| System info | `psutil` (CPU/RAM for the dashboard) |

Full dependency list (`requirements.txt`): `requests`, `pandas`, `ccxt`, `PySide6`,
`openpyxl`, `reportlab`, `pyqtgraph`, `fastapi`, `uvicorn[standard]`, `psutil`, `qrcode`.

### How to run it

```bash
# Desktop app (PySide6 GUI)
cd E:\sindhu
python main.py

# Web dashboard (FastAPI + web UI) — opens http://localhost:8420 automatically
cd E:\sindhu
python web_main.py

# CLI (headless data download / status)
python run.py download --exchange binance
python run.py status
python run.py watch --exchange binance
```

Both the desktop app and the web dashboard can run **simultaneously** against the
same database file — SQLite handles the concurrent access safely. The web dashboard
is reachable from other devices on the same WiFi network at
`http://<this-PC's-LAN-IP>:8420` (the Home page shows this URL and a QR code).

No environment variables are used for configuration — everything lives in JSON files
under `data/config/` (see Section 8). The web server always listens on port **8420**.

---

## 2. FOLDER & FILE STRUCTURE

```
E:\sindhu\
│
├── main.py                       Desktop app entry point (launches PySide6 GUI)
├── web_main.py                   Web dashboard entry point (launches FastAPI/Uvicorn on :8420)
├── run.py                        CLI entry point (download / status / watch commands)
├── requirements.txt               Full pip dependency list
├── PROGRESS.md                    Human-readable phase-by-phase build history
├── PROJECT_PLAN.md                Original (Urdu/English mixed) vision document
├── PROJECT_FULL_DOCUMENTATION.md  This file
│
├── data/                          ALL persisted state lives here (git-ignorable)
│   ├── database/
│   │   ├── sindhu.db              The one SQLite database (~3GB with full history)
│   │   └── backups/               Automatic + manual hot-copy backups (sindhu_<timestamp>.db)
│   ├── config/                    JSON config files, human-editable, seeded with defaults on first run
│   │   ├── exchanges.json         Enabled exchanges + default exchange
│   │   ├── coins.json             num_coins, quote_asset
│   │   ├── timeframes.json        base_interval + supported timeframe list
│   │   ├── app_settings.json      history_days, request_delay, klines_limit, retries, default_risk_pct
│   │   ├── web_settings.json      theme, refresh_speed_seconds
│   │   ├── backup_settings.json   auto_backup_enabled, interval_hours
│   │   ├── api_token.json         auto-generated state-changing-request auth token
│   │   └── paper_trading_settings.json   Paper Trading engine settings (see Section 8)
│   ├── logs/sindhu.log            Central append-only log file (also streamed live to UIs)
│   ├── reports/<batch_id>/        report.json + report.txt per completed backtest batch
│   ├── history/sessions.jsonl     (reserved; session history)
│   ├── settings/                  (reserved folder)
│   └── market_data/                (reserved folder)
│
├── strategies/
│   ├── __init__.py
│   ├── base.py                    Strategy/Signal base classes (legacy hand-written strategy interface)
│   └── library/<id>/              On-disk saved strategies (see Section 4)
│       ├── meta.json              {id, name, tags, favourite, created_at, updated_at, current_version}
│       └── versions/vN.json       Full StrategyConfig snapshot per saved version
│
├── data_engine/                    DATA LAYER (Section 5)
│   ├── __init__.py
│   ├── paths.py                   Central folder-path constants + ensure_folders()/disk_usage_bytes()
│   ├── config.py                  JSON-config load/seed/save system + module-level constants
│   ├── storage.py                 THE central SQLite access layer — full schema + ~90 functions
│   ├── downloader.py               download_symbol()/download_all() — resumable candle fetching
│   ├── resample.py                 get_ohlcv() — derives any timeframe from stored 1m candles
│   ├── symbols.py                  pick_top_symbols() — CoinGecko-ranked, exchange-filtered coin list
│   ├── control.py                  DownloadControl — thread-safe pause/resume/stop switch
│   ├── logging_setup.py            log()/subscribe() — central logging + live-subscriber fan-out
│   ├── binance_client.py           (legacy/likely superseded by exchanges/binance.py)
│   ├── coingecko_client.py         get_top_market_cap_coins() — CoinGecko market-cap ranking
│   └── exchanges/
│       ├── __init__.py
│       ├── base.py                 ExchangeClient interface (get_tradeable_symbols/get_ohlcv/get_tickers)
│       ├── registry.py              get_exchange_client(id) — Binance native vs ccxt dispatch, with caching
│       ├── binance.py               BinanceClient — native lightweight REST implementation
│       └── ccxt_client.py           CCXTClient — wraps the `ccxt` library for OKX/Bybit/Bitget/Gate.io
│
├── backtest_engine/                 BACKTEST ENGINE (Section 6) + STRATEGY COMPILER (Section 4)
│   ├── __init__.py
│   ├── strategy_config.py           Condition / SLTPSpec / StrategyConfig dataclasses (the schema)
│   ├── strategy_parser.py           THE bilingual free-text -> StrategyConfig parser
│   ├── validator.py                 validate(config) -> list[str] errors; defines VALID vs INVALID
│   ├── concepts.py                  Vectorized indicator/SMC-structure calculations (ema, rsi, BOS, FVG, ...)
│   ├── configured_strategy.py        ConfiguredStrategy — interprets a StrategyConfig into a runnable Strategy
│   ├── mtf_context.py               MultiTimeframeContext — aligns multiple timeframes, zero look-ahead
│   ├── engine.py                    run_backtest() — the core bar-by-bar simulation loop
│   ├── metrics.py                   compute_metrics() — PnL/win-rate/drawdown/profit-factor/etc.
│   ├── runner.py                    run_batch()/run_mtf_batch() — resumable multi-coin batch runner + multiprocessing
│   ├── mtf_worker.py                 run_one_symbol() — one coin's backtest, used by both sequential and multiprocessing paths
│   ├── queue_runner.py               Runs multiple strategies back-to-back (the "Backtest Queue" feature)
│   ├── reports.py                    generate_report() — aggregates results into rankings + writes report.json/.txt
│   ├── export.py                     export_csv()/export_excel()/export_pdf() — one-click report export
│   ├── strategy_library.py           On-disk CRUD for saved strategies (meta.json + versions/vN.json)
│   └── strategy_loader.py            Legacy: discovers hand-written Strategy subclasses under strategies/*.py
│
├── knowledge_engine/                 KNOWLEDGE ENGINE (lessons)
│   ├── __init__.py
│   ├── lesson.py                    Lesson dataclass + new_lesson()/from_storage_dict() factory
│   ├── condition_eval.py             evaluate_condition() — standalone lesson condition evaluator
│   ├── engine.py                    KnowledgeEngine class — loads active lessons, gates trades, logs applications
│   └── scoring.py                   compute_knowledge_score() + per-lesson estimated impact %
│
├── knowledge_compiler/                KNOWLEDGE COMPILER (document understanding pipeline)
│   ├── __init__.py
│   ├── dictionary.py                 Canonical trading-terminology dictionary + normalize_text()
│   ├── classifier.py                 classify_document() — Strategy/Lesson/Mixed/Psychology/etc. detection
│   ├── sections.py                   detect_sections() — splits a document into labelled sections
│   ├── rule_extractor.py             Routes strategy-shaped sections through the existing strategy_parser
│   ├── lesson_extractor.py           Extracts candidate lessons from educational sections
│   ├── normalizer.py                 CompiledDocument / CompiledStrategyResult / CompiledLessonResult schema
│   ├── compiler_validator.py         Wraps backtest_engine.validator with default-fill/borrow resolution
│   ├── quality.py                    DNA fingerprinting, dedup, conflict detection, searchable tags
│   └── compiler.py                   compile_document() — the orchestrator tying everything together
│
├── paper_trading/                    PAPER TRADING ENGINE (24/7 automatic simulation)
│   ├── __init__.py
│   ├── config.py                     Settings (dry_run, max_open_trades, cooldown, priority rule, ...)
│   ├── coin_filter.py                shortlist() — ranks coins by volume/trend/volatility, top-N only
│   ├── live_feed.py                  refresh_coins() — keeps shortlisted coins' candles current
│   ├── market_state.py               classify() + EventTracker — market-state detection & event-trigger gate
│   ├── strategy_matcher.py           relevant_strategies() — which saved strategies apply to this coin/state
│   ├── lesson_matcher.py             relevant_lessons() — which active lessons apply to this coin/state
│   ├── frame_builder.py              build_entry_frame() — indicator frame for standalone lesson signals
│   ├── signal_generator.py           generate_candidates() — the Decision Engine (strategy path + lesson path)
│   ├── confidence.py                 score() — 0-100 reporting-only confidence score
│   ├── risk_manager.py               evaluate()/account_balance() — the one mandatory approval gate
│   ├── guards.py                     Position Lock, Duplicate Protection, Reservation, Cooldown, Priority
│   ├── position_manager.py           open_position()/monitor_and_close()/force_close() — trade lifecycle
│   ├── reflection.py                 build() — deterministic post-trade "why enter/exit, mistakes, success"
│   ├── evolution.py                  record_outcome() — updates strategy/lesson performance rankings only
│   └── engine.py                     PaperTradingEngine — the 24/7 background-thread orchestrator
│
├── dashboard/                          DESKTOP UI (PySide6/Qt) — independent of the web dashboard
│   ├── __init__.py
│   ├── main_window.py                 Main window, tab layout
│   ├── worker.py                      QThread wrapper for the download job
│   ├── settings_dialog.py             Settings dialog
│   ├── backtest_tab.py                Backtesting tab (single-timeframe, legacy Strategy subclasses)
│   ├── backtest_worker.py             QThread wrapper for a legacy backtest run
│   ├── mtf_backtest_worker.py          QThread wrapper for a StrategyConfig (multi-timeframe) backtest run
│   ├── strategy_builder_tab.py         Free-text strategy input + parse/validate preview (parser consumer)
│   ├── strategy_library_tab.py         Saved-strategy library UI (CRUD, favourite, search)
│   ├── candlestick_item.py            pyqtgraph candlestick chart item
│   ├── trade_replay_dialog.py          Per-trade candlestick replay dialog
│   ├── trade_history_tab.py           Trade history table
│   ├── queue_worker.py                QThread wrapper for the multi-strategy backtest queue
│   └── rankings_tab.py                Coin/timeframe/session ranking views
│
├── sindhu_web/                          WEB DASHBOARD (FastAPI backend + vanilla-JS frontend)
│   ├── __init__.py
│   ├── server.py                      FastAPI app assembly: middleware, routers, WebSocket broadcast loop, lifespan
│   ├── broadcast.py                   Thread-safe pub/sub queue -> WebSocket fan-out
│   ├── sync.py                        sync.notify() — central change notification (activity_log + live push)
│   ├── network.py                     LAN IP detection + QR code generation
│   ├── devices.py                     In-memory "connected devices" tracker (per open WebSocket)
│   ├── security.py                    LAN-only IP restriction + X-Sindhu-Token guard middleware
│   ├── cache.py                       In-memory TTL cache helper (cache.cached/invalidate/clear_all)
│   ├── jobs/
│   │   ├── __init__.py
│   │   └── job_manager.py             Generic background-thread job registry (downloads, backtests)
│   ├── api/                             One file per page/feature, all mounted as FastAPI routers
│   │   ├── __init__.py
│   │   ├── home.py                     /api/nav, /api/home — Overview cards, module status, Control Center
│   │   ├── market.py                   /api/market — live prices, signal, volatility per coin
│   │   ├── data.py                     /api/data, /api/data/download — Data Engine status + trigger download
│   │   ├── backtesting.py              /api/backtesting/* — parse/save/list/run strategies
│   │   ├── reports.py                  /api/reports/* — batch results, rankings, trade list, export
│   │   ├── knowledge.py                /api/knowledge/* — lesson CRUD + Knowledge Score report
│   │   ├── knowledge_compiler.py       /api/knowledge-compiler/* — document compile/list/concepts
│   │   ├── paper_trading.py            /api/paper-trading/* — engine control, positions, decisions, performance
│   │   ├── settings.py                 /api/settings — exchange/coins/theme/risk defaults
│   │   ├── backup.py                   /api/backup/* — manual/automatic DB backup + restore
│   │   ├── jobs.py                     /api/jobs/* — list/pause/resume/stop background jobs
│   │   ├── ws.py                       /ws/logs — the one WebSocket endpoint
│   │   ├── network.py                  /api/network — LAN IP/QR/connected devices
│   │   ├── activity.py                 /api/activity — Activity Feed log
│   │   ├── search.py                   /api/search — global cross-entity search
│   │   └── system.py                   /api/system/restart-services — soft cache-clear reset
│   └── static/
│       ├── index.html                  Page shell (nav, topbar, content div)
│       ├── css/app.css                 Design system (dark theme, cards, pills, responsive breakpoints)
│       └── js/app.js                   The entire frontend SPA (router, API client, every page renderer)
│
└── (temporary/generated: __pycache__, data/reports/<batch>/report.txt sample, etc.)
```

---

## 3. EVERY MODULE IN DETAIL

Below, "module" follows the web dashboard's own page groupings (as the spec
requested), cross-referencing the backend files that implement each.

### Dashboard (Home page)

**What it does:** the landing page — system health, account snapshot, module status,
Control Center (LAN URL/QR, connected devices, task manager, quick actions, activity
feed).

**Backend:** `sindhu_web/api/home.py`
- `GET /api/nav` → `{"pages": [...]}` — the enabled nav items (id/label/icon), driven
  by the `NAV_PAGES` list (flipping `enabled` is how a new module goes live).
- `GET /api/home` → one big dict: `project_status`, `version`, `system_health`,
  `database_status`, `database_size_bytes`, `total_coins`, `available_timeframes`,
  `total_candles`, `cpu_percent`/`ram_percent` (via `psutil`), `current_task`,
  `running_jobs`, `knowledge_score`, `task_summary` (`running/waiting/completed/failed`
  counts), `module_status` (dict of module name → "Running"/"Idle"), `disk_usage_bytes`,
  `exchange`, `latest_batch` (the account snapshot below), `evolution_score` (always
  `None` currently — Evolution has no standalone page yet).
- `_account_snapshot()`: prefers the **live Paper Trading account** (balance/PnL/win
  rate/total trades computed from `paper_positions`) once it has any closed trade
  history; otherwise falls back to the most recent completed **Backtest** batch's
  report, so the cards are never empty on a fresh install.

**Connects to:** every other module feeds `module_status`/`task_summary` here (via
`job_manager`); Paper Trading and Backtesting both feed the Overview cards.

### Market

**What it does:** live price table for every tracked coin — price, 24h change, volume,
a cheap directional "signal" (Bullish/Bearish/Neutral), and short-term volatility.

**Backend:** `sindhu_web/api/market.py`, one endpoint:
- `GET /api/market` → `{"exchange", "quote", "coins": [{"symbol","price","change_pct","volume","trend","signal","volatility_pct"}]}`.
  Signal = close vs. its 20-period EMA on 1h candles (>0.1% above → Bullish, >0.1%
  below → Bearish, else Neutral). Volatility = stdev of 1h returns over the last ~50
  hours, as a %. Cached 30s (`sindhu_web/cache.py`) since it fans out one ticker call
  plus a resample per coin.

**Connects to:** reads through `data_engine.resample.get_ohlcv` and the exchange
client registry — no separate data source from the Data module.

### Data

**What it does:** shows per-coin candle counts/date ranges/download status, database
size, and lets the CEO trigger a (re)download pass.

**Backend:** `sindhu_web/api/data.py`
- `GET /api/data` → `{"exchange","coins":[{"symbol","candles","start","end","status"}],"timeframes","missing_data","total_coins","database_size_bytes"}` (cached 60s).
- `POST /api/data/download` → starts a background job (`job_manager.create_job`)
  that calls `data_engine.downloader.download_all`, the exact same resumable
  downloader the CLI/desktop app use. Returns `{"job_id"}` immediately; progress
  streams over the WebSocket (`channel: "progress"`).

**Connects to:** `data_engine.storage`, `data_engine.downloader`, `data_engine.symbols`
(to auto-pick top coins if none tracked yet), `sindhu_web.jobs.job_manager`.

### Strategies

**What it does:** full strategy-library management — search, favourite, duplicate,
delete, and "Edit in Backtesting" (loads a saved strategy back into the paste/parse
workflow).

**Backend:** `sindhu_web/api/backtesting.py` (shared with the Backtesting page):
- `GET /api/backtesting/strategies?q=` → `{"strategies": [...]}` (search by name/tag).
- `GET /api/backtesting/strategies/{id}` → `{"config": StrategyConfig.to_dict()}`.
- `DELETE /api/backtesting/strategies/{id}` → deletes the whole library folder.
- `POST /api/backtesting/strategies/{id}/favourite?favourite=bool`.
- `POST /api/backtesting/strategies/{id}/duplicate` → new id.

**Connects to:** `backtest_engine.strategy_library` (the on-disk store, Section 4),
`sindhu_web.sync` (every mutation calls `sync.notify()` so other open devices update
live).

### Knowledge

**What it does:** CEO-authored trading "lessons" that gate trades during backtesting
and paper trading — CRUD, search/filter, per-lesson usage stats, Knowledge Score,
Best/Worst Lessons ranking.

**Backend:** `sindhu_web/api/knowledge.py`
- `GET /api/knowledge/categories` → the 18 fixed `Lesson.CATEGORIES`.
- `GET /api/knowledge/report` → Knowledge Score + total/active/disabled lesson counts
  + lessons-applied/approved/rejected stats + `recent_lessons`.
- `GET /api/knowledge/lessons?q=&category=` → lessons with `stats` (times_used,
  trades_approved, trades_rejected) and `estimated_impact_pct` attached per lesson.
- `GET /api/knowledge/lessons/{id}`.
- `POST /api/knowledge/lessons` (body: title, category, description, priority, notes,
  status, apply_backtesting/apply_paper_trading/apply_evolution) → calls
  `knowledge_engine.lesson.new_lesson()` then `storage.save_lesson()`.
  **Note:** this request model does not currently expose `tags`,
  `supported_market_types`, or `supported_timeframes` even though the `Lesson`
  dataclass and DB schema support them — those can only be set via direct DB access
  or the Knowledge Compiler pipeline (which does set `tags`).
- `PUT /api/knowledge/lessons/{id}`, `DELETE /api/knowledge/lessons/{id}`.
- `POST /api/knowledge/lessons/{id}/duplicate`.
- `POST /api/knowledge/lessons/{id}/status` (body: `{"status"}`) → active/disabled/draft.

**Connects to:** `knowledge_engine.lesson`, `knowledge_engine.scoring`, and is read by
`backtest_engine.engine.run_backtest` (via a `KnowledgeEngine` instance) and by
`paper_trading.lesson_matcher`/`signal_generator` for live gating.

### Knowledge Compiler

**What it does:** the CEO pastes any trading document; the system classifies it,
extracts executable rules into a Strategy and/or educational content into Lessons,
resolves what it safely can, and reports what still needs a human answer. See
Section 4 for the exact pipeline.

**Backend:** `sindhu_web/api/knowledge_compiler.py`
- `POST /api/knowledge-compiler/compile` (body: `text`, optional `title`,
  `source_hint`) → the full `CompiledDocument` (doc type + confidence, detected
  sections, extracted strategies with status/clarification notes, extracted lessons,
  concepts recognized, overall status).
- `GET /api/knowledge-compiler/documents?doc_type=&status=&limit=` → compile history.
- `GET /api/knowledge-compiler/documents/{id}`.
- `GET /api/knowledge-compiler/concepts` → the auto-growing usage-tracked dictionary
  terms (not the static dictionary itself — that's code-defined).

**Connects to:** `backtest_engine.strategy_parser`/`validator`/`strategy_library`
(reused, not rebuilt), `knowledge_engine.lesson.new_lesson` (reused), and its own new
`knowledge_compiler/` package (Section 4). Frontend: the "Knowledge Compiler" nav page
(paste box + Compile button + results panel).

### Backtesting

**What it does:** paste/parse a strategy, preview validation, run it across many
coins at once, live progress, and hand off to the Reports page.

**Backend:** `sindhu_web/api/backtesting.py`
- `POST /api/backtesting/parse` (body: `text`, `name`) → `{"config", "errors", "valid"}`
  — the manual-edit preview flow (Strategy Builder's live parse-as-you-type).
- `POST /api/backtesting/strategies` (save/update, described above under Strategies).
- `GET /api/backtesting/coins` → tracked symbols for the default exchange.
- `POST /api/backtesting/run` (body: `strategy_id` or inline `config`, `symbols`,
  `all_coins`, `initial_balance`, `risk_pct`, `commission_pct`, `slippage_pct`,
  `position_size_pct`, `start_ms`/`end_ms`, `use_multiprocessing`) → validates first
  (`400` with `{"errors"}` if invalid), then starts a background job running
  `backtest_engine.runner.run_mtf_batch`, then `generate_report()` on completion.
  Returns `{"job_id"}` immediately.

**Connects to:** the whole Backtest Engine (Section 6) and Strategy Compiler
(Section 4); progress and per-trade events stream over the WebSocket.

### Paper Trading

**What it does:** dashboard for the fully-automatic 24/7 paper trading engine — start/
stop, live status, open/closed positions, decision log, strategy/lesson performance.

**Backend:** `sindhu_web/api/paper_trading.py`
- `GET /api/paper-trading/status` → `{"running","dry_run","started_at","last_tick_at","tick_count","open_trades","queue","balance","last_summary"}`.
- `POST /api/paper-trading/start` / `POST /api/paper-trading/stop`.
- `POST /api/paper-trading/run-tick-now` → manual single-tick trigger for testing.
- `GET /api/paper-trading/settings` / `POST /api/paper-trading/settings` (partial
  update of any of: dry_run, initial_balance, risk_pct_default, max_open_trades,
  cooldown_minutes, priority_rule, opposite_signal_policy, coin_filter_top_n,
  tick_interval_seconds, lookback_days, lesson_default_timeframe/sl_pct/rr,
  daily_goal_pct).
- `GET /api/paper-trading/positions` → currently open positions.
- `GET /api/paper-trading/trades?limit=` → closed positions (trade history).
- `POST /api/paper-trading/positions/{id}/close` → manual force-close.
- `GET /api/paper-trading/decisions?decision=&limit=` → the No-Trade Journal /
  full decision log (every "opened"/"rejected"/"dry_run" outcome).
- `GET /api/paper-trading/strategy-performance` / `GET /api/paper-trading/lesson-performance`.
- `GET/POST /api/paper-trading/strategy-config/{strategy_id}` — per-strategy Paper
  Trading metadata (enabled, priority, supported_coins, supported_market_types).

**Connects to:** the entire `paper_trading/` package (Section 3's own subsection
below), which itself reuses `backtest_engine.configured_strategy`/`mtf_context` and
`knowledge_engine` verbatim.

### Reports

**What it does:** per-batch results — summary metrics, equity/drawdown charts (built
client-side from raw trades), coin/timeframe/session rankings, Best/Worst strategy
across all batches, CSV/Excel/PDF export.

**Backend:** `sindhu_web/api/reports.py`
- `GET /api/reports` → recent batches list.
- `GET /api/reports/best-worst/strategies` → ranking of every strategy ever run, by
  average profit % across its batches.
- `GET /api/reports/{batch_id}` → the full `generate_report()` output (Section 6).
- `GET /api/reports/{batch_id}/trades` → chronological trade list (frontend builds
  the equity/drawdown curve from this).
- `GET /api/reports/{batch_id}/export/{fmt}` — `fmt` = `csv` (paths list), `excel` or
  `pdf` (FileResponse download).

### Settings

**What it does:** exchange/coin/theme/refresh-rate/default-risk config, all backed by
the JSON config files (Section 8).

**Backend:** `sindhu_web/api/settings.py`
- `GET /api/settings` → merged view of `exchanges.json`+`coins.json`+`app_settings.json`+`web_settings.json`, plus `available_exchanges` and the (read-only, informational)
  `database_location`.
- `POST /api/settings` (partial update of any of: exchange, quote_asset, num_coins,
  theme, refresh_speed_seconds, default_risk_pct) → writes back to the relevant JSON
  file(s) and calls `sync.notify()`.

Also: `sindhu_web/api/backup.py` (`/api/backup/create`, `/api/backup/list`,
`/api/backup/restore`) and `sindhu_web/api/system.py`
(`/api/system/restart-services` — a soft cache-clear, not a real process restart)
live under the Settings page's "Control Center"/quick-actions area.

---

## 4. STRATEGY COMPILER / PARSER

This is the heart of both the Backtest Engine and (extended, not rebuilt) the
Knowledge Compiler. There are two layers:

1. `backtest_engine/strategy_parser.py` — the original, still-unmodified-in-behavior
   bilingual keyword parser.
2. `knowledge_compiler/` — a newer routing/normalization/validation-resolution layer
   built *around* the parser (Section "Knowledge Compiler" further down).

### 4a. The bilingual parser (`strategy_parser.py`)

No AI/LLM. Understands English, Roman Urdu, and mixed text because the trading
jargon itself (BOS, CHoCH, FVG, EMA, RSI, ...) is used verbatim in all three — only
the connector words differ, handled via small synonym tables.

**Public entry points:**
- `parse_strategy_text(text, name="Unnamed Strategy") -> StrategyConfig`
- `parse_conditions(text) -> list[Condition]` (also used by `knowledge_engine.lesson.new_lesson()` to parse a lesson's description)

**Regex/keyword tables (exact):**
```
_TIMEFRAME_RE = r"\b(\d{1,3})\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days|w|week|weeks)\b"  (case-insensitive)

_ROLE_KEYWORDS = {
  "bias": ["bias", "market bias", "daily bias", "higher timeframe", "htf"],
  "trend": ["trend"],
  "analysis": ["analysis", "structure", "structure tf", "intermediate"],
  "entry": ["entry", "entry tf", "entry timeframe", "ltf", "lower timeframe"],
  "confirmation": ["confirmation", "confirm", "trigger", "entry confirmation"],
}

_SECTION_KEYWORDS = {
  "entry_conditions": ["entry rule", "entry rules", "entry:", "entry condition", "entry conditions", "buy rule", "entry setup"],
  "exit_conditions": ["exit rule", "exit rules", "exit:", "exit condition", "exit conditions", "sell rule"],
  "confirmation_conditions": ["confirmation rule", "confirmation:", "confirmation condition", "trigger:"],
}

CONCEPT_KEYWORDS = {   # (exported publicly; used verbatim by knowledge_compiler.dictionary)
  "liquidity_sweep": ["liquidity sweep", "liquidity grab", "stop hunt", "sweep"],
  "bos": ["bos", "break of structure"],
  "choch": ["choch", "change of character"],
  "fvg": ["fvg", "fair value gap", "imbalance"],
  "order_block": ["order block", "orderblock", " ob "],
  "breaker_block": ["breaker block", "breaker"],
  "support": ["support"], "resistance": ["resistance"],
  "ema": ["ema"], "sma": ["sma"], "vwap": ["vwap"], "rsi": ["rsi"],
  "macd": ["macd"], "atr": ["atr"], "volume": ["volume"],
  "session_filter": ["session"],
  "trend_filter": ["trend filter", "with trend", "trend ke sath", "trend follow"],
}

SESSION_NAMES = {
  "asian": ["asian session", "asia session", "tokyo session", "asian"],
  "london": ["london session", "london"],
  "ny": ["new york session", "ny session", "newyork", "new york", " ny "],
}

DIRECTION_WORDS = {
  "bullish": ["bullish", "buy", "long", "upar", "upward", "up"],
  "bearish": ["bearish", "sell", "short", "neeche", "downward", "down"],
}

_ABOVE_WORDS = ["above", "upar", ">", "greater than", "crosses above"]
_BELOW_WORDS = ["below", "neeche", "<", "less than", "crosses below"]

_INDICATOR_WITH_PERIOD_RE = r"\b(ema|sma|rsi|atr)\D{0,3}(\d{1,4})\b"
_INDICATOR_COMPARE_RE     = r"\b(rsi|atr)\b.{0,15}?(<=|>=|<|>|below|neeche|above|upar)\s*(\d+(?:\.\d+)?)"
_PRICE_VS_INDICATOR_RE    = r"\b(close|price)\b.{0,15}?(above|below|upar|neeche|>|<)\s*(ema|sma|vwap)\D{0,3}(\d{1,4})?"

_RISK_RE          = r"\brisk\b\D{0,5}(\d+(?:\.\d+)?)\s*%?"
_RR_RE            = r"(?:\brr\b|risk\s*reward|r\s*:\s*r)\D{0,5}1\s*:\s*(\d+(?:\.\d+)?)"   # NOTE: only 1:N ratios
_SL_PCT_RE        = r"\bsl\b.{0,10}?(\d+(?:\.\d+)?)\s*%"
_SL_ATR_RE        = r"\bsl\b.{0,15}?atr\D{0,3}(\d+(?:\.\d+)?)"
_SL_STRUCTURE_RE  = r"\bsl\b.{0,25}?\b(order block|ob|swing|structure|breaker)\b"   # NOTE: does NOT include "fvg"
_TP_PCT_RE        = r"\btp\b.{0,10}?(\d+(?:\.\d+)?)\s*%"
```

**Line-by-line parse order in `parse_strategy_text` (exact precedence):**
1. Unconditionally scan the line for any `CONCEPT_KEYWORDS` mention → add to
   `config.concepts_used` (regardless of anything else on the line).
2. Unconditionally scan for `_INDICATOR_WITH_PERIOD_RE` matches (e.g. "EMA 50") →
   append `{"name","params":{"period"},"role"}` to `config.indicators`.
3. **Role + timeframe on the same line** (e.g. "Entry: 15M") → set
   `config.timeframes[role] = normalized_tf`, clear role hint, `continue`.
4. **Bare timeframe following a role hint from the previous line** → same effect.
5. **Explicit section header** (matches `_SECTION_KEYWORDS`) → set
   `current_section`, parse anything after the colon on the same line into that
   bucket, `continue`.
6. **Bare role keyword alone** (e.g. "Bias") → sets `current_role_hint` for the next
   line, `continue`.
7. **Session directive** (line starts with "session" or contains "session:") → adds
   matched session names to `config.session_filter`, `continue`.
8. **Risk / RR / SL% / SL-ATR / SL-structure / TP% regexes**, tried in that exact
   order, first match wins, `continue`. **Only one of these can match per line** —
   a compact line like "SL 2% TP 4% Risk 1%" only ever yields the *first* one found
   in this order (Risk is checked before SL/TP, so in that example only `risk_pct`
   would be set, and SL/TP would both remain "unknown" from parsing this one line).
9. **Fallback:** if `current_section` is active, the whole line is fed through
   `_parse_conditions_from_line` into that bucket. If no section is active AND the
   line mentions any concept keyword, it's added to `entry_conditions` instead
   (this fallback is why a raw "Strategy Name: ... Long" title line, if fed into the
   parser directly, can be accidentally read as a condition — the Knowledge Compiler
   strips a leading title line before this ever happens).

After the main loop: if no take-profit was set but `risk_reward` was detected,
`take_profit` defaults to `SLTPSpec(type="rr", value=risk_reward)`. Then
`_ensure_indicators_for_conditions` backfills a default-period indicator entry for
any indicator referenced by a condition but never declared with an explicit period.
Finally `_fill_missing_and_warnings` populates `config.missing`/`config.warnings`.

**`_parse_conditions_from_line(line)`** — splits the line on `and|aur|+|,` (regex,
case-insensitive), then for each segment tries, in order, until one matches:
1. `_PRICE_VS_INDICATOR_RE` → `Condition(type="price_compare", op, indicator, params={"period"})`
2. `_INDICATOR_COMPARE_RE` → `Condition(type="indicator_compare", indicator, op, value)`
3. A session name match → `Condition(type="session", name)`
4. Any `CONCEPT_KEYWORDS` match (except `session_filter`) → `Condition(type="concept", name, direction)` (direction from `DIRECTION_WORDS`, may be `None`)
5. A `trend_filter` keyword match → `Condition(type="trend", direction)`
6. Otherwise → `Condition(type="raw", text=segment)` — **never guessed at**, this is
   what shows up as an "unclear rule, needs clarification" error.

### 4b. Fields extracted (the `StrategyConfig` schema — `strategy_config.py`)

```python
@dataclass
class Condition:
    type: str            # "indicator_compare" | "price_compare" | "concept" | "session" | "trend" | "raw"
    indicator: str = None    # for indicator_compare (e.g. RSI < 30) and price_compare (e.g. close > EMA50)
    params: dict = {}        # e.g. {"period": 14}
    op: str = None           # ">" | "<" | "<=" | ">="
    value: float = None      # comparison threshold
    name: str = None         # concept name (e.g. "bos") or session name (e.g. "london")
    direction: str = None    # "bullish" | "bearish" (concept/trend conditions)
    text: str = None         # raw/unparsed text (type="raw" only)
    role: str = None         # which timeframe role this condition evaluates on
    is_unclear(self) -> bool  # True iff type == "raw"

@dataclass
class SLTPSpec:
    type: str = "unknown"    # "fixed_pct" | "atr_multiple" | "structure" | "rr" (TP only) | "unknown"
    value: float = None

@dataclass
class StrategyConfig:
    name: str
    raw_text: str = ""
    timeframes: dict = {}              # {"bias":"4h","trend":"1h","analysis":"15m","entry":"5m","confirmation":"1m"}
    indicators: list = []               # [{"name":"ema","params":{"period":50},"role":"trend"}]
    concepts_used: list = []            # ["bos","fvg",...]
    entry_conditions: list[Condition] = []
    exit_conditions: list[Condition] = []
    confirmation_conditions: list[Condition] = []
    stop_loss: SLTPSpec = SLTPSpec()
    take_profit: SLTPSpec = SLTPSpec()
    risk_pct: float = None
    risk_reward: float = None
    session_filter: list = []           # ["london","ny"]
    trend_filter: str = None            # "up" / "down" / None
    tags: list = []
    favourite: bool = False
    missing: list = []                  # required fields not detected
    warnings: list = []                 # detected but ambiguous
```
`to_dict()`/`from_dict()` round-trip through plain dicts (used for JSON storage and
the web API's request/response bodies), reconstructing nested `Condition`/`SLTPSpec`
objects on load.

### 4c. Validation rules — VALID vs INVALID (`validator.py`)

`validate(config) -> list[str]` (empty = valid). **Never mutates config, never
guesses a fix — only reports.** Checks, in order:
1. `"entry" not in config.timeframes` → "Missing entry timeframe..."
2. `not config.entry_conditions` → "Missing entry rules..."; else every `is_unclear()`
   entry condition → `'Unclear entry rule, needs clarification: "<text>"'`
3. `not config.exit_conditions and stop_loss.type == "unknown"` → "Missing exit
   rules..."; else every unclear exit condition reported the same way.
4. `stop_loss.type == "unknown"` → "Missing stop loss..."
5. `take_profit.type == "unknown"` → "Missing take profit..."
6. `risk_pct is None` → "Missing risk %..."; `not (0 < risk_pct <= 100)` → "Invalid
   risk %..."
7. `risk_reward is not None and risk_reward <= 0` → "Invalid risk:reward ratio..."
8. Every condition's `indicator`/`concept name` checked against
   `_KNOWN_INDICATORS = {ema, sma, vwap, rsi, macd, atr, volume, support, resistance,
   bos, choch, fvg, order_block, breaker_block, liquidity_sweep}` → "Invalid
   indicator/concept..." if not recognized.

`is_valid(config) -> bool` = `len(validate(config)) == 0`. This exact function gates
both the web `/api/backtesting/run` endpoint and the desktop Strategy Builder's Run
button.

### 4d. Supported keywords/formats — quick reference

| You can write | Recognized as |
|---|---|
| `Entry: 15M`, `Bias: 4H`, `Trend Timeframe 1h` | timeframe for that role |
| `Entry Rules:` / `Exit Rules:` / `Confirmation:` | section header |
| `Close above EMA 50`, `Price below SMA(200)` | price_compare condition |
| `RSI below 30`, `RSI > 70` | indicator_compare condition |
| `BOS`, `bullish break of structure` | concept condition (bos) |
| `CHoCH`, `change of character` | concept condition (choch) |
| `FVG`, `fair value gap`, `imbalance` | concept condition (fvg) |
| `order block`, `orderblock` | concept condition (order_block) |
| `breaker block` | concept condition (breaker_block) |
| `liquidity sweep`, `stop hunt` | concept condition (liquidity_sweep) |
| `support` / `resistance` | concept condition |
| `Session: London` | session filter |
| `Trend Filter: with trend` | trend filter |
| `SL 2%` | stop_loss fixed_pct |
| `SL ATR 1.5` | stop_loss atr_multiple |
| `SL order block` / `SL structure` / `SL swing` | stop_loss structure (does NOT recognize "SL fvg") |
| `TP 4%` | take_profit fixed_pct |
| `RR 1:3` / `Risk Reward 1:3` (must be "1:N" form) | risk_reward + rr-based take_profit |
| `Risk 1%` | risk_pct |
| Roman Urdu: `upar`/`neeche` (above/below), `aur` (and), `long`/`short`/`buy`/`sell` | same as English equivalents |

**Known parser limitations** (pre-existing, documented, not "fixed" by later phases
since they're core Backtest Engine behavior): only one SL/TP/RR/Risk directive is
recognized per line (a compact "SL 2% TP 4% Risk 1%" only picks up "Risk"); RR must be
literal "1:N" notation, not spoken "1 to 3"; SL-structure only recognizes order
block/swing/structure/breaker, not FVG; entry conditions within one strategy are
AND'd together (no OR-alternative setups).

### 4e. Knowledge Compiler — the extended pipeline

Built entirely **on top of** the parser above (never modifying its condition-parsing
regex logic). Full pipeline in `knowledge_compiler/compiler.py:compile_document(text, title, source_hint)`:

1. **`sections.extract_title(text)`** — strips a leading "Strategy Name:"/"Title:"/
   "Name:" line so it can't be accidentally parsed as a rule; returns `(title, working_text)`.
2. **`classifier.classify_document(working_text)`** — keyword-bucket scoring into
   `STRATEGY | LESSON | MIXED | PSYCHOLOGY | RISK_MANAGEMENT | INDICATOR_GUIDE |
   MARKET_STRUCTURE | UNKNOWN`, with a confidence score (0.3–0.95, never 1.0).
   Buckets counted: `_ENTRY_EXIT_KEYWORDS` (rule-structure signals), `_LESSON_KEYWORDS`
   (mistake/tip/important/checklist/etc — deliberately excludes the word "avoid" alone,
   too generic), and dictionary category counts for psychology/risk/indicator/
   structure terms. `MIXED` when both rule-signal and lesson-signal clear the
   threshold.
3. **`sections.detect_sections(working_text)`** — splits into labelled `Section`
   objects (`kind`, `heading`, `text`, line range) recognizing markdown headers (`#`),
   bold headers (`**Heading**`), and short colon headers ("Entry Rules:"). No headers
   at all → one `body` section covering everything (fully backward compatible with a
   flat strategy paste). Kinds: `summary, entry_rules, exit_rules, risk,
   market_conditions, indicators, filters, psychology, common_mistakes, weaknesses,
   strengths, checklist, pseudocode, if_then_rules, performance, body, narrative`
   (`narrative` = an unrecognized header, ignored by both extractors per spec's
   "ignore unrelated narrative").
4. **If doc_type is `STRATEGY` or `MIXED`**: `rule_extractor.extract_strategy()` —
   concatenates the strategy-relevant sections (only re-emitting the section
   *heading* text for `entry_rules`/`exit_rules`, since those are the only two kinds
   `strategy_parser`'s own header keywords recognize — any other heading like
   "Filters:" would otherwise get mis-parsed as a bogus condition), applies two
   contained text-level fixes (`_split_combined_directives` — splits "SL 2% TP 4%
   Risk 1%" onto separate lines; `_normalize_spoken_phrasing` — "stop loss"→"SL",
   "take profit"→"TP", "1 to 3 risk reward"→"risk reward 1:3"), then
   `dictionary.normalize_text()` (rewrites recognized structural/indicator/session/
   trend aliases — e.g. "bullish OB", "PDH" — into wording the parser already knows;
   deliberately never touches risk/psychology terms, which would break the parser's
   own literal `sl`/`tp`/`rr`/`risk` regex matching), then calls the **unmodified**
   `strategy_parser.parse_strategy_text()`.
5. **`quality.dedupe_rules(config)`** + **`quality.merge_concepts()`** — removes
   exact-duplicate conditions, canonicalizes concept names.
6. **`quality.detect_conflicts(config)`** — same-bucket contradictions (e.g. an
   indicator required both `>` and `<`, or a concept required both bullish and
   bearish direction).
7. **`compiler_validator.resolve_and_validate(config)`** — wraps (never replaces)
   `validator.validate()`. First fills default Trading-Dictionary indicator periods
   (RSI 14, EMA/SMA 20, ATR 14) unconditionally. Then, for each raw validation error:
   missing risk % → default 1.0; missing take-profit → derive from a detected RR, or
   default 2.0:1; missing entry timeframe → borrow from the most-similar strategy
   already in the Knowledge Library (≥2 shared concepts), else default `1h`; missing
   stop-loss → borrow from a similar strategy if one has a computed SL type, else left
   unresolved (never invents a risk-critical value from nothing). Unclear entry/exit
   rules and invalid indicator names are **never** auto-resolved. Result:
   `READY_FOR_BACKTEST` (nothing left unresolved) or `NEEDS_CLARIFICATION` (with the
   exact remaining error strings).
8. **`quality.strategy_dna(config)`** — SHA-256 fingerprint (16 hex chars) over sorted
   condition tuples + SL/TP type+value + risk/RR + timeframes; falls back to a
   normalized-raw-text hash when no conditions were extracted at all (so two empty
   parses of different text don't collide). Used to detect an identical strategy
   already saved in the Knowledge Library (`quality.find_duplicate_strategy`) — if
   found, the new one is **not** saved again.
9. **`lesson_extractor.extract_lessons(working_text, sections)`** — runs
   independently of doc_type (always attempted). For each lesson-relevant section,
   splits into bullet/sentence candidates; a candidate becomes a lesson if its
   section is explicitly lesson-shaped (`common_mistakes`/`weaknesses`/`strengths`/
   `psychology`/`checklist`/`risk`/`performance`) OR it contains a recognized
   dictionary term (word-boundary-aware matching — see the "SMA-in-Smart" bug fix
   below). Each candidate gets a title (first ~9 words), a category (mapped from its
   first recognized tag, via `dictionary.LESSON_CATEGORY_MAP`, else a kind-based
   fallback), and a `kind` (`mistake|strength|weakness|psychology|risk_advice|tip|
   example|rule`) purely for reporting. Each is created via the **unmodified**
   `knowledge_engine.lesson.new_lesson()`.
10. **`quality.lesson_dna(lesson)`** — condition-based fingerprint when the lesson has
    real enforceable conditions (wording-independent duplicate detection); falls back
    to a normalized-description-text hash for pure-prose lessons (fixed bug: using
    only category+rule_type+direction for non-enforceable lessons caused *every*
    unrelated Psychology tip with no detected direction to collide as "duplicates" of
    each other).
11. **Auto-save everything**: strategies via `strategy_library.create()` (unless an
    exact DNA duplicate exists), lessons via `storage.save_lesson()` (unless an exact
    DNA duplicate exists, checked both within the same document and against the whole
    existing Knowledge Library), plus a `compiled_documents` row, `knowledge_concepts`
    usage-tracker rows for every dictionary term seen, and `knowledge_relationships`
    rows linking the document → its strategies/lessons → the concepts they use.

**Trading Dictionary** (`knowledge_compiler/dictionary.py`) — extends (imports, never
duplicates) `strategy_parser.CONCEPT_KEYWORDS`/`SESSION_NAMES`, adding: PDH, PDL, PDC,
PWH, PWL, POI, mitigation, inducement, equal highs/lows, premium/discount (structure
terms with no execution primitive yet — recognized/tagged but a rule referencing one
still correctly falls through to "unclear", never guessed); extra real-world aliases
for existing executable concepts (e.g. "demand zone"→support, "bullish OB"→order_block,
"london killzone"→london session); risk terms (stop_loss, take_profit, risk_reward,
risk_per_trade, position_sizing, drawdown) and psychology terms (fomo,
revenge_trading, overtrading, discipline, patience, emotional_trading) — these two
categories are used only for classification/tagging, **never** rewritten into strategy
text (would break the parser's own SL/TP/RR regexes).

**Bugs found and fixed during the Knowledge Compiler build** (self-caught via direct
testing, not user-reported):
1. A document's own title line ("Strategy Name: EMA Pullback **Long**") could get
   scanned as a rule by the parser's concept-keyword fallback, since "Long" reads as
   a bullish direction word — fixed by stripping the title line upstream.
2. Short aliases like "SMA" or "OB" matched as plain substrings inside unrelated
   words ("sma" is literally inside "Smart", so "Smart Money Concepts" was wrongly
   tagged with the SMA indicator) — fixed with word-boundary-aware alias matching
   (`dictionary.alias_in_text()`) everywhere the dictionary is scanned against text.
3. Injecting a section heading the parser doesn't recognize (e.g. "Filters:",
   "Market Conditions:") as a bare text line let it fall through and get misread as a
   bogus unclear condition — fixed by only re-emitting headings for `entry_rules`/
   `exit_rules`.
4. The classifier's "avoid" keyword alone was too weak a lesson signal (common in
   ordinary strategy filter text like "avoid trading during news") and caused clean
   strategies to misclassify as MIXED — removed as a standalone trigger.

---

## 5. DATA LAYER

### Where data comes from

- **Candle data**: 5 exchanges — Binance (native lightweight REST client,
  `data_engine/exchanges/binance.py`) and OKX/Bybit/Bitget/Gate.io (via the `ccxt`
  library, `data_engine/exchanges/ccxt_client.py`). Both implement the common
  `ExchangeClient` interface (`data_engine/exchanges/base.py`):
  - `get_tradeable_symbols(quote) -> {base_asset: exchange_symbol}`
  - `get_ohlcv(symbol, interval, since_ms, limit) -> list[(open_time_ms, open, high, low, close, volume, close_time_ms, quote_volume, trades)]`
  - `get_tickers(quote) -> {symbol: {"price","change_pct","volume"}}`
  - `data_engine/exchanges/registry.py:get_exchange_client(id)` dispatches to
    `BinanceClient` or `CCXTClient(id)`, cached per-id.
- **Coin selection**: `data_engine/symbols.py:pick_top_symbols()` ranks by **CoinGecko
  market-cap** (`data_engine/coingecko_client.py:get_top_market_cap_coins()`), not raw
  exchange volume — this avoids pulling in stablecoins/leveraged tokens/volume-spiking
  new listings. Filters out leveraged-token suffixes (UP/DOWN/BULL/BEAR), a hardcoded
  stablecoin/gold-backed asset list, and non-alphanumeric tickers.
- Only **1-minute candles** are ever fetched/stored (`data_engine/config.py:BASE_INTERVAL = "1m"`).
  Every other timeframe is derived by resampling on demand — a candle is never
  downloaded twice at a different resolution.

### How and where data is stored

Single SQLite file: **`data/database/sindhu.db`**, accessed exclusively through
`data_engine/storage.py` (no other module touches SQLite directly). Connection helper
`get_conn()` (context manager). Schema is applied via `conn.executescript(_SCHEMA)`
using `CREATE TABLE IF NOT EXISTS` everywhere — **fully additive across every phase**,
new columns are added via `ALTER TABLE ... ADD COLUMN` migration functions, never a
destructive rebuild.

**Full schema (`_SCHEMA` in storage.py):**

| Table | Key columns |
|---|---|
| `symbols` | exchange, symbol, added_at — PK(exchange, symbol) |
| `klines_1m` | exchange, symbol, open_time, open, high, low, close, volume, close_time, quote_volume, trades — PK(exchange, symbol, open_time) — **the source of truth** |
| `download_progress` | exchange, symbol, last_open_time, status, updated_at — PK(exchange, symbol) |
| `strategies` | name (PK), file_path, added_at — legacy hand-written strategy registry |
| `backtest_batches` | batch_id (PK), strategy_name, exchange, settings_json, status, created_at, updated_at |
| `backtest_results` | batch_id, symbol, timeframe, status, metrics_json, completed_at — PK(batch_id, symbol, timeframe) |
| `backtest_trades` | batch_id, symbol, timeframe, trade_num, side, entry_time, entry_price, exit_time, exit_price, size, pnl, pnl_pct, exit_reason, stop_loss, take_profit, risk_amount, reward_amount, entry_reason — PK(batch_id, symbol, timeframe, trade_num) |
| `lessons` | id (PK), title, category, description, priority, status, notes, apply_backtesting, apply_paper_trading, apply_evolution, rule_type, direction, conditions_json, created_at, updated_at, **+ version, tags_json, supported_market_types_json, supported_timeframes_json** (added later, additive) |
| `lesson_applications` | id (PK autoincrement), lesson_id, batch_id, symbol, timeframe, applied_at, outcome |
| `activity_log` | id (PK autoincrement), entity, action, message, created_at — capped at most-recent 500 rows |
| `paper_positions` | id (PK), exchange, symbol, direction, entry_price, exit_price, stop_loss, take_profit, size, risk_amount, entry_time, exit_time, pnl, pnl_pct, exit_reason, entry_reason, strategy_id, strategy_name, strategy_version, lesson_ids_json, confidence, market_snapshot_json, tags_json, session, timeframe, market_state, lifecycle_json, reflection_json, status, created_at, closed_at |
| `paper_decision_log` | id (PK autoincrement), exchange, symbol, direction, decision, reason, strategy_id, strategy_name, lesson_ids_json, confidence, market_state, session, timeframe, position_id, market_snapshot_json, created_at |
| `paper_strategy_performance` | strategy_id (PK), strategy_name, trades, wins, losses, total_pnl, avg_rr, score, updated_at |
| `paper_lesson_performance` | lesson_id (PK), lesson_title, usage_count, wins, losses, total_pnl, confidence_avg, score, updated_at |
| `paper_strategy_config` | strategy_id (PK), enabled, priority, supported_coins_json, supported_market_types_json, updated_at |
| `compiled_documents` | id (PK), title, source_type, doc_type, classification_confidence, status, raw_text, sections_json, strategy_ids_json, lesson_ids_json, concepts_json, unresolved_json, clarification_notes_json, tags_json, created_at |
| `knowledge_concepts` | canonical_name (PK), category, aliases_json, usage_count, first_seen_at, last_seen_at |
| `knowledge_relationships` | id (PK autoincrement), from_type, from_id, to_type, to_id, relation, created_at |

**Migrations applied on every `init_db()` call** (idempotent, additive-only):
`_migrate_add_exchange_column` (early multi-exchange upgrade), `_migrate_trade_history_columns`
(adds stop_loss/take_profit/risk_amount/reward_amount/entry_reason to
`backtest_trades`), `_migrate_lesson_meta_columns` (adds version/tags_json/
supported_market_types_json/supported_timeframes_json to `lessons`).

**Storage.py function groups** (≈90 functions total): symbols/progress
(`save_symbols`, `load_symbols`, `load_all_exchanges`, `get_progress`, `set_progress`),
klines (`insert_klines`, `count_rows`, `count_all_rows`, `get_klines_range`,
`db_file_size_bytes`), backtest batches/results/trades (`register_strategy`,
`create_batch`, `get_batch`, `list_recent_batches`, `update_batch_status`,
`get_completed_result_keys`, `save_result`, `save_trades`, `get_trades`,
`search_trades`, `get_batch_results`), lessons (`save_lesson`, `get_lesson`,
`list_lessons`, `delete_lesson`, `record_lesson_application`, `get_lesson_stats`,
`get_batch_lesson_stats`, `get_knowledge_report`), activity (`log_activity`,
`list_activity`), paper trading (`open_paper_position`, `close_paper_position`,
`get_open_paper_positions`, `get_paper_position`, `list_closed_paper_positions`,
`last_closed_paper_position`, `log_paper_decision`, `list_paper_decisions`,
`update_paper_strategy_performance`, `list_paper_strategy_performance`,
`update_paper_lesson_performance`, `list_paper_lesson_performance`,
`get_paper_strategy_config`, `list_paper_strategy_configs`,
`save_paper_strategy_config`), knowledge compiler (`save_compiled_document`,
`get_compiled_document`, `list_compiled_documents`, `touch_knowledge_concept`,
`list_knowledge_concepts`, `save_knowledge_relationship`,
`list_knowledge_relationships`).

### Resampling (`data_engine/resample.py`)

`get_ohlcv(exchange, symbol, interval, start_ms, end_ms)` — reads raw 1m rows via
`storage.get_klines_range`, builds a UTC-indexed dataframe, and if `interval != "1m"`,
applies `df.resample(RESAMPLE_RULE[interval], label="left", closed="left").agg(...)`
with `open=first, high=max, low=min, close=last, volume=sum, quote_volume=sum,
trades=sum`. `RESAMPLE_RULE` maps every supported interval to its pandas rule string
(e.g. `"4h":"4h"`, `"1w":"1W-MON"`).

### JSON structures

See Section 8 for every config file's exact JSON shape. The `StrategyConfig.to_dict()`
shape is documented in Section 4b; the `CompiledDocument.to_dict()` shape in the
Knowledge Compiler subsection of Section 4e.

---

## 6. BACKTESTING ENGINE

### How a backtest runs, step by step

1. **CEO pastes/loads a strategy** → parsed into a `StrategyConfig` (Section 4) →
   validated (must be error-free to run).
2. **`POST /api/backtesting/run`** starts a background job calling
   `backtest_engine.runner.run_mtf_batch(config, exchange, symbols, settings, ...)`.
3. For each symbol (in parallel via a process pool, or sequentially — see below):
   a. **`MultiTimeframeContext(exchange, symbol, config.timeframes)`** fetches every
      referenced timeframe's OHLCV via `resample.get_ohlcv` (`mtf_context.py`).
   b. **`ConfiguredStrategy(config).prepare_context(ctx)`** (`configured_strategy.py`)
      computes every referenced indicator (EMA/SMA/RSI/ATR) on each role's *native*
      resolution frame (a 4H EMA is computed on real 4H bars, never upsampled), plus
      structural concepts (BOS/CHoCH/FVG/Order Block/Breaker Block/Support-Resistance/
      Volume spike/Session/Trend) — only the ones the strategy actually references
      (`config.concepts_used`).
   c. `ctx.build()` merges every non-entry role onto the entry timeframe's index via
      `pd.merge_asof(..., direction="backward")` after `shift(1)`ing each role's own
      frame — this guarantees **zero look-ahead**: a higher-timeframe bar's data only
      becomes visible starting at the entry-timeframe bar that follows its actual
      close. Columns are prefixed `entry_*` / `{role}_*`.
   d. **`engine.run_backtest(df, strategy, settings, ...)`** (`engine.py`) — the core
      simulation. For each bar `i` (vectorized indicator prep, then a plain Python
      loop over rows):
      - If a position is open: check forced exit first (SL/TP hit by intrabar
        high/low — `_check_forced_exit`), else check the strategy's own exit signal
        (`ConfiguredStrategy.on_bar` → AND of `exit_conditions`). On exit: apply
        slippage (`_apply_slippage` — always worse for the trader), subtract
        commission, record realized PnL, close the position.
      - If flat: evaluate entry (AND of `entry_conditions`, then AND of
        `confirmation_conditions` if any, then session filter, then trend filter). If
        a **Knowledge Engine** was passed in, every prospective entry is checked via
        `knowledge_engine.check(df, i, direction)` first — a blocking lesson vetoes
        the entry entirely (Phase 4 integration, optional/backward-compatible). If
        approved: compute SL (`_compute_stop_loss` — fixed_pct/atr_multiple/structure)
        and TP (`_compute_take_profit` — fixed_pct/rr/atr_multiple), size the position
        (`_position_size` — risk-based if a SL exists: `(balance*risk_pct)/stop_distance`;
        else a fixed fraction of equity: `(balance*position_size_pct)/entry_price`;
        capped at 1x balance, no margin/leverage modeled), open the position.
      - Track the running equity curve every bar (realized balance + unrealized PnL
        on any open position).
      - Force-close any still-open position at the last bar (`exit_reason:
        "end_of_data"`).
   e. **`metrics.compute_metrics(trades, equity_curve, initial_balance)`** — see below.
   f. Trades + results saved to `backtest_trades`/`backtest_results` (resumable — a
      `(symbol, timeframe)` combo already marked "completed" is skipped on re-run,
      so an interrupted batch picks up exactly where it left off).
4. **`reports.generate_report(batch_id)`** aggregates every completed
   symbol/timeframe result into one summary (below), writes `report.json` +
   `report.txt` under `data/reports/<batch_id>/`.

**Multiprocessing** (`runner.run_mtf_batch`): when `use_multiprocessing=True` and more
than one symbol remains, each symbol's backtest runs in its own OS process via
`ProcessPoolExecutor` (capped at `min(4, cpu_count-1)` workers — uncapped reliably
exhausted RAM and crashed with `BrokenProcessPool` on an 8GB test machine); only the
main process ever writes to the database. If the pool breaks mid-run, the remaining
symbols automatically fall back to running sequentially rather than being marked
failed. **Pause is not supported mid-flight in multiprocessing mode** (already-
dispatched symbols keep computing) — only Stop is honored between completions; use
`use_multiprocessing=False` for true pause/resume responsiveness.

### Metrics calculated (`metrics.py:compute_metrics`)

- `total_trades`, `wins`, `losses`
- `win_rate` = wins / total_trades × 100
- `final_balance` = last equity-curve value
- `profit_pct` = (final_balance − initial_balance) / initial_balance × 100
- `max_drawdown_pct` = largest peak-to-trough % drop in the equity curve, tracked
  bar-by-bar (running peak, `(peak-eq)/peak*100`, keep the max)
- `avg_win` / `avg_loss` = mean PnL of winning/losing trades
- `profit_factor` = gross profit / |gross loss| (`None` if no losses)
- `risk_reward` = avg_win / |avg_loss| (`None` if no losses)

**Batch-level aggregation** (`reports.generate_report`) additionally computes: overall
win rate/profit/drawdown across every symbol×timeframe combo, average profit factor/
risk-reward, **coin ranking** and **timeframe ranking** (each combo's total trades/
win rate/avg profit/max drawdown/avg profit factor, sorted best-profit-first), best/
worst coin and timeframe (by average profit %), and **session analysis** (every trade
bucketed by its entry time's UTC session — Asian 0-8h, London 8-13h, NY 13-21h,
`session_of_hour()` in `concepts.py` — ranked by total PnL), plus lesson stats
(lessons_applied, trades_approved/rejected_by_lessons via
`storage.get_batch_lesson_stats`).

### Indicator/concept definitions (`concepts.py`) — exact

- **EMA**: `series.ewm(span=period, adjust=False).mean()`
- **SMA**: `series.rolling(period).mean()`
- **RSI**: Wilder-style smoothing — `avg_gain/avg_loss` via
  `ewm(alpha=1/period, adjust=False)`, `100 - 100/(1+rs)`, NaN → 50.0
- **MACD**: `ema(fast=12) - ema(slow=26)`, signal = `ema(macd_line, 9)`, histogram =
  macd − signal
- **ATR**: true range = max(high−low, |high−prev_close|, |low−prev_close|), smoothed
  via `ewm(alpha=1/period)`
- **VWAP**: typical price × volume, cumulative sum reset at each UTC day boundary
- **Volume spike filter**: `volume > rolling_avg(20) × 1.5`
- **Trend filter**: `"up"` if close > EMA(50) else `"down"`
- **Sessions**: Asian 00:00–08:00 UTC, London 08:00–13:00 UTC, NY 13:00–21:00 UTC,
  else `"off_hours"`
- **Swing points**: a bar is a confirmed swing high/low if it's the max/min of a
  `2×lookback+1`-bar centered window, **confirmed `lookback` bars later** (so it's
  never look-ahead)
- **Support/Resistance**: last confirmed swing low/high, forward-filled
- **BOS (Break of Structure)**: close breaks above the most recent confirmed swing
  high (bullish) / below the most recent confirmed swing low (bearish)
- **CHoCH (Change of Character)**: a BOS in the *opposite* direction of the
  currently-established trend (tracked as a running state machine over confirmed
  BOS events) — the first sign a trend may be reversing
- **FVG (Fair Value Gap)**: a 3-candle imbalance — bar `i`'s low > bar `i-2`'s high
  (bullish) or high < bar `i-2`'s low (bearish)
- **Order Blocks**: the last opposite-direction candle before a confirmed BOS —
  tracked as an active zone (low/high) per direction until superseded
- **Breaker Blocks**: an order block that price later closes *through* (invalidating
  it) flips polarity into a breaker block, tracked the same way

### `mtf_context.py` — MultiTimeframeContext (exact)

```python
MultiTimeframeContext(exchange, symbol, timeframes, start_ms=None, end_ms=None)
  # timeframes: {role: tf_string}, must include "entry"
  .is_empty() -> bool          # True if any role's frame came back empty
  .build() -> pd.DataFrame     # call AFTER indicator columns are added to self.frames[role]
```
`build()`: takes the entry frame, prefixes its columns `entry_*`. For every other
role, `shift(1)` its frame (so only the last *closed* bar of that timeframe is ever
visible) and prefix `{role}_*`, then `merge_asof(..., direction="backward")` onto the
entry index. This is the mechanism that guarantees zero look-ahead across timeframes.

---

## 7. API ENDPOINTS

All endpoints are served by FastAPI (`sindhu_web/server.py`) on port **8420**. Every
state-changing request (non-GET/HEAD/OPTIONS, non-`/`, non-`/api/token`, non-`/static`,
non-`/ws`) requires header `X-Sindhu-Token: <token>` (fetched once via `GET
/api/token`). All requests are additionally restricted to loopback or private-LAN
client IPs (`192.168.x.x`, `10.x.x.x`, `172.16-31.x.x`) — a public-internet client is
refused with 403 regardless of token.

`GET /api/token` → `{"token"}` (auto-generated once, stored in `data/config/api_token.json`).

### Home
- `GET /api/nav` → `{"pages": [{"id","label","enabled","icon"}]}`
- `GET /api/home` → see Section 3 (Dashboard/Home module) for the full shape

### Market
- `GET /api/market` → `{"exchange","quote","coins":[{"symbol","price","change_pct","volume","trend","signal","volatility_pct"}]}`

### Data
- `GET /api/data` → `{"exchange","coins":[{"symbol","candles","start","end","status"}],"timeframes","missing_data","total_coins","database_size_bytes"}`
- `POST /api/data/download` → `{"job_id"}`

### Strategies / Backtesting
- `POST /api/backtesting/parse` — body `{"text","name"}` → `{"config","errors","valid"}`
- `POST /api/backtesting/strategies` — body `{"config","tags","strategy_id"?}` → `{"id"}`
- `GET /api/backtesting/strategies?q=` → `{"strategies"}`
- `GET /api/backtesting/strategies/{id}` → `{"config"}`
- `DELETE /api/backtesting/strategies/{id}` → `{"ok"}`
- `POST /api/backtesting/strategies/{id}/favourite?favourite=bool` → `{"ok"}`
- `POST /api/backtesting/strategies/{id}/duplicate` → `{"id"}`
- `GET /api/backtesting/coins` → `{"exchange","symbols"}`
- `POST /api/backtesting/run` — body: `strategy_id`|`config`, `symbols`, `all_coins`,
  `initial_balance`, `risk_pct`, `commission_pct`, `slippage_pct`, `position_size_pct`,
  `start_ms`, `end_ms`, `use_multiprocessing` → `{"job_id"}` (400 with `{"errors"}` if invalid)

### Reports
- `GET /api/reports` → `{"batches"}`
- `GET /api/reports/best-worst/strategies` → `{"ranking","best_strategy","worst_strategy"}`
- `GET /api/reports/{batch_id}` → full report summary (Section 6)
- `GET /api/reports/{batch_id}/trades` → `{"trades"}`
- `GET /api/reports/{batch_id}/export/{fmt}` — fmt=csv → `{"paths"}`; excel/pdf → file download

### Knowledge
- `GET /api/knowledge/categories` → `{"categories"}` (18 fixed values)
- `GET /api/knowledge/report` → Knowledge Score + counts (Section 3)
- `GET /api/knowledge/lessons?q=&category=` → `{"lessons"}` (each with `stats`, `estimated_impact_pct`)
- `GET /api/knowledge/lessons/{id}`
- `POST /api/knowledge/lessons` — body: title, category, description, priority, notes,
  status, apply_backtesting/paper_trading/evolution → created lesson dict
- `PUT /api/knowledge/lessons/{id}` — same body, updates in place
- `DELETE /api/knowledge/lessons/{id}`
- `POST /api/knowledge/lessons/{id}/duplicate`
- `POST /api/knowledge/lessons/{id}/status` — body `{"status"}`

### Knowledge Compiler
- `POST /api/knowledge-compiler/compile` — body `{"text","title"?,"source_hint"?}` →
  full `CompiledDocument` dict
- `GET /api/knowledge-compiler/documents?doc_type=&status=&limit=` → `{"documents"}`
- `GET /api/knowledge-compiler/documents/{id}` → compiled document dict
- `GET /api/knowledge-compiler/concepts` → `{"concepts"}` (usage-tracked dictionary terms)

### Paper Trading
- `GET /api/paper-trading/status` → engine status (Section 3)
- `POST /api/paper-trading/start` / `POST /api/paper-trading/stop` → `{"ok"}`
- `POST /api/paper-trading/run-tick-now` → `{"ok","summary"}`
- `GET /api/paper-trading/settings` → settings dict
- `POST /api/paper-trading/settings` — partial update (any settings field) → updated dict
- `GET /api/paper-trading/positions` → `{"positions"}`
- `GET /api/paper-trading/trades?limit=` → `{"trades"}`
- `POST /api/paper-trading/positions/{id}/close` → `{"ok","trade"}`
- `GET /api/paper-trading/decisions?decision=&limit=` → `{"decisions"}`
- `GET /api/paper-trading/strategy-performance` → `{"performance"}`
- `GET /api/paper-trading/lesson-performance` → `{"performance"}`
- `GET /api/paper-trading/strategy-config/{strategy_id}` → config dict
- `POST /api/paper-trading/strategy-config/{strategy_id}` — body: enabled, priority,
  supported_coins, supported_market_types → `{"ok"}`

### Settings / Backup / System / Jobs / Network / Activity / Search
- `GET /api/settings` / `POST /api/settings` (Section 3)
- `POST /api/backup/create` → `{"backup"}`
- `GET /api/backup/list` → `{"backups"}`
- `POST /api/backup/restore` — body `{"backup_name","confirm"}` (must be `true`) → `{"ok"}`
- `GET /api/jobs` → `{"jobs"}`
- `GET /api/jobs/{job_id}` → job dict
- `POST /api/jobs/{job_id}/pause` / `/resume` / `/stop` → `{"ok"}`
- `GET /api/network` → `{"local_ip","port","url","qr_svg","connected_devices"}`
- `GET /api/activity?limit=` → `{"activity"}`
- `GET /api/search?q=` → `{"coins","strategies","lessons","reports","trades"}`
- `POST /api/system/restart-services` → `{"ok"}` (clears in-memory caches only)

### WebSocket
- `ws://<host>:8420/ws/logs` — one channel for everything live. Every message has a
  `"channel"` field: `"log"` (log lines), `"job"` (started/finished), `"progress"`
  (per-job progress dict), `"sync"` (entity/action/message change notifications —
  strategy/lesson/settings/paper_trading/knowledge_compiler mutations), `"paper"`
  (Paper Trading engine events: engine_started/tick/position_opened/engine_stopped).
  Rejects non-LAN clients at the handshake (code 4403).

---

## 8. CONFIGURATION & SETTINGS

No environment variables anywhere — all configuration lives in JSON files under
`data/config/`, auto-created with defaults on first run
(`data_engine/config.py:load_or_seed()`), and editable live from the dashboard's
Settings page (writes go straight back to these files, no restart needed).

| File | Fields (defaults) |
|---|---|
| `exchanges.json` | `enabled: ["binance","okx","bybit","bitget","gate"]`, `default: "binance"` |
| `coins.json` | `num_coins: 50`, `quote_asset: "USDT"` |
| `timeframes.json` | `base_interval: "1m"`, `supported: [1m,3m,5m,15m,30m,1h,2h,4h,6h,12h,1d,1w]` |
| `app_settings.json` | `history_days: 365`, `request_delay_seconds: 0.25`, `klines_limit: 1000`, `max_retries: 5`, `watch_interval_seconds: 300`, `default_risk_pct: 1.0` |
| `web_settings.json` | `theme: "dark"`, `refresh_speed_seconds: 10` |
| `backup_settings.json` | `auto_backup_enabled: true`, `interval_hours: 24` |
| `api_token.json` | `{"token": "<32-hex-char secret>"}` — auto-generated once, never regenerated unless deleted |
| `paper_trading_settings.json` | `dry_run: true`, `initial_balance: 10000.0`, `risk_pct_default: 1.0`, `max_open_trades: 5`, `cooldown_minutes: 15`, `priority_rule: "confidence"` (confidence\|win_rate\|profit\|manual), `opposite_signal_policy: "block"` (block\|allow\|close_and_reverse), `coin_filter_top_n: 20`, `tick_interval_seconds: 60`, `lookback_days: 20`, `lesson_default_timeframe: "1h"`, `lesson_default_sl_pct: 2.0`, `lesson_default_rr: 2.0`, `daily_goal_pct: 2.0` |

**Ports:** web dashboard always on **8420** (`sindhu_web/network.py:DEFAULT_PORT`),
no other network services.

**Folder layout** (`data_engine/paths.py`): `data/database/`, `data/market_data/`,
`data/logs/`, `data/reports/`, `data/settings/`, `data/history/`, `data/config/` — all
created by `ensure_folders()` on every startup; `migrate_legacy_files()` moves a
pre-restructure flat `data/sindhu.db` into the new layout automatically if found.

**Security model** (`sindhu_web/security.py`): appropriate for a single-user local/LAN
tool, not full auth infra. Every request must originate from loopback or a private LAN
IP range. Read-only GET/HEAD/OPTIONS and `/`, `/api/token`, `/static/*`, `/ws/*` are
always open; every other request needs the `X-Sindhu-Token` header matching the
locally-generated token.

---

## 9. CURRENT STATUS

### Complete (all verified live against real data, not just unit-level)

| Phase | What | Status |
|---|---|---|
| 1 | Data System (multi-exchange download engine, SQLite, desktop dashboard) | ✅ |
| 2 / 2.1 | Backtesting Engine (single + multi-timeframe, bilingual parser, strategy library, multiprocessing, rankings, export) | ✅ |
| 3 | Professional Dashboard + Web Interface (FastAPI + JS SPA) | ✅ |
| 4 | Knowledge Engine (CEO lessons gating backtests) | ✅ |
| 4.5 | Local Remote Control, Mobile Access, Real-Time Sync (LAN QR connect, WebSocket live sync, autosave-everywhere) | ✅ |
| — | Dashboard Professional Redesign (institutional UI overhaul, sidebar/topbar/search) | ✅ |
| 5 | Paper Trading Engine (24/7 automatic, simulation-only, full 20-stage pipeline) | ✅ |
| — | Knowledge Compiler (Strategy + Lesson Engine document-understanding upgrade) | ✅ |

Current real data volume: 50 coins on Binance, ~24.7 million 1-minute candles,
~3.2 GB database.

**Paper Trading Engine current state:** stopped (`running: false`), `dry_run: true` —
it will not place any simulated trade until explicitly started from the dashboard or
API. This is the CEO's own current configuration, not a code default being enforced.

### Not yet built (explicitly excluded so far, each phase said "do not build this yet")

- Reflection and Evolution as **standalone dashboard pages/workflows** — both exist
  today only as an internal per-trade step inside Paper Trading (see
  `paper_trading/reflection.py` and `paper_trading/evolution.py`); there is no
  separate "Reflection" or "Evolution" nav page yet even though both are reserved in
  `NAV_PAGES` with `enabled: False`.
- Live/real trading execution — Paper Trading is simulation-only by explicit design;
  no code path in this project ever places a real order.
- News monitoring, Telegram alerts, Cloud Deployment — reserved nav slots
  (`enabled: False`), no backend at all yet.
- Any AI/ML-based decision-making anywhere — every "engine" in this project (parser,
  classifier, confidence score, reflection, evolution) is deterministic rule-based
  code, by explicit, repeated design constraint across every phase.

### Known bugs / limitations (currently accepted, not blocking)

- **Parser**: only one SL/TP/RR/Risk directive recognized per line (compact "SL 2% TP
  4% Risk 1%" only catches the first); RR must be literal "1:N" notation; SL
  "structure" type doesn't recognize FVG as an anchor (only order block/swing/
  structure/breaker); no OR-alternative entry setups within one strategy (all entry
  conditions are AND'd).
- **Multiprocessing backtests**: no true pause mid-flight (already-dispatched symbols
  keep computing; only Stop is honored between completions).
- **Knowledge API**: `POST/PUT /api/knowledge/lessons` doesn't expose `tags`,
  `supported_market_types`, or `supported_timeframes` in its request model even
  though the underlying `Lesson` schema/DB supports them (only settable via the
  Knowledge Compiler pipeline or direct DB access).
- **Evolution score**: always reported as `None` on the Home page — no standalone
  Evolution scoring exists outside Paper Trading's internal per-strategy/lesson
  performance tracking.
- **Browser-preview automation tooling** (documented across multiple phases as an
  environment quirk, not an app defect): the automated browser-preview tool used
  during development has repeatedly failed to reflect hash-based SPA navigation and
  full reloads reliably in this environment, even for long-working pages — verified
  each time via direct HTTP API testing and raw static-file fetches instead, which
  are fully reliable.
- A previously-existing placeholder strategy ("Unnamed Strategy") disappeared from
  the strategy library at some point during Phase 5 cleanup; cause not pinpointed,
  held no real CEO-authored content, not treated as blocking.

---

## 10. HOW TO EXTEND

### Add a new strategy input format / new parser keyword

Never edit condition-parsing regex logic in `strategy_parser.py` directly unless
fixing a genuine bug in existing behavior. To recognize a new phrasing:
1. Add the new alias(es) to `knowledge_compiler/dictionary.py` (`_entry(...)` calls),
   mapping to an existing `concept_key` if the underlying engine already computes
   that concept (in `concepts.py`), or `concept_key=None` if it's just for
   classification/tagging with no execution primitive yet.
2. If it needs actual condition-parsing (not just tagging), add a small, contained
   text-normalization step in `knowledge_compiler/rule_extractor.py` (following the
   pattern of `_split_combined_directives`/`_normalize_spoken_phrasing`) that rewrites
   the new phrasing into wording `strategy_parser` already understands, **before**
   calling `parse_strategy_text()`. Never modify the parser's own regex tables to
   special-case new wording — that risks regressing existing, proven parsing.
3. If it needs a genuinely new **executable concept** (e.g., PDH/PDL as a real
   tradeable level, not just a recognized tag): implement the calculation in
   `backtest_engine/concepts.py` (vectorized, causal/no-look-ahead, following the
   existing function style), wire it into `configured_strategy.py:prepare_context()`
   (gated on `"your_concept" in config.concepts_used`) and `_eval()` (condition
   evaluation), and mirror the same wiring in `knowledge_engine/condition_eval.py`
   and `paper_trading/frame_builder.py` if lessons/paper-trading should also be able
   to reference it. This is the only place that touches core execution logic — do
   this deliberately and test against the existing backtest suite for regressions.

### Add a new dashboard module/page

1. Backend: new file under `sindhu_web/api/your_module.py` with an `APIRouter()`;
   register it in `sindhu_web/server.py`'s router tuple and import list.
2. Add a nav entry to `NAV_PAGES`/`NAV_ICONS` in `sindhu_web/api/home.py`
   (`enabled: True` makes it appear immediately — this is the existing "reserved but
   hidden" pattern already used for Reflection/Evolution/News/Telegram).
3. Frontend: add a `renderYourModule()` function to `sindhu_web/static/js/app.js`
   following the existing pattern (capture `activeRouteToken`, check
   `isStaleRoute()` before writing to `content.innerHTML`, use `apiGet`/`apiPost`),
   and add it to the `PAGES` map.
4. If it needs new persisted state: add new tables to `data_engine/storage.py`'s
   `_SCHEMA` using `CREATE TABLE IF NOT EXISTS` (never alter/drop an existing table),
   and if extending an existing table, add a new `_migrate_*_columns` function using
   `ALTER TABLE ... ADD COLUMN`, called from `init_db()`. This additive-only pattern
   has been followed in every phase of this project and must not be broken.

### Add a new exchange

1. Implement `data_engine/exchanges/base.py:ExchangeClient`'s three methods
   (`get_tradeable_symbols`, `get_ohlcv`, `get_tickers`) either natively (like
   `binance.py`) or via a `ccxt` wrapper (like `ccxt_client.py` — if `ccxt` already
   supports the exchange, add its id to `CCXT_EXCHANGE_IDS` in
   `exchanges/registry.py` and it likely works with zero new code, `CCXTClient` is
   already generic).
2. Add the exchange id to `data/config/exchanges.json`'s `"enabled"` list (or let the
   Settings page do it).
3. No changes needed anywhere else — `data_engine.storage`, `resample`, the
   Backtest Engine, and Paper Trading are all already exchange-agnostic (every
   function takes an `exchange` string parameter and reads/writes scoped to it).

### General extension principles this codebase follows (do not violate)

- **Never rebuild a working module to add a new one** — every phase so far has
  extended existing code (new files, new additive DB columns/tables, new API
  endpoints) rather than rewriting proven logic. When in doubt, wrap/reuse the
  existing function rather than reimplementing its behavior.
- **Never guess** — every parser/validator/classifier in this project reports
  "unclear"/"needs clarification"/"missing" rather than inventing a plausible-looking
  value. Any extension should preserve this: prefer surfacing an honest gap over a
  silent default, except where a *safe, disclosed* default is explicitly appropriate
  (as Knowledge Compiler's validator does for non-safety-critical fields like RSI
  period, but never for a missing stop-loss with nothing to borrow from).
- **No AI/ML** — this is a hard, repeated constraint across every phase. Any new
  "smart" behavior should be deterministic rule-based logic, transparent and
  explainable, not a model call.
