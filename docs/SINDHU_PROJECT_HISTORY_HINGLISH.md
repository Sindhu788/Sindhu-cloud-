# SINDHU — Poori Project History (Hinglish)

> Yeh document SINDHU ki shuru se ab tak ki kahani hai — kya bana, kab bana, kya toota, kaise theek hua.
> Har tareekh aur har cheez **git history (237 commits, 12 Jul 2026 → 16 Sep 2026)** aur repo ke apne checkpoint/report files se li gayi hai — koi baat andaze se nahi likhi.
> Aakhri update: **16 Sep 2026** (Grand Master Hands-On Audit batch).

---

## 0. SINDHU hai kya? (ek paragraph mein)

SINDHU ek **crypto trading research + paper-trading bot** hai. Yeh strategies ko documents/text se samajhta hai (AI sirf import ke waqt), unko purane candles par **backtest** karta hai, achi strategies ko **paper trading** (naqli paisa, asli market prices) mein chalata hai, aur strong signals **Telegram** channel par bhejta hai. Is ke saath ek bada **dashboard** hai (local laptop par poora version, aur Render cloud par halka "cloud runner" version jo 24/7 chalta hai).

**Kabhi real paisa trade nahi hota** — sirf paper trading. AI kabhi live signal/risk decision mein nahi aata, sirf strategy import ke waqt.

---

## 1. Timeline — mahine dar mahine

### July 2026 — Neev (Backtesting Engine + Dashboard)

| Tareekh | Kya hua |
|---|---|
| **12 Jul** | Baseline commit. Backtesting hang, lesson-veto, history bugs fix. `/api/home` ki bohot zyada slowness theek. Pytest suite shuru. |
| **13 Jul** | Automation pipeline (backtest → optimize → compare → paper trade). Reports page timeout fix (`quick_batch_summary`). |
| **14 Jul** | Candle resample caching, per-bar engine speedup, **SINDHU CEO command center** page. |
| **17–18 Jul** | "0 trades" wale khamosh bugs, stop-loss/position-sizing PnL bugs, system-wide slowness fix. |
| **19 Jul** | Har strategy ka **alag paper trading book**. **Evolution Core Engine** + Strategy Generator. Dashboard mobile-responsive. |
| **20 Jul** | Evolution Engine dashboard ko hang kar raha tha — fix. Backtest engine ke woh bugs jo lagbhag har result negative dikha rahe the — fix. |
| **22–24 Jul** | Backtesting **Master Spec** (20 requirements). Trade Execution/PnL/Risk Engine (Phase 1), Verification Engine (Phase 2), look-ahead proof tests, **Automatic Strategy Safety Check**. |
| **25 Jul** | Branching entry rules (`entry_rule_groups`), Self-Correcting Import Pipeline, poori library ka backtest (2 asli bugs mile). |
| **26–27 Jul** | Resample cache sharding. **Self-learning activation**: Pattern Auto-Avoid, Drawdown Protection, Lesson Auto-Apply, Market Regime Detection. |
| **28 Jul** | **Feature Control Center** (master pause + per-feature toggles). Genuine Evolution Engine (statistically sound). |
| **29 Jul** | Navigation reorganize. **Telegram high-confidence signals** statistical gate (Wilson) ke saath shuru. Single-session guard. |
| **30 Jul** | Telegram **master on/off switch** + $100/month hypothetical PnL tracker. |

### August 2026 — Telegram, AI Import, Batches

| Tareekh | Kya hua |
|---|---|
| **1 Aug** | Evolution ka alag 100-trade gate + rollback. `candle_break()` level-triggered bug fix. Telegram **dual-tier** sending. |
| **2 Aug** | Multi-pass AI extraction + rule counting, auto-retry missing rules, **Incomplete Lock**, **Signal Freshness Gate**. |
| **3 Aug** | System Maturity Level Tracker, Manager Chat (read-only Q&A), sentence-level extraction pipeline. |
| **4 Aug** | Telegram Signal Mirror panel, server launch par Paper Trading auto-restore, **Challenge Mode** (sirf tracking). |
| **5 Aug** | Strategy import fixes, **Strategy Wizard** aur **Strategy Lab**, Roman Urdu clarification UI. |

### September 2026 — Cloud (Render) + Grand Master Batches

| Tareekh | Kya hua |
|---|---|
| **1 Sep** | **Lightweight cloud runner** (`cloud_runtime/app.py`) — 24/7 deployment ke liye. `/health` endpoint. |
| **2 Sep** | Cloud env-var parsing fix, `/health` misconfigured deploy mein bhi chale. |
| **3 Sep** | Cloud settings/session **Postgres persistence** (Render ka disk har restart par mit jata hai). Telegram sirf High Confidence. 24h cloud→local sync. |
| **4 Sep** | **Grand Feature Expansion (~110 features)**, Master Tasks 3–5 (Self-Learning Engine, Near-Miss Log, SINDHU 2.0 docs). |
| **7 Sep** | Binance 451 geo-block → **Bybit** switch. Telegram env-var shadowing fix. Local↔cloud strategy sync, status ping. |
| **8 Sep** | Grand Master Prompt Phases 1–4: 10-Department company structure, Strategy Lifecycle, cloud monitoring, UI/UX. |
| **9–10 Sep** | Live cloud logs se Postgres-only errors fix, numpy values Postgres INSERT kharab kar rahe the — fix, timeouts fix. **Saare timestamps PKT** mein. |
| **12 Sep** | Paper Trading page crash (Groups tab/buttons stuck), Groups ranking, Reset Balance ki khamosh failures. |
| **13 Sep** | Paper Trading page-load timeout: ~34 API calls ko batches mein kiya. Telegram ka asli network test. |
| **14 Sep** | Grand Master Batch Phase 2–4: priority ranking, cloud settings persistence, System Health Score, cost tracker. |
| **15 Sep** | Trade attribution, realistic spread simulator, expected-value gate, Telegram close-result spam band, **Losing-group ke signals Telegram par roke gaye**, Telegram Signal Performance Report. |
| **16 Sep (subah)** | Full-system audit: test-isolation leak (asli 11 GB DB copy ho kar C: drive bhar rahi thi) fix, local Telegram env fallback, **cloud dependencies pin** (commit `baa8497`), fresh verified backup `sindhu_20260916_124514.db`. |
| **16 Sep (shaam)** | **Grand Master Hands-On Audit** — neeche Section 3 dekhein. |

---

## 2. Bade sabaq (jo baar baar saamne aaye)

1. **Local file vs cloud database** — Render ka disk har restart par saaf hota hai. Jo setting sirf JSON file mein save hoti thi woh cloud par "save hoti dikhti" phir gayab ho jati. Hal: `load_persistent`/`save_persistent` (cloud par Postgres).
2. **Cloud runner mein router mount na hona** — cloud app sirf chune hue API routers load karta hai. Koi page aisa endpoint call kare jo cloud par mount hi nahi, to woh 404 deta hai — aur "Save" kabhi kaam nahi karta. (16 Sep ko `/api/settings` isi wajah se toota mila.)
3. **Slowness ki asli wajah aksar ek "fan-out" hoti hai** — ek page 70 alag requests ek saath bhej de to server ke saare worker threads bhar jate hain aur har doosra page bhi atak jata hai.
4. **Tests ko asli data se alag rakhna** — `test_db` fixture ke saath `CONFIG_DIR` bhi patch karna zaroori; warna tests asli DB/settings bigaad dete hain.
5. **Confidence % probability nahi hai** — 1,085 trades par AUC 0.47; claimed ~71% vs asli ~37% win rate. Isko "jeetne ka chance" samajhna ghalat hai.
6. **Gates kabhi dheeli nahi karni** — metric acha dikhane ke liye Wilson/Evolution/Confluence/Drawdown/Freshness/Incomplete Lock/Kill Switch ko kabhi kamzor nahi kiya gaya.

---

## 3. 16 Sep 2026 — Grand Master Hands-On Audit (is batch mein kya hua)

Poori tafseel: `docs/FULL_A_TO_Z_AUDIT_AND_UPDATE_REPORT.md`. Mukhtasar:

- **Login gate**: public cloud par login band NAHI kiya (risky tha). Uski jagah laptop par **loopback-only (127.0.0.1)** test servers chalaye jin mein sirf us process ke andar login bypass tha — local app, aur **asli cloud app code** (asli trading data ki copy ke saath). Testing ke baad dono band kiye aur 401 se verify kiya ke login wapas lag gaya.
- **Settings save nahi hoti thi (cloud)** — asli wajah: cloud par `/api/settings` router mount hi nahi tha → CEO page (cloud ka default page) ka Settings card khali values dikhata aur har Save 404 hota. Fix + saath mein: validation, "✓ Saved" sirf asli success par, Reset to default, Save button sirf change par enable, multi-field save, settings change history, aur har keystroke par auto-save hatana (jo Initial Balance ko beech ki value "1" par save kar sakta tha).
- **Telegram page nahi khulta tha** — page apne pehle render se pehle Telegram network-check ka intezar karta tha (local par har baar 15 sec). Ab page foran khulta hai, check baad mein bharta hai. Nayi **Telegram Status** section (overall + Losing/Profitable/Challenge + aaj ke signals).
- **Navigation 30–50 sec** — asli wajah: Paper Trading page har 30 sec par har open position ke liye alag confluence request (70 requests) bhejta tha → server ke threads bhar jate. Plus `risk-metrics-all` 154 alag queries, ek SQLite MIN/MAX query jo index seek use nahi kar rahi thi (0.46s → 0.003s), aur kuch uncached heavy endpoints. Asli before/after seconds report mein.
- **Daily 24h report** — pehle se mojood report ko Overall / Group-wise / Telegram sections diye, aur usko **cloud par bhi chalaya** (pehle sirf laptop app mein start hoti thi jahan Telegram token hi khali hai).
- **Per-strategy cooling-off** — lagataar 4 losses ke baad sirf us strategy ke naye trades 3 ghante band, phir khud chalu (0 = off).
- **Trading analysis (Section 9)**: modeled costs $155.19 (slippage+spread $68.98 + commission $86.22) — yani costs se pehle system taqreeban +$67 hota; last 50 trades ka win rate 18% vs claimed confidence 75.8%.

---

## 4. 17 Sep 2026 — Investigation Batch (Confidence fix, per-coin cap, Telegram /challenge)

- **Confidence % fix**: asli wajah nikli — `confidence.score()` ek hath-se-bana formula tha jo kabhi asli outcomes se check hi nahi hua tha. Ab yeh apne raw score ka bucket `confidence_calibration`'s real calibration map mein dekhta hai aur (25+ real trades hone par) **asli win rate** dikhata hai, warna raw heuristic par wapas gir jata hai. Asli 50-trade sample: pehle 75.8% average confidence dikhta tha, fix ke baad 36.3% (asli win rate 18% ke kaafi qareeb).
- **Ek hi coin par 14 positions** ka asli sabab mila: 14 alag strategies har ek chhota risk le rahi thin, is liye dollar-based cap (`max_portfolio_risk_pct_per_coin`) کبھی cross نہیں hua. Naya `max_open_positions_per_coin` (default 5) cap laga — ab ek coin par zyada se zyada 5 positions, sab strategies milakar.
- **Paper Trading page 16.1s se ~3.2s**: asli measurement se pata chala ke har individual endpoint <1s tha lekin ~20 ek saath chalne par Python GIL contention se 1-2s tak phool jate the. Un sab ko cache kiya aur cloud runner mein pehli baar cache-warming laga di (pehle sirf laptop app warm karta tha).
- **Session-expiry warning**: 30-din session khatam hone se 24 ghante aur 1 ghanta pehle ek toast warning, taake achanak logout na ho.
- **Telegram `/challenge` command family** (naya): `/challenge <balance> <target> <days>d` (ya template: `conservative`/`aggressive`) — asli history se best strategy+coin khud chunta hai, ghair-haqiqi target par honest warning deta hai, aur do challenges ko ek hi strategy+coin claim karne se rokta hai. `/stopchallenge`, `/resumechallenge`, `/mychallenges` (progress bar + leaderboard), `/report` (Total Trades + Group Detail + Challenges), `/menu` (har command aur har marker ki poori guide). Naya ⚫ marker challenge signals par. Har 15 minute par completion (celebration message), deadline-fail ("Challenge failed -- reached X%"), aur 50%-balance-drop (auto-pause + warning) check hoti hai; roz ek dafa har active challenge ka update bhi jata hai.
- Weekly snapshot ki khaali/toothi DB file aur purani throwaway cloud-test-data copy delete ki.

---

## 5. Ab kya baaki hai (CEO ke faislay ke liye)

- Cloud par ek dafa ≥12 minute ke liye app bina restart ke jawab dena band kar gaya tha (14:33–14:45 UTC, 16 Sep) — Render logs dekhne ke liye login/API access chahiye. Fix ke baad se dobara nahi hua (17 Sep tak 24+ ghante continuous uptime), lekin asli platform logs abhi tak nahi dekhe ja sake.
- Challenge group ke liye alag $2 **trading** balance — position sizing aur account-drawdown breaker ki math badalta hai (safety gate), is liye implement nahi kiya; faisla CEO ka.
- Correlated coins (alag coins, ek hi direction) ka combined exposure sizing mein shamil nahi — sirf same-coin cap hai (ab count-based bhi, pehle sirf dollar-based).
- Proxy password rotate karna (plaintext mein mila tha) — iske liye us proxy provider ke account mein login chahiye, jo AI khud nahi kar sakta.
- Telegram `/challenge` ke naye commands sirf code-level tests se verify hue hain (37 real tests) — asli Telegram chat se ek dafa manually try karna baaki hai.
