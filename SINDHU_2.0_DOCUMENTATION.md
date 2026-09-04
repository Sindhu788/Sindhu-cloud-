# SINDHU 2.0 — Poori Documentation (A to Z)

> **Master Task 5, Part 2 — 2026-09-04.** Ye document `PROJECT_DOCUMENTATION.md` ka patch nahi hai — ek bilkul fresh, mukammal rewrite hai jo project ke shuru se lekar aaj tak ka **poora current state** cover karta hai: Grand Feature Expansion ke baad, Master Task 3 (Self-Learning Engine + Challenge Mode), Master Task 4 (Self-Learning cloud visibility, Evolution Engine bug fix, Strategies staleness fix, Telegram multi-challenge), aur Master Task 5 (Confidence Threshold Investigation + Near-Miss Log) tak. Har number is doc mein **live database se abhi (2026-09-04) nikala gaya hai** — koi purana estimate copy-paste nahi kiya gaya. Agar koi cheez verify nahi ho saki, "TBD" likha hai — guess nahi kiya gaya.

---

## 1. Executive Summary

**SINDHU** ek institutional-grade, self-learning crypto trading system hai jo ek akele bande (CEO) ne, part-time, **Claude Code** ke saath milkar banaya hai — koi team nahi, koi funding nahi, sirf ek laptop (`E:\sindhu`) aur ab ek free-tier cloud deployment (Render).

**Core mission**, jo `ai_integration/__init__.py` mein likha hua hai, poore project ka north star hai:

> *"AI is only a temporary teacher. SINDHU must become independent after learning. Trading Engine must never depend on AI."*

Matlab: AI sirf **import ke waqt, ek dafa** kaam karta hai — jab CEO koi strategy paste karta hai, AI usay poori tarah samajh kar ek structured `StrategyConfig` mein badal deta hai. Uske baad Backtesting, Paper Trading, aur Telegram Signals kabhi AI call nahi karte — sab kuch pehle se compiled, deterministic data se chalta hai. Ye rule aaj bhi zero-exception hai (grep se baar-baar verify kiya gaya hai).

SINDHU ab sirf ek backtest tool nahi hai — ye ek **poora chalta-phirta platform** hai: 24/7 paper trading, live Telegram signals, ek khud-mutate hone wala Evolution Engine, ek naya Self-Learning discovery system, Challenge Mode (target-based gamified tracking), aur ek cloud-deployed dashboard jo kahin se bhi dekha ja sakta hai.

---

## 2. Poori Architecture — Har Module

| # | Module | Kaam ek line mein |
|---|---|---|
| 1 | `data_engine/` | Candle data download/storage/resample + poora database layer (SQLite local, Postgres cloud) |
| 2 | `backtest_engine/` | Strategy parser, validator, multi-timeframe backtest engine, JSON-file Strategy Library |
| 3 | `knowledge_engine/` | CEO ke manually diye "Lessons" ko evaluate/apply karta hai |
| 4 | `knowledge_compiler/` | Pasted document ko deterministic (bina AI ke) tarike se Strategy+Lessons mein compile karta hai |
| 5 | `ai_integration/` | AI Knowledge Learning Engine — sirf import ke waqt, structured extraction, self-building dictionary |
| 6 | `paper_trading/` | 24/7 simulated live trading engine + Telegram + Challenge Mode + Near-Miss Log (sabse bada module) |
| 7 | `strategies/` | Base `Strategy`/`Signal` interface + JSON Strategy Library storage |
| 8 | `evolution_engine/` | Genuine Evolution Engine — BOT-owned strategy lineages ko khud mutate karta hai (Governor, Champion, rollback) |
| 9 | `self_learning_engine/` | Naya (Master Task 3) — khud se naye strategy combinations discover/validate karta hai, LOCAL-ONLY |
| 10 | `sindhu_strategy/` | SINDHU Strategy Generator — daily naye candidate strategies (1 AI + 10 deterministic) |
| 11 | `automation_pipeline/` | Auto backtest → optimize → compare → paper trading handoff |
| 12 | `sindhu_web/` | FastAPI web server (LOCAL, poora feature set) — REST API, WebSocket, static frontend |
| 13 | `cloud_runtime/` | Halka, alag cloud entrypoint (Render/Railway) — sirf Paper Trading + Telegram + login |
| 14 | `dashboard/` | Purana PySide6 desktop GUI (2 tabs, legacy, web hi primary hai) |
| 15 | `external_signals/` | Bahar se (non-SINDHU) aane wale signals ko track karne ka module |
| 16 | `data/` | Saara persistent data — SQLite DB, config JSON, logs, checkpoints |

### Local vs Cloud — Kya Kahan Chalta Hai (Aur Kyun)

Ye split is project ki sabse important architectural decision hai:

- **Local (`sindhu_web/server.py`)** — sab kuch. Backtesting, Evolution Engine, Self-Learning Engine, AI Center, Strategy Import — in sabko **poori historical candle database + heavy compute** chahiye, jo sirf local machine par hai.
- **Cloud (`cloud_runtime/app.py`)** — jaan-boojh kar halka rakha gaya hai. Sirf Paper Trading engine, Telegram signal system, aur ek login-gated dashboard. `cloud_runtime/app.py` ka apna module docstring explicitly likhta hai ke ye kabhi `backtest_engine.runner`, `backtest_engine.mtf_worker`, `backtest_engine.optimizer`, `evolution_engine.engine`/`governor`, `ai_integration` ki extraction pipeline, ya `automation_pipeline` import nahi karta — ek automated test (`tests/test_cloud_runtime.py`) is baat ko permanently lock karta hai, taake koi bhi future change galti se cloud ko bhaari na bana de.
- **Kyun ye split zaroori hai:** Cloud ka Postgres schema (`data_engine/db_backend.py`) jaan-boojh kar `klines_1m`, `backtest_*`, `self_learning_attempts/cycles` jaisi tables EXCLUDE karta hai. Backtest/Evolution/Self-Learning teeno ko poori 1-minute candle history + bhaari compute chahiye — Render ke free tier par ye possible hi nahi hai.
- **Result:** CEO Render URL se apna Paper Trading + Telegram dashboard kahin se bhi dekh sakta hai (mobile se bhi), jabke asli "dimagh" wala kaam (Evolution, Self-Learning, naye strategy discovery) sirf local machine par hota hai jab CEO apna laptop chalata hai.

---

## 3. Strategy System — A to Z Ki Poori Kahani

Ek strategy jo CEO ke paste karne se lekar ek real Telegram signal tak jaati hai, is poore pipeline se guzarti hai:

1. **Input**: CEO ek YouTube link, PDF/DOCX/TXT file, ya seedha text paste karta hai (`ai_integration/`).
2. **AI Extraction (ek dafa)**: `deep_understanding.py` provider-chain (CEO ka active provider → Claude → Groq → OpenAI → Gemini → DeepSeek → Offline Mode) se poori strategy samajhta hai — entry/exit/SL/TP/risk/sessions/hidden rules sab. Confidence >=60% par direct "Automation Ready" ban jaati hai.
3. **StrategyConfig Construction**: `strategy_builder.py` AI ke JSON output ko seedha `StrategyConfig`/`Condition`/`Lesson` objects mein banata hai — koi unknown vocabulary condition `type="raw"` (safe fallback) mein demote ho jaati hai.
4. **Validator**: `backtest_engine/validator.py` check karta hai ke config safe hai (missing SL/TP/entry/exit to nahi) — **Incomplete Lock** yahin lagti hai: agar extraction genuinely incomplete hai, strategy hamesha ek warning ke saath dikhti hai, kabhi silently "fair test" jaisi nahi lagti.
5. **50-Coin Backtest**: `backtest_engine/runner.py` + `mtf_worker.py` top-50 coins par multi-timeframe simulation chalate hain — 11 named debug stages ke saath, koi silent crash nahi.
6. **Metrics + Why-Win/Why-Loss**: `metrics.py` win rate/profit factor/drawdown/Sharpe nikalta hai; Signal Explainer (`paper_trading/signal_explainer.py`) plain-language explanation aur A+/A/B/C grade deta hai.
7. **Confirmation-Strictness Variants**: automation_pipeline ke through loose/strict confirmation variants automatically generate hote hain (tags: `confirmation_optimizer_variant`, `level:strict`/`level:loose`).
8. **Strategy Lifecycle**: har strategy ka apna lifecycle track hota hai (dashboard page `strategy_lifecycle`).
9. **Paper Trading Activation**: CEO (ya auto-activation logic) strategy ko Paper Trading mein "on" karta hai — `paper_trading/engine.py` isay 24/7 simulated live market par chalata hai, **bilkul wahi compiled `ConfiguredStrategy`** use karke jo backtest ne use kiya tha (koi dobara text-parsing nahi).
10. **Confluence + Statistical Gate**: har real signal `paper_trading/confluence.py` (4-factor score) aur `pattern_stats.py` (Wilson 25-trade gate) se guzarta hai.
11. **Telegram Signal**: agar High Confidence tier clear hoti hai (dono gates), signal Telegram par jata hai — confidence-filtered, profitable/under-evaluation label, risk disclaimer, aur agar Challenge Mode se scoped hai to us challenge ka naam bhi.
12. **Tracking**: har signal `telegram_message_log` mein permanently log hota hai; agar High Confidence na mile to ab (Master Task 5 se) **Near-Miss Log** mein reason ke saath record hota hai.

---

## 4. Current Strategy Numbers (Live Database Se, 2026-09-04)

- **Total strategies** (Strategy Library, `strategies/library/*`): **154** (paper trading overview API se verified)
- **Genuinely Profitable** (>= 25 closed trades AND net positive live PnL — same definition Telegram bhi use karta hai): **sirf 1 / 154**
- **Under Evaluation** (baaki sab — ya to 25 trades nahi hue, ya net negative hain): **153 / 154**
- **Currently active in Paper Trading** (`in_paper_trading` flag True): **39**
- **Total paper positions ever opened**: **672** (2026-08-29 se 2026-09-04 tak, ~6 din)
- **Closed positions**: **545**; **Open right now**: **127**
- **Aggregate closed PnL across ALL strategies combined**: **-$60.29** (halka negative — system abhi bhi apna real edge dhoond raha hai)

**Honest reading:** System abhi "building" phase mein hai. 154 strategies ka bohot bada hissa (153) abhi statistically prove nahi hua — na profitable, na losing, sirf "abhi data ikattha ho raha hai." Ye number khud Section 8 (Telegram) aur Section 6 (Confidence Threshold) ke honest findings se seedha juda hua hai.

---

## 5. Evolution Engine — Asli Current Status

**Kya karta hai:** BOT-owned strategy "lineages" (`bot_strategies` table, `strategies/library/*.json` se bilkul alag, kabhi CEO khud nahi banata) ko khud analyze → mutate → archive → rank karta hai, bina kisi AI call ke — purely statistical.

**Real current numbers (live DB se):**
- Total BOT lineages: **198**
- Sab abhi tak **generation 1 par hain (max generation = 1)** — kisi ek ne bhi kabhi mutate nahi kiya, chahe 6 din se system chal raha ho
- Sirf **107 / 198** ke paas koi real backtest data hai (baaki abhi bhi 0-trade hain)
- Ek hi evolution job kabhi bana hai (`evo_1788039735952`, created 2026-08-29), **iska current status "stopped" hai** (last update 2026-09-04T02:32)

**Master Task 4 mein mila hua aur fix kiya gaya bug (evidence ke saath):** Chha din tak Evolution Engine ne EK bhi generation produce nahi ki. Do alag bugs mile:
1. **Queue starvation**: Governor ki queue sirf 20 slots ki thi, lekin 198 lineages the — aur queue selection mein koi ordering nahi thi, isliye har baar wahi pehli 20 (alphabetically `BOT_S001`-`BOT_S020`) queue mein aati thin, kabhi baaki 178 ko mauka hi nahi milta tha.
2. **Scoring bug**: naye (0-trade) lineages ka score formula unhe 27.5 (bohot "urgent") deta tha jabke asal mein unke paas koi data hi nahi tha — is wajah se har tick ka poora 5-experiment budget hamesha inhi guaranteed-to-fail lineages par khatam ho jata tha.

Dono fix ho chuke hain (`evolution_engine/governor.py`'s queue ab "evict-the-worst" logic use karti hai; `engine.py` ab 0-trade lineages ko skip karta hai). **Lekin fix hone ke baad bhi abhi tak koi naya generation nahi bana** — kyunki evolution job khud "stopped" state mein hai. Isay dobara "Start" karna CEO ka apna operational step hai.

**Governor limits (kabhi weaken nahi kiye gaye):** `MAX_QUEUE_SIZE=20`, `MAX_EXPERIMENTS_PER_RUN=5` (ek tick mein max 5 naye experiments), `MAX_GENERATIONS_PER_STRATEGY=25`, `CPU_LIMIT_PERCENT=60%`, `RAM_LIMIT_PERCENT=80%`. Ye limits system ko apna hi laptop overload karne se rokte hain.

---

## 6. Self-Learning Engine — Naya System (Master Task 3)

**Kya hai, aur Evolution se kaise alag hai:** Evolution Engine EXISTING lineages ko mutate karta hai. Self-Learning Engine bilkul naye strategy **combinations discover** karta hai — do alag time-periods par test karke, sirf tab accept karta hai jab combination genuinely robust nikle.

**Files:** `discovery_cycle.py` (orchestrator), `candidate_builder.py`, `combination_scorer.py`, `validation_gate.py` (safety gates), `explainability.py`, `memory.py`, `ai_advisor.py`.

**Safety gates (`validation_gate.py`, sab live code se verified):**
- **Mandatory out-of-sample validation** — do ALAG time periods par backtest hota hai, dono pass karna zaroori
- **Minimum sample size**: `MIN_TRADES_PER_PERIOD = 25` — **wahi Wilson gate threshold** jo baaki poore system mein hai, koi naya/softer number invent nahi kiya gaya
- **Dual filter**: minimum **1:2 Risk:Reward** (`MIN_RISK_REWARD = 2.0`) AND ek genuinely high win rate, jo **real currently-profitable strategies ke against benchmark** hoti hai (koi hardcoded arbitrary number nahi)

**Current status (live DB se, honest):** **ZERO discovery cycles kabhi chali hain, ZERO attempts logged hain.** `self_learning_cycles` aur `self_learning_attempts` dono tables khaali hain. System bana hua hai, wired hai, dashboard par visible hai — lekin abhi tak kabhi actually run nahi hua.

**Current limitation:** Self-Learning Engine **local-only** hai. Cloud ka Postgres schema deliberately `self_learning_attempts`/`self_learning_cycles` tables exclude karta hai — kyunki discovery cycles ko poori historical candle database + real backtest pipeline chahiye, jo halke cloud runner mein nahi hai (bilkul Evolution/Backtesting jaisi wajah se).

**Master Task 4 mein fix hua:** Pehle cloud dashboard par Self-Learning Engine ka koi nav link hi nahi tha — CEO ko pata bhi nahi chal sakta tha ke ye feature exist karta hai. Ab cloud nav mein ek entry hai ("Intelligence" group ke andar) jo khulne par ek saaf, bilingual explanation deta hai ke ye feature kyun cloud par available nahi hai — silent 404 ki jagah.

---

## 7. Paper Trading System

**Kaam:** Saved strategies ko real-time simulated market data par 24/7 chalana — same compiled `ConfiguredStrategy` jo backtest use karta hai.

**Do-group split:** Har strategy "Profitable" (>=25 closed trades AND net positive PnL) ya "Under Evaluation" (baaki sab) mein classify hoti hai — Section 4 ke real numbers ke hisaab se, abhi sirf 1 strategy "Profitable" group mein hai.

**Per-strategy controls:** `paper_strategy_config` table se har strategy ka apna priority, supported coins, market types set kiye ja sakte hain.

**5-coin cap (per strategy)**: `risk_manager.py` mein `max_open_trades` default = **5** — ek strategy kisi bhi waqt 5 se zyada coins par open position nahi rakh sakti. (Portfolio-wide, cross-strategy combined view alag hai — `portfolio.py` mein.)

**Currently active:** 39 strategies `in_paper_trading=True` hain, 30 distinct strategies ke paas is waqt kam se kam ek open position hai.

---

## 8. Telegram Signal System — Poora Current Behavior

**Confidence filtering:** `telegram_bot.evaluate_auto_send_tier()` — HIGH tier (`evaluate_auto_send`) pehle try hota hai, phir LOW tier (`evaluate_auto_send_low_tier`) fallback. Default setting `auto_send_high_confidence_only=True` ka matlab: sirf HIGH tier hi Telegram par jata hai, LOW-tier-qualifying signal dashboard par dikhta hai lekin channel par nahi jata.

**Profitable vs Under-Evaluation labeling:** `_profitability_label()` har signal message mein plainly likhta hai ke ye strategy ka "real record" hai ya "abhi build ho raha hai" — Section 4 ke same definition (25+ trades, net positive) use karke.

**Risk disclaimer:** `PROFITABLE_RISK_DISCLAIMER` har profitable-strategy signal par **bina exception ke** attach hota hai.

**Challenge Mode attribution (Master Task 4 mein add hua):** Agar 2-3 challenges ek saath active hon, signal ab bata sakta hai ke ye specifically KIS challenge se related hai — `_multi_challenge_tags()` har active challenge ka scope check karta hai (strategy + optional coin), aur match hone par uska label (HTML-escaped, taake special characters delivery na todein) message mein add karta hai. Purana single-challenge system (`challenge_mode.py`) bhi alag se, parallel chalta hai.

**Near-Miss Log (Master Task 5, naya):** Har signal jo generate hua lekin High Confidence tak nahi pahuncha, ab permanently log hota hai (ek position ke liye ek dafa) — confluence ratio/count, statistical sample count, aur exact reason ke saath. Telegram Dashboard page par apna section hai, distribution bands ke saath.

**Telegram-specific analytics** (`telegram_analytics.py`, pehle se maujood tha): total signals sent, wins, losses, win rate %, total PnL, best-performing strategy — sab sirf Telegram-SENT signals par, `list_telegram_signal_outcomes` se.

**Honest current status:** `telegram_message_log` mein 45 total messages hain, sab `daily_report` (33) ya `manual` (12) trigger type ke — **ZERO automatic sends ever succeeded**. Section 6 (niche) ye poori tarah explain karta hai kyun.

---

## 9. Challenge Mode — Poora Current Feature List

Do parallel systems: purana single-challenge (`challenge_mode.py`) aur naya multi-challenge (`challenge_multi.py`, `challenges` table, **max 3 simultaneously active**).

Poori feature list (sab verified working, `get_challenge_full_analysis()` se real data ke saath test kiya gaya):
- **Adaptive Risk Suggestion** — specific % (e.g. real test mein `1.524%` mila, vague nahi)
- **Best Historical Period Finder** — kab ye target realistically achieve hua hota
- **Challenge Difficulty Rating** — Easy/Moderate/Hard/**Extremely Unlikely**
- **Compound vs Fixed-Risk Toggle** — challenge banate waqt choose kar sakte hain
- **Strategy Rotation Suggestion** — real regime-dependent performance se
- **Custom Deadline Flexibility** — extend/shorten bina recreate kiye
- **Achievability Score Trend Line** — 7-din ka trend, sirf ek snapshot nahi
- **AI Explanation Layer** — real Groq-generated explanation
- **Scope to strategy/coin** — ab UI se bhi set ho sakta hai (pehle sirf API mein tha, Master Task 4 mein form add hua)

**Current state:** Is waqt **0 active challenges** hain (verification ke baad archive kiye gaye, real data corrupt nahi hui).

---

## 10. Cloud Deployment — Poori Kahani

**Kyun ek alag lightweight cloud app banaya gaya:** `sindhu_web/server.py` import hote hi poora heavy stack (backtesting, evolution, AI Center) le aata hai — "thoda sa" import karne ka koi tarika nahi. Isliye `cloud_runtime/app.py` apna separate, minimal FastAPI app banata hai.

**Cloud par kya chalta hai:** Paper Trading engine, Telegram signal system, login-gated dashboard — bas. `strategy_overview`, `telegram_dashboard`, `signal_tracker`, `challenge_mode`, aur (informational-only) `self_learning` nav entries.

**Kya LOCAL-only reh gaya:** Backtesting, Evolution Engine ka actual tick-loop, AI Center/strategy import pipeline, automation_pipeline — inko poori historical candle database chahiye jo Render ke free tier par practical nahi.

**Render + Postgres setup:** `DATABASE_URL` set hone par `data_engine/db_backend.py` automatically Postgres use karta hai (curated schema — `POSTGRES_SCHEMA`), warna local SQLite file. Same `data_engine.storage` code dono ke liye kaam karta hai.

**Login/security system:** `sindhu_web/auth.py` + `auth_credentials`/`auth_sessions` tables — session-based login gate cloud runner ke liye.

**Deployment history — real bugs jo mile aur fix hue:**
1. **WiFi-restriction bug** — kuch networks se cloud app access nahi ho pata tha
2. **Login-persistence bug** — session properly persist nahi ho raha tha
3. **Evolution Engine dormant-queue bug** — Section 5 mein poori detail
4. **Empty-backtest-row bug (Strategies dual-row staleness)** — Master Task 4 mein mila: `_strategy_last_batch_result()` sirf ek fixed, global top-100-most-recent batch window mein dhoondta tha, jo background Evolution/Self-Learning candidate backtests se hamesha crowd ho jata tha. Fix: agar window mein na mile to ek targeted per-strategy fallback lookup (`storage.latest_completed_batch_for_strategy_name`) use hota hai. Real result: pehle 154/154 strategies "backtest: None" dikha rahi thin, fix ke baad 75/75 active (non-archived) strategies ka real snapshot mil gaya.

**Current known limitations:**
- **Free-tier sleep behavior** — Render 15 min inactivity ke baad so jata hai, agla real visit 30-60 second cold-start leta hai. `CRON_JOB_SETUP.md` (Master Task 4) mein iska free fix documented hai (cron-job.org se har 10 min `/health` ping) — **lekin ye setup abhi bhi CEO ka apna manual step hai, khud-ba-khud nahi hua**.
- **Self-Learning Engine cloud par sirf informational hai**, actually chalta nahi (Section 6).

---

## 11. Database / Infrastructure

- **Local**: SQLite, ek hi file (`data/database/sindhu.db`), WAL mode — desktop aur web dono ek saath safely share karte hain.
- **Cloud**: Postgres (jab `DATABASE_URL` set ho) — curated schema, sirf Paper Trading/Telegram/Challenge Mode ke liye zaroori tables.
- **Data flow**: ek-tarfa (one-way) — local ka poora backtest/evolution/self-learning kaam kabhi cloud ko sync nahi hota (aur na hi hona chahiye, kyunki cloud ka schema unhe store hi nahi kar sakta). Cloud apna khud ka Paper Trading/Telegram data independently accumulate karta hai.
- **Backup approach**: Local ka rolling 6-hourly backup + weekly 2-mahine-retention snapshot (`paper_weekly_reports`/snapshot system, Grand Feature Expansion se). Purane multiple `.db` backups clean kiye ja chuke hain (space recovery, `PROJECT_DOCUMENTATION.md` Section 18 mein history hai).

---

## 12. Safety Gates — Jo Kabhi Weaken Nahi Karne (Poori List)

| Gate | Kahan | Kya protect karta hai |
|---|---|---|
| **Wilson Score Gate** | `pattern_stats.py`, `MIN_SAMPLE_SIZE=25`, `GOOD_LOWER_BOUND=0.55` | Chhoti sample size se galat "ye pattern reliable hai" conclusion nikalne se rokta hai (95% confidence interval) |
| **Evolution 100-Trade Gate** | `evolution_engine/rollback.py`, `TRADE_THRESHOLD_STEP=100` | Ek lineage ko sirf har 100 completed trades par hi evolve hone deta hai — bohot jaldi/bohot kam data par mutate hone se rokta hai |
| **Rollback** | `evolution_engine/rollback.py` | Ek naya mutation agar purane se worse nikle to automatically wapas roll ho jata hai |
| **Confluence Threshold** | `paper_trading/confluence.py` + `telegram_bot.py` (`auto_send_min_confluence_ratio=1.0`, `auto_send_min_confluence_count=3`) | Kamzor setups ko High Confidence label milne se rokta hai |
| **Signal Freshness Gate** | `telegram_bot.py` (`signal_freshness_minutes=15`, `signal_price_drift_pct=0.5`) | Purana ya price-drifted signal Telegram par jaane se rokta hai — jab tak entry ka mauka hi na guzar chuka ho |
| **Incomplete Lock** | `ai_integration/extraction_lock.py` | Adhoori (incomplete) extraction wali strategy ke results ko "fair test" jaisa dikhne se rokta hai |
| **5-Coin Cap (per strategy)** | `paper_trading/risk_manager.py`, `max_open_trades=5` | Ek strategy ko ek hi waqt bohot zyada coins par overexposed hone se rokta hai |
| **Governor Limits** | `evolution_engine/governor.py` | `MAX_QUEUE_SIZE=20`, `MAX_EXPERIMENTS_PER_RUN=5`, `MAX_GENERATIONS_PER_STRATEGY=25`, `CPU_LIMIT_PERCENT=60%`, `RAM_LIMIT_PERCENT=80%` — Evolution Engine ko khud apna hi laptop overload karne se rokta hai |
| **Self-Learning Dual Filter** | `self_learning_engine/validation_gate.py` | `MIN_RISK_REWARD=2.0` + benchmark-relative win rate — kamzor naye combinations ko accept hone se rokta hai |
| **Self-Learning Out-of-Sample Gate** | `self_learning_engine/validation_gate.py` | Do alag time-periods par pass hona zaroori — sirf ek period par "lucky" result se rokta hai |

Is Master Task 5 ki investigation ke doran **koi bhi upar wala gate weaken/bypass nahi kiya gaya** — sirf ek naya *observational* Near-Miss Log add hua hai jo khud kisi gate ko affect nahi karta.

---

## 13. Known Gaps / Honest Limitations

- **Confluence gate ka ek suspected bug** — "no existing position crowding" factor apni khud ki position ko bhi count kar leta hai, jisse ye factor ~97% waqt fail hota hai (Section 14/Master Task 5 Part 1 dekhein). **Flag kiya gaya hai, fix NAHI kiya gaya** — CEO ka faisla hai.
- **Evolution Engine ka job "stopped" hai** — bug fix ho chuka hai, lekin job khud restart nahi hua. Naya generation banne ke liye CEO ko dobara "Start" karna hoga.
- **Self-Learning Engine ne kabhi ek bhi discovery cycle nahi chalayi** — bana hua hai, wired hai, lekin 0 real-world evidence hai ke ye kaam karta hai end-to-end.
- **Telegram automatic sending ne kabhi kaam nahi kiya** — 6 din, 672 signals, 0 automatic sends (Section 14 mein poori wajah).
- **Cron-job keep-alive setup abhi bhi manual hai** — `CRON_JOB_SETUP.md` likha ja chuka hai, lekin CEO ko khud cron-job.org par account banana/setup karna hai.
- **8 naye strategies** jo CEO ne diye hain — **is task ka hissa nahi the, alag future task hain**.
- **Wilson gate ki granularity** (exact strategy+symbol+market_state+session) — itni fine hai ke 508+ distinct combos mein trade volume fragment ho jata hai, koi combo abhi tak 4 se zyada trades tak nahi pahuncha (need 25). Flag kiya gaya, fix nahi kiya (CEO ka faisla).
- **DCA/multi-entry averaging** — engine abhi bhi sirf single-entry-per-trade support karta hai (purana gap, `PROJECT_DOCUMENTATION.md` Section 16 se).
- **requirements.txt mein version pinning nahi hai** — reproducibility risk.
- **6 items** jo pehle Grand Feature Expansion se CEO ke faisle par ruke hain (Emergency Contact Alert, Chart Attachment, Mobile Push Notifications, aur 3 execution-gate items) — abhi bhi wahi status hai.

---

## 14. Master Task 5 — Confidence Threshold Investigation (Poori Findings)

**1.1 — Exact threshold:** "High Confidence" koi ek single percentage number nahi hai — ek **compound gate** hai:
1. `auto_send_enabled=True` (abhi live True hai)
2. Confluence ratio (passed/total counted factors) >= `auto_send_min_confluence_ratio` (default **1.0 = 100%**)
3. Confluence passed count >= `auto_send_min_confluence_count` (default **3**)
4. Exact (strategy, coin, market_state, session) pattern **Wilson-gate `reliable_good`** honi chahiye — >= **25 trades** AND 95% CI lower bound >= **55%**
5. Strategy Drawdown Protection se paused na ho
6. Strategy ka live realized PnL is session mein >= 0

**1.2 — Real distribution (672 positions, 2026-08-29 se 2026-09-04):** Confluence ratio **kabhi ek dafa bhi 100% nahi hui** — sirf 33% (333 baar) ya 67% (339 baar) values aayi hain. Wilson gate ke liye: 508 distinct exact-combos hain, **kisi ek ka bhi trade count 4 se zyada nahi hua** (25 chahiye).

**1.3 — Honest assessment:** Threshold KI SANKHYA khud unreasonable nahi hai — lekin do structural wajuhaat se ye practically kabhi satisfy nahi ho pati:
- **(A) Suspected bug**: "coin crowding" confluence factor apni khud ki already-open position ko bhi count karta hai — 60 recent positions ke live sample mein 58/60 (97%) sirf isi wajah se fail hui.
- **(B) Structural**: Wilson gate ka exact-match grouping itna fine hai ke 508+ combos mein trade volume fragment ho jata hai.

Dono findings CEO ke liye flag ki gayi hain (Section 13), **koi bhi khud change nahi ki gayi** — ye task explicitly reporting-only tha.

**1.5 — Near-Miss Log:** Naya permanent system (`near_miss_log` table, local + cloud dono) — ab har genuine near-miss signal automatically record hota hai, Telegram Dashboard par apna section hai. Ye data ab khud accumulate hoga, dobara manual investigation ki zaroorat nahi.

---

## 15. Key Lessons/Principles (Poore Project Se, Carried Forward)

- **Real evidence over claims** — har number is document mein live database se aaya hai, kabhi estimate nahi.
- **Documented does not mean working** — Self-Learning Engine poora bana hua hai, safety gates ke saath, lekin kabhi actually run nahi hua. Ye do alag cheezein hain.
- **Suspect shared root causes** — jab bohot saari cheezein similar tarike se fail hoti hain (jaise Evolution ke 198 lineages sab gen-1 par atke), do independent bugs mil sakte hain, ek nahi.
- **Single-concept-focused batches** achhe result dete hain — mixed-concept batches se behtar (purani strategy-batch sessions se sabak).
- **Genuine bugs vs policy decisions ka farak** — ek bug fix karna alag baat hai, ek threshold/policy CEO ka faisla hai. Master Task 5 ne dono ko clearly separate rakha.
- **Archive, never delete** — poore project mein data kabhi hard-delete nahi hota.

---

## 16. Quick Summary (5 Lines)

SINDHU ek self-learning crypto trading system hai jahan CEO sirf ek strategy paste karta hai aur AI (sirf import ke waqt) usay poori tarah samajh kar executable bana deta hai — uske baad AI ki zaroorat kabhi nahi padti. Ab ye ek poora chalta-phirta platform hai: 154 strategies (sirf 1 abhi genuinely profitable), 24/7 Paper Trading, ek khud-mutate hone wala Evolution Engine (198 BOT lineages, do real bugs is task se pehle mile aur fix hue), ek naya Self-Learning discovery system (bana hua hai lekin kabhi run nahi hua), Challenge Mode, aur Telegram Signals (jinka automatic sending 6 din mein ek dafa bhi kaam nahi kar saka — Master Task 5 ne is ki asli, evidence-based wajah dhoondi aur ek permanent Near-Miss Log bhi bana diya). Poora system ek local machine (`E:\sindhu`, poora feature set) aur ek halke cloud deployment (Render, sirf Paper Trading + Telegram) mein split hai, dono ka apna clear role hai. Har safety gate (Wilson, Evolution, Rollback, Confluence, Freshness, Incomplete Lock, 5-coin cap, Governor, Self-Learning ke dual filters) is poore session mein intact rakha gaya — koi bhi weaken nahi hua. Kuch cheezein abhi bhi honestly incomplete hain (Evolution job stopped hai, cron-job setup manual hai, 8 naye strategies alag task hain) — ye sab yahan clearly likhi gayi hain, chupayi nahi gayi.
