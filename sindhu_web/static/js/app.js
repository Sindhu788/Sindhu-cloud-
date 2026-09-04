(() => {
  "use strict";

  // ------------------------------------------------------------ Language toggle (Batch 4, Task 4)
  // Two small lookup tables instead of a separate key namespace, so
  // existing hardcoded strings can be wrapped in place without renaming
  // them: T_UR translates an English default (used by most of the app) to
  // Roman Urdu; T_EN translates a Roman-Urdu default (used by the Batch 3
  // Incomplete Lock / verification view, which was built Urdu-first) back
  // to plain English. Missing keys fall through to whatever was already
  // hardcoded, so an untranslated string is never blank -- only ever in
  // the "wrong" (but still readable) language. Persisted in localStorage
  // (this machine/browser), same mechanism already used for the API token.
  let LANG = localStorage.getItem("sindhu_lang") || "en";
  function getLang() { return LANG; }
  function setLang(lang) {
    LANG = lang;
    localStorage.setItem("sindhu_lang", lang);
    route();
  }
  // Covers the section titles, card labels, and button text actually
  // exercised on the Overview, Paper Trading, Telegram Signals, Strategies,
  // and Strategy Verification pages (Batch 4, Task 4's named priority
  // pages) -- not literally every string in the app. Other pages fall back
  // to their existing English/Urdu text unchanged.
  const T_UR = {
    "Overview": "Overview",
    "Manager Chat": "Manager Chat",
    "Strategies Evolved": "Kitni Strategies Evolve Hui",
    "New Generations Created": "Naye Generations Bane",
    "Rollbacks": "Wapas Ki Gayi Tabdeeliyan",
    "Improved (Kept)": "Behtar Hui (Rakhi Gayi)",
    "Still Awaiting 100 Trades": "Abhi 100 Trades Ka Intezaar",
    "System Maturity Level": "System Kitna Mature Hai (Level)",
    "System Alerts": "System Alerts (Zaroori Baatein)",
    "Top Strategies by Profit": "Sabse Profitable Strategies",
    "System Monitor": "System Ki Halat",
    "Available Timeframes": "Kaunse Timeframes Available Hain",
    "Control Center": "Control Center",
    "Task Manager": "Task Manager",
    "Balance": "Balance",
    "PnL": "Munafa/Nuksan (PnL)",
    "Win Rate": "Jeetne Ki Dar",
    "Total Trades": "Kul Trades",
    "Knowledge Score": "Knowledge Score",
    "Evolution Score": "Evolution Score",
    "Database Status": "Database Ki Halat",
    "System Health": "System Theek Hai Ya Nahi",
    "CPU Usage": "CPU Kitna Chal Raha Hai",
    "RAM Usage": "RAM Kitni Bhari Hai",
    "Disk Usage": "Disk Space Kitni Use Hui",
    "Database Size": "Database Ka Size",
    "API": "API",
    "Exchange": "Exchange",
    "Queue": "Line Mein (Queue)",
    "Background Tasks": "Peeche Chal Rahe Kaam",
    "Paper Trading": "Paper Trading (Nakli Paise Se Trading)",
    "Engine Status": "Engine Chal Raha Hai Ya Nahi",
    "Mode": "Mode",
    "Combined Balance": "Total Balance (Sab Strategies Milakar)",
    "Open Positions": "Chal Rahi Trades",
    "Closed Trades (All-Time)": "Ab Tak Band Hui Trades",
    "Win Rate (All-Time)": "Ab Tak Ki Jeetne Ki Dar",
    "Realized PnL (All-Time)": "Ab Tak Ka Asli Munafa/Nuksan",
    "Queue (shortlisted coins)": "Line Mein Coins",
    "Start Engine": "Engine Shuru Karein",
    "Stop Engine": "Engine Band Karein",
    "Run One Tick Now": "Abhi Ek Chaal Chalao",
    "Reset Balance": "Balance Reset Karein",
    "Alerts": "Zaroori Baatein",
    "Daily Goal": "Aaj Ka Target",
    "Strategies": "Strategies",
    "Search strategies...": "Strategy Dhoondein...",
    "New Strategy": "Nayi Strategy",
    "Show Archived": "Archived Bhi Dikhayein",
    "Name": "Naam",
    "Concepts": "Concepts",
    "Timeframes": "Timeframes",
    "Condition Roles": "Sharton Ka Kirdar",
    "Status": "Halat",
    "Last Backtest": "Aakhri Backtest",
    "Version": "Version",
    "Profile": "Profile",
    "Edit": "Badlein",
    "Duplicate": "Copy Banayein",
    "Delete": "Hatayein",
    "Restore": "Wapas Lao",
    "Duplicate Strategies": "Milti-Julti (Duplicate) Strategies",
    "Strategy Graveyard": "Retire Hui Strategies",
    "Telegram Signals": "Telegram Signals",
    "Signals Sent": "Bheje Gaye Signals",
    "Open / Pending": "Chal Rahe / Baaki",
    "Wins": "Jeet",
    "Losses": "Haar",
    "Trades Counted": "Ginti Ki Gayi Trades",
    "Hypothetical PnL": "Andaazi Munafa/Nuksan",
    "Hypothetical Balance": "Andaazi Balance",
    "Per-Strategy Breakdown": "Har Strategy Ka Alag Hisaab",
    "Signal Log": "Signals Ki Poori List",
  };
  const T_EN = {
    "Aapne Jo Likha (Original)": "What You Wrote (Original)",
    "System Ne Kya Samjha": "What The System Understood",
    "Status": "Status",
    "Phir Bhi Test Karein": "Test Anyway",
    "Samajh Aaya": "Understood",
    "Samajh Nahi Aaya": "Not Understood",
    "Strategy Samjhi Gayi? (Verification)": "Was The Strategy Understood? (Verification)",
    "Yeh check load nahi ho saka.": "This check could not be loaded.",
    "Ab Check Karein": "Check Now",
    "Dobara Check Karein": "Check Again",
    "Yeh strategy abhi test nahi ho sakti": "This strategy can't be tested yet",
    "neeche jo rules \"Samajh Nahi Aaya\" hain, unki wajah se.": "because of the rules below marked \"Not Understood\".",
    "Warning": "Warning",
    "Yeh strategy adhoori samajh ke saath test ho rahi hai (aapne \"Test Anyway\" dabaya tha) -- iske results poori tarah bharosemand nahi hain.":
      "This strategy is being tested with an incomplete understanding (you pressed \"Test Anyway\") -- its results are not fully reliable.",
    "Lock Wapas Laga Dein": "Re-Enable The Lock",
    "Is document mein koi rule nahi mila.": "No rules were found in this document.",
    "rules samajh aaye": "rules understood",
    "dobara koshish ki gayi": "retries made",
  };
  function t(englishDefault) {
    return LANG === "ur" ? (T_UR[englishDefault] || englishDefault) : englishDefault;
  }
  function tu(urduDefault) {
    return LANG === "en" ? (T_EN[urduDefault] || urduDefault) : urduDefault;
  }

  // ------------------------------------------------------------ API client
  let apiToken = localStorage.getItem("sindhu_token") || "";

  async function ensureToken() {
    if (apiToken) return apiToken;
    const res = await fetch("/api/token");
    const data = await res.json();
    apiToken = data.token;
    localStorage.setItem("sindhu_token", apiToken);
    return apiToken;
  }

  async function apiGet(path, timeoutMs = 15000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(path, { signal: controller.signal });
      if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`);
      return await res.json();
    } catch (e) {
      // A plain fetch() with no abort/timeout can hang forever if the
      // server or network stalls, leaving a page stuck on "Loading..."
      // indefinitely with no way to recover -- this turns that into a
      // real error after timeoutMs so callers can show a retry state.
      if (e.name === "AbortError") throw new Error(`GET ${path} timed out after ${timeoutMs}ms`);
      throw e;
    } finally {
      clearTimeout(timer);
    }
  }

  // Part 4 (reliability): a plain fetch() with no abort/timeout can hang
  // forever if the server stalls (crashed mid-request, port conflict,
  // network drop) -- every POST/DELETE/upload gets the same bounded-wait
  // treatment apiGet already had, just with a longer default since some of
  // these (AI import, file upload) can legitimately take a while.
  async function apiSend(method, path, body, timeoutMs = 120000) {
    await ensureToken();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    let res;
    try {
      res = await fetch(path, {
        method,
        headers: { "Content-Type": "application/json", "X-Sindhu-Token": apiToken },
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });
    } catch (e) {
      if (e.name === "AbortError") throw new Error(`${method} ${path} timed out after ${timeoutMs}ms`);
      throw e;
    } finally {
      clearTimeout(timer);
    }
    if (!res.ok) {
      let detail = `${method} ${path} -> ${res.status}`;
      try { detail = JSON.stringify(await res.json()); } catch (e) {}
      throw new Error(detail);
    }
    return res.json();
  }
  const apiPost = (path, body, timeoutMs) => apiSend("POST", path, body, timeoutMs);
  const apiDelete = (path) => apiSend("DELETE", path);

  async function apiUpload(path, formData, timeoutMs = 180000) {
    await ensureToken();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    let res;
    try {
      res = await fetch(path, { method: "POST", headers: { "X-Sindhu-Token": apiToken }, body: formData, signal: controller.signal });
    } catch (e) {
      if (e.name === "AbortError") throw new Error(`POST ${path} timed out after ${timeoutMs}ms`);
      throw e;
    } finally {
      clearTimeout(timer);
    }
    if (!res.ok) {
      let detail = `POST ${path} -> ${res.status}`;
      try { detail = JSON.stringify(await res.json()); } catch (e) {}
      throw new Error(detail);
    }
    return res.json();
  }

  function debounce(fn, ms) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  }

  // ------------------------------------------------------------ autosave / offline queue
  // Every "no Save button" field (strategy text, lesson form, settings)
  // routes its writes through here instead of apiSend directly, so a
  // dropped connection doesn't silently lose the edit -- it's queued and
  // retried the moment the WebSocket reconnects or the browser comes
  // back online.
  let pendingQueue = [];

  async function autosave(method, path, body) {
    try {
      return await apiSend(method, path, body);
    } catch (e) {
      pendingQueue.push({ method, path, body });
      appendLog(`Autosave queued (connection lost): ${path}`);
      throw e;
    }
  }

  async function flushPending() {
    if (!pendingQueue.length) return;
    const queue = pendingQueue;
    pendingQueue = [];
    for (const item of queue) {
      try {
        await apiSend(item.method, item.path, item.body);
        appendLog(`Pending change saved: ${item.path}`);
      } catch (e) {
        pendingQueue.push(item);
      }
    }
  }
  window.addEventListener("online", flushPending);

  function fmtBytes(n) {
    if (n == null) return "-";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let v = n, i = 0;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
    return `${v.toFixed(1)} ${units[i]}`;
  }
  function fmtNum(n) { return n == null ? "-" : Number(n).toLocaleString(); }
  // Same tick-style display rounding as the Telegram message itself
  // (paper_trading.telegram_bot._format_price) -- 3 decimals floor, more
  // for sub-$1 coins so real precision isn't rounded away. Display-only.
  function fmtPrice(n) {
    if (n == null) return "-";
    const v = Number(n);
    if (v === 0) return "0.000";
    const decimals = Math.abs(v) >= 1 ? 3 : Math.max(3, -Math.floor(Math.log10(Math.abs(v))) + 3);
    return v.toFixed(decimals);
  }
  function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
  // Batch 9, Task 2: renders a stored telegram_message_log.message_text --
  // escapes EVERYTHING first (so any injected content, e.g. a strategy
  // name, can never break out as live HTML), then restores only the
  // literal <b>/</b> tags OUR OWN templates put there, so bold formatting
  // shows exactly as it appeared in the real delivered Telegram message.
  function renderTelegramMessageHtml(text) {
    return esc(text).replace(/&lt;b&gt;/g, "<b>").replace(/&lt;\/b&gt;/g, "</b>");
  }

  // ------------------------------------------------------------ "Explain This to Me" popovers
  // Pre-written, static plain-language text -- no AI call, just a tooltip.
  // Any page can drop helpIcon("key") next to a metric; a single delegated
  // click handler (registered once, below) shows the matching popover.
  const HELP_TEXT = {
    confidence_score: "How sure the system is that a trade setup is a good one, from 0-100%. Higher means more of the system's own checks agreed with each other before it acted. It is not a guarantee of profit -- it just means the setup looked stronger by the system's own rules.",
    sharpe_ratio: "A single number for \"how smooth were the profits\" -- it compares how much a strategy made to how bumpy the ride was to get there. Roughly: above 1 is good, above 2 is very good, below 0 means it lost money on average. Two strategies can make the same profit, but the one with the higher Sharpe Ratio got there with fewer scary swings.",
    sortino_ratio: "Like the Sharpe Ratio, but it only counts the LOSING swings as \"bumpy\" -- big winning trades don't count against it. Two strategies with the same Sharpe Ratio can have very different Sortino Ratios; a higher Sortino means its ups and downs were mostly big wins and small, steady losses, not the other way around.",
    value_at_risk: "A realistic worst-case single-trade loss, based on this strategy's own real trade history (not a guess) -- \"Value at Risk (95%)\" means 95% of past trades lost less than this amount; only the worst 5% were worse. It needs at least 25 finished trades before it means anything.",
    health_score: "One number out of 100 that combines win rate, profit factor, how bad the worst losing streak was, and how much real trade history backs it up -- a quick way to compare strategies at a glance. Above 70 is strong, 40-70 is mixed/early, below 40 needs attention. It's a plain weighted formula, not a black box -- open the strategy's detail view to see exactly which part of the score is pulling it up or down.",
    strategy_correlation: "How much two strategies tend to win and lose on the SAME days, based on their real day-by-day profit history -- not their coins or setups, their actual results. A high number (shown in red) means running both together gives less real diversification than it looks like, since a bad day for one is often a bad day for the other too. A negative number (blue) means they tend to balance each other out.",
    strategy_similarity: "How much a new strategy overlaps with an existing one, based on the trading concepts they share (not their name or wording). 80% or higher triggers a warning before saving, so you don't accidentally build a near-duplicate strategy without realizing it -- you can still save it anyway if the overlap is intentional.",
    strategy_family_tree: "Strategies grouped by the core trading idea they're built on -- e.g. every strategy using Order Blocks together, every one using Fair Value Gaps together. A strategy can belong to more than one family if it combines multiple ideas. Only groups of 2 or more show up as a real 'family' -- a strategy with a genuinely unique concept isn't forced into one.",
    custom_alert_rules: "Your own personal 'tell me if this happens' rules, on top of everything the system already watches automatically. For example: alert me if a specific strategy's realized profit drops below $0, or if the whole account's drawdown goes above 15%. Checked about once an hour; once triggered, the same rule waits a few hours before checking again so it doesn't spam you.",
    coin_blacklist: "Coins you never want any strategy to trade -- maybe it's too illiquid, too erratic, or you've simply decided to avoid it. A blacklisted coin is removed before it's even considered, no matter how good its numbers might otherwise look. Different from the automatic top-N coin ranking, which only decides which ALLOWED coins get priority.",
    time_of_day_filter: "Blocks the system from opening any NEW trade during a set window of hours (UTC), e.g. hours you've noticed tend to be too quiet or unpredictable. Any trade already open when the window starts keeps running normally -- this only ever stops something from starting, never forces something to close.",
    risk_pct_recommendation: "A suggested risk-per-trade percentage for this strategy, based on its own Sharpe Ratio -- the same bounded, transparent formula the Capital Allocation Engine already uses for capital, just applied to risk % instead. Purely a suggestion: nothing changes until you click Apply, which simply fills in that strategy's existing manual risk-per-trade override.",
    evolution_weekly_review: "A weekly summary of the EVOLUTION/TUNING side of the system -- how many strategies mutated, how many changes were kept vs. automatically rolled back for performing worse -- separate from the Weekly Auto-Report, which covers trading performance (wins/losses/PnL) only.",
    strategy_lineage_explainer: "A plain-language story of how this BOT strategy lineage got to where it is -- every generation it went through, why each change was made, and whether that change was kept or automatically rolled back for performing worse. Nothing new is computed here; it just ties together facts that already exist separately (generation history, mutation reasons, rollback results) into one readable summary.",
    evolution_confidence: "How much to trust THIS specific evolution result (0-100), not how good the strategy itself is. Combines how many real trades backed the 'after' numbers, how big the swing between before and after actually was, and how many of the 4 core metrics could even be compared. A small, thin improvement scores lower here than a big, clearly-measured one, even if both technically 'improved.'",
    backtest_replay: "Step through this coin's real backtest bar by bar (or press Play to watch it automatically), with every real trade's entry marked on the chart -- green if it ended in profit, red if it lost. Different from Trade Audit, which only shows one static window around a single trade you pick, not the whole run in sequence.",
    best_portfolio_suggestion: "The top few DIFFERENT strategies (never the same one twice), each paired with its own best-performing coin, ranked by real profit -- and only combinations with enough real closed trades to actually trust. Purely a suggestion: nothing here turns any strategy on or off by itself.",
    infra_weekly_digest: "A weekly summary of the SYSTEM itself -- how many backups were made, how many incidents were opened or resolved, and the current database/disk size -- separate from the Weekly Auto-Report (trading performance) and the Evolution Weekly Review (tuning activity), which cover different subjects entirely.",
    weekly_snapshot: "A database copy taken once a week and kept for about 2 months, separate from the regular rolling backup above (which only keeps its last 10 copies, roughly 1-2 days of history at the default schedule). Useful for going back further in time than the rolling backup allows.",
    duplicate_exposure_warning: "A heads-up that 2 or more DIFFERENT strategies are all trading the SAME coin right now, regardless of whether that coin is statistically correlated with anything else (see Correlation Warning above for that separate check). It doesn't mean anything is wrong -- it just means more of your real risk is concentrated in one coin than a quick glance at each strategy separately would suggest.",
    strategy_variants: "Creates a few sibling versions of this strategy -- each one swaps a single entry condition for a related alternative (e.g. a different liquidity concept) -- and tests all of them side-by-side in one go, alongside the original. Different from the Evolution Engine, which only ever produces one next generation at a time, sequentially. Nothing here changes the real saved strategy; it's purely a side-by-side comparison.",
    cross_coin_validation: "Splits this batch's real, already-tested coins into three groups by how volatile each one actually is (low/medium/high, computed fresh from real price data -- never a fixed list), and compares this strategy's win rate and PnL across those groups. A strategy that only does well in ONE volatility group might be overfit to that specific kind of coin rather than genuinely robust.",
    feature_importance: "Tests what would happen if this strategy lost each of its own entry/confirmation conditions, one at a time, and re-runs a real (bounded, ~30 day) backtest each time. A condition whose removal hurts PnL a lot is doing real work; one that barely changes anything when removed might not be adding much.",
    what_if_simulator: "A genuine re-simulation against this batch's own real historical data, with ONE parameter (like risk % or stop-loss) changed -- different from Monte Carlo (which just reshuffles the order of already-recorded trades) and from Slippage Sensitivity (which recomputes PnL on the same trades without re-running anything). Bounded to about 30 days and a few coins to stay fast -- treat it as a quick preview, not a full validation; a promising result is still worth a full re-backtest before trusting it.",
    position_size_calculator: "A what-if tool -- type in a balance, entry price, stop-loss, and risk %, and see exactly what position size the system would actually open, without opening a real trade. Uses the exact same sizing math the real engine uses for every live trade.",
    ensemble_voting: "When turned on (Feature Control Center), a coin will only actually be traded if at least this many INDEPENDENT strategies agree on the same direction at the same time -- a single strategy's signal alone is never enough. This can only make trading more cautious, never more aggressive, since it just adds an extra requirement on top of everything else.",
    profit_lock: "Once a trade has moved far enough in your favor (the 'Trigger', measured in multiples of the original risk -- 1.0 means it's up by as much as it was risking), the stop-loss moves up to guarantee at least the 'Lock In %' of that gain, and keeps trailing as the trade moves further in profit. The stop-loss only ever tightens from here, never loosens -- worst case from that point on is a smaller win, never the original full loss.",
    voice_alerts: "When the kill switch or account-wide drawdown circuit-breaker activates, an open browser tab speaks it out loud immediately, in real time -- not on the next page refresh. Uses your browser's own built-in text-to-speech, nothing installed or downloaded. Mute it per-browser from this Settings page if you don't want the sound.",
    health_badge: "A one-word summary of this strategy's overall state: 'Stable' (Health Score 70+), 'Unproven' (still building a track record or scoring in the middle), 'Weak' (Health Score under 40), or 'Archived' (retired, kept for reference but no longer traded). A quick-glance label -- open the Health Score card for the actual number and its breakdown.",
    mae_mfe: "How far a trade moved AGAINST the position (Maximum Adverse Excursion) or IN ITS FAVOR (Maximum Favorable Excursion) before it closed, regardless of how it ended. A winning trade that first dipped deep into the red before recovering had a real MAE even though it won -- this can reveal whether a stop-loss is placed too tight (winners routinely almost get stopped out) or a take-profit too greedy (losers were often in profit first, before reversing).",
    duration_tracker: "How long backtests are actually taking, based on real, permanently-recorded start and finish times -- not a live 'in progress' status, but a genuine history so you can see if backtests are getting slower over time or which ones are the biggest time sinks.",
    slippage_sensitivity: "Slippage is the small price difference between what you expected to pay and what you actually got, due to the market moving in the split-second it takes to fill an order. This test checks how much WORSE the strategy's real backtested trades could have gone if slippage had been higher than assumed -- a strategy whose profit disappears at a small extra slippage has a thin, fragile edge; one that stays profitable even at high extra slippage has a sturdier one.",
    what_changed_today: "An automatic, honest list of everything that actually happened today, built directly from the permanent Audit Trail -- not a hand-written summary someone has to remember to update. If nothing changed, it says so plainly instead of making something up.",
    strategy_aging: "Whether this strategy is getting BETTER or WORSE over time, not just how it's doing right now. Its trade history is split into equal-sized chunks in order; if the win rate in the newest chunks is at least 10 points higher than the oldest chunks it's 'Improving', 10+ points lower is 'Weakening', otherwise 'Stable'. Needs at least 30 closed trades (3 full chunks) before it can show a real trend.",
    portfolio_heat_map: "Where your real risk is concentrated right now, across every strategy combined -- by coin, by strategy, or by direction (long vs short). Even if each strategy looks balanced on its own, the whole portfolio could secretly be leaning heavily on one coin, one strategy, or one direction -- this view is built to catch that.",
    coin_heatmap: "Whether a coin is RELIABLY good, not just profitable overall. \"Consistency\" is the percentage of strategies that traded this coin and came out ahead on it -- a coin where only 1 of 5 strategies made money can still show a big total profit number elsewhere, but this view would correctly flag it as inconsistent (shown in red/orange) rather than reliably good (green).",
    max_drawdown: "The biggest drop a strategy's balance took from its highest point before recovering, shown as a percentage. A 20% max drawdown means that at its worst, this strategy was down 20% from its best-ever balance. Lower is safer -- it's the number that best answers \"how bad could it get?\"",
    confluence_score: "How many independent signals (like trend direction, momentum, and market condition) all agree, out of everything the system checked for this trade. A high confluence score means many separate signals pointed the same way, not just one.",
    market_regime: "A simple label for what the market is currently doing: \"Trending\" means prices are moving clearly in one direction, \"Ranging\" means prices are bouncing sideways without a clear direction, and \"High Volatility\" means prices are moving fast and unpredictably. Strategies often perform very differently depending on which of these is happening.",
    correlation_warning: "A heads-up that two or more strategies have open trades on coins that tend to move together (e.g. two coins that usually rise and fall at the same time). It doesn't mean anything is wrong -- it just means your real risk may be more concentrated than it looks, since a single market move could affect several trades at once.",
    profit_factor: "For every $1 this strategy lost, how many dollars it made. Above 1.00 means it made more than it lost; below 1.00 means it lost more than it made; exactly 1.00 means it broke even. This number comes from the backtest (the strategy tested against real past price history), not from live paper trading.",
    risk_reward: "How much a typical trade made compared to how much it was risking. \"2R\" means the average trade made twice what it put at risk. Below 1R means the wins were smaller than the amount being risked, which is hard to stay profitable on unless you win very often.",
    signal_freshness: "A trade signal goes out of date fast. If a signal is older than this many minutes, or the price has already moved away from the intended entry, the system refuses to send it rather than sending you a trade whose moment has already passed.",
    delivery_status: "What actually happened to this signal. \"Sent\" means it genuinely reached Telegram. \"Withheld\" means the system deliberately held it back (usually because it went stale). \"Failed -- network blocked\" means the message never reached Telegram because the connection itself was blocked. \"Queued\" means the trade is still open and the system will check again whether to send it. Nothing is ever shown as sent unless it truly was.",
    pattern_reliability: "Before the system trusts a win rate as real (not just luck), it needs at least 25 trades for that exact strategy + coin + market condition combination, and a statistical check (a 95% confidence interval) confirming the true win rate is clearly above or below 50% -- not just close to a coin flip. Below 25 trades, or when the result is too close to call, nothing is applied automatically.",
  };

  function helpIcon(key) {
    if (!HELP_TEXT[key]) return "";
    return `<span class="help-icon" data-help-key="${key}" tabindex="0" role="button" aria-label="What does this mean?">?</span>`;
  }

  (function setupHelpPopovers() {
    let popoverEl = null;
    function closePopover() {
      if (popoverEl) { popoverEl.remove(); popoverEl = null; }
    }
    function openPopover(icon) {
      closePopover();
      const text = HELP_TEXT[icon.dataset.helpKey];
      if (!text) return;
      const el = document.createElement("div");
      el.className = "help-popover";
      el.textContent = text;
      document.body.appendChild(el);
      const r = icon.getBoundingClientRect();
      const maxLeft = window.innerWidth - el.offsetWidth - 12;
      el.style.left = `${Math.max(8, Math.min(r.left, maxLeft))}px`;
      el.style.top = `${r.bottom + 6 + window.scrollY}px`;
      popoverEl = el;
    }
    document.addEventListener("click", (e) => {
      const icon = e.target.closest(".help-icon");
      if (icon) {
        e.stopPropagation();
        if (popoverEl && popoverEl.dataset.forKey === icon.dataset.helpKey) { closePopover(); return; }
        openPopover(icon);
        if (popoverEl) popoverEl.dataset.forKey = icon.dataset.helpKey;
        return;
      }
      if (popoverEl && !popoverEl.contains(e.target)) closePopover();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        const icon = document.activeElement && document.activeElement.closest && document.activeElement.closest(".help-icon");
        if (icon) { e.preventDefault(); icon.click(); }
      }
      if (e.key === "Escape") closePopover();
    });
  })();

  // ------------------------------------------------------------ Confidence Threshold filter
  // A single, page-local slider (Paper Trading page) that dims or hides any
  // row/card marked with a data-confidence attribute, applied client-side
  // and instantly -- no reload, no server round-trip. The threshold and
  // display mode are remembered in localStorage (same simple client-side
  // persistence already used for the API token) so they survive across
  // sessions/page reloads without needing a new server-side settings field.
  const CONF_THRESH_KEY = "sindhu_confidence_threshold";
  const CONF_HIDE_KEY = "sindhu_confidence_hide_mode";

  function getConfidenceThreshold() {
    const v = parseInt(localStorage.getItem(CONF_THRESH_KEY), 10);
    return Number.isFinite(v) ? v : 0;
  }
  function getConfidenceHideMode() {
    return localStorage.getItem(CONF_HIDE_KEY) === "1";
  }
  function applyConfidenceFilter() {
    const threshold = getConfidenceThreshold();
    const hide = getConfidenceHideMode();
    document.querySelectorAll("[data-confidence]").forEach(el => {
      const c = parseFloat(el.dataset.confidence);
      const below = Number.isFinite(c) && c < threshold;
      el.classList.toggle("conf-dimmed", below && !hide);
      el.style.display = below && hide ? "none" : "";
    });
  }
  function confidenceFilterHtml() {
    const threshold = getConfidenceThreshold();
    return `
      <div class="section-title">Confidence Filter</div>
      <div class="card" style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
        <div style="flex:1;min-width:220px;">
          <label>Minimum Confidence: <b id="confThreshVal">${threshold}%</b></label>
          <input type="range" id="confThreshSlider" min="0" max="100" value="${threshold}" style="width:100%;">
          <div class="muted" style="font-size:11.5px;">Applies to Open Positions and Strategy Comparison below -- updates instantly as you move it.</div>
        </div>
        <label style="width:auto;display:flex;align-items:center;gap:6px;">
          <input type="checkbox" id="confThreshHide" style="width:auto;" ${getConfidenceHideMode() ? "checked" : ""}>
          Hide below threshold (instead of dimming)
        </label>
      </div>`;
  }
  function wireConfidenceFilter() {
    const slider = document.getElementById("confThreshSlider");
    const hideBox = document.getElementById("confThreshHide");
    if (!slider) return;
    slider.addEventListener("input", () => {
      document.getElementById("confThreshVal").textContent = `${slider.value}%`;
      localStorage.setItem(CONF_THRESH_KEY, slider.value);
      applyConfidenceFilter();
    });
    hideBox.addEventListener("change", () => {
      localStorage.setItem(CONF_HIDE_KEY, hideBox.checked ? "1" : "0");
      applyConfidenceFilter();
    });
    applyConfidenceFilter();
  }

  // ------------------------------------------------------------ WebSocket / live logs
  const logsBody = document.getElementById("logsBody");
  const connStatus = document.getElementById("connStatus");
  let liveListeners = [];

  function onLive(fn) { liveListeners.push(fn); }
  function clearLiveListeners() { liveListeners = []; }

  function appendLog(text) {
    const div = document.createElement("div");
    div.textContent = text;
    logsBody.appendChild(div);
    if (logsBody.children.length > 500) logsBody.removeChild(logsBody.firstChild);
    logsBody.scrollTop = logsBody.scrollHeight;
  }

  // Listeners that survive route changes (unlike liveListeners, which are
  // cleared on every navigation) -- used for cross-device sync concerns
  // that aren't tied to whichever page happens to be open right now.
  let globalListeners = [];
  function onGlobalLive(fn) { globalListeners.push(fn); }

  // Task 2 (single active session): identifies this browser profile so the
  // server can tell "a new tab/window on the SAME computer" (should close
  // the old one) apart from "a different device" (e.g. a phone connected
  // via Connect-from-mobile, which must stay connected at the same time --
  // see sindhu_web/session_guard.py). localStorage is shared by every tab
  // in the same browser profile, so this id is stable across tabs on one
  // device but unique per device.
  function getDeviceId() {
    let id = localStorage.getItem("sindhu_device_id");
    if (!id) {
      id = (crypto.randomUUID ? crypto.randomUUID() : `dev-${Date.now()}-${Math.random().toString(16).slice(2)}`);
      localStorage.setItem("sindhu_device_id", id);
    }
    return id;
  }

  const SUPERSEDED_CLOSE_CODE = 4409;

  function connectWs() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/logs?device_id=${encodeURIComponent(getDeviceId())}`);
    ws.onopen = () => {
      connStatus.textContent = "● online"; connStatus.className = "conn-status conn-online";
      flushPending();
    };
    ws.onclose = (event) => {
      if (event.code === SUPERSEDED_CLOSE_CODE) {
        connStatus.textContent = "● replaced by another tab"; connStatus.className = "conn-status conn-offline";
        showToast({
          title: "Dashboard opened elsewhere",
          body: "This tab was disconnected because the dashboard was opened in another tab or window on this device.",
          isError: true, timeoutMs: 30000,
        });
        return; // do not auto-reconnect -- the newer tab is now the live session
      }
      connStatus.textContent = "● offline"; connStatus.className = "conn-status conn-offline";
      setTimeout(connectWs, 2000);
    };
    ws.onerror = () => ws.close();
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.channel === "log") appendLog(msg.message);
      globalListeners.forEach(fn => { try { fn(msg); } catch (e) { console.error(e); } });
      liveListeners.forEach(fn => { try { fn(msg); } catch (e) { console.error(e); } });
    };
  }

  // Dashboard preference (theme) sync: if another device changes it via
  // Settings, this device's theme flips live without a manual refresh.
  onGlobalLive((msg) => {
    if (msg.channel === "sync" && msg.entity === "settings") {
      apiGet("/api/settings").then(s => {
        document.documentElement.setAttribute("data-theme", s.theme);
        localStorage.setItem("sindhu_theme", s.theme);
      }).catch(() => {});
    }
  });

  // Grand Feature Expansion, Phase 4 Feature 26: Voice Alert on critical
  // events. Uses the browser's built-in speechSynthesis (no new
  // dependency, no audio file to host) -- fires from the SAME real-time
  // WebSocket sync.notify() events already broadcast for every
  // significant action (see Phase 1's Audit Trail), so this reacts the
  // instant the event happens, on whichever page the user is currently on,
  // not on the next poll. Deliberately narrow: only the two truly
  // safety-critical events (kill switch, account-wide drawdown pause) --
  // routine notifications (a strategy tag changed, a backup ran) should
  // never interrupt with sound.
  const VOICE_ALERT_EVENTS = {
    "kill_switch:activated": "Emergency: the kill switch has been activated. All trading is halted.",
    "account_drawdown:paused": "Warning: the account-wide drawdown circuit breaker has activated. New trades are paused for every strategy.",
  };

  function _speak(text) {
    try {
      if (!("speechSynthesis" in window)) return;
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 0.95;
      window.speechSynthesis.speak(utterance);
    } catch (e) { /* best-effort only -- never let a speech failure break the app */ }
  }

  function speakCriticalAlert(text) {
    if (localStorage.getItem("sindhu_voice_alerts_muted") === "true") return;
    _speak(text);
  }

  onGlobalLive((msg) => {
    if (msg.channel !== "sync") return;
    const key = `${msg.entity}:${msg.action}`;
    if (VOICE_ALERT_EVENTS[key]) speakCriticalAlert(VOICE_ALERT_EVENTS[key]);
  });

  // App-wide toast banner -- survives navigation (lives in #toastStack,
  // outside #content which route() wipes on every page change).
  function showToast({ title, body, isError, actionLabel, onAction, timeoutMs }) {
    const stack = document.getElementById("toastStack");
    const el = document.createElement("div");
    el.className = "toast" + (isError ? " toast-error" : "");
    el.innerHTML = `
      <button class="toast-close" aria-label="Dismiss">&times;</button>
      <div class="toast-title">${esc(title)}</div>
      <div class="toast-body">${esc(body)}</div>
      ${actionLabel ? `<div class="toast-actions"><button class="btn-ghost toast-action">${esc(actionLabel)}</button></div>` : ""}`;
    stack.appendChild(el);
    const remove = () => el.remove();
    el.querySelector(".toast-close").onclick = remove;
    if (actionLabel && onAction) {
      el.querySelector(".toast-action").onclick = () => { onAction(); remove(); };
    }
    setTimeout(remove, timeoutMs || 15000);
  }

  // A backtest finishing must be visible from ANY page, not just the
  // Backtesting page itself -- registered on the global (nav-surviving)
  // listener rather than the per-page one.
  onGlobalLive((msg) => {
    if (msg.channel === "job" && msg.event === "finished" && msg.kind === "backtest") {
      const ok = msg.status === "completed";
      showToast({
        title: ok ? "Backtest complete" : `Backtest ${msg.status}`,
        body: msg.batch_id
          ? `Batch ${msg.batch_id} -- view results in Backtest History.`
          : "View results in Backtest History.",
        isError: !ok,
        actionLabel: "View Results",
        onAction: () => {
          pendingHistoryBatchId = msg.batch_id || null;
          if (location.hash === "#backtest_history") route();
          else location.hash = "#backtest_history";
        },
      });
    }
  });

  // Automation Pipeline (Part 2): auto backtest -> optimize -> compare ->
  // paper trading, triggered the moment a strategy import succeeds (no
  // manual click anywhere). Same app-wide-visibility treatment as the
  // backtest toast above, plus a live-updating banner through every stage
  // since this runs unattended and can take several minutes.
  let activePipelineJobId = null;
  let pipelineBannerEl = null;

  function _pipelineStageLabel(msg) {
    // Part 4 (plain-language live logs): the backend now sends its own
    // plain-English stage_label alongside current_stage (see
    // automation_pipeline/pipeline.py) -- this fallback map only covers
    // stage values that predate that field or arrive without it.
    const fallbackLabels = {
      backtesting: "Running the strategy against historical price data",
      optimizing: "Testing different settings to find the best version of this strategy",
      comparing: "Saving the original vs optimized comparison",
      starting_paper_trading: "Starting Paper Trading with the winning version",
      completed: "Done -- see the results in Backtest History",
      aborted: "Could not continue -- see Live Logs for why",
      stopped: "Stopped by request -- see Live Logs for details",
    };
    let text = msg.stage_label || fallbackLabels[msg.current_stage] || msg.current_stage || "Starting";
    if (msg.current_strategy) text = `${msg.current_strategy} -- ${text}`;
    if (msg.current_stage === "optimizing" && msg.optimizer_tried != null && msg.optimizer_total != null) {
      text += ` (${msg.optimizer_tried}/${msg.optimizer_total} combinations tried)`;
    } else if (msg.done != null && msg.total != null) {
      text += ` (${msg.done}/${msg.total} coins)`;
    }
    return text;
  }

  onGlobalLive((msg) => {
    if (msg.channel === "job" && msg.event === "started" && msg.kind === "pipeline") {
      activePipelineJobId = msg.job_id;
      showToast({
        title: "Automation pipeline started",
        body: "Backtesting -> Optimizing -> Comparing -> Paper Trading, fully automatic.",
        timeoutMs: 6000,
      });
      return;
    }
    if (msg.channel === "progress" && msg.job_id === activePipelineJobId) {
      const stack = document.getElementById("toastStack");
      if (!pipelineBannerEl || !document.body.contains(pipelineBannerEl)) {
        pipelineBannerEl = document.createElement("div");
        pipelineBannerEl.className = "toast";
        pipelineBannerEl.innerHTML = `<div class="toast-title">Automation Pipeline</div><div class="toast-body" id="pipelineBannerBody"></div>`;
        stack.appendChild(pipelineBannerEl);
      }
      const body = pipelineBannerEl.querySelector("#pipelineBannerBody");
      if (body) body.textContent = _pipelineStageLabel(msg);
      return;
    }
    if (msg.channel === "job" && msg.event === "finished" && msg.kind === "pipeline") {
      if (pipelineBannerEl) { pipelineBannerEl.remove(); pipelineBannerEl = null; }
      activePipelineJobId = null;
      const ok = msg.status === "completed";
      showToast({
        title: ok ? "Automation pipeline finished" : `Automation pipeline ${msg.status}`,
        body: msg.batch_id
          ? "Backtest + optimization complete -- view the comparison in Backtest History."
          : "Check Logs for details.",
        isError: !ok,
        actionLabel: msg.batch_id ? "View Results" : undefined,
        onAction: msg.batch_id ? () => {
          pendingHistoryBatchId = msg.batch_id || null;
          if (location.hash === "#backtest_history") route();
          else location.hash = "#backtest_history";
        } : undefined,
      });
    }
  });

  // ------------------------------------------------------------ chrome (nav/sidebar/theme/logs)
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("overlay");
  document.getElementById("navToggle").onclick = () => {
    sidebar.classList.toggle("open");
    overlay.classList.toggle("open");
  };
  overlay.onclick = () => { sidebar.classList.remove("open"); overlay.classList.remove("open"); };

  const logsPanel = document.getElementById("logsPanel");
  document.getElementById("logsToggle").onclick = () => logsPanel.classList.toggle("open");
  document.getElementById("logsClose").onclick = () => logsPanel.classList.remove("open");

  // Manager Chat (Batch 4, Task 6): deterministic, read-only keyword Q&A --
  // no AI, no state changes. Reuses the Live Logs panel's slide-in styling.
  const chatPanel = document.getElementById("chatPanel");
  const chatMessages = document.getElementById("chatMessages");
  const chatInput = document.getElementById("chatInput");
  function chatAppend(text, who) {
    const div = document.createElement("div");
    div.style.margin = "6px 0";
    div.style.padding = "6px 8px";
    div.style.borderRadius = "6px";
    div.style.fontSize = "13px";
    div.style.background = who === "user" ? "var(--accent-bg, #2a2a35)" : "var(--card-bg, #1c1c24)";
    div.textContent = text;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }
  async function chatSend() {
    const question = chatInput.value.trim();
    if (!question) return;
    chatAppend(question, "user");
    chatInput.value = "";
    try {
      const res = await apiPost("/api/manager-chat/ask", { question, lang: getLang() === "en" ? "en" : "ur" });
      chatAppend(res.answer, "bot");
    } catch (e) {
      chatAppend(getLang() === "en" ? "Could not get an answer right now." : "Abhi jawab nahi mil saka.", "bot");
    }
  }
  document.getElementById("chatToggle").onclick = () => {
    chatPanel.classList.toggle("open");
    document.getElementById("chatPanelTitle").textContent = t("Manager Chat");
    chatInput.placeholder = getLang() === "en" ? "Ask anything..." : "Kuch bhi poochein...";
    if (chatPanel.classList.contains("open") && !chatMessages.dataset.greeted) {
      chatMessages.dataset.greeted = "1";
      chatAppend(getLang() === "en"
        ? "Hi! Ask me about strategy performance, today's activity, signals, balance, locked strategies, or the system's maturity level."
        : "Salaam! Mujhse strategy performance, aaj ki activity, signals, balance, locked strategies, ya system ka maturity level poochh sakte hain.", "bot");
    }
  };
  document.getElementById("chatClose").onclick = () => chatPanel.classList.remove("open");
  document.getElementById("chatSend").onclick = chatSend;
  chatInput.addEventListener("keydown", (e) => { if (e.key === "Enter") chatSend(); });

  const themeToggle = document.getElementById("themeToggle");
  themeToggle.onclick = () => {
    const root = document.documentElement;
    const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    localStorage.setItem("sindhu_theme", next);
    autosave("POST", "/api/settings", { theme: next }).catch(() => {});
  };
  document.documentElement.setAttribute("data-theme", localStorage.getItem("sindhu_theme") || "dark");

  // Grand Feature Expansion, Phase 4 Feature 17: Beginner Mode -- a
  // per-browser display preference (localStorage only, like Voice Alert's
  // mute toggle) that highlights every existing "?" help icon via a body
  // class, so someone new to trading/SINDHU notices they can click any of
  // them for a plain-language explanation. Never hides or changes a real
  // number -- purely a visibility nudge on top of the glossary tooltip
  // mechanism that already exists everywhere.
  function applyBeginnerModeClass() {
    document.body.classList.toggle("beginner-mode", localStorage.getItem("sindhu_beginner_mode") === "true");
  }
  applyBeginnerModeClass();

  // Grand Feature Expansion, Phase 4 Feature 16: Onboarding Tutorial -- a
  // short, dependency-free spotlight tour over the sidebar, shown once
  // automatically (localStorage flag) and replayable anytime from
  // Settings. Steps with a `selector` are anchored to a real nav element
  // (a transparent cutout via box-shadow, no canvas/image); steps without
  // one are shown as a centered tooltip (welcome/closing steps).
  function onboardingSteps() {
    const en = getLang() === "en";
    return [
      { selector: null,
        title: en ? "Welcome to SINDHU" : "SINDHU Mein Khush Aamdeed",
        text: en ? "A quick 30-second look around -- click Next, or Skip if you'd rather explore on your own."
                 : "Chaliye 30 second mein ek chakkar laga lete hain -- Next par click karein, ya khud explore karne ke liye Skip karein." },
      { selector: 'a[data-id="home"]',
        title: en ? "Home" : "Home",
        text: en ? "Your overall system status at a glance -- including Today's Focus, the single most important thing to check right now."
                 : "Ek nazar mein poore system ka haal -- Aaj Ka Focus bhi yahin hai, abhi sabse zaroori cheez check karne ke liye." },
      { selector: 'a[data-id="backtesting"]',
        title: en ? "Backtesting" : "Backtesting",
        text: en ? "Test a trading strategy against real historical price data before ever risking real money on it."
                 : "Kisi trading strategy ko asal purani price data par test karein, real paisa lagane se pehle." },
      { selector: 'a[data-id="paper_trading"]',
        title: en ? "Paper Trading" : "Paper Trading",
        text: en ? "SINDHU trades with fake (simulated) money in real-time market conditions -- see how strategies actually perform live, with zero real risk."
                 : "SINDHU nakli (simulated) paise se real-time market mein trade karta hai -- dekhein strategies asal mein kaisi perform karti hain, bilkul risk ke bina." },
      { selector: 'a[data-id="ceo"]',
        title: en ? "SINDHU CEO" : "SINDHU CEO",
        text: en ? "Settings, Beginner Mode, backups, and a system-wide checkup all live here."
                 : "Settings, Beginner Mode, backups, aur poore system ka checkup -- sab yahan milta hai." },
      { selector: null,
        title: en ? "One more thing" : "Aik Aur Baat",
        text: en ? "Anywhere you see a small \"?\" icon next to a number or term, click it for a plain-language explanation -- no coding or trading background needed."
                 : "Jahan bhi kisi number ya term ke saath chhota sa \"?\" icon dikhe, click karke plain-language explanation dekhein -- coding ya trading ka background zaroori nahi." },
    ];
  }

  function startOnboardingTour() {
    const steps = onboardingSteps();
    let idx = 0;
    const dim = document.createElement("div");
    dim.className = "tour-dim";
    const spotlight = document.createElement("div");
    spotlight.className = "tour-spotlight";
    spotlight.style.display = "none";
    const tooltip = document.createElement("div");
    tooltip.className = "tour-tooltip";
    document.body.append(dim, spotlight, tooltip);

    function cleanup() {
      dim.remove(); spotlight.remove(); tooltip.remove();
      localStorage.setItem("sindhu_onboarding_seen", "true");
    }

    function renderStep() {
      const step = steps[idx];
      const en = getLang() === "en";
      const target = step.selector ? document.querySelector(step.selector) : null;
      if (target) {
        const r = target.getBoundingClientRect();
        spotlight.style.display = "block";
        spotlight.style.top = `${r.top - 6}px`;
        spotlight.style.left = `${r.left - 6}px`;
        spotlight.style.width = `${r.width + 12}px`;
        spotlight.style.height = `${r.height + 12}px`;
        let top = r.bottom + 10;
        let left = r.left;
        if (top + 160 > window.innerHeight) top = Math.max(10, r.top - 170);
        if (left + 300 > window.innerWidth) left = Math.max(10, window.innerWidth - 312);
        tooltip.style.top = `${top}px`;
        tooltip.style.left = `${left}px`;
      } else {
        spotlight.style.display = "none";
        tooltip.style.top = "40%";
        tooltip.style.left = "50%";
        tooltip.style.transform = "translate(-50%, -50%)";
      }
      if (target) tooltip.style.transform = "none";
      tooltip.innerHTML = `
        <div class="tour-title">${esc(step.title)}</div>
        <div class="tour-body">${esc(step.text)}</div>
        <div class="tour-footer">
          <span class="tour-step-count">${idx + 1} / ${steps.length}</span>
          <span class="btn-row">
            ${idx > 0 ? `<button class="btn-ghost" id="tourBack">${en ? "Back" : "Peechay"}</button>` : ""}
            <button class="btn-ghost" id="tourSkip">${en ? "Skip" : "Skip"}</button>
            <button class="btn" id="tourNext">${idx === steps.length - 1 ? (en ? "Finish" : "Khatam") : (en ? "Next" : "Agla")}</button>
          </span>
        </div>`;
      document.getElementById("tourSkip").onclick = cleanup;
      document.getElementById("tourNext").onclick = () => {
        if (idx === steps.length - 1) { cleanup(); return; }
        idx += 1; renderStep();
      };
      const backBtn = document.getElementById("tourBack");
      if (backBtn) backBtn.onclick = () => { idx -= 1; renderStep(); };
    }
    renderStep();
  }

  if (localStorage.getItem("sindhu_onboarding_seen") !== "true") {
    // Give the nav a moment to render (it loads via its own async fetch)
    // before anchoring the first real step's spotlight to it.
    setTimeout(() => {
      if (document.querySelector('a[data-id="home"]')) startOnboardingTour();
    }, 1200);
  }

  const langToggle = document.getElementById("langToggle");
  langToggle.textContent = LANG === "ur" ? "UR" : "EN";
  langToggle.title = LANG === "ur" ? "Switch to English" : "Roman Urdu mein dekhein";
  langToggle.onclick = () => {
    setLang(LANG === "ur" ? "en" : "ur");
    langToggle.textContent = LANG === "ur" ? "UR" : "EN";
    langToggle.title = LANG === "ur" ? "Switch to English" : "Roman Urdu mein dekhein";
  };

  // Collapsible desktop sidebar rail -- persisted across sessions.
  const appShell = document.querySelector(".app-shell");
  const railToggle = document.getElementById("railToggle");
  appShell.classList.toggle("rail-collapsed", localStorage.getItem("sindhu_rail_collapsed") === "1");
  railToggle.onclick = () => {
    const collapsed = appShell.classList.toggle("rail-collapsed");
    localStorage.setItem("sindhu_rail_collapsed", collapsed ? "1" : "0");
  };

  // Live clock (topbar).
  function updateClock() {
    document.getElementById("clockDisplay").textContent = new Date().toLocaleTimeString();
  }
  updateClock();
  setInterval(updateClock, 1000);

  // Version / system health pill (topbar) -- independent of whichever
  // page is open, so it always reflects live server state.
  async function refreshTopbarStatus() {
    const h = await apiGet("/api/home").catch(() => null);
    if (!h) return;
    document.getElementById("versionPill").textContent = `v${h.version}`;
    const healthPill = document.getElementById("healthPill");
    healthPill.textContent = h.system_health;
    healthPill.className = `pill ${h.system_health === "OK" ? "pill-completed" : "pill-error"}`;
  }
  refreshTopbarStatus();
  setInterval(refreshTopbarStatus, 20000);

  // Master Task 3, Phase 0.8a/0.8c/0.8e: System Status Banner, visible from
  // every page. Reuses the same /api/paper-trading/status the Paper
  // Trading page itself polls -- no new endpoint needed for the numbers
  // (running/started_at/last_tick_at/trades_today), just a second consumer
  // of data that already exists.
  function _fmtClock(iso) {
    if (!iso) return "--";
    try { return new Date(iso).toLocaleTimeString(); } catch (e) { return "--"; }
  }
  async function refreshEngineStatusBanner() {
    const banner = document.getElementById("engineStatusBanner");
    if (!banner) return;
    const s = await apiGet("/api/paper-trading/status").catch(() => null);
    if (!s) { banner.style.display = "none"; document.documentElement.style.setProperty("--banner-h", "0px"); return; }
    const en = getLang() === "en";
    const runningLabel = s.running
      ? `<span class="esb-running">🟢 ${en ? "RUNNING" : "CHAL RAHA HAI"}${s.started_at ? ` (${en ? "since" : "se"} ${_fmtClock(s.started_at)})` : ""}</span>`
      : `<span class="esb-stopped">🔴 ${en ? "STOPPED" : "BAND HAI"}</span>`;
    banner.innerHTML = `
      <span class="esb-item">${runningLabel}</span>
      <span class="esb-item esb-muted">${en ? "Last heartbeat" : "Aakhri Dhadkan"}: ${_fmtClock(s.last_tick_at)}</span>
      <span class="esb-item esb-muted">${en ? "Today" : "Aaj"}: ${s.trades_today || 0} ${en ? "trades" : "trades"}</span>`;
    banner.style.display = "flex";
    document.documentElement.style.setProperty("--banner-h", "30px");
  }
  refreshEngineStatusBanner();
  setInterval(refreshEngineStatusBanner, 20000);
  onGlobalLive((msg) => { if (msg.channel === "paper") refreshEngineStatusBanner(); });

  // Notifications dropdown, backed by the Activity Feed.
  let lastSeenActivityAt = localStorage.getItem("sindhu_last_seen_activity") || "";
  async function refreshNotifications(markSeen) {
    const res = await apiGet("/api/activity?limit=10").catch(() => ({ activity: [] }));
    const items = res.activity || [];
    const unseen = lastSeenActivityAt ? items.filter(a => a.created_at > lastSeenActivityAt).length : items.length;
    const badge = document.getElementById("notifBadge");
    if (unseen > 0) { badge.textContent = unseen > 9 ? "9+" : String(unseen); badge.style.display = "block"; }
    else { badge.style.display = "none"; }
    document.getElementById("notifMenu").innerHTML = items.map(a => `
      <div class="dropdown-item" style="cursor:default;">
        <div style="font-size:12px;">${esc(a.message)}</div>
        <div class="muted" style="font-size:11px;">${esc((a.created_at || "").slice(0, 19))}</div>
      </div>`).join("") || `<div class="dropdown-item muted">No activity yet.</div>`;
    if (markSeen && items.length) {
      lastSeenActivityAt = items[0].created_at;
      localStorage.setItem("sindhu_last_seen_activity", lastSeenActivityAt);
      badge.style.display = "none";
    }
  }
  refreshNotifications(false);
  setInterval(() => refreshNotifications(false), 20000);
  onGlobalLive((msg) => { if (msg.channel === "sync" || msg.channel === "job") refreshNotifications(false); });

  const notifBtn = document.getElementById("notifBtn");
  const notifMenu = document.getElementById("notifMenu");
  const quickActionsBtn = document.getElementById("quickActionsBtn");
  const quickActionsMenu = document.getElementById("quickActionsMenu");

  notifBtn.onclick = (e) => {
    e.stopPropagation();
    quickActionsMenu.classList.remove("open");
    notifMenu.classList.toggle("open");
    if (notifMenu.classList.contains("open")) refreshNotifications(true);
  };
  quickActionsBtn.onclick = (e) => {
    e.stopPropagation();
    notifMenu.classList.remove("open");
    quickActionsMenu.classList.toggle("open");
  };
  document.addEventListener("click", () => {
    notifMenu.classList.remove("open");
    quickActionsMenu.classList.remove("open");
    document.getElementById("searchResults").classList.remove("open");
  });

  document.getElementById("qaDownload").onclick = async () => {
    await apiPost("/api/data/download");
    appendLog("Download job started from Quick Actions.");
  };
  document.getElementById("qaBackup").onclick = async () => {
    await apiPost("/api/backup/create");
    appendLog("Manual backup created from Quick Actions.");
  };
  document.getElementById("qaLogs").onclick = () => {
    document.getElementById("logsPanel").classList.toggle("open");
  };
  document.getElementById("qaRestart").onclick = async () => {
    await apiPost("/api/system/restart-services");
    appendLog("Services soft-restarted (server caches cleared).");
  };
  // Master Task 3, Phase 0.8f: One-Click Health Check -- "Test Everything"
  // runs a quick self-check (database, engine state, live candle/ticker
  // fetch) and reports pass/fail per item, right from the dashboard, no
  // logs or terminal access needed (especially useful on the cloud deploy).
  document.getElementById("qaHealthCheck").onclick = async () => {
    appendLog("Running health check...");
    let r;
    try {
      r = await apiGet("/api/paper-trading/health-check", 20000);
    } catch (e) {
      showToast({ title: "Health check failed to run", body: e.message, isError: true });
      return;
    }
    const lines = r.checks.map(c => `${c.ok ? "✓" : "✗"} ${c.name}: ${c.detail}`).join("\n");
    appendLog(`Health check (${r.all_ok ? "ALL OK" : "ISSUE FOUND"}):\n${lines}`);
    showToast({
      title: r.all_ok ? "Health Check: All Good ✓" : "Health Check: Issue Found ✗",
      body: lines,
      isError: !r.all_ok,
      timeoutMs: 20000,
    });
  };

  // Global search across coins / strategies / lessons / reports / trades.
  const searchInput = document.getElementById("globalSearch");
  const searchResults = document.getElementById("searchResults");
  const doSearch = debounce(async () => {
    const q = searchInput.value.trim();
    if (!q) { searchResults.classList.remove("open"); return; }
    const res = await apiGet(`/api/search?q=${encodeURIComponent(q)}`).catch(() => null);
    if (!res) return;

    const groups = [
      { title: "Coins", items: res.coins.map(c => ({ label: c, go: () => { location.hash = "#market"; } })) },
      { title: "Strategies", items: res.strategies.map(s => ({ label: s.name, go: () => { location.hash = "#strategies"; } })) },
      { title: "Lessons", items: res.lessons.map(l => ({ label: `${l.title} (${l.category})`, go: () => { location.hash = "#knowledge"; } })) },
      { title: "Reports", items: res.reports.map(r => ({ label: `${r.strategy_name} - ${(r.created_at || "").slice(0, 10)}`, go: () => { location.hash = "#reports"; } })) },
      { title: "Trades", items: res.trades.map(t => ({ label: `${t.symbol} ${t.side} pnl=${t.pnl != null ? t.pnl.toFixed(2) : "-"}`, go: () => { location.hash = "#reports"; } })) },
    ].filter(g => g.items.length);

    searchResults.innerHTML = groups.map((g, gi) => `
      <div class="search-group-title">${g.title}</div>
      ${g.items.map((it, ii) => `<div class="search-result-item" data-gi="${gi}" data-ii="${ii}">${esc(it.label)}</div>`).join("")}
    `).join("") || `<div class="search-group-title">No results</div>`;
    searchResults.classList.add("open");

    groups.forEach((g, gi) => g.items.forEach((it, ii) => {
      const el = searchResults.querySelector(`[data-gi="${gi}"][data-ii="${ii}"]`);
      if (el) el.onclick = () => { it.go(); searchResults.classList.remove("open"); searchInput.value = ""; };
    }));
  }, 300);
  searchInput.addEventListener("input", doSearch);
  searchInput.addEventListener("focus", () => { if (searchInput.value.trim()) searchResults.classList.add("open"); });
  searchResults.addEventListener("click", (e) => e.stopPropagation());
  searchInput.addEventListener("click", (e) => e.stopPropagation());

  const NAV_ICONS = {
    dashboard: '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>',
    market: '<path d="M4 20V10M10 20V4M16 20v-8M22 20v-4"/>',
    database: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
    layers: '<path d="M12 3l9 5-9 5-9-5 9-5z"/><path d="M3 13l9 5 9-5"/>',
    book: '<path d="M4 4.5A2.5 2.5 0 016.5 2H20v17H6.5A2.5 2.5 0 004 21.5v-17z"/><path d="M4 19a2.5 2.5 0 012.5-2.5H20"/>',
    flask: '<path d="M9 2v6L4 20a1 1 0 001 1h14a1 1 0 001-1L15 8V2"/><path d="M9 2h6"/><path d="M6.5 15h11"/>',
    wallet: '<rect x="2" y="6" width="20" height="14" rx="2"/><path d="M2 10h20"/><circle cx="17" cy="15" r="1.4"/>',
    mirror: '<circle cx="12" cy="12" r="9"/><path d="M12 3v18"/>',
    dna: '<path d="M7 3c0 5 10 5 10 10s-10 5-10 10"/><path d="M17 3c0 5-10 5-10 10s10 5 10 10"/><path d="M8 7h8M8 17h8"/>',
    chart: '<path d="M3 17l5-5 4 4 8-9"/><path d="M3 21h18"/>',
    news: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 8h10M7 12h10M7 16h6"/>',
    send: '<path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/>',
    gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 00.3 1.9 2 2 0 11-2.8 2.8 1.7 1.7 0 00-1.9-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1-1.6 1.7 1.7 0 00-1.9.3 2 2 0 11-2.8-2.8 1.7 1.7 0 00.3-1.9 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.6-1 1.7 1.7 0 00-.3-1.9 2 2 0 112.8-2.8 1.7 1.7 0 001.9.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.9-.3 2 2 0 112.8 2.8 1.7 1.7 0 00-.3 1.9V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z"/>',
    compiler: '<path d="M9 3L5 21"/><path d="M15 3l4 18"/><path d="M12 3v18"/><circle cx="12" cy="12" r="2"/>',
    ai_center: '<rect x="5" y="7" width="14" height="12" rx="2"/><circle cx="9.5" cy="13" r="1.3"/><circle cx="14.5" cy="13" r="1.3"/><path d="M12 7V3"/><circle cx="12" cy="2.3" r="1"/><path d="M3 12h2M19 12h2"/>',
    history: '<path d="M3 12a9 9 0 109-9 9 9 0 00-6.4 2.6"/><path d="M3 3v6h6"/><path d="M12 7v5l4 2"/>',
    ceo: '<path d="M12 2l2.5 5 5.5.8-4 3.9.9 5.5-4.9-2.6L6.6 17.2l.9-5.5-4-3.9 5.5-.8z"/>',
    spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4"/><path d="M12 8l1.8 2.2L16 12l-2.2 1.8L12 16l-1.8-2.2L8 12l2.2-1.8z"/>',
    target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
  };

  // Mobile bottom tab bar: the most-used pages, one tap away without the
  // hamburger drawer. Rendered from the same /api/nav payload as the
  // sidebar (single source of truth for what's enabled), just filtered to
  // this fixed shortlist. Labels are shortened to fit a 5-tab bar.
  const BOTTOM_NAV_IDS = ["home", "backtesting", "paper_trading", "strategies", "ceo"];
  const BOTTOM_NAV_SHORT_LABELS = {
    home: "Home", backtesting: "Backtest", paper_trading: "Paper",
    strategies: "Strategies", ceo: "CEO",
  };

  async function renderNav() {
    const { pages, groups } = await apiGet("/api/nav");
    const list = document.getElementById("navList");
    // Navigation Reorganization: pages now render as labeled groups
    // (Overview / Strategies / Backtesting / Paper Trading / Intelligence
    // / Control / Reports) instead of one long flat list -- falls back to
    // a flat list if an older /api/nav response has no `groups` field.
    // A page with `external_url` (e.g. Concepts, still a standalone static
    // page rather than a ported SPA route) links straight to that URL
    // instead of a `#hash` -- a normal same-tab navigation away from the
    // SPA, not routed through PAGES{}. Keeps concepts.html untouched while
    // still making it reachable by a single click from the sidebar.
    const navHref = p => p.external_url ? p.external_url : `#${p.id}`;
    if (groups && groups.length) {
      const byGroup = {};
      pages.forEach(p => { (byGroup[p.group] = byGroup[p.group] || []).push(p); });
      list.innerHTML = groups.filter(g => byGroup[g]).map(g => `
        <li class="nav-group-label">${esc(g)}</li>
        ${byGroup[g].map(p => `
          <li><a href="${navHref(p)}" data-id="${p.id}" title="${esc(p.label)}">
            <svg viewBox="0 0 24 24">${NAV_ICONS[p.icon] || NAV_ICONS.dashboard}</svg>
            <span class="nav-label">${esc(p.label)}</span>
          </a></li>`).join("")}`).join("");
    } else {
      list.innerHTML = pages.map(p => `
        <li><a href="${navHref(p)}" data-id="${p.id}" title="${esc(p.label)}">
          <svg viewBox="0 0 24 24">${NAV_ICONS[p.icon] || NAV_ICONS.dashboard}</svg>
          <span class="nav-label">${esc(p.label)}</span>
        </a></li>`).join("");
    }

    const bottom = document.getElementById("bottomNav");
    if (bottom) {
      const byId = Object.fromEntries(pages.map(p => [p.id, p]));
      bottom.innerHTML = BOTTOM_NAV_IDS.filter(id => byId[id]).map(id => `
        <a href="#${id}" data-id="${id}" title="${esc(byId[id].label)}">
          <svg viewBox="0 0 24 24">${NAV_ICONS[byId[id].icon] || NAV_ICONS.dashboard}</svg>
          <span>${esc(BOTTOM_NAV_SHORT_LABELS[id] || byId[id].label)}</span>
        </a>`).join("");
    }
  }

  function setActiveNav(id) {
    document.querySelectorAll("#navList a, #bottomNav a").forEach(a => {
      a.classList.toggle("active", a.dataset.id === id);
    });
  }

  // ------------------------------------------------------------ router
  const content = document.getElementById("content");

  // Mobile table->card support: below 768px, CSS renders every table row as
  // a stacked card and shows each cell's column name via td[data-label]
  // (see app.css). Rather than hand-editing all 50+ table render sites,
  // this stamps data-label onto every td generically from its own table's
  // thead -- and a MutationObserver re-stamps whenever any page (or a live
  // tbody refresh) injects new rows, so current AND future tables get card
  // mode for free. Attribute writes don't trigger childList mutations, so
  // this can't loop. Desktop ignores data-label entirely.
  function stampTableLabels() {
    content.querySelectorAll("table").forEach(table => {
      const ths = table.querySelectorAll("thead th");
      if (!ths.length) return;
      const labels = [...ths].map(th => th.textContent.trim());
      table.querySelectorAll(":scope > tbody > tr").forEach(tr => {
        const tds = tr.children;
        // A lone td in a multi-column table is a colspan empty-state
        // message ("No trades yet") -- leave it unlabeled so it renders
        // as plain full-width text instead of "NAME: No trades yet".
        if (tds.length === 1 && labels.length > 1) return;
        for (let i = 0; i < tds.length && i < labels.length; i++) {
          if (labels[i]) tds[i].setAttribute("data-label", labels[i]);
        }
      });
    });
  }
  // Rooted on window ON PURPOSE: an observer created without any reachable
  // reference is eligible for garbage collection (verified live -- an
  // unreferenced observer here stamped fine right after load, then went
  // dead minutes later once GC ran, silently leaving later re-renders
  // unlabeled). window.* is always a GC root, so this can never be
  // collected for the lifetime of the page.
  window.__sindhuTableLabelObserver = new MutationObserver(debounce(stampTableLabels, 40));
  window.__sindhuTableLabelObserver.observe(content, { childList: true, subtree: true });

  // ---------------------------------------------------------------- Compare
  // Consolidates the earlier standalone Strategy Optimizer / Project
  // Overview pages: all 14 strategies side by side, before/after where the
  // recent tuning pass touched them. Pure presentation -- /api/compare-strategies
  // reuses the same computation as the Home dashboard's aggregate summary.
  function dualTpVerdictPill(v, en) {
    if (v === "better") return `<span class="pill pill-up">&uarr; ${en ? "Better" : "Behtar"}</span>`;
    if (v === "worse") return `<span class="pill pill-down">&darr; ${en ? "Worse" : "Kam"}</span>`;
    if (v === "equivalent") return `<span class="pill pill-muted">&harr; ${en ? "Equivalent" : "Barabar"}</span>`;
    return `<span class="muted">-</span>`;
  }

  // ------------------------------------------------------------ STRATEGY LIFECYCLE
  function lifecyclePfSpan(pf) {
    if (pf == null) return `<span class="muted">-</span>`;
    const cls = pf >= 1.0 ? "positive" : "negative";
    return `<span class="stat-hero ${cls}">${pf.toFixed(4)}</span>`;
  }

  function openPaperTradingConfirm(row, en, onDone) {
    const pf = row.backtest.profit_factor;
    const profitable = pf != null && pf >= 1.0;
    const overlay = document.createElement("div");
    overlay.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:9999;display:flex;align-items:center;justify-content:center;";
    const pfText = pf != null ? pf.toFixed(4) : (en ? "unknown (no backtest data)" : "maloom nahi (backtest data nahi)");
    overlay.innerHTML = `
      <div style="background:var(--bg-elevated,#1a1f2b);color:inherit;border-radius:12px;padding:28px;max-width:480px;width:92%;box-shadow:0 20px 60px rgba(0,0,0,.4);">
        <div class="section-title" style="margin-top:0;">${en ? "Move to Paper Trading?" : "Paper Trading Mein Bhejein?"}</div>
        <p style="margin:0 0 6px;"><b>${esc(row.name)}</b></p>
        <p style="margin:0 0 14px;">${en ? "Current Profit Factor" : "Abhi ka Profit Factor"}: <b>${pfText}</b></p>
        ${profitable
          ? `<div class="pill pill-up" style="display:inline-block;margin-bottom:14px;">${en ? "This strategy is profitable. Activate it in paper trading?" : "Ye strategy munafa mein hai. Paper trading mein activate karein?"}</div>`
          : `<div class="pill pill-down" style="display:inline-block;margin-bottom:14px;">${en
              ? `Warning: this strategy is currently losing (profit factor ${pfText}). Are you sure you want to activate it in paper trading anyway?`
              : `Warning: ye strategy abhi nuqsaan mein hai (profit factor ${pfText}). Kya aap phir bhi ise paper trading mein activate karna chahte hain?`}</div>`}
        <p class="muted" style="font-size:12px;margin:0 0 16px;">${en
          ? "This only flips this strategy's paper-trading switch on. Every existing safety gate (Wilson score, Confluence threshold, Signal Freshness, Incomplete Lock) still applies before any real signal fires."
          : "Ye sirf strategy ka paper-trading switch ON karta hai. Har existing safety gate (Wilson score, Confluence threshold, Signal Freshness, Incomplete Lock) ab bhi lagu rahega, kisi bhi signal se pehle."}</p>
        <div class="btn-row" style="justify-content:flex-end;">
          <button class="btn-ghost" id="lcCancelBtn">${en ? "Cancel" : "Cancel"}</button>
          <button class="btn" id="lcConfirmBtn">${en ? "Yes, activate" : "Haan, activate karein"}</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    const close = () => overlay.remove();
    overlay.onclick = (e) => { if (e.target === overlay) close(); };
    document.getElementById("lcCancelBtn").onclick = close;
    document.getElementById("lcConfirmBtn").onclick = async () => {
      const btn = document.getElementById("lcConfirmBtn");
      btn.disabled = true;
      try {
        const pc = row.paper_config || {};
        await apiPost(`/api/paper-trading/strategy-config/${row.strategy_id}`, {
          enabled: true,
          priority: pc.priority != null ? pc.priority : 5,
          supported_coins: pc.supported_coins || [],
          supported_market_types: pc.supported_market_types || [],
        });
        close();
        showToast({ title: en ? "Activated" : "Activate ho gaya", body: `${row.name} ${en ? "is now enabled in paper trading." : "ab paper trading mein enabled hai."}` });
        if (onDone) onDone();
      } catch (e) {
        btn.disabled = false;
        showToast({ title: en ? "Failed" : "Nakam", body: e.message, isError: true });
      }
    };
  }

  function lifecycleOptimizerCell(row, en) {
    const opt = row.optimizer || {};
    const base = row.backtest.profit_factor;
    if (opt.medium == null && opt.strict == null) {
      return `<span class="muted" style="font-size:12px;">${en ? "N/A" : "N/A"}</span>`;
    }
    const vals = [["Loose", base], ["Medium", opt.medium ? opt.medium.profit_factor : null], ["Strict", opt.strict ? opt.strict.profit_factor : null]]
      .filter(([, v]) => v != null);
    const bestVal = Math.max(...vals.map(([, v]) => v));
    return vals.map(([label, v]) => `
      <div style="font-size:12px;color:${v >= 1.0 ? "var(--green)" : "var(--red)"};${v === bestVal ? "font-weight:700;" : ""}">
        ${label}: ${v.toFixed(3)}${v === bestVal ? " ★" : ""}
      </div>`).join("");
  }

  // ------------------------------------------------ MASTER TASK 2, PART 2/3
  // Strategy Comparison table shared by both the "Profitable" and "Under
  // Evaluation" sections on the Paper Trading page -- same row renderer for
  // both so neither section can ever end up with less detail than the
  // other (a genuine transparency requirement, not cosmetic).
  function strategyComparisonTableHtml(rows, pfById, cls) {
    if (!rows.length) {
      return `<div class="card muted">No strategies in this group yet.</div>`;
    }
    return `
      <div class="table-wrap"><table>
        <thead><tr>
          <th><input type="checkbox" class="pt-select-all-section" style="width:auto;"></th>
          <th>Strategy</th><th>Backtest PF</th><th>Trades</th><th>Wins</th><th>Losses</th>
          <th>Win Ratio</th><th>PnL ($)</th><th>Current Balance</th>
          <th>Confidence ${helpIcon("confidence_score")}</th><th>Streak</th><th></th>
        </tr></thead>
        <tbody>${rows.map(p => {
          const pf = pfById[p.strategy_id];
          const losses = p.closed_trades - p.win_count;
          return `
          <tr data-confidence="${p.confidence_score != null ? p.confidence_score : ""}">
            <td><input type="checkbox" class="pt-bulk-select" data-id="${p.strategy_id}" style="width:auto;"></td>
            <td style="max-width:200px;">${esc(p.strategy_name || p.strategy_id)}</td>
            <td><span class="${pf != null ? (pf > 1.0 ? "positive" : "negative") : ""}">${pf != null ? pf.toFixed(4) : "-"}</span></td>
            <td>${p.closed_trades}</td>
            <td>${p.win_count}</td>
            <td>${losses}</td>
            <td>${Number(p.win_rate).toFixed(1)}%</td>
            <td class="${p.total_pnl >= 0 ? "pill-up" : "pill-down"}">${p.total_pnl.toFixed(2)}</td>
            <td>$${Number(p.balance).toFixed(2)}</td>
            <td>${p.confidence_score != null ? p.confidence_score + "%" : "-"}</td>
            <td>${p.streak && p.streak.count ? `<span class="pill ${p.streak.type === "win" ? "pill-bullish" : "pill-error"}">${p.streak.count} ${p.streak.type}</span>` : "-"}</td>
            <td>
              <div class="pt-action-group">
                <button class="btn-ghost pt-strategy-periods" data-id="${p.strategy_id}" data-name="${esc(p.strategy_name || p.strategy_id)}">By Period</button>
                <button class="btn-ghost pt-controls" data-id="${p.strategy_id}" data-name="${esc(p.strategy_name || p.strategy_id)}">Controls</button>
                <button class="btn-ghost pt-override" data-id="${p.strategy_id}" data-active="${p.manual_alert ? "1" : "0"}">
                  ${p.manual_alert ? "Flagged for Telegram" : "Flag for Telegram"}
                </button>
                <button class="btn-ghost pt-genealogy" data-id="${p.strategy_id}" data-name="${esc(p.strategy_name || p.strategy_id)}">History</button>
                <button class="btn-ghost pt-readiness" data-id="${p.strategy_id}" data-name="${esc(p.strategy_name || p.strategy_id)}">Real-Trading Check</button>
              </div>
            </td>
          </tr>`;
        }).join("")}</tbody>
      </table></div>`;
  }

  // Per-strategy drill-down: the SAME time-period breakdown the whole
  // Paper Trading page offers, narrowed to one strategy's own independent
  // book. One request returns all six periods at once, so every number in
  // the table is from the same instant rather than from six separate
  // moments as the reader clicks around.
  function openStrategyPeriodsModal(strategyId, strategyName) {
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.innerHTML = `
      <div class="modal-panel modal-wide">
        <div class="modal-head">
          <div>
            <div class="modal-eyebrow">Strategy record</div>
            <h3 class="modal-title">${esc(strategyName)}</h3>
          </div>
          <button class="btn-ghost" data-modal-close>Close</button>
        </div>
        <div id="spmBody" class="muted">Loading...</div>
      </div>`;
    document.body.appendChild(overlay);
    const close = () => overlay.remove();
    overlay.onclick = (e) => { if (e.target === overlay) close(); };
    overlay.querySelector("[data-modal-close]").onclick = close;

    apiGet(`/api/paper-trading/strategy-periods/${strategyId}`).then(d => {
      const body = overlay.querySelector("#spmBody");
      const open = (d.periods[0] || {}).open_positions || 0;
      body.innerHTML = `
        <div class="modal-stat-row">
          <div><span class="modal-stat-label">Balance right now</span><span class="modal-stat-value">$${Number(d.current_balance).toFixed(2)}</span></div>
          <div><span class="modal-stat-label">Started from</span><span class="modal-stat-value">$${Number(d.initial_balance).toFixed(2)}</span></div>
          <div><span class="modal-stat-label">Open right now</span><span class="modal-stat-value">${fmtNum(open)}</span></div>
          <div><span class="modal-stat-label">Status</span><span class="modal-stat-value">${
            !d.enabled ? '<span class="pill pill-muted">Off</span>'
            : d.paused ? '<span class="pill pill-pending">Paused</span>'
            : '<span class="pill pill-bullish">Running</span>'}</span></div>
        </div>
        <p class="muted plain-note">This is this strategy's own separate account. Its balance and results are never mixed with, or averaged against, any other strategy.</p>
        <div class="table-wrap"><table>
          <thead><tr>
            <th>Period</th><th>Trades</th><th>Wins</th><th>Losses</th><th>Win Ratio</th><th>Profit / Loss</th>
          </tr></thead>
          <tbody>${d.periods.map(p => `
            <tr>
              <td><b>${esc(p.label)}</b></td>
              <td>${fmtNum(p.closed_trades)}</td>
              <td>${fmtNum(p.win_count)}</td>
              <td>${fmtNum(p.loss_count)}</td>
              <td>${p.closed_trades ? p.win_rate.toFixed(1) + "%" : '<span class="muted">-</span>'}</td>
              <td>${p.closed_trades ? pnlSpan(p.total_pnl) : '<span class="muted">no trades</span>'}</td>
            </tr>`).join("")}</tbody>
        </table></div>
        <p class="muted plain-note">Open trades are shown once, at the top, and are never counted as wins or losses &mdash; a trade that has not finished has no result yet.</p>
        <div class="btn-row" style="margin-top:14px;">
          <button class="btn-ghost" id="spmControls">Open this strategy's settings</button>
        </div>`;
      const ctrl = overlay.querySelector("#spmControls");
      if (ctrl) ctrl.onclick = () => { close(); openStrategyControlsModal(strategyId, strategyName, () => {}); };
    }).catch(e => {
      overlay.querySelector("#spmBody").innerHTML = `<p class="muted">Couldn't load: ${esc(e.message)}</p>`;
    });
  }

  // Any element carrying .pt-strategy-periods (with data-id/data-name)
  // opens the drill-down above. Wired in one place so every table, card,
  // and summary panel that lists a strategy gets the behaviour for free.
  function wireStrategyPeriodDrilldowns(root) {
    (root || document).querySelectorAll(".pt-strategy-periods").forEach(el => {
      el.onclick = (e) => {
        e.stopPropagation();
        openStrategyPeriodsModal(el.dataset.id, el.dataset.name || el.dataset.id);
      };
    });
  }

  // Advanced per-strategy controls (Master Task 2, Part 3): ON/OFF,
  // pause/resume, risk%/max-open-positions override, and a full stats
  // reset that archives (never deletes) the previous numbers.
  function openStrategyControlsModal(strategyId, strategyName, onDone) {
    const overlay = document.createElement("div");
    overlay.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:9999;display:flex;align-items:center;justify-content:center;";
    overlay.innerHTML = `
      <div style="background:var(--bg-elevated,#1a1f2b);color:inherit;border-radius:12px;padding:28px;max-width:480px;width:92%;box-shadow:0 20px 60px rgba(0,0,0,.4);max-height:85vh;overflow:auto;">
        <div class="section-title" style="margin-top:0;">Strategy Controls</div>
        <p style="margin:0 0 14px;"><b>${esc(strategyName)}</b></p>
        <div id="scmBody" class="muted">Loading...</div>
        <div class="btn-row" style="justify-content:flex-end;margin-top:16px;">
          <button class="btn-ghost" id="scmClose">Close</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    const close = () => overlay.remove();
    overlay.onclick = (e) => { if (e.target === overlay) close(); };
    document.getElementById("scmClose").onclick = close;

    async function load() {
      const [cfg, paused, history] = await Promise.all([
        apiGet(`/api/paper-trading/strategy-config/${strategyId}`),
        apiGet("/api/paper-trading/paused-strategies"),
        apiGet(`/api/paper-trading/strategy-config/${strategyId}/reset-history`).catch(() => ({ archives: [] })),
      ]);
      const pausedEntry = (paused.paused || []).find(p => p.strategy_id === strategyId);
      const body = document.getElementById("scmBody");
      body.innerHTML = `
        <div class="form-row" style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
          <label style="width:auto;margin:0;">Enabled (ON/OFF, manual override)</label>
          <input type="checkbox" id="scmEnabled" style="width:auto;" ${cfg.enabled ? "checked" : ""}>
        </div>
        <div class="form-row" style="margin-bottom:10px;">
          <label>Pause / Resume (new trades only -- open positions unaffected)</label>
          ${pausedEntry
            ? `<div class="pill pill-error" style="margin-bottom:6px;">Paused: ${esc(pausedEntry.reason || "-")}</div><button class="btn-ghost" id="scmResume">Resume</button>`
            : `<button class="btn-ghost" id="scmPause">Pause</button>`}
        </div>
        <div class="form-row"><label>Risk % Override (blank = use global default)</label>
          <input type="number" step="0.1" min="0" max="10" id="scmRiskPct" value="${cfg.risk_pct_override != null ? cfg.risk_pct_override : ""}" placeholder="global default">
        </div>
        <div class="form-row"><label>Max Open Positions Override (blank = use global default, 1-20)</label>
          <input type="number" step="1" min="1" max="20" id="scmMaxOpen" value="${cfg.max_open_trades_override != null ? cfg.max_open_trades_override : ""}" placeholder="global default">
        </div>
        <div class="btn-row" style="margin:6px 0 14px;">
          <button class="btn" id="scmSaveOverrides">Save Overrides</button>
          <span id="scmOverrideStatus" class="muted"></span>
        </div>
        <div class="form-row"><label>Balance / Stats Reset</label>
          <button class="btn-ghost" id="scmReset" style="border-color:var(--red,#c0392b);color:var(--red,#c0392b);">Reset This Strategy's Stats</button>
        </div>
        ${history.archives && history.archives.length ? `
        <div style="margin-top:14px;">
          <div class="muted" style="font-size:11px;margin-bottom:4px;">Reset history (archived, never deleted):</div>
          ${history.archives.map(a => `<div class="muted" style="font-size:11px;">${esc((a.archived_at||"").slice(0,19).replace("T"," "))} -- previous PnL ${a.previous_realized_pnl_total.toFixed(2)}, ${a.previous_closed_count} trades</div>`).join("")}
        </div>` : ""}
      `;

      document.getElementById("scmEnabled").onchange = async (e) => {
        await apiPost(`/api/paper-trading/strategy-config/${strategyId}`, {
          enabled: e.target.checked, priority: cfg.priority != null ? cfg.priority : 5,
          supported_coins: cfg.supported_coins || [], supported_market_types: cfg.supported_market_types || [],
        });
        appendLog(`Strategy ${strategyId} ${e.target.checked ? "activated" : "deactivated"} manually.`);
        if (onDone) onDone();
      };
      const pauseBtn = document.getElementById("scmPause");
      if (pauseBtn) pauseBtn.onclick = async () => {
        await apiPost(`/api/paper-trading/strategy-config/${strategyId}/pause`);
        appendLog(`Strategy ${strategyId} paused manually.`);
        load();
      };
      const resumeBtn = document.getElementById("scmResume");
      if (resumeBtn) resumeBtn.onclick = async () => {
        await apiPost(`/api/paper-trading/strategy-config/${strategyId}/resume`);
        appendLog(`Strategy ${strategyId} resumed manually.`);
        load();
      };
      document.getElementById("scmSaveOverrides").onclick = async () => {
        const status = document.getElementById("scmOverrideStatus");
        const riskVal = document.getElementById("scmRiskPct").value;
        const maxVal = document.getElementById("scmMaxOpen").value;
        status.textContent = "Saving...";
        try {
          await apiPost(`/api/paper-trading/strategy-config/${strategyId}/overrides`, {
            risk_pct_override: riskVal === "" ? null : parseFloat(riskVal),
            max_open_trades_override: maxVal === "" ? null : parseInt(maxVal, 10),
          });
          status.textContent = "Saved.";
          appendLog(`Strategy ${strategyId} risk overrides updated.`);
        } catch (e) {
          status.textContent = `Failed: ${e.message}`;
        }
      };
      document.getElementById("scmReset").onclick = async () => {
        const preview = await apiGet(`/api/paper-trading/strategy-config/${strategyId}/reset-stats/preview`);
        const msg = `Resetting this strategy's stats will do this:\n\n` +
          `- Balance goes from $${preview.current_balance.toFixed(2)} back to the starting balance.\n` +
          `- ${preview.current_closed_trades} closed trades (${preview.current_win_count} wins) will be ARCHIVED, not deleted -- viewable in this strategy's reset history.\n` +
          (preview.open_positions_left_running > 0
            ? `- ${preview.open_positions_left_running} open position(s) will KEEP RUNNING, not be closed.\n`
            : `- There are no open positions right now.\n`) +
          `\nConfirm?`;
        if (!confirm(msg)) return;
        await apiPost(`/api/paper-trading/strategy-config/${strategyId}/reset-stats`, { confirm: true });
        appendLog(`Strategy ${strategyId} stats reset (archived, not deleted).`);
        load();
        if (onDone) onDone();
      };
    }
    load();
  }

  async function renderStrategyLifecycle() {
    const en = getLang() === "en";
    const d = await apiGet("/api/strategy-lifecycle");
    content.innerHTML = `
      <div class="section-title">${en ? "Strategy Lifecycle" : "Strategy Lifecycle"}</div>
      <div class="metric-explainer">
        ${en
          ? `The whole picture for every active strategy in one table: its real backtest result, WHY it wins or loses (Part 1's computed analysis), how a stricter confirmation filter changes it (Part 2's optimizer), and a gated switch to move it into paper trading.`
          : `Har active strategy ki poori tasveer ek table mein: uska real backtest result, WHY jeet ya haar hoti hai (Part 1 ka computed analysis), stricter confirmation filter se kya farak padta hai (Part 2 ka optimizer), aur ek gated switch jo ise paper trading mein bhejta hai.`}
      </div>
      ${(d.part1_status || d.part2_status) ? `
      <div class="grid">
        ${d.part1_status ? cardClass(en ? "Why Win/Loss Analysis" : "Why Win/Loss Analysis", `${d.part1_status.done}/${d.part1_status.total}`, "positive") : ""}
        ${d.part2_status ? cardClass(en ? "Optimizer Variants Built" : "Optimizer Variants Built", `${d.part2_status.done}/${d.part2_status.total}`, d.part2_status.done === d.part2_status.total ? "positive" : "") : ""}
      </div>` : ""}
      <div class="table-wrap"><table>
        <thead><tr>
          <th>${en ? "Strategy" : "Strategy"}</th>
          <th>${en ? "Backtest PF" : "Backtest PF"}</th>
          <th>${en ? "Why Win/Loss" : "Why Win/Loss"}</th>
          <th>${en ? "Optimizer (Loose/Med/Strict)" : "Optimizer (Loose/Med/Strict)"}</th>
          <th></th>
        </tr></thead>
        <tbody>${d.rows.map((r, i) => `
          <tr>
            <td style="max-width:220px;">${esc(r.name)}${r.paper_config && r.paper_config.enabled ? ` <span class="pill pill-up" style="font-size:10px;">${en ? "Live in Paper" : "Paper Mein Live"}</span>` : ""}</td>
            <td>${lifecyclePfSpan(r.backtest.profit_factor)}</td>
            <td style="max-width:320px;">
              <span class="lc-why-text" id="lcWhy${i}" style="font-size:12.5px;display:inline-block;max-height:2.8em;overflow:hidden;">${esc(r.why_summary || (en ? "Not yet analyzed" : "Abhi analysis nahi hui"))}</span>
              ${r.why_summary ? `<div><button class="btn-ghost" style="font-size:11px;padding:2px 6px;" data-lc-expand="${i}">${en ? "Show more" : "Aur Dekhein"}</button></div>` : ""}
            </td>
            <td style="max-width:150px;">${lifecycleOptimizerCell(r, en)}</td>
            <td><button class="btn" style="font-size:12px;" data-lc-activate="${i}">${en ? "Move to paper trading" : "Paper Trading Mein Bhejein"}</button></td>
          </tr>
        `).join("")}</tbody>
      </table></div>
      <p class="muted" style="font-size:12px; margin-top:16px;">${en ? "Optimizer variants are archived drafts -- they never count toward the main strategy totals or roster." : "Optimizer variants archived drafts hain -- ye kabhi bhi main strategy totals ya roster mein shamil nahi hote."}</p>
    `;
    content.querySelectorAll("[data-lc-expand]").forEach(btn => {
      btn.onclick = () => {
        const i = btn.dataset.lcExpand;
        const el = document.getElementById(`lcWhy${i}`);
        el.style.maxHeight = el.style.maxHeight === "none" ? "2.8em" : "none";
        btn.textContent = el.style.maxHeight === "none" ? (en ? "Show less" : "Kam Dekhein") : (en ? "Show more" : "Aur Dekhein");
      };
    });
    content.querySelectorAll("[data-lc-activate]").forEach(btn => {
      btn.onclick = () => {
        const row = d.rows[Number(btn.dataset.lcActivate)];
        openPaperTradingConfirm(row, en, () => renderStrategyLifecycle());
      };
    });
  }

  // ------------------------------------------------------------ Cloud "Strategies" overview
  // Cloud-only page (see cloud_runtime/app.py's _CLOUD_NAV_PAGES) --
  // deliberately its own function/id, NOT a reuse of renderStrategies
  // (that one calls /api/backtesting/strategies and other routers the
  // lightweight cloud runner never mounts). Backed entirely by
  // /api/paper-trading/strategy-overview, which itself pulls only from
  // Paper Trading's own real history -- there is no backtest database in
  // this runner (see db_backend.py), so win rate/PnL are live-trading
  // numbers, not backtest ones.
  let strategyOverviewSort = "total_pnl";

  function strategyOverviewRrCell(row, en) {
    if (row.risk_reward == null) return `<span class="muted">${en ? "Not enough data yet" : "Abhi kaafi data nahi"}</span>`;
    return `1 : ${row.risk_reward.toFixed(2)}${row.risk_reward_is_fixed ? "" : ` <span class="muted" style="font-size:11px;">(${en ? "avg" : "avg"})</span>`}`;
  }

  function strategyOverviewSortValue(row, key) {
    if (key === "name") return (row.name || "").toLowerCase();
    if (key === "status") return row.in_paper_trading ? 1 : 0;
    if (key === "backtest_win_rate") return (row.backtest && row.backtest.win_rate) ?? -Infinity;
    const v = row[key];
    return v == null ? -Infinity : v;
  }

  // Master Task 3, Phase 0.7: dual-row Strategies table -- each strategy is
  // one card with two clearly-labeled sub-rows (Backtest expectation from
  // the local machine's own last completed batch vs real Paper Trading
  // history), so backtest promises and live reality sit side by side
  // instead of the CEO having to remember one number while looking at the
  // other page. Replaces the old single-row table (win rate/PnL/R:R only,
  // paper-trading numbers exclusively) that this cloud-only page used to
  // render -- same data source (/api/paper-trading/strategy-overview) plus
  // the new "backtest" field it now also returns.
  function strategyOverviewCard(s, en) {
    const bt = s.backtest;
    const statusPill = s.in_paper_trading
      ? `<span class="pill pill-up">${en ? "Active" : "Active"}</span>`
      : `<span class="pill pill-muted">${en ? "Not yet added" : "Shamil Nahi"}</span>`;
    return `
      <div class="card" data-strategy-card="${esc(s.strategy_id)}">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:10px;">
          <b style="font-size:13.5px;">${esc(s.name)}</b>
          ${statusPill}
        </div>
        <div class="muted" style="font-size:10.5px;text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px;">${en ? "Backtest (local)" : "Backtest (Local)"}</div>
        <div style="font-size:12.5px;display:flex;flex-wrap:wrap;gap:4px 14px;margin-bottom:10px;">
          ${bt
            ? `<span>${en ? "Win Rate" : "Win Rate"}: <b>${bt.win_rate != null ? bt.win_rate.toFixed(1) + "%" : "-"}</b></span>
               <span>R:R: <b>${bt.risk_reward != null ? "1:" + Number(bt.risk_reward).toFixed(2) : (s.risk_reward != null ? "1:" + s.risk_reward.toFixed(2) : "-")}</b></span>
               <span>${en ? "Profit Factor" : "Profit Factor"}: <b>${bt.profit_factor != null ? bt.profit_factor.toFixed(2) : "-"}</b></span>`
            : `<span class="muted">${en ? "No local backtest recorded yet for this strategy." : "Is strategy ka abhi tak koi local backtest record nahi."}</span>`}
        </div>
        <div class="muted" style="font-size:10.5px;text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px;">${en ? "Paper Trading (live)" : "Paper Trading (Live)"}</div>
        <div style="font-size:12.5px;display:flex;flex-wrap:wrap;gap:4px 14px;margin-bottom:10px;">
          <span>${en ? "Win Rate" : "Win Rate"}: <b>${s.closed_trades > 0 ? s.win_rate.toFixed(1) + "%" : "-"}</b></span>
          <span>${en ? "PnL" : "PnL"}: ${s.closed_trades > 0 ? pnlSpan(s.total_pnl) : "<b>$0.00</b>"}</span>
          <span>${en ? "Trades" : "Trades"}: <b>${s.closed_trades}</b></span>
        </div>
        ${s.in_paper_trading
          ? ""
          : s.can_activate
            ? `<button class="btn" style="font-size:12px;" data-activate="${esc(s.strategy_id)}">${en ? "Move to Paper Trading" : "Paper Trading Mein Bhejein"}</button>`
            : `<button class="btn" style="font-size:12px;" disabled title="${esc(s.activation_blocked_reason || "")}">${en ? "Move to Paper Trading" : "Paper Trading Mein Bhejein"}</button>
               <div class="muted" style="font-size:11px;">${esc(s.activation_blocked_reason || "")}</div>`}
      </div>`;
  }

  async function renderStrategyOverview() {
    const en = getLang() === "en";
    const myToken = activeRouteToken;
    const data = await apiGet("/api/paper-trading/strategy-overview");
    if (isStaleRoute(myToken)) return;
    const strategies = data.strategies || [];

    const SORT_OPTIONS = [
      { key: "total_pnl", label: en ? "Paper PnL" : "Paper PnL" },
      { key: "name", label: en ? "Name" : "Naam" },
      { key: "win_rate", label: en ? "Paper Win Rate" : "Paper Win Rate" },
      { key: "backtest_win_rate", label: en ? "Backtest Win Rate" : "Backtest Win Rate" },
      { key: "status", label: en ? "Status" : "Status" },
    ];

    function renderTable() {
      const sorted = [...strategies].sort((a, b) => {
        const av = strategyOverviewSortValue(a, strategyOverviewSort);
        const bv = strategyOverviewSortValue(b, strategyOverviewSort);
        if (av < bv) return 1;
        if (av > bv) return -1;
        return 0;
      });

      const cards = sorted.map(s => strategyOverviewCard(s, en)).join("");

      content.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:6px;">
          <div class="section-title" style="margin:0;">${en ? "Strategies" : "Strategies"}</div>
          <label style="font-size:12px;display:flex;align-items:center;gap:6px;">
            ${en ? "Sort by" : "Sort Karein"}:
            <select id="strategyOverviewSortSelect">
              ${SORT_OPTIONS.map(o => `<option value="${o.key}" ${strategyOverviewSort === o.key ? "selected" : ""}>${o.label}</option>`).join("")}
            </select>
          </label>
        </div>
        <p class="muted" style="font-size:12px;margin:0 0 14px;">${en
          ? "Every strategy currently in the system, one card each -- the top row is what the backtest predicted (from the local machine's own last completed batch), the bottom row is what Paper Trading has actually done since. A strategy not yet added shows $0.00 until it starts trading."
          : "System mein maujood har strategy, ek-ek card mein -- upar wali row backtest ne kya predict kiya (local machine ke aakhri complete batch se), neeche wali row Paper Trading ne asal mein kya kiya hai. Jo strategy abhi shamil nahi hui uska $0.00 dikhega jab tak trading shuru nahi hoti."}</p>
        <div class="grid">${cards || `<p class="muted">${en ? "No strategies saved yet." : "Abhi koi strategy save nahi hui."}</p>`}</div>`;

      document.getElementById("strategyOverviewSortSelect").onchange = (e) => {
        strategyOverviewSort = e.target.value;
        renderTable();
      };

      content.querySelectorAll("[data-activate]").forEach(btn => {
        btn.onclick = async () => {
          const sid = btn.dataset.activate;
          const row = strategies.find(s => s.strategy_id === sid);
          const confirmMsg = en
            ? `Move "${row.name}" into Paper Trading?\n\nThis switches it ON so it starts taking real (simulated) trades. Every other safety gate (Confluence, Signal Freshness, Drawdown Protection) still applies before any trade fires.`
            : `"${row.name}" ko Paper Trading mein bhejna hai?\n\nYe isko ON kar dega, jisse ye real (simulated) trades lena shuru kar degi. Baaki har safety gate (Confluence, Signal Freshness, Drawdown Protection) ab bhi lagu rahega, kisi bhi trade se pehle.`;
          if (!confirm(confirmMsg)) return;
          btn.disabled = true;
          try {
            await apiPost(`/api/paper-trading/strategy-config/${sid}`, {
              enabled: true,
              priority: row.paper_config.priority,
              supported_coins: row.paper_config.supported_coins,
              supported_market_types: row.paper_config.supported_market_types,
            });
            showToast({ title: en ? "Activated" : "Activate ho gaya", body: `${row.name} ${en ? "is now active in Paper Trading." : "ab Paper Trading mein active hai."}` });
            renderStrategyOverview();
          } catch (e) {
            btn.disabled = false;
            showToast({ title: en ? "Failed" : "Nakam", body: e.message, isError: true });
          }
        };
      });
    }

    renderTable();
  }

  // "All / Profitable / Losing" filter on Compare's main table -- client-
  // side only (the full list is already fetched), remembered per-tab-switch
  // like the Project Status period tabs use the exact same pill pattern.
  let compareFilter = "all";

  // Grand Feature Expansion, Phase 4 Feature 5: Compare 2 Strategies View --
  // a focused side-by-side of exactly two strategies, using data already
  // computed by the existing per-strategy profile endpoint (health score,
  // Sharpe/Sortino, Value at Risk, MAE/MFE, streak) rather than the Main
  // Strategies table's PF-only row. Purely additive: the all-strategies
  // table above is completely untouched.
  let compare2StrategyA = null, compare2StrategyB = null;

  // Grand Feature Expansion, Phase 4 Feature 6: Strategy Comparison
  // Snapshot -- a shareable export of the Compare 2 Strategies result.
  // Deliberately dependency-free (no image/chart library exists anywhere
  // in this codebase, per the same reasoning Weekly Report's text
  // sparkline used over a real chart image): "Copy as Text" builds a
  // plain-text version of the exact same rows shown on screen using the
  // browser's built-in Clipboard API, pasteable into Telegram/WhatsApp/
  // notes -- no new dependency, no CDN, nothing to break on a cloud deploy.
  function compare2Rows(en, profileA, profileB) {
    const fNum = (v, suffix = "") => v == null ? "-" : `${v.toFixed(2)}${suffix}`;
    const fInt = (v) => v == null ? "-" : fmtNum(v);
    const fStreak = (s) => !s || !s.count ? "-" : `${s.count} ${s.type === "win" ? (en ? "wins" : "jeet") : (en ? "losses" : "haar")}`;
    const yn = (v) => v ? (en ? "Yes" : "Haan") : (en ? "No" : "Nahi");
    return [
      [en ? "Health Score" : "Health Score", fInt(profileA.health_score && profileA.health_score.health_score), fInt(profileB.health_score && profileB.health_score.health_score)],
      [en ? "Confidence Score" : "Confidence Score", fNum(profileA.confidence_score), fNum(profileB.confidence_score)],
      [en ? "Current Streak" : "Current Streak", fStreak(profileA.streak), fStreak(profileB.streak)],
      ["Sharpe Ratio", fNum(profileA.risk_metrics && profileA.risk_metrics.sharpe_ratio), fNum(profileB.risk_metrics && profileB.risk_metrics.sharpe_ratio)],
      ["Sortino Ratio", fNum(profileA.risk_metrics && profileA.risk_metrics.sortino_ratio), fNum(profileB.risk_metrics && profileB.risk_metrics.sortino_ratio)],
      [en ? "Max Drawdown" : "Max Drawdown", fNum(profileA.risk_metrics && profileA.risk_metrics.max_drawdown_pct, "%"), fNum(profileB.risk_metrics && profileB.risk_metrics.max_drawdown_pct, "%")],
      [en ? "Value at Risk (95%)" : "Value at Risk (95%)", fNum(profileA.value_at_risk && profileA.value_at_risk.var_amount), fNum(profileB.value_at_risk && profileB.value_at_risk.var_amount)],
      [en ? "Avg. Winner MFE" : "Avg. Winner MFE", fNum(profileA.mae_mfe && profileA.mae_mfe.winners && profileA.mae_mfe.winners.avg_mfe), fNum(profileB.mae_mfe && profileB.mae_mfe.winners && profileB.mae_mfe.winners.avg_mfe)],
      [en ? "Avg. Loser MAE" : "Avg. Loser MAE", fNum(profileA.mae_mfe && profileA.mae_mfe.losers && profileA.mae_mfe.losers.avg_mae), fNum(profileB.mae_mfe && profileB.mae_mfe.losers && profileB.mae_mfe.losers.avg_mae)],
      [en ? "Aging Trend" : "Aging Trend", (profileA.aging && profileA.aging.trend) || "-", (profileB.aging && profileB.aging.trend) || "-"],
      [en ? "Open Positions" : "Open Positions", fInt(profileA.open_position_count), fInt(profileB.open_position_count)],
      [en ? "Currently Paused" : "Currently Paused", yn(profileA.paused), yn(profileB.paused)],
      [en ? "Archived" : "Archived", yn(profileA.archived), yn(profileB.archived)],
    ];
  }

  function compare2Html(en, profileA, profileB) {
    const rows = compare2Rows(en, profileA, profileB);
    return `
      <div class="table-wrap"><table>
        <thead><tr>
          <th>${en ? "Metric" : "Metric"}</th>
          <th>${esc(profileA.name)}</th>
          <th>${esc(profileB.name)}</th>
        </tr></thead>
        <tbody>
          ${rows.map(([label, av, bv]) => `<tr><td class="stat-secondary">${esc(label)}</td><td>${esc(av)}</td><td>${esc(bv)}</td></tr>`).join("")}
        </tbody>
      </table></div>
      <div class="btn-row" style="margin-top:8px;">
        <button class="btn-ghost" id="btnCompare2Snapshot">${en ? "Copy as Text" : "Text Ke Taur Par Copy Karein"}</button>
      </div>
    `;
  }

  function compare2SnapshotText(en, profileA, profileB) {
    const rows = compare2Rows(en, profileA, profileB);
    const lines = [
      `${en ? "Strategy Comparison" : "Strategy Comparison"}: ${profileA.name} vs ${profileB.name}`,
      ...rows.map(([label, av, bv]) => `${label}: ${av}  |  ${bv}`),
    ];
    return lines.join("\n");
  }

  function compareRowsHtml(rows, en) {
    return rows.map(r => `
      <tr class="${r.profitable ? "row-positive" : ""} compare-row-clickable" data-strategy-row="${esc(r.name)}" data-strategy-id="${esc(r.id)}">
        <td>${esc(r.name)}${r.protected ? ` <span class="pill pill-muted">${en ? "Protected" : "Protected"}</span>` : ""}</td>
        <td><span class="stat-hero ${r.profitable ? "positive" : "negative"}">${r.profit_factor != null ? r.profit_factor.toFixed(4) : "-"}</span></td>
        <td>${r.profitable
          ? `<span class="pill pill-up">${en ? "Profitable" : "Munafa"}</span>`
          : `<span class="pill pill-down">${en ? "Losing" : "Nuqsaan"}</span>`}</td>
        <td class="stat-secondary">${r.original ? r.original.pf.toFixed(4) : "-"}</td>
        <td class="stat-secondary">${fmtNum(r.trades)}</td>
        <td class="stat-secondary">${r.win_rate.toFixed(2)}%</td>
        <td class="stat-secondary">${pnlSpan(r.net_pnl)}</td>
        <td class="stat-secondary">${r.worst_drawdown_pct != null ? r.worst_drawdown_pct.toFixed(2) + "%" : "-"}</td>
      </tr>
      ${r.tuning_change ? `<tr><td colspan="8" class="muted" style="font-size:12px;">
        ${en ? "Tuning change" : "Tuning change"}: ${esc(r.tuning_change)}${r.next_idea ? ` -- ${esc(r.next_idea)}` : ""}
      </td></tr>` : ""}
    `).join("");
  }

  function wireCompareRowClicks(root) {
    // Compare -> Strategy Profile (the reverse of the Profile page's own
    // "View on Compare page" link) -- reuses the exact same
    // pendingProfileStrategyId hand-off the Strategies page's Balance
    // History/Coin-Wise deep-links already use, so opening a Profile from
    // here behaves identically to opening it from anywhere else.
    root.querySelectorAll("tr[data-strategy-id]").forEach(row => {
      row.style.cursor = "pointer";
      row.title = getLang() === "en" ? "Open this strategy's profile" : "Is strategy ka profile kholein";
      row.onclick = () => {
        pendingProfileStrategyId = row.dataset.strategyId;
        location.hash = "#strategies";
      };
    });
  }

  async function renderCompare() {
    const en = getLang() === "en";
    const [d, dtp, familyTree] = await Promise.all([
      apiGet("/api/compare-strategies"),
      apiGet("/api/compare-strategies/dual-tp").catch(() => null),
      apiGet("/api/concepts/family-tree").catch(() => ({ families: [], ungrouped_strategies: [] })),
    ]);
    const losingCount = d.total_strategies - d.profitable_count;
    const best = d.strategies.find(r => r.profitable) || d.strategies[0] || null;

    content.innerHTML = `
      <div class="section-title">${en ? "Compare -- All Strategies Side by Side" : "Compare -- Saari Strategies Ek Saath"}</div>
      <div class="metric-explainer">
        ${en
          ? `<b>What is Profit Factor (PF)?</b> Total money won &divide; total money lost, across every trade. Above <b>1.0</b> means the strategy made more than it lost overall (profitable); below 1.0 means it lost more than it made (losing). It's the single most important number below -- shown larger and bolder than everything else in each row on purpose.`
          : `<b>Profit Factor (PF) kya hai?</b> Kul jeeta hua paisa &divide; kul haara hua paisa, sab trades milaakar. <b>1.0</b> se upar matlab strategy ne overall zyada kamaya (munafa mein); 1.0 se neeche matlab zyada nuqsaan hua. Yeh sabse zaroori number hai -- isliye har row mein sabse bada aur bold dikhaya gaya hai.`}
      </div>
      <div class="grid">
        ${card(en ? "Total Strategies" : "Kul Strategies", fmtNum(d.total_strategies))}
        ${cardClass(en ? "Genuinely Profitable" : "Genuinely Profitable", fmtNum(d.profitable_count), "positive")}
        ${cardClass(en ? "Losing" : "Nuqsaan Mein", fmtNum(losingCount), losingCount > 0 ? "negative" : "")}
        ${best ? cardClass(en ? "Best Performer" : "Sabse Behtareen", `${best.profit_factor != null ? best.profit_factor.toFixed(2) : "-"} PF`, best.profitable ? "positive" : "negative", esc(best.name)) : ""}
      </div>

      <div class="section-card">
        <div class="section-title">${en ? "Main Strategies" : "Main Strategies"}</div>
        <p class="muted" style="font-size:12.5px; margin:-4px 0 12px;">
          ${en
            ? `Every active strategy's real backtest result, best performer first. Click any row to open that strategy's full profile.`
            : `Har active strategy ka asal backtest result, sabse behtareen sab se upar. Kisi bhi row pe click karke us strategy ki poori profile khulti hai.`}
        </p>
        <div class="period-tabs">
          <button class="period-tab ${compareFilter === "all" ? "active" : ""}" data-compare-filter="all">${en ? "All" : "Sab"} (${d.strategies.length})</button>
          <button class="period-tab ${compareFilter === "profitable" ? "active" : ""}" data-compare-filter="profitable">${en ? "Profitable" : "Munafa"} (${d.profitable_count})</button>
          <button class="period-tab ${compareFilter === "losing" ? "active" : ""}" data-compare-filter="losing">${en ? "Losing" : "Nuqsaan"} (${losingCount})</button>
        </div>
        <div class="table-wrap"><table>
          <thead><tr>
            <th>${en ? "Strategy" : "Strategy"}</th>
            <th>${en ? "Profit Factor" : "Profit Factor"}</th>
            <th>${en ? "Verdict" : "Verdict"}</th>
            <th>${en ? "Original PF" : "Pehle PF"}</th>
            <th>${en ? "Trades" : "Trades"}</th>
            <th>${en ? "Win Rate" : "Win Rate"}</th>
            <th>${en ? "Net PnL" : "Net PnL"}</th>
            <th>${en ? "Worst Drawdown" : "Worst Drawdown"}</th>
          </tr></thead>
          <tbody id="compareMainRows">${compareRowsHtml(d.strategies, en)}</tbody>
        </table></div>
      </div>

      <div class="section-card">
        <div class="section-title">${en ? "Compare 2 Strategies" : "2 Strategies Compare Karein"}</div>
        <p class="muted" style="font-size:12.5px; margin:-4px 0 12px;">
          ${en
            ? `Pick any two strategies for a focused, side-by-side look at health score, risk metrics, and more -- deeper than the Profit Factor row above.`
            : `Koi bhi 2 strategies chunein aur health score, risk metrics waghera ka side-by-side moazna dekhein -- upar ki Profit Factor row se zyada gehra.`}
        </p>
        <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
          <select id="compare2SelectA" style="max-width:220px;">
            <option value="">${en ? "Strategy A..." : "Strategy A..."}</option>
            ${d.strategies.map(r => `<option value="${esc(r.id)}">${esc(r.name)}</option>`).join("")}
          </select>
          <select id="compare2SelectB" style="max-width:220px;">
            <option value="">${en ? "Strategy B..." : "Strategy B..."}</option>
            ${d.strategies.map(r => `<option value="${esc(r.id)}">${esc(r.name)}</option>`).join("")}
          </select>
          <button id="btnCompare2" class="btn-ghost">${en ? "Compare" : "Compare Karein"}</button>
        </div>
        <div id="compare2Result" style="margin-top:12px;"></div>
      </div>

      ${dtp ? `
      <div class="section-card compare-archived-section">
        <div class="section-title">
          ${en ? "Take-Profit Comparison" : "Take-Profit Comparison"}
          <span class="pill pill-muted" style="font-size:11px; font-weight:600; margin-left:8px;">${en ? "Draft variants -- not in totals above" : "Draft variants -- upar ke totals mein shamil nahi"}</span>
        </div>
        <p class="muted" style="font-size:12.5px; margin:-4px 0 12px;">
          ${en
            ? `Original vs. Fixed 1:2 -- every strategy's normal take-profit rule, re-run with ONLY the take-profit swapped to a flat 1:2 risk-reward (everything else identical). These are archived draft comparisons, kept separate from the Main Strategies totals above. ${dtp.completed} of ${dtp.total} finished so far; the rest fill in as their batch completes.`
            : `Original vs. Fixed 1:2 -- har strategy ka apna take-profit rule, sirf take-profit ko flat 1:2 se badal kar dobara chalaya gaya (baaki sab wahi hai). Yeh archived draft comparisons hain, upar ke Main Strategies totals se alag rakhi gayi hain. Abhi tak ${dtp.completed} mein se ${dtp.total} mukammal hue hain.`}
        </p>
        <div class="table-wrap"><table>
          <thead><tr>
            <th>${en ? "Strategy" : "Strategy"}</th>
            <th>${en ? "Original TP" : "Original TP"}</th>
            <th>${en ? "Original PF" : "Original PF"}</th>
            <th>1:2 TP PF</th>
            <th></th>
            <th>${en ? "Original Trades" : "Original Trades"}</th>
            <th>1:2 TP Trades</th>
            <th>${en ? "Original Net PnL" : "Original Net PnL"}</th>
            <th>1:2 TP Net PnL</th>
          </tr></thead>
          <tbody>${dtp.strategies.map(r => `
            <tr>
              <td>${esc(r.name)}</td>
              <td class="stat-secondary">${esc(r.original_tp_label)}</td>
              <td><span class="stat-hero">${r.original && r.original.profit_factor != null ? r.original.profit_factor.toFixed(4) : "-"}</span></td>
              <td><span class="stat-hero ${r.verdict === "better" ? "positive" : r.verdict === "worse" ? "negative" : ""}">${r.variant && r.variant.profit_factor != null ? r.variant.profit_factor.toFixed(4) : `<span class="muted" style="font-size:12.5px;font-weight:400;">${esc(r.variant_status)}</span>`}</span></td>
              <td>${dualTpVerdictPill(r.verdict, en)}</td>
              <td class="stat-secondary">${r.original ? fmtNum(r.original.trades) : "-"}</td>
              <td class="stat-secondary">${r.variant ? fmtNum(r.variant.trades) : "-"}</td>
              <td class="stat-secondary">${r.original ? pnlSpan(r.original.net_pnl) : "-"}</td>
              <td class="stat-secondary">${r.variant ? pnlSpan(r.variant.net_pnl) : "-"}</td>
            </tr>
          `).join("")}</tbody>
        </table></div>
      </div>
      ` : ""}

      ${familyTree.families.length ? `
      <div class="section-card">
        <div class="section-title">${en ? "Strategy Family Tree" : "Strategy Family Tree"} ${helpIcon("strategy_family_tree")}</div>
        <p class="muted" style="font-size:12.5px; margin:-4px 0 12px;">${en ? "Strategies grouped by which core trading concept they share." : "Strategies apne shared trading concept ke hisaab se grouped."}</p>
        ${familyTree.families.map(f => `
          <div class="card" style="margin-bottom:8px;">
            <div class="label">${esc(f.concept)} <span class="pill pill-muted">${f.member_count}</span></div>
            <div style="font-size:12px;margin-top:4px;">${f.strategies.map(esc).join(", ")}</div>
          </div>`).join("")}
        ${familyTree.ungrouped_strategies.length ? `
        <div class="muted" style="font-size:12px;margin-top:8px;">${en ? "Not yet part of any family" : "Abhi tak kisi family ka hissa nahi"} (${familyTree.ungrouped_strategies.length}): ${familyTree.ungrouped_strategies.map(esc).join(", ")}</div>` : ""}
      </div>
      ` : ""}

      <p class="muted" style="font-size:12px; margin-top:16px;">${en ? "Generated" : "Bana"}: ${esc(d.generated_at)}</p>
    `;

    wireCompareRowClicks(content);
    content.querySelectorAll("[data-compare-filter]").forEach(btn => {
      btn.onclick = () => {
        compareFilter = btn.dataset.compareFilter;
        content.querySelectorAll("[data-compare-filter]").forEach(b => b.classList.toggle("active", b === btn));
        const filtered = compareFilter === "all" ? d.strategies
          : compareFilter === "profitable" ? d.strategies.filter(r => r.profitable)
          : d.strategies.filter(r => !r.profitable);
        const tbody = document.getElementById("compareMainRows");
        tbody.innerHTML = compareRowsHtml(filtered, en);
        wireCompareRowClicks(tbody);
      };
    });

    const compare2SelA = document.getElementById("compare2SelectA");
    const compare2SelB = document.getElementById("compare2SelectB");
    if (compare2StrategyA) compare2SelA.value = compare2StrategyA;
    if (compare2StrategyB) compare2SelB.value = compare2StrategyB;
    document.getElementById("btnCompare2").onclick = async () => {
      compare2StrategyA = compare2SelA.value;
      compare2StrategyB = compare2SelB.value;
      const resultEl = document.getElementById("compare2Result");
      if (!compare2StrategyA || !compare2StrategyB) {
        resultEl.innerHTML = `<p class="muted" style="font-size:12.5px;">${en ? "Pick both strategies first." : "Pehle dono strategies chunein."}</p>`;
        return;
      }
      if (compare2StrategyA === compare2StrategyB) {
        resultEl.innerHTML = `<p class="muted" style="font-size:12.5px;">${en ? "Pick two different strategies." : "Do alag strategies chunein."}</p>`;
        return;
      }
      resultEl.innerHTML = `<p class="muted" style="font-size:12.5px;">${en ? "Loading..." : "Load ho raha hai..."}</p>`;
      try {
        const [profileA, profileB] = await Promise.all([
          apiGet(`/api/paper-trading/strategy-profile/${compare2StrategyA}`),
          apiGet(`/api/paper-trading/strategy-profile/${compare2StrategyB}`),
        ]);
        resultEl.innerHTML = compare2Html(en, profileA, profileB);
        document.getElementById("btnCompare2Snapshot").onclick = async () => {
          const text = compare2SnapshotText(en, profileA, profileB);
          try {
            await navigator.clipboard.writeText(text);
            showToast({ title: en ? "Copied" : "Copy Ho Gaya", body: en ? "Comparison copied -- paste it anywhere." : "Comparison copy ho gaya -- kahin bhi paste karein." });
          } catch (e) {
            showToast({ title: en ? "Could not copy" : "Copy Nahi Ho Saka", body: en ? "Your browser blocked clipboard access." : "Browser ne clipboard access block kar diya.", isError: true });
          }
        };
      } catch (e) {
        resultEl.innerHTML = `<p class="muted" style="font-size:12.5px;">${en ? "Could not load one of these strategies." : "In mein se ek strategy load nahi ho saki."}</p>`;
      }
    };

    // Arrived here via a strategy's own Profile page's "View on Compare"
    // link -- scroll to and briefly flash that exact row so the CEO doesn't
    // have to hunt for it in a long table. One-shot: cleared immediately
    // so a plain page revisit/refresh never re-triggers it.
    const highlightName = sessionStorage.getItem("compareHighlightStrategy");
    if (highlightName) {
      sessionStorage.removeItem("compareHighlightStrategy");
      const row = content.querySelector(`tr[data-strategy-row="${CSS.escape(highlightName)}"]`);
      if (row) {
        row.scrollIntoView({ behavior: "smooth", block: "center" });
        row.classList.add("row-flash");
      }
    }
  }

  // -------------------------------------------------------------- Live Logs
  // Read-only, three-tier view over the existing job_manager + activity_log
  // -- no new tracking mechanism, just presentation. Auto-refreshes while
  // this page is open so "Running Now" stays current without a manual reload.
  function fmtElapsed(seconds) {
    if (seconds == null) return "-";
    const s = Math.floor(seconds);
    if (s < 60) return `${s}s`;
    if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
    return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
  }

  async function renderLiveLogs() {
    const en = getLang() === "en";
    async function load() {
      const [d, auditRes, changedRes] = await Promise.all([
        apiGet("/api/live-logs"),
        apiGet("/api/audit-trail?limit=30").catch(() => ({ audit_trail: [], total_count: 0 })),
        apiGet("/api/what-changed?period=today").catch(() => ({ total_events: 0, summary_lines: [] })),
      ]);
      content.innerHTML = `
        <div class="section-title">${en ? "Live Logs" : "Live Logs"}</div>

        <div class="section-title" style="font-size:13px;">${en ? "What Changed Today" : "Aaj Kya Badla"} ${helpIcon("what_changed_today")}</div>
        <div class="card">
          ${changedRes.total_events === 0
            ? `<p class="muted" style="margin:0;">${en ? "Nothing has changed yet today." : "Aaj tak kuch nahi badla."}</p>`
            : `<p class="muted" style="font-size:12px;margin-top:0;">${en ? `${changedRes.total_events} events recorded today (from the permanent Audit Trail).` : `Aaj ${changedRes.total_events} events record hue (permanent Audit Trail se).`}</p>
               <ul style="margin:0;padding-left:18px;">${changedRes.summary_lines.map(line => `<li>${esc(line)}</li>`).join("")}</ul>`}
        </div>

        <div class="section-title" style="font-size:13px;">${en ? "Running Now" : "Abhi Chal Raha Hai"}</div>
        ${d.running_now.length ? `<div class="grid">${d.running_now.map(j => `
          <div class="card">
            <div class="label">${esc(j.kind)} -- ${esc(j.id)}</div>
            <div class="value" style="font-size:15px;">${esc(j.stage)}${j.progress_pct != null ? ` (${j.progress_pct}%)` : ""}</div>
            <div class="muted" style="font-size:12px;">${en ? "Elapsed" : "Guzra waqt"}: ${fmtElapsed(j.elapsed_seconds)}</div>
            ${j.stalled ? `<div class="pill pill-down" style="margin-top:6px;">${en ? "Possibly stalled -- no update in a long time" : "Shayad ruk gaya hai -- lambe waqt se update nahi"}</div>` : ""}
          </div>
        `).join("")}</div>` : `<p class="muted">${en ? "Nothing running right now." : "Abhi kuch nahi chal raha."}</p>`}

        <div class="section-title" style="font-size:13px;">${en ? "Queued" : "Queue Mein"}</div>
        ${d.queued.length ? `<div class="grid">${d.queued.map(j => `<div class="card">${esc(j.kind)} -- ${esc(j.id)}</div>`).join("")}</div>`
          : `<p class="muted">${en ? "Nothing queued -- backtests run one at a time, so there's no explicit queue today." : "Kuch queue mein nahi -- backtests ek waqt mein ek hi chalti hain."}</p>`}

        <div class="section-title" style="font-size:13px;">${en ? "Recently Completed" : "Abhi Abhi Mukammal Hua"}</div>
        <div class="table-wrap"><table>
          <thead><tr><th>${en ? "Kind" : "Kism"}</th><th>${en ? "Status" : "Status"}</th><th>${en ? "Started" : "Shuru"}</th><th>${en ? "Finished" : "Khatam"}</th><th>${en ? "Outcome" : "Nateeja"}</th></tr></thead>
          <tbody>${d.recently_completed.map(j => `
            <tr>
              <td>${esc(j.kind)}</td>
              <td><span class="pill ${j.status === "completed" ? "pill-up" : j.status === "error" ? "pill-down" : "pill-muted"}">${esc(j.status)}</span></td>
              <td>${esc((j.started_at || "").replace("T", " ").slice(0, 19))}</td>
              <td>${esc((j.finished_at || "").replace("T", " ").slice(0, 19))}</td>
              <td>${esc(j.error || j.outcome || "-")}</td>
            </tr>
          `).join("") || `<tr><td colspan="5">${en ? "Nothing yet." : "Abhi kuch nahi."}</td></tr>`}</tbody>
        </table></div>

        <div class="section-title" style="font-size:13px;">${en ? "Recent Activity" : "Haal Ki Sargarmi"}</div>
        <div class="table-wrap"><table>
          <thead><tr><th>${en ? "Entity" : "Entity"}</th><th>${en ? "Action" : "Action"}</th><th>${en ? "Message" : "Message"}</th><th>${en ? "When" : "Kab"}</th></tr></thead>
          <tbody>${d.recent_activity.map(a => `
            <tr><td>${esc(a.entity)}</td><td>${esc(a.action)}</td><td>${esc(a.message)}</td><td>${esc((a.created_at || "").replace("T", " ").slice(0, 19))}</td></tr>
          `).join("") || `<tr><td colspan="4">${en ? "No activity logged yet." : "Abhi koi sargarmi nahi."}</td></tr>`}</tbody>
        </table></div>

        <div class="section-title" style="font-size:13px;">${en ? "Audit Trail (Permanent Record)" : "Audit Trail (Mustaqil Record)"} <span class="muted">(${fmtNum(auditRes.total_count)} ${en ? "total events, never deleted" : "kul events, kabhi delete nahi hote"})</span></div>
        <div class="table-wrap"><table>
          <thead><tr><th>${en ? "Entity" : "Entity"}</th><th>${en ? "Action" : "Action"}</th><th>${en ? "Message" : "Message"}</th><th>${en ? "When" : "Kab"}</th></tr></thead>
          <tbody>${(auditRes.audit_trail || []).map(a => `
            <tr><td>${esc(a.entity)}</td><td>${esc(a.action)}</td><td>${esc(a.message)}</td><td>${esc((a.created_at || "").replace("T", " ").slice(0, 19))}</td></tr>
          `).join("") || `<tr><td colspan="4">${en ? "No audit events yet." : "Abhi koi audit event nahi."}</td></tr>`}</tbody>
        </table></div>
      `;
    }
    await load();
    autoRefresh(load, 8);
  }

  // -------------------------------------------------------------- Incidents
  // Grand Feature Expansion, Phase 1 Feature 4: a structured record for
  // problem -> detection -> root cause -> fix -> test -> resolution.
  // Backed by /api/incidents (data_engine/storage.py's incidents table).
  const INCIDENT_SEVERITIES = ["low", "medium", "high", "critical"];
  const INCIDENT_STATUSES = ["open", "root_cause_found", "fix_in_progress", "fixed", "resolved"];

  async function renderIncidents() {
    const myToken = activeRouteToken;
    let statusFilter = "";
    const render = async () => {
      const res = await apiGet(`/api/incidents?limit=100${statusFilter ? `&status=${statusFilter}` : ""}`);
      if (isStaleRoute(myToken)) return;
      const incidents = res.incidents || [];
      content.innerHTML = `
        <div class="section-title">Incident Management</div>
        <p class="muted">Track a problem from the moment it's noticed through root cause, fix, test, and resolution -- nothing here is ever deleted.</p>

        <div class="card">
          <div class="section-title" style="font-size:13px;">Report a New Incident</div>
          <div class="btn-row">
            <input id="incTitle" placeholder="Short title" style="flex:2;">
            <select id="incSeverity">${INCIDENT_SEVERITIES.map(s => `<option value="${s}" ${s === "medium" ? "selected" : ""}>${s}</option>`).join("")}</select>
          </div>
          <textarea id="incProblem" placeholder="What happened? Be specific." style="width:100%;margin-top:8px;min-height:60px;"></textarea>
          <div class="btn-row" style="margin-top:8px;">
            <input id="incDetectedBy" placeholder="Detected by (optional)" style="flex:1;">
            <button class="btn" id="incCreateBtn">Report Incident</button>
          </div>
          <span id="incCreateStatus" class="muted"></span>
        </div>

        <div class="section-title" style="font-size:13px;">Filter</div>
        <div class="btn-row">
          <button class="btn-ghost ${!statusFilter ? "active" : ""}" data-status="">All</button>
          ${INCIDENT_STATUSES.map(s => `<button class="btn-ghost ${statusFilter === s ? "active" : ""}" data-status="${s}">${s.replace(/_/g, " ")}</button>`).join("")}
        </div>

        <div class="table-wrap"><table>
          <thead><tr><th>Title</th><th>Severity</th><th>Status</th><th>Detected</th><th>Root Cause</th><th>Fix</th><th>Actions</th></tr></thead>
          <tbody>${incidents.map(inc => `
            <tr>
              <td>${esc(inc.title)}</td>
              <td><span class="pill ${inc.severity === "critical" || inc.severity === "high" ? "pill-down" : "pill-muted"}">${esc(inc.severity)}</span></td>
              <td><span class="pill ${inc.status === "resolved" ? "pill-up" : "pill-muted"}">${esc(inc.status.replace(/_/g, " "))}</span></td>
              <td style="font-size:12px;">${esc((inc.detected_at || "").slice(0, 19))}</td>
              <td style="font-size:12px;max-width:180px;">${esc(inc.root_cause || "-")}</td>
              <td style="font-size:12px;max-width:180px;">${esc(inc.fix_description || "-")}</td>
              <td>${inc.status !== "resolved" ? `<button class="btn-ghost inc-edit" data-id="${inc.id}" style="font-size:12px;">Update</button>` : ""}</td>
            </tr>
          `).join("") || `<tr><td colspan="7">No incidents recorded${statusFilter ? ` with status "${statusFilter}"` : ""}.</td></tr>`}</tbody>
        </table></div>
      `;

      content.querySelectorAll("[data-status]").forEach(b => b.onclick = () => { statusFilter = b.dataset.status; render(); });

      document.getElementById("incCreateBtn").onclick = async () => {
        const title = document.getElementById("incTitle").value.trim();
        const problem = document.getElementById("incProblem").value.trim();
        const statusEl = document.getElementById("incCreateStatus");
        if (!title || !problem) { statusEl.textContent = "Title and problem description are required."; return; }
        await apiPost("/api/incidents", {
          title, problem,
          detected_by: document.getElementById("incDetectedBy").value.trim() || null,
          severity: document.getElementById("incSeverity").value,
        });
        statusEl.textContent = "Reported.";
        render();
      };

      content.querySelectorAll(".inc-edit").forEach(b => b.onclick = () => {
        const inc = incidents.find(i => i.id === b.dataset.id);
        const rootCause = prompt("Root cause (leave blank to skip):", inc.root_cause || "");
        const fixDescription = prompt("Fix description (leave blank to skip):", inc.fix_description || "");
        const testDescription = prompt("How was the fix tested/verified? (leave blank to skip):", inc.test_description || "");
        const newStatus = prompt(`Status (one of: ${INCIDENT_STATUSES.join(", ")}):`, inc.status);
        const fields = {};
        if (rootCause) fields.root_cause = rootCause;
        if (fixDescription) fields.fix_description = fixDescription;
        if (testDescription) fields.test_description = testDescription;
        const wantsResolve = newStatus === "resolved";
        if (newStatus && INCIDENT_STATUSES.includes(newStatus) && !wantsResolve) fields.status = newStatus;
        (async () => {
          if (Object.keys(fields).length > 0) await apiPost(`/api/incidents/${inc.id}/update`, fields);
          if (wantsResolve) await apiPost(`/api/incidents/${inc.id}/resolve`, {});
          render();
        })();
      });
    };
    await render();
  }

  // ---------------------------------------------------------- Project Status
  const PS_PERIOD_TABS = [
    ["today", "Today"], ["yesterday", "Yesterday"], ["week", "This Week"],
    ["month", "This Month"], ["all", "All-Time"],
  ];

  async function renderProjectStatus() {
    const en = getLang() === "en";

    async function loadQuickNotes() {
      const qn = await apiGet("/api/quick-notes");
      const list = document.getElementById("psQuickNotesList");
      if (!list) return;
      list.innerHTML = qn.notes.map(n => `
        <div class="card" style="margin-bottom:6px;display:flex;justify-content:space-between;gap:8px;align-items:flex-start;">
          <div>
            <div style="white-space:pre-wrap;">${esc(n.content)}</div>
            <div class="muted" style="font-size:11px;margin-top:4px;">${esc((n.created_at || "").replace("T", " ").slice(0, 19))}</div>
          </div>
          <button class="btn-ghost quick-note-delete" data-id="${n.id}">${en ? "Delete" : "Hataayein"}</button>
        </div>
      `).join("") || `<p class="muted">${en ? "No quick notes yet." : "Abhi koi quick note nahi."}</p>`;
      list.querySelectorAll(".quick-note-delete").forEach(btn => {
        btn.onclick = async () => {
          await apiDelete(`/api/quick-notes/${btn.dataset.id}`);
          await loadQuickNotes();
        };
      });
    }

    async function loadFeedback() {
      const fb = await apiGet("/api/feedback");
      const list = document.getElementById("psFeedbackList");
      if (!list) return;
      list.innerHTML = fb.feedback.map(f => `
        <div class="card" style="margin-bottom:8px;">
          <div><span class="pill pill-muted">${esc(f.type)}</span> <span class="pill ${f.status === "addressed" ? "pill-up" : "pill-pending"}">${esc(f.status)}</span></div>
          <div style="margin-top:6px;">${esc(f.text)}</div>
          <div class="muted" style="font-size:11px;margin-top:4px;">${esc((f.created_at || "").replace("T", " ").slice(0, 19))}</div>
        </div>
      `).join("") || `<p class="muted">${en ? "No notes yet." : "Abhi koi note nahi."}</p>`;
    }

    async function load(period) {
      const [d, handoff] = await Promise.all([
        apiGet(`/api/project-status?period=${period}`),
        apiGet(`/api/session-handoff?period=${period}`).catch(() => null),
      ]);
      content.innerHTML = `
        <div class="section-title">${en ? "Project Status" : "Project Status"}</div>

        <div class="period-tabs">${PS_PERIOD_TABS.map(([id, label]) => `
          <button class="period-tab ${id === period ? "active" : ""}" data-ps-period="${id}">${label}</button>
        `).join("")}</div>

        ${handoff ? `
        <div class="section-title" style="font-size:13px;">${en ? "Session Handoff" : "Session Handoff"}</div>
        <div class="card" style="margin-bottom:8px;">
          <p class="muted" style="font-size:12px;margin:0 0 8px;">${en
            ? "A ready-to-paste note summarizing this period and what to check next -- useful when handing off to someone else, or to your future self."
            : "Is period ka khulasa aur aage kya dekhna hai -- kisi aur ko handoff dete waqt, ya khud apne liye baad mein, kaam aata hai."}</p>
          <div style="white-space:pre-wrap;font-size:13px;">${esc(handoff.text)}</div>
          <div class="btn-row" style="margin-top:8px;">
            <button class="btn-ghost" id="btnCopyHandoff">${en ? "Copy as Text" : "Text Ke Taur Par Copy Karein"}</button>
          </div>
        </div>` : ""}

        <div class="section-title" style="font-size:13px;">${en ? "What Changed" : "Kya Badla"}</div>
        ${d.changelog.length ? d.changelog.map(c => `
          <div class="card" style="margin-bottom:8px;">
            <div><span class="pill pill-muted">${esc(c.category)}</span> <span class="muted" style="font-size:11px;">${esc(c.date)}</span></div>
            <div style="font-weight:600;margin-top:6px;">${esc(c.title)}</div>
            <div class="muted" style="font-size:13px;margin-top:4px;">${esc(c.detail)}</div>
            <div style="margin-top:6px;font-size:13px;"><b>${en ? "Outcome" : "Nateeja"}:</b> ${esc(c.outcome)}</div>
          </div>
        `).join("") : `<p class="muted">${en ? "Nothing changed in this period." : "Is period mein kuch nahi badla."}</p>`}

        <div class="section-title" style="font-size:13px;">${en ? "Quick Summary" : "Khulasa"}</div>
        <div class="grid">
          ${card("Total Strategies", fmtNum(d.summary.total_strategies))}
          ${cardClass("Genuinely Profitable", fmtNum(d.summary.profitable_count), "positive")}
          ${card("Aggregate Win Rate", d.summary.aggregate_win_rate != null ? d.summary.aggregate_win_rate.toFixed(2) + "%" : "-")}
          ${cardClass("Aggregate Net PnL", `${d.summary.aggregate_net_pnl >= 0 ? "+" : ""}$${d.summary.aggregate_net_pnl.toFixed(2)}`, d.summary.aggregate_net_pnl >= 0 ? "positive" : "negative")}
          ${card("Engine Gaps Found", fmtNum(d.summary.engine_gaps_found))}
          ${card("Engine Gaps Fixed", fmtNum(d.summary.engine_gaps_fixed))}
        </div>

        <div class="section-title" style="font-size:13px;">${en ? "What's Pending" : "Kya Baaki Hai"}</div>
        ${d.pending.map(p => `
          <div class="card" style="margin-bottom:8px;">
            <div><span class="pill ${p.status === "blocked" ? "pill-down" : p.status === "not started" ? "pill-muted" : "pill-pending"}">${esc(p.status)}</span> <b>${esc(p.item)}</b></div>
            <div class="muted" style="font-size:13px;margin-top:4px;">${esc(p.detail)}</div>
          </div>
        `).join("")}

        <div class="section-title" style="font-size:13px;">${en ? "Quick Notes" : "Quick Notes"}</div>
        <p class="muted" style="font-size:12.5px; margin:-4px 0 12px;">
          ${en ? "An instant scratch-pad -- jot anything down, no type or status needed. Different from Feedback / Requests below, which is a tracked backlog." : "Ek turant scratch-pad -- kuch bhi likh dein, koi type ya status nahi chahiye. Neeche ki Feedback/Requests se alag hai, wo ek tracked backlog hai."}
        </p>
        <div class="card">
          <div class="form-row">
            <textarea id="psQuickNoteText" rows="2" style="width:100%;" placeholder="${en ? "Quick note..." : "Quick note..."}"></textarea>
          </div>
          <button class="btn" id="psQuickNoteSubmit" style="margin-top:8px;">${en ? "Add Note" : "Note Jodein"}</button>
        </div>
        <div id="psQuickNotesList" style="margin-top:12px;"></div>

        <div class="section-title" style="font-size:13px;">${en ? "Feedback / Requests" : "Feedback / Guzarish"}</div>
        <div class="card">
          <div class="form-row">
            <select id="psFeedbackType">
              <option value="Suggest">Suggest</option>
              <option value="Add">Add</option>
              <option value="Fix">Fix</option>
              <option value="Wrong">Wrong</option>
            </select>
          </div>
          <div class="form-row" style="margin-top:8px;">
            <textarea id="psFeedbackText" rows="3" style="width:100%;" placeholder="${en ? "Type your note..." : "Apna note likhein..."}"></textarea>
          </div>
          <button class="btn" id="psFeedbackSubmit" style="margin-top:8px;">${en ? "Submit" : "Bhej Dein"}</button>
        </div>
        <div id="psFeedbackList" style="margin-top:12px;"></div>

        <p class="muted" style="font-size:12px;">${en ? "Generated" : "Bana"}: ${esc(d.generated_at)}</p>
      `;
      content.querySelectorAll("[data-ps-period]").forEach(btn => {
        btn.onclick = () => load(btn.dataset.psPeriod);
      });
      const copyHandoffBtn = document.getElementById("btnCopyHandoff");
      if (copyHandoffBtn && handoff) {
        copyHandoffBtn.onclick = async () => {
          try {
            await navigator.clipboard.writeText(handoff.text);
            showToast({ title: en ? "Copied" : "Copy Ho Gaya", body: en ? "Handoff note copied -- paste it anywhere." : "Handoff note copy ho gaya -- kahin bhi paste karein." });
          } catch (e) {
            showToast({ title: en ? "Could not copy" : "Copy Nahi Ho Saka", body: en ? "Your browser blocked clipboard access." : "Browser ne clipboard access block kar diya.", isError: true });
          }
        };
      }
      const submitBtn = document.getElementById("psFeedbackSubmit");
      if (submitBtn) {
        submitBtn.onclick = async () => {
          const type = document.getElementById("psFeedbackType").value;
          const text = document.getElementById("psFeedbackText").value.trim();
          if (!text) return;
          submitBtn.disabled = true;
          try {
            await apiPost("/api/feedback", { type, text });
            document.getElementById("psFeedbackText").value = "";
            await loadFeedback();
          } catch (e) {
            alert(`${en ? "Could not submit" : "Bhej nahi saka"}: ${e.message}`);
          } finally {
            submitBtn.disabled = false;
          }
        };
      }
      const quickNoteBtn = document.getElementById("psQuickNoteSubmit");
      if (quickNoteBtn) {
        quickNoteBtn.onclick = async () => {
          const content = document.getElementById("psQuickNoteText").value.trim();
          if (!content) return;
          quickNoteBtn.disabled = true;
          try {
            await apiPost("/api/quick-notes", { content });
            document.getElementById("psQuickNoteText").value = "";
            await loadQuickNotes();
          } catch (e) {
            alert(`${en ? "Could not save" : "Save nahi ho saka"}: ${e.message}`);
          } finally {
            quickNoteBtn.disabled = false;
          }
        };
      }
      await loadQuickNotes();
      await loadFeedback();
    }
    await load("all");
  }

  const PAGES = {
    home: renderHome, market: renderMarket, data: renderData,
    backtesting: renderBacktesting, reports: renderReports, settings: renderSettings,
    knowledge: renderKnowledge, strategies: renderStrategies,
    paper_trading: renderPaperTrading, knowledge_compiler: renderKnowledgeCompiler,
    ai_center: renderAiCenter, backtest_history: renderBacktestHistory,
    pipeline_history: renderPipelineHistory,
    evolution: renderEvolution, evolution_history: renderEvolutionHistory, sindhu_strategy: renderSindhuStrategy,
    signal_tracker: renderSignalTracker, strategy_lab: renderStrategyLab, self_learning: renderSelfLearning,
    challenge_mode: renderChallengeMode,
    strategy_wizard: renderStrategyWizard,
    web_sourced_strategies: renderWebSourcedStrategies,
    control_center: renderControlCenter,
    telegram_dashboard: renderTelegramDashboard,
    ceo: renderCEO,
    clarification_center: renderClarificationCenter,
    external_signals: renderExternalSignals,
    compare: renderCompare, live_logs: renderLiveLogs, project_status: renderProjectStatus,
    incidents: renderIncidents,
    strategy_lifecycle: renderStrategyLifecycle,
    strategy_overview: renderStrategyOverview,
  };
  let refreshTimer = null;
  let pendingStrategyLoadId = null;
  let pendingHistoryBatchId = null;
  // Task 4 (navigation): lets Reports' Per-Strategy Breakdown table deep-link
  // straight into that strategy's Profile popup on the Strategies page
  // (Balance History / Coin-Wise Performance / Confluence Score Trend live
  // there) instead of making the CEO find the same strategy again by hand.
  let pendingProfileStrategyId = null;
  // Bumped on every navigation. A page's own render()/autoRefresh callback
  // captures the token in effect when it started; if it's stale by the
  // time an awaited fetch resolves (the user already navigated away), it
  // skips writing to `content` instead of clobbering whatever page is
  // showing now. Without this, a slow Home refresh landing after you'd
  // already clicked through to another page would silently overwrite it.
  let activeRouteToken = 0;
  function isStaleRoute(token) { return token !== activeRouteToken; }

  async function route() {
    activeRouteToken++;
    const id = (location.hash || "#home").slice(1);
    setActiveNav(id);
    clearLiveListeners();
    if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null; }
    sidebar.classList.remove("open"); overlay.classList.remove("open");

    const renderFn = PAGES[id] || renderHome;
    content.innerHTML = `
      <div class="page-skeleton">
        <div class="skel-bar skel-title"></div>
        <div class="skel-grid">
          <div class="skel-card"></div><div class="skel-card"></div>
          <div class="skel-card"></div><div class="skel-card"></div>
        </div>
        <div class="skel-bar skel-row"></div>
        <div class="skel-bar skel-row"></div>
        <div class="skel-bar skel-row"></div>
      </div>`;
    try {
      await renderFn();
    } catch (e) {
      content.innerHTML = `<div class="card"><b>Failed to load page</b><br>${esc(e.message)}</div>`;
    }
    // Deterministic stamp right after every page render, in addition to the
    // MutationObserver (which covers later in-place tbody refreshes) -- so
    // even if the observer somehow misses a beat, a freshly-routed page is
    // always labeled.
    stampTableLabels();
  }
  window.addEventListener("hashchange", route);

  function autoRefresh(fn, seconds) {
    const token = activeRouteToken;
    refreshTimer = setInterval(() => {
      if (isStaleRoute(token)) { clearInterval(refreshTimer); return; }
      fn().catch(console.error);
    }, seconds * 1000);
  }

  // ------------------------------------------------------------ HOME
  function moduleStatusPill(status) {
    const cls = status === "Running" ? "pill-completed" : "pill-pending";
    return `<span class="pill ${cls}">${esc(status)}</span>`;
  }

  function timeAgo(iso) {
    if (!iso) return "-";
    const secs = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
    if (secs < 60) return `${secs}s ago`;
    if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
    return `${Math.floor(secs / 3600)}h ago`;
  }

  async function renderHome() {
    const myToken = activeRouteToken;
    const settings = await apiGet("/api/settings").catch(() => ({ refresh_speed_seconds: 10 }));
    const render = async () => {
      const [h, net, act, bw, strats, tgAlert, stratSummary, killSwitch, drawdown, openIncidents, paperAlerts, retirementSug] = await Promise.all([
        apiGet("/api/home"),
        apiGet("/api/network").catch(() => null),
        apiGet("/api/activity?limit=20").catch(() => ({ activity: [] })),
        apiGet("/api/reports/best-worst/strategies").catch(() => ({ ranking: [] })),
        apiGet("/api/backtesting/strategies").catch(() => ({ strategies: [] })),
        apiGet(`/api/paper-trading/telegram/alert-status?lang=${getLang()}`).catch(() => ({ stale: false })),
        apiGet("/api/strategy-summary").catch(() => null),
        apiGet("/api/paper-trading/kill-switch/status").catch(() => ({ active: false })),
        apiGet("/api/paper-trading/account-drawdown-status").catch(() => ({ paused: false })),
        apiGet("/api/incidents?status=open&limit=20").catch(() => ({ incidents: [] })),
        apiGet("/api/paper-trading/alerts?limit=20").catch(() => ({ alerts: [] })),
        apiGet("/api/paper-trading/retirement-suggestions").catch(() => ({ suggestions: [] })),
      ]);
      if (isStaleRoute(myToken)) return;

      const topStrategies = (bw.ranking || []).slice(0, 3);
      const zeroTradeAlerts = (strats.strategies || []).filter(s =>
        s.last_batch_result && s.last_batch_result.status === "completed" && s.last_batch_result.total_trades === 0
      );

      // Grand Feature Expansion, Phase 4 Feature 19: Today's Focus Widget --
      // synthesizes the single most important thing to look at right now
      // from several already-computed, already-cheap sources (kill switch,
      // account drawdown pause, open high/critical incidents, paper_alerts
      // -- which itself already aggregates win-rate decay/divergence/custom-
      // rule triggers, retirement suggestions, plus the zero-trade/Telegram-
      // stale alerts already computed above) rather than re-running the CEO
      // page's ~20 heavier per-module checks, which would reintroduce the
      // same N-calls-per-poll cost this codebase has already fixed elsewhere.
      // Fixed, documented severity order -- most safety-critical first.
      const focusItems = [];
      if (killSwitch.active) {
        focusItems.push({ severity: "critical", text: getLang() === "en"
          ? `Kill switch is ACTIVE${killSwitch.reason ? ` (${killSwitch.reason})` : ""} -- all trading is halted.`
          : `Kill switch ACTIVE hai${killSwitch.reason ? ` (${killSwitch.reason})` : ""} -- saari trading ruki hui hai.` });
      }
      if (drawdown.paused) {
        focusItems.push({ severity: "critical", text: getLang() === "en"
          ? `Account-wide drawdown protection is active${drawdown.paused_reason ? ` (${drawdown.paused_reason})` : ""} -- new trades are paused for every strategy.`
          : `Account-wide drawdown protection active hai${drawdown.paused_reason ? ` (${drawdown.paused_reason})` : ""} -- har strategy ke naye trades paused hain.` });
      }
      (openIncidents.incidents || []).filter(i => i.severity === "critical" || i.severity === "high").forEach(i => {
        focusItems.push({ severity: i.severity === "critical" ? "critical" : "high", text: getLang() === "en"
          ? `Open incident (${i.severity}): ${i.title}` : `Khula incident (${i.severity}): ${i.title}` });
      });
      (paperAlerts.alerts || []).filter(a => a.severity === "critical" || a.severity === "error" || a.severity === "warning").slice(0, 5).forEach(a => {
        focusItems.push({ severity: a.severity === "critical" || a.severity === "error" ? "high" : "medium", text: a.message });
      });
      (retirementSug.suggestions || []).forEach(s => {
        focusItems.push({ severity: "medium", text: getLang() === "en"
          ? `"${s.strategy_name}" was auto-retired long ago and is still active -- consider archiving it.`
          : `"${s.strategy_name}" bohot pehle retire ho chuki thi aur abhi bhi active hai -- archive karne par ghor karein.` });
      });
      zeroTradeAlerts.forEach(s => {
        focusItems.push({ severity: "medium", text: getLang() === "en"
          ? `Strategy "${s.name}" produced 0 trades -- check its entry conditions.`
          : `Strategy "${s.name}" ne 0 trades diye -- entry conditions check karein.` });
      });
      if (tgAlert.stale) {
        focusItems.push({ severity: "low", text: tgAlert.message });
      }
      const severityOrder = { critical: 0, high: 1, medium: 2, low: 3 };
      focusItems.sort((a, b) => severityOrder[a.severity] - severityOrder[b.severity]);
      const todaysFocus = focusItems[0] || null;

      // Grand Feature Expansion, Phase 4 Feature 18: Onboarding Checklist
      // Per Session -- genuinely distinct from Real-Trading Readiness (a
      // one-time go-live gate) and Project Status's pending[] (a
      // persistent project backlog): a fresh "what to actually look at
      // today" list that resets every calendar day, mixing a few standing
      // routine checks with today's own Today's Focus items rendered as
      // checkable tasks instead of a passive alert. Stored per-browser in
      // localStorage keyed by today's date, so it naturally starts empty
      // (unchecked) again tomorrow with zero backend/schedule needed.
      const todayKey = new Date().toISOString().slice(0, 10);
      const checklistStorageKey = `sindhu_session_checklist_${todayKey}`;
      const routineChecklistItems = getLang() === "en" ? [
        "Review any open positions on the Paper Trading page",
        "Check the Telegram Signals delivery status",
        "Skim Live Logs for anything unusual",
      ] : [
        "Paper Trading page par open positions dekhein",
        "Telegram Signals ki delivery status check karein",
        "Live Logs mein kuch ajeeb to nahi, dekh lein",
      ];
      const checklistItems = [
        ...routineChecklistItems,
        ...focusItems.map(f => (getLang() === "en" ? `Resolve: ${f.text}` : `Hal karein: ${f.text}`)),
      ];

      const moduleRows = Object.entries(h.module_status || {})
        .map(([name, status]) => `<tr><td>${esc(name)}</td><td>${moduleStatusPill(status)}</td></tr>`).join("");

      const deviceRows = (net ? net.connected_devices : []).map(d => `
        <tr><td>${esc(d.ip)}</td><td>${timeAgo(d.connected_at)}</td><td>${esc((d.user_agent || "").slice(0, 40))}</td></tr>
      `).join("");

      const ts = h.task_summary || { running: 0, waiting: 0, completed: 0, failed: 0 };

      const activityRows = (act.activity || []).map(a => `
        <div class="activity-item"><span class="activity-time">${esc((a.created_at || "").slice(11, 19))}</span> ${esc(a.message)}</div>
      `).join("") || `<div class="muted">No activity yet.</div>`;

      const lb = h.latest_batch;
      const pnlClass = lb ? (lb.profit_pct > 0 ? "positive" : lb.profit_pct < 0 ? "negative" : "") : "";
      // The caption under "Overview" used to hardcode "there is no live Paper
      // Trading yet, so this reflects the most recent backtest". That became
      // untrue the moment Paper Trading started closing real trades -- the API
      // already reports which source it used in latest_batch.strategy, so the
      // note is now derived from that instead of asserted.
      const isLiveSource = lb && /paper trading/i.test(String(lb.strategy || ""));
      const sourceNote = isLiveSource
        ? (getLang() === "en"
            ? `Live <b>Paper Trading</b> account -- realized results only`
            : `Live <b>Paper Trading</b> account -- sirf realized (band) trades`)
        : (getLang() === "en"
            ? `Latest completed <b>backtest</b>, not a live account`
            : `Latest <b>backtest</b> ke numbers, live account ke nahi`);

      content.innerHTML = `
        <div class="card" style="border-left:3px solid ${todaysFocus ? (todaysFocus.severity === "critical" ? "var(--red, #e5484d)" : todaysFocus.severity === "high" ? "var(--red, #e5484d)" : todaysFocus.severity === "medium" ? "var(--orange, #d68910)" : "var(--muted-fg, #888)") : "var(--green, #2fb344)"}; margin-bottom:14px;">
          <div style="font-weight:600;font-size:13px;">${getLang() === "en" ? "Today's Focus" : "Aaj Ka Focus"}</div>
          <div style="margin-top:6px;">${todaysFocus ? esc(todaysFocus.text) : (getLang() === "en" ? "Nothing urgent -- everything looks fine right now." : "Kuch bhi zaroori nahi -- abhi sab kuch theek lag raha hai.")}</div>
          ${focusItems.length > 1 ? `<div class="muted" style="font-size:11px;margin-top:6px;">${getLang() === "en" ? `+${focusItems.length - 1} more thing(s) to check (System Alerts, Alerts, Incidents, Strategies pages).` : `+${focusItems.length - 1} aur cheezein check karne ke liye (System Alerts, Alerts, Incidents, Strategies pages).`}</div>` : ""}
        </div>

        <div class="card" id="sessionChecklistCard" style="margin-bottom:14px;">
          <div style="font-weight:600;font-size:13px;">${getLang() === "en" ? "Today's Checklist" : "Aaj Ki Checklist"}</div>
          <p class="muted" style="font-size:11.5px;margin:4px 0 8px;">${getLang() === "en" ? "Resets fresh every day -- just for this browser." : "Har din nayi ho jaati hai -- sirf is browser ke liye."}</p>
          <div id="sessionChecklistBody"></div>
        </div>

        <div class="section-head">
          <div class="section-title">${t("Overview")}</div>
          ${lb ? `<div class="section-sub">${sourceNote}</div>` : ""}
        </div>
        <div class="kpi-grid">
          ${kpi("Balance", lb ? `$${Number(lb.final_balance).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}` : "--", "",
                lb ? esc(lb.strategy) : (getLang() === "en" ? "No data yet" : "Abhi koi data nahi"))}
          ${kpi("PnL", lb ? `${lb.profit_pct > 0 ? "+" : ""}${lb.profit_pct}%` : "--", pnlClass,
                isLiveSource
                  ? (getLang() === "en" ? "Realized, live account" : "Realized, live account")
                  : (getLang() === "en" ? "Return over the backtest" : "Backtest ka return"))}
          ${kpi("Win Rate", lb ? `${lb.win_rate}%` : "--", "",
                lb ? (getLang() === "en" ? `across ${fmtNum(lb.total_trades)} closed trades` : `${fmtNum(lb.total_trades)} band trades par`) : "")}
          ${kpi("Total Trades", lb ? fmtNum(lb.total_trades) : "--", "",
                getLang() === "en" ? "Simulated fills" : "Simulated trades")}
        </div>
        <div class="status-strip">
          ${statusChip("Knowledge Score", `${h.knowledge_score}%`, h.knowledge_score >= 100 ? "positive" : "")}
          ${statusChip("Evolution Score", "N/A", "muted-v")}
          ${statusChip("Database Status", esc(h.database_status),
                       String(h.database_status).toLowerCase() === "connected" ? "positive" : "")}
          ${statusChip("System Health", esc(h.system_health),
                       String(h.system_health).toUpperCase() === "OK" ? "positive" : "")}
        </div>

        <div class="section-head">
          <div class="section-title">${t("System Maturity Level")}</div>
          <div class="section-sub">${getLang() === "en" ? "Step" : "Step"} ${h.maturity.level} / 5</div>
        </div>
        <div class="card maturity-card">
          <div class="maturity-top">
            <div class="maturity-level"><span class="ml-num">Level ${h.maturity.level}</span> -- ${esc(h.maturity.level_name)}</div>
            <div class="maturity-steps">
              ${[1,2,3,4,5].map(n => `<div class="maturity-step${n <= h.maturity.level ? " on" : ""}"></div>`).join("")}
            </div>
          </div>
          <div class="maturity-body">${esc(h.maturity.criteria_text)}</div>
          ${h.maturity.next_level
            ? `<div class="maturity-next"><b>${getLang() === "en" ? `To reach Level ${h.maturity.next_level}` : `Level ${h.maturity.next_level} tak pahunchne ke liye`}:</b> ${esc(h.maturity.next_level_criteria_text)}</div>`
            : `<div class="maturity-next">${getLang() === "en" ? "Highest level reached." : "Sabse upar wala level haasil ho chuka hai."}</div>`}
          <div class="maturity-metrics">
            ${maturityMetric(`${h.maturity.metrics.strategies_with_25plus_trades}/${h.maturity.metrics.total_strategy_books}`,
              getLang() === "en" ? "strategies with 25+ real trades" : "strategies ne 25+ real trades poori ki")}
            ${maturityMetric(h.maturity.metrics.strategies_statistically_proven_positive,
              getLang() === "en" ? "statistically proven positive" : "statistically positive saabit hui")}
            ${maturityMetric(h.maturity.metrics.evolution_gate_completions,
              getLang() === "en" ? "passed the 100-trade Evolution gate" : "100-trade Evolution gate poora kiya")}
            ${maturityMetric(h.maturity.metrics.signals_sent_last_7_days,
              getLang() === "en" ? "signals sent in the last 7 days" : "signals pichle 7 dinon mein bheje")}
          </div>
        </div>

        ${(zeroTradeAlerts.length || tgAlert.stale) ? `
        <div class="section-title">${t("System Alerts")}</div>
        <div class="card" style="border-left:3px solid var(--red, #e5484d);">
          ${tgAlert.stale ? `<div>⚠ ${esc(tgAlert.message)} ${getLang() === "en" ? "Check the Telegram Signals page or Settings if this is unexpected." : "Agar yeh ummeed se zyada hai to Telegram Signals page ya Settings check karein."}</div>` : ""}
          ${zeroTradeAlerts.map(s => `<div>⚠ ${getLang() === "en"
            ? `Strategy <b>${esc(s.name)}</b> produced 0 trades on ${s.last_batch_result.symbols_tested || 0} coins -- check entry conditions (see Backtesting or Reports for the condition-hit breakdown).`
            : `Strategy <b>${esc(s.name)}</b> ne ${s.last_batch_result.symbols_tested || 0} coins par 0 trades diye -- entry conditions check karein (Backtesting ya Reports mein condition-hit breakdown dekhein).`}</div>`).join("")}
        </div>` : ""}

        <div class="section-title">${t("Top Strategies by Profit")}</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Strategy</th><th>Avg Profit %</th><th>Batches</th></tr></thead>
          <tbody>${topStrategies.map(t => `
            <tr><td>${esc(t.strategy)}</td><td class="${t.avg_profit_pct > 0 ? 'positive' : t.avg_profit_pct < 0 ? 'negative' : ''}">${t.avg_profit_pct}%</td><td>${t.batches}</td></tr>
          `).join("") || `<tr><td colspan="3" class="empty-cell">${getLang() === "en"
              ? "No completed backtests yet -- run one from the Backtesting page."
              : "Abhi koi backtest mukammal nahi hui -- Backtesting page se ek chalayein."}</td></tr>`}</tbody>
        </table></div>

        ${stratSummary ? `
        <div class="section-title">${t("All Strategies -- Aggregate Performance")}</div>
        ${stratSummary.optimizer_in_progress ? `
        <div class="card" style="border-left:3px solid var(--accent, #4f7cff); margin-bottom:12px; font-size:12.5px;">
          ${getLang() === "en"
            ? "The Optimizer tuning pass is currently running in the background -- the figures below are the last completed backtest for each strategy (pre-optimization for whichever strategy is mid-run), not partial/draft optimizer results."
            : "Optimizer tuning pass abhi background mein chal rahi hai -- neeche diye numbers har strategy ke aakhri complete backtest ke hain (jo strategy abhi tune ho rahi hai uske purane/pre-optimization numbers), koi adhoora/draft result nahi dikhaya ja raha."}
        </div>` : ""}
        <div class="kpi-grid">
          ${kpi("Total Strategies", stratSummary.total_strategies, "",
                getLang() === "en" ? "with a completed backtest" : "jinka backtest mukammal hai")}
          ${kpi("Genuinely Profitable", `${stratSummary.profitable_count} / ${stratSummary.total_strategies}`,
                stratSummary.profitable_count > 0 ? "positive" : "",
                getLang() === "en" ? "profit factor above 1.0" : "profit factor 1.0 se upar")}
          ${kpi("Aggregate Win Rate", stratSummary.aggregate_trade_weighted_win_rate !== null ? `${stratSummary.aggregate_trade_weighted_win_rate}%` : "--", "",
                getLang() === "en" ? "weighted by trade count" : "trade count ke hisaab se weighted")}
          ${kpi("Aggregate Net PnL", `${stratSummary.aggregate_net_pnl >= 0 ? "+" : ""}$${Number(stratSummary.aggregate_net_pnl).toLocaleString(undefined, {maximumFractionDigits: 0})}`,
                stratSummary.aggregate_net_pnl >= 0 ? "positive" : "negative",
                getLang() === "en" ? "every strategy combined" : "sab strategies mila kar")}
        </div>
        <div class="grid" style="grid-template-columns: repeat(2, 1fr); margin-top:8px;">
          ${stratSummary.best ? `<div class="card" style="border-left:3px solid var(--green, #22c55e);">
            <div class="muted" style="font-size:11px; text-transform:uppercase; letter-spacing:.04em;">${getLang() === "en" ? "Best Performer" : "Sabse Behtar"}</div>
            <div style="font-weight:700; margin:4px 0;">${esc(stratSummary.best.name.replace(" [Manual Build]", ""))}</div>
            <div class="muted" style="font-size:12.5px;">PF <b class="positive">${stratSummary.best.profit_factor}</b> &middot; ${stratSummary.best.trades.toLocaleString()} trades &middot; net ${stratSummary.best.net_pnl >= 0 ? "+" : ""}$${Number(stratSummary.best.net_pnl).toLocaleString(undefined, {maximumFractionDigits: 0})}</div>
          </div>` : ""}
          ${stratSummary.worst ? `<div class="card" style="border-left:3px solid var(--red, #e5484d);">
            <div class="muted" style="font-size:11px; text-transform:uppercase; letter-spacing:.04em;">${getLang() === "en" ? "Worst Performer" : "Sabse Kam"}</div>
            <div style="font-weight:700; margin:4px 0;">${esc(stratSummary.worst.name.replace(" [Manual Build]", ""))}</div>
            <div class="muted" style="font-size:12.5px;">PF <b class="negative">${stratSummary.worst.profit_factor}</b> &middot; ${stratSummary.worst.trades.toLocaleString()} trades &middot; net ${stratSummary.worst.net_pnl >= 0 ? "+" : ""}$${Number(stratSummary.worst.net_pnl).toLocaleString(undefined, {maximumFractionDigits: 0})}</div>
          </div>` : ""}
        </div>
        <div class="table-wrap" style="margin-top:12px;"><table>
          <thead><tr><th>${getLang() === "en" ? "Strategy" : "Strategy"}</th><th>${getLang() === "en" ? "Trades" : "Trades"}</th><th>${getLang() === "en" ? "Win Rate" : "Win Rate"}</th><th>PF</th><th>${getLang() === "en" ? "Net PnL" : "Net PnL"}</th><th>${getLang() === "en" ? "Verdict" : "Verdict"}</th></tr></thead>
          <tbody>${stratSummary.strategies.map(s => `
            <tr><td>${esc(s.name.replace(" [Manual Build]", ""))}</td><td>${s.trades.toLocaleString()}</td><td>${s.win_rate}%</td>
              <td class="${s.profitable ? "positive" : "negative"}">${s.profit_factor}</td>
              <td class="${s.net_pnl >= 0 ? "positive" : "negative"}">${s.net_pnl >= 0 ? "+" : ""}$${Number(s.net_pnl).toLocaleString(undefined, {maximumFractionDigits: 0})}</td>
              <td>${s.profitable ? `<span class="pill pill-completed">${getLang() === "en" ? "Profitable" : "Profitable"}</span>` : `<span class="pill pill-muted">${getLang() === "en" ? "Not Profitable" : "Not Profitable"}</span>`}</td>
            </tr>`).join("")}</tbody>
        </table></div>
        <div class="muted" style="font-size:11px; margin-top:6px;">${getLang() === "en" ? "Last updated" : "Aakhri update"}: ${new Date(stratSummary.generated_at).toLocaleString()}</div>
        ` : ""}

        <div class="section-title">${t("System Monitor")}</div>
        <div class="grid">
          ${card("CPU Usage", `${h.cpu_percent}%`)}
          ${card("RAM Usage", `${h.ram_percent}%`)}
          ${card("Disk Usage", fmtBytes(h.disk_usage_bytes))}
          ${card("Database Size", fmtBytes(h.database_size_bytes))}
          ${card("API", `<span class="pill pill-completed">Online</span>`)}
          ${card("Exchange", esc(h.exchange))}
          ${card("Queue", fmtNum(ts.running))}
          ${card("Background Tasks", fmtNum(ts.running + ts.completed + ts.failed))}
        </div>
        <div class="section-title">${t("Available Timeframes")}</div>
        <div class="card">${h.available_timeframes.join(", ")}</div>

        <div class="section-title">${t("Control Center")}</div>
        <div class="two-col">
          <div class="card">
            <div class="label">Connect from mobile (same WiFi)</div>
            <div class="value" style="font-size:15px;margin:6px 0;">${net ? esc(net.url) : "-"}</div>
            <div class="qr-box">${net ? net.qr_svg : ""}</div>
          </div>
          <div>
            <div class="section-title" style="margin-top:0;">${t("Task Manager")}</div>
            <div class="grid">
              ${card("Running", fmtNum(ts.running))}
              ${card("Waiting", fmtNum(ts.waiting))}
              ${card("Completed", fmtNum(ts.completed))}
              ${card("Failed", fmtNum(ts.failed))}
            </div>
            <div class="section-title">Module Status</div>
            <div class="table-wrap"><table><tbody>${moduleRows}</tbody></table></div>
            <div class="section-title">Quick Buttons</div>
            <div class="btn-row">
              <button class="btn-ghost" id="ccStart">Start Download</button>
              <button class="btn-ghost" id="ccPause">Pause Current Task</button>
              <button class="btn-ghost" id="ccStop">Stop Current Task</button>
              <button class="btn-ghost" id="ccBackup">Backup Now</button>
              <button class="btn-ghost" id="ccLogs">Open Logs</button>
              <button class="btn-ghost" id="ccRestart">Restart Services</button>
            </div>
          </div>
        </div>

        <div class="section-title">Connected Devices</div>
        <div class="table-wrap"><table>
          <thead><tr><th>IP Address</th><th>Connected</th><th>Device</th></tr></thead>
          <tbody>${deviceRows || '<tr><td colspan="3">No other devices connected</td></tr>'}</tbody>
        </table></div>

        <div class="section-title">Activity Feed</div>
        <div class="card activity-feed">${activityRows}</div>
      `;

      document.getElementById("ccStart").onclick = async () => { await apiPost("/api/data/download"); appendLog("Download started from Control Center."); };
      document.getElementById("ccPause").onclick = async () => { if (h.current_task) await apiPost(`/api/jobs/${h.current_task.id}/pause`); };
      document.getElementById("ccStop").onclick = async () => { if (h.current_task) await apiPost(`/api/jobs/${h.current_task.id}/stop`); };
      document.getElementById("ccBackup").onclick = async () => { await apiPost("/api/backup/create"); appendLog("Manual backup created."); };
      document.getElementById("ccLogs").onclick = () => document.getElementById("logsPanel").classList.toggle("open");
      document.getElementById("ccRestart").onclick = async () => { await apiPost("/api/system/restart-services"); appendLog("Services soft-restarted."); };

      // Today's Checklist (Feature 18) -- rendered/wired separately from
      // the innerHTML template above since checkbox state comes from
      // localStorage, read fresh on every render() call (including the
      // periodic auto-refresh), not from the server.
      let checked = {};
      try { checked = JSON.parse(localStorage.getItem(checklistStorageKey) || "{}"); } catch (e) { checked = {}; }
      const checklistBody = document.getElementById("sessionChecklistBody");
      if (checklistBody) {
        // Keyed by the item's own text (not array index) so a checked box
        // stays correctly attached to its item even if the list's content
        // shifts between renders (e.g. a new alert appears above it).
        checklistBody.innerHTML = checklistItems.map((text) => `
          <label style="display:flex;align-items:flex-start;gap:8px;padding:4px 0;font-size:13px;">
            <input type="checkbox" class="session-checklist-item" data-text="${esc(text)}" style="width:auto;margin-top:3px;" ${checked[text] ? "checked" : ""}>
            <span style="${checked[text] ? "text-decoration:line-through;opacity:.55;" : ""}">${esc(text)}</span>
          </label>`).join("") || `<p class="muted">${getLang() === "en" ? "Nothing on today's list." : "Aaj ki list khaali hai."}</p>`;
        checklistBody.querySelectorAll(".session-checklist-item").forEach(cb => {
          cb.onchange = () => {
            checked[cb.dataset.text] = cb.checked;
            localStorage.setItem(checklistStorageKey, JSON.stringify(checked));
            cb.nextElementSibling.style.textDecoration = cb.checked ? "line-through" : "none";
            cb.nextElementSibling.style.opacity = cb.checked ? ".55" : "1";
          };
        });
      }
    };
    await render();
    autoRefresh(render, settings.refresh_speed_seconds || 10);
    onLive((msg) => { if (msg.channel === "sync") render().catch(console.error); });
  }

  function card(label, value) {
    return `<div class="card"><div class="label">${t(label)}</div><div class="value">${value}</div></div>`;
  }

  function cardClass(label, value, valueClass, caption) {
    // caption: optional small line under the value (e.g. Compare's "Best
    // Performer" card showing which strategy). Omitted by every existing
    // caller, so this stays a no-op unless a 4th argument is passed.
    return `<div class="card"><div class="label">${t(label)}</div><div class="value ${valueClass || ""}">${value}</div>${caption ? `<div class="muted" style="font-size:11.5px;margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${caption}</div>` : ""}</div>`;
  }

  // ---- Overview hierarchy helpers (see .kpi / .status-strip in app.css) ----
  // cardClass() stays exactly as it is and every other page keeps using it;
  // these exist so the Overview can express "headline number" vs "system
  // state" as two different things instead of eight identical cards.
  function kpi(label, value, valueClass, sub) {
    const tone = valueClass === "positive" ? " is-positive"
               : valueClass === "negative" ? " is-negative" : "";
    return `<div class="kpi${tone}">
      <div class="kpi-label">${t(label)}</div>
      <div class="kpi-value ${valueClass || ""}">${value}</div>
      ${sub ? `<div class="kpi-sub">${sub}</div>` : ""}
    </div>`;
  }

  function statusChip(label, value, valueClass) {
    return `<div class="status-chip">
      <span class="sc-k">${t(label)}</span>
      <span class="sc-v ${valueClass || ""}">${value}</span>
    </div>`;
  }

  function maturityMetric(value, caption) {
    return `<div class="maturity-metric"><div class="mm-v">${value}</div><div class="mm-k">${caption}</div></div>`;
  }

  function cardId(id, label, value) {
    return `<div class="card"><div class="label">${t(label)}</div><div class="value" id="${id}">${value}</div></div>`;
  }

  // ------------------------------------------------------------ STRATEGY IMPORT CHOICE
  function showImportChoiceModal() {
    const en = getLang() === "en";
    const overlay = document.createElement("div");
    overlay.id = "importChoiceOverlay";
    overlay.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:9999;display:flex;align-items:center;justify-content:center;";
    overlay.innerHTML = `
      <div style="background:var(--bg-elevated,#1a1f2b);color:inherit;border-radius:12px;padding:28px;max-width:460px;width:92%;box-shadow:0 20px 60px rgba(0,0,0,.4);">
        <div class="section-title" style="margin-top:0;">${en ? "Nayi Strategy Kaise Banayein?" : "Nayi Strategy Kaise Banayein?"}</div>
        <p class="muted">${en
          ? "Both ways end up in the same place -- pick whichever suits this strategy."
          : "Dono raaste same jagah pohanchte hain -- jo is strategy ke liye theek lage woh choose karein."}</p>
        <button class="btn" id="choicePasteBtn" style="width:100%;margin-bottom:10px;text-align:left;">
          ${en ? "Strategy paste karo (AI se samjhega)" : "Strategy paste karo (AI se samjhega)"}<br>
          <span class="muted" style="font-size:12px;font-weight:normal;">${en ? "Fastest -- paste your notes, the system extracts the rules." : "Sabse tez -- apne notes paste karein, system rules nikaal lega."}</span>
        </button>
        <button class="btn-ghost" id="choiceWizardBtn" style="width:100%;text-align:left;">
          ${en ? "Step-by-step khud banao (Wizard)" : "Step-by-step khud banao (Wizard)"}<br>
          <span class="muted" style="font-size:12px;font-weight:normal;">${en ? "Guaranteed exact -- every field you pick or type yourself, nothing guessed." : "Bilkul exact -- har field aap khud choose ya type karte hain, kuch guess nahi hota."}</span>
        </button>
        <div class="btn-row" style="margin-top:16px;justify-content:flex-end;">
          <button class="btn-ghost" id="choiceCancelBtn">${en ? "Cancel" : "Cancel"}</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    const close = () => overlay.remove();
    overlay.onclick = (e) => { if (e.target === overlay) close(); };
    document.getElementById("choiceCancelBtn").onclick = close;
    document.getElementById("choicePasteBtn").onclick = () => { close(); location.hash = "#backtesting"; };
    document.getElementById("choiceWizardBtn").onclick = () => { close(); location.hash = "#strategy_wizard"; };
  }

  // ---- Paper Trading analytics: one shared renderer for the Paper Trading
  // page and the SINDHU CEO Paper Trading card's expanded view (CEO-parity
  // rule), both backed by the same /api/paper-trading/analytics endpoint so
  // neither can show a number the other disagrees with.
  // Mirrors PERIODS in sindhu_web/api/paper_trading.py -- the backend is
  // the source of truth; this list must stay in step with it.
  // "Last 7/15 Days" and "Last 1 Month" are ROLLING windows (today plus
  // the N-1 days before it), which is what a person means by "last week"
  // -- not "this calendar week", which resets to almost nothing every
  // Monday morning.
  const PERIOD_TABS = [
    ["today", "Today"], ["yesterday", "Yesterday"], ["7d", "Last 7 Days"],
    ["15d", "Last 15 Days"], ["30d", "Last 1 Month"], ["all", "All-Time"],
  ];

  function pnlSpan(pnl) {
    const v = Number(pnl || 0);
    // Sign goes BEFORE the currency symbol ("-$2.73", not "$-2.73") --
    // the latter reads as a malformed amount rather than a loss.
    return `<span class="${v >= 0 ? "pill-up" : "pill-down"}">${v >= 0 ? "+" : "-"}$${Math.abs(v).toFixed(2)}</span>`;
  }

  function paperPeriodTabsHtml(idPrefix, activePeriod) {
    return `<div class="period-tabs">${PERIOD_TABS.map(([id, label]) => `
      <button class="period-tab ${id === activePeriod ? "active" : ""}" data-period-tab="${idPrefix}" data-period="${id}">${label}</button>
    `).join("")}</div>`;
  }

  // The three numbers a person actually opens this page to see, given
  // their own row at the top at a size you cannot miss -- everything else
  // is detail underneath. Deliberately not six equal-weight cards: when
  // everything is emphasised, nothing is.
  function paperHeroHtml(d) {
    const s = d.summary;
    const pnl = s.total_pnl;
    const tone = pnl > 0 ? "up" : pnl < 0 ? "down" : "flat";
    return `
      <div class="headline-band">
        <div class="headline-main tone-${tone}">
          <div class="headline-label">Profit / Loss</div>
          <div class="headline-value">${pnl >= 0 ? "+" : "-"}$${Math.abs(pnl).toFixed(2)}</div>
          <div class="headline-sub">${fmtNum(s.closed_trades)} finished trades in this period</div>
        </div>
        <div class="headline-side">
          <div class="headline-label">Win Ratio</div>
          <div class="headline-value">${s.win_rate.toFixed(1)}%</div>
          <div class="headline-sub">${fmtNum(s.win_count)} won &middot; ${fmtNum(d.loss_count != null ? d.loss_count : Math.max(s.closed_trades - s.win_count, 0))} lost</div>
        </div>
        <div class="headline-side">
          <div class="headline-label">Open Right Now</div>
          <div class="headline-value">${fmtNum(d.open_positions_count)}</div>
          <div class="headline-sub">Still running &mdash; not counted above</div>
        </div>
      </div>`;
  }

  // Best / worst strategy IN THIS PERIOD. Both come from the backend,
  // which only ever nominates a strategy that actually closed a trade in
  // the window -- a strategy that has not traded yet is never labelled
  // "worst" just because its $0.00 sorts below a losing one.
  function periodLeaderCardHtml(row, kind) {
    const isBest = kind === "best";
    const title = isBest ? "Best Strategy This Period" : "Worst Strategy This Period";
    if (!row) {
      return `<div class="card lead-card">
        <div class="label">${title}</div>
        <div class="muted" style="font-size:12.5px;margin-top:6px;">No strategy closed a trade in this period yet, so there is nothing to rank.</div>
      </div>`;
    }
    return `<div class="card lead-card ${isBest ? "lead-best" : "lead-worst"}">
      <div class="label">${title}</div>
      <div class="lead-name">${esc(row.strategy_name || row.strategy_id)}</div>
      <div class="lead-meta">
        ${pnlSpan(row.total_pnl)}
        <span class="muted">${fmtNum(row.closed_trades)} trades &middot; ${Number(row.win_rate).toFixed(1)}% won</span>
      </div>
      <button class="btn-ghost pt-strategy-periods" data-id="${esc(row.strategy_id)}" data-name="${esc(row.strategy_name || row.strategy_id)}">See its full record</button>
    </div>`;
  }

  function paperAnalyticsSectionHtml(d) {
    const s = d.summary;
    const isAll = d.period === "all";
    return `
      ${paperHeroHtml(d)}

      <div class="two-col">
        ${periodLeaderCardHtml(d.best_strategy, "best")}
        ${periodLeaderCardHtml(d.worst_strategy, "worst")}
      </div>

      <div class="grid">
        ${card("Current Balance (all books added up)", `$${Number(d.current_balance != null ? d.current_balance : 0).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}`)}
        ${card("Total Trades Taken", fmtNum(s.closed_trades))}
        ${card("Wins", fmtNum(s.win_count))}
        ${card("Losses", fmtNum(d.loss_count != null ? d.loss_count : Math.max(s.closed_trades - s.win_count, 0)))}
        ${card("Active Strategies", fmtNum(s.active_strategies))}
        ${card(`Average Reward vs Risk ${helpIcon("risk_reward")}`, s.avg_rr != null ? `${s.avg_rr.toFixed(2)}R` : "-")}
      </div>
      <p class="muted plain-note">A balance is a right-now figure, so it reads the same whichever period you pick. Everything else above only counts trades that finished inside the selected period. Trades still open are never mixed in &mdash; they get their own count.</p>

      <div class="two-col">
        <div class="card">
          <div class="label">Best-Performing Coin</div>
          ${d.best_coin
            ? `<div class="value positive">${esc(d.best_coin.symbol)}</div>
               <div class="muted" style="font-size:12px;">${fmtNum(d.best_coin.closed_trades)} trades, ${d.best_coin.win_rate.toFixed(1)}% win rate, ${pnlSpan(d.best_coin.total_pnl)}</div>`
            : `<div class="muted">No closed trades yet.</div>`}
        </div>
        <div class="card">
          <div class="label">Worst-Performing Coin</div>
          ${d.worst_coin
            ? `<div class="value negative">${esc(d.worst_coin.symbol)}</div>
               <div class="muted" style="font-size:12px;">${fmtNum(d.worst_coin.closed_trades)} trades, ${d.worst_coin.win_rate.toFixed(1)}% win rate, ${pnlSpan(d.worst_coin.total_pnl)}</div>`
            : `<div class="muted">No closed trades yet.</div>`}
        </div>
      </div>

      <div class="section-title">Per-Strategy Breakdown${isAll ? " -- Permanent Record" : ""}</div>
      ${strategyBreakdownCardsHtml(d.per_strategy, isAll)}

      <div class="section-title">Per-Coin Breakdown${isAll ? " (All-Time)" : ""}</div>
      <div class="table-wrap"><table>
        <thead><tr><th>Coin</th><th>Closed Trades</th><th>Win Rate</th><th>PnL</th></tr></thead>
        <tbody>${d.per_coin.map(c => `
          <tr><td>${esc(c.symbol)}</td><td>${fmtNum(c.closed_trades)}</td><td>${c.win_rate.toFixed(1)}%</td><td>${pnlSpan(c.total_pnl)}</td></tr>
        `).join("") || '<tr><td colspan="4">No closed trades yet.</td></tr>'}</tbody>
      </table></div>
    `;
  }

  // Batch 9, Task 5 (dashboard redesign): replaces the old back-to-back
  // "Per-Strategy Breakdown" table + separate "Strategy Comparison" table
  // (same per-strategy numbers shown twice, in two dense tables) with ONE
  // clearly separated card per strategy -- same underlying data, same
  // View Profile deep-link, just presented so each strategy reads as its
  // own thing instead of one more row in a wall of numbers.
  function strategyBreakdownCardsHtml(list, isAll) {
    const en = getLang() === "en";
    if (!list.length) return `<div class="muted">${en ? "No strategies active in this period." : "Is period mein koi strategy active nahi hai."}</div>`;
    const maxAbsPnl = Math.max(1, ...list.map(p => Math.abs(p.total_pnl)));
    return `<div class="strategy-card-grid">${list.map(p => `
      <div class="card strategy-card">
        <div class="strategy-card-header">
          <b>${esc(p.strategy_name || p.strategy_id)}</b>
          <div class="pt-action-group">
            <button class="btn-ghost pt-strategy-periods" data-id="${esc(p.strategy_id)}" data-name="${esc(p.strategy_name || p.strategy_id)}">${en ? "By Period" : "Period Ke Hisaab Se"}</button>
            <button class="btn-ghost strat-view-profile" data-id="${esc(p.strategy_id)}">${en ? "View Profile" : "Profile Dekhein"}</button>
          </div>
        </div>
        <div class="strategy-card-stats">
          <div><span class="muted">${en ? "Closed Trades" : "Band Trades"}</span><div class="value" style="font-size:17px;">${fmtNum(p.closed_trades)}</div></div>
          <div><span class="muted">${en ? "Win Rate" : "Jeetne Ki Dar"}</span><div class="value" style="font-size:17px;">${p.win_rate.toFixed(1)}%</div></div>
          <div><span class="muted">${en ? "Open" : "Khuli"}</span><div class="value" style="font-size:17px;">${fmtNum(p.open_positions)}</div></div>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:10px;">
          <span class="muted" style="font-size:11px;">${en ? "PnL" : "Munafa/Nuksan"}</span>
          ${pnlSpan(p.total_pnl)}
        </div>
        <div class="progress-bar"><div class="progress-bar-fill" style="width:${Math.abs(p.total_pnl) / maxAbsPnl * 100}%;background:${p.total_pnl >= 0 ? "var(--green)" : "var(--red)"};"></div></div>
        ${isAll ? `<div class="muted" style="font-size:11px;margin-top:8px;">${en ? "Trading since" : "Kab Se Trading"} ${esc((p.trading_since || "-").slice(0, 10))}</div>` : ""}
      </div>`).join("")}</div>`;
  }

  async function loadPaperAnalytics(boxId, idPrefix, period) {
    const box = document.getElementById(boxId);
    if (!box) return;
    box.innerHTML = `<p class="muted">Loading...</p>`;
    // Batch 10, Task 1: both real call sites (Paper Trading, SINDHU CEO)
    // invoke this WITHOUT awaiting it -- a rejected promise here (a real
    // apiGet timeout under load, not hypothetical: reproduced live during
    // Batch 9) used to become an unhandled rejection with nothing left to
    // catch it, so the box stayed on "Loading..." forever with no way to
    // recover short of a full page reload. Caught here, at the source, so
    // it's fixed regardless of how a caller invokes this function.
    let data;
    try {
      data = await apiGet(`/api/paper-trading/analytics?period=${period}`);
    } catch (e) {
      const en = getLang() === "en";
      box.innerHTML = `<p class="muted">${en ? "Couldn't load" : "Load nahi hua"}: ${esc(e.message)}. ` +
        `<button class="btn-ghost" id="${boxId}RetryBtn">${en ? "Retry" : "Dobara Koshish"}</button></p>`;
      const retryBtn = document.getElementById(`${boxId}RetryBtn`);
      if (retryBtn) retryBtn.onclick = () => loadPaperAnalytics(boxId, idPrefix, period);
      return;
    }
    box.innerHTML = paperPeriodTabsHtml(idPrefix, period) + paperAnalyticsSectionHtml(data);
    box.querySelectorAll(`[data-period-tab="${idPrefix}"]`).forEach(btn => {
      btn.onclick = () => loadPaperAnalytics(boxId, idPrefix, btn.dataset.period);
    });
    wireStrategyPeriodDrilldowns(box);
    // Deep-links into that strategy's Profile popup (Balance History /
    // Coin-Wise Performance / Confluence Score Trend) on the Strategies
    // page, instead of leaving the CEO to find the same strategy again.
    box.querySelectorAll(".strat-view-profile").forEach(btn => {
      btn.onclick = () => {
        pendingProfileStrategyId = btn.dataset.id;
        location.hash = "#strategies";
      };
    });
  }

  // Shared sparkline renderer used by both the Backtesting page's live
  // equity chart and the Reports page's equity/drawdown charts -- returns
  // just the inner <line>/<polygon>/<polyline> markup so callers can drop
  // it into an existing <svg> (live chart) or wrap it in a fresh one
  // (static report chart).
  function sparklineInner(series, w, h, pad) {
    if (series.length < 2) return "";
    const min = Math.min(...series, 0), max = Math.max(...series, 0);
    const range = (max - min) || 1;
    const stepX = (w - pad * 2) / (series.length - 1);
    const pts = series.map((v, i) => {
      const x = pad + i * stepX;
      const y = h - pad - ((v - min) / range) * (h - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    const zeroY = (h - pad - ((0 - min) / range) * (h - pad * 2)).toFixed(1);
    const lastX = (pad + (series.length - 1) * stepX).toFixed(1);
    const lineCls = series[series.length - 1] < 0 ? "chart-line negative" : "chart-line";
    return `
      <line class="chart-zero" x1="${pad}" y1="${zeroY}" x2="${w - pad}" y2="${zeroY}"/>
      <polygon class="chart-fill" points="${pad},${zeroY} ${pts.join(" ")} ${lastX},${zeroY}"/>
      <polyline class="${lineCls}" points="${pts.join(" ")}"/>`;
  }

  // Batch 3, Task 3: side-by-side verification view + Incomplete Lock.
  // Left column = the user's own document text (verbatim). Right column =
  // a plain Roman Urdu/Hinglish sentence of what SINDHU actually
  // understood, or a clear "samajh nahi aaya" placeholder. No jargon, no
  // internal identifiers -- the user's task is just to visually compare
  // the two columns.
  function renderExtractionVerificationSection(strategyId, v) {
    // This view was built Urdu-first (Batch 3) -- tu() supplies the
    // English side of the Batch 4 toggle for its static chrome (titles,
    // buttons, table headers, badges). v.summary_text and v.rows'
    // original_text/understood_as are generated server-side in Roman Urdu
    // (ai_integration/extraction_lock.py) and are NOT machine-translated
    // here -- retranslating AI-generated explanatory prose is out of this
    // task's scope (see the Batch 4 Task 4 coverage note), so in English
    // mode this section's title/labels switch but that body text stays
    // Roman Urdu.
    const title = tu("Strategy Samjhi Gayi? (Verification)");
    if (!v) {
      return `<div class="section-title">${title}</div>
        <div class="card"><span class="muted">${tu("Yeh check load nahi ho saka.")}</span></div>`;
    }
    if (!v.has_report) {
      return `
        <div class="section-title">${title}</div>
        <div class="card">
          <div style="margin-bottom:10px;">${esc(v.summary_text)}</div>
          <button class="btn" id="extractionAuditBtn" data-id="${esc(strategyId)}">${tu("Ab Check Karein")}</button>
          <div id="extractionAuditMsg" class="muted" style="margin-top:6px;"></div>
        </div>`;
    }

    const lockBanner = v.locked
      ? `<div class="card" style="border-left:3px solid var(--red, #e5484d); margin-bottom:10px;">
           🔒 <b>${tu("Yeh strategy abhi test nahi ho sakti")}</b> -- ${tu("neeche jo rules \"Samajh Nahi Aaya\" hain, unki wajah se.")}<br>
           <button class="btn" id="extractionOverrideBtn" data-id="${esc(strategyId)}" data-value="true" style="margin-top:8px;">${tu("Phir Bhi Test Karein")}</button>
         </div>`
      : (v.overridden
          ? `<div class="card" style="border-left:3px solid var(--yellow, #e5a944); margin-bottom:10px;">
               ⚠ <b>${tu("Warning")}:</b> ${tu("Yeh strategy adhoori samajh ke saath test ho rahi hai (aapne \"Test Anyway\" dabaya tha) -- iske results poori tarah bharosemand nahi hain.")}<br>
               <button class="btn-ghost" id="extractionOverrideBtn" data-id="${esc(strategyId)}" data-value="false" style="margin-top:8px;">${tu("Lock Wapas Laga Dein")}</button>
             </div>`
          : "");

    const rows = v.rows.map(r => `
      <tr>
        <td style="max-width:320px;">${esc(r.original_text)}</td>
        <td style="max-width:320px;">${esc(r.understood_as || "-")}</td>
        <td>${r.captured ? `<span class="pill pill-bullish">✅ ${tu("Samajh Aaya")}</span>` : `<span class="pill pill-bearish">❌ ${tu("Samajh Nahi Aaya")}</span>`}</td>
      </tr>`).join("");

    return `
      <div class="section-title">${title}</div>
      <div class="card" style="margin-bottom:10px;">
        ${esc(v.summary_text)}
        <div class="muted" style="margin-top:6px;font-size:12px;">${v.captured_count} / ${v.expected_count} ${tu("rules samajh aaye")}${v.retry_count ? ` -- ${v.retry_count} ${tu("dobara koshish ki gayi")}` : ""}</div>
      </div>
      ${lockBanner}
      <div class="table-wrap"><table>
        <thead><tr><th>${tu("Aapne Jo Likha (Original)")}</th><th>${tu("System Ne Kya Samjha")}</th><th>${t("Status")}</th></tr></thead>
        <tbody>${rows || `<tr><td colspan="3">${tu("Is document mein koi rule nahi mila.")}</td></tr>`}</tbody>
      </table></div>
      <div class="btn-row" style="margin-top:10px;">
        <button class="btn-ghost" id="extractionAuditBtn" data-id="${esc(strategyId)}">${tu("Dobara Check Karein")}</button>
        <span id="extractionAuditMsg" class="muted"></span>
      </div>`;
  }

  // Batch 5, Task 2: warns wherever a strategy's paper trading history
  // includes trades from BEFORE a re-extraction fixed its config --
  // those numbers were generated under an incomplete understanding of
  // the rules and must never be silently trusted or blended with the
  // corrected version's own accumulating stats.
  function renderSupersessionWarning(s) {
    if (!s) return "";
    const en = getLang() === "en";
    const pnl = s.corrected_stats.realized_pnl_total;
    return `
      <div class="card" style="border-left:3px solid var(--yellow, #e5a944); margin-bottom:16px;">
        <div style="font-weight:600;margin-bottom:6px;">⚠️ ${en ? "Old Data From Before A Correction" : "Purani Data -- Correction Se Pehle Ki"}</div>
        <div>${en
          ? `This strategy's understanding was corrected on ${esc((s.corrected_at || "").slice(0, 10))} `
            + `(before: ${s.previous_captured_count}/${s.previous_expected_count} rules understood; `
            + `after: ${s.new_captured_count}/${s.new_expected_count}). `
            + `${s.superseded_trade_count} paper trade(s)${s.superseded_signals_sent ? ` and ${s.superseded_signals_sent} Telegram signal(s)` : ""} `
            + `from before this fix were generated under the OLD, incomplete rules -- their results should NOT be trusted.`
          : `Is strategy ki samajh ${esc((s.corrected_at || "").slice(0, 10))} ko theek ki gayi thi `
            + `(pehle: ${s.previous_captured_count}/${s.previous_expected_count} rules samajh aaye the; `
            + `ab: ${s.new_captured_count}/${s.new_expected_count}). `
            + `${s.superseded_trade_count} paper trade(s)${s.superseded_signals_sent ? ` aur ${s.superseded_signals_sent} Telegram signal(s)` : ""} `
            + `is fix se pehle ki, PURANI adhoori samajh se bani thi -- inpar bharosa NA karein.`}
        </div>
        <div class="muted" style="margin-top:8px;font-size:12px;">
          ${en
            ? `Corrected-version stats only (V${s.corrected_at_version} onward): ${s.corrected_stats.closed_count} trades, `
              + `${pnl >= 0 ? "+" : ""}$${pnl.toFixed(2)} realized PnL. Nothing was deleted -- the older trades stay in Trade History for audit.`
            : `Sirf corrected version ki stats (V${s.corrected_at_version} se aage): ${s.corrected_stats.closed_count} trades, `
              + `${pnl >= 0 ? "+" : ""}$${pnl.toFixed(2)} asli PnL. Kuch delete nahi hua -- purani trades Trade History mein audit ke liye maujood hain.`}
        </div>
      </div>`;
  }

  function sparklineSvg(series) {
    if (series.length < 2) return `<div class="muted">Not enough trades for a chart.</div>`;
    return `<svg viewBox="0 0 400 160" preserveAspectRatio="none">${sparklineInner(series, 400, 160, 6)}</svg>`;
  }

  // Coin-Wise Performance -- Visual Chart (Remaining Dashboard
  // Enhancements, item 2): a plain horizontal bar chart alongside the
  // existing table, one bar per coin, positive/negative colored, for
  // faster visual comparison than scanning a PnL column.
  function barChartSvg(items, labelFn, valueFn, maxBars = 15) {
    const rows = items.slice(0, maxBars);
    if (!rows.length) return `<div class="muted">No data yet.</div>`;
    const values = rows.map(valueFn);
    const maxAbs = Math.max(...values.map(v => Math.abs(v)), 0.0001);
    const rowH = 22, w = 400, labelW = 90, chartW = w - labelW - 10;
    const midX = labelW + chartW / 2;
    const bars = rows.map((r, i) => {
      const v = values[i];
      const barW = (Math.abs(v) / maxAbs) * (chartW / 2);
      const x = v >= 0 ? midX : midX - barW;
      const y = i * rowH + 3;
      const fillColor = v >= 0 ? "var(--green)" : "var(--red)";
      return `
        <text x="0" y="${y + 12}" style="font-size:10.5px;fill:var(--text-dim);stroke:none;">${esc(String(labelFn(r)).slice(0, 12))}</text>
        <rect x="${x.toFixed(1)}" y="${y}" width="${barW.toFixed(1)}" height="14" rx="2" style="fill:${fillColor};stroke:none;opacity:0.85;"/>
        <text x="${(v >= 0 ? x + barW + 4 : x - 4)}" y="${y + 11}" style="font-size:10px;fill:var(--text-faint);stroke:none;" text-anchor="${v >= 0 ? "start" : "end"}">${v.toFixed(2)}</text>`;
    }).join("");
    const h = rows.length * rowH + 6;
    return `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}">
      <line x1="${midX}" y1="0" x2="${midX}" y2="${h}" style="stroke:var(--border);stroke-width:1;"/>
      ${bars}
    </svg>`;
  }

  // ------------------------------------------------------------ shared Original vs Optimized comparison
  // Single component used by both the Backtest History page and the
  // SINDHU CEO Backtesting card, backed by the single shared endpoint
  // /api/backtest-history/{batch_id}/comparison -- per the standing rule
  // that SINDHU CEO must never show data that could conflict with the
  // dedicated page it mirrors. Works whether `batchId` is the original or
  // the optimized side of the pair.
  function comparisonBoxHtml(data) {
    if (!data || !data.has_optimization) {
      return `<div class="card muted">Not optimized -- original strategy only, no comparison available.</div>`;
    }
    const { winner, why, original, optimized, params_changed, candidates_tried } = data;
    const winnerIsOptimized = winner === "optimized";
    const rows = [
      ["Total PnL", original && original.total_pnl, optimized && optimized.total_pnl],
      ["Win Rate", original && `${original.win_rate}%`, optimized && `${optimized.win_rate}%`],
      ["Max Drawdown", original && `${original.max_drawdown_pct}%`, optimized && `${optimized.max_drawdown_pct}%`],
      ["Total Trades", original && original.total_trades, optimized && optimized.total_trades],
    ];
    return `
      <div class="card">
        <div style="font-weight:700;margin-bottom:6px;">Original vs Optimized</div>
        <p class="muted" style="margin:0 0 10px;">Winner: <b class="${winnerIsOptimized ? 'positive' : ''}">${winnerIsOptimized ? "Optimized" : "Original"}</b>
          ${why ? ` -- ${esc(why)}` : ""}
          <span class="muted"> (${candidates_tried} combination${candidates_tried === 1 ? "" : "s"} tried${params_changed && params_changed.length ? ": " + esc(params_changed.map(p => p.description).join(", ")) : ""})</span></p>
        <div class="table-wrap"><table>
          <thead><tr><th>Metric</th><th${!winnerIsOptimized ? ' style="font-weight:700;"' : ''}>Original</th><th${winnerIsOptimized ? ' style="font-weight:700;"' : ''}>Optimized${optimized ? "" : " (none beat original)"}</th></tr></thead>
          <tbody>
            ${rows.map(([label, o, n]) => `<tr><td>${label}</td><td${!winnerIsOptimized ? ' style="font-weight:700;"' : ''}>${o != null ? o : "-"}</td><td${winnerIsOptimized ? ' style="font-weight:700;"' : ''}>${n != null ? n : "-"}</td></tr>`).join("")}
          </tbody>
        </table></div>
      </div>`;
  }

  async function loadComparisonBox(container, batchId) {
    if (!container) return;
    container.innerHTML = `<div class="muted">Loading comparison...</div>`;
    try {
      const data = await apiGet(`/api/backtest-history/${batchId}/comparison`);
      container.innerHTML = comparisonBoxHtml(data);
    } catch (e) {
      container.innerHTML = `<div class="card muted">Could not load comparison: ${esc(e.message)}</div>`;
    }
  }

  // ------------------------------------------------------------ shared Automation Pipeline run journey
  // One shared renderer for the Automation Pipeline History page and the
  // SINDHU CEO Pipeline History card (CEO-parity rule) -- both backed by
  // GET /api/automation/pipeline-history[/:job_id], which reads directly
  // from the same pipeline_jobs table used by crash-recovery resume, not a
  // separate tracking system.
  function pipelineStatusBadge(run) {
    const map = { completed: "pill-completed", failed: "pill-error", stopped: "pill-muted", running: "pill-running" };
    const cls = map[run.status] || "pill-neutral";
    const label = run.status === "running" ? `Running -- ${run.stage}`
      : run.status === "failed" ? `Failed at ${run.stage}`
      : run.status === "stopped" ? `Stopped at ${run.stage}`
      : run.status === "completed" ? "Completed" : run.status;
    return `<span class="pill ${cls}">${esc(label)}</span>`;
  }

  function pipelineJourneyHtml(job) {
    const cp = job.checkpoint || {};
    const stages = [];

    stages.push({
      name: "1. Import / Strategy",
      body: `<div>Strategy: <b>${esc(job.strategy_name || job.strategy_id)}</b></div>
             <div class="muted" style="font-size:12px;">${job.symbols ? fmtNum(job.symbols.length) + " coin(s)" : "full coin universe"} -- started ${esc((job.created_at || "").slice(0, 19))}</div>`,
    });

    if (cp.original_summary) {
      const s = cp.original_summary;
      stages.push({
        name: "2. Backtest",
        body: `<div>${fmtNum(s.total_trades)} trades, ${s.win_rate}% win rate, total PnL ${s.total_pnl}</div>
               ${cp.original_batch_id ? `<button class="btn-ghost pipeline-view-batch" data-batch="${esc(cp.original_batch_id)}">View full backtest in Backtest History</button>` : ""}`,
      });
    } else {
      stages.push({ name: "2. Backtest", body: `<div class="muted">Not reached yet.</div>` });
    }

    if (cp.optimizer_done) {
      const os = cp.optimized_summary;
      stages.push({
        name: "3. Optimizer",
        body: `<div>${fmtNum(Array.isArray(cp.tried) ? cp.tried.length : (cp.tried || 0))} combination(s) tried${cp.best_desc ? ` -- best found: ${esc(cp.best_desc)}` : ""}</div>
               ${os ? `<div>Full re-test of the best candidate: ${fmtNum(os.total_trades)} trades, ${os.win_rate}% win rate, total PnL ${os.total_pnl}</div>` : ""}
               ${cp.winner ? `<div>Winner: <b class="${cp.winner === "optimized" ? "positive" : ""}">${cp.winner === "optimized" ? "Optimized" : "Original"}</b></div>` : ""}
               <div id="pipelineCompareBox-${esc(job.job_id)}" style="margin-top:8px;"></div>`,
      });
    } else {
      stages.push({ name: "3. Optimizer", body: `<div class="muted">Not reached yet.</div>` });
    }

    stages.push({
      name: "4. Paper Trading Handoff",
      body: cp.paper_trading_attempted
        ? `<div>Handoff attempted -- see the Paper Trading page for '${esc(job.strategy_name || job.strategy_id)}''s current live status (multiple strategies can run there simultaneously).</div>`
        : `<div class="muted">Not reached yet.</div>`,
    });

    if (job.error) {
      stages.push({ name: "Error", body: `<div class="negative">${esc(job.error)}</div>` });
    }

    return stages.map(s => `<div class="card" style="margin-bottom:8px;"><div style="font-weight:700;margin-bottom:4px;">${esc(s.name)}</div>${s.body}</div>`).join("");
  }

  async function loadPipelineRunDetail(container, jobId) {
    if (!container) return;
    container.innerHTML = `<p class="muted">Loading...</p>`;
    try {
      const job = await apiGet(`/api/automation/pipeline-history/${jobId}`);
      container.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
          <div style="font-weight:700;font-size:15px;">${esc(job.strategy_name || job.strategy_id)}</div>
          ${pipelineStatusBadge(job)}
        </div>
        ${pipelineJourneyHtml(job)}`;
      const cp = job.checkpoint || {};
      if (cp.optimizer_done && cp.original_batch_id) {
        const box = document.getElementById(`pipelineCompareBox-${job.job_id}`);
        loadComparisonBox(box, cp.original_batch_id).catch(console.error);
      }
      container.querySelectorAll(".pipeline-view-batch").forEach(btn => {
        btn.onclick = () => { pendingHistoryBatchId = btn.dataset.batch; location.hash = "#backtest_history"; };
      });
    } catch (e) {
      container.innerHTML = `<div class="card muted">Could not load run detail: ${esc(e.message)}</div>`;
    }
  }

  // ------------------------------------------------------------ shared 0-trade condition-hit diagnosis
  // Part 2 (auto-surfaced 0-trade diagnosis): single component used by both
  // Backtest History and the SINDHU CEO Backtesting card, backed by the
  // single shared endpoint /api/reports/{batch_id}/condition-reports --
  // same CEO-parity rule as the comparison box above. Requires no extra
  // clicks: rendered directly wherever a batch is shown, not tucked behind
  // an expandable section.
  function zeroTradeBoxHtml(data) {
    const reports = (data && data.reports) || [];
    if (!reports.length) return "";
    return `
      <div class="card" style="background:var(--yellow-dim);border-left:3px solid var(--yellow);">
        <div style="font-weight:700;margin-bottom:6px;">${reports.length} coin${reports.length === 1 ? "" : "s"} produced 0 trades</div>
        ${reports.map(r => `<p style="margin:4px 0;"><b>${esc(r.symbol)}</b>: ${esc(r.diagnosis || "No diagnosis available.")}</p>`).join("")}
      </div>`;
  }

  async function loadZeroTradeBox(container, batchId) {
    if (!container) return;
    container.innerHTML = "";
    try {
      const data = await apiGet(`/api/reports/${batchId}/condition-reports`);
      container.innerHTML = zeroTradeBoxHtml(data);
    } catch (e) {
      container.innerHTML = "";
    }
  }

  // ------------------------------------------------------------ MARKET
  async function renderMarket() {
    const myToken = activeRouteToken;
    const settings = await apiGet("/api/settings").catch(() => ({ refresh_speed_seconds: 10 }));
    const regimeCls = { trending: "pill-bullish", ranging: "pill-neutral", high_volatility: "pill-bearish" };
    const regimeLabel = { trending: "Trending", ranging: "Ranging", high_volatility: "High Volatility" };
    const render = async () => {
      const filterEl = document.getElementById("marketRegimeFilter");
      const filterValue = filterEl ? filterEl.value : "all";
      const [m, regimeRes] = await Promise.all([
        apiGet("/api/market"),
        apiGet("/api/paper-trading/regime").catch(() => ({ regimes: {} })),
      ]);
      if (isStaleRoute(myToken)) return;
      const regimes = regimeRes.regimes || {};
      const signalCls = s => s === "Bullish" ? "pill-bullish" : s === "Bearish" ? "pill-bearish" : "pill-neutral";
      const coins = filterValue === "all" ? m.coins : m.coins.filter(c => (regimes[c.symbol] || {}).regime === filterValue);
      const rows = coins.map(c => {
        const r = regimes[c.symbol];
        return `
        <tr>
          <td>${esc(c.symbol)}</td>
          <td>${c.price}</td>
          <td class="${c.change_pct >= 0 ? 'pill-up' : 'pill-down'}">${c.change_pct.toFixed(2)}%</td>
          <td>${fmtNum(Math.round(c.volume))}</td>
          <td><span class="pill ${c.trend === 'up' ? 'pill-up' : 'pill-down'}">${c.trend}</span></td>
          <td><span class="pill ${signalCls(c.signal)}">${esc(c.signal || "-")}</span></td>
          <td>${c.volatility_pct != null ? c.volatility_pct + "%" : "-"}</td>
          <td>${r ? `<span class="pill ${regimeCls[r.regime] || 'pill-neutral'}">${regimeLabel[r.regime] || esc(r.regime)}</span>` : `<span class="muted">-</span>`}</td>
        </tr>`;
      }).join("");
      content.innerHTML = `
        <div class="section-title">Market (${esc(m.exchange)} / ${esc(m.quote)})</div>
        <div class="btn-row">
          <span class="muted" style="display:flex;align-items:center;gap:6px;">
            <label for="marketRegimeFilter">Market Condition</label>${helpIcon("market_regime")}:
            <select id="marketRegimeFilter" style="width:auto;">
              <option value="all" ${filterValue === "all" ? "selected" : ""}>All</option>
              <option value="trending" ${filterValue === "trending" ? "selected" : ""}>Trending</option>
              <option value="ranging" ${filterValue === "ranging" ? "selected" : ""}>Ranging</option>
              <option value="high_volatility" ${filterValue === "high_volatility" ? "selected" : ""}>High Volatility</option>
            </select>
          </span>
        </div>
        <div class="table-wrap"><table>
          <thead><tr><th>Coin</th><th>Price</th><th>24H Change</th><th>Volume</th><th>Trend</th><th>Signal</th><th>Volatility</th><th>Market Condition ${helpIcon("market_regime")}</th></tr></thead>
          <tbody>${rows || '<tr><td colspan="8">No market data</td></tr>'}</tbody>
        </table></div>`;
      document.getElementById("marketRegimeFilter").addEventListener("change", render);
    };
    await render();
    autoRefresh(render, Math.max(settings.refresh_speed_seconds || 10, 15));
  }

  // ------------------------------------------------------------ DATA
  async function renderData() {
    const myToken = activeRouteToken;
    const render = async () => {
      const [d, dq] = await Promise.all([
        apiGet("/api/data"),
        apiGet("/api/data/quality").catch(() => null),
      ]);
      if (isStaleRoute(myToken)) return;
      const rows = d.coins.map(c => `
        <tr>
          <td>${esc(c.symbol)}</td>
          <td>${fmtNum(c.candles)}</td>
          <td><span class="pill pill-${c.status}">${esc(c.status)}</span></td>
        </tr>`).join("");
      content.innerHTML = `
        <div class="section-title">Data</div>
        <div class="grid">
          ${card("Downloaded Coins", fmtNum(d.total_coins))}
          ${card("Database Size", fmtBytes(d.database_size_bytes))}
          ${card("Missing Data", d.missing_data.length ? d.missing_data.join(", ") : "None")}
          ${dq && dq.overall_score != null ? cardClass("Data Quality (separate from strategy performance)", `${dq.overall_score}/100`, dq.overall_score >= 90 ? "positive" : dq.overall_score >= 70 ? "" : "negative") : dq && dq.warming_up ? cardClass("Data Quality (separate from strategy performance)", "Warming up...", "") : ""}
        </div>
        ${dq && dq.symbols_with_issues ? `
        <div class="section-title">Data Quality Issues (${dq.symbols_with_issues} coin(s))</div>
        <div class="card">${dq.per_symbol.filter(s => s.issues.length).map(s => `
          <div style="padding:4px 0;"><b>${esc(s.symbol)}</b> (score ${s.score}/100): ${esc(s.issues.join("; "))}</div>`).join("")}
        </div>` : ""}
        <div class="btn-row"><button class="btn" id="btnDownload">Start / Resume Download</button></div>
        <div class="section-title">Available Timeframes</div>
        <div class="card">${d.timeframes.join(", ")}</div>
        <div class="section-title">Per-Coin Detail</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Coin</th><th>Candles</th><th>Status</th></tr></thead>
          <tbody>${rows}</tbody>
        </table></div>`;
      document.getElementById("btnDownload").onclick = async () => {
        await apiPost("/api/data/download");
        appendLog("Download job started from Data page.");
      };
    };
    await render();
    autoRefresh(render, 15);
  }

  // ------------------------------------------------------------ STRATEGIES
  function strategyStatusPill(status) {
    const cls = status === "READY_FOR_BACKTEST" ? "pill-completed" : "pill-pending";
    const label = status === "READY_FOR_BACKTEST" ? "Ready"
      : status === "NEEDS_REVIEW" ? "Needs Review" : "Needs Clarification";
    return `<span class="pill ${cls}">${esc(label)}</span>`;
  }

  // Batch 3, Task 3: at-a-glance Incomplete Lock indicator on the
  // strategies table, no jargon -- full explanation lives in Profile.
  function extractionLockBadge(s) {
    if (s.extraction_locked) return `<br><span class="pill pill-bearish" style="margin-top:4px;">🔒 Locked</span>`;
    if (s.extraction_overridden) return `<br><span class="pill" style="margin-top:4px;background:var(--yellow,#e5a944);">⚠ Adhoori Test</span>`;
    return "";
  }

  // Strategy Performance Dashboard: a single GREEN/RED read at a glance,
  // combining expectancy/profit-factor/trade-count/Walk-Forward into one
  // verdict (backtest_engine/performance_dashboard.py computes this --
  // display-only here, never blocks or hides a strategy either way).
  function performanceBadge(verdict, label, failedFactors) {
    if (!verdict) return "";
    const cls = verdict === "GREEN" ? "pill-completed" : "pill-error";
    const title = verdict === "RED" && failedFactors && failedFactors.length
      ? esc(failedFactors.join(" | ")) : "";
    return `<span class="pill ${cls}" title="${title}">${verdict === "GREEN" ? "🟢" : "🔴"} ${esc(label || verdict)}</span>`;
  }

  function lastBacktestCell(r) {
    if (!r) return `<span class="muted">Never run</span>`;
    if (r.status !== "completed") return `<span class="pill pill-pending">${esc(r.status)}</span>`;
    const pnlCls = r.avg_profit_pct > 0 ? "positive" : r.avg_profit_pct < 0 ? "negative" : "";
    return `${fmtNum(r.total_trades)} trades, ${r.win_rate}% win, <span class="${pnlCls}">${r.avg_profit_pct}%</span>`;
  }

  // Basic visibility for which declared timeframe (bias/trend/analysis/
  // entry) each concept condition actually reads from -- without this the
  // "Timeframes" column looks like every declared role is in play, when in
  // practice a condition with no role set only ever reads the entry
  // timeframe. "entry" is shown plainly (not flagged) since it's the
  // correct value for a genuinely entry-scoped concept (e.g. a 1-minute
  // candle_break trigger), not just an unset default.
  function conditionRolesCell(roles) {
    if (!roles || !roles.length) return `<span class="muted">-</span>`;
    return roles.map(r =>
      `<span class="pill pill-muted" title="${esc(r.bucket)}">${esc(r.name)}${r.direction ? " (" + esc(r.direction) + ")" : ""} -> ${esc(r.role)}</span>`
    ).join(" ");
  }

  async function renderStrategies() {
    const myToken = activeRouteToken;
    const render = async () => {
      const searchEl = document.getElementById("stratLibSearch");
      const q = searchEl ? searchEl.value : "";
      const showArchivedEl = document.getElementById("stratShowArchived");
      const showArchived = showArchivedEl ? showArchivedEl.checked : false;
      const [res, riskRes, retirementRes] = await Promise.all([
        apiGet(`/api/backtesting/strategies?q=${encodeURIComponent(q)}&include_archived=${showArchived}`).catch(() => ({ strategies: [] })),
        apiGet("/api/paper-trading/risk-metrics-all").catch(() => ({ metrics: {} })),
        apiGet("/api/paper-trading/retirement-suggestions").catch(() => ({ suggestions: [] })),
      ]);
      if (isStaleRoute(myToken)) return;
      const riskMetrics = riskRes.metrics || {};
      // Basic Risk Analytics (Sharpe Ratio / Max Drawdown %): computed from
      // this strategy's own live Paper Trading trade history, not the
      // backtest -- shows "-" until a strategy has at least 2 closed paper
      // trades (see paper_trading.insights.compute_risk_metrics).
      function riskCell(sid) {
        const r = riskMetrics[sid];
        if (!r || r.sharpe_ratio == null) return `<span class="muted" title="Needs at least 2 closed Paper Trading trades">Not enough data</span>`;
        const ddCls = r.max_drawdown_pct > 15 ? "negative" : "";
        return `Sharpe ${r.sharpe_ratio.toFixed(2)}, Max DD <span class="${ddCls}">${r.max_drawdown_pct.toFixed(1)}%</span>`;
      }
      const rows = res.strategies.map(s => `
        <tr${s.archived ? ' style="opacity:0.55;"' : ""}>
          <td>${s.favourite ? "★" : "☆"}</td>
          <td>${esc(s.name)} ${s.archived ? '<span class="pill pill-muted">Archived</span>' : ""} ${performanceBadge(s.performance_verdict, s.performance_label, s.performance_failed_factors)}
            <div style="font-size:11px;margin-top:2px;">
              ${(s.tags || []).map(tag => `<span class="pill pill-muted" style="margin-right:3px;">${esc(tag)}</span>`).join("")}
              <button class="btn-ghost strat-edit-tags" data-id="${s.id}" data-tags="${esc((s.tags || []).join(", "))}" title="Edit tags" style="padding:0 4px;font-size:11px;">🏷</button>
              <button class="btn-ghost strat-edit-comment" data-id="${s.id}" data-comment="${esc(s.ceo_comment || "")}" title="${esc(s.ceo_comment || "Add a note")}" style="padding:0 4px;font-size:11px;">${s.ceo_comment ? "📝" : "🗒"}</button>
            </div>
            <div class="muted" style="font-size:10px;">Last changed: ${s.updated_at ? esc(s.updated_at.slice(0, 16).replace("T", " ")) : "-"}</div>
          </td>
          <td>${(s.concepts_used || []).join(", ") || "-"}</td>
          <td>${Object.entries(s.timeframes || {}).map(([role, tf]) => `${role}:${tf}`).join(", ") || "-"}</td>
          <td>${conditionRolesCell(s.condition_roles)}</td>
          <td>${strategyStatusPill(s.status)}${extractionLockBadge(s)}</td>
          <td>${lastBacktestCell(s.last_batch_result)}</td>
          <td>${riskCell(s.id)}</td>
          <td>V${s.current_version || 1} <button class="btn-ghost strat-versions" data-id="${s.id}" data-name="${esc(s.name)}">History</button></td>
          <td>
            ${s.archived ? `<button class="btn-ghost strat-unarchive" data-id="${s.id}" data-name="${esc(s.name)}">${t("Restore")}</button>` : `
            <button class="btn-ghost strat-profile" data-id="${s.id}" data-name="${esc(s.name)}">${t("Profile")}</button>
            <button class="btn-ghost strat-claim-check" data-id="${s.id}" data-name="${esc(s.name)}">${t("Claim Check")}</button>
            <button class="btn-ghost strat-edit" data-id="${s.id}">${t("Edit")}</button>
            ${s.status !== "READY_FOR_BACKTEST" ? `<button class="btn-ghost strat-clarify" data-id="${s.id}" data-name="${esc(s.name)}">Clarify</button>` : ""}
            <button class="btn-ghost strat-fav" data-id="${s.id}" data-fav="${s.favourite}">${s.favourite ? "★" : "☆"}</button>
            <button class="btn-ghost strat-dup" data-id="${s.id}">${t("Duplicate")}</button>
            <button class="btn-ghost strat-del" data-id="${s.id}" data-name="${esc(s.name)}">${t("Delete")}</button>
            `}
          </td>
        </tr>`).join("");

      content.innerHTML = `
        <div class="section-title">${t("Strategies")}</div>
        ${(retirementRes.suggestions || []).length ? `
        <div class="card" style="border:1px solid var(--orange,#d68910);background:rgba(214,137,16,0.08);margin-bottom:10px;">
          <div style="font-weight:600;">Retirement Suggestions ${helpIcon("retirement_suggestion")}</div>
          ${retirementRes.suggestions.map(s => `
            <div style="padding:4px 0;border-top:1px solid var(--border,#333);font-size:13px;display:flex;justify-content:space-between;align-items:center;gap:8px;">
              <span><b>${esc(s.strategy_name)}</b> -- ${esc(s.reason)}</span>
              <button class="btn-ghost retirement-archive" data-id="${s.strategy_id}" data-name="${esc(s.strategy_name)}">Archive</button>
            </div>`).join("")}
        </div>` : ""}
        <div class="btn-row">
          <input id="stratLibSearch" placeholder="${t("Search strategies...")}" style="max-width:280px;" value="${esc(q)}">
          <button class="btn" id="btnNewStrategy">${t("New Strategy")}</button>
          <label style="display:flex;align-items:center;gap:6px;width:auto;">
            <input type="checkbox" id="stratShowArchived" ${showArchived ? "checked" : ""} style="width:auto;"> ${t("Show Archived")}
          </label>
        </div>
        <div class="table-wrap"><table>
          <thead><tr><th></th><th>${t("Name")}</th><th>${t("Concepts")}</th><th>${t("Timeframes")}</th><th>${t("Condition Roles")}</th><th>${t("Status")}</th><th>${t("Last Backtest")}</th><th>Live Risk (Sharpe ${helpIcon("sharpe_ratio")} / Max DD ${helpIcon("max_drawdown")})</th><th>${t("Version")}</th><th></th></tr></thead>
          <tbody>${rows || '<tr><td colspan="10">No saved strategies yet -- create one on the Backtesting page.</td></tr>'}</tbody>
        </table></div>
        <div id="versionHistoryBox" style="display:none;">
          <div class="section-title" id="versionHistoryTitle">Version History</div>
          <div class="table-wrap"><table>
            <thead><tr><th>Version</th><th>Modified</th><th>Reason</th><th></th></tr></thead>
            <tbody id="versionHistoryBody"></tbody>
          </table></div>
          <div id="versionDiffBox" style="display:none;margin-top:8px;"></div>
        </div>
        <div id="claimCheckBox" class="card" style="display:none;"></div>
        <div id="clarifyBox" style="display:none;">
          <div class="section-title" id="clarifyTitle">Clarification Needed</div>
          <div id="clarifyBody"></div>
        </div>
        <div id="strategyProfileBox" style="display:none;">
          <div class="section-title" style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;">
            <span id="strategyProfileTitle">${t("Profile")}</span>
            <button class="btn-ghost" id="strategyProfileCompareLink" style="font-size:12px;">${t("View on Compare page")} &rarr;</button>
          </div>
          <div id="strategyProfileBody"></div>
        </div>

        <div class="section-title">${t("Duplicate Strategies")}</div>
        <div id="duplicatesBox" class="card"><span class="muted">Checking for duplicates...</span></div>

        <div class="section-title">${t("Strategy Graveyard")}</div>
        <div id="graveyardBox" class="card"><span class="muted">Loading...</span></div>`;

    (async () => {
      const g = await apiGet("/api/paper-trading/graveyard").catch(() => ({ graveyard: [] }));
      const box = document.getElementById("graveyardBox");
      if (!box) return;
      box.innerHTML = g.graveyard.length
        ? g.graveyard.map(x => `<div style="padding:6px 0;border-bottom:1px solid var(--border,#333);">
            <b>${esc(x.strategy_name)}</b> -- retired ${esc((x.buried_at||"").slice(0,10))}<br>
            <span class="muted">${esc(x.reason_detail)}</span></div>`).join("")
        : `<span class="muted">No strategies retired yet.</span>`;
    })();

    (async () => {
      // Batch 4, Task 3: same DNA-fingerprint detection already used at
      // import time (knowledge_compiler.quality.strategy_dna), surfaced
      // as a grouped, actionable view. Loaded into its own box so it
      // never blocks the main Strategies table from rendering.
      const d = await apiGet("/api/backtesting/duplicates").catch(() => ({ groups: [] }));
      const box = document.getElementById("duplicatesBox");
      if (!box) return;
      if (!d.groups.length) {
        box.innerHTML = `<span class="muted">${getLang() === "en" ? "No duplicate strategies found." : "Koi duplicate strategy nahi mili."}</span>`;
        return;
      }
      const en = getLang() === "en";
      const backtestSummary = r => !r ? (en ? "Never tested" : "Kabhi test nahi hua")
        : r.status !== "completed" ? (en ? "Test still running" : "Test abhi chal raha hai")
        : `${r.total_trades || 0} trades, ${r.win_rate != null ? r.win_rate + "%" : "-"} win rate`;
      box.innerHTML = d.groups.map((g, gi) => `
        <div style="padding:10px 0;border-bottom:1px solid var(--border,#333);">
          <div class="muted" style="font-size:12px;margin-bottom:6px;">${en
            ? `Duplicate group ${gi + 1} -- these ${g.strategies.length} strategies have the same rules`
            : `Duplicate group ${gi + 1} -- yeh ${g.strategies.length} strategies same rules ke saath hain`}</div>
          <table><thead><tr><th>${t("Name")}</th><th>${en ? "Imported" : "Import Hua"}</th><th>${en ? "Rules Captured" : "Rules Capture Hue"}</th><th>${t("Last Backtest")}</th><th></th></tr></thead>
          <tbody>
          ${g.strategies.map(s => `
            <tr>
              <td>${esc(s.name)}</td>
              <td>${esc((s.imported_at || "").slice(0, 10))}</td>
              <td>${s.rule_count}</td>
              <td>${esc(backtestSummary(s.last_batch_result))}</td>
              <td><button class="btn-ghost dup-archive" data-id="${s.id}" data-name="${esc(s.name)}">${en ? "Archive" : "Archive Karein"}</button></td>
            </tr>`).join("")}
          </tbody></table>
        </div>`).join("");
      document.querySelectorAll(".dup-archive").forEach(btn => btn.onclick = async () => {
        const confirmMsg = getLang() === "en"
          ? `Archive "${btn.dataset.name}"?\n\n` +
            `- It will disappear from the list, but will NOT be permanently deleted -- it can be restored any time.\n` +
            `- All its backtest history and data stays safe.\n` +
            `- If this is the last active copy of its group, the system will not allow archiving it.`
          : `"${btn.dataset.name}" ko archive karna hai?\n\n` +
            `- Yeh strategy list se hat jayegi, lekin PERMANENTLY delete NAHI hogi -- kabhi bhi wapas la sakte hain.\n` +
            `- Iski saari backtest history aur data safe rahega.\n` +
            `- Agar yeh group ki aakhri active copy hai to system yeh archive nahi karne dega.`;
        if (!confirm(confirmMsg)) return;
        try {
          await apiPost(`/api/backtesting/strategies/${btn.dataset.id}/archive`, { confirm: true });
          render();
        } catch (e) {
          alert(e.message || (getLang() === "en" ? "Could not archive." : "Archive nahi ho saka."));
        }
      });
    })();

      document.getElementById("stratLibSearch").addEventListener("input", debounce(render, 300));
      document.getElementById("btnNewStrategy").onclick = () => { showImportChoiceModal(); };
      document.getElementById("stratShowArchived").addEventListener("change", render);
      document.querySelectorAll(".retirement-archive").forEach(btn => btn.onclick = async () => {
        // Grand Feature Expansion, Phase 4 Feature 4: reuses the EXACT
        // same reversible archive endpoint the row-level Archive action
        // uses -- this suggestion never has its own separate action.
        if (!confirm(`Archive "${btn.dataset.name}"? It will disappear from the active list but can be restored any time -- nothing is deleted.`)) return;
        try {
          await apiPost(`/api/backtesting/strategies/${btn.dataset.id}/archive`, { confirm: true });
          appendLog(`Archived "${btn.dataset.name}" (retirement suggestion accepted).`);
          render();
        } catch (e) {
          alert(e.message || "Could not archive.");
        }
      });
      document.querySelectorAll(".strat-unarchive").forEach(btn => btn.onclick = async () => {
        await apiPost(`/api/backtesting/strategies/${btn.dataset.id}/unarchive`, {});
        appendLog(`Restored "${btn.dataset.name}" from archive.`);
        render();
      });

      document.querySelectorAll(".strat-edit").forEach(btn => btn.onclick = () => {
        pendingStrategyLoadId = btn.dataset.id;
        location.hash = "#backtesting";
      });
      document.querySelectorAll(".strat-fav").forEach(btn => btn.onclick = async () => {
        await apiPost(`/api/backtesting/strategies/${btn.dataset.id}/favourite?favourite=${btn.dataset.fav === "true" ? "false" : "true"}`);
        render();
      });
      document.querySelectorAll(".strat-edit-tags").forEach(btn => btn.onclick = async () => {
        const input = prompt("Tags (comma-separated):", btn.dataset.tags || "");
        if (input === null) return;
        const tags = input.split(",").map(t => t.trim()).filter(Boolean);
        await apiPost(`/api/backtesting/strategies/${btn.dataset.id}/tags`, { tags });
        render();
      });
      document.querySelectorAll(".strat-edit-comment").forEach(btn => btn.onclick = async () => {
        const comment = prompt("Note about this strategy:", btn.dataset.comment || "");
        if (comment === null) return;
        await apiPost(`/api/backtesting/strategies/${btn.dataset.id}/comment`, { comment });
        render();
      });
      document.querySelectorAll(".strat-dup").forEach(btn => btn.onclick = async () => {
        await apiPost(`/api/backtesting/strategies/${btn.dataset.id}/duplicate`, {});
        render();
      });
      document.querySelectorAll(".strat-del").forEach(btn => btn.onclick = async () => {
        if (!confirm(`Delete strategy "${btn.dataset.name}"? This cannot be undone.`)) return;
        await apiSend("DELETE", `/api/backtesting/strategies/${btn.dataset.id}`);
        render();
      });
      document.querySelectorAll(".strat-profile").forEach(btn => btn.onclick = async () => {
        const box = document.getElementById("strategyProfileBox");
        const body = document.getElementById("strategyProfileBody");
        document.getElementById("strategyProfileTitle").textContent = `Strategy Profile -- ${btn.dataset.name}`;
        document.getElementById("strategyProfileCompareLink").onclick = () => {
          sessionStorage.setItem("compareHighlightStrategy", btn.dataset.name);
          location.hash = "#compare";
        };
        body.innerHTML = `<p class="muted">Loading everything known about this strategy...</p>`;
        box.style.display = "block";
        box.scrollIntoView({ behavior: "smooth", block: "start" });
        try {
          const [p, balHistRes, coinStatsRes, confHistRes, verification] = await Promise.all([
            apiGet(`/api/paper-trading/strategy-profile/${btn.dataset.id}`),
            apiGet(`/api/paper-trading/balance-history/${btn.dataset.id}`).catch(() => ({ points: [] })),
            apiGet(`/api/paper-trading/coin-stats/${btn.dataset.id}`).catch(() => ({ coins: [] })),
            apiGet(`/api/paper-trading/confluence-history/${btn.dataset.id}`).catch(() => ({ history: [] })),
            apiGet(`/api/backtesting/strategies/${btn.dataset.id}/extraction-verification?lang=${getLang()}`).catch(() => null),
          ]);
          const readiness = p.real_trading_readiness;
          const balSeries = (balHistRes.points || []).map(pt => pt.balance);
          const coinRows = coinStatsRes.coins || [];
          const confSeries = (confHistRes.history || []).map(h => h.confluence_ratio * 100);
          body.innerHTML = `
            ${renderExtractionVerificationSection(btn.dataset.id, verification)}
            ${renderSupersessionWarning(p.supersession)}

            <div class="grid">
              ${card(`Confidence Score ${helpIcon("confidence_score")}`, p.confidence_score != null ? p.confidence_score : "No data yet")}
              ${card("Current Streak", p.streak ? `${p.streak.count} ${p.streak.type}${p.streak.count !== 1 ? "es" : ""}` : "-")}
              ${p.risk_metrics.sharpe_ratio != null ? card(`Sharpe ${helpIcon("sharpe_ratio")} / Max DD ${helpIcon("max_drawdown")}`, `${p.risk_metrics.sharpe_ratio.toFixed(2)} / ${p.risk_metrics.max_drawdown_pct.toFixed(1)}%`) : card("Sharpe / Max DD", "Not enough data")}
              ${p.risk_metrics.sortino_ratio != null ? card(`Sortino ${helpIcon("sortino_ratio")}`, p.risk_metrics.sortino_ratio.toFixed(2)) : card(`Sortino ${helpIcon("sortino_ratio")}`, "Not enough data")}
              ${p.value_at_risk.var_amount != null ? card(`Value at Risk (95%) ${helpIcon("value_at_risk")}`, `$${p.value_at_risk.var_amount.toFixed(2)}`) : card(`Value at Risk ${helpIcon("value_at_risk")}`, `Needs ${p.value_at_risk.min_sample_size}+ closed trades`)}
              ${(() => {
                // Grand Feature Expansion, Phase 4 Feature 11: Health Badge
                // -- a plain stable/unproven/archived LABEL, distinct from
                // the 3 existing badges elsewhere (READY/NEEDS_REVIEW status,
                // GREEN/RED performance, Archived pill) and from the raw
                // Health Score number itself, computed client-side from data
                // already on this page (no new backend call).
                const hs = p.health_score.health_score;
                const badge = p.archived ? { label: "Archived", cls: "" }
                  : hs == null ? { label: "Unproven -- no closed trades yet", cls: "" }
                  : hs >= 70 ? { label: "Stable", cls: "positive" }
                  : hs >= 40 ? { label: "Unproven", cls: "" }
                  : { label: "Weak", cls: "negative" };
                return cardClass(`Health Badge ${helpIcon("health_badge")}`, badge.label, badge.cls);
              })()}
              ${p.health_score.health_score != null ? cardClass(`Health Score ${helpIcon("health_score")}`, `${p.health_score.health_score}/100`, p.health_score.health_score >= 70 ? "positive" : p.health_score.health_score >= 40 ? "" : "negative") : card(`Health Score ${helpIcon("health_score")}`, "No closed trades yet")}
              ${p.aging.trend != null ? cardClass(`Aging Trend ${helpIcon("strategy_aging")}`, p.aging.trend === "improving" ? "Improving" : p.aging.trend === "weakening" ? "Weakening" : "Stable", p.aging.trend === "improving" ? "positive" : p.aging.trend === "weakening" ? "negative" : "") : card(`Aging Trend ${helpIcon("strategy_aging")}`, p.aging.reason || "Not enough data")}
              ${cardClass("Drawdown Protection", p.paused ? "Paused" : "Active", p.paused ? "negative" : "positive")}
              ${card("Backtest Verdict", p.backtest_verdict || "-")}
              ${card("Walk-Forward", p.walk_forward_status || "not yet run")}
            </div>
            ${p.paused ? `<div class="card" style="margin-bottom:16px;"><b>Why paused:</b> ${esc(p.pause_reason)}</div>` : ""}

            ${(p.aging.windows || []).length ? `
            <div class="section-title">Performance Over Time (${p.aging.window_size}-trade windows) ${helpIcon("strategy_aging")}</div>
            <div class="table-wrap"><table>
              <thead><tr><th>Window</th><th>Trades</th><th>Win Rate</th><th>PnL</th></tr></thead>
              <tbody>${p.aging.windows.map(w => `
                <tr><td>#${w.window_index + 1}</td><td>${w.trade_count}</td><td>${w.win_rate_pct.toFixed(1)}%</td>
                <td class="${w.total_pnl >= 0 ? "pill-up" : "pill-down"}">${w.total_pnl.toFixed(2)}</td></tr>`).join("")}</tbody>
            </table></div>` : ""}

            ${p.mae_mfe.sample_size > 0 ? `
            <div class="section-title">Max Adverse/Favorable Excursion ${helpIcon("mae_mfe")}</div>
            <div class="grid">
              ${p.mae_mfe.winners ? card("Winners -- Avg Worst Dip Before Working Out", `$${p.mae_mfe.winners.avg_mae.toFixed(2)} (${p.mae_mfe.winners.count} trades)`) : ""}
              ${p.mae_mfe.losers ? card("Losers -- Avg Best Point Before Reversing", `$${p.mae_mfe.losers.avg_mfe.toFixed(2)} (${p.mae_mfe.losers.count} trades)`) : ""}
            </div>` : ""}

            <div class="section-title">Balance History (Fake Money)</div>
            <div class="card">${sparklineSvg(balSeries)}</div>

            <div class="section-title">Coin-Wise Performance</div>
            <div class="two-col">
              <div class="table-wrap"><table>
                <thead><tr><th>Coin</th><th>Trades</th><th>Win Rate</th><th>Total PnL</th></tr></thead>
                <tbody>${coinRows.map(c => `
                  <tr><td>${esc(c.symbol)}</td><td>${c.closed_trades}</td><td>${c.win_rate}%</td>
                  <td class="${c.total_pnl >= 0 ? "pill-up" : "pill-down"}">${c.total_pnl.toFixed(2)}</td></tr>`).join("")
                  || '<tr><td colspan="4">No closed trades yet.</td></tr>'}</tbody>
              </table></div>
              <div class="card">${barChartSvg(coinRows, c => c.symbol, c => c.total_pnl)}</div>
            </div>

            <div class="section-title">Confluence Score Trend ${helpIcon("confluence_score")}</div>
            <div class="card">${sparklineSvg(confSeries)}
              <div class="muted" style="font-size:11px;margin-top:4px;">${confSeries.length} signal(s) logged${confSeries.length ? ` -- most recent: ${confSeries[confSeries.length - 1].toFixed(0)}%` : ""}</div>
            </div>

            <div class="section-title">Coins Currently Traded &amp; Their Market Condition ${helpIcon("market_regime")}</div>
            <div class="card">${Object.keys(p.traded_coin_regimes).length
              ? Object.entries(p.traded_coin_regimes).map(([sym, r]) => `<span class="pill pill-neutral" style="margin:2px;">${esc(sym)}: ${esc(r)}</span>`).join("")
              : `<span class="muted">No open positions right now.</span>`}</div>

            ${p.correlation_warnings.length ? `
            <div class="section-title">Correlation Warnings Involving This Strategy ${helpIcon("correlation_warning")}</div>
            <div class="card">${p.correlation_warnings.map(w => `<div style="padding:4px 0;">${esc(w.message)}</div>`).join("")}</div>` : ""}

            ${p.auto_avoid_rules.length ? `
            <div class="section-title">Active Pattern Auto-Avoid Rules</div>
            <div class="card">${p.auto_avoid_rules.map(r => `<div style="padding:4px 0;">${esc(r.reason)}</div>`).join("")}</div>` : ""}

            ${p.auto_lessons.length ? `
            <div class="section-title">Auto-Applied Lessons</div>
            <div class="card">${p.auto_lessons.map(l => `<div style="padding:4px 0;">${esc(l.explanation)}</div>`).join("")}</div>` : ""}

            ${p.lesson_candidates.length ? `
            <div class="section-title">Lesson Candidates Awaiting Review</div>
            <div class="card">${p.lesson_candidates.map(c => `<div style="padding:4px 0;">${esc(c.pattern_description)}</div>`).join("")}</div>` : ""}

            <div class="section-title">Real-Trading Readiness Checklist</div>
            <div class="card">${readiness.checklist.map(c => `<div style="padding:4px 0;">${c.passed ? "✅" : "❌"} ${esc(c.label)} <span class="muted">(${esc(c.detail)})</span></div>`).join("")}
              <div style="margin-top:8px;"><b>${readiness.ready_for_real_trading ? "✅ Ready for real-trading consideration" : "❌ Not ready yet"}</b></div>
            </div>

            <div class="section-title">Version History</div>
            <div class="card">${p.genealogy.map(v => `<div>V${v.version} -- ${esc((v.modified_at || "").slice(0,19))}</div>`).join("") || `<span class="muted">No history.</span>`}</div>`;

          const auditBtn = document.getElementById("extractionAuditBtn");
          if (auditBtn) auditBtn.onclick = async () => {
            const msg = document.getElementById("extractionAuditMsg");
            auditBtn.disabled = true;
            msg.textContent = getLang() === "en" ? "Checking... this will take a moment." : "Check ho raha hai... thoda time lagega.";
            try {
              await apiPost(`/api/backtesting/strategies/${auditBtn.dataset.id}/extraction-audit?lang=${getLang()}`, {});
              btn.click();  // re-open the profile to show the fresh result
            } catch (e) {
              msg.textContent = (getLang() === "en" ? "Check failed: " : "Check nahi ho saka: ") + e.message;
              auditBtn.disabled = false;
            }
          };
          const overrideBtn = document.getElementById("extractionOverrideBtn");
          if (overrideBtn) overrideBtn.onclick = async () => {
            const goingTo = overrideBtn.dataset.value === "true";
            const confirmMsg = getLang() === "en"
              ? "Do you want to test with an incomplete understanding? Results will always show a warning."
              : "Aap adhoori samajh ke saath test karna chahte hain? Results par hamesha warning dikhegi.";
            if (goingTo && !confirm(confirmMsg)) return;
            await apiPost(`/api/backtesting/strategies/${overrideBtn.dataset.id}/extraction-override?lang=${getLang()}`, { overridden: goingTo });
            btn.click();
          };
        } catch (e) {
          body.innerHTML = `<p class="muted">Could not load profile: ${esc(e.message)}</p>`;
        }
      });

      document.querySelectorAll(".strat-versions").forEach(btn => btn.onclick = async () => {
        const strategyId = btn.dataset.id;
        const v = await apiGet(`/api/backtesting/strategies/${strategyId}/versions`).catch(() => ({ versions: [] }));
        document.getElementById("versionHistoryTitle").textContent = `Version History -- ${btn.dataset.name}`;
        const versions = v.versions || [];
        const currentVersion = versions.length ? Math.max(...versions.map(ver => ver.version)) : null;
        const en = getLang() === "en";
        // Item 6: shows WHY each version was saved (never fabricated -- null
        // for versions saved before this existed), and a "vs previous"
        // diff button for every version after the first.
        // Grand Feature Expansion, Phase 4 Feature 22: Undo/Rollback -- a
        // Restore button on every non-current version, reusing this same
        // history view rather than a separate page.
        document.getElementById("versionHistoryBody").innerHTML = versions.slice().reverse().map(ver => `
          <tr>
            <td>V${ver.version}${ver.version === currentVersion ? ` <span class="pill pill-muted">${en ? "Current" : "Current"}</span>` : ""}</td>
            <td>${esc((ver.modified_at || "").slice(0, 19))}</td>
            <td class="muted">${esc(ver.reason || "--")}</td>
            <td>
              ${ver.version > 1 ? `<button class="btn btn-ghost btn-version-diff" data-id="${esc(strategyId)}" data-a="${ver.version - 1}" data-b="${ver.version}">Compare to V${ver.version - 1}</button>` : ""}
              ${ver.version !== currentVersion ? `<button class="btn btn-ghost btn-version-restore" data-id="${esc(strategyId)}" data-version="${ver.version}" data-name="${esc(btn.dataset.name)}">${en ? "Restore" : "Restore Karein"}</button>` : ""}
            </td>
          </tr>
        `).join("") || '<tr><td colspan="4">No version history</td></tr>';

        document.querySelectorAll(".btn-version-restore").forEach(rbtn => rbtn.onclick = async () => {
          const confirmMsg = en
            ? `Restore "${rbtn.dataset.name}" to V${rbtn.dataset.version}? This creates a NEW version copied from V${rbtn.dataset.version} -- nothing is deleted, and you can restore back to the current version the same way afterwards.`
            : `"${rbtn.dataset.name}" ko V${rbtn.dataset.version} par restore karna hai? Yeh V${rbtn.dataset.version} se copy ki gayi ek NAYI version banata hai -- kuch bhi delete nahi hota, aur baad mein isi tarah wapas current version par bhi restore kar sakte hain.`;
          if (!confirm(confirmMsg)) return;
          try {
            await apiPost(`/api/backtesting/strategies/${rbtn.dataset.id}/restore-version`, { version: parseInt(rbtn.dataset.version, 10) });
            appendLog(`Restored "${rbtn.dataset.name}" to V${rbtn.dataset.version} (saved as a new version).`);
            btn.click(); // Re-open the version history so it reflects the newly created version.
          } catch (e) {
            alert(e.message || (en ? "Could not restore." : "Restore nahi ho saka."));
          }
        });
        document.getElementById("versionHistoryBox").style.display = "block";
        document.getElementById("versionDiffBox").style.display = "none";
        document.getElementById("versionHistoryBox").scrollIntoView({ behavior: "smooth", block: "nearest" });

        document.querySelectorAll(".btn-version-diff").forEach(dbtn => dbtn.onclick = async () => {
          const diffBox = document.getElementById("versionDiffBox");
          diffBox.style.display = "block";
          diffBox.innerHTML = "Loading diff...";
          const d = await apiGet(`/api/backtesting/strategies/${dbtn.dataset.id}/versions/${dbtn.dataset.a}/diff/${dbtn.dataset.b}`).catch(() => ({ changes: [] }));
          diffBox.innerHTML = `
            <div class="section-title">V${dbtn.dataset.a} vs V${dbtn.dataset.b}</div>
            ${(d.changes || []).length ? `<div class="table-wrap"><table>
              <thead><tr><th>Field</th><th>Before</th><th>After</th></tr></thead>
              <tbody>${d.changes.map(c => `
                <tr><td>${esc(c.label)}</td>
                  <td class="muted" style="max-width:260px;word-break:break-word;">${esc(JSON.stringify(c.before))}</td>
                  <td style="max-width:260px;word-break:break-word;">${esc(JSON.stringify(c.after))}</td>
                </tr>`).join("")}</tbody>
            </table></div>` : '<p class="muted">No differences.</p>'}`;
        });
      });
      document.querySelectorAll(".strat-clarify").forEach(btn => btn.onclick = () => {
        openClarifyBox(btn.dataset.id, btn.dataset.name, render);
      });
      document.querySelectorAll(".strat-claim-check").forEach(btn => btn.onclick = async () => {
        // Item 7 (Cross-Reference Validation): compares the source
        // document's own performance claim against SINDHU's real, measured
        // backtest result -- never trusting the document's number blindly.
        const box = document.getElementById("claimCheckBox");
        box.style.display = "block";
        box.innerHTML = "Loading...";
        const r = await apiGet(`/api/backtesting/strategies/${btn.dataset.id}/claim-check`).catch(() => ({ has_claim: false }));
        box.innerHTML = claimCheckHtml(btn.dataset.name, r);
        box.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });

      if (pendingProfileStrategyId) {
        const id = pendingProfileStrategyId;
        pendingProfileStrategyId = null;
        const btn = document.querySelector(`.strat-profile[data-id="${CSS.escape(id)}"]`);
        if (btn) btn.click();
      }
    };
    await render();
    onLive((msg) => { if (msg.channel === "sync" && msg.entity === "strategy") render().catch(console.error); });
  }

  // Part 1: the clarification flow. issueControlHtml() renders the right
  // control per issue "kind" (free-text redescribe, a small set of
  // suggested options, or a reject button) -- see
  // sindhu_web/api/clarification.py::build_issues() for the shape.
  function issueControlHtml(issue) {
    const en = getLang() === "en";
    const reasonBlock = `
      <div><b>${esc(issue.reason)}</b></div>
      ${issue.detail ? `<div class="muted" style="margin-top:2px;">${esc(issue.detail)}</div>` : ""}
      ${issue.ai_reason ? `<div class="muted" style="margin-top:4px;">AI's own note: "${esc(issue.ai_reason)}"${issue.ai_confidence != null ? ` (${Math.round(issue.ai_confidence * 100)}% confidence)` : ""}</div>` : ""}`;

    if (issue.kind === "raw_condition" || issue.kind === "missing_conditions") {
      // A short, plain Roman Urdu question -- the actual "reason"/"detail"
      // strings above stay in English (they come straight from the
      // backend's validator/AI reasoning, useful detail for anyone who
      // wants it), but the ACTUAL QUESTION the CEO has to answer is framed
      // simply here, with a one-click suggested default (defer to Manual
      // Review, never guessed/never silently dropped) plus the free-text
      // alternative.
      const question = issue.original_text
        ? (en
            ? `This rule wasn't understood: "${issue.original_text}". What should happen to it?`
            : `Yeh rule samajh nahi aaya: "${issue.original_text}". Ab kya karein?`)
        : (en
            ? "No rule was found here at all. What should happen?"
            : "Yahan koi rule mila hi nahi. Ab kya karein?");
      const canDefault = issue.kind === "raw_condition";  // needs a specific rule's text -- a brand-new "missing" issue has nothing to defer
      return `
        <div class="card" data-issue-id="${esc(issue.id)}" data-issue-kind="${issue.kind}">
          ${reasonBlock}
          <div style="margin-top:8px;"><b>${question}</b></div>
          <div class="btn-row" style="margin-top:8px;">
            ${canDefault ? `<button class="btn issue-mark-manual">${en ? "Skip for now (Manual Review)" : "Filhaal chodo (Manual Review)"}</button>` : ""}
            ${issue.can_reject ? `<button class="btn btn-ghost issue-apply-reject">${en ? "Remove this rule" : "Yeh rule hata dein"}</button>` : ""}
          </div>
          <div class="form-row" style="margin-top:8px;"><label>${en ? "Or describe it yourself" : "Ya main khud batata hoon"}</label>
            <input class="issue-text-input" placeholder="${en ? "e.g. RSI 14 below 30, or close above EMA50" : "misaal: RSI 14, 30 se neeche"}">
          </div>
          <div class="btn-row">
            <button class="btn btn-ghost issue-apply-edit">${en ? "Try this instead" : "Yeh try karein"}</button>
          </div>
        </div>`;
    }
    if (issue.kind === "invalid_indicator") {
      const options = (issue.suggested_options || []).map(o =>
        `<button class="btn btn-ghost issue-pick-indicator" data-value="${esc(o.value)}">${esc(o.label)}</button>`).join("");
      return `
        <div class="card" data-issue-id="${esc(issue.id)}" data-issue-kind="${issue.kind}">
          ${reasonBlock}
          ${options ? `<div class="btn-row" style="margin-top:8px;">${options}</div>` : ""}
          <div class="form-row" style="margin-top:8px;"><label>${en ? "Or describe the whole rule yourself" : "Ya poora rule khud batayein"}</label>
            <input class="issue-text-input" placeholder="e.g. RSI 14 below 30">
          </div>
          <div class="btn-row">
            <button class="btn btn-ghost issue-apply-edit">${en ? "Try this instead" : "Yeh try karein"}</button>
            ${issue.can_reject ? `<button class="btn btn-ghost issue-apply-reject">${en ? "Remove this rule" : "Yeh rule hata dein"}</button>` : ""}
          </div>
        </div>`;
    }
    if (issue.kind === "missing_field") {
      const options = (issue.suggested_options || []).map(o =>
        `<button class="btn btn-ghost issue-pick-field" data-value='${esc(JSON.stringify(o.value))}'>${esc(o.label)}</button>`).join("");
      return `
        <div class="card" data-issue-id="${esc(issue.id)}" data-issue-kind="${issue.kind}">
          ${reasonBlock}
          <div class="btn-row" style="margin-top:8px;">${options}</div>
        </div>`;
    }
    return `<div class="card" data-issue-id="${esc(issue.id)}">${reasonBlock}</div>`;
  }

  async function openClarifyBox(strategyId, name, refreshList) {
    const en = getLang() === "en";
    const box = document.getElementById("clarifyBox");
    const body = document.getElementById("clarifyBody");
    document.getElementById("clarifyTitle").textContent = en ? `Clarification Needed -- ${name}` : `Saaf Karna Hai -- ${name}`;
    body.innerHTML = `<div class="muted">${en ? "Loading..." : "Load ho raha hai..."}</div>`;
    box.style.display = "block";
    box.scrollIntoView({ behavior: "smooth", block: "nearest" });

    async function load() {
      const data = await apiGet(`/api/backtesting/strategies/${strategyId}/clarification`).catch(() => null);
      if (!data) { body.innerHTML = `<div class="muted">${en ? "Could not load clarification details." : "Details load nahi ho sakin."}</div>`; return; }
      if (data.status === "READY_FOR_BACKTEST") {
        body.innerHTML = `<div class="card"><span class="pill pill-completed">${en ? "Ready for Backtesting" : "Backtest Ke Liye Tayyar"}</span> ${en ? "Nothing left to clarify -- this strategy is fully executable." : "Kuch bhi saaf karna baaki nahi -- yeh strategy poori tarah chalne ke liye tayyar hai."}</div>`;
        return;
      }
      const confidenceNote = data.confidence_pct != null
        ? `<div class="muted" style="margin-bottom:8px;">${en ? "AI import confidence" : "AI import ka confidence"}: ${data.confidence_pct}%</div>` : "";
      body.innerHTML = `
        ${confidenceNote}
        ${data.issues.map(issueControlHtml).join("")}
        <div class="btn-row" style="margin-top:10px;">
          <button class="btn" id="btnApplyClarifications">${en ? "Apply Changes" : "Changes Lagayein"}</button>
          <button class="btn btn-ghost" id="btnCloseClarify">${en ? "Close" : "Band Karein"}</button>
          <span id="clarifyStatus" class="muted"></span>
        </div>`;
      wireIssueCards();
    }

    function wireIssueCards() {
      const pending = new Map();  // issue id -> resolution payload

      body.querySelectorAll(".issue-apply-edit").forEach(btn => btn.onclick = () => {
        const card = btn.closest("[data-issue-id]");
        const text = card.querySelector(".issue-text-input").value;
        if (!text || !text.trim()) { alert(en ? "Type a replacement description first." : "Pehle apni description likhein."); return; }
        pending.set(card.dataset.issueId, { id: card.dataset.issueId, action: "edit", text });
        btn.textContent = en ? "Queued ✓" : "Queue Ho Gaya ✓";
      });
      body.querySelectorAll(".issue-apply-reject").forEach(btn => btn.onclick = () => {
        const card = btn.closest("[data-issue-id]");
        pending.set(card.dataset.issueId, { id: card.dataset.issueId, action: "reject" });
        btn.textContent = en ? "Queued ✓" : "Queue Ho Gaya ✓";
      });
      body.querySelectorAll(".issue-mark-manual").forEach(btn => btn.onclick = () => {
        const card = btn.closest("[data-issue-id]");
        pending.set(card.dataset.issueId, { id: card.dataset.issueId, action: "mark_manual_review" });
        btn.textContent = en ? "Queued ✓" : "Queue Ho Gaya ✓";
        btn.classList.add("btn-active");
      });
      body.querySelectorAll(".issue-pick-indicator").forEach(btn => btn.onclick = () => {
        const card = btn.closest("[data-issue-id]");
        pending.set(card.dataset.issueId, { id: card.dataset.issueId, action: "replace_indicator", value: btn.dataset.value });
        card.querySelectorAll(".issue-pick-indicator").forEach(b => b.classList.remove("btn-active"));
        btn.classList.add("btn-active");
      });
      body.querySelectorAll(".issue-pick-field").forEach(btn => btn.onclick = () => {
        const card = btn.closest("[data-issue-id]");
        pending.set(card.dataset.issueId, { id: card.dataset.issueId, action: "set_field", value: JSON.parse(btn.dataset.value) });
        card.querySelectorAll(".issue-pick-field").forEach(b => b.classList.remove("btn-active"));
        btn.classList.add("btn-active");
      });

      document.getElementById("btnCloseClarify").onclick = () => { box.style.display = "none"; };
      document.getElementById("btnApplyClarifications").onclick = async () => {
        if (!pending.size) { alert(en ? "Pick or type at least one resolution first." : "Pehle kam se kam ek jawab chunein ya likhein."); return; }
        const status = document.getElementById("clarifyStatus");
        status.textContent = en ? "Applying..." : "Lagaya ja raha hai...";
        try {
          const result = await apiPost(`/api/backtesting/strategies/${strategyId}/clarify`, {
            resolutions: Array.from(pending.values()),
          });
          const failedNote = result.failed.length
            ? ` ${result.failed.length} ${en ? "still unresolved" : "abhi bhi baaki"}: ${result.failed.map(f => esc(f.detail)).join(" | ")}`
            : "";
          if (result.status === "READY_FOR_BACKTEST") {
            status.textContent = (en
              ? "Resolved -- strategy is now Ready for Backtesting."
              : "Saaf ho gaya -- strategy ab Backtest ke liye tayyar hai.") +
              (result.pipeline_job_id ? (en ? " Automation pipeline started automatically." : " Automation pipeline khud shuru ho gayi.") : "");
          } else {
            status.textContent = en
              ? `Applied ${result.applied.length} change(s).${failedNote}`
              : `${result.applied.length} change(s) lag gaye.${failedNote}`;
          }
          if (refreshList) refreshList();
          await load();
        } catch (e) {
          status.textContent = `Failed: ${e.message}`;
        }
      };
    }

    await load();
  }

  // ------------------------------------------------------------ CLARIFICATION CENTER
  // Step 3, Part B: the dedicated Clarification Page. Ten required
  // features: (1) progress counter, (2) one-click suggested answers,
  // (3) "answer later" skip, (4) a concrete example per question, (5) all
  // strategies' pending questions grouped in one list, (6) an "(i)"
  // tooltip explaining WHY the system is asking, (7) a mandatory
  // confirm-back echo before any free-text answer is saved, (8) editing a
  // previously-given answer, (9) a "this matters because..." hint, (10) a
  // final Read Mode summary of the whole strategy in plain Roman Urdu
  // before the real "Haan, ab backtest karo" confirmation. Reuses the
  // same /clarify and /clarification endpoints openClarifyBox above uses
  // -- this is a full page around the same safe, deterministic backend,
  // not a parallel/duplicate resolution path.
  const clarState = { skipped: new Set() };

  async function renderClarificationCenter() {
    const en = getLang() === "en";
    content.innerHTML = `
      <div class="page-header"><h2>${en ? "Clarification Center" : "Clarification Center"}</h2>
        <div class="muted">${en
          ? "Resolve every strategy's unclear items here -- one question at a time, or read the whole strategy back before confirming."
          : "Har strategy ke unclear sawaalon ko yahan resolve karein -- ek-ek karke, ya poori strategy wapas parh kar confirm karein."}</div>
      </div>
      <div id="clarProgressWrap" class="card"></div>
      <div id="clarGroups"></div>`;

    async function load() {
      const data = await apiGet("/api/backtesting/clarification/all").catch(() => ({ groups: [], total_issues: 0, strategy_count: 0 }));
      renderProgress(data);
      renderGroups(data.groups);
    }

    function renderProgress(data) {
      const wrap = document.getElementById("clarProgressWrap");
      const skippedCount = clarState.skipped.size;
      const remaining = Math.max(0, data.total_issues - skippedCount);
      const total = Math.max(1, data.total_issues);
      const answeredThisView = Math.max(0, total - remaining);
      const pct = Math.round((answeredThisView / total) * 100);
      if (!data.total_issues) {
        wrap.innerHTML = `<span class="pill pill-completed">${en ? "All clear" : "Sab saaf hai"}</span> ${en
          ? "No strategy currently needs clarification."
          : "Abhi koi strategy clarification ke liye nahi ruki hui."}`;
        return;
      }
      wrap.innerHTML = `
        <div><b>${remaining}</b> ${en ? "of" : "mein se"} <b>${data.total_issues}</b> ${en ? "questions remaining" : "sawaal baaki"}
          ${skippedCount ? `<span class="muted">(${skippedCount} ${en ? "skipped this session" : "is session mein chode gaye"})</span>` : ""}
          ${en ? "across" : ""} <b>${data.strategy_count}</b> ${en ? "strategies" : "strategies mein"}</div>
        <div style="height:8px;border-radius:4px;background:var(--border,#333);margin-top:6px;overflow:hidden;">
          <div style="height:100%;width:${pct}%;background:var(--accent,#4caf82);"></div>
        </div>`;
    }

    function renderGroups(groups) {
      const wrapEl = document.getElementById("clarGroups");
      if (!groups.length) { wrapEl.innerHTML = ""; return; }
      wrapEl.innerHTML = groups.map(g => `
        <div class="card" data-strategy-id="${esc(g.strategy_id)}" style="margin-top:12px;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <div><b>${esc(g.name)}</b> <span class="muted">(${g.issue_count} ${en ? "question(s)" : "sawaal"})</span></div>
            <div class="btn-row">
              <button class="btn btn-ghost btn-readmode" data-strategy-id="${esc(g.strategy_id)}" data-name="${esc(g.name)}">
                ${en ? "Read Mode" : "Read Mode Mein Dekhein"}</button>
              ${reextractFieldControlHtml(g.strategy_id, en)}
            </div>
          </div>
          ${ambiguityOverviewHtml(g.ambiguity_overview, en)}
          <div class="answer-log-wrap" data-strategy-id="${esc(g.strategy_id)}"></div>
          <div class="issue-list" style="margin-top:8px;">
            ${g.issues.filter(i => !clarState.skipped.has(i.id)).map(i => clarIssueCardHtml(g.strategy_id, i)).join("")
              || `<div class="muted">${en ? "All questions skipped this session -- reload to see them again." : "Is session mein sab sawaal chode gaye -- dobara dekhne ke liye reload karein."}</div>`}
          </div>
        </div>`).join("");

      groups.forEach(g => loadAnswerLog(g.strategy_id));
      wireGroupEvents(load);
    }

    async function loadAnswerLog(strategyId) {
      const data = await apiGet(`/api/backtesting/strategies/${strategyId}/clarification`).catch(() => null);
      if (!data || !data.answer_log || !data.answer_log.length) return;
      const el = content.querySelector(`.answer-log-wrap[data-strategy-id="${CSS.escape(strategyId)}"]`);
      if (!el) return;
      // Feature 8: previously-given answers, with a Reopen action for the
      // most common one-click default (Manual Review) so it can genuinely
      // be re-answered, not just viewed.
      el.innerHTML = `<details style="margin-top:6px;"><summary class="muted">${en ? "Previous answers" : "Pichle jawab"} (${data.answer_log.length})</summary>
        ${data.answer_log.map(a => `
          <div style="padding:4px 0;border-top:1px solid var(--border,#333);">
            <span class="muted">${new Date(a.at).toLocaleString()}:</span> ${esc(a.detail)}
            ${a.action === "mark_manual_review" ? `<button class="btn btn-ghost btn-reopen-answer" data-strategy-id="${esc(strategyId)}" data-issue-id="${esc(a.id)}">${en ? "Reopen" : "Dobara Kholein"}</button>` : ""}
          </div>`).join("")}
      </details>`;
      el.querySelectorAll(".btn-reopen-answer").forEach(btn => btn.onclick = async () => {
        await apiPost(`/api/backtesting/strategies/${btn.dataset.strategyId}/clarify`, {
          resolutions: [{ id: btn.dataset.issueId, action: "unmark_manual_review" }],
        }).catch(() => null);
        await load();
      });
    }

    function wireGroupEvents(reload) {
      // Feature 3: "Answer later" -- purely a local/session skip, the
      // question is never sent to the backend so it's never blocked or
      // lost, just hidden from view until reload.
      content.querySelectorAll(".btn-skip-issue").forEach(btn => btn.onclick = () => {
        clarState.skipped.add(btn.dataset.issueId);
        reload();
      });

      // Feature 2: one-click suggested answers (Manual Review default for
      // an unmapped rule, or a specific suggested_options value).
      content.querySelectorAll(".btn-suggest-manual").forEach(btn => btn.onclick = async () => {
        await applyResolution(btn.dataset.strategyId, { id: btn.dataset.issueId, action: "mark_manual_review" }, reload);
      });
      content.querySelectorAll(".btn-suggest-option").forEach(btn => btn.onclick = async () => {
        const action = btn.dataset.action;
        const value = btn.dataset.value ? JSON.parse(btn.dataset.value) : undefined;
        await applyResolution(btn.dataset.strategyId, { id: btn.dataset.issueId, action, value }, reload);
      });
      content.querySelectorAll(".btn-reject-issue").forEach(btn => btn.onclick = async () => {
        await applyResolution(btn.dataset.strategyId, { id: btn.dataset.issueId, action: "reject" }, reload);
      });

      // Feature 7 (CRITICAL SAFETY FEATURE): typed free text is NEVER sent
      // straight to /clarify. It first goes to /clarify/preview (read-only,
      // mutates nothing), the interpretation is echoed back, and only an
      // explicit second click on "Haan, yeh sahi hai" actually saves it.
      content.querySelectorAll(".btn-preview-text").forEach(btn => btn.onclick = async () => {
        // .card[data-issue-id], not the bare attribute selector: the button
        // itself also carries data-issue-id (for its own wiring), so
        // .closest("[data-issue-id]") alone would match the button itself
        // (closest() checks the starting element first) instead of walking
        // up to the actual card that holds the sibling input/preview box.
        const card = btn.closest(".card[data-issue-id]");
        const input = card.querySelector(".clar-text-input");
        const text = input.value.trim();
        const previewBox = card.querySelector(".clar-preview-box");
        if (!text) { previewBox.textContent = en ? "Type something first." : "Pehle kuch likhein."; return; }
        const preview = await apiPost(
          `/api/backtesting/strategies/${btn.dataset.strategyId}/clarify/preview`,
          { id: btn.dataset.issueId, text },
        ).catch(e => ({ understood_as: null, still_unclear: true, error: e.message }));
        if (!preview.understood_as) {
          previewBox.innerHTML = `<div class="muted">${en
            ? "Still couldn't understand this -- try rephrasing."
            : "Abhi bhi samajh nahi aaya -- dobara likhne ki koshish karein."}</div>`;
          return;
        }
        previewBox.innerHTML = `
          <div style="margin-top:6px;padding:8px;border:1px solid var(--border,#333);border-radius:6px;">
            <div>${en ? "Here's how I understood this:" : "Maine ise aise samjha:"} <b>${esc(preview.understood_as)}</b></div>
            <div class="muted" style="margin-top:2px;">${en ? "Is this correct?" : "Kya ye sahi hai?"}</div>
            <div class="btn-row" style="margin-top:6px;">
              <button class="btn btn-confirm-text" data-strategy-id="${btn.dataset.strategyId}" data-issue-id="${btn.dataset.issueId}">${en ? "Yes, correct" : "Haan, yeh sahi hai"}</button>
              <button class="btn btn-ghost btn-retype-text">${en ? "No, let me retype" : "Nahi, dobara likhna hai"}</button>
            </div>
          </div>`;
        previewBox.querySelector(".btn-confirm-text").onclick = async () => {
          await applyResolution(btn.dataset.strategyId, { id: btn.dataset.issueId, action: "edit", text }, reload);
        };
        previewBox.querySelector(".btn-retype-text").onclick = () => { previewBox.innerHTML = ""; input.focus(); };
      });

      content.querySelectorAll(".btn-readmode").forEach(btn => btn.onclick = () => {
        openReadMode(btn.dataset.strategyId, btn.dataset.name, reload);
      });

      content.querySelectorAll(".btn-reextract-field").forEach(btn => btn.onclick = async () => {
        const strategyId = btn.dataset.strategyId;
        const select = content.querySelector(`.reextract-field-select[data-strategy-id="${CSS.escape(strategyId)}"]`);
        const statusEl = content.querySelector(`.reextract-status[data-strategy-id="${CSS.escape(strategyId)}"]`);
        statusEl.textContent = en ? "Re-extracting..." : "Dobara nikal rahe hain...";
        const result = await apiPost(`/api/backtesting/strategies/${strategyId}/reextract-field`, { field: select.value })
          .catch(e => ({ success: false, note: e.message }));
        statusEl.textContent = result.success
          ? (en ? `Done -- other fields untouched.` : `Ho gaya -- baaki fields waise hi hain.`)
          : `${en ? "Failed:" : "Nahi hua:"} ${result.note || ""}`;
        if (result.success) await reload();
      });
    }

    async function applyResolution(strategyId, resolution, reload) {
      const result = await apiPost(`/api/backtesting/strategies/${strategyId}/clarify`, { resolutions: [resolution] }).catch(e => null);
      if (result) await reload();
    }

    await load();
  }

  const REEXTRACT_FIELDS = [
    { value: "entry_conditions", en: "Entry Conditions", ur: "Entry Conditions" },
    { value: "exit_conditions", en: "Exit Conditions", ur: "Exit Conditions" },
    { value: "stop_loss", en: "Stop-Loss", ur: "Stop-Loss" },
    { value: "take_profit", en: "Take-Profit", ur: "Take-Profit" },
  ];

  function reextractFieldControlHtml(strategyId, en) {
    // Item 5 (Partial Re-Extraction): redo ONE field from the strategy's
    // own original source text -- much cheaper/faster than re-importing
    // the whole document, and every other field stays untouched.
    return `
      <select class="reextract-field-select" data-strategy-id="${esc(strategyId)}" style="max-width:160px;">
        ${REEXTRACT_FIELDS.map(f => `<option value="${f.value}">${en ? f.en : f.ur}</option>`).join("")}
      </select>
      <button class="btn btn-ghost btn-reextract-field" data-strategy-id="${esc(strategyId)}">
        ${en ? "Re-extract this field" : "Yeh field dobara nikalein"}</button>
      <span class="muted reextract-status" data-strategy-id="${esc(strategyId)}"></span>`;
  }

  function claimCheckHtml(name, r) {
    // Item 7 (Cross-Reference Validation).
    if (!r || !r.has_claim) {
      return `<div class="section-title">Claim Check -- ${esc(name)}</div><p class="muted">This strategy's source document made no performance claim to check.</p>`;
    }
    if (!r.has_result) {
      return `<div class="section-title">Claim Check -- ${esc(name)}</div>
        <p>Source document claims a <b>${r.claimed_win_rate_pct}%</b> win rate${r.claim_source_text ? ` ("${esc(r.claim_source_text)}")` : ""}.</p>
        <p class="muted">No completed real backtest yet -- nothing to compare it against.</p>`;
    }
    const badge = r.diverges
      ? `<span class="pill pill-error">Diverges from real result${r.sample_reliable ? "" : " (small sample)"}</span>`
      : `<span class="pill pill-completed">Matches real result</span>`;
    return `<div class="section-title">Claim Check -- ${esc(name)}</div>
      <p>Source document claims: <b>${r.claimed_win_rate_pct}%</b> win rate${r.claim_source_text ? ` ("${esc(r.claim_source_text)}")` : ""}</p>
      <p>SINDHU's real measured result: <b>${r.actual_win_rate_pct}%</b> win rate over ${r.actual_trade_count} trades ${badge}</p>
      ${!r.sample_reliable ? '<p class="muted">Fewer than 25 real trades so far -- this comparison isn\'t statistically reliable yet, even though it\'s shown honestly.</p>' : ""}`;
  }

  function ambiguityOverviewHtml(overview, en) {
    // Item 8: a plain, colour-coded at-a-glance summary -- confidently
    // understood vs still-uncertain vs genuinely-unresolved -- built purely
    // from data already computed server-side (no new AI call). Complements
    // the item-by-item Q&A list below it, doesn't replace it.
    if (!overview) return "";
    const dotColor = overview.status === "good" ? "#4caf82" : overview.status === "attention" ? "#e05252" : "#e0a828";
    const pct = overview.confidence_pct != null ? overview.confidence_pct : 0;
    return `
      <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-top:8px;padding:8px;border:1px solid var(--border,#333);border-radius:6px;">
        <div style="display:flex;align-items:center;gap:6px;">
          <span style="width:10px;height:10px;border-radius:50%;background:${dotColor};display:inline-block;"></span>
          <b>${pct}%</b> <span class="muted">${en ? "confidently understood" : "confidently samjha gaya"}</span>
        </div>
        ${overview.uncertain_count ? `<span class="pill pill-pending">${overview.uncertain_count} ${en ? "uncertain (suggestion available)" : "uncertain (suggestion maujood)"}</span>` : ""}
        ${overview.unresolved_count ? `<span class="pill pill-error">${overview.unresolved_count} ${en ? "unresolved (your input needed)" : "unresolved (aapka jawab chahiye)"}</span>` : ""}
        ${!overview.uncertain_count && !overview.unresolved_count ? `<span class="pill pill-completed">${en ? "Nothing uncertain" : "Kuch bhi uncertain nahi"}</span>` : ""}
      </div>`;
  }

  function clarIssueCardHtml(strategyId, issue) {
    const en = getLang() === "en";
    const question = issue.original_text
      ? (en ? `This wasn't understood: "${issue.original_text}"` : `Yeh samajh nahi aaya: "${issue.original_text}"`)
      : (en ? issue.reason : issue.reason);
    // Feature 2: one-click suggested answer per kind.
    let suggestButtons = "";
    if (issue.kind === "raw_condition") {
      suggestButtons = `<button class="btn btn-suggest-manual" data-strategy-id="${esc(strategyId)}" data-issue-id="${esc(issue.id)}">${en ? "Skip for now (Manual Review)" : "Filhaal Manual Review par rakhein"}</button>`;
    } else if ((issue.suggested_options || []).length) {
      // Item 3 (Contradiction Detection): each option can name its own
      // action/value (e.g. "remove_condition" -> {bucket, index}) since a
      // contradiction issue offers two different removal targets from one
      // card -- falls back to the old per-kind default for every other
      // issue kind, unchanged.
      const defaultAction = issue.kind === "invalid_indicator" ? "replace_indicator" : "set_field";
      suggestButtons = issue.suggested_options.map(o =>
        `<button class="btn btn-suggest-option" data-strategy-id="${esc(strategyId)}" data-issue-id="${esc(issue.id)}" data-action="${o.action || defaultAction}" data-value='${esc(JSON.stringify(o.value))}'>${esc(o.label)}</button>`,
      ).join("");
    }
    return `
      <div class="card" data-issue-id="${esc(issue.id)}" style="margin-top:8px;">
        <div style="display:flex;justify-content:space-between;gap:8px;">
          <div><b>${esc(question)}</b>
            <span class="tooltip-i" title="${esc(issue.why_asking || "")}">ⓘ</span>
          </div>
          <button class="btn btn-ghost btn-skip-issue" data-issue-id="${esc(issue.id)}">${en ? "Answer later" : "Baad mein"}</button>
        </div>
        ${issue.why_matters ? `<div class="muted" style="margin-top:4px;">${en ? "Why this matters:" : "Yeh isliye zaroori hai:"} ${esc(issue.why_matters)}</div>` : ""}
        ${issue.example ? `<div class="muted" style="margin-top:2px;font-style:italic;">${esc(issue.example)}</div>` : ""}
        <div class="btn-row" style="margin-top:8px;">
          ${suggestButtons}
          ${issue.can_reject ? `<button class="btn btn-ghost btn-reject-issue" data-strategy-id="${esc(strategyId)}" data-issue-id="${esc(issue.id)}">${en ? "Remove this rule" : "Yeh rule hata dein"}</button>` : ""}
        </div>
        <div class="form-row" style="margin-top:8px;"><label>${en ? "Or describe it yourself" : "Ya khud batayein"}</label>
          <input class="clar-text-input" placeholder="${en ? "e.g. RSI 14 below 30" : "misaal: RSI 14, 30 se neeche"}">
        </div>
        <div class="btn-row"><button class="btn btn-ghost btn-preview-text" data-strategy-id="${esc(strategyId)}" data-issue-id="${esc(issue.id)}">${en ? "Check my answer" : "Mera jawab check karein"}</button></div>
        <div class="clar-preview-box"></div>
      </div>`;
  }

  async function openReadMode(strategyId, name, onDone) {
    const en = getLang() === "en";
    const data = await apiGet(`/api/backtesting/strategies/${strategyId}/read-mode`).catch(() => null);
    if (!data) { showToast({ title: "Failed", body: "Could not load Read Mode.", isError: true }); return; }
    // Feature 10: full strategy read back in plain Roman Urdu, one section
    // at a time, each independently editable, before the real run-it
    // confirmation. The Incomplete Lock is checked for real (a live call
    // to /api/backtesting/run) rather than trusted from ready_for_backtest
    // alone, so the gate can never be silently bypassed from this screen.
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.innerHTML = `
      <div class="modal-box" style="max-width:640px;">
        <div class="modal-header"><b>${en ? "Read Mode" : "Read Mode"} -- ${esc(name)}</b><button class="btn-ghost readmode-close">&times;</button></div>
        <div class="modal-body">
          ${data.sections.map(s => `
            <div style="margin-bottom:10px;">
              <div style="display:flex;justify-content:space-between;">
                <b>${esc(s.title)}</b>
                <button class="btn-ghost readmode-edit" data-section="${esc(s.id)}">${en ? "Edit" : "Edit Karein"}</button>
              </div>
              <div class="muted">${esc(s.text)}</div>
            </div>`).join("")}
          <div id="readModeRunStatus" class="muted"></div>
        </div>
        <div class="modal-footer btn-row">
          <button class="btn readmode-run" ${data.ready_for_backtest ? "" : "disabled"}>${en ? "Yes, run backtest now" : "Haan, ab backtest karo"}</button>
          <button class="btn btn-ghost readmode-close">${en ? "Close" : "Band Karein"}</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    overlay.querySelectorAll(".readmode-close").forEach(b => b.onclick = () => overlay.remove());
    overlay.querySelectorAll(".readmode-edit").forEach(b => b.onclick = () => {
      overlay.remove();
      const card = content.querySelector(`.card[data-strategy-id="${CSS.escape(strategyId)}"]`);
      if (card) card.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    overlay.querySelector(".readmode-run").onclick = async () => {
      const status = overlay.querySelector("#readModeRunStatus");
      status.textContent = en ? "Starting backtest..." : "Backtest shuru ho raha hai...";
      try {
        const res = await apiPost("/api/backtesting/run", { strategy_id: strategyId });
        status.textContent = en ? `Backtest started (job ${res.job_id}).` : `Backtest shuru ho gaya (job ${res.job_id}).`;
      } catch (e) {
        // Proves the Incomplete Lock is still genuinely enforced here --
        // a locked strategy's 423 surfaces verbatim, never silently
        // swallowed or bypassed by this screen.
        status.textContent = `${en ? "Blocked:" : "Roka gaya:"} ${e.message}`;
      }
      if (onDone) onDone();
    };
  }

  // ------------------------------------------------------------ BACKTESTING
  async function renderBacktesting() {
    content.innerHTML = `
      <div class="section-title">Backtesting</div>
      <div class="two-col">
        <div>
          <div class="form-row">
            <label>Strategy Text (English / Roman Urdu / mixed)</label>
            <textarea id="stratText" placeholder="Entry: 1H&#10;Entry Rules:&#10;BOS and FVG bullish&#10;RSI below 40&#10;Exit Rules:&#10;CHoCH&#10;SL: below order block&#10;Risk: 1%&#10;RR: 1:3"></textarea>
          </div>
          <div class="form-row"><label>Name</label><input id="stratName" value="Unnamed Strategy"></div>
          <div class="btn-row">
            <button class="btn" id="btnParse">Parse &amp; Validate</button>
            <button class="btn" id="btnSave">Save to Library</button>
            <button class="btn" id="btnRun" disabled>Run Backtest</button>
            <span id="stratSaveStatus" class="muted"></span>
          </div>
          <div id="previewBox" class="card" style="white-space:pre-wrap;font-family:Consolas,monospace;font-size:12px;"></div>
          <div class="section-title">Saved Strategies</div>
          <div class="table-wrap"><table><thead><tr><th>Name</th><th>Tags</th><th>Status</th><th></th></tr></thead>
            <tbody id="stratTableBody"></tbody></table></div>
        </div>
        <div>
          <div id="bResumeStatus" class="muted" style="font-size:12px;margin-bottom:6px;">Checking for a running backtest&hellip;</div>
          <div class="grid">
            ${card("Current Strategy", `<span id="bCurStrategy">-</span>`)}
            ${card("Current Coin", `<span id="bCurCoin">-</span>`)}
            ${card("Current Timeframe", `<span id="bCurTf">-</span>`)}
            ${card("Stage", `<span id="bStage">-</span>`)}
            ${card("Coins Progress", `<span id="bProgress">-</span>`)}
            ${card("Trade Counter", `<span id="bTotalTrades">0</span>`)}
            ${card("Win Rate", `<span id="bWinRate">-</span>`)}
            ${card("PnL", `<span id="bPnl">$0.00</span>`)}
            ${card("Drawdown", `<span id="bDrawdown">0.00%</span>`)}
            ${card("Estimated Time", `<span id="bEta">-</span>`)}
            ${card("Current Trade", `<span id="bCurTrade">-</span>`)}
          </div>
          <div class="muted" style="font-size:11px;margin-top:8px;">Coins completed</div>
          <div class="progress-bar"><div id="bProgressFill" class="progress-bar-fill" style="width:0%"></div></div>
          <div class="muted" style="font-size:11px;margin-top:8px;">Current coin -- bars simulated</div>
          <div class="progress-bar"><div id="bBarProgressFill" class="progress-bar-fill" style="width:0%"></div></div>
          <div class="btn-row">
            <button class="btn" id="btnPause">Pause</button>
            <button class="btn" id="btnResume">Resume</button>
            <button class="btn" id="btnStop">Stop</button>
          </div>
          <div class="section-title">Progress Chart (cumulative PnL)</div>
          <div class="chart-box"><svg id="equityChart" viewBox="0 0 400 160" preserveAspectRatio="none"></svg></div>
          <div id="completionSummary" class="card" style="display:none;margin-top:16px;"></div>
          <div id="conditionReportPanel" style="display:none;">
            <div class="section-title">0-Trade Coins -- Why No Trades Fired</div>
            <div class="table-wrap"><table>
              <thead><tr><th>Coin</th><th>Condition</th><th>True Bars</th><th>Total Bars</th></tr></thead>
              <tbody id="conditionReportBody"></tbody>
            </table></div>
          </div>
        </div>
      </div>`;

    let currentConfig = null;
    let currentStrategyId = null;
    let currentJobId = null;
    // Set whenever a saved strategy is Loaded, alongside currentConfig --
    // lets doParse() tell "user hasn't touched the text since Load" apart
    // from "user is typing/pasting new directive text to parse."
    let loadedRawText = null;
    let loadedValid = false;
    let loadedErrors = [];
    let loadedPerformance = null;
    let wins = 0, total = 0;
    let cumulativePnl = 0, peakPnl = 0, jobStartTime = null;
    const equityCurve = [0];
    // Matches RunRequest.initial_balance's backend default (sindhu_web/api/backtesting.py) --
    // the "Run" button never overrides it, so each coin in the batch starts at this balance.
    const BACKTEST_INITIAL_BALANCE = 1000;
    let batchTotalCombos = 0;

    function drawEquitySparkline() {
      const svg = document.getElementById("equityChart");
      if (!svg || equityCurve.length < 2) return;
      svg.innerHTML = sparklineInner(equityCurve, 400, 160, 6);
    }

    async function refreshStrategyTable() {
      const res = await apiGet("/api/backtesting/strategies").catch(() => ({ strategies: [] }));
      document.getElementById("stratTableBody").innerHTML = res.strategies.map(s => `
        <tr><td>${esc(s.name)}</td><td>${(s.tags||[]).join(", ")}</td>
        <td>${strategyStatusPill(s.status)}</td>
        <td><button class="btn-ghost load-strategy" data-id="${s.id}">Load</button></td></tr>
      `).join("") || '<tr><td colspan="4">No saved strategies yet</td></tr>';

      document.querySelectorAll(".load-strategy").forEach(btn => {
        btn.onclick = async () => {
          const res = await apiGet(`/api/backtesting/strategies/${btn.dataset.id}`);
          if (!res.valid) {
            const proceed = confirm(
              `"${res.config.name}" is marked Needs Clarification and will NOT generate any ` +
              `backtest trades as saved (${res.errors.join("; ")}). Load it anyway to inspect or edit it?`
            );
            if (!proceed) return;
          }
          document.getElementById("stratText").value = res.config.raw_text;
          document.getElementById("stratName").value = res.config.name;
          currentConfig = res.config;
          currentStrategyId = btn.dataset.id;
          loadedRawText = res.config.raw_text;
          loadedValid = res.valid;
          loadedErrors = res.errors || [];
          loadedPerformance = res.performance || null;
          renderConfigPreview(res.config, res.valid, res.errors, res.performance);
        };
      });
    }
    await refreshStrategyTable();

    // Resume live progress if a backtest is already running -- otherwise
    // currentJobId stays null after any page reload/navigation away and
    // back, every subsequent "progress" WS message gets filtered out by
    // the `msg.job_id !== currentJobId` check below, and every field on
    // this page appears stuck/frozen even though the backtest is fine.
    try {
      const jobs = await apiGet("/api/jobs");
      const runningBacktest = (jobs.jobs || []).find(j => j.kind === "backtest" && j.status === "running");
      const resumeStatusEl = document.getElementById("bResumeStatus");
      if (!runningBacktest && resumeStatusEl) {
        resumeStatusEl.textContent = "No backtest currently running.";
      }
      if (runningBacktest) {
        if (resumeStatusEl) resumeStatusEl.textContent = `Resuming live view of running backtest (job ${runningBacktest.id})… this can take a few seconds while the backtest's CPU-heavy workers are active.`;
        currentJobId = runningBacktest.id;
        jobStartTime = Date.parse(runningBacktest.started_at) || Date.now();
        const p = runningBacktest.progress || {};
        if (p.current_strategy) document.getElementById("bCurStrategy").textContent = p.current_strategy;
        if (p.current_coin) document.getElementById("bCurCoin").textContent = p.current_coin;
        if (p.current_timeframe) document.getElementById("bCurTf").textContent = p.current_timeframe;
        if (p.current_stage) document.getElementById("bStage").textContent = p.current_stage;
        if (p.bar_pct != null) document.getElementById("bBarProgressFill").style.width = `${p.bar_pct}%`;
        if (p.total != null) {
          batchTotalCombos = p.total;
          document.getElementById("bProgress").textContent = `${p.done} / ${p.total}`;
          document.getElementById("bProgressFill").style.width = `${(p.done / Math.max(p.total, 1)) * 100}%`;
        }
        // Trade-level stats (count/win-rate/PnL/drawdown/chart) are now
        // persisted server-side too (see backtesting.py's _trade_cb), not
        // just streamed live -- restore them here instead of starting
        // back at zero, which is exactly what looked like "the backtest
        // reset" even though it never stopped.
        if (p.total_trades != null) {
          total = p.total_trades;
          wins = p.wins || 0;
          cumulativePnl = p.cumulative_pnl || 0;
          peakPnl = Math.max(cumulativePnl, cumulativePnl + (p.max_drawdown || 0));
          if (Array.isArray(p.equity_curve) && p.equity_curve.length) {
            equityCurve.length = 0;
            equityCurve.push(0, ...p.equity_curve);
          }
          document.getElementById("bTotalTrades").textContent = total;
          document.getElementById("bWinRate").textContent = total > 0 ? `${((wins / total) * 100).toFixed(1)}%` : "-";
          document.getElementById("bPnl").textContent = `${cumulativePnl >= 0 ? "" : "-"}$${Math.abs(cumulativePnl).toFixed(2)}`;
          document.getElementById("bPnl").className = cumulativePnl > 0 ? "positive" : cumulativePnl < 0 ? "negative" : "";
          const batchCapital = Math.max(batchTotalCombos, 1) * BACKTEST_INITIAL_BALANCE;
          const drawdown = peakPnl - cumulativePnl;
          document.getElementById("bDrawdown").textContent = `${((drawdown / batchCapital) * 100).toFixed(2)}%`;
          if (p.last_trade) {
            document.getElementById("bCurTrade").textContent =
              `#${p.last_trade.trade_num} ${p.last_trade.side} ${p.last_trade.symbol} pnl=${p.last_trade.pnl.toFixed(2)}`;
          }
          drawEquitySparkline();
        }
        if (resumeStatusEl) resumeStatusEl.textContent = `Live -- resumed job ${currentJobId} (${total} trade(s) so far).`;
        appendLog(`Resumed live view of running backtest job: ${currentJobId} (${total} trade(s) so far).`);
      }
    } catch (e) { /* non-fatal -- page still works, just won't auto-resume */ }

    if (pendingStrategyLoadId) {
      const id = pendingStrategyLoadId;
      pendingStrategyLoadId = null;
      try {
        const res = await apiGet(`/api/backtesting/strategies/${id}`);
        document.getElementById("stratText").value = res.config.raw_text;
        document.getElementById("stratName").value = res.config.name;
        currentConfig = res.config;
        currentStrategyId = id;
        loadedRawText = res.config.raw_text;
        loadedValid = res.valid;
        loadedErrors = res.errors || [];
        loadedPerformance = res.performance || null;
        renderConfigPreview(res.config, res.valid, res.errors, res.performance);
      } catch (e) { /* strategy may have been deleted meanwhile */ }
    }

    // Autosave: saves are keyed off currentStrategyId, so the first save
    // creates the record and every save after that updates the same one
    // -- editing the text never piles up duplicate library entries.
    const doAutosaveStrategy = debounce(async () => {
      if (!currentConfig) return;
      const status = document.getElementById("stratSaveStatus");
      status.textContent = "Saving...";
      try {
        const res = await autosave("POST", "/api/backtesting/strategies",
          { config: currentConfig, tags: [], strategy_id: currentStrategyId });
        currentStrategyId = res.id;
        status.textContent = "Saved";
        refreshStrategyTable();
      } catch (e) {
        status.textContent = "Save failed (will retry)";
      }
    }, 800);

    // Basic visibility + correction for Condition.role (which declared
    // timeframe -- bias/trend/analysis/entry -- a concept condition
    // actually reads from). "entry" is a real, valid, explicit choice
    // here (e.g. a 1-minute candle_break trigger genuinely belongs on the
    // entry timeframe), not just "unset" -- selecting it writes role back
    // to null, which is exactly equivalent everywhere it's read.
    const _ROLE_OPTIONS = ["entry", "bias", "trend", "analysis", "confirmation"];
    function _conditionRoleRow(bucket, idx, cond) {
      if (cond.type !== "concept") return "";
      const currentRole = cond.role || "entry";
      const opts = _ROLE_OPTIONS.map(r => `<option value="${r}"${r === currentRole ? " selected" : ""}>${r}</option>`).join("");
      return `<div class="cond-role-row" data-bucket="${bucket}" data-idx="${idx}" style="display:flex;align-items:center;gap:8px;margin:3px 0;">
        <span style="min-width:180px;">${esc(bucket.replace("_conditions", ""))}: ${esc(cond.name)}${cond.direction ? " (" + esc(cond.direction) + ")" : ""}</span>
        <select class="cond-role-select">${opts}</select>
      </div>`;
    }

    // Strategy Performance Dashboard detail breakdown: each of the 4
    // factors (backtest_engine/performance_dashboard.py computes these --
    // this only renders what the API already returned), with its real
    // number and pass/fail, plus the overall GREEN/RED verdict.
    function performanceBreakdownHtml(performance) {
      if (!performance) return "";
      const cls = performance.verdict === "GREEN" ? "pill-completed" : "pill-error";
      const rows = (performance.factors || []).map(f => {
        const icon = f.passed ? "✅" : "❌";
        return `<div style="margin:3px 0;">${icon} <b>${esc(f.factor.replace("_", " "))}</b> `
          + `(need ${esc(f.requirement)}): ${esc(f.detail)}</div>`;
      }).join("");
      return `<br><br><b>Performance Dashboard</b> `
        + `<span class="pill ${cls}">${performance.verdict === "GREEN" ? "🟢" : "🔴"} ${esc(performance.label)}</span>`
        + (performance.batch_id ? `<div class="muted" style="margin-top:2px;">based on backtest ${esc(performance.batch_id)} `
            + `(${performance.symbols_tested} symbol${performance.symbols_tested === 1 ? "" : "s"})</div>` : "")
        + `<div style="margin-top:6px;">${rows}</div>`;
    }

    function renderConfigPreview(config, valid, errors, performance) {
      const conditionRowsHtml = ["entry_conditions", "exit_conditions", "confirmation_conditions"]
        .map(bucket => (config[bucket] || []).map((c, i) => _conditionRoleRow(bucket, i, c)).join(""))
        .join("");
      document.getElementById("previewBox").innerHTML =
        `Timeframes: ${esc(JSON.stringify(config.timeframes))}<br>` +
        `Entry conditions: ${config.entry_conditions.length}<br>` +
        `Exit conditions: ${config.exit_conditions.length}<br>` +
        `Stop Loss: ${esc(config.stop_loss.type)}<br>Take Profit: ${esc(config.take_profit.type)}<br>` +
        `Risk%: ${config.risk_pct}  RR: ${config.risk_reward}<br><br>` +
        (valid ? "STATUS: VALID" : "STATUS: INVALID<br>" + errors.map(e => " - " + esc(e)).join("<br>")) +
        (conditionRowsHtml
          ? `<br><br><b>Condition timeframe roles</b> (which declared timeframe each concept actually reads from -- change if wrong):<br>${conditionRowsHtml}`
          : "") +
        performanceBreakdownHtml(performance);
      document.querySelectorAll(".cond-role-select").forEach(sel => {
        sel.onchange = () => {
          const row = sel.closest(".cond-role-row");
          const bucket = row.dataset.bucket, idx = Number(row.dataset.idx);
          currentConfig[bucket][idx].role = sel.value === "entry" ? null : sel.value;
          doAutosaveStrategy();
        };
      });
      document.getElementById("btnRun").disabled = !valid;
    }

    async function doParse() {
      const text = document.getElementById("stratText").value;
      const name = document.getElementById("stratName").value || "Unnamed Strategy";
      if (!text.trim()) return;
      // A Loaded strategy's raw_text is often the ORIGINAL source document
      // fed to the AI Center (analysis prose, not SINDHU's directive
      // syntax) -- it was never meant to be re-parsed by the regex parser
      // below. If the text still matches what Load put there, just
      // re-show the already-valid loaded config instead of mangling it.
      if (currentConfig && text === loadedRawText && name === currentConfig.name) {
        renderConfigPreview(currentConfig, loadedValid, loadedErrors, loadedPerformance);
        return;
      }
      const res = await apiPost("/api/backtesting/parse", { text, name });
      currentConfig = res.config;
      loadedPerformance = null;  // a freshly (re-)parsed, not-yet-saved config has no backtest history to judge yet
      renderConfigPreview(res.config, res.valid, res.errors, null);
      if (res.valid) doAutosaveStrategy();
    }

    document.getElementById("btnParse").onclick = doParse;
    const debouncedParse = debounce(doParse, 900);
    document.getElementById("stratText").addEventListener("input", debouncedParse);
    document.getElementById("stratName").addEventListener("input", () => { debouncedParse(); doAutosaveStrategy(); });

    document.getElementById("btnSave").onclick = async () => {
      if (!currentConfig) return;
      // Grand Feature Expansion, Phase 4 Feature 2: only checked for a
      // genuinely NEW strategy (no currentStrategyId yet) -- editing an
      // existing one isn't "building something new", so it's not checked
      // on every autosave/re-save.
      if (!currentStrategyId) {
        const sim = await apiPost("/api/backtesting/strategies/similarity-check", {
          concepts_used: currentConfig.concepts_used || [],
        }).catch(() => ({ warnings: [] }));
        if (sim.warnings && sim.warnings.length) {
          const top = sim.warnings[0];
          const proceed = confirm(
            `This looks ${top.similarity_pct}% similar to "${top.strategy_name}" (based on shared concepts). ` +
            `Save it anyway as a separate strategy?`
          );
          if (!proceed) return;
        }
      }
      const res = await apiPost("/api/backtesting/strategies", { config: currentConfig, tags: [], strategy_id: currentStrategyId });
      currentStrategyId = res.id;
      appendLog(`Saved strategy: ${currentConfig.name}`);
      refreshStrategyTable();
    };

    document.getElementById("btnRun").onclick = async () => {
      let res;
      // /api/backtesting/run does NOT return immediately: it first runs the
      // pre-flight sanity check (a real 2-coin backtest, measured 2.2s on a
      // 5m strategy and far longer on 1m) before it will start the job.
      // Without this feedback the button looked completely dead for those
      // seconds -- click, nothing happens -- which is exactly what "the
      // Backtesting page does not respond to clicks" was. Re-enabled in
      // finally so a failed run never leaves the button stuck disabled.
      const runBtn = document.getElementById("btnRun");
      const originalLabel = runBtn.textContent;
      runBtn.disabled = true;
      runBtn.textContent = "Checking strategy...";
      appendLog("Running pre-flight sanity check (2 coins, recent data) before the full backtest...");
      try {
        res = await apiPost("/api/backtesting/run", { config: currentConfig, all_coins: true, lang: getLang() });
      } catch (e) {
        let msg = e.message;
        try {
          const detail = JSON.parse(e.message).detail;
          // The pre-flight sanity check's failure detail is an OBJECT
          // ({errors, diagnosis, sanity_check_failed}), not a plain string --
          // passing that straight to alert()/a template string silently
          // printed "[object Object]", swallowing the actual diagnosis text
          // the backend worked out for exactly this "why did it fail"
          // moment. Pull the real message out of it instead.
          if (detail && typeof detail === "object") {
            msg = detail.diagnosis || (detail.errors || []).join("; ") || JSON.stringify(detail);
          } else if (detail) {
            msg = detail;
          }
        } catch (_) {}
        appendLog(`Backtest not started: ${msg}`);
        alert(msg);
        return;
      } finally {
        runBtn.disabled = false;
        runBtn.textContent = originalLabel;
      }
      currentJobId = res.job_id;
      wins = 0; total = 0;
      cumulativePnl = 0; peakPnl = 0; jobStartTime = Date.now();
      batchTotalCombos = 0;
      equityCurve.length = 0; equityCurve.push(0);
      document.getElementById("bPnl").textContent = "$0.00";
      document.getElementById("bDrawdown").textContent = "0.00%";
      document.getElementById("bEta").textContent = "-";
      document.getElementById("bStage").textContent = "-";
      document.getElementById("bBarProgressFill").style.width = "0%";
      document.getElementById("completionSummary").style.display = "none";
      document.getElementById("conditionReportPanel").style.display = "none";
      drawEquitySparkline();
      appendLog(`Backtest job started: ${currentJobId}`);
    };
    document.getElementById("btnPause").onclick = () => currentJobId && apiPost(`/api/jobs/${currentJobId}/pause`);
    document.getElementById("btnResume").onclick = () => currentJobId && apiPost(`/api/jobs/${currentJobId}/resume`);
    document.getElementById("btnStop").onclick = () => currentJobId && apiPost(`/api/jobs/${currentJobId}/stop`);

    async function showCompletionSummary(jobId) {
      try {
        const job = await apiGet(`/api/jobs/${jobId}`);
        const batchId = job.result && job.result.batch_id;
        if (!batchId) return;
        const [r, crs] = await Promise.all([
          apiGet(`/api/reports/${batchId}`),
          apiGet(`/api/reports/${batchId}/condition-reports`).catch(() => ({ reports: [] })),
        ]);
        document.getElementById("completionSummary").style.display = "block";
        document.getElementById("completionSummary").innerHTML = `
          <div><b>Backtest complete.</b> ${r.combos_completed}/${r.combos_total} coins completed.</div>
          <div class="grid" style="margin-top:8px;">
            ${card("Total Trades", fmtNum(r.total_trades))}
            ${card("Win Rate", `${r.win_rate}%`)}
            ${card("Total PnL", `${r.total_pnl}`)}
            ${card("Avg Profit", `${r.avg_profit_pct}%`)}
            ${card("Max Drawdown", `${r.max_drawdown_pct}%`)}
          </div>
          <div style="margin-top:8px;">
            Best Coin: <b>${esc(r.best_coin || "-")}</b> (pnl=${r.best_coin_pnl}, win_rate=${r.best_coin_win_rate}%) &nbsp;|&nbsp;
            Worst Coin: <b>${esc(r.worst_coin || "-")}</b> (pnl=${r.worst_coin_pnl}, win_rate=${r.worst_coin_win_rate}%)
          </div>
          <div class="btn-row" style="margin-top:8px;">
            <button class="btn" id="btnOpenFullReport">Open Full Report</button>
          </div>`;
        document.getElementById("btnOpenFullReport").onclick = () => { location.hash = "#reports"; };

        if (crs.reports && crs.reports.length) {
          document.getElementById("conditionReportPanel").style.display = "block";
          const rows = [];
          crs.reports.forEach(cr => {
            const rep = cr.report;
            if (!rep.per_condition || !rep.per_condition.length) {
              rows.push(`<tr><td>${esc(cr.symbol)}</td><td colspan="3" class="muted">No entry conditions to report on</td></tr>`);
              return;
            }
            rep.per_condition.forEach((pc, idx) => {
              rows.push(`<tr><td>${idx === 0 ? esc(cr.symbol) : ""}</td><td>${esc(pc.description)}</td><td>${pc.true_bars}</td><td>${idx === 0 ? rep.total_bars : ""}</td></tr>`);
            });
            rows.push(`<tr><td></td><td><b>ALL TOGETHER</b></td><td><b>${rep.all_together_bars}</b></td><td></td></tr>`);
          });
          document.getElementById("conditionReportBody").innerHTML = rows.join("");
        }
      } catch (e) { /* report may not be ready yet or job failed -- non-fatal */ }
    }

    onLive((msg) => {
      if (msg.channel === "sync" && msg.entity === "strategy") { refreshStrategyTable(); return; }
      if (msg.channel === "job" && msg.event === "finished" && msg.job_id === currentJobId) {
        showCompletionSummary(currentJobId);
        return;
      }
      if (msg.channel !== "progress" || msg.job_id !== currentJobId) return;
      if (msg.current_strategy) document.getElementById("bCurStrategy").textContent = msg.current_strategy;
      if (msg.current_coin) document.getElementById("bCurCoin").textContent = msg.current_coin;
      if (msg.current_timeframe) document.getElementById("bCurTf").textContent = msg.current_timeframe;
      if (msg.current_stage) document.getElementById("bStage").textContent = msg.current_stage;
      if (msg.bar_pct != null) document.getElementById("bBarProgressFill").style.width = `${msg.bar_pct}%`;
      if (msg.total != null) {
        batchTotalCombos = msg.total;
        document.getElementById("bProgress").textContent = `${msg.done} / ${msg.total}`;
        document.getElementById("bProgressFill").style.width = `${(msg.done / Math.max(msg.total,1)) * 100}%`;
        if (msg.eta_seconds != null) {
          const etaSec = Math.round(msg.eta_seconds);
          document.getElementById("bEta").textContent = etaSec <= 0 ? "Done" :
            etaSec < 60 ? `${etaSec}s` : `${Math.floor(etaSec / 60)}m ${etaSec % 60}s`;
        } else if (jobStartTime && msg.done > 0) {
          const elapsedMs = Date.now() - jobStartTime;
          const remaining = Math.max(msg.total - msg.done, 0);
          const etaMs = (elapsedMs / msg.done) * remaining;
          const etaSec = Math.round(etaMs / 1000);
          document.getElementById("bEta").textContent = remaining === 0 ? "Done" :
            etaSec < 60 ? `${etaSec}s` : `${Math.floor(etaSec / 60)}m ${etaSec % 60}s`;
        }
      }
      if (msg.last_trade) {
        total++; if (msg.last_trade.pnl > 0) wins++;
        cumulativePnl += msg.last_trade.pnl;
        peakPnl = Math.max(peakPnl, cumulativePnl);
        equityCurve.push(cumulativePnl);
        const drawdown = peakPnl - cumulativePnl;

        document.getElementById("bTotalTrades").textContent = total;
        document.getElementById("bWinRate").textContent = `${((wins/total)*100).toFixed(1)}%`;
        document.getElementById("bPnl").textContent = `${cumulativePnl >= 0 ? "" : "-"}$${Math.abs(cumulativePnl).toFixed(2)}`;
        document.getElementById("bPnl").className = cumulativePnl > 0 ? "positive" : cumulativePnl < 0 ? "negative" : "";
        const batchCapital = Math.max(batchTotalCombos, 1) * BACKTEST_INITIAL_BALANCE;
        document.getElementById("bDrawdown").textContent = `${((drawdown / batchCapital) * 100).toFixed(2)}%`;
        document.getElementById("bCurTrade").textContent =
          `#${msg.last_trade.trade_num} ${msg.last_trade.side} ${msg.last_trade.symbol} pnl=${msg.last_trade.pnl.toFixed(2)}`;
        drawEquitySparkline();
      }
    });
  }

  // ------------------------------------------------------------ SHARED BATCH DETAIL
  // Used by both the Reports page and the Backtest History page so the
  // full-results view (best/worst coin, per-coin table, equity/drawdown
  // charts, 0-trade breakdown) isn't duplicated -- each caller just passes
  // its own set of element ids since the two pages have separate DOM.
  async function renderBatchDetailInto(batchId, ids) {
    const [r, tr, crs] = await Promise.all([
      apiGet(`/api/reports/${batchId}`),
      apiGet(`/api/reports/${batchId}/trades`).catch(() => ({ trades: [] })),
      apiGet(`/api/reports/${batchId}/condition-reports`).catch(() => ({ reports: [] })),
    ]);
    document.getElementById(ids.detail).style.display = "block";
    document.getElementById(ids.summary).textContent =
      `Best Coin: ${r.best_coin} (pnl=${r.best_coin_pnl}, win_rate=${r.best_coin_win_rate}%)   ` +
      `Worst Coin: ${r.worst_coin} (pnl=${r.worst_coin_pnl}, win_rate=${r.worst_coin_win_rate}%)\n` +
      `Best Timeframe: ${r.best_timeframe}   Worst Timeframe: ${r.worst_timeframe}\n` +
      `Best Session: ${r.best_session}   Worst Session: ${r.worst_session}\n\n` +
      `Total Trades: ${r.total_trades}  Win Rate: ${r.win_rate}%  Avg Profit: ${r.avg_profit_pct}%  Total PnL: ${r.total_pnl}\n` +
      `Max Drawdown: ${r.max_drawdown_pct}%  Profit Factor: ${r.avg_profit_factor}\n\n` +
      `Lessons Applied: ${r.lessons_applied}  ` +
      `Trades Approved by Lessons: ${r.trades_approved_by_lessons}  ` +
      `Trades Rejected by Lessons: ${r.trades_rejected_by_lessons}`;

    // Part 2 (auto-surfaced 0-trade diagnosis): shown immediately, right
    // after the summary -- no extra clicks needed to discover why a coin
    // got 0 trades, unlike the detailed raw breakdown table further below.
    const diagBox = document.getElementById(ids.zeroDiagnosis);
    if (diagBox) diagBox.innerHTML = zeroTradeBoxHtml(crs);

    document.getElementById(ids.coinBody).innerHTML =
      (r.coin_ranking || []).map(c => {
        const pnlCls = c.total_pnl > 0 ? "positive" : c.total_pnl < 0 ? "negative" : "";
        const profitCls = c.avg_profit_pct > 0 ? "positive" : c.avg_profit_pct < 0 ? "negative" : "";
        return `<tr><td>${esc(c.symbol)}</td><td>${c.total_trades}</td><td>${c.win_rate}%</td>` +
          `<td class="${profitCls}">${c.avg_profit_pct}%</td><td class="${pnlCls}">${c.total_pnl}</td>` +
          `<td>${c.max_drawdown_pct}%</td>` +
          `<td>${ids.replayBox ? `<button class="btn-ghost hist-replay-btn" data-symbol="${esc(c.symbol)}">Replay</button>` : ""}</td></tr>`;
      }).join("") || '<tr><td colspan="7">No completed coins in this batch yet.</td></tr>';

    if (ids.replayBox) {
      document.querySelectorAll(".hist-replay-btn").forEach(btn => {
        btn.onclick = () => loadBacktestReplay(batchId, btn.dataset.symbol, ids.replayBox);
      });
    }

    let cum = 0, peak = 0;
    const equity = [0], drawdown = [0];
    (tr.trades || []).forEach(t => {
      cum += (t.pnl_pct || 0);
      peak = Math.max(peak, cum);
      equity.push(cum);
      drawdown.push(cum - peak);
    });
    document.getElementById(ids.equityBox).innerHTML = sparklineSvg(equity);
    document.getElementById(ids.drawdownBox).innerHTML = sparklineSvg(drawdown);

    // Trade-by-trade breakdown: the data was already being fetched for the
    // equity/drawdown sparklines above, then discarded -- surfacing it as a
    // real table means a person can see exactly why each trade won/lost
    // without needing devtools or server logs.
    if (ids.tradeLogBody) {
      document.getElementById(ids.tradeLogBody).innerHTML = (tr.trades || []).slice(0, 200).map(t => `
        <tr>
          <td>${esc(t.symbol)}</td>
          <td><span class="pill ${t.direction === "long" ? "pill-bullish" : "pill-bearish"}">${esc(t.direction || "-")}</span></td>
          <td>${t.entry_price != null ? t.entry_price : "-"}</td>
          <td>${t.exit_price != null ? t.exit_price : "-"}</td>
          <td class="${(t.pnl_pct || 0) >= 0 ? "pill-up" : "pill-down"}">${t.pnl_pct != null ? t.pnl_pct.toFixed(2) : "-"}%</td>
          <td>${esc(t.exit_reason || "-")}</td>
          <td style="font-size:12px;max-width:220px;">${esc(t.entry_reason || "-")}</td>
        </tr>`).join("") || '<tr><td colspan="7">No trades in this batch.</td></tr>';
    }

    // Failed coins: a symbol whose run ended in an actual ERROR (not just
    // "ran fine, 0 trades" -- that's the separate 0-trade diagnosis above)
    // used to be visible only by fetching this same /api/reports/{id}
    // response directly and reading its raw `results` array by hand.
    if (ids.failedSection && ids.failedBody) {
      const failed = (r.results || []).filter(x => x.status === "error");
      const failedSection = document.getElementById(ids.failedSection);
      if (failed.length) {
        failedSection.style.display = "block";
        document.getElementById(ids.failedBody).innerHTML = failed.map(x => {
          const m = x.metrics || {};
          return `<tr>
            <td>${esc(x.symbol || "-")}</td>
            <td>${esc(m.stage || "-")}</td>
            <td>${esc(m.reason || "-")}</td>
            <td>${esc(m.suggested_fix || "-")}</td>
          </tr>`;
        }).join("");
      } else {
        failedSection.style.display = "none";
      }
    }

    const zeroSection = document.getElementById(ids.zeroSection);
    if (crs.reports && crs.reports.length) {
      zeroSection.style.display = "block";
      const rows = [];
      crs.reports.forEach(cr => {
        const rep = cr.report;
        if (!rep.per_condition || !rep.per_condition.length) {
          rows.push(`<tr><td>${esc(cr.symbol)}</td><td colspan="3" class="muted">No entry conditions to report on</td></tr>`);
          return;
        }
        rep.per_condition.forEach((pc, idx) => {
          rows.push(`<tr><td>${idx === 0 ? esc(cr.symbol) : ""}</td><td>${esc(pc.description)}</td><td>${pc.true_bars}</td><td>${idx === 0 ? rep.total_bars : ""}</td></tr>`);
        });
        rows.push(`<tr><td></td><td><b>ALL TOGETHER</b></td><td><b>${rep.all_together_bars}</b></td><td></td></tr>`);
      });
      document.getElementById(ids.zeroBody).innerHTML = rows.join("");
    } else {
      zeroSection.style.display = "none";
    }
    return r;
  }

  // ------------------------------------------------------------ REPORTS
  // Navigation Reorganization: this page used to duplicate Backtest
  // History's own batch list + full per-batch detail almost exactly (both
  // read the same underlying batch data). Reports now focuses on
  // cross-strategy/cross-time summaries instead -- Best/Worst Strategy,
  // Strategy Comparison export, and Weekly Reports (moved here from
  // Settings, where it didn't really belong). Raw per-batch results
  // (equity curve, trade log, 0-trade diagnosis, etc.) live in Backtest
  // History, which already has everything Reports used to show plus more
  // (Monte Carlo, Trade Audit, Stress Test) -- one clear home instead of two.
  async function renderReports() {
    const myToken = activeRouteToken;
    const [bw, weeklyRes] = await Promise.all([
      apiGet("/api/reports/best-worst/strategies").catch(() => ({})),
      apiGet("/api/paper-trading/weekly-reports").catch(() => ({ reports: [] })),
    ]);
    if (isStaleRoute(myToken)) return;
    content.innerHTML = `
      <div class="section-title">Reports</div>
      <p class="muted" style="margin-top:-10px;">Cross-strategy summaries and exports. For a specific backtest's raw results (trade log, equity curve, coin breakdown), see Backtest History.</p>
      <div class="grid">
        ${card("Best Strategy", esc(bw.best_strategy || "-"))}
        ${card("Worst Strategy", esc(bw.worst_strategy || "-"))}
      </div>

      <div class="section-title">Strategy Comparison Export</div>
      <div class="card">
        <p class="muted" style="font-size:12px;margin-top:0;">Exports the same Strategy Comparison table shown on the Paper Trading page.</p>
        <div class="btn-row"><button class="btn-ghost" id="btnExportComparisonFromReports">Export to Excel</button></div>
      </div>

      <div class="section-title">Weekly Reports</div>
      <div class="card">
        <div class="btn-row"><button class="btn" id="btnGenerateReport">Generate Report Now</button></div>
        <div id="weeklyReportList"></div>
      </div>`;

    document.getElementById("btnExportComparisonFromReports").onclick = () => {
      window.open("/api/paper-trading/strategy-comparison/export?period=all", "_blank");
    };

    function renderWeeklyReports(r) {
      const box = document.getElementById("weeklyReportList");
      if (!r.reports.length) { box.innerHTML = `<p class="muted">No reports yet -- generate one now, or wait for the automatic weekly cycle.</p>`; return; }
      box.innerHTML = r.reports.map((rep, i) => `
        <details ${i === 0 ? "open" : ""} style="margin-bottom:8px;">
          <summary>${esc((rep.created_at || "").slice(0,10))}</summary>
          <pre style="white-space:pre-wrap;font-family:inherit;font-size:13px;">${esc(rep.report_text)}</pre>
        </details>`).join("");
    }
    renderWeeklyReports(weeklyRes);
    document.getElementById("btnGenerateReport").onclick = async () => {
      await apiPost("/api/paper-trading/weekly-reports/generate-now", {});
      appendLog("Weekly report generated.");
      const r = await apiGet("/api/paper-trading/weekly-reports").catch(() => ({ reports: [] }));
      renderWeeklyReports(r);
    };

    onLive((msg) => {
      if (msg.channel === "job" && msg.event === "finished") renderReports().catch(console.error);
    });
  }

  // ------------------------------------------------------------ BACKTEST HISTORY
  // Permanent, database-backed list of every completed batch (unlike the
  // Backtesting page's live progress, which is in-memory and gone once the
  // job finishes) -- separate from Reports so a user can browse past runs
  // without the Reports page's best/worst-strategy framing getting in the way.
  async function renderBacktestHistory() {
    const myToken = activeRouteToken;

    async function renderList() {
      document.getElementById("histTableBody").innerHTML = '<tr><td colspan="7">Loading...</td></tr>';
      let batches;
      try {
        ({ batches } = await apiGet("/api/backtest-history"));
      } catch (e) {
        if (isStaleRoute(myToken)) return;
        document.getElementById("histTableBody").innerHTML =
          `<tr><td colspan="7">Couldn't load backtest history: ${esc(e.message)}. ` +
          `<button class="btn-ghost" id="histRetryBtn">Retry</button></td></tr>`;
        document.getElementById("histRetryBtn").onclick = () => renderList().catch(console.error);
        return;
      }
      if (isStaleRoute(myToken)) return;
      document.getElementById("histTableBody").innerHTML = batches.map(b => {
        const pnlCls = b.total_pnl > 0 ? "positive" : b.total_pnl < 0 ? "negative" : "";
        const optBadge = b.optimization
          ? `<span class="pill pill-completed" style="cursor:pointer;" title="This batch was compared by the automation pipeline -- click View to see original vs optimized." >⚖ ${esc(b.optimization.winner === "optimized" && b.batch_id === b.optimization.optimized_batch_id ? "Optimized (winner)" : b.optimization.winner === "original" && b.batch_id === b.optimization.original_batch_id ? "Original (winner)" : b.optimization.original_batch_id === b.batch_id ? "Original" : "Optimized")}</span>`
          : "";
        return `<tr>
          <td>${esc((b.created_at || "").slice(0, 19))}</td>
          <td>
            <span class="hist-name-display" data-id="${b.batch_id}">${esc(b.display_name || b.strategy)}</span>
            <button class="btn-ghost hist-rename-btn" data-id="${b.batch_id}" data-name="${esc(b.display_name || b.strategy)}" title="Rename">✎</button>
            ${optBadge}
          </td>
          <td>${b.symbol_count}</td>
          <td>${b.total_trades}</td>
          <td>${b.win_rate}%</td>
          <td class="${pnlCls}">${b.total_pnl != null ? b.total_pnl : "-"}</td>
          <td>
            <button class="btn-ghost view-history" data-id="${b.batch_id}">View</button>
            <button class="btn-ghost hist-export" data-id="${b.batch_id}" data-fmt="csv">CSV</button>
            <button class="btn-ghost hist-export" data-id="${b.batch_id}" data-fmt="excel">Excel</button>
            <button class="btn-ghost hist-export" data-id="${b.batch_id}" data-fmt="pdf">PDF</button>
          </td>
        </tr>`;
      }).join("") || '<tr><td colspan="7">No completed backtests yet -- run one from the Backtesting page.</td></tr>';

      document.querySelectorAll(".view-history").forEach(btn => {
        btn.onclick = () => openHistoryDetail(btn.dataset.id);
      });

      // Navigation Reorganization: the old standalone Reports page's batch
      // list duplicated this exact list -- its one genuinely unique
      // capability (CSV/Excel/PDF export per batch) moved here rather than
      // being lost.
      document.querySelectorAll(".hist-export").forEach(btn => {
        btn.onclick = () => window.open(`/api/reports/${btn.dataset.id}/export/${btn.dataset.fmt}`, "_blank");
      });

      document.querySelectorAll(".hist-rename-btn").forEach(btn => {
        btn.onclick = () => startRename(btn.dataset.id, btn.dataset.name);
      });

      // Auto-open a specific batch if we arrived here via the completion
      // notification banner's "View Results" link.
      if (pendingHistoryBatchId) {
        const id = pendingHistoryBatchId;
        pendingHistoryBatchId = null;
        if (batches.some(b => b.batch_id === id)) openHistoryDetail(id);
      }
    }

    function startRename(batchId, currentName) {
      const span = document.querySelector(`.hist-name-display[data-id="${batchId}"]`);
      if (!span) return;
      const wrap = document.createElement("span");
      wrap.innerHTML = `<input type="text" class="hist-rename-input" value="${esc(currentName)}" style="width:180px;">` +
        `<button class="btn-ghost hist-rename-save">Save</button>` +
        `<button class="btn-ghost hist-rename-cancel">Cancel</button>`;
      span.replaceWith(wrap);
      const input = wrap.querySelector(".hist-rename-input");
      input.focus();
      input.select();
      const cancel = () => renderList().catch(console.error);
      wrap.querySelector(".hist-rename-cancel").onclick = cancel;
      const save = async () => {
        const newName = input.value.trim();
        if (!newName) { cancel(); return; }
        try {
          await apiPost(`/api/backtest-history/${batchId}/rename`, { display_name: newName });
        } catch (e) {
          alert(`Rename failed: ${e.message}`);
        }
        renderList().catch(console.error);
      };
      wrap.querySelector(".hist-rename-save").onclick = save;
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") save();
        if (e.key === "Escape") cancel();
      });
    }

    function openHistoryDetail(batchId) {
      document.getElementById("histDetail").scrollIntoView({ behavior: "smooth", block: "start" });
      const box = document.getElementById("histComparisonBox");
      box.style.display = "block";
      loadComparisonBox(box, batchId).catch(console.error);
      loadMonteCarloBox(batchId).catch(console.error);
      loadSlippageSensitivityBox(batchId).catch(console.error);
      loadWhatIfBox(batchId);
      loadFeatureImportanceBox(batchId);
      loadCrossCoinBox(batchId).catch(console.error);
      loadVariantsBox(batchId);
      wireTradeAuditForm(batchId);
      wireStressTestForm();
      return renderBatchDetailInto(batchId, histDetailIds);
    }

    // Stress Testing Engine (B5): re-runs a strategy against the single
    // worst real historical week already in the stored data.
    function wireStressTestForm() {
      const box = document.getElementById("histStressTestBox");
      box.innerHTML = `
        <div class="btn-row">
          <input id="stStrategyId" placeholder="Strategy ID" style="max-width:180px;">
          <input id="stSymbol" placeholder="Symbol (e.g. BTCUSDT)" style="max-width:160px;">
          <button class="btn" id="btnRunStressTest">Run Stress Test</button>
        </div>
        <div id="stResult"></div>`;
      document.getElementById("btnRunStressTest").onclick = async () => {
        const sid = document.getElementById("stStrategyId").value.trim();
        const symbol = document.getElementById("stSymbol").value.trim();
        const resultBox = document.getElementById("stResult");
        if (!sid || !symbol) { resultBox.innerHTML = `<p class="muted">Fill in strategy ID and symbol.</p>`; return; }
        resultBox.innerHTML = `<p class="muted">Finding the worst historical week and re-running...</p>`;
        try {
          const r = await apiGet(`/api/backtesting/stress-test/${sid}/${symbol}`);
          if (!r.available) { resultBox.innerHTML = `<p class="muted">${esc(r.reason)}</p>`; return; }
          const m = r.metrics;
          resultBox.innerHTML = `
            <p>Worst week found: <b>${r.worst_week.range_pct}%</b> price range (${new Date(r.worst_week.start_ms).toISOString().slice(0,10)} to ${new Date(r.worst_week.end_ms).toISOString().slice(0,10)})</p>
            <div class="grid">
              ${card("Trades That Week", m.total_trades)}
              ${card("Win Rate", m.win_rate + "%")}
              ${cardClass("Profit %", m.profit_pct + "%", m.profit_pct >= 0 ? "positive" : "negative")}
              ${card("Max Drawdown", m.max_drawdown_pct + "%")}
            </div>`;
        } catch (e) {
          resultBox.innerHTML = `<p class="muted">${esc(e.message)}</p>`;
        }
      };
    }

    // Monte Carlo Engine (Group 6 #4): reshuffles this batch's own real
    // trades 1000 times and shows the distribution -- a wide gap between
    // p5 and p95 means the reported result depended heavily on lucky order.
    async function loadMonteCarloBox(batchId) {
      const mcBox = document.getElementById("histMonteCarloBox");
      mcBox.innerHTML = `<button class="btn" id="btnRunMonteCarlo">Run Monte Carlo Simulation (1,000 iterations)</button>`;
      document.getElementById("btnRunMonteCarlo").onclick = async () => {
        mcBox.innerHTML = `<span class="muted">Running 1,000 simulations...</span>`;
        const r = await apiGet(`/api/backtesting/monte-carlo/${batchId}`);
        if (!r.available) {
          mcBox.innerHTML = `<span class="muted">Not enough trades for a meaningful simulation: ${esc(r.reason)}</span>`;
          return;
        }
        mcBox.innerHTML = `
          <div class="grid">
            ${card("Actual Result", `$${r.original_final_equity.toLocaleString()}`)}
            ${card("Worst Case (5th %ile)", `$${r.p5_final_equity.toLocaleString()}`)}
            ${card("Typical (Median)", `$${r.median_final_equity.toLocaleString()}`)}
            ${card("Best Case (95th %ile)", `$${r.p95_final_equity.toLocaleString()}`)}
            ${cardClass("Risk of Ruin", `${r.risk_of_ruin_pct}%`, r.risk_of_ruin_pct > 20 ? "negative" : "")}
            ${card("Profitable Outcomes", `${r.profitable_outcomes_pct}%`)}
          </div>
          <div class="muted" style="font-size:12px;">
            Based on ${r.trade_count} real trades reshuffled ${r.iterations} times. "Risk of Ruin" = share of
            reshuffled orders where equity fell 50%+ below its peak at some point -- ${esc(r.ruin_definition)}.
          </div>`;
      };
    }

    // Slippage Sensitivity Test (Grand Feature Expansion, Phase 3 Feature
    // 18): recomputes this batch's own real trades' PnL under
    // progressively worse slippage (never re-runs the full simulation).
    async function loadSlippageSensitivityBox(batchId) {
      const box = document.getElementById("histSlippageBox");
      box.innerHTML = `<button class="btn" id="btnRunSlippageTest">Run Slippage Sensitivity Test</button>`;
      document.getElementById("btnRunSlippageTest").onclick = async () => {
        box.innerHTML = `<span class="muted">Testing...</span>`;
        const r = await apiGet(`/api/backtesting/slippage-sensitivity/${batchId}`);
        if (!r.levels || !r.levels.length) {
          box.innerHTML = `<span class="muted">${esc(r.reason || "Not enough trades for this test.")}</span>`;
          return;
        }
        box.innerHTML = `
          <div class="table-wrap"><table>
            <thead><tr><th>Extra Slippage</th><th>Total PnL</th><th>Win Rate</th></tr></thead>
            <tbody>${r.levels.map(lvl => `
              <tr><td>${lvl.extra_slippage_pct === 0 ? "None (actual result)" : `+${lvl.extra_slippage_pct}%`}</td>
              <td class="${lvl.total_pnl >= 0 ? "pill-up" : "pill-down"}">$${lvl.total_pnl.toFixed(2)}</td>
              <td>${lvl.win_rate.toFixed(1)}%</td></tr>`).join("")}</tbody>
          </table></div>
          <div class="muted" style="font-size:12px;margin-top:6px;">
            ${r.breakeven_extra_slippage_pct != null
              ? `This strategy's edge goes to $0 once slippage worsens by about +${r.breakeven_extra_slippage_pct}% per fill${r.fragile ? " -- fragile: that's a small real-world margin." : "."}`
              : "This strategy stayed profitable across every slippage level tested -- a durable edge."}
          </div>`;
      };
    }

    // Historical What-If Simulator (Grand Feature Expansion, Phase 5
    // Feature 14): a real re-simulation (not a PnL recompute like
    // Slippage Sensitivity above) with ONE parameter changed, bounded to
    // the last ~30 days and a few coins for speed -- an honest, fast
    // preview, not a full-dataset validation pass.
    function loadWhatIfBox(batchId) {
      const box = document.getElementById("histWhatIfBox");
      const en = getLang() === "en";
      box.innerHTML = `
        <p class="muted" style="font-size:12px;margin-top:0;">${en
          ? "A fast preview (~30 days, up to 3 coins) of what would have happened with ONE parameter changed -- not a full validation."
          : "Ek tez preview (~30 din, 3 tak coins) ke saath dekhein agar EK parameter badla jata to kya hota -- yeh poori validation nahi hai."}</p>
        <div class="btn-row">
          <select id="wiParam">
            <option value="risk_pct">${en ? "Risk % per Trade" : "Risk % per Trade"}</option>
            <option value="stop_loss">${en ? "Stop-Loss %" : "Stop-Loss %"}</option>
            <option value="take_profit">${en ? "Take-Profit %" : "Take-Profit %"}</option>
          </select>
          <input id="wiValue" type="number" step="0.1" placeholder="${en ? "New value" : "Naya value"}" style="max-width:140px;">
          <button class="btn" id="btnRunWhatIf">${en ? "Run What-If" : "What-If Chalayein"}</button>
        </div>
        <div id="wiResult" style="margin-top:8px;"></div>`;
      document.getElementById("btnRunWhatIf").onclick = async () => {
        const resultEl = document.getElementById("wiResult");
        const param = document.getElementById("wiParam").value;
        const value = parseFloat(document.getElementById("wiValue").value);
        if (isNaN(value)) { resultEl.innerHTML = `<p class="muted">${en ? "Enter a value." : "Value dalein."}</p>`; return; }
        const parameterChanges = param === "risk_pct" ? { risk_pct: value } : { [param]: { type: "fixed_pct", value } };
        resultEl.innerHTML = `<p class="muted">${en ? "Running..." : "Chal raha hai..."}</p>`;
        try {
          const r = await apiPost("/api/backtesting/what-if", { batch_id: batchId, parameter_changes: parameterChanges });
          const diff = r.modified.net_profit - r.original.net_profit;
          resultEl.innerHTML = `
            <div class="grid">
              ${card(en ? "Original Net PnL" : "Original Net PnL", `$${r.original.net_profit.toLocaleString()}`)}
              ${cardClass(en ? "What-If Net PnL" : "What-If Net PnL", `$${r.modified.net_profit.toLocaleString()}`, diff >= 0 ? "positive" : "negative")}
              ${card(en ? "Original Trades" : "Original Trades", r.original.total_trades)}
              ${card(en ? "What-If Trades" : "What-If Trades", r.modified.total_trades)}
            </div>
            <div class="muted" style="font-size:11.5px;margin-top:6px;">
              ${en ? `Based on ${r.symbols.join(", ")}, last ${r.window_days} days of this batch's own real data.`
                   : `${r.symbols.join(", ")} par, is batch ke asal data ke aakhri ${r.window_days} dinon ke hisaab se.`}
            </div>`;
        } catch (e) {
          resultEl.innerHTML = `<p class="muted">${esc(e.message)}</p>`;
        }
      };
    }

    // Backtest Replay Visualizer (Grand Feature Expansion, Phase 5
    // Feature 15): a full-run, bar-by-bar step-through of one coin's real
    // backtest candles + real trade entry/exit markers -- distinct from
    // the per-trade static candle window in Trade Audit above. Hand-rolled
    // inline SVG, same convention as sparklineSvg/barChartSvg elsewhere in
    // this file -- no charting library.
    function candleReplaySvg(candles, trades, uptoIndex) {
      const shown = candles.slice(0, uptoIndex + 1);
      if (shown.length < 2) return `<div class="muted">Not enough bars yet.</div>`;
      const w = 760, h = 260, padTop = 10, padBottom = 20, padLeft = 4, padRight = 4;
      const lo = Math.min(...shown.map(c => c.low)), hi = Math.max(...shown.map(c => c.high));
      const range = (hi - lo) || 1;
      const chartW = w - padLeft - padRight, chartH = h - padTop - padBottom;
      const barW = chartW / shown.length;
      const yOf = (price) => padTop + chartH - ((price - lo) / range) * chartH;
      const xOf = (i) => padLeft + i * barW + barW / 2;

      const bars = shown.map((c, i) => {
        const x = xOf(i);
        const color = c.close >= c.open ? "var(--green)" : "var(--red)";
        const bodyTop = yOf(Math.max(c.open, c.close));
        const bodyBottom = yOf(Math.min(c.open, c.close));
        return `
          <line x1="${x}" y1="${yOf(c.high)}" x2="${x}" y2="${yOf(c.low)}" style="stroke:${color};stroke-width:1;"/>
          <rect x="${(x - barW * 0.35).toFixed(1)}" y="${bodyTop.toFixed(1)}" width="${(barW * 0.7).toFixed(1)}"
                height="${Math.max(1, bodyBottom - bodyTop).toFixed(1)}" style="fill:${color};stroke:none;"/>`;
      }).join("");

      const timeByIndex = new Map(shown.map((c, i) => [c.time, i]));
      const markers = trades.filter(t => shown.length && t.entry_time >= shown[0].time && t.entry_time <= shown[shown.length - 1].time)
        .map(t => {
          // Nearest visible bar to this trade's entry time -- real trade
          // timestamps rarely land exactly on a resampled bar boundary.
          let nearest = 0, bestDiff = Infinity;
          shown.forEach((c, i) => { const diff = Math.abs(c.time - t.entry_time); if (diff < bestDiff) { bestDiff = diff; nearest = i; } });
          const x = xOf(nearest);
          const isLong = t.side === "long" || t.side === "bullish";
          const y = isLong ? yOf(shown[nearest].low) + 10 : yOf(shown[nearest].high) - 10;
          const color = t.pnl == null ? "var(--text-dim)" : (t.pnl >= 0 ? "var(--green)" : "var(--red)");
          return `<circle cx="${x}" cy="${y}" r="4" style="fill:${color};stroke:#fff;stroke-width:1;"><title>Trade #${t.trade_num} ${esc(t.side)} pnl=${t.pnl != null ? t.pnl.toFixed(2) : "-"}</title></circle>`;
        }).join("");

      return `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}">${bars}${markers}</svg>`;
    }

    async function loadBacktestReplay(batchId, symbol, containerId) {
      const box = document.getElementById(containerId);
      const en = getLang() === "en";
      box.innerHTML = `<p class="muted">${en ? "Loading..." : "Load ho raha hai..."}</p>`;
      let data;
      try {
        data = await apiGet(`/api/backtesting/replay/${batchId}/${symbol}`);
      } catch (e) {
        box.innerHTML = `<p class="muted">${esc(e.message)}</p>`;
        return;
      }
      if (!data.candles.length) {
        box.innerHTML = `<p class="muted">${en ? "No candle data available for this coin." : "Is coin ke liye candle data mojood nahi."}</p>`;
        return;
      }
      let step = 0;
      let playTimer = null;
      const render = () => {
        document.getElementById("replayChart").innerHTML = candleReplaySvg(data.candles, data.trades, step);
        document.getElementById("replayStepLabel").textContent = `${step + 1} / ${data.candles.length}`;
      };
      box.innerHTML = `
        <div class="muted" style="font-size:11.5px;margin-bottom:6px;">
          ${esc(symbol)} -- ${esc(data.timeframe)}${data.truncated ? ` (${en ? "showing the most recent" : "sabse haal ke"} ${data.candles.length} ${en ? "bars only" : "bars hi"})` : ""}
        </div>
        <div id="replayChart"></div>
        <div class="btn-row" style="margin-top:8px;align-items:center;">
          <button class="btn-ghost" id="replayStepBack">&laquo; ${en ? "Step" : "Step"}</button>
          <button class="btn" id="replayPlayPause">${en ? "Play" : "Play"}</button>
          <button class="btn-ghost" id="replayStepForward">${en ? "Step" : "Step"} &raquo;</button>
          <button class="btn-ghost" id="replayReset">${en ? "Reset" : "Reset"}</button>
          <span id="replayStepLabel" class="muted"></span>
        </div>`;
      step = data.candles.length > 1 ? 1 : 0;
      render();

      const stop = () => {
        if (playTimer) { clearInterval(playTimer); playTimer = null; }
        document.getElementById("replayPlayPause").textContent = en ? "Play" : "Play";
      };
      document.getElementById("replayStepForward").onclick = () => {
        stop();
        step = Math.min(data.candles.length - 1, step + 1);
        render();
      };
      document.getElementById("replayStepBack").onclick = () => {
        stop();
        step = Math.max(1, step - 1);
        render();
      };
      document.getElementById("replayReset").onclick = () => {
        stop();
        step = 1;
        render();
      };
      document.getElementById("replayPlayPause").onclick = () => {
        if (playTimer) { stop(); return; }
        document.getElementById("replayPlayPause").textContent = en ? "Pause" : "Pause";
        playTimer = setInterval(() => {
          if (step >= data.candles.length - 1) { stop(); return; }
          step += 1;
          render();
        }, 180);
      };
    }

    // Feature Importance Ranking (Grand Feature Expansion, Phase 6
    // Feature 6): leave-one-out ablation over this strategy's own entry/
    // confirmation conditions, reusing the same bounded fast-window
    // re-simulation infrastructure as the What-If Simulator above.
    function loadFeatureImportanceBox(batchId) {
      const box = document.getElementById("histFeatureImportanceBox");
      const en = getLang() === "en";
      box.innerHTML = `
        <p class="muted" style="font-size:12px;margin-top:0;">${en
          ? "Removes each of this strategy's own entry/confirmation conditions one at a time and re-tests (~30 days, up to 3 coins) to see which ones actually matter most."
          : "Is strategy ki har entry/confirmation condition ko baari baari hata kar dobara test karta hai (~30 din, 3 tak coins) takay pata chale kaun si condition sabse zyada zaroori hai."}</p>
        <div class="btn-row">
          <button class="btn" id="btnRunFeatureImportance">${en ? "Run Feature Importance" : "Feature Importance Chalayein"}</button>
        </div>
        <div id="fiResult" style="margin-top:8px;"></div>`;
      document.getElementById("btnRunFeatureImportance").onclick = async () => {
        const resultEl = document.getElementById("fiResult");
        resultEl.innerHTML = `<p class="muted">${en ? "Running..." : "Chal raha hai..."}</p>`;
        try {
          const r = await apiPost("/api/backtesting/feature-importance", { batch_id: batchId });
          if (!r.conditions.length) {
            resultEl.innerHTML = `<p class="muted">${esc(r.reason || (en ? "Not enough conditions to compare." : "Compare karne ke liye kaafi conditions nahi."))}</p>`;
            return;
          }
          resultEl.innerHTML = `
            <p class="muted" style="font-size:11.5px;">${en ? "Baseline net PnL" : "Baseline net PnL"}: $${r.baseline_net_profit.toLocaleString()} (${r.symbols.join(", ")}, ${en ? "last" : "aakhri"} ${r.window_days} ${en ? "days" : "din"})</p>
            <div class="table-wrap"><table>
              <thead><tr><th>${en ? "Condition" : "Condition"}</th><th>${en ? "Net PnL Without It" : "Iske Bina Net PnL"}</th><th>${en ? "Impact" : "Impact"}</th></tr></thead>
              <tbody>${r.conditions.map(c => `
                <tr>
                  <td>${esc(c.label)}</td>
                  <td>$${c.net_profit_without.toLocaleString()}</td>
                  <td class="${c.impact >= 0 ? "positive" : "negative"}">${c.impact >= 0 ? "+" : ""}$${c.impact.toLocaleString()}</td>
                </tr>`).join("")}</tbody>
            </table></div>
            <div class="muted" style="font-size:11px;margin-top:6px;">${en ? "Higher impact = removing it hurt PnL more = this condition is doing more of the real work." : "Zyada impact = hatane se PnL zyada gira = yeh condition zyada asal kaam kar rahi hai."}</div>`;
        } catch (e) {
          resultEl.innerHTML = `<p class="muted">${esc(e.message)}</p>`;
        }
      };
    }

    // Cross-Coin Group Validation (Grand Feature Expansion, Phase 6
    // Feature 8): whether this batch's real results hold up similarly
    // across low/medium/high volatility groups, computed fresh from real
    // data (never a hardcoded coin list) -- distinct from the flat
    // per-coin ranking table shown elsewhere on this page.
    async function loadCrossCoinBox(batchId) {
      const box = document.getElementById("histCrossCoinBox");
      const en = getLang() === "en";
      box.innerHTML = `<p class="muted">${en ? "Loading..." : "Load ho raha hai..."}</p>`;
      try {
        const r = await apiGet(`/api/backtesting/cross-coin-validation/${batchId}`);
        if (!r.groups.length) {
          box.innerHTML = `<p class="muted">${esc(r.reason || (en ? "Not enough data." : "Kaafi data nahi."))}</p>`;
          return;
        }
        const groupLabel = (g) => ({ low_volatility: en ? "Low Volatility" : "Kam Volatility",
          medium_volatility: en ? "Medium Volatility" : "Darmiyani Volatility",
          high_volatility: en ? "High Volatility" : "Zyada Volatility" }[g] || g);
        box.innerHTML = `
          <div class="table-wrap"><table>
            <thead><tr><th>${en ? "Group" : "Group"}</th><th>${en ? "Coins" : "Coins"}</th><th>${en ? "Trades" : "Trades"}</th><th>${en ? "Win Rate" : "Win Rate"}</th><th>${en ? "Net PnL" : "Net PnL"}</th></tr></thead>
            <tbody>${r.groups.map(g => `
              <tr>
                <td>${groupLabel(g.group)}</td>
                <td>${g.coin_count}</td>
                <td>${g.total_trades}</td>
                <td>${g.win_rate != null ? g.win_rate + "%" : "-"}</td>
                <td class="${g.net_pnl >= 0 ? "positive" : "negative"}">${g.net_pnl >= 0 ? "+" : ""}$${g.net_pnl.toLocaleString()}</td>
              </tr>`).join("")}</tbody>
          </table></div>
          ${r.consistent_across_groups != null ? `
            <div class="muted" style="font-size:12px;margin-top:6px;">${r.consistent_across_groups
              ? (en ? "Consistent -- win rate holds up similarly across every volatility group tested." : "Consistent -- win rate har volatility group mein takriban barabar hai.")
              : (en ? "Inconsistent -- win rate swings by more than 20 points between the best and worst volatility group, a sign this strategy may be overfit to one specific type of coin." : "Inconsistent -- best aur worst volatility group ke darmiyan win rate 20 points se zyada farq karta hai, ho sakta hai yeh strategy sirf ek khaas tarah ke coin par overfit ho.")}</div>
          ` : (r.reason ? `<div class="muted" style="font-size:12px;margin-top:6px;">${esc(r.reason)}</div>` : "")}`;
      } catch (e) {
        box.innerHTML = `<p class="muted">${esc(e.message)}</p>`;
      }
    }

    // Self-Generated Strategy Variants (Grand Feature Expansion, Phase 6
    // Feature 5): several PARALLEL sibling variants tested side-by-side in
    // one pass -- distinct from the sequential, one-generation-per-tick
    // Evolution Engine mutations shown on the Evolution page.
    function loadVariantsBox(batchId) {
      const box = document.getElementById("histVariantsBox");
      const en = getLang() === "en";
      box.innerHTML = `
        <p class="muted" style="font-size:12px;margin-top:0;">${en
          ? "Generates a few sibling variants of this strategy (each swapping one entry condition for a related alternative) and tests them all side-by-side (~30 days, up to 3 coins)."
          : "Is strategy ki chand sibling variants banata hai (har ek mein ek entry condition ko related alternative se badal kar) aur sabko saath test karta hai (~30 din, 3 tak coins)."}</p>
        <div class="btn-row">
          <button class="btn" id="btnRunVariants">${en ? "Generate & Test Variants" : "Variants Banayein Aur Test Karein"}</button>
        </div>
        <div id="variantsResult" style="margin-top:8px;"></div>`;
      document.getElementById("btnRunVariants").onclick = async () => {
        const resultEl = document.getElementById("variantsResult");
        resultEl.innerHTML = `<p class="muted">${en ? "Running..." : "Chal raha hai..."}</p>`;
        try {
          const r = await apiPost("/api/backtesting/strategy-variants", { batch_id: batchId });
          if (!r.variants.length) {
            resultEl.innerHTML = `<p class="muted">${esc(r.reason || (en ? "No variants to test." : "Test karne ke liye koi variant nahi."))}</p>`;
            return;
          }
          resultEl.innerHTML = `
            <p class="muted" style="font-size:11.5px;">${en ? "Baseline (original) net PnL" : "Baseline (original) net PnL"}: $${r.baseline_net_profit.toLocaleString()} (${r.symbols.join(", ")}, ${en ? "last" : "aakhri"} ${r.window_days} ${en ? "days" : "din"})</p>
            <div class="table-wrap"><table>
              <thead><tr><th>${en ? "Variant" : "Variant"}</th><th>${en ? "Net PnL" : "Net PnL"}</th><th>${en ? "vs. Original" : "Original Se"}</th></tr></thead>
              <tbody>${r.variants.map(v => `
                <tr>
                  <td>${esc(v.label)}</td>
                  <td>$${v.net_profit.toLocaleString()}</td>
                  <td class="${v.improvement >= 0 ? "positive" : "negative"}">${v.improvement >= 0 ? "+" : ""}$${v.improvement.toLocaleString()}</td>
                </tr>`).join("")}</tbody>
            </table></div>
            <div class="muted" style="font-size:11px;margin-top:6px;">${en ? "A variant is a throwaway test -- nothing here changes the strategy's real saved config. Save it as a new version yourself if one looks genuinely better." : "Variant sirf ek test hai -- yahan strategy ka asal saved config nahi badalta. Agar koi genuinely behtar lage to khud naye version ke taur par save karein."}</div>`;
        } catch (e) {
          resultEl.innerHTML = `<p class="muted">${esc(e.message)}</p>`;
        }
      };
    }

    // Trade Audit Engine (Group 6 #5): look up any single trade by its
    // coordinates and see the exact entry/exit rule plus raw candles --
    // manual end-to-end verification without touching the database.
    function wireTradeAuditForm(batchId) {
      const box = document.getElementById("histTradeAuditBox");
      box.innerHTML = `
        <div class="btn-row">
          <input id="taSymbol" placeholder="Symbol (e.g. BTCUSDT)" style="max-width:160px;">
          <input id="taTimeframe" placeholder="Timeframe (e.g. 1h)" style="max-width:120px;">
          <input id="taTradeNum" type="number" placeholder="Trade #" style="max-width:100px;">
          <button class="btn" id="btnTradeAudit">Inspect Trade</button>
        </div>
        <div id="taResult"></div>`;
      document.getElementById("btnTradeAudit").onclick = async () => {
        const symbol = document.getElementById("taSymbol").value.trim();
        const timeframe = document.getElementById("taTimeframe").value.trim();
        const tradeNum = document.getElementById("taTradeNum").value.trim();
        const resultBox = document.getElementById("taResult");
        if (!symbol || !timeframe || !tradeNum) { resultBox.innerHTML = `<p class="muted">Fill in symbol, timeframe, and trade number.</p>`; return; }
        resultBox.innerHTML = `<p class="muted">Loading...</p>`;
        try {
          const r = await apiGet(`/api/backtesting/trade-audit/${batchId}/${symbol}/${timeframe}/${tradeNum}`);
          const t = r.trade;
          resultBox.innerHTML = `
            <div class="card">
              <div class="label">Trade #${t.trade_num} -- ${esc(t.symbol)} ${esc(t.side)}</div>
              <p><b>Entry:</b> $${t.entry_price} at ${new Date(t.entry_time).toISOString().slice(0,19)} -- reason: "${esc(t.entry_reason || "-")}"</p>
              <p><b>Exit:</b> $${t.exit_price} at ${t.exit_time ? new Date(t.exit_time).toISOString().slice(0,19) : "-"} -- reason: "${esc(t.exit_reason || "-")}"</p>
              <p><b>PnL:</b> <span class="${t.pnl > 0 ? 'positive' : t.pnl < 0 ? 'negative' : ''}">${t.pnl != null ? '$' + t.pnl.toFixed(2) : "-"} (${t.pnl_pct != null ? t.pnl_pct.toFixed(2) : "-"}%)</span></p>
              <p><b>Stop-Loss:</b> ${t.stop_loss != null ? '$' + t.stop_loss : "-"} &nbsp; <b>Take-Profit:</b> ${t.take_profit != null ? '$' + t.take_profit : "-"}</p>
              <p class="muted">${r.candles.length} raw 1-minute candles fetched spanning this trade (30min padding each side) -- available via the API for anyone who wants to plot/verify it directly.</p>
            </div>`;
        } catch (e) {
          resultBox.innerHTML = `<p class="muted">${esc(e.message)}</p>`;
        }
      };
    }

    const histDetailIds = {
      detail: "histDetail", summary: "histSummary", coinBody: "histCoinBreakdownBody",
      equityBox: "histEquityChartBox", drawdownBox: "histDrawdownChartBox",
      zeroSection: "histZeroTradeSection", zeroBody: "histZeroTradeBody", zeroDiagnosis: "histZeroDiagnosis",
      tradeLogBody: "histTradeLogBody", failedSection: "histFailedSection", failedBody: "histFailedBody",
      replayBox: "histReplayBox",
    };

    content.innerHTML = `
      <div class="section-title">Backtest History</div>
      <p class="muted">Every completed backtest batch, permanently -- stored in the database, not just live progress.</p>
      <div class="section-title" style="font-size:13px;">Time Spent Backtesting ${helpIcon("duration_tracker")}</div>
      <div id="histDurationBox" class="grid" style="margin-bottom:12px;"></div>
      <div class="table-wrap"><table>
        <thead><tr><th>Date</th><th>Strategy</th><th>Coins</th><th>Trades</th><th>Win Rate</th><th>Total PnL</th><th></th></tr></thead>
        <tbody id="histTableBody"><tr><td colspan="7">Loading...</td></tr></tbody>
      </table></div>
      <div id="histDetail" style="display:none;margin-top:16px;">
        <div id="histComparisonBox" class="card" style="display:none;margin-bottom:16px;"></div>
        <div id="histSummary" class="card" style="white-space:pre-wrap;font-family:Consolas,monospace;font-size:12px;"></div>
        <div id="histZeroDiagnosis"></div>
        <div id="histFailedSection" style="display:none;">
          <div class="section-title">Coins That Failed to Run -- Why</div>
          <div class="table-wrap"><table>
            <thead><tr><th>Coin</th><th>Stage</th><th>Reason</th><th>Suggested Fix</th></tr></thead>
            <tbody id="histFailedBody"></tbody>
          </table></div>
        </div>

        <div class="section-title">Monte Carlo Simulation</div>
        <div id="histMonteCarloBox" class="card"></div>

        <div class="section-title">Slippage Sensitivity Test ${helpIcon("slippage_sensitivity")}</div>
        <div id="histSlippageBox" class="card"></div>

        <div class="section-title">${getLang() === "en" ? "Historical What-If Simulator" : "Historical What-If Simulator"} ${helpIcon("what_if_simulator")}</div>
        <div id="histWhatIfBox" class="card"></div>

        <div class="section-title">${getLang() === "en" ? "Feature Importance Ranking" : "Feature Importance Ranking"} ${helpIcon("feature_importance")}</div>
        <div id="histFeatureImportanceBox" class="card"></div>

        <div class="section-title">${getLang() === "en" ? "Cross-Coin Group Validation" : "Cross-Coin Group Validation"} ${helpIcon("cross_coin_validation")}</div>
        <div id="histCrossCoinBox" class="card"></div>

        <div class="section-title">${getLang() === "en" ? "Self-Generated Strategy Variants" : "Self-Generated Strategy Variants"} ${helpIcon("strategy_variants")}</div>
        <div id="histVariantsBox" class="card"></div>

        <div class="section-title">Trade Audit -- Inspect Any Trade</div>
        <div id="histTradeAuditBox" class="card"></div>

        <div class="section-title">Stress Test -- Worst Historical Week</div>
        <div id="histStressTestBox" class="card"></div>
        <div class="section-title">Per-Coin Breakdown</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Coin</th><th>Trades</th><th>Win Rate</th><th>Profit %</th><th>Total PnL</th><th>Max Drawdown</th><th></th></tr></thead>
          <tbody id="histCoinBreakdownBody"></tbody>
        </table></div>
        <div class="section-title">${getLang() === "en" ? "Backtest Replay" : "Backtest Replay"} ${helpIcon("backtest_replay")}</div>
        <div id="histReplayBox" class="card"><p class="muted">${getLang() === "en" ? "Click Replay on a coin above to step through its real backtest bar by bar." : "Upar kisi coin par Replay click karke uska asal backtest bar-by-bar dekhein."}</p></div>
        <div class="section-title">Equity Curve</div>
        <div id="histEquityChartBox" class="chart-box"></div>
        <div class="section-title">Drawdown</div>
        <div id="histDrawdownChartBox" class="chart-box"></div>
        <div id="histZeroTradeSection" style="display:none;">
          <div class="section-title">0-Trade Coins -- Condition-Hit Breakdown</div>
          <div class="table-wrap"><table>
            <thead><tr><th>Coin</th><th>Condition</th><th>True Bars</th><th>Total Bars</th></tr></thead>
            <tbody id="histZeroTradeBody"></tbody>
          </table></div>
        </div>
        <div class="section-title">Trade-by-Trade Log (first 200)</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Coin</th><th>Direction</th><th>Entry</th><th>Exit</th><th>PnL%</th><th>Exit Reason</th><th>Entry Reason</th></tr></thead>
          <tbody id="histTradeLogBody"></tbody>
        </table></div>
      </div>`;

    // Session Time-Tracker (Grand Feature Expansion, Phase 3 Feature 14):
    // loaded once, independent of renderList()'s own polling -- this
    // doesn't change as often as the batch list itself.
    apiGet("/api/backtesting/duration-stats").then(d => {
      if (isStaleRoute(myToken)) return;
      const box = document.getElementById("histDurationBox");
      if (!d.count) { box.innerHTML = `<p class="muted">No completed backtests yet.</p>`; return; }
      box.innerHTML = `
        ${card("Backtests Timed", fmtNum(d.count))}
        ${card("Average Duration", fmtElapsed(d.avg_duration_seconds))}
        ${card("Total Time Spent", fmtElapsed(d.total_time_spent_seconds))}
        ${d.slowest[0] ? card("Slowest Batch", `${esc(d.slowest[0].strategy_name)} (${fmtElapsed(d.slowest[0].duration_seconds)})`) : ""}
      `;
    }).catch(() => {});

    await renderList();

    // A newly completed backtest must appear here without a manual
    // refresh -- re-fetching the list on every "finished" event is cheap
    // (it's a lightweight per-batch aggregate, not the full report).
    // kind === "pipeline" is included so a batch produced by the
    // automation pipeline (Part 2) also shows up without a manual refresh.
    onLive((msg) => {
      if (msg.channel === "job" && msg.event === "finished" && (msg.kind === "backtest" || msg.kind === "pipeline")) {
        renderList().catch(console.error);
      }
    });
  }

  // ------------------------------------------------------------ AUTOMATION PIPELINE HISTORY
  async function renderPipelineHistory() {
    const myToken = activeRouteToken;

    async function renderList() {
      document.getElementById("pphTableBody").innerHTML = '<tr><td colspan="5">Loading...</td></tr>';
      let runs;
      try {
        ({ runs } = await apiGet("/api/automation/pipeline-history"));
      } catch (e) {
        if (isStaleRoute(myToken)) return;
        document.getElementById("pphTableBody").innerHTML =
          `<tr><td colspan="5">Couldn't load pipeline history: ${esc(e.message)}. ` +
          `<button class="btn-ghost" id="pphRetryBtn">Retry</button></td></tr>`;
        document.getElementById("pphRetryBtn").onclick = () => renderList().catch(console.error);
        return;
      }
      if (isStaleRoute(myToken)) return;
      document.getElementById("pphTableBody").innerHTML = runs.map(r => `
        <tr>
          <td>${esc((r.created_at || "").slice(0, 19))}</td>
          <td>${esc(r.strategy_name || r.strategy_id)}</td>
          <td>${pipelineStatusBadge(r)}</td>
          <td>${r.symbols ? fmtNum(r.symbols.length) : "all"}</td>
          <td><button class="btn-ghost pph-view" data-id="${esc(r.job_id)}">View</button></td>
        </tr>`).join("") || '<tr><td colspan="5">No automation pipeline runs yet -- trigger one from the Strategies page.</td></tr>';

      document.querySelectorAll(".pph-view").forEach(btn => {
        btn.onclick = () => openRunDetail(btn.dataset.id);
      });
    }

    function openRunDetail(jobId) {
      document.getElementById("pphDetail").style.display = "block";
      document.getElementById("pphDetail").scrollIntoView({ behavior: "smooth", block: "start" });
      loadPipelineRunDetail(document.getElementById("pphDetailBox"), jobId);
    }

    async function renderQueue() {
      let q;
      try {
        q = await apiGet("/api/automation/submission-queue");
      } catch (e) {
        return;
      }
      if (isStaleRoute(myToken)) return;
      const box = document.getElementById("pphQueueBox");
      if (!box) return;
      const current = q.current
        ? `Running now: <b>${esc(q.current.strategy_name || q.current.strategy_id)}</b>`
        : "Nothing running from the queue right now.";
      box.innerHTML = `
        <div class="grid">
          ${card("Pending in Queue", fmtNum(q.pending_count))}
          ${card("Currently Running", q.current ? esc(q.current.strategy_name || q.current.strategy_id) : "-")}
        </div>
        <p class="muted" style="margin-top:8px;">${current} Strategies submitted together run one at a time, in the order submitted -- the rest wait here.</p>`;
    }

    content.innerHTML = `
      <div class="section-title">Automation Pipeline History</div>
      <p class="muted">Every automation run (import -&gt; backtest -&gt; optimizer -&gt; paper trading), permanently -- the same data tracked for crash-recovery resume, not a separate log.</p>

      <div class="section-title" style="margin-top:24px;">Submission Queue</div>
      <p class="muted">Strategies waiting for their turn to run the full pipeline. Only one runs at a time; the rest queue here automatically (e.g. when several strategies are imported close together).</p>
      <div id="pphQueueBox"></div>
      <div style="margin-top:12px;">
        <textarea id="pphBatchInput" class="input" rows="2" placeholder="Paste strategy IDs to submit together, separated by commas or new lines"></textarea>
        <button class="btn-ghost" id="pphSubmitBatchBtn" style="margin-top:6px;">Submit Batch to Queue</button>
        <span id="pphBatchResult" class="muted" style="margin-left:8px;"></span>
      </div>

      <div class="table-wrap" style="margin-top:24px;"><table>
        <thead><tr><th>Started</th><th>Strategy</th><th>Status</th><th>Coins</th><th></th></tr></thead>
        <tbody id="pphTableBody"><tr><td colspan="5">Loading...</td></tr></tbody>
      </table></div>
      <div id="pphDetail" style="display:none;margin-top:16px;">
        <div class="section-title">Run Detail</div>
        <div id="pphDetailBox"></div>
      </div>`;

    await Promise.all([renderList(), renderQueue()]);

    document.getElementById("pphSubmitBatchBtn").onclick = async () => {
      const raw = document.getElementById("pphBatchInput").value || "";
      const strategy_ids = raw.split(/[\n,]/).map(s => s.trim()).filter(Boolean);
      const resultEl = document.getElementById("pphBatchResult");
      if (!strategy_ids.length) {
        resultEl.textContent = "Paste at least one strategy ID first.";
        return;
      }
      try {
        const res = await apiPost("/api/automation/submit-batch", { strategy_ids });
        resultEl.textContent = `Queued ${res.queued.length} strategy(ies).` +
          (res.skipped_not_found.length ? ` Not found: ${res.skipped_not_found.join(", ")}` : "");
        document.getElementById("pphBatchInput").value = "";
        renderQueue().catch(console.error);
      } catch (e) {
        resultEl.textContent = `Failed: ${e.message}`;
      }
    };

    // A run reaching a terminal state (or progressing a stage) should
    // appear here without a manual refresh.
    onLive((msg) => {
      if (msg.channel === "job" && (msg.kind === "pipeline")) {
        renderList().catch(console.error);
        renderQueue().catch(console.error);
      }
      if (msg.channel === "automation_pipeline") {
        renderList().catch(console.error);
        renderQueue().catch(console.error);
      }
    });
  }

  // ------------------------------------------------------------ TELEGRAM (signal log, honest delivery status, message preview)
  // Every delivery status the backend can report (paper_trading/
  // telegram_delivery.py STATUS_LABELS) mapped to its pill colour. The
  // rule the whole page follows: a signal is ONLY ever shown as green/
  // "Sent" when a real successful send was actually recorded for it.
  // Withheld-by-a-gate is amber (the system did its job), a network
  // failure is red (something is genuinely broken), queued is neutral.
  const TG_STATUS_TONE = {
    sent: "pill-bullish",
    blocked_network: "pill-error",
    failed_telegram: "pill-error",
    not_configured: "pill-error",
    withheld_stale: "pill-pending",
    withheld_drift: "pill-pending",
    withheld_switch: "pill-pending",
    withheld_rate_limit: "pill-pending",
    queued: "pill-muted",
    never_sent: "pill-muted",
  };

  function tgStatusPill(row) {
    const tone = TG_STATUS_TONE[row.delivery_status] || "pill-muted";
    const title = row.delivery_detail ? ` title="${esc(row.delivery_detail)}"` : "";
    return `<span class="pill ${tone}"${title}>${esc(row.delivery_label)}</span>`;
  }

  function telegramOutcomePill(outcome) {
    if (outcome === "win") return `<span class="pill-up">Win</span>`;
    if (outcome === "loss") return `<span class="pill-down">Loss</span>`;
    if (outcome === "breakeven") return `<span class="muted">Break-even</span>`;
    if (outcome === "pending") return `<span class="pill pill-running">Open / Pending</span>`;
    return `<span class="muted">Unknown</span>`;
  }

  // The one panel that answers "is this actually reaching my phone right
  // now, and if not, why". Deliberately reads recorded evidence rather
  // than probing the network on page load -- Test Connection is the
  // explicit live check.
  function tgConnectionPanelHtml(cs) {
    const map = {
      working: ["ok", "Delivery is working"],
      blocked: ["bad", "Delivery is blocked"],
      failing: ["bad", "Delivery is failing"],
      turned_off: ["warn", "Sending is switched off"],
      not_configured: ["warn", "Not set up yet"],
      unknown: ["warn", "Nothing to judge from yet"],
    };
    const [tone, headline] = map[cs.state] || map.unknown;
    const s = cs.settings || {};
    return `
      <div class="conn-panel conn-${tone}">
        <div class="conn-main">
          <div class="conn-dot"></div>
          <div>
            <div class="conn-headline">${esc(headline)}</div>
            <div class="conn-reason">${esc(cs.reason || "")}</div>
          </div>
        </div>
        <div class="conn-facts">
          <div><span class="muted">Bot set up</span><b>${s.token_configured ? "Yes" : "No"}</b></div>
          <div><span class="muted">Channel set</span><b>${s.channel_id ? "Yes" : "No"}</b></div>
          <div><span class="muted">Sending switch</span><b>${s.master_send_enabled ? "On" : "Off"}</b></div>
          <div><span class="muted">Proxy</span><b>${cs.proxy_enabled ? (cs.proxy_configured ? "On" : "On, but empty") : "Off"}</b></div>
          <div><span class="muted">Last success</span><b>${cs.last_success_at ? esc(cs.last_success_at.slice(0, 16).replace("T", " ")) : "Never"}</b></div>
          <div><span class="muted">Last failure</span><b>${cs.last_failure_at ? esc(cs.last_failure_at.slice(0, 16).replace("T", " ")) : "None"}</b></div>
        </div>
        ${cs.last_failure_reason ? `<div class="conn-detail">Last recorded failure: ${esc(cs.last_failure_reason)}</div>` : ""}
      </div>`;
  }

  // Shows the exact text that WOULD go out for one signal, built by the
  // same formatter a real send uses -- so formatting can be checked long
  // before delivery ever works.
  function openTelegramPreviewModal(positionId) {
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.innerHTML = `
      <div class="modal-panel">
        <div class="modal-head">
          <div>
            <div class="modal-eyebrow">Message preview</div>
            <h3 class="modal-title">Exactly what would be sent</h3>
          </div>
          <button class="btn-ghost" data-modal-close>Close</button>
        </div>
        <div id="tgPrevBody" class="muted">Loading...</div>
      </div>`;
    document.body.appendChild(overlay);
    const close = () => overlay.remove();
    overlay.onclick = (e) => { if (e.target === overlay) close(); };
    overlay.querySelector("[data-modal-close]").onclick = close;

    // Longer than the default 15s: the very first preview for a signal
    // has to score its confluence against live market data, which can
    // legitimately take a while when an engine tick is holding the
    // storage lock. Subsequent opens hit the server-side cache.
    apiGet(`/api/paper-trading/telegram/preview/${positionId}`, 60000).then(p => {
      overlay.querySelector("#tgPrevBody").innerHTML = `
        <div class="modal-stat-row">
          <div><span class="modal-stat-label">Coin</span><span class="modal-stat-value">${esc(p.symbol || "-")}</span></div>
          <div><span class="modal-stat-label">Direction</span><span class="modal-stat-value">${esc((p.direction || "-").toUpperCase())}</span></div>
          <div><span class="modal-stat-label">Grade</span><span class="modal-stat-value">${esc(p.quality_grade || "-")}</span></div>
          <div><span class="modal-stat-label">Age</span><span class="modal-stat-value">${p.age_minutes != null ? p.age_minutes + " min" : "-"}</span></div>
        </div>
        ${p.would_be_withheld_as_stale
          ? `<div class="notice notice-warn">This one would be held back right now: it is older than the ${p.freshness_limit_minutes}-minute freshness limit ${helpIcon("signal_freshness")}. The text below is still exactly how it would be formatted.</div>`
          : `<div class="notice notice-ok">This one is fresh enough to go out right now (limit is ${p.freshness_limit_minutes} minutes) ${helpIcon("signal_freshness")}.</div>`}
        <div class="tg-preview">${renderTelegramMessageHtml(p.message_text)}</div>
        <p class="muted plain-note">This is a preview only &mdash; opening it never sends anything. The live "current price" line is the one field only a real send can fill in.</p>`;
    }).catch(e => {
      overlay.querySelector("#tgPrevBody").innerHTML = `<p class="muted">Couldn't build the preview: ${esc(e.message)}</p>`;
    });
  }

  async function renderTelegramDashboard() {
    const myToken = activeRouteToken;
    let activeTgTab = "log";
    let activePeriod = "today";

    async function loadPeriod(period) {
      activePeriod = period;
      const box = document.getElementById("tgDashBox");
      if (!box) return;
      box.innerHTML = `<p class="muted">Loading...</p>`;
      let delivery, analytics, mirrorRes, nearMiss;
      try {
        [delivery, analytics, mirrorRes, nearMiss] = await Promise.all([
          apiGet(`/api/paper-trading/telegram/delivery-log?period=${period}`),
          apiGet(`/api/paper-trading/telegram/analytics?period=${period}`).catch(() => null),
          apiGet(`/api/paper-trading/telegram/log?limit=30`).catch(() => ({ messages: [] })),
          apiGet(`/api/paper-trading/telegram/near-misses?limit=200`).catch(() => null),
        ]);
      } catch (e) {
        if (isStaleRoute(myToken)) return;
        box.innerHTML = `<p class="muted">Couldn't load: ${esc(e.message)}</p>`;
        return;
      }
      if (isStaleRoute(myToken)) return;

      const sum = delivery.summary;
      const signals = delivery.signals || [];
      const mirror = mirrorRes.messages || [];
      const o = sum.outcomes;

      box.innerHTML = `
        <div class="headline-band">
          <div class="headline-main tone-flat">
            <div class="headline-label">Signals Generated</div>
            <div class="headline-value">${fmtNum(sum.total_generated)}</div>
            <div class="headline-sub">Everything the system found in this period</div>
          </div>
          <div class="headline-side">
            <div class="headline-label">Actually Delivered</div>
            <div class="headline-value ${sum.delivered ? "tone-up" : ""}">${fmtNum(sum.delivered)}</div>
            <div class="headline-sub">Confirmed as reaching Telegram</div>
          </div>
          <div class="headline-side">
            <div class="headline-label">Held Back or Failed</div>
            <div class="headline-value">${fmtNum(sum.withheld + sum.failed)}</div>
            <div class="headline-sub">${fmtNum(sum.withheld)} withheld &middot; ${fmtNum(sum.failed)} failed</div>
          </div>
        </div>

        <div class="section-title">Where Every Signal Ended Up ${helpIcon("delivery_status")}</div>
        <div class="status-strip">
          ${sum.by_status.length
            ? sum.by_status.map(b => `
              <div class="status-chip">
                <span class="pill ${TG_STATUS_TONE[b.status] || "pill-muted"}">${esc(b.label)}</span>
                <b>${fmtNum(b.count)}</b>
              </div>`).join("")
            : `<div class="muted">No signals were generated in this period.</div>`}
        </div>

        <div class="section-title">How Those Trades Actually Turned Out</div>
        <div class="grid">
          ${card("Won", fmtNum(o.win))}
          ${card("Lost", fmtNum(o.loss))}
          ${card("Still Open", fmtNum(o.pending))}
          ${card("Win Ratio", sum.win_rate_pct != null ? `${sum.win_rate_pct.toFixed(1)}%` : "No finished trades yet")}
        </div>
        <p class="muted plain-note">These are the real results of the trades these signals belonged to, taken straight from Paper Trading. A trade still running always shows as open &mdash; never guessed at.</p>

        <div class="section-title">Signal Log &mdash; Every Signal, Delivered Or Not</div>
        <div class="table-wrap"><table>
          <thead><tr>
            <th>When</th><th>Strategy</th><th>Coin</th><th>Direction</th>
            <th>Entry</th><th>Stop-Loss</th><th>Take-Profit</th><th>Grade</th>
            <th>Delivery ${helpIcon("delivery_status")}</th><th>Result</th><th></th>
          </tr></thead>
          <tbody>${signals.slice(0, 200).map(s => `
            <tr>
              <td>${esc((s.generated_at || "").slice(0, 16).replace("T", " "))}</td>
              <td style="max-width:190px;">${esc(s.strategy_name || "-")}</td>
              <td>${esc(s.symbol || "-")}</td>
              <td><span class="pill ${s.direction === "long" ? "pill-bullish" : "pill-bearish"}">${esc((s.direction || "-").toUpperCase())}</span></td>
              <td>${fmtPrice(s.entry_price)}</td>
              <td>${fmtPrice(s.stop_loss)}</td>
              <td>${fmtPrice(s.take_profit)}</td>
              <td>${s.quality_grade ? esc(s.quality_grade) : (s.confidence != null ? Math.round(s.confidence) + "%" : "-")}</td>
              <td>${tgStatusPill(s)}</td>
              <td>${telegramOutcomePill(s.outcome)}</td>
              <td><button class="btn-ghost tg-preview-btn" data-id="${esc(s.position_id)}">Preview</button></td>
            </tr>`).join("") || `<tr><td colspan="11">No signals were generated in this period.</td></tr>`}</tbody>
        </table></div>
        ${signals.length > 200 ? `<p class="muted plain-note">Showing the 200 most recent of ${fmtNum(signals.length)} signals in this period.</p>` : ""}

        ${nearMiss ? `
        <div class="section-title">Near-Miss Log &mdash; How Close Signals Came to High Confidence</div>
        <p class="muted plain-note">Master Task 5: every real signal that was generated and checked for auto-send, but did not reach High Confidence, gets logged here once (all-time, not just this period) &mdash; with exactly why, and how far short it fell. This builds up automatically over time so the CEO can judge whether the bar is set right without a one-off manual investigation each time.</p>
        <div class="grid">
          ${card("Total Near-Misses Logged", fmtNum(nearMiss.total))}
          ${card("Blocked by Confluence Alone", fmtNum(nearMiss.near_misses.filter(n => (n.confluence_deficit_pct || 0) > 0).length))}
          ${card("Blocked by Statistical Sample Gate", fmtNum(nearMiss.pattern_gate_insufficient_data_count) + ` (need ${nearMiss.pattern_required_trades}+ trades on that exact setup)`)}
        </div>
        <div class="section-title" style="font-size:14px;">Confluence Shortfall Distribution</div>
        <div class="status-strip">
          ${nearMiss.confluence_deficit_bands.length
            ? nearMiss.confluence_deficit_bands.map(b => `
              <div class="status-chip">
                <span class="pill pill-muted">${esc(b.band)}</span>
                <b>${fmtNum(b.count)}</b>
              </div>`).join("")
            : `<div class="muted">No near-misses logged yet.</div>`}
        </div>
        <div class="table-wrap"><table>
          <thead><tr>
            <th>When</th><th>Strategy</th><th>Coin</th><th>Confluence</th><th>Sample Gate</th><th>Why</th>
          </tr></thead>
          <tbody>${nearMiss.near_misses.slice(0, 100).map(n => `
            <tr>
              <td>${esc((n.created_at || "").slice(0, 16).replace("T", " "))}</td>
              <td style="max-width:180px;">${esc(n.strategy_name || "-")}</td>
              <td>${esc(n.symbol || "-")}</td>
              <td>${n.confluence_passed}/${n.confluence_total} aligned (needed ${n.confluence_required_count}+, ratio ${(n.confluence_required_ratio * 100).toFixed(0)}%)</td>
              <td>${n.pattern_trades != null ? `${fmtNum(n.pattern_trades)}/${n.pattern_required} trades` : "-"}</td>
              <td style="max-width:320px; font-size:12px;">${esc(n.reason || "-")}</td>
            </tr>`).join("") || `<tr><td colspan="6">No near-misses logged yet &mdash; this fills in automatically as new signals are evaluated.</td></tr>`}</tbody>
        </table></div>
        ${nearMiss.near_misses.length > 100 ? `<p class="muted plain-note">Showing the 100 most recent of ${fmtNum(nearMiss.near_misses.length)} near-misses logged so far.</p>` : ""}
        ` : ""}

        ${analytics ? `
        <div class="section-title">Telegram-Sent Signals Only &mdash; Real Performance ${helpIcon("delivery_status")}</div>
        <p class="muted plain-note">Every number below counts ONLY signals that genuinely reached Telegram (the High-Confidence-filtered subset) &mdash; never every signal the system generated, and never a hypothetical figure.</p>
        <div class="grid">
          ${card("Signals Sent", fmtNum(analytics.summary.total_signals))}
          ${card("Wins", fmtNum(analytics.summary.wins))}
          ${card("Losses", fmtNum(analytics.summary.losses))}
          ${card("Win Rate", analytics.summary.win_rate_pct != null ? `${analytics.summary.win_rate_pct.toFixed(1)}%` : `Needs ${analytics.summary.min_sample_size}+ finished`)}
          ${card("Total PnL", pnlSpan(analytics.summary.total_pnl))}
          ${card("Best Strategy", analytics.best_strategy
            ? `${esc(analytics.best_strategy.strategy_name)} (${pnlSpan(analytics.best_strategy.total_pnl)})`
            : "Not enough closed trades yet")}
        </div>

        <div class="section-title">Per-Strategy &mdash; Delivered Signals Only</div>
        <p class="muted plain-note">This table counts only signals that genuinely reached Telegram, so it will read lower than the log above whenever delivery is blocked.</p>
        <div class="table-wrap"><table>
          <thead><tr><th>Strategy</th><th>Delivered</th><th>Wins</th><th>Losses</th><th>Still Open</th><th>Win Ratio</th></tr></thead>
          <tbody>${(analytics.strategy_breakdown || []).map(b => `
            <tr>
              <td>${esc(b.strategy_name)}</td>
              <td>${fmtNum(b.total_signals)}</td>
              <td>${fmtNum(b.wins)}</td>
              <td>${fmtNum(b.losses)}</td>
              <td>${fmtNum(b.pending)}</td>
              <td>${b.win_rate_pct != null ? b.win_rate_pct.toFixed(1) + "%" : `Needs ${analytics.summary.min_sample_size}+ finished`}</td>
            </tr>`).join("") || `<tr><td colspan="6">Nothing was delivered in this period.</td></tr>`}</tbody>
        </table></div>` : ""}

        <div class="section-title">Signal Mirror &mdash; Exactly What Was Sent</div>
        <p class="muted plain-note">The real message text stored at the moment each send was attempted &mdash; not a re-generated guess, so this always matches what Telegram actually received.</p>
        <div class="mirror-list">
          ${mirror.map(m => `
            <div class="card mirror-card">
              <div class="mirror-head">
                <div>
                  <b>${esc(m.strategy_name || "Unknown strategy")}</b>
                  <span class="muted" style="font-size:12px;"> &mdash; ${esc(m.trigger_type)} &mdash; ${esc((m.sent_at || "").slice(0, 16).replace("T", " "))}</span>
                </div>
                ${tgStatusPill({
                  delivery_status: m.success ? "sent" : "blocked_network",
                  delivery_label: m.success ? "Sent" : "Not delivered",
                  delivery_detail: m.error,
                })}
              </div>
              ${m.message_text
                ? `<div class="tg-preview">${renderTelegramMessageHtml(m.message_text)}</div>`
                : `<div class="muted" style="font-size:12px;">No message text &mdash; it was stopped before the message was even written. ${esc(m.error || "")}</div>`}
            </div>`).join("") || `<p class="muted">No send has been attempted yet.</p>`}
        </div>
      `;
      box.querySelectorAll(".tg-preview-btn").forEach(btn => {
        btn.onclick = () => openTelegramPreviewModal(btn.dataset.id);
      });
    }

    const [cs, tgAlert] = await Promise.all([
      apiGet("/api/paper-trading/telegram/connection-status").catch(() => ({ state: "unknown", reason: "Status unavailable.", settings: {} })),
      apiGet(`/api/paper-trading/telegram/alert-status?lang=${getLang()}`).catch(() => ({ stale: false })),
    ]);
    if (isStaleRoute(myToken)) return;
    const s = cs.settings || {};

    content.innerHTML = `
      <div class="page-head">
        <div>
          <div class="page-eyebrow">Paper Trading</div>
          <h2 class="page-title">Telegram</h2>
          <p class="page-lede">Every signal the system produced, and honestly what happened to each one. Nothing here is shown as sent unless it truly reached Telegram.</p>
        </div>
      </div>

      ${tgAlert.stale ? `<div class="notice notice-warn">${esc(tgAlert.message)}</div>` : ""}

      ${tgConnectionPanelHtml(cs)}

      <div class="pill-tabs">
        <button class="pill-tab active" data-tg-tab="log">Signal Log</button>
        <button class="pill-tab" data-tg-tab="settings">Settings</button>
      </div>

      <div data-tg-panel="log">
        ${paperPeriodTabsHtml("tgdash", "today")}
        <div id="tgDashBox"><p class="muted">Loading...</p></div>
      </div>

      <div data-tg-panel="settings" style="display:none;">
        <div class="section-title">Delivery</div>
        <div class="card settings-card">
          <label class="switch-row">
            <input type="checkbox" id="tgMasterSwitch" ${s.master_send_enabled ? "checked" : ""}>
            <span><b>Send signals to Telegram</b><br><span class="muted">When this is off, nothing at all goes out &mdash; not a manual send, not an automatic one &mdash; no matter how strong a signal looks.</span></span>
          </label>
          <label class="switch-row">
            <input type="checkbox" id="tgAutoSwitch" ${s.auto_send_enabled ? "checked" : ""}>
            <span><b>Send strong signals automatically</b><br><span class="muted">When on, the system checks each open trade on its own and sends the ones that clear its confidence bar. It never lowers that bar.</span></span>
          </label>
          <span id="tgSettingsStatus" class="muted"></span>
        </div>

        <div class="section-title">Connection (for when the block is lifted)</div>
        <div class="card settings-card">
          <p class="muted plain-note">Telegram is blocked on this internet connection, so messages cannot get through directly. A working proxy, or running this on a cloud server, fixes that. Fill these in and everything above starts delivering on its own &mdash; nothing else needs rebuilding.</p>
          <label class="switch-row">
            <input type="checkbox" id="tgProxyEnabled" ${s.proxy_enabled ? "checked" : ""}>
            <span><b>Route through a proxy</b></span>
          </label>
          <div class="form-row">
            <label>Proxy address</label>
            <input id="tgProxyUrl" placeholder="${s.proxy_configured ? "•••••• (one is already saved)" : "socks5://user:pass@host:1080"}">
          </div>
          <div class="btn-row">
            <button class="btn" id="tgSaveProxy">Save connection settings</button>
            <button class="btn-ghost" id="tgTestProxy">Test the proxy only</button>
            <button class="btn-ghost" id="tgTestSend">Send a real test message</button>
          </div>
          <span id="tgProxyStatus" class="muted"></span>
        </div>

        <div class="section-title">Safety Gate</div>
        <div class="card settings-card">
          <div class="settings-readonly">
            <div><span class="muted">Freshness limit ${helpIcon("signal_freshness")}</span><b>${s.signal_freshness_minutes != null ? s.signal_freshness_minutes + " minutes" : "-"}</b></div>
            <div><span class="muted">Price-drift limit</span><b>${s.signal_price_drift_pct != null ? s.signal_price_drift_pct + "%" : "-"}</b></div>
            <div><span class="muted">Most messages per hour</span><b>${s.rate_limit_per_hour != null ? s.rate_limit_per_hour : "-"}</b></div>
          </div>
          <p class="muted plain-note">Shown here so you can see the rule that is protecting you, but deliberately not editable from this screen &mdash; this is the gate that stops an out-of-date signal from ever being sent, and it is not something a stray click should be able to weaken.</p>
        </div>
      </div>
    `;


    content.querySelectorAll("[data-tg-tab]").forEach(btn => {
      btn.onclick = () => {
        activeTgTab = btn.dataset.tgTab;
        content.querySelectorAll("[data-tg-tab]").forEach(b => b.classList.toggle("active", b === btn));
        content.querySelectorAll("[data-tg-panel]").forEach(panel => {
          panel.style.display = panel.dataset.tgPanel === activeTgTab ? "" : "none";
        });
      };
    });

    const setStatus = (id, text) => { const el = document.getElementById(id); if (el) el.textContent = text; };

    document.getElementById("tgMasterSwitch").addEventListener("change", async (e) => {
      setStatus("tgSettingsStatus", "Saving...");
      try {
        await apiPost("/api/paper-trading/telegram/settings", { master_send_enabled: e.target.checked });
        setStatus("tgSettingsStatus", e.target.checked ? "Sending is on." : "Sending is off -- nothing will go out.");
        appendLog(`[Telegram] Sending turned ${e.target.checked ? "ON" : "OFF"}.`);
      } catch (err) {
        setStatus("tgSettingsStatus", "Save failed -- try again.");
        e.target.checked = !e.target.checked;
      }
    });
    document.getElementById("tgAutoSwitch").addEventListener("change", async (e) => {
      setStatus("tgSettingsStatus", "Saving...");
      try {
        await apiPost("/api/paper-trading/telegram/settings", { auto_send_enabled: e.target.checked });
        setStatus("tgSettingsStatus", e.target.checked ? "Automatic sending is on." : "Automatic sending is off.");
        appendLog(`[Telegram] Auto-send turned ${e.target.checked ? "ON" : "OFF"}.`);
      } catch (err) {
        setStatus("tgSettingsStatus", "Save failed -- try again.");
        e.target.checked = !e.target.checked;
      }
    });
    document.getElementById("tgSaveProxy").onclick = async () => {
      setStatus("tgProxyStatus", "Saving...");
      const body = { proxy_enabled: document.getElementById("tgProxyEnabled").checked };
      const url = document.getElementById("tgProxyUrl").value.trim();
      if (url) body.proxy_url = url;
      try {
        await apiPost("/api/paper-trading/telegram/settings", body);
        setStatus("tgProxyStatus", "Saved.");
      } catch (e) { setStatus("tgProxyStatus", `Failed: ${e.message}`); }
    };
    document.getElementById("tgTestProxy").onclick = async () => {
      setStatus("tgProxyStatus", "Testing the proxy (this can take a moment)...");
      try {
        const r = await apiPost("/api/paper-trading/telegram/test-proxy", {}, 120000);
        setStatus("tgProxyStatus", r.ok
          ? `The proxy works. It reaches the internet as ${r.exit_ip}.`
          : `The proxy did not work: ${r.error}`);
      } catch (e) { setStatus("tgProxyStatus", `Failed: ${e.message}`); }
    };
    document.getElementById("tgTestSend").onclick = async () => {
      setStatus("tgProxyStatus", "Sending a real test message (this can take a moment)...");
      try {
        const r = await apiPost("/api/paper-trading/telegram/test", {}, 120000);
        setStatus("tgProxyStatus", r.ok
          ? "It worked -- check your Telegram channel."
          : `It did not get through: ${r.error}`);
      } catch (e) { setStatus("tgProxyStatus", `Failed: ${e.message}`); }
    };

    await loadPeriod("today");
    content.querySelectorAll('[data-period-tab="tgdash"]').forEach(btn => {
      btn.onclick = () => {
        content.querySelectorAll('[data-period-tab="tgdash"]').forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        loadPeriod(btn.dataset.period).catch(console.error);
      };
    });

    onLive((msg) => {
      if (msg.channel === "job" || msg.channel === "sync") {
        loadPeriod(activePeriod).catch(console.error);
      }
    });
  }

  // ------------------------------------------------------------ EVOLUTION (Phase 7A, Part A)
  async function renderEvolution() {
    const myToken = activeRouteToken;

    async function render() {
      const [status, championsRes, strategiesRes, lessonsRes, versionsRes, correlationsRes, comparisonsRes, weeklyReviewsRes] = await Promise.all([
        apiGet("/api/evolution/status"),
        apiGet("/api/evolution/champions"),
        apiGet("/api/evolution/strategies"),
        apiGet("/api/evolution/lessons"),
        apiGet("/api/evolution/knowledge-versions?limit=1"),
        apiGet("/api/evolution/research/dna-correlations?min_sample=1"),
        apiGet("/api/evolution/comparisons?limit=50"),
        apiGet("/api/evolution/weekly-reviews?limit=1").catch(() => ({ reports: [] })),
      ]);
      if (isStaleRoute(myToken)) return;

      const gov = status.governor;
      const champions = championsRes.champions || [];
      const strategies = strategiesRes.strategies || [];
      const lessons = lessonsRes.lessons || [];
      const latestVersion = (versionsRes.versions || [])[0];
      const correlations = correlationsRes.correlations || [];
      const comparisons = comparisonsRes.comparisons || [];

      const championRow = (label, cat) => {
        const c = champions.find(x => x.category === cat);
        return `<tr><td>${label}</td><td>${c ? esc(String(c.value)) : "-"}</td><td>${c ? Number(c.score).toFixed(2) : "-"}</td></tr>`;
      };

      content.innerHTML = `
        <div class="section-title">Evolution Engine</div>
        <p class="muted">Continuously Analyzes, Compares, Mutates, Ranks, and Archives BOT-owned strategies and lessons -- pure deterministic logic, zero AI, never touches user-imported strategies or user-written lessons.</p>
        <div class="grid">
          ${cardClass("Status", status.running ? "<span class=\"pill pill-completed\">Running</span>" : "<span class=\"pill pill-muted\">Stopped</span>", "")}
          ${card("CPU", `${gov.cpu_percent.toFixed(1)}% <span class="muted">/ ${gov.cpu_limit_percent}% limit</span>`)}
          ${card("RAM", `${gov.ram_percent.toFixed(1)}% <span class="muted">/ ${gov.ram_limit_percent}% limit</span>`)}
          ${card("Research Queue", `${fmtNum(gov.queue_size)} <span class="muted">/ ${gov.max_queue_size} max</span>`)}
          ${card("Experiments This Run", `${fmtNum(gov.experiments_this_run)} <span class="muted">/ ${gov.max_experiments_per_run} max</span>`)}
          ${card("Max Generations / Strategy", fmtNum(gov.max_generations_per_strategy))}
          ${card("Knowledge Version", latestVersion ? `V${latestVersion.version}` : "-")}
          ${card("BOT Strategies (active)", fmtNum(strategies.length))}
        </div>

        <div class="section-title">Control Center</div>
        <div class="btn-row">
          <button class="btn" id="evoStart" ${status.running ? "disabled" : ""}>Start Engine</button>
          <button class="btn-ghost" id="evoStop" ${status.running ? "" : "disabled"}>Stop Engine</button>
          <button class="btn-ghost" id="evoRunTick">Run One Tick Now</button>
          <span id="evoStatusMsg" class="muted"></span>
        </div>

        <div class="section-title">Champion Engine</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Category</th><th>Champion</th><th>Score</th></tr></thead>
          <tbody>
            ${championRow("Strategy", "strategy")}
            ${championRow("Lesson", "lesson")}
            ${championRow("Coin", "coin")}
            ${championRow("Session", "session")}
            ${championRow("Timeframe", "timeframe")}
            ${championRow("Market Condition", "market_condition")}
            ${championRow("Generation", "generation")}
          </tbody>
        </table></div>

        <div class="section-title">BOT Strategies (${strategies.length})</div>
        <div class="table-wrap"><table>
          <thead><tr><th>ID</th><th>Generation</th><th>Origin</th><th>Evolution Score</th><th>Created</th><th></th></tr></thead>
          <tbody>
            ${strategies.slice(0, 100).map(s => `
              <tr>
                <td>${esc(s.name)} <span class="muted">(${esc(s.id)})</span></td>
                <td>Gen ${s.generation}</td>
                <td><span class="pill ${s.made_with_ai ? "pill-bullish" : "pill-muted"}">${s.origin}</span></td>
                <td>${s.evolution_score != null ? Number(s.evolution_score).toFixed(2) : "not backtested"}</td>
                <td>${esc((s.created_at || "").slice(0, 19))}</td>
                <td><button class="btn-ghost evo-explain-btn" data-base-id="${esc(s.base_id)}">Explain ${helpIcon("strategy_lineage_explainer")}</button></td>
              </tr>`).join("") || '<tr><td colspan="6">No BOT strategies yet -- the Evolution Engine mutates existing lineages, and SINDHU Strategy creates new ones.</td></tr>'}
          </tbody>
        </table></div>
        <div id="evoExplainBox" class="card" style="display:none;"></div>

        <div class="section-title">${getLang() === "en" ? "Automated Weekly Strategy Review" : "Automated Weekly Strategy Review"} ${helpIcon("evolution_weekly_review")}</div>
        <div class="card">
          ${weeklyReviewsRes.reports.length ? `
            <div style="white-space:pre-wrap;font-size:13px;">${esc(weeklyReviewsRes.reports[0].report_text)}</div>
            <div class="muted" style="font-size:11px;margin-top:6px;">${esc((weeklyReviewsRes.reports[0].created_at || "").slice(0, 19))}</div>
          ` : `<p class="muted">${getLang() === "en" ? "No weekly review generated yet." : "Abhi tak koi weekly review nahi bani."}</p>`}
          <div class="btn-row" style="margin-top:8px;">
            <button class="btn-ghost" id="btnGenEvoWeeklyReview">${getLang() === "en" ? "Generate Now" : "Abhi Banayein"}</button>
          </div>
        </div>

        <div class="section-title">Evolution Before/After Comparisons (${comparisons.length})</div>
        <p class="muted">Every time a BOT strategy lineage crosses a 100-completed-trades milestone (100, 200, 300...), it evolves into a new generation. This shows the parent's real numbers ("before") against the new generation's real numbers ("after") once it has 100 trades of its own -- and whether it was automatically rolled back for performing worse.</p>
        <div class="table-wrap"><table>
          <thead><tr><th>Lineage</th><th>Trades Threshold</th><th>Win Rate (before -&gt; after)</th><th>Net PnL (before -&gt; after)</th><th>Profit Factor (before -&gt; after)</th><th>Max Drawdown (before -&gt; after)</th><th>Result</th><th>Confidence ${helpIcon("evolution_confidence")}</th></tr></thead>
          <tbody>
            ${comparisons.map(c => {
              const fmt = (v, suffix = "") => v == null ? "-" : `${Number(v).toFixed(2)}${suffix}`;
              const pair = (key, suffix = "") => `${fmt(c.before[key], suffix)} -&gt; ${c.after ? fmt(c.after[key], suffix) : "pending"}`;
              const resultPill = !c.after
                ? `<span class="pill pill-muted">Awaiting 100 trades</span>`
                : c.rolled_back
                  ? `<span class="pill pill-bearish">Rolled back to parent</span>`
                  : `<span class="pill pill-bullish">Kept -- improved</span>`;
              const conf = c.confidence && c.confidence.confidence_score != null
                ? `<span class="${c.confidence.confidence_score >= 70 ? "positive" : c.confidence.confidence_score >= 40 ? "" : "negative"}">${c.confidence.confidence_score}/100</span>`
                : `<span class="muted">-</span>`;
              return `
              <tr>
                <td>${esc(c.base_id)} <span class="muted">(${esc(c.parent_id)} -&gt; ${esc(c.child_id)})</span></td>
                <td>${c.trade_threshold}</td>
                <td>${pair("win_rate", "%")}</td>
                <td>${pair("total_pnl")}</td>
                <td>${pair("avg_profit_factor")}</td>
                <td>${pair("max_drawdown_pct", "%")}</td>
                <td>${resultPill}</td>
                <td>${conf}</td>
              </tr>`;
            }).join("") || '<tr><td colspan="8">No evolution events yet -- a lineage needs 100 completed backtest trades before it evolves.</td></tr>'}
          </tbody>
        </table></div>

        <div class="section-title">Self-Generated Lessons (${lessons.length})</div>
        <div class="table-wrap"><table>
          <thead><tr><th>ID</th><th>Title</th><th>Confidence</th></tr></thead>
          <tbody>
            ${lessons.slice(0, 50).map(l => `
              <tr><td>${esc(l.id)}</td><td>${esc(l.title)}</td><td>${l.confidence != null ? Number(l.confidence).toFixed(0) + "%" : "-"}</td></tr>
            `).join("") || '<tr><td colspan="3">No self-generated lessons yet -- these appear automatically as paper-trading positions close.</td></tr>'}
          </tbody>
        </table></div>

        <div class="section-title">Research: DNA Correlations</div>
        <p class="muted">Which combinations of DNA blocks (Trend/Momentum/Liquidity/Volume/Breakout/Session/Risk) have historically scored best -- feeds the SINDHU Strategy Generator's deterministic candidates.</p>
        <div class="table-wrap"><table>
          <thead><tr><th>DNA Combo</th><th>Avg Score</th><th>Sample Size</th></tr></thead>
          <tbody>
            ${correlations.slice(0, 20).map(c => `
              <tr><td>${esc(c.dna_combo.join(" + "))}</td><td>${c.avg_score}</td><td>${c.sample_size}</td></tr>
            `).join("") || '<tr><td colspan="3">No scored BOT strategies yet.</td></tr>'}
          </tbody>
        </table></div>`;

      document.getElementById("evoStart").onclick = async () => {
        document.getElementById("evoStatusMsg").textContent = "Starting...";
        try { await apiPost("/api/evolution/start"); await render(); }
        catch (e) { document.getElementById("evoStatusMsg").textContent = `Failed: ${e.message}`; }
      };
      document.getElementById("evoStop").onclick = async () => {
        document.getElementById("evoStatusMsg").textContent = "Stopping...";
        try { await apiPost("/api/evolution/stop"); await render(); }
        catch (e) { document.getElementById("evoStatusMsg").textContent = `Failed: ${e.message}`; }
      };
      document.getElementById("evoRunTick").onclick = async () => {
        document.getElementById("evoStatusMsg").textContent = "Running one tick...";
        try { await apiPost("/api/evolution/run-tick"); document.getElementById("evoStatusMsg").textContent = "Done."; await render(); }
        catch (e) { document.getElementById("evoStatusMsg").textContent = `Failed: ${e.message}`; }
      };
      document.getElementById("btnGenEvoWeeklyReview").onclick = async () => {
        try {
          await apiPost("/api/evolution/weekly-reviews/generate-now");
          await render();
        } catch (e) {
          alert(e.message || "Could not generate.");
        }
      };
      document.querySelectorAll(".evo-explain-btn").forEach(btn => {
        btn.onclick = async () => {
          const box = document.getElementById("evoExplainBox");
          box.style.display = "block";
          box.innerHTML = `<p class="muted">Loading...</p>`;
          box.scrollIntoView({ behavior: "smooth", block: "nearest" });
          try {
            const r = await apiGet(`/api/evolution/strategies/${btn.dataset.baseId}/explain`);
            box.innerHTML = `
              <div class="label">Lineage ${esc(r.base_id)} -- ${r.generation_count} generation(s), currently on Gen ${r.active_generation}</div>
              <p style="margin-top:8px;line-height:1.5;">${esc(r.narrative)}</p>`;
          } catch (e) {
            box.innerHTML = `<p class="muted">${esc(e.message)}</p>`;
          }
        };
      });
    }

    await render();
  }

  // ------------------------------------------------------------ Evolution History Timeline (Batch 6, Task 1)
  const EVOLUTION_HISTORY_WINDOWS = [
    ["week", "This Week"], ["15d", "Last 15 Days"], ["month", "This Month"], ["longer", "Longer (120 Days)"],
  ];

  async function renderEvolutionHistory() {
    const myToken = activeRouteToken;
    let activeWindow = "week";

    async function render() {
      const result = await apiGet(`/api/evolution/history/compare?window=${activeWindow}`);
      if (isStaleRoute(myToken)) return;
      const cur = result.current;
      const prev = result.previous;

      const fmt = (v, suffix = "") => v == null ? "-" : `${Number(v).toFixed(2)}${suffix}`;
      const pair = (block, key, suffix = "") => `${fmt(block.before[key], suffix)} → ${block.after[key] == null ? (getLang() === "en" ? "pending" : "abhi tak nahi") : fmt(block.after[key], suffix)}`;
      const delta = (curVal, prevVal) => {
        if (curVal == null || prevVal == null) return "";
        const diff = curVal - prevVal;
        if (Math.abs(diff) < 0.001) return "";
        const cls = diff > 0 ? "positive" : "negative";
        return ` <span class="${cls}">(${diff > 0 ? "+" : ""}${diff.toFixed(0)} ${getLang() === "en" ? "vs last period" : "pichle period se"})</span>`;
      };

      content.innerHTML = `
        <div class="section-title">${getLang() === "en" ? "Evolution History" : "Evolution Ki Tareekh"}</div>
        <p class="muted">${getLang() === "en"
          ? "Real self-learning activity over time, straight from the same 100-trade gate records the Evolution page already tracks -- this view never starts, stops, or changes anything, it only reports."
          : "Waqt ke saath asli self-learning activity, wahi 100-trade gate records se jo Evolution page pehle se track karta hai -- yeh sirf report karta hai, kuch shuru ya band nahi karta."}</p>

        <div class="btn-row">
          ${EVOLUTION_HISTORY_WINDOWS.map(([key, label]) =>
            `<button class="btn${activeWindow === key ? "" : "-ghost"}" data-window="${key}">${label}</button>`).join("")}
        </div>

        <div class="grid">
          ${cardClass("Strategies Evolved", `${fmtNum(cur.strategies_evolved)}${delta(cur.strategies_evolved, prev.strategies_evolved)}`, "")}
          ${card("New Generations Created", fmtNum(cur.generations_created))}
          ${cardClass("Rollbacks", `${fmtNum(cur.rollbacks)}${delta(cur.rollbacks, prev.rollbacks)}`, cur.rollbacks > 0 ? "negative" : "")}
          ${card("Improved (Kept)", fmtNum(cur.improved))}
          ${card("Still Awaiting 100 Trades", fmtNum(cur.pending))}
        </div>
        <div class="muted" style="font-size:12px;margin-top:-8px;">
          ${getLang() === "en" ? "Previous period (for comparison)" : "Pichla period (comparison ke liye)"}:
          ${prev.strategies_evolved} ${getLang() === "en" ? "strategies evolved" : "strategies evolve hui"},
          ${prev.rollbacks} rollbacks.
        </div>

        <div class="section-title">${getLang() === "en" ? "Average Before → After (this period)" : "औसत Before → After (is period mein)"}</div>
        <div class="table-wrap"><table>
          <thead><tr><th>${getLang() === "en" ? "Metric" : "Metric"}</th><th>${getLang() === "en" ? "Before → After" : "Pehle → Baad"}</th></tr></thead>
          <tbody>
            <tr><td>${getLang() === "en" ? "Win Rate" : "Jeetne Ki Dar"}</td><td>${pair(cur, "win_rate", "%")}</td></tr>
            <tr><td>${getLang() === "en" ? "Net PnL" : "Asli Munafa/Nuksan"}</td><td>${pair(cur, "total_pnl")}</td></tr>
            <tr><td>Profit Factor</td><td>${pair(cur, "avg_profit_factor")}</td></tr>
            <tr><td>${getLang() === "en" ? "Max Drawdown" : "Sabse Zyada Drawdown"}</td><td>${pair(cur, "max_drawdown_pct", "%")}</td></tr>
          </tbody>
        </table></div>
        ${cur.finalized === 0 ? `<div class="muted" style="font-size:12px;">${getLang() === "en"
          ? "No evolution events in this window have finished being judged yet (each needs 100 real trades on the new generation) -- averages will appear once at least one has."
          : "Is period mein abhi tak koi evolution event poori tarah judge nahi hua (har ek ko naye generation par 100 real trades chahiye) -- averages tab dikhenge jab kam se kam ek poora ho jaye."}</div>` : ""}

        <div class="section-title">${getLang() === "en" ? "Events In This Window" : "Is Period Ke Events"} (${cur.comparisons.length})</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Lineage</th><th>${getLang() === "en" ? "Trades Threshold" : "Trades Ki Had"}</th><th>${getLang() === "en" ? "Result" : "Nateeja"}</th><th>${getLang() === "en" ? "When" : "Kab"}</th></tr></thead>
          <tbody>
            ${cur.comparisons.map(c => {
              const resultPill = !c.after
                ? `<span class="pill pill-muted">${getLang() === "en" ? "Awaiting 100 trades" : "100 trades ka intezaar"}</span>`
                : c.rolled_back
                  ? `<span class="pill pill-bearish">${getLang() === "en" ? "Rolled back" : "Wapas kar diya gaya"}</span>`
                  : `<span class="pill pill-bullish">${getLang() === "en" ? "Kept -- improved" : "Rakha gaya -- behtar hua"}</span>`;
              return `<tr>
                <td>${esc(c.base_id)} <span class="muted">(${esc(c.parent_id)} → ${esc(c.child_id)})</span></td>
                <td>${c.trade_threshold}</td>
                <td>${resultPill}</td>
                <td>${esc((c.created_at || "").slice(0, 10))}</td>
              </tr>`;
            }).join("") || `<tr><td colspan="4">${getLang() === "en" ? "No evolution events in this window." : "Is period mein koi evolution event nahi hua."}</td></tr>`}
          </tbody>
        </table></div>`;

      document.querySelectorAll("[data-window]").forEach(btn => btn.onclick = () => {
        activeWindow = btn.dataset.window;
        render();
      });
    }

    await render();
  }

  // ------------------------------------------------------------ STRATEGY LAB
  async function renderStrategyLab() {
    const myToken = activeRouteToken;

    async function render() {
      const result = await apiGet("/api/strategy-lab/latest");
      if (isStaleRoute(myToken)) return;
      const en = getLang() === "en";
      const scan = result.scan;
      const q = scan.qualifying_strategy_id ? scan : null;

      content.innerHTML = `
        <div class="section-title">${en ? "Strategy Lab" : "Strategy Lab"}</div>
        <p class="muted">${en
          ? `On a weekly schedule, checks every real strategy's actual paper trading record for one that's genuinely profitable -- real, after-cost results, with at least ${result.min_closed_trades} closed trades and a real win rate of ${result.min_win_rate}% or better. Never presents a losing or weak strategy as "best" just to have something to show.`
          : `Har hafte, har asli strategy ka asli paper trading record check karta hai kisi genuinely profitable strategy ke liye -- asli, cost ke baad results, kam se kam ${result.min_closed_trades} band trades aur ${result.min_win_rate}% ya usse behtar asli win rate ke saath. Kabhi bhi haarti hui ya kamzor strategy ko "best" bana kar nahi dikhata.`}</p>

        <div class="btn-row">
          <button class="btn-ghost" id="slScanNow">${en ? "Scan Now" : "Abhi Scan Karein"}</button>
        </div>

        ${q ? `
          <div class="section-title">${en ? "Genuinely Profitable Strategy Found" : "Genuinely Profitable Strategy Mil Gayi"}</div>
          <div class="grid">
            ${card("Strategy", esc(q.qualifying_strategy_name || q.qualifying_strategy_id))}
            ${cardClass("Win Rate", `${q.qualifying_win_rate.toFixed(1)}%`, "positive")}
            ${cardClass("PnL", `${q.qualifying_pnl >= 0 ? "+" : ""}$${q.qualifying_pnl.toFixed(2)}`, q.qualifying_pnl >= 0 ? "positive" : "negative")}
            ${card("Trade Count", fmtNum(q.qualifying_trade_count))}
          </div>
          ${q.approved
            ? `<p class="muted">${en
                ? `Approved ${esc((q.approved_at || "").slice(0, 16).replace("T", " "))} -- now enabled in live Paper Trading and flagged for Telegram alerts.`
                : `${esc((q.approved_at || "").slice(0, 16).replace("T", " "))} ko approve ki gayi -- ab live Paper Trading mein enabled hai aur Telegram alerts ke liye flag ki gayi hai.`}</p>`
            : `<p>${en
                ? "This strategy has cleared the real profitability bar, but nothing has been enabled automatically. Approving below turns it on in live Paper Trading and flags it for Telegram alerts -- nothing else changes."
                : "Yeh strategy asli profitability ki had paar kar chuki hai, lekin kuch bhi khud ba khud enable nahi hua. Neeche approve karne se yeh live Paper Trading mein on ho jayegi aur Telegram alerts ke liye flag ho jayegi -- aur kuch nahi badlega."}</p>
               <button class="btn" id="slApprove">${en ? "Approve -- Enable in Live Paper Trading + Telegram" : "Approve Karein -- Live Paper Trading + Telegram Mein Enable Karein"}</button>`}
        ` : `
          <div class="section-title">${en ? "No Profitable Strategy Yet" : "Abhi Tak Koi Profitable Strategy Nahi Mili"}</div>
          <p>${en
            ? `Abhi tak koi profitable strategy nahi mili. Checked ${scan.strategies_checked} strategies' real paper trading records -- none has both a real edge (positive PnL after cost) and a reliable win rate (${result.min_win_rate}%+) over at least ${result.min_closed_trades} closed trades yet.`
            : `Abhi tak koi profitable strategy nahi mili. ${scan.strategies_checked} strategies ke asli paper trading records check kiye -- abhi tak kisi ne bhi asli edge (cost ke baad positive PnL) aur bharosemand win rate (${result.min_win_rate}%+) kam se kam ${result.min_closed_trades} band trades par nahi dikhaya.`}</p>
        `}

        <p class="muted" style="font-size:12px;">${en ? "Last scanned" : "Aakhri scan"}: ${esc((scan.scanned_at || "").slice(0, 16).replace("T", " "))} (${scan.strategies_checked} ${en ? "strategies checked" : "strategies check kiye"})</p>
      `;

      document.getElementById("slScanNow").onclick = async () => {
        await apiSend("POST", "/api/strategy-lab/scan-now", {});
        render();
      };
      const approveBtn = document.getElementById("slApprove");
      if (approveBtn) {
        approveBtn.onclick = async () => {
          approveBtn.disabled = true;
          try {
            await apiSend("POST", "/api/strategy-lab/approve", { scan_id: scan.id, strategy_id: q.qualifying_strategy_id });
            render();
          } catch (e) {
            alert(e.message || String(e));
            approveBtn.disabled = false;
          }
        };
      }
    }

    await render();
  }

  // ------------------------------------------------------------ SELF-LEARNING ENGINE
  // Master Task 3, Phase 1: deliberately its own page, not folded into
  // Evolution or Strategy Lab -- this discovers brand-new candidate
  // strategies by combining concepts, a genuinely different mechanism from
  // both (Evolution only tweaks existing strategies; Strategy Lab only
  // reads already-existing real records, it invents nothing).
  async function renderSelfLearning() {
    const myToken = activeRouteToken;
    const en = getLang() === "en";

    async function render() {
      // Master Task 4, Phase 0: the Self-Learning Engine's discovery cycles
      // need the full local historical candle database + real backtest
      // pipeline (same reason Evolution/Backtesting are also local-only) --
      // its API router is deliberately never mounted on the lightweight
      // cloud runner (see sindhu_web/api/self_learning.py's own docstring).
      // On a cloud deploy these calls 404; catch that here and explain WHY
      // plainly instead of showing a raw "Failed to load page" error, so
      // the page is genuinely findable/understandable everywhere, even
      // where the engine itself can't run.
      let status, cycles, attempts, scores, overview;
      try {
        [status, cycles, attempts, scores, overview] = await Promise.all([
          apiGet("/api/self-learning/status"),
          apiGet("/api/self-learning/cycles?limit=10"),
          apiGet("/api/self-learning/attempts?limit=30"),
          apiGet("/api/self-learning/combination-scores"),
          // Phase 0.3: accepted candidates are just regular saved strategies
          // tagged "self-learning-discovered" (discovery_cycle.py) -- reuse
          // the same dual-row overview data the Strategies page already
          // computes, filtered client-side, instead of a new endpoint.
          apiGet("/api/paper-trading/strategy-overview"),
        ]);
      } catch (e) {
        if (isStaleRoute(myToken)) return;
        content.innerHTML = `
          <div class="section-title">${en ? "Self-Learning Engine" : "Self-Learning Engine"}</div>
          <div class="card">
            <p>${en
              ? "This feature is not available on the cloud dashboard. Discovering brand-new strategies requires running real backtests against the full historical price database, which (by design, to keep the free cloud server light) only exists on your local computer -- the same reason the Evolution Engine and Backtesting pages also aren't on this cloud dashboard."
              : "Yeh feature cloud dashboard par available nahi hai. Naye strategies discover karne ke liye asli backtests chalane padte hain, jo poori historical price database maangte hain -- yeh database (jaanbujh kar, free cloud server ko halka rakhne ke liye) sirf aapke local computer par maujood hai. Isi wajah se Evolution Engine aur Backtesting pages bhi is cloud dashboard par nahi hain."}</p>
            <p class="muted" style="font-size:12.5px;">${en
              ? "Open the SINDHU app on your own computer (E:\\\\sindhu) to see live Self-Learning status, past discovery cycles, and to click \"Run Discovery Cycle Now.\""
              : "Live Self-Learning status, purane discovery cycles dekhne aur \"Run Discovery Cycle Now\" dabane ke liye apne computer par (E:\\\\sindhu) SINDHU app kholein."}</p>
          </div>`;
        return;
      }
      if (isStaleRoute(myToken)) return;

      const latest = status.latest_cycle;
      const latestReport = latest && latest.report_json;
      const discovered = (overview.strategies || []).filter(s => (s.tags || []).includes("self-learning-discovered"));

      content.innerHTML = `
        <div class="section-title">${en ? "Self-Learning Engine" : "Self-Learning Engine"}</div>
        <p class="muted">${en
          ? "Discovers brand-new candidate strategies by combining existing proven concepts in new ways -- distinct from the Evolution Engine, which only tweaks existing strategies. Runs at most once a week, and a candidate is only saved to the strategy library if it independently passes an out-of-sample test in BOTH an earlier and a later period."
          : "Naye candidate strategies banata hai, existing proven concepts ko naye tareeqon se combine karke -- Evolution Engine se alag, jo sirf existing strategies mein chhoti tabdeeliyan karta hai. Hafte mein ek baar se zyada nahi chalta, aur koi candidate tab hi strategy library mein save hota hai jab wo ek pehle aur ek baad ke period, dono mein alag alag out-of-sample test paas kare."}</p>

        <div class="btn-row">
          <button class="btn" id="slRunNow" ${status.run_in_progress ? "disabled" : ""}>${status.run_in_progress
            ? (en ? "Running..." : "Chal Raha Hai...")
            : (en ? "Run Discovery Cycle Now" : "Abhi Discovery Cycle Chalayein")}</button>
          <span class="muted" style="font-size:12px;align-self:center;">${status.would_run_now
            ? (en ? "A new weekly cycle is due." : "Naya weekly cycle due hai.")
            : (en ? "Not due yet this week (or disabled in Feature Control)." : "Is hafte abhi due nahi (ya Feature Control mein disabled hai).")}</span>
        </div>

        ${latestReport ? `
          <div class="section-title">${en ? "Most Recent Discovery Cycle" : "Sabse Haaliya Discovery Cycle"}</div>
          <div class="grid">
            ${card(en ? "Concepts Tried" : "Concepts Try Kiye", esc((latestReport.drawn_concepts || []).join(", ") || "-"))}
            ${cardClass(en ? "Outcome" : "Outcome", esc((latestReport.outcome || latest.status || "-").toUpperCase()),
              latestReport.outcome === "accepted" ? "positive" : latestReport.outcome === "rejected" ? "negative" : "")}
            ${card(en ? "AI-Assisted?" : "AI-Assisted?", latestReport.ai_used ? (en ? "Yes" : "Haan") : (en ? "No (real-data ranking only)" : "Nahi (sirf real-data ranking)"))}
          </div>
          <p style="white-space:pre-line;font-size:13px;">${esc(latestReport.narrative || "")}</p>
        ` : `<p class="muted">${en ? "No discovery cycle has run yet." : "Abhi tak koi discovery cycle nahi chala."}</p>`}

        <div class="section-title">${en ? "Discovered Strategies (Accepted)" : "Discover Ki Gayi Strategies (Accepted)"}</div>
        <div class="grid">${discovered.length
          ? discovered.map(s => strategyOverviewCard(s, en)).join("")
          : `<p class="muted">${en
              ? "No candidate has been accepted yet -- a candidate only lands here once it independently passes the out-of-sample test in both periods."
              : "Abhi tak koi candidate accepted nahi hua -- koi candidate yahan tabhi aata hai jab wo dono periods mein alag alag out-of-sample test paas kare."}</p>`}</div>

        <div class="section-title">${en ? "What The Engine Currently Sees As Best" : "Engine Ko Abhi Kya Best Lag Raha Hai"}</div>
        <div class="table-wrap"><table>
          <thead><tr><th>${en ? "Concept Combination" : "Concept Combination"}</th><th>${en ? "Real Score" : "Real Score"}</th><th>${en ? "Sample Size" : "Sample Size"}</th><th>${en ? "Best Coins" : "Best Coins"}</th></tr></thead>
          <tbody>${(scores.combinations || []).slice(0, 10).map(c => `
            <tr>
              <td>${esc(c.dna_combo.join(" + "))}</td>
              <td>${c.avg_score}</td>
              <td>${c.sample_size}</td>
              <td>${esc((c.best_coins || []).slice(0, 3).map(bc => bc.symbol).join(", ") || "-")}</td>
            </tr>`).join("") || `<tr><td colspan="4">${en ? "Not enough data yet." : "Abhi kaafi data nahi."}</td></tr>`}</tbody>
        </table></div>

        <div class="section-title">${en ? "Every Attempt (Accepted And Rejected Alike)" : "Har Koshish (Accepted Aur Rejected Dono)"}</div>
        <div class="table-wrap"><table>
          <thead><tr><th>${en ? "When" : "Kab"}</th><th>${en ? "Combo" : "Combo"}</th><th>${en ? "Outcome" : "Outcome"}</th><th>${en ? "Reason" : "Reason"}</th></tr></thead>
          <tbody>${(attempts.attempts || []).map(a => `
            <tr>
              <td>${esc((a.created_at || "").slice(0, 16).replace("T", " "))}</td>
              <td>${esc((a.dna_combo || []).join(" + "))}</td>
              <td><span class="pill ${a.outcome === "accepted" ? "pill-up" : "pill-down"}">${esc(a.outcome)}</span></td>
              <td style="max-width:360px;">${esc(a.reason)}</td>
            </tr>`).join("") || `<tr><td colspan="4">${en ? "No attempts yet." : "Abhi koi koshish nahi hui."}</td></tr>`}</tbody>
        </table></div>
      `;

      document.getElementById("slRunNow").onclick = async () => {
        await apiPost("/api/self-learning/run-now");
        appendLog("Self-Learning discovery cycle started in the background.");
        showToast({ title: en ? "Started" : "Shuru Ho Gaya", body: en ? "Running in the background -- refresh this page in a few minutes." : "Background mein chal raha hai -- kuch minute mein yeh page refresh karein." });
        render();
      };
    }

    await render();
    autoRefresh(render, 30);
  }

  // ------------------------------------------------------------ CHALLENGE MODE (multi)
  // Master Task 3, Phase 2.1/2.9: a dedicated dashboard page for the NEW
  // multi-challenge system (2-3 challenges tracked side by side) --
  // deliberately separate from the original single-challenge widget still
  // embedded inside the Paper Trading page (loadChallenge() above), which
  // is left completely untouched for backward compatibility.
  let challengeExpandedId = null;

  function challengeDifficultyPill(difficulty, en) {
    const cls = { "Easy": "pill-bullish", "Moderate": "pill-neutral", "Hard": "pill-bearish",
                  "Extremely Unlikely": "pill-bearish" }[difficulty] || "pill-muted";
    return `<span class="pill ${cls}">${esc(difficulty)}</span>`;
  }

  async function renderChallengeMode() {
    const myToken = activeRouteToken;
    const en = getLang() === "en";

    async function render() {
      const [data, overview] = await Promise.all([
        apiGet("/api/paper-trading/challenges"),
        // Master Task 4, Phase 3.7: needed so the create form can offer a
        // specific strategy to scope a new challenge to -- without a real
        // scope set here, a matching Telegram signal can never be
        // attributed to this challenge by name later.
        apiGet("/api/paper-trading/strategy-overview"),
      ]);
      if (isStaleRoute(myToken)) return;
      const challenges = data.challenges || [];
      const strategies = overview.strategies || [];

      const cards = await Promise.all(challenges.map(async (c) => {
        const isExpanded = challengeExpandedId === c.challenge_id;
        let analysisHtml = "";
        if (isExpanded) {
          const a = await apiGet(`/api/paper-trading/challenges/${c.challenge_id}/full-analysis`).catch(() => null);
          if (isStaleRoute(myToken)) return "";
          analysisHtml = a ? challengeAnalysisHtml(a, en) : `<p class="muted">${en ? "Could not load analysis." : "Analysis load nahi hui."}</p>`;
        }
        return `
          <div class="card" data-challenge-card="${esc(c.challenge_id)}">
            <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
              <b>${esc(c.label)}</b>
              <span class="pill pill-muted">${esc(c.timeframe_type)}</span>
            </div>
            <p class="muted" style="font-size:12px;margin:4px 0;">$${c.start_amount} → $${c.target_amount} -- ${c.remaining_days} ${en ? "days left" : "din baaki"}</p>
            <div class="progress-bar"><div class="progress-bar-fill" style="width:${c.progress_pct}%;"></div></div>
            <p style="font-size:12.5px;margin:6px 0;">${en ? "Current" : "Abhi"}: <b>$${c.current_amount}</b> (${c.progress_pct}%)
              ${c.ahead_of_pace ? `<span class="pill pill-bullish">${en ? "Ahead of pace" : "Pace Se Aage"}</span>` : `<span class="pill pill-muted">${en ? "Behind pace" : "Pace Se Peeche"}</span>`}</p>
            <p class="muted" style="font-size:12px;">${esc(c.honest_note)}</p>
            <div class="btn-row">
              <button class="btn-ghost ch-toggle" data-id="${esc(c.challenge_id)}">${isExpanded ? (en ? "Hide Details" : "Details Chupayein") : (en ? "Full Analysis" : "Poori Analysis")}</button>
              <button class="btn-ghost ch-extend" data-id="${esc(c.challenge_id)}" data-days="${c.days}">${en ? "Extend Deadline" : "Deadline Barhayein"}</button>
              <button class="btn-ghost ch-archive" data-id="${esc(c.challenge_id)}">${en ? "Archive" : "Archive Karein"}</button>
            </div>
            ${analysisHtml ? `<div style="margin-top:12px;border-top:1px solid var(--border);padding-top:12px;">${analysisHtml}</div>` : ""}
          </div>`;
      }));

      content.innerHTML = `
        <div class="section-title">${en ? "Challenge Mode" : "Challenge Mode"}</div>
        <p class="muted" style="font-size:12px;margin:0 0 14px;">${en
          ? "Track up to 3 personal targets at once, side by side -- every number here comes from real Paper Trading history. This is tracking/analysis only: it never changes risk %, position sizing, or any trading behavior."
          : "Ek saath 3 tak personal targets track karein, side by side -- yahan har number real Paper Trading history se hai. Yeh sirf tracking/analysis hai: risk %, position sizing, ya koi bhi trading behavior kabhi nahi badalta."}</p>

        <div class="grid">${cards.join("") || `<p class="muted">${en ? "No active challenges." : "Koi active challenge nahi."}</p>`}</div>

        ${challenges.length < 3 ? `
          <div class="section-title">${en ? "Start a New Challenge" : "Naya Challenge Shuru Karein"}</div>
          <div class="card" style="max-width:480px;">
            <label>${en ? "Label" : "Label"}<input type="text" id="chmLabel" placeholder="${en ? "e.g. Weekly Push" : "misal: Weekly Push"}"></label>
            <label>${en ? "Starting Amount ($)" : "Shuru Ka Amount ($)"}<input type="number" id="chmStart" step="0.01" min="0.01"></label>
            <label>${en ? "Target Amount ($)" : "Target Amount ($)"}<input type="number" id="chmTarget" step="0.01" min="0.01"></label>
            <label>${en ? "Timeframe" : "Timeframe"}
              <select id="chmTimeframe">
                <option value="daily">${en ? "Daily" : "Daily"}</option>
                <option value="weekly" selected>${en ? "Weekly" : "Weekly"}</option>
                <option value="monthly">${en ? "Monthly" : "Monthly"}</option>
                <option value="custom">${en ? "Custom (days)" : "Custom (din)"}</option>
              </select>
            </label>
            <label id="chmDaysWrap" style="display:none;">${en ? "Days" : "Din"}<input type="number" id="chmDays" step="1" min="1"></label>
            <label style="display:flex;align-items:center;gap:8px;width:auto;">
              <input type="checkbox" id="chmCompounding" checked style="width:auto;"> ${en ? "Compounding risk" : "Compounding Risk"}
            </label>
            <label>${en ? "Scope to one strategy (optional)" : "Ek Strategy Tak Mehdood Karein (Optional)"}
              <select id="chmScopeStrategy">
                <option value="">${en ? "-- System-wide (no scope) --" : "-- Poore System Ke Liye (Koi Scope Nahi) --"}</option>
                ${strategies.map(s => `<option value="${esc(s.strategy_id)}">${esc(s.name)}</option>`).join("")}
              </select>
            </label>
            <label id="chmScopeSymbolWrap" style="display:none;">${en ? "Coin (optional, e.g. BTCUSDT)" : "Coin (Optional, Misal BTCUSDT)"}<input type="text" id="chmScopeSymbol" placeholder="BTCUSDT"></label>
            <p class="muted" style="font-size:11px;">${en
              ? "Scoping lets Telegram signals from that exact strategy+coin be labeled with this challenge's own name -- leave unscoped to just track your whole account's real progress."
              : "Scope karne se us exact strategy+coin ke Telegram signals is challenge ke apne naam se label honge -- scope na karein to sirf poore account ki real progress track hogi."}</p>
            <button class="btn" id="chmCreate">${en ? "Start Challenge" : "Challenge Shuru Karein"}</button>
          </div>` : `<p class="muted">${en ? "Maximum 3 active challenges reached -- archive one to start another." : "Zyada se zyada 3 active challenges ho chuke -- naya shuru karne ke liye ek archive karein."}</p>`}

        <div class="section-title">${en ? "Historical Replay" : "Historical Replay"}</div>
        <p class="muted" style="font-size:12px;">${en ? "If you had started this exact challenge N days ago, what would have really happened -- using real trades only." : "Agar aap ne yeh challenge N din pehle shuru kiya hota, to real trades ke mutabiq kya hota."}</p>
        <div class="card" style="max-width:480px;">
          <label>${en ? "Starting Amount ($)" : "Shuru Ka Amount ($)"}<input type="number" id="chmReplayStart" step="0.01" min="0.01" value="1000"></label>
          <label>${en ? "Target Amount ($)" : "Target Amount ($)"}<input type="number" id="chmReplayTarget" step="0.01" min="0.01" value="2000"></label>
          <label>${en ? "Started N Days Ago" : "N Din Pehle Shuru"}<input type="number" id="chmReplayDaysAgo" step="1" min="1" value="30"></label>
          <button class="btn-ghost" id="chmReplayRun">${en ? "Run Replay" : "Replay Chalayein"}</button>
          <div id="chmReplayResult" style="margin-top:10px;"></div>
        </div>

        <div class="section-title">${en ? "Strategy Rotation Suggestion" : "Strategy Rotation Suggestion"}</div>
        <div id="chmRotation" class="card" style="max-width:520px;">
          <p class="muted">${en ? "Loading..." : "Load ho raha hai..."}</p>
        </div>
      `;

      content.querySelectorAll(".ch-toggle").forEach(btn => {
        btn.onclick = () => {
          challengeExpandedId = challengeExpandedId === btn.dataset.id ? null : btn.dataset.id;
          render();
        };
      });
      content.querySelectorAll(".ch-archive").forEach(btn => {
        btn.onclick = async () => {
          if (!confirm(en ? "Archive this challenge? It stops being tracked but its history is never deleted." : "Yeh challenge archive karna hai? Track hona band ho jayega lekin history kabhi delete nahi hoti.")) return;
          await apiPost(`/api/paper-trading/challenges/${btn.dataset.id}/archive`);
          render();
        };
      });
      content.querySelectorAll(".ch-extend").forEach(btn => {
        btn.onclick = async () => {
          const newDays = prompt(en ? "New total number of days:" : "Nayi total din ki tadaad:", btn.dataset.days);
          if (!newDays) return;
          await apiSend("POST", `/api/paper-trading/challenges/${btn.dataset.id}/extend`, { new_days: Number(newDays) });
          render();
        };
      });

      const timeframeSelect = document.getElementById("chmTimeframe");
      if (timeframeSelect) {
        timeframeSelect.onchange = () => {
          document.getElementById("chmDaysWrap").style.display = timeframeSelect.value === "custom" ? "" : "none";
        };
      }
      const scopeStrategySelect = document.getElementById("chmScopeStrategy");
      if (scopeStrategySelect) {
        scopeStrategySelect.onchange = () => {
          document.getElementById("chmScopeSymbolWrap").style.display = scopeStrategySelect.value ? "" : "none";
        };
      }
      const createBtn = document.getElementById("chmCreate");
      if (createBtn) {
        createBtn.onclick = async () => {
          const timeframe_type = document.getElementById("chmTimeframe").value;
          const scopeStrategyId = document.getElementById("chmScopeStrategy").value;
          const body = {
            label: document.getElementById("chmLabel").value || (en ? "Untitled Challenge" : "Bila Naam Challenge"),
            start_amount: Number(document.getElementById("chmStart").value),
            target_amount: Number(document.getElementById("chmTarget").value),
            timeframe_type,
            compounding: document.getElementById("chmCompounding").checked,
            scope_strategy_id: scopeStrategyId || null,
            scope_symbol: scopeStrategyId ? (document.getElementById("chmScopeSymbol").value.trim().toUpperCase() || null) : null,
          };
          if (timeframe_type === "custom") body.days = Number(document.getElementById("chmDays").value);
          try {
            await apiPost("/api/paper-trading/challenges", body);
            render();
          } catch (e) {
            showToast({ title: en ? "Could not start challenge" : "Challenge Shuru Nahi Hua", body: e.message, isError: true });
          }
        };
      }

      document.getElementById("chmReplayRun").onclick = async () => {
        const resultBox = document.getElementById("chmReplayResult");
        resultBox.innerHTML = `<p class="muted">${en ? "Computing from real trades..." : "Real trades se hisaab lagaya ja raha hai..."}</p>`;
        try {
          const r = await apiPost("/api/paper-trading/challenges/replay", {
            start_amount: Number(document.getElementById("chmReplayStart").value),
            target_amount: Number(document.getElementById("chmReplayTarget").value),
            days_ago_started: Number(document.getElementById("chmReplayDaysAgo").value),
          });
          resultBox.innerHTML = `<p>${en ? "Ending amount" : "Aakhri Amount"}: <b>$${r.ending_amount}</b> (${r.trades_counted} ${en ? "real trades" : "real trades"}) -- ${r.would_have_reached_target ? `<span class="pill pill-bullish">${en ? "Would have reached target" : "Target Tak Pohanch Jata"}</span>` : `<span class="pill pill-muted">${en ? "Would not have reached target" : "Target Tak Nahi Pohanchta"}</span>`}</p>`;
        } catch (e) {
          resultBox.innerHTML = `<p class="muted">${esc(e.message)}</p>`;
        }
      };

      apiGet("/api/paper-trading/challenges/rotation-suggestion").then(r => {
        const box = document.getElementById("chmRotation");
        if (!box || isStaleRoute(myToken)) return;
        if (!r.suggestion) {
          box.innerHTML = `<p class="muted">${esc(r.reason)}</p>`;
          return;
        }
        const s = r.suggestion;
        box.innerHTML = `<p>${esc(s.strategy_a.strategy_name)} (${en ? "best in" : "best in"} ${esc(s.strategy_a.best_in)}) ↔ ${esc(s.strategy_b.strategy_name)} (${en ? "best in" : "best in"} ${esc(s.strategy_b.best_in)})</p><p class="muted" style="font-size:12px;">${esc(r.reason)}</p>`;
      }).catch(() => {});
    }

    await render();
    autoRefresh(render, 60);
  }

  function challengeAnalysisHtml(a, en) {
    const p = a.progress;
    const bwl = a.best_worst_likely || {};
    const caseHtml = (label, c) => c ? `<div><b>${label}</b>: ${c.daily_rate_pct}%/${en ? "day" : "din"} (${esc(c.strategy_name)}, ${esc(c.symbol)})${c.days_to_target ? ` -- ${c.days_to_target.toFixed(0)} ${en ? "days" : "din"}` : ""}</div>` : `<div><b>${label}</b>: -</div>`;
    return `
      <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px;">
        ${challengeDifficultyPill(a.difficulty, en)}
        ${a.give_up_point && a.give_up_point.implausible ? `<span class="pill pill-bearish">${en ? "Mathematically implausible" : "Riyazi Tor Par Namumkin"}</span>` : ""}
      </div>
      ${a.give_up_point && a.give_up_point.implausible ? `<p class="muted" style="font-size:12.5px;">${esc(a.give_up_point.reason)}</p>` : ""}
      <div style="font-size:12.5px;margin-bottom:8px;">
        ${caseHtml(en ? "Best case" : "Best Case", bwl.best_case)}
        ${caseHtml(en ? "Likely case" : "Likely Case", bwl.likely_case)}
        ${caseHtml(en ? "Worst case" : "Worst Case", bwl.worst_case)}
      </div>
      ${a.risk_suggestion ? `<p style="font-size:12.5px;">${en ? "Suggested risk" : "Tajweez Kardah Risk"}: <b>${a.risk_suggestion.suggested_risk_pct}%</b> (${en ? "currently" : "abhi"} ${a.risk_suggestion.current_risk_pct}%)</p>` : ""}
      ${a.risk_warning && a.risk_warning.warn ? `<p class="muted" style="font-size:12px;color:var(--red,#c0392b);">${esc(a.risk_warning.messages.join(" "))}</p>` : ""}
      ${a.loss_streak_impact && a.loss_streak_impact.checked ? `<p class="muted" style="font-size:12px;">${esc(a.loss_streak_impact.note)}</p>` : ""}
      ${a.best_historical_period ? `<p class="muted" style="font-size:12px;">${en ? "Best historical" : "Behtareen Tareekhi"} ${p.days}-${en ? "day period" : "din period"}: ${a.best_historical_period.growth_multiple}x growth (${a.best_historical_period.trades_in_window} ${en ? "trades" : "trades"}).</p>` : ""}
      ${a.compounding_comparison ? `<p style="font-size:12.5px;">${en ? "Compounding" : "Compounding"}: $${a.compounding_comparison.compounding_amount} ${en ? "vs Fixed-Risk" : "vs Fixed-Risk"}: $${a.compounding_comparison.fixed_risk_amount}</p>` : ""}
      ${(a.achievability_trend && a.achievability_trend.length > 1) ? `<p class="muted" style="font-size:12px;">${en ? "Achievability trend (7 days)" : "Achievability Trend (7 din)"}: ${a.achievability_trend.map(s => s.achievability_score).join(" → ")}${a.achievability_trend[a.achievability_trend.length - 1].achievability_score >= a.achievability_trend[0].achievability_score ? ` (${en ? "improving" : "behtar ho raha"})` : ` (${en ? "worsening" : "kharab ho raha"})`}</p>` : ""}
      <p style="font-size:12.5px;"><b>${en ? "AI Explanation" : "AI Wazahat"}</b>${a.ai_explanation.ai_used ? "" : ` (${en ? "no AI available" : "AI available nahi"})`}: ${esc(a.ai_explanation.explanation)}</p>
    `;
  }

  // ------------------------------------------------------------ STRATEGY WIZARD
  // A second, independent path into the exact same StrategyConfig the
  // paste-and-parse flow builds -- guided, form-based, zero interpretation.
  // Two rules: NEVER GUESS (every stored value traces to an explicit user
  // selection/typed text) and NEVER REJECT (an unmatched "Other" condition
  // always saves, tagged for manual review, instead of blocking the user).
  let wizState = null;

  function _wizEmptyCondition() {
    return { input_mode: "known", concept: "", direction: "", role: "", lookback_bars: "", period: "", op: "", value: "", raw_text: "", matched_concept: null };
  }

  function _wizReadConditionRows(containerId) {
    const rows = [...document.querySelectorAll(`#${containerId} .wiz-cond-row`)];
    return rows.map(row => {
      const mode = row.querySelector(".wiz-cond-mode").value;
      if (mode === "other") {
        // The mode <select>'s value can flip to "other" via a live onchange
        // BEFORE the row's own HTML has been rebuilt into the "other"
        // layout (the textarea doesn't exist yet at that exact instant) --
        // read whatever's there defensively instead of throwing, so a mode
        // switch never loses the rest of the row's/list's state.
        const rawEl = row.querySelector(".wiz-cond-rawtext");
        return {
          input_mode: "other",
          raw_text: rawEl ? rawEl.value.trim() : "",
          matched_concept: row.dataset.matchedConcept || null,
        };
      }
      const val = (sel) => { const el = row.querySelector(sel); return el ? el.value : ""; };
      const numOrNull = (v) => (v === "" || v === null ? null : parseFloat(v));
      return {
        input_mode: "known",
        concept: val(".wiz-cond-concept"),
        direction: val(".wiz-cond-direction") || null,
        role: val(".wiz-cond-role") || null,
        lookback_bars: val(".wiz-cond-lookback") === "" ? null : parseInt(val(".wiz-cond-lookback"), 10),
        period: val(".wiz-cond-period") === "" ? null : parseInt(val(".wiz-cond-period"), 10),
        op: val(".wiz-cond-op") || null,
        value: numOrNull(val(".wiz-cond-value")),
      };
    });
  }

  function _wizConditionRowHtml(cond, idx, en) {
    const catalog = wizState.catalog || { concepts: [], indicators: [] };
    const mode = cond.input_mode || "known";
    return `
      <div class="wiz-cond-row" data-idx="${idx}" data-matched-concept="${esc(cond.matched_concept || "")}" style="border:1px solid var(--border,#333);padding:10px;border-radius:8px;margin-bottom:8px;">
        <div class="btn-row" style="align-items:center;">
          <select class="wiz-cond-mode" data-idx="${idx}" style="max-width:220px;">
            <option value="known" ${mode === "known" ? "selected" : ""}>${en ? "Known Concept" : "Jaana Pehchana Concept"}</option>
            <option value="other" ${mode === "other" ? "selected" : ""}>${en ? "Other / Not Listed" : "Other / List Mein Nahi"}</option>
          </select>
          <button class="btn-ghost wiz-cond-remove" data-idx="${idx}" style="margin-left:auto;">${en ? "Remove" : "Hatayein"}</button>
        </div>
        ${mode === "known" ? `
          <div class="btn-row" style="margin-top:8px;flex-wrap:wrap;">
            <select class="wiz-cond-concept" style="max-width:220px;">
              <option value="">-- ${en ? "select concept" : "concept chunein"} --</option>
              <optgroup label="${en ? "Concepts" : "Concepts"}">
                ${catalog.concepts.map(c => `<option value="${c}" ${c === cond.concept ? "selected" : ""}>${c}</option>`).join("")}
              </optgroup>
              <optgroup label="${en ? "Indicators (period-based)" : "Indicators (period wale)"}">
                ${catalog.indicators.map(c => `<option value="${c}" ${c === cond.concept ? "selected" : ""}>${c}</option>`).join("")}
              </optgroup>
            </select>
            <select class="wiz-cond-direction" style="max-width:140px;">
              <option value="">${en ? "Direction (any)" : "Direction (koi bhi)"}</option>
              <option value="bullish" ${cond.direction === "bullish" ? "selected" : ""}>Bullish</option>
              <option value="bearish" ${cond.direction === "bearish" ? "selected" : ""}>Bearish</option>
            </select>
            <select class="wiz-cond-role" style="max-width:150px;">
              <option value="">${en ? "Timeframe role (any)" : "Timeframe role (koi bhi)"}</option>
              ${["bias", "trend", "analysis", "entry", "confirmation"].map(r => `<option value="${r}" ${cond.role === r ? "selected" : ""}>${r}</option>`).join("")}
            </select>
            <input class="wiz-cond-lookback" type="number" min="1" placeholder="${en ? "Lookback bars" : "Pichle kitne bars"}" value="${esc(cond.lookback_bars ?? "")}" style="max-width:130px;">
          </div>
          <div class="btn-row" style="margin-top:6px;flex-wrap:wrap;">
            <input class="wiz-cond-period" type="number" min="1" placeholder="${en ? "Period (indicators only)" : "Period (sirf indicators)"}" value="${esc(cond.period ?? "")}" style="max-width:170px;">
            <select class="wiz-cond-op" style="max-width:90px;">
              <option value="">${en ? "op" : "op"}</option>
              <option value=">" ${cond.op === ">" ? "selected" : ""}>&gt;</option>
              <option value="<" ${cond.op === "<" ? "selected" : ""}>&lt;</option>
            </select>
            <input class="wiz-cond-value" type="number" step="any" placeholder="${en ? "Threshold value" : "Threshold value"}" value="${esc(cond.value ?? "")}" style="max-width:140px;">
          </div>
        ` : `
          <div style="margin-top:8px;">
            <textarea class="wiz-cond-rawtext" placeholder="${en ? "Describe this condition in your own words" : "Yeh condition apne alfaaz mein likhein"}" style="width:100%;min-height:60px;">${esc(cond.raw_text || "")}</textarea>
            <div class="btn-row" style="margin-top:6px;">
              <button class="btn-ghost wiz-cond-classify" data-idx="${idx}">${en ? "Check with AI (optional)" : "AI se check karein (optional)"}</button>
              <span class="wiz-cond-classify-result muted" style="font-size:12px;">${cond.matched_concept ? `✅ ${en ? "Matched to" : "Match hua"}: ${esc(cond.matched_concept)}` : ""}</span>
            </div>
          </div>
        `}
      </div>`;
  }

  function _wizConditionListHtml(listKey, label, en) {
    const items = wizState[listKey];
    return `
      <div class="section-title" style="font-size:15px;">${label}</div>
      <div id="wizList_${listKey}">
        ${items.map((c, i) => _wizConditionRowHtml(c, i, en)).join("") || `<p class="muted">${en ? "No conditions added yet." : "Abhi tak koi condition add nahi hui."}</p>`}
      </div>
      <button class="btn-ghost" data-addlist="${listKey}">+ ${en ? "Add Condition" : "Condition Add Karein"}</button>`;
  }

  function _wizWireConditionList(listKey) {
    const container = document.getElementById(`wizList_${listKey}`);
    if (!container) return;
    container.querySelectorAll(".wiz-cond-remove").forEach(btn => {
      btn.onclick = () => {
        wizState[listKey] = _wizReadConditionRows(`wizList_${listKey}`);
        wizState[listKey].splice(parseInt(btn.dataset.idx, 10), 1);
        renderWizardStep();
      };
    });
    container.querySelectorAll(".wiz-cond-mode").forEach(sel => {
      sel.onchange = () => {
        wizState[listKey] = _wizReadConditionRows(`wizList_${listKey}`);
        wizState[listKey][parseInt(sel.dataset.idx, 10)].input_mode = sel.value;
        renderWizardStep();
      };
    });
    container.querySelectorAll(".wiz-cond-classify").forEach(btn => {
      btn.onclick = async () => {
        const row = btn.closest(".wiz-cond-row");
        const rawText = row.querySelector(".wiz-cond-rawtext").value.trim();
        if (!rawText) return;
        const resultEl = row.querySelector(".wiz-cond-classify-result");
        const en = getLang() === "en";
        resultEl.textContent = en ? "Checking..." : "Check ho raha hai...";
        try {
          const res = await apiPost("/api/wizard/classify-other", { raw_text: rawText });
          if (!res.ai_available) {
            resultEl.textContent = en
              ? "No AI available right now -- saved as Manual Review, which is safe."
              : "Abhi AI available nahi -- Manual Review mein save hoga, yeh safe hai.";
            return;
          }
          if (!res.matched_concept) {
            resultEl.textContent = en
              ? "Bilkul naya -- no close match found. Saved as Manual Review."
              : "Bilkul naya -- koi milta julta concept nahi mila. Manual Review mein save hoga.";
            return;
          }
          resultEl.innerHTML = `${en ? "Yeh sab se milta julta hai" : "Yeh sab se milta julta hai"}: <b>${esc(res.matched_concept)}</b>
            <button class="btn-ghost wiz-confirm-match" data-idx="${row.dataset.idx}" data-concept="${esc(res.matched_concept)}" style="margin-left:6px;">${en ? "Haan, yehi hai" : "Haan, yehi hai"}</button>
            <button class="btn-ghost wiz-reject-match" data-idx="${row.dataset.idx}" style="margin-left:4px;">${en ? "Nahi, bilkul naya" : "Nahi, bilkul naya"}</button>`;
          resultEl.querySelector(".wiz-confirm-match").onclick = () => {
            row.dataset.matchedConcept = res.matched_concept;
            wizState[listKey] = _wizReadConditionRows(`wizList_${listKey}`);
            const idx = parseInt(row.dataset.idx, 10);
            wizState[listKey][idx].input_mode = "known";
            wizState[listKey][idx].concept = res.matched_concept;
            wizState[listKey][idx].matched_concept = res.matched_concept;
            renderWizardStep();
          };
          resultEl.querySelector(".wiz-reject-match").onclick = () => {
            resultEl.textContent = en ? "OK -- saved as Manual Review." : "Theek hai -- Manual Review mein save hoga.";
          };
        } catch (e) {
          resultEl.textContent = en ? "Check failed -- saved as Manual Review, which is safe." : "Check fail hua -- Manual Review mein save hoga, yeh safe hai.";
        }
      };
    });
    const addBtn = document.querySelector(`[data-addlist="${listKey}"]`);
    if (addBtn) addBtn.onclick = () => {
      wizState[listKey] = _wizReadConditionRows(`wizList_${listKey}`);
      wizState[listKey].push(_wizEmptyCondition());
      renderWizardStep();
    };
  }

  const WIZ_STEP_LABELS_EN = ["Basic Setup", "Entry Conditions", "Exit Conditions", "Stop Loss", "Take Profit", "Risk & Position Sizing", "Filters / Discards", "Review & Save"];
  const WIZ_STEP_LABELS_UR = ["Basic Setup", "Entry Conditions", "Exit Conditions", "Stop Loss", "Take Profit", "Risk & Position Sizing", "Filters / Discards", "Review & Save"];

  function _wizCollectStep1() {
    wizState.name = document.getElementById("wizName").value.trim();
    wizState.entry_timeframe = document.getElementById("wizEntryTf").value;
    wizState.bias_timeframe = document.getElementById("wizBiasTf").value || null;
    wizState.session = document.getElementById("wizSession").value || null;
    wizState.session_start = document.getElementById("wizSessionStart").value || null;
    wizState.session_end = document.getElementById("wizSessionEnd").value || null;
    wizState.direction_mode = document.getElementById("wizDirection").value;
  }

  function _wizRenderStep1(en) {
    const tfOptions = (wizState.timeframeOptions || []).map(tf => `<option value="${tf}" ${wizState.entry_timeframe === tf ? "selected" : ""}>${tf}</option>`).join("");
    const tfOptionsBias = (wizState.timeframeOptions || []).map(tf => `<option value="${tf}" ${wizState.bias_timeframe === tf ? "selected" : ""}>${tf}</option>`).join("");
    return `
      <label>${en ? "Strategy Name" : "Strategy Ka Naam"}</label>
      <input id="wizName" value="${esc(wizState.name)}" placeholder="${en ? "e.g. HTF FVG Reversal" : "misaal: HTF FVG Reversal"}">

      <label style="margin-top:10px;">${en ? "Entry Timeframe" : "Entry Timeframe"}</label>
      <select id="wizEntryTf"><option value="">--</option>${tfOptions}</select>

      <label style="margin-top:10px;">${en ? "Bias / Analysis Timeframe (optional)" : "Bias / Analysis Timeframe (optional)"}</label>
      <select id="wizBiasTf"><option value="">${en ? "-- none --" : "-- koi nahi --"}</option>${tfOptionsBias}</select>

      <label style="margin-top:10px;">${en ? "Trading Session (optional)" : "Trading Session (optional)"}</label>
      <select id="wizSession">
        <option value="any">${en ? "Any" : "Koi Bhi"}</option>
        <option value="new_york" ${wizState.session === "new_york" ? "selected" : ""}>New York</option>
        <option value="london" ${wizState.session === "london" ? "selected" : ""}>London</option>
        <option value="asian" ${wizState.session === "asian" ? "selected" : ""}>Asian</option>
      </select>

      <div class="btn-row" style="margin-top:10px;">
        <div style="flex:1;">
          <label>${en ? "Session Start (optional)" : "Session Start (optional)"}</label>
          <input id="wizSessionStart" placeholder="09:30" value="${esc(wizState.session_start || "")}">
        </div>
        <div style="flex:1;">
          <label>${en ? "Session End (optional)" : "Session End (optional)"}</label>
          <input id="wizSessionEnd" placeholder="11:00" value="${esc(wizState.session_end || "")}">
        </div>
      </div>

      <label style="margin-top:10px;">${en ? "Direction" : "Direction"}</label>
      <select id="wizDirection">
        <option value="long_only" ${wizState.direction_mode === "long_only" ? "selected" : ""}>${en ? "Long only" : "Sirf Long"}</option>
        <option value="short_only" ${wizState.direction_mode === "short_only" ? "selected" : ""}>${en ? "Short only" : "Sirf Short"}</option>
        <option value="both_mirror" ${wizState.direction_mode === "both_mirror" ? "selected" : ""}>${en ? "Both (mirror rules)" : "Dono (mirror rules)"}</option>
        <option value="both_independent" ${wizState.direction_mode === "both_independent" ? "selected" : ""}>${en ? "Both (independent rules)" : "Dono (independent rules)"}</option>
      </select>
      <p class="muted" style="font-size:12px;">${en
        ? "\"Both (mirror rules)\": fill entry/exit/SL/TP ONCE, the opposite direction is generated automatically. \"Both (independent rules)\": fill long and short separately, no assumption they mirror."
        : "\"Both (mirror rules)\": entry/exit/SL/TP SIRF EK BAAR bharein, opposite direction khud ban jayegi. \"Both (independent rules)\": long aur short alag alag bharein, koi assumption nahi ke woh mirror karte hain."}</p>`;
  }

  function _wizRenderStep2(en) {
    if (wizState.direction_mode === "both_independent") {
      return `
        ${_wizConditionListHtml("long_entry_conditions", en ? "Long Entry Conditions" : "Long Entry Conditions", en)}
        <div style="height:14px;"></div>
        ${_wizConditionListHtml("short_entry_conditions", en ? "Short Entry Conditions" : "Short Entry Conditions", en)}`;
    }
    return _wizConditionListHtml("entry_conditions", en ? "Entry Conditions" : "Entry Conditions", en);
  }

  function _wizWireStep2() {
    if (wizState.direction_mode === "both_independent") {
      _wizWireConditionList("long_entry_conditions");
      _wizWireConditionList("short_entry_conditions");
    } else {
      _wizWireConditionList("entry_conditions");
    }
  }

  function _wizRenderStep3(en) {
    return _wizConditionListHtml("exit_conditions", en ? "Exit Conditions" : "Exit Conditions", en);
  }

  function _wizCollectSlTp(prefix, stateObj) {
    stateObj.type = document.getElementById(`${prefix}Type`).value;
    const val = document.getElementById(`${prefix}Value`).value;
    stateObj.value = val === "" ? null : parseFloat(val);
    const level = document.getElementById(`${prefix}Level`);
    stateObj.level = level && level.value ? level.value : null;
    const raw = document.getElementById(`${prefix}Raw`);
    stateObj.raw_source = raw ? raw.value.trim() : null;
  }

  function _wizRenderStep4(en) {
    const sl = wizState.stop_loss;
    return `
      <label>${en ? "Stop Loss Type" : "Stop Loss Ka Type"}</label>
      <select id="wizSlType">
        <option value="">--</option>
        <option value="fixed_pct" ${sl.type === "fixed_pct" ? "selected" : ""}>${en ? "Fixed Percentage" : "Fixed Percentage"}</option>
        <option value="fixed_points" ${sl.type === "fixed_points" ? "selected" : ""}>${en ? "Fixed Points" : "Fixed Points"}</option>
        <option value="atr_multiple" ${sl.type === "atr_multiple" ? "selected" : ""}>${en ? "ATR Multiple" : "ATR Multiple"}</option>
        <option value="structure" ${sl.type === "structure" ? "selected" : ""}>${en ? "Structure-based" : "Structure-based"}</option>
        <option value="signal_candle" ${sl.type === "signal_candle" ? "selected" : ""}>${en ? "Signal Candle High/Low" : "Signal Candle High/Low"}</option>
        <option value="other" ${sl.type === "other" ? "selected" : ""}>${en ? "Other" : "Other"}</option>
      </select>
      <p class="muted" style="font-size:12px;">${en
        ? "\"Fixed Points\" and \"Other\" have no direct engine support yet -- they save as Manual Review, excluded from execution until resolved, never silently ignored."
        : "\"Fixed Points\" aur \"Other\" ka abhi direct engine support nahi -- yeh Manual Review mein save hote hain, resolve hone tak execution se bahar rehte hain, kabhi silently ignore nahi hote."}</p>
      <label style="margin-top:8px;">${en ? "Value (%, points, ATR multiple, or buffer %)" : "Value (%, points, ATR multiple, ya buffer %)"}</label>
      <input id="wizSlValue" type="number" step="any" value="${sl.value ?? ""}">
      <label style="margin-top:8px;">${en ? "Level (only for structure-based, e.g. pdh/pdl -- optional)" : "Level (sirf structure-based ke liye, e.g. pdh/pdl -- optional)"}</label>
      <input id="wizSlLevel" value="${esc(sl.level || "")}">
      <label style="margin-top:8px;">${en ? "Describe in your own words (only if type = Other / Fixed Points)" : "Apne alfaaz mein likhein (sirf Other / Fixed Points ke liye)"}</label>
      <textarea id="wizSlRaw" style="width:100%;min-height:50px;">${esc(sl.raw_source || "")}</textarea>`;
  }

  function _wizRenderStep5(en) {
    const tp = wizState.take_profit;
    return `
      <label>${en ? "Take Profit Type" : "Take Profit Ka Type"}</label>
      <select id="wizTpType">
        <option value="">--</option>
        <option value="fixed_pct" ${tp.type === "fixed_pct" ? "selected" : ""}>${en ? "Fixed Percentage" : "Fixed Percentage"}</option>
        <option value="rr" ${tp.type === "rr" ? "selected" : ""}>${en ? "Risk:Reward Ratio" : "Risk:Reward Ratio"}</option>
        <option value="structure" ${tp.type === "structure" ? "selected" : ""}>${en ? "Structure-based Target" : "Structure-based Target"}</option>
        <option value="level" ${tp.type === "level" ? "selected" : ""}>${en ? "Named Level (PDH/PDL)" : "Named Level (PDH/PDL)"}</option>
        <option value="other" ${tp.type === "other" ? "selected" : ""}>${en ? "Other / Partial Exits" : "Other / Partial Exits"}</option>
      </select>
      <p class="muted" style="font-size:12px;">${en
        ? "\"Other\" (including partial-exit splits, which the engine doesn't compute automatically yet) saves as Manual Review."
        : "\"Other\" (partial-exit splits sameet, jo engine abhi khud compute nahi karta) Manual Review mein save hota hai."}</p>
      <label style="margin-top:8px;">${en ? "Value (%, or R multiple)" : "Value (%, ya R multiple)"}</label>
      <input id="wizTpValue" type="number" step="any" value="${tp.value ?? ""}">
      <label style="margin-top:8px;">${en ? "Level (only for Named Level, e.g. pdh/pdl)" : "Level (sirf Named Level ke liye, e.g. pdh/pdl)"}</label>
      <input id="wizTpLevel" value="${esc(tp.level || "")}">
      <label style="margin-top:8px;">${en ? "Describe in your own words (only if type = Other)" : "Apne alfaaz mein likhein (sirf Other ke liye)"}</label>
      <textarea id="wizTpRaw" style="width:100%;min-height:50px;">${esc(tp.raw_source || "")}</textarea>`;
  }

  function _wizCollectStep6() {
    const risk = document.getElementById("wizRiskPct").value;
    wizState.risk_pct = risk === "" ? null : parseFloat(risk);
    const maxSim = document.getElementById("wizMaxSim").value;
    wizState.max_simultaneous_trades = maxSim === "" ? null : parseInt(maxSim, 10);
    const maxDaily = document.getElementById("wizMaxDaily").value;
    wizState.max_daily_trades = maxDaily === "" ? null : parseInt(maxDaily, 10);
    const maxLoss = document.getElementById("wizMaxLoss").value;
    wizState.max_daily_loss_pct = maxLoss === "" ? null : parseFloat(maxLoss);
  }

  function _wizRenderStep6(en) {
    return `
      <label>${en ? "Risk % per trade" : "Har Trade Par Risk %"}</label>
      <input id="wizRiskPct" type="number" step="any" value="${wizState.risk_pct ?? ""}" placeholder="${en ? "e.g. 1.0 -- leave blank if not specified anywhere" : "misaal 1.0 -- khali chodein agar kahin specify nahi hua"}">
      <p class="muted" style="font-size:12px;">${en
        ? "If you don't know, a common conservative default is 1% -- but it's never applied silently. Type it yourself if you accept it."
        : "Agar pata nahi to ek aam conservative default 1% hai -- lekin yeh kabhi silently apply nahi hota. Khud type karein agar accept karte hain."}</p>
      <label style="margin-top:10px;">${en ? "Max Simultaneous Trades (optional)" : "Max Simultaneous Trades (optional)"}</label>
      <input id="wizMaxSim" type="number" min="1" value="${wizState.max_simultaneous_trades ?? ""}">
      <label style="margin-top:10px;">${en ? "Max Daily Trades (optional)" : "Max Daily Trades (optional)"}</label>
      <input id="wizMaxDaily" type="number" min="1" value="${wizState.max_daily_trades ?? ""}">
      <label style="margin-top:10px;">${en ? "Max Daily Loss % (optional)" : "Max Daily Loss % (optional)"}</label>
      <input id="wizMaxLoss" type="number" step="any" value="${wizState.max_daily_loss_pct ?? ""}">`;
  }

  function _wizRenderStep7(en) {
    return `
      <p class="muted">${en
        ? "Conditions that cause an otherwise-valid setup to be SKIPPED (e.g. \"skip if inside a chop range\")."
        : "Conditions jo warna-valid setup ko SKIP kara dein (jaise \"chop range ke andar ho to skip karein\")."}</p>
      ${_wizConditionListHtml("filters", en ? "Filters / Discards" : "Filters / Discards", en)}`;
  }

  function _wizComputeReview() {
    const wd = _wizToWizardData();
    // Local mirror of backend trust math (backend recomputes authoritatively on save;
    // this is only for the review screen preview before the user commits).
    const allCondLists = [wd.entry_conditions, wd.long_entry_conditions, wd.short_entry_conditions, wd.exit_conditions, wd.filters];
    let total = 0, manual = 0;
    const items = [];
    allCondLists.forEach(list => (list || []).forEach(c => {
      total++;
      if (c.input_mode === "other" && !c.matched_concept) { manual++; items.push(c.raw_text); }
    }));
    [["Stop Loss", wd.stop_loss], ["Take Profit", wd.take_profit]].forEach(([label, spec]) => {
      if (spec && spec.type) {
        total++;
        if (!["fixed_pct", "atr_multiple", "structure", "signal_candle", "rr", "level"].includes(spec.type)) {
          manual++; items.push(`${label}: ${spec.raw_source || spec.type}`);
        }
      }
    });
    return { total, manual, items, trustPct: total ? Math.round((total - manual) / total * 1000) / 10 : 100 };
  }

  function _wizRenderStep8(en) {
    const wd = _wizToWizardData();
    const review = _wizComputeReview();
    const summarizeList = (list, label) => (list && list.length)
      ? `<li>${esc(label)}: ${list.map(c => c.input_mode === "other" ? `"${esc(c.raw_text)}"${c.matched_concept ? ` (${en ? "matched" : "match hua"}: ${esc(c.matched_concept)})` : ` (${en ? "MANUAL REVIEW" : "MANUAL REVIEW"})`}` : esc(c.concept || "-")).join(", ")}</li>`
      : "";
    return `
      <div class="section-title" style="font-size:15px;">${en ? "Summary" : "Khulasa"}</div>
      <ul>
        <li>${en ? "Name" : "Naam"}: ${esc(wd.name || "-")}</li>
        <li>${en ? "Entry Timeframe" : "Entry Timeframe"}: ${esc(wd.entry_timeframe || "-")}${wd.bias_timeframe ? `, ${en ? "Bias" : "Bias"}: ${esc(wd.bias_timeframe)}` : ""}</li>
        <li>${en ? "Direction" : "Direction"}: ${esc(wd.direction_mode)}</li>
        ${summarizeList(wd.entry_conditions, en ? "Entry Conditions" : "Entry Conditions")}
        ${summarizeList(wd.long_entry_conditions, en ? "Long Entry Conditions" : "Long Entry Conditions")}
        ${summarizeList(wd.short_entry_conditions, en ? "Short Entry Conditions" : "Short Entry Conditions")}
        ${summarizeList(wd.exit_conditions, en ? "Exit Conditions" : "Exit Conditions")}
        ${summarizeList(wd.filters, en ? "Filters" : "Filters")}
        <li>${en ? "Stop Loss" : "Stop Loss"}: ${esc(wd.stop_loss.type || "-")} ${wd.stop_loss.value != null ? `(${wd.stop_loss.value})` : ""}</li>
        <li>${en ? "Take Profit" : "Take Profit"}: ${esc(wd.take_profit.type || "-")} ${wd.take_profit.value != null ? `(${wd.take_profit.value})` : ""}</li>
        <li>${en ? "Risk %" : "Risk %"}: ${wd.risk_pct != null ? wd.risk_pct : (en ? "not set" : "set nahi hua")}</li>
      </ul>
      <div class="section-title" style="font-size:15px;">${en ? "Trust Score" : "Trust Score"}</div>
      <div class="grid">
        ${cardClass("Trust Score", `${review.trustPct}%`, review.trustPct === 100 ? "positive" : review.manual > 0 ? "negative" : "")}
        ${card(en ? "Fields Set By You" : "Aapne Khud Set Kiye", review.total - review.manual)}
        ${card(en ? "Need Manual Review" : "Manual Review Chahiye", review.manual)}
      </div>
      ${review.manual > 0 ? `
        <p>${en ? `${review.total - review.manual} field(s) set by you directly, ${review.manual} need manual review:` : `${review.total - review.manual} fields aapne khud set kiye, ${review.manual} ko Manual Review chahiye:`}</p>
        <ul>${review.items.map(i => `<li class="muted">${esc(i)}</li>`).join("")}</ul>
        <p class="muted" style="font-size:12px;">${en
          ? "These stay excluded from live backtesting/signals until resolved -- never executed unverified."
          : "Yeh live backtesting/signals se bahar rehte hain jab tak resolve na ho -- kabhi unverified execute nahi hote."}</p>
      ` : `<p>${en ? "100% -- every field traces back to something you selected or typed." : "100% -- har field aapke khud select ya type kiye hue se aata hai."}</p>`}
      <div class="btn-row" style="margin-top:14px;">
        <button class="btn" id="wizSaveBtn">${en ? "Save Strategy" : "Strategy Save Karein"}</button>
        <button class="btn-ghost" id="wizSaveRunBtn">${en ? "Save and Run Backtest" : "Save Karein aur Backtest Chalayein"}</button>
      </div>
      <div id="wizSaveResult" style="margin-top:12px;"></div>`;
  }

  function _wizToWizardData() {
    return {
      name: wizState.name, entry_timeframe: wizState.entry_timeframe, bias_timeframe: wizState.bias_timeframe,
      session: wizState.session, session_start: wizState.session_start, session_end: wizState.session_end,
      direction_mode: wizState.direction_mode,
      entry_conditions: wizState.entry_conditions, long_entry_conditions: wizState.long_entry_conditions,
      short_entry_conditions: wizState.short_entry_conditions, exit_conditions: wizState.exit_conditions,
      filters: wizState.filters,
      stop_loss: wizState.stop_loss, take_profit: wizState.take_profit,
      risk_pct: wizState.risk_pct, max_simultaneous_trades: wizState.max_simultaneous_trades,
      max_daily_trades: wizState.max_daily_trades, max_daily_loss_pct: wizState.max_daily_loss_pct,
    };
  }

  function _wizCollectCurrentStep() {
    const step = wizState.step;
    if (step === 1) _wizCollectStep1();
    else if (step === 2) {
      if (wizState.direction_mode === "both_independent") {
        wizState.long_entry_conditions = _wizReadConditionRows("wizList_long_entry_conditions");
        wizState.short_entry_conditions = _wizReadConditionRows("wizList_short_entry_conditions");
      } else {
        wizState.entry_conditions = _wizReadConditionRows("wizList_entry_conditions");
      }
    } else if (step === 3) wizState.exit_conditions = _wizReadConditionRows("wizList_exit_conditions");
    else if (step === 4) _wizCollectSlTp("wizSl", wizState.stop_loss);
    else if (step === 5) _wizCollectSlTp("wizTp", wizState.take_profit);
    else if (step === 6) _wizCollectStep6();
    else if (step === 7) wizState.filters = _wizReadConditionRows("wizList_filters");
  }

  async function renderStrategyWizard() {
    const myToken = activeRouteToken;
    const en = getLang() === "en";

    if (!wizState) {
      wizState = {
        step: 1, catalog: null, timeframeOptions: null,
        name: "", entry_timeframe: "", bias_timeframe: "", session: "any", session_start: "", session_end: "",
        direction_mode: "long_only",
        entry_conditions: [], long_entry_conditions: [], short_entry_conditions: [], exit_conditions: [],
        filters: [],
        stop_loss: { type: "", value: null, level: null, raw_source: null },
        take_profit: { type: "", value: null, level: null, raw_source: null },
        risk_pct: null, max_simultaneous_trades: null, max_daily_trades: null, max_daily_loss_pct: null,
      };
    }

    if (!wizState.catalog || !wizState.timeframeOptions) {
      const [catalog, home] = await Promise.all([
        apiGet("/api/wizard/concept-library"),
        apiGet("/api/home").catch(() => ({ available_timeframes: ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"] })),
      ]);
      if (isStaleRoute(myToken)) return;
      wizState.catalog = catalog;
      wizState.timeframeOptions = home.available_timeframes || ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"];
    }

    renderWizardStep();
  }

  function renderWizardStep() {
    const en = getLang() === "en";
    const labels = en ? WIZ_STEP_LABELS_EN : WIZ_STEP_LABELS_UR;
    const step = wizState.step;

    let body = "";
    if (step === 1) body = _wizRenderStep1(en);
    else if (step === 2) body = _wizRenderStep2(en);
    else if (step === 3) body = _wizRenderStep3(en);
    else if (step === 4) body = _wizRenderStep4(en);
    else if (step === 5) body = _wizRenderStep5(en);
    else if (step === 6) body = _wizRenderStep6(en);
    else if (step === 7) body = _wizRenderStep7(en);
    else if (step === 8) body = _wizRenderStep8(en);

    content.innerHTML = `
      <div class="section-title">${en ? "Strategy Wizard" : "Strategy Wizard"}</div>
      <p class="muted">${en
        ? "Step-by-step, zero guessing -- every value you pick or type yourself. Saves into the exact same format as the paste-and-parse import."
        : "Step-by-step, koi guessing nahi -- har value aap khud choose ya type karte hain. Paste-and-parse import wale exact format mein hi save hota hai."}</p>
      <div class="btn-row" style="flex-wrap:wrap;margin-bottom:10px;">
        ${labels.map((l, i) => `<span class="pill ${i + 1 === step ? "pill-bullish" : "pill-muted"}" style="cursor:default;">${i + 1}. ${l}</span>`).join("")}
      </div>
      <div style="max-width:640px;">
        ${body}
      </div>
      <div class="btn-row" style="margin-top:16px;">
        ${step > 1 ? `<button class="btn-ghost" id="wizBackBtn">${en ? "Back" : "Peeche"}</button>` : ""}
        ${step < 8 ? `<button class="btn" id="wizNextBtn">${en ? "Next" : "Aage"}</button>` : ""}
      </div>`;

    if (step === 2) _wizWireStep2();
    else if (step === 3) _wizWireConditionList("exit_conditions");
    else if (step === 7) _wizWireConditionList("filters");

    const backBtn = document.getElementById("wizBackBtn");
    if (backBtn) backBtn.onclick = () => { _wizCollectCurrentStep(); wizState.step--; renderWizardStep(); };
    const nextBtn = document.getElementById("wizNextBtn");
    if (nextBtn) nextBtn.onclick = () => { _wizCollectCurrentStep(); wizState.step++; renderWizardStep(); };

    if (step === 8) {
      document.getElementById("wizSaveBtn").onclick = () => _wizSave(false);
      document.getElementById("wizSaveRunBtn").onclick = () => _wizSave(true);
    }
  }

  async function _wizSave(runAfter) {
    const en = getLang() === "en";
    const resultEl = document.getElementById("wizSaveResult");
    resultEl.textContent = en ? "Saving..." : "Save ho raha hai...";
    try {
      const res = await apiPost("/api/wizard/save", { wizard_data: _wizToWizardData(), tags: [] });
      resultEl.innerHTML = `<p class="positive">${en ? "Saved!" : "Save ho gaya!"} ${en ? "Strategy ID" : "Strategy ID"}: ${esc(res.strategy_id)}. ${en ? "Trust Score" : "Trust Score"}: ${res.trust_report.trust_score_pct}%.</p>`;
      if (runAfter) {
        resultEl.innerHTML += `<p class="muted">${en ? "Go to the Strategies page to run a backtest on this strategy." : "Is strategy par backtest chalane ke liye Strategies page par jayein."}</p>`;
      }
      wizState = null;  // fresh wizard next time
    } catch (e) {
      resultEl.innerHTML = `<p class="negative">${en ? "Save failed" : "Save fail hua"}: ${esc(e.message || String(e))}</p>`;
    }
  }

  // ------------------------------------------------------------ EXTERNAL SIGNAL TRACKER
  // A COMPLETELY SEPARATE module from the CEO's own Paper Trading /
  // Signal Tracker above -- external Telegram channels, isolated tables,
  // never averaged with the CEO's own strategy results. See
  // external_signals/ (Python) and sindhu_web/api/external_signals.py.
  async function renderExternalSignals() {
    const myToken = activeRouteToken;
    const en = getLang() === "en";

    async function render() {
      const [channelsRes, comparisonRes, settingsRes] = await Promise.all([
        apiGet("/api/external-signals/channels").catch(() => ({ channels: [] })),
        apiGet("/api/external-signals/comparison").catch(() => ({ channels: [] })),
        apiGet("/api/external-signals/settings").catch(() => ({})),
      ]);
      if (isStaleRoute(myToken)) return;

      content.innerHTML = `
        <div class="page-header"><h2>${en ? "External Signal Tracker" : "External Signal Tracker"}</h2>
          <div class="muted">${en
            ? "Tracks signals from Telegram channels you follow -- completely separate fake-money book from your own Paper Trading. Never mixed, never averaged together."
            : "Un Telegram channels ke signals track karta hai jinhein aap follow karte hain -- yeh aapki apni Paper Trading se bilkul alag, nakli paise ka hisaab hai. Kabhi mix nahi hota."}</div>
        </div>

        <div class="card" style="margin-bottom:16px;">
          <div class="section-title">${en ? "Add a Channel" : "Channel Add Karein"}</div>
          <div class="form-row"><label>${en ? "Name (for your own reference)" : "Naam (sirf aapke liye)"}</label>
            <input id="extAddName" placeholder="${en ? "e.g. Crypto VIP Signals" : "misaal: Crypto VIP Signals"}"></div>
          <div class="form-row"><label>${en ? "Telegram username or id you're a member of" : "Telegram username ya id jiske aap member hain"}</label>
            <input id="extAddHandle" placeholder="@channel_username"></div>
          <button class="btn" id="extAddBtn">${en ? "Add Channel" : "Channel Add Karein"}</button>
          <div class="muted" id="extAddResult" style="margin-top:6px;"></div>
        </div>

        <div class="section-title">${en ? "Your Channels" : "Aapke Channels"}</div>
        <div class="table-wrap"><table>
          <thead><tr><th>${en ? "Name" : "Naam"}</th><th>${en ? "Source Label" : "Source Label"}</th>
            <th>${en ? "Status" : "Status"}</th><th>${en ? "Proving Progress" : "Proving Progress"}</th>
            <th>${en ? "Result" : "Natija"}</th><th></th></tr></thead>
          <tbody>${(channelsRes.channels || []).map(c => {
            const comp = (comparisonRes.channels || []).find(r => r.channel_id === c.id) || {};
            return `
            <tr>
              <td>${esc(c.name)}</td>
              <td><span class="pill pill-muted">${esc(c.forwarding_source_label || "-")}</span></td>
              <td>${c.enabled
                ? `<span class="pill pill-bullish">${en ? "Enabled" : "Chalu"}</span>`
                : `<span class="pill pill-muted">${en ? "Disabled" : "Band"}</span>`}</td>
              <td>${comp.proving_progress ?? 0}/${comp.proving_required ?? 30}</td>
              <td>${comp.honest_label ? esc(comp.honest_label) : (en ? "No trades yet" : "Abhi koi trade nahi")}</td>
              <td>
                <button class="btn-ghost ext-view" data-id="${esc(c.id)}" data-name="${esc(c.name)}">${en ? "View" : "Dekhein"}</button>
                ${c.enabled
                  ? `<button class="btn-ghost ext-disable" data-id="${esc(c.id)}">${en ? "Disable" : "Band Karein"}</button>`
                  : `<button class="btn-ghost ext-enable" data-id="${esc(c.id)}">${en ? "Enable" : "Chalu Karein"}</button>`}
                <button class="btn-ghost ext-remove" data-id="${esc(c.id)}" data-name="${esc(c.name)}">${en ? "Remove" : "Hatayein"}</button>
              </td>
            </tr>`;
          }).join("") || `<tr><td colspan="6">${en ? "No channels added yet." : "Abhi koi channel add nahi hua."}</td></tr>`}</tbody>
        </table></div>

        <div id="extChannelDetail" style="margin-top:16px;"></div>

        <div class="card" style="margin-top:16px;">
          <div class="section-title">${en ? "Telegram Reading Connection" : "Telegram Padhne Ka Connection"}</div>
          <p class="muted">${en
            ? "Reading channels you're a member of needs your OWN Telegram login (not a bot) -- see the setup guide below."
            : "Jin channels ke aap member hain unhein padhne ke liye aapka apna Telegram login chahiye (bot nahi) -- neeche guide dekhein."}</p>
          <div class="form-row"><label>api_id (my.telegram.org)</label><input id="extApiId" placeholder="1234567" value="${settingsRes.telegram_api_id || ""}"></div>
          <div class="form-row"><label>api_hash (my.telegram.org)</label><input id="extApiHash" placeholder="${settingsRes.telegram_api_hash === "SET" ? "•••••• (already saved)" : "abcdef0123456789..."}"></div>
          <button class="btn" id="extSaveCreds">${en ? "Save Credentials" : "Credentials Save Karein"}</button>
          <div class="muted" id="extCredsResult" style="margin-top:6px;"></div>
          <details style="margin-top:10px;">
            <summary>${en ? "How do I get api_id / api_hash? (step by step)" : "api_id / api_hash kaise milega? (ek-ek step)"}</summary>
            <ol style="margin-top:8px;line-height:1.7;">
              <li>${en ? "Apne phone/computer se my.telegram.org kholein." : "Apne phone/computer se my.telegram.org kholein."}</li>
              <li>${en ? "Apna wahi phone number daalein jo aapke Telegram account mein hai, phir Telegram par aane wala code daalein." : "Apna wahi phone number daalein jo aapke Telegram account mein hai, phir Telegram par aane wala code daalein."}</li>
              <li>${en ? "'API development tools' par click karein." : "'API development tools' par click karein."}</li>
              <li>${en ? "Ek form aayega -- 'App title' aur 'Short name' mein kuch bhi likh dein (misaal: SINDHU), baaki khaali chod sakte hain." : "Ek form aayega -- 'App title' aur 'Short name' mein kuch bhi likh dein (misaal: SINDHU), baaki khaali chod sakte hain."}</li>
              <li>${en ? "'Create application' dabayein -- ab aapko api_id (numbers) aur api_hash (letters+numbers) dikhega." : "'Create application' dabayein -- ab aapko api_id (numbers) aur api_hash (letters+numbers) dikhega."}</li>
              <li>${en ? "Yeh dono values yahan upar copy-paste kar dein aur Save Credentials dabayein." : "Yeh dono values yahan upar copy-paste kar dein aur Save Credentials dabayein."}</li>
              <li>${en ? "Yeh sirf AAPKE apne Telegram account tak access deta hai -- kisi aur ke saath share na karein." : "Yeh sirf AAPKE apne Telegram account tak access deta hai -- kisi aur ke saath share na karein."}</li>
            </ol>
            <p class="muted">${en
              ? "Login (phone number + code, and a session) is a separate one-time step done together in a live session, since Telegram sends the code straight to your phone -- ask to set this up when you're ready."
              : "Login (phone number + code, aur session banana) ek alag, sirf-ek-baar wala step hai jo live session mein saath milkar karte hain, kyunke Telegram code seedha aapke phone par bhejta hai -- jab ready hon to bata dein."}</p>
          </details>
        </div>

        <div class="card" style="margin-top:16px;">
          <div class="section-title">${en ? "Forwarding Settings" : "Forwarding Settings"}</div>
          <p class="muted">${en
            ? "Once a channel proves itself (30 closed trades AND profitable), its NEW signals get forwarded here in real time -- the source is never named, only a stable label like \"Source A\"."
            : "Jab koi channel khud ko saabit kar de (30 band trades AUR profitable), to uske NAYE signals yahan real-time forward hote hain -- source ka naam kabhi nahi batata, sirf ek stable label jaise \"Source A\"."}</p>
          <div class="form-row"><label>${en ? "Forwarding Bot Token" : "Forwarding Bot Token"}</label>
            <input id="extBotToken" placeholder="${settingsRes.forward_bot_token === "SET" ? "•••••• (already saved)" : "123456:ABC-DEF..."}"></div>
          <div class="form-row"><label>${en ? "Destination Channel/Chat ID" : "Destination Channel/Chat ID"}</label>
            <input id="extForwardChatId" placeholder="-1001234567890"></div>
          <button class="btn" id="extSaveForwarding">${en ? "Save Forwarding Settings" : "Forwarding Settings Save Karein"}</button>
          <div class="muted" id="extForwardingResult" style="margin-top:6px;"></div>
        </div>
      `;

      document.getElementById("extAddBtn").onclick = async () => {
        const name = document.getElementById("extAddName").value.trim();
        const handle = document.getElementById("extAddHandle").value.trim();
        const resultEl = document.getElementById("extAddResult");
        if (!name || !handle) {
          resultEl.textContent = en ? "Name and Telegram handle are both required." : "Naam aur Telegram handle dono zaroori hain.";
          return;
        }
        try {
          await apiPost("/api/external-signals/channels", { name, telegram_identifier: handle });
          resultEl.textContent = en ? "Added!" : "Add ho gaya!";
          await render();
        } catch (e) {
          resultEl.textContent = `${en ? "Failed" : "Nahi hua"}: ${e.message}`;
        }
      };

      content.querySelectorAll(".ext-enable").forEach(btn => btn.onclick = async () => {
        await apiPost(`/api/external-signals/channels/${btn.dataset.id}/enable`);
        await render();
      });
      content.querySelectorAll(".ext-disable").forEach(btn => btn.onclick = async () => {
        await apiPost(`/api/external-signals/channels/${btn.dataset.id}/disable`);
        await render();
      });
      content.querySelectorAll(".ext-remove").forEach(btn => btn.onclick = async () => {
        if (!confirm(en ? `Remove "${btn.dataset.name}"? Its trade history is kept, only the channel entry is removed.` : `"${btn.dataset.name}" hatayein? Trade history rehti hai, sirf channel entry hatti hai.`)) return;
        await apiDelete(`/api/external-signals/channels/${btn.dataset.id}`);
        await render();
      });
      content.querySelectorAll(".ext-view").forEach(btn => btn.onclick = () => renderChannelDetail(btn.dataset.id, btn.dataset.name));

      document.getElementById("extSaveCreds").onclick = async () => {
        const telegram_api_id = document.getElementById("extApiId").value.trim();
        const telegram_api_hash = document.getElementById("extApiHash").value.trim();
        const resultEl = document.getElementById("extCredsResult");
        try {
          await apiPost("/api/external-signals/settings", {
            ...(telegram_api_id ? { telegram_api_id } : {}),
            ...(telegram_api_hash ? { telegram_api_hash } : {}),
          });
          resultEl.textContent = en ? "Saved." : "Save ho gaya.";
        } catch (e) {
          resultEl.textContent = `${en ? "Failed" : "Nahi hua"}: ${e.message}`;
        }
      };

      document.getElementById("extSaveForwarding").onclick = async () => {
        const forward_bot_token = document.getElementById("extBotToken").value.trim();
        const forward_channel_id = document.getElementById("extForwardChatId").value.trim();
        const resultEl = document.getElementById("extForwardingResult");
        try {
          await apiPost("/api/external-signals/settings", {
            ...(forward_bot_token ? { forward_bot_token } : {}),
            ...(forward_channel_id ? { forward_channel_id } : {}),
          });
          resultEl.textContent = en ? "Saved." : "Save ho gaya.";
        } catch (e) {
          resultEl.textContent = `${en ? "Failed" : "Nahi hua"}: ${e.message}`;
        }
      };
    }

    async function renderChannelDetail(channelId, channelName) {
      const [report, signalsRes, positionsRes] = await Promise.all([
        apiGet(`/api/external-signals/channels/${channelId}/report`).catch(() => null),
        apiGet(`/api/external-signals/channels/${channelId}/signals?limit=20`).catch(() => ({ signals: [] })),
        apiGet(`/api/external-signals/channels/${channelId}/positions`).catch(() => ({ positions: [] })),
      ]);
      if (!report) return;
      const box = document.getElementById("extChannelDetail");
      box.innerHTML = `
        <div class="card">
          <div class="section-title">${esc(channelName)} -- ${en ? "Real Results" : "Asli Natija"}</div>
          <div class="stats-row" style="display:flex;gap:24px;flex-wrap:wrap;margin-bottom:10px;">
            <div><div class="muted">${en ? "Balance" : "Balance"}</div><div style="font-size:20px;font-weight:700;">$${report.balance}</div></div>
            <div><div class="muted">${en ? "Closed / Open / Pending" : "Band / Khula / Pending"}</div><div style="font-size:20px;font-weight:700;">${report.closed_trades} / ${report.open_trades} / ${report.pending_trades}</div></div>
            <div><div class="muted">${en ? "Win Rate" : "Win Rate"}</div><div style="font-size:20px;font-weight:700;">${report.win_rate_pct != null ? report.win_rate_pct + "%" : "-"}</div></div>
            <div><div class="muted">${en ? "Total PnL" : "Total PnL"}</div><div style="font-size:20px;font-weight:700;">$${report.total_pnl}</div></div>
            <div><div class="muted">${en ? "Avg R:R Achieved" : "Avg R:R"}</div><div style="font-size:20px;font-weight:700;">${report.avg_rr ?? "-"}</div></div>
            <div><div class="muted">${en ? "Best Coin" : "Best Coin"}</div><div style="font-size:20px;font-weight:700;">${report.best_coin ? esc(report.best_coin.symbol) : "-"}</div></div>
            <div><div class="muted">${en ? "Worst Coin" : "Worst Coin"}</div><div style="font-size:20px;font-weight:700;">${report.worst_coin ? esc(report.worst_coin.symbol) : "-"}</div></div>
          </div>
          <div style="height:8px;border-radius:4px;background:var(--border,#333);overflow:hidden;max-width:400px;">
            <div style="height:100%;width:${Math.min(100, (report.proving_progress / report.proving_required) * 100)}%;background:var(--accent,#4caf82);"></div>
          </div>
          <div class="muted" style="margin-top:4px;">${report.proving_progress}/${report.proving_required} ${en ? "trades toward the proving threshold" : "trades proving threshold ki taraf"}${!report.is_proven_sample_size ? (en ? " -- numbers still unproven, can change a lot" : " -- abhi numbers saabit nahi, kaafi badal sakte hain") : ""}</div>

          <div class="section-title" style="margin-top:14px;">${en ? "Recent Signals" : "Haal Ke Signals"}</div>
          <div class="table-wrap"><table>
            <thead><tr><th>${en ? "Coin" : "Coin"}</th><th>${en ? "Direction" : "Direction"}</th><th>${en ? "Entries" : "Entries"}</th><th>${en ? "Status" : "Status"}</th></tr></thead>
            <tbody>${(signalsRes.signals || []).map(s => `
              <tr>
                <td>${esc(s.symbol || "-")}</td>
                <td>${s.direction ? esc(s.direction) : "-"}</td>
                <td>${(s.entries || []).map(e => e.price).join(", ") || "-"}</td>
                <td>${s.is_signal
                  ? `<span class="pill pill-bullish">${en ? "Parsed" : "Samjha Gaya"}</span>`
                  : `<span class="pill pill-muted" title="${esc(s.reject_reason || "")}">${en ? "Not a signal" : "Signal Nahi"}</span>`}</td>
              </tr>`).join("") || `<tr><td colspan="4">${en ? "No signals yet." : "Abhi koi signal nahi."}</td></tr>`}</tbody>
          </table></div>

          <div class="section-title" style="margin-top:14px;">${en ? "Positions" : "Positions"}</div>
          <div class="table-wrap"><table>
            <thead><tr><th>${en ? "Coin" : "Coin"}</th><th>${en ? "Direction" : "Direction"}</th><th>${en ? "Avg Entry" : "Avg Entry"}</th><th>${en ? "Filled %" : "Filled %"}</th><th>${en ? "Status" : "Status"}</th><th>${en ? "PnL" : "PnL"}</th></tr></thead>
            <tbody>${(positionsRes.positions || []).map(p => `
              <tr>
                <td>${esc(p.symbol)}</td><td>${esc(p.direction)}</td>
                <td>${p.avg_entry_price ?? "-"}</td><td>${p.filled_size_pct}%</td>
                <td>${p.status}</td><td>${p.pnl != null ? "$" + p.pnl.toFixed(2) : "-"}</td>
              </tr>`).join("") || `<tr><td colspan="6">${en ? "No positions yet." : "Abhi koi position nahi."}</td></tr>`}</tbody>
          </table></div>
        </div>`;
      box.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    await render();
  }

  // ------------------------------------------------------------ SIGNAL TRACKER (Batch 6, Task 5)
  async function renderSignalTracker() {
    const myToken = activeRouteToken;

    async function render() {
      const [feed, table] = await Promise.all([
        apiGet("/api/paper-trading/signal-tracker/feed"),
        apiGet("/api/paper-trading/signal-tracker/match-table"),
      ]);
      if (isStaleRoute(myToken)) return;

      const en = getLang() === "en";
      const outcomeLabel = (o) => ({
        win: en ? "Win" : "Jeet", loss: en ? "Loss" : "Haar",
        breakeven: en ? "Breakeven" : "Barabar", pending: en ? "Pending" : "Chal Raha Hai",
        unknown: en ? "Unknown" : "Pata Nahi",
      }[o] || o);
      const outcomePill = (o) => {
        const cls = o === "win" ? "pill-bullish" : o === "loss" ? "pill-bearish" : "pill-muted";
        return `<span class="pill ${cls}">${outcomeLabel(o)}</span>`;
      };
      const fmtRate = (v) => v == null
        ? (en ? `not enough trades yet` : `abhi kaafi trades nahi huay`)
        : `${v.toFixed(1)}%`;

      const summaryLine = feed.win_rate_pct == null
        ? (en
          ? `${feed.total_signals} signals sent so far, ${feed.closed} closed, ${feed.pending} still open -- win rate needs ${feed.min_sample_size} closed signals before it's shown (only ${feed.closed} so far).`
          : `Ab tak ${feed.total_signals} signals bheje gaye, ${feed.closed} band ho chuke, ${feed.pending} abhi khule hain -- win rate dikhane ke liye ${feed.min_sample_size} band signals chahiye (abhi sirf ${feed.closed}).`)
        : (en
          ? `${feed.total_signals} signals sent, ${feed.closed} closed at a real ${feed.win_rate_pct}% win rate, ${feed.pending} still open.`
          : `${feed.total_signals} signals bheje gaye, ${feed.closed} band hue jinka asli win rate ${feed.win_rate_pct}% hai, ${feed.pending} abhi khule hain.`);

      content.innerHTML = `
        <div class="section-title">${en ? "Signal Tracker" : "Signal Tracker"}</div>
        <p class="muted">${en
          ? "Every real signal sent to Telegram, tracked from send to real outcome, plus a side-by-side check of whether backtest, paper trading, and Telegram-sent results still agree with each other. Read-only -- never sends a signal or changes anything."
          : "Telegram par bheja gaya har asli signal, send se le kar asli outcome tak track kiya gaya, saath hi yeh check ke backtest, paper trading, aur Telegram-sent results abhi bhi aapas mein match karte hain ya nahi. Sirf report karta hai -- na koi signal bhejta hai na kuch badalta hai."}</p>

        <div class="section-title">${en ? "Running Summary" : "Chalta Hua Khulasa"}</div>
        <p>${summaryLine}</p>

        <div class="section-title">${en ? "Recent Signals" : "Haal Ke Signals"}</div>
        <div class="table-wrap"><table>
          <thead><tr>
            <th>${en ? "Strategy" : "Strategy"}</th><th>${en ? "Symbol" : "Symbol"}</th>
            <th>${en ? "Direction" : "Direction"}</th><th>${en ? "Sent At" : "Kab Bheja"}</th>
            <th>${en ? "Outcome" : "Nateeja"}</th><th>${en ? "Grade" : "Grade"}</th>
            <th>${en ? "Why This Signal" : "Yeh Signal Kyun"}</th>
          </tr></thead>
          <tbody>
            ${feed.signals.map(s => `<tr>
              <td>${esc(s.strategy_name || s.strategy_id || "-")}</td>
              <td>${esc(s.symbol || "-")}</td>
              <td>${esc(s.direction || "-")}</td>
              <td>${esc((s.sent_at || "").slice(0, 16).replace("T", " "))}</td>
              <td>${outcomePill(s.outcome)}</td>
              <td>${s.quality_grade
                ? `<span class="pill ${s.quality_grade === "A+" || s.quality_grade === "A" ? "pill-bullish" : s.quality_grade === "B" ? "pill-muted" : "pill-bearish"}" title="${esc(s.grade_reason || "")}">${esc(s.quality_grade)}</span>`
                : "-"}</td>
              <td class="muted" style="font-size:12px;max-width:320px;">${esc(s.explanation_text || (en ? "not recorded" : "record nahi hai"))}</td>
            </tr>`).join("") || `<tr><td colspan="7">${en ? "No signals sent yet." : "Abhi tak koi signal nahi bheja gaya."}</td></tr>`}
          </tbody>
        </table></div>

        <div class="section-title">${en ? "Backtest vs Paper vs Telegram -- Per Strategy" : "Backtest vs Paper vs Telegram -- Har Strategy Ke Liye"}</div>
        <p class="muted" style="font-size:12px;">${en
          ? `A win rate only appears once at least ${table.min_sample_size} closed trades back it -- and a divergence is only flagged once BOTH the paper and Telegram-sent sides clear that same floor and disagree by ${table.divergence_threshold_pct} percentage points or more.`
          : `Win rate tabhi dikhega jab kam se kam ${table.min_sample_size} band trades uske peeche hon -- aur divergence tabhi flag hoga jab paper aur Telegram-sent dono sides yeh had paar karein aur ${table.divergence_threshold_pct} percentage points ya zyada se alag ho.`}</p>
        <div class="table-wrap"><table>
          <thead><tr>
            <th>${en ? "Strategy" : "Strategy"}</th>
            <th>${en ? "Backtest Win Rate" : "Backtest Win Rate"}</th>
            <th>${en ? "Paper Win Rate" : "Paper Win Rate"}</th>
            <th>${en ? "Telegram-Sent Win Rate" : "Telegram-Sent Win Rate"}</th>
            <th>${en ? "Backtest vs Paper" : "Backtest vs Paper"}</th>
            <th>${en ? "Paper vs Telegram-Sent" : "Paper vs Telegram-Sent"}</th>
          </tr></thead>
          <tbody>
            ${table.strategies.map(s => `<tr>
              <td>${esc(s.strategy_name)}</td>
              <td>${fmtRate(s.backtest_win_rate)}</td>
              <td>${fmtRate(s.paper_win_rate)} <span class="muted">(${s.paper_closed_trades})</span></td>
              <td>${fmtRate(s.telegram_win_rate)} <span class="muted">(${s.telegram_closed_trades})</span></td>
              <td>${s.backtest_vs_paper_diverges
                ? `<span class="pill pill-bearish" title="${en ? "An alert is also raised on the Alerts page once this is detected." : "Alerts page par bhi alert ban jaata hai jab yeh detect hota hai."}">${en ? "Diverges" : "Farq Hai"}</span>`
                : `<span class="pill pill-bullish">${en ? "In line" : "Theek Match"}</span>`}</td>
              <td>${s.diverges
                ? `<span class="pill pill-bearish">${en ? "Diverges" : "Farq Hai"}</span>`
                : `<span class="pill pill-bullish">${en ? "In line" : "Theek Match"}</span>`}</td>
            </tr>`).join("") || `<tr><td colspan="6">${en ? "No strategies with closed trades yet." : "Abhi tak koi strategy ka trade band nahi hua."}</td></tr>`}
          </tbody>
        </table></div>`;
    }

    await render();
  }

  // ------------------------------------------------------------ SINDHU STRATEGY (Phase 7A, Part B)
  async function renderSindhuStrategy() {
    const myToken = activeRouteToken;
    let filter = "all"; // all | ai | non_ai

    async function render() {
      const [dailyLog, candidatesRes] = await Promise.all([
        apiGet("/api/sindhu-strategy/daily-log"),
        apiGet("/api/sindhu-strategy/candidates"),
      ]);
      if (isStaleRoute(myToken)) return;

      let candidates = candidatesRes.candidates || [];
      if (filter === "ai") candidates = candidates.filter(c => c.made_with_ai);
      if (filter === "non_ai") candidates = candidates.filter(c => !c.made_with_ai);
      candidates = candidates.slice().sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));

      content.innerHTML = `
        <div class="section-title">SINDHU Strategy</div>
        <p class="muted">Generates entirely new BOT strategy candidates from scratch every day -- exactly 11, of which exactly 1 uses a single AI call and 10 are pure deterministic recombination of DNA blocks. Every candidate is saved permanently and labeled, whether AI-made or not.</p>
        <div class="grid">
          ${card("Today's Date", esc(dailyLog.date))}
          ${card("Candidates Generated Today", `${fmtNum(dailyLog.candidates_generated)} <span class="muted">/ 11</span>`)}
          ${cardClass("AI Call Used Today", dailyLog.ai_calls_used ? "<span class=\"pill pill-bullish\">Yes (1/1)</span>" : "<span class=\"pill pill-muted\">Not yet (0/1)</span>", "")}
          ${card("Total Candidates (all-time)", fmtNum((candidatesRes.candidates || []).length))}
        </div>

        <div class="section-title">Control Center</div>
        <div class="btn-row">
          <button class="btn" id="sstratGenerate">Generate Today's Candidates Now</button>
          <span id="sstratStatusMsg" class="muted"></span>
        </div>

        <div class="section-title">Candidates</div>
        <div class="btn-row">
          <button class="btn-ghost ${filter === "all" ? "active" : ""}" id="sstratFilterAll">All</button>
          <button class="btn-ghost ${filter === "ai" ? "active" : ""}" id="sstratFilterAi">Made with AI</button>
          <button class="btn-ghost ${filter === "non_ai" ? "active" : ""}" id="sstratFilterNonAi">Made without AI</button>
        </div>
        <div class="table-wrap"><table>
          <thead><tr><th>Name</th><th>Label</th><th>Evolution Score</th><th>Created</th></tr></thead>
          <tbody>
            ${candidates.slice(0, 200).map(c => `
              <tr>
                <td>${esc(c.name)} <span class="muted">(${esc(c.id)})</span></td>
                <td><span class="pill ${c.made_with_ai ? "pill-bullish" : "pill-muted"}">${c.made_with_ai ? "Made with AI" : "Made without AI"}</span></td>
                <td>${c.evolution_score != null ? Number(c.evolution_score).toFixed(2) : "not backtested yet"}</td>
                <td>${esc((c.created_at || "").slice(0, 19))}</td>
              </tr>`).join("") || '<tr><td colspan="4">No candidates generated yet -- click "Generate Today\'s Candidates Now", or wait for the daily scheduler.</td></tr>'}
          </tbody>
        </table></div>`;

      document.getElementById("sstratGenerate").onclick = async () => {
        document.getElementById("sstratStatusMsg").textContent = "Generating...";
        try {
          const res = await apiPost("/api/sindhu-strategy/generate", {}, 180000);
          document.getElementById("sstratStatusMsg").textContent = `Created ${res.count} candidate(s).`;
          await render();
        } catch (e) { document.getElementById("sstratStatusMsg").textContent = `Failed: ${e.message}`; }
      };
      document.getElementById("sstratFilterAll").onclick = () => { filter = "all"; render(); };
      document.getElementById("sstratFilterAi").onclick = () => { filter = "ai"; render(); };
      document.getElementById("sstratFilterNonAi").onclick = () => { filter = "non_ai"; render(); };
    }

    await render();
  }

  // ------------------------------------------------------------ WEB-SOURCED STRATEGIES (Part 3)
  // A dedicated, clearly-labeled view of every strategy that came from the
  // Autonomous Strategy Research feature (separate from anything manually
  // pasted) -- every one of these already went through the exact same
  // validation pipeline (safety check, backtest, Walk-Forward) as any
  // other saved strategy; this page is pure visibility, nothing special
  // happens to them.
  async function renderWebSourcedStrategies() {
    const myToken = activeRouteToken;
    async function render() {
      const [listRes, runsRes] = await Promise.all([
        apiGet("/api/research/web-sourced-strategies").catch(() => ({ strategies: [], count: 0 })),
        apiGet("/api/research/runs?limit=10").catch(() => ({ runs: [], runs_used_today: 0, settings: { max_runs_per_day: 1 } })),
      ]);
      if (isStaleRoute(myToken)) return;
      const settings = runsRes.settings || { max_runs_per_day: 1 };

      content.innerHTML = `
        <div class="section-title">Web-Sourced Strategies</div>
        <p class="muted" style="margin-top:-10px;">Every strategy on this page was discovered automatically by the Autonomous Strategy Research feature (a web search or a single trusted article) -- never manually pasted. Each one went through the exact same checks (Safety Check, Backtest, Walk-Forward Test) as any other saved strategy; nothing here gets special treatment.</p>

        <div class="grid">
          ${card("Web-Sourced Strategies", fmtNum(listRes.count))}
          ${card("Research Runs Today", `${runsRes.runs_used_today} / ${settings.max_runs_per_day}`)}
        </div>

        <div class="section-title">Run Research Now</div>
        <div class="card">
          <div class="form-row"><label>Search Query</label><input id="wsQuery" placeholder="e.g. ICT order block strategy"></div>
          <div class="btn-row">
            <button class="btn" id="wsRunSearch">Search &amp; Queue</button>
            <span id="wsRunStatus" class="muted"></span>
          </div>
          <div class="muted" style="font-size:11.5px;margin-top:6px;">Limited to ${settings.max_runs_per_day} run(s) per day (change this below) -- respects trusted-source-only rules, same as before.</div>
        </div>

        <div class="section-title">Strategies Found</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Strategy</th><th>Safety Status</th><th>Source</th><th>Source URL</th><th>Article</th><th>Queued</th></tr></thead>
          <tbody>${listRes.strategies.map(s => `
            <tr>
              <td>${esc(s.strategy_name || s.strategy_id)}</td>
              <td><span class="pill ${s.safety_status === "ready" ? "pill-bullish" : s.safety_status ? "pill-error" : "pill-muted"}">${esc(s.safety_status || "unknown")}</span></td>
              <td><span class="pill pill-neutral">${esc(s.source)}</span></td>
              <td><a href="${esc(s.source_url)}" target="_blank" rel="noopener noreferrer">${esc(s.source_domain)}</a></td>
              <td style="max-width:260px;">${esc(s.document_title || "-")}</td>
              <td>${esc((s.queued_at || "").slice(0, 10))}</td>
            </tr>`).join("") || `<tr><td colspan="6">No web-sourced strategies yet -- none have been discovered by Autonomous Strategy Research so far. Run a search above, or check back after it finds something worth queuing.</td></tr>`}</tbody>
        </table></div>

        <div class="section-title">Recent Research Runs</div>
        <div class="table-wrap"><table>
          <thead><tr><th>When</th><th>Type</th><th>Query / URL</th><th>Queued</th></tr></thead>
          <tbody>${(runsRes.runs || []).map(r => `
            <tr><td>${esc((r.run_at || "").slice(0, 19))}</td><td>${esc(r.kind)}</td>
            <td>${esc(r.query_or_url || "-")}</td><td>${r.queued_count}</td></tr>`).join("")
            || '<tr><td colspan="4">No research runs yet.</td></tr>'}</tbody>
        </table></div>

        <div class="section-title">Research Rate Limit</div>
        <div class="card" style="max-width:420px;">
          <div class="form-row"><label>Max Research Runs Per Day</label><input id="wsMaxRuns" type="number" min="1" value="${settings.max_runs_per_day}"></div>
          <div class="muted" style="font-size:11.5px;">Keeps Autonomous Strategy Research from making too many outside web/AI calls -- one run is one search or one single-URL queue.</div>
          <div class="btn-row"><button class="btn" id="wsSaveRateLimit">Save</button><span id="wsRateLimitStatus" class="muted"></span></div>
        </div>
      `;

      document.getElementById("wsRunSearch").onclick = async () => {
        const status = document.getElementById("wsRunStatus");
        const query = document.getElementById("wsQuery").value.trim();
        if (!query) { status.textContent = "Enter a search query first."; return; }
        status.textContent = "Searching...";
        try {
          const res = await apiPost("/api/research/search", { query, max_results: 5 });
          status.textContent = `Queued ${((res.queued || []).length)} article(s), skipped ${(res.skipped || []).length}.`;
          render();
        } catch (e) {
          status.textContent = `Failed: ${e.message}`;
        }
      };

      document.getElementById("wsSaveRateLimit").onclick = async () => {
        const status = document.getElementById("wsRateLimitStatus");
        const value = parseInt(document.getElementById("wsMaxRuns").value, 10);
        if (!value || value < 1) { status.textContent = "Must be at least 1."; return; }
        status.textContent = "Saving...";
        await apiPost("/api/research/settings", { max_runs_per_day: value });
        status.textContent = "Saved.";
        render();
      };
    }
    await render();
  }

  // Batch 10, Task 3: Live Market Scan indicator -- presentation only,
  // reflects the engine's REAL last-tick shortlist (paper_trading.engine.
  // PaperTradingEngine._tick's `shortlisted_symbols`, already returned as
  // status.last_summary.shortlisted -- no new backend logic, no change to
  // scanning timing/order/triggers). A CSS pulse + a plain text cycle
  // through the real coin list, refreshed automatically because the page
  // already re-renders on every real "paper" channel tick event.
  let _scanCycleTimer = null;
  function scanIndicatorHtml(status) {
    if (!status.running) return "";
    const coins = (status.last_summary && status.last_summary.shortlisted) || [];
    const en = getLang() === "en";
    return `
      <div class="card scan-indicator" style="margin-bottom:16px;">
        <div style="display:flex;align-items:center;gap:12px;">
          <span class="scan-pulse"></span>
          <div>
            <div style="font-weight:600;font-size:13px;">${en ? "Live Market Scan" : "Live Market Scan"}</div>
            <div class="muted" style="font-size:12px;" id="scanCycleText">
              ${coins.length
                ? `${en ? "Scanning" : "Scan Ho Raha Hai"}: <span id="scanCycleCoin">${esc(coins[0])}</span> (${coins.length} ${en ? "coins this tick" : "coins is tick mein"})`
                : (en ? "No coins shortlisted yet -- waiting for the next tick." : "Abhi tak koi coin shortlist nahi hui -- agle tick ka intezaar.")}
            </div>
          </div>
        </div>
      </div>`;
  }
  function startScanCycle(coins) {
    clearInterval(_scanCycleTimer);
    if (!coins || !coins.length) return;
    let i = 0;
    _scanCycleTimer = setInterval(() => {
      const el = document.getElementById("scanCycleCoin");
      if (!el) { clearInterval(_scanCycleTimer); return; }
      i = (i + 1) % coins.length;
      el.textContent = coins[i];
    }, 1400);
  }

  // ------------------------------------------------------------ PAPER TRADING
  // Paper Trading sub-navigation: the page has grown into ~18 distinct
  // sections (status, alerts, portfolio/risk, analytics, trade history,
  // engine settings...) that used to all sit on one long scroll. These
  // panels group them into 5 sub-tabs WITHOUT changing any data fetch,
  // calculation, or moving anything out of the Paper Trading page --
  // every panel still renders from the exact same render() call below,
  // just tagged with data-pt-tab so only the active group is visible at
  // once (CSS display toggle, not conditional rendering) -- this keeps
  // every existing element id and event handler wiring completely
  // unchanged, since all elements still exist in the DOM at all times.
  const PT_TABS = [
    ["overview", "Overview"], ["analytics", "Analytics"],
    ["challenge", "Challenge"], ["portfolio", "Portfolio & Risk"],
    ["history", "Trade History"], ["settings", "Settings"],
  ];
  function ptTabBarHtml(active) {
    return `<div class="pill-tabs">${PT_TABS.map(([id, label]) => `
      <button class="pill-tab ${id === active ? "active" : ""}" data-pt-tab-btn="${id}">${label}</button>
    `).join("")}</div>`;
  }

  async function renderPaperTrading() {
    const myToken = activeRouteToken;
    let activePtTab = "overview";
    let ptStrategySectionFilter = "profitable";
    const render = async () => {
      const [status, positionsRes, tradesRes, decisionsRes, stratPerfRes, lessonPerfRes,
             settings, strategiesRes, lessonsRes, allTimeAnalytics, alertsRes, sessionsRes, hourOfDayRes,
             candidatesRes, portfolioRes, riskScoreRes, exposureRes, corrWarningsRes, strategyCorrMatrixRes, coinHeatmapRes,
             strategyExposureRes, directionExposureRes, customRulesRes, patternReliabilityRes,
             lifecycleRes, configsRes, pausedRes, killSwitch, acctDrawdown, coinBlacklistRes,
             riskPctRecsRes, dupExposureRes] = await Promise.all([
        apiGet("/api/paper-trading/status"),
        apiGet("/api/paper-trading/positions"),
        apiGet("/api/paper-trading/trades?limit=50"),
        apiGet("/api/paper-trading/decisions?limit=30"),
        apiGet("/api/paper-trading/strategy-performance"),
        apiGet("/api/paper-trading/lesson-performance"),
        apiGet("/api/paper-trading/settings"),
        apiGet("/api/backtesting/strategies").catch(() => ({ strategies: [] })),
        apiGet("/api/knowledge/lessons?status=active").catch(() => ({ lessons: [] })),
        apiGet("/api/paper-trading/analytics?period=all"),
        apiGet("/api/paper-trading/alerts?limit=10").catch(() => ({ alerts: [] })),
        apiGet("/api/paper-trading/session-stats").catch(() => ({ sessions: [] })),
        apiGet("/api/paper-trading/hour-of-day-stats").catch(() => ({ hours: [] })),
        apiGet("/api/paper-trading/lesson-candidates").catch(() => ({ candidates: [] })),
        apiGet("/api/paper-trading/portfolio").catch(() => null),
        apiGet("/api/paper-trading/portfolio-risk-score").catch(() => null),
        apiGet("/api/paper-trading/coin-exposure").catch(() => ({ exposure: [] })),
        apiGet("/api/paper-trading/correlation-warnings").catch(() => ({ warnings: [] })),
        apiGet("/api/paper-trading/strategy-correlation-matrix").catch(() => ({ strategies: [], matrix: [] })),
        apiGet("/api/paper-trading/coin-heatmap").catch(() => ({ coins: [] })),
        apiGet("/api/paper-trading/strategy-exposure").catch(() => ({ exposure: [] })),
        apiGet("/api/paper-trading/direction-exposure").catch(() => ({ long: null, short: null })),
        apiGet("/api/paper-trading/custom-alert-rules").catch(() => ({ rules: [], metric_choices: [], comparison_choices: [] })),
        apiGet("/api/paper-trading/pattern-reliability").catch(() => ({ min_sample_size: 25, patterns: [] })),
        apiGet("/api/strategy-lifecycle").catch(() => ({ rows: [] })),
        apiGet("/api/paper-trading/strategy-configs").catch(() => ({ configs: {} })),
        apiGet("/api/paper-trading/paused-strategies").catch(() => ({ paused: [] })),
        apiGet("/api/paper-trading/kill-switch/status").catch(() => ({ active: false })),
        apiGet("/api/paper-trading/account-drawdown-status").catch(() => ({ paused: false })),
        apiGet("/api/paper-trading/coin-blacklist").catch(() => ({ blacklist: [] })),
        apiGet("/api/paper-trading/risk-pct-recommendations").catch(() => ({ recommendations: [] })),
        apiGet("/api/paper-trading/duplicate-exposure-warnings").catch(() => ({ warnings: [] })),
      ]);
      if (isStaleRoute(myToken)) return;

      // Per-strategy settings state, keyed by strategy id for O(1) lookup
      // while rendering the settings table.
      const paperConfigs = configsRes.configs || {};
      const pausedIds = {};
      (pausedRes.paused || []).forEach(x => { pausedIds[x.strategy_id] = x; });
      const strategyNameById = {};
      (strategiesRes.strategies || []).forEach(s => { strategyNameById[s.id] = s.name; });

      // Overview cards use the real all-time totals (allTimeAnalytics), not
      // just the 50 most-recently-fetched trades -- with 700+ trades in a
      // real account, deriving "Closed Trades"/"Win Rate"/"Realized PnL"
      // from a capped list silently undercounted all three.
      const trades = tradesRes.trades || [];
      const allTimeSummary = allTimeAnalytics.summary;

      const today = new Date().toISOString().slice(0, 10);
      const todaysTrades = trades.filter(t => (t.closed_at || "").slice(0, 10) === today);
      const todaysPnlPct = todaysTrades.reduce((sum, t) => sum + (t.pnl_pct || 0), 0);
      const goalPct = settings.daily_goal_pct || 2.0;
      const goalProgress = Math.min(Math.max((todaysPnlPct / goalPct) * 100, 0), 100);

      const runningLessons = (lessonsRes.lessons || []).filter(l => l.apply_paper_trading);

      // Master Task 2, Part 2: split every currently-enabled strategy into
      // "Profitable" (real backtest PF > 1.0, same threshold the Compare
      // page already uses) vs "Under Evaluation" (everything else) --
      // classification comes from the real backtest result
      // (strategy-lifecycle), never from live paper-trading PnL (a
      // profitable strategy can have a losing streak in paper trading
      // without becoming "unprofitable" by this definition, and vice versa).
      const backtestPfById = {};
      (lifecycleRes.rows || []).forEach(r => { backtestPfById[r.strategy_id] = r.backtest.profit_factor; });
      const allStrategyRows = allTimeAnalytics.per_strategy || [];
      const profitableRows = allStrategyRows.filter(p => backtestPfById[p.strategy_id] != null && backtestPfById[p.strategy_id] > 1.0);
      const evaluationRows = allStrategyRows.filter(p => !(backtestPfById[p.strategy_id] != null && backtestPfById[p.strategy_id] > 1.0));

      content.innerHTML = `
        <div class="section-title">${t("Paper Trading")}</div>
        ${ptTabBarHtml(activePtTab)}
        <div class="pt-tab-panel" data-pt-tab="overview">
        <div class="grid">
          ${cardClass("Engine Status", status.running ? "<span class=\"pill pill-completed\">Running</span>" : "<span class=\"pill pill-muted\">Stopped</span>", "")}
          ${cardClass("Mode", status.dry_run ? "<span class=\"pill pill-pending\">Dry Run</span>" : "<span class=\"pill pill-bullish\">Live Paper Trading</span>", "")}
          ${card("Combined Balance", `$${Number(status.balance).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}`)}
          ${card("Open Positions", fmtNum(status.open_trades))}
          ${card("Closed Trades (All-Time)", fmtNum(allTimeSummary.closed_trades))}
          ${card("Win Rate (All-Time)", `${allTimeSummary.win_rate.toFixed(1)}%`)}
          ${cardClass("Realized PnL (All-Time)", `${allTimeSummary.total_pnl >= 0 ? "+" : ""}$${allTimeSummary.total_pnl.toFixed(2)}`, allTimeSummary.total_pnl > 0 ? "positive" : allTimeSummary.total_pnl < 0 ? "negative" : "")}
          ${card("Queue (shortlisted coins)", fmtNum(status.queue))}
        </div>
        <div class="muted" style="font-size:12px;">Each strategy runs its own independent book -- balance/PnL/open positions are never merged between strategies. See the breakdown below.</div>

        ${scanIndicatorHtml(status)}
        <div id="ptSignalMatchDetail" class="card" style="display:none;margin-bottom:16px;"></div>

        ${(alertsRes.alerts || []).length ? `
        <div class="section-title">${t("Alerts")}</div>
        <div class="card">
          ${alertsRes.alerts.slice(0, 8).map(a => `
            <div style="padding:4px 0;border-bottom:1px solid var(--border,#333);font-size:13px;">
              <span class="pill ${a.severity === "positive" ? "pill-bullish" : a.severity === "warning" ? "pill-error" : "pill-pending"}">${a.severity === "positive" ? "Strong" : a.severity === "warning" ? "Drawdown" : "Info"}</span>
              ${esc(a.message)}
              <span class="muted" style="float:right;">${esc((a.created_at||"").slice(0,16).replace("T"," "))}</span>
            </div>`).join("")}
        </div>` : ""}

        <div class="section-title">Custom Alert Rules ${helpIcon("custom_alert_rules")}</div>
        <div class="card">
          <p class="muted" style="font-size:12px;margin-top:0;">Define your own "alert me if X" rules on top of the system's built-in alerts.</p>
          <div class="btn-row">
            <select id="carMetric">
              <option value="strategy_pnl">Strategy realized PnL</option>
              <option value="strategy_win_rate">Strategy win rate %</option>
              <option value="consecutive_losses">Strategy consecutive losses</option>
              <option value="account_drawdown_pct">Account-wide drawdown %</option>
            </select>
            <select id="carStrategy"><option value="">(account-wide metrics only)</option>${(strategiesRes.strategies || []).map(s => `<option value="${s.id}">${esc(s.name)}</option>`).join("")}</select>
            <select id="carComparison"><option value="below">drops below</option><option value="above">goes above</option></select>
            <input id="carThreshold" type="number" step="any" placeholder="Threshold" style="max-width:120px;">
            <button class="btn" id="btnAddCustomRule">Add Rule</button>
          </div>
          <div id="carStatus" class="muted"></div>
          <div class="table-wrap" style="margin-top:8px;"><table>
            <thead><tr><th>Name</th><th>Rule</th><th>Enabled</th><th>Last Triggered</th><th></th></tr></thead>
            <tbody>${(customRulesRes.rules || []).map(r => `
              <tr>
                <td>${esc(r.name)}</td>
                <td style="font-size:12px;">${esc(r.metric)}${r.strategy_id ? ` (${esc(strategyNameById[r.strategy_id] || r.strategy_id)})` : ""} ${esc(r.comparison)} ${r.threshold}</td>
                <td><input type="checkbox" class="car-toggle" data-id="${r.id}" ${r.enabled ? "checked" : ""}></td>
                <td style="font-size:12px;">${r.last_triggered_at ? esc(r.last_triggered_at.slice(0, 16).replace("T", " ")) : "-"}</td>
                <td><button class="btn-ghost car-delete" data-id="${r.id}">Delete</button></td>
              </tr>`).join("") || `<tr><td colspan="5">No custom rules yet.</td></tr>`}</tbody>
          </table></div>
        </div>

        <div class="section-title">${getLang() === "en" ? "Coin Blacklist" : "Coin Blacklist"} ${helpIcon("coin_blacklist")}</div>
        <div class="card">
          <p class="muted" style="font-size:12px;margin-top:0;">${getLang() === "en"
            ? "Coins listed here are never traded by any strategy -- removed before they're even ranked, no matter how strong their activity score would otherwise be."
            : "Yahan listed coins kisi bhi strategy se trade nahi hote -- ranking se pehle hi hata diye jaate hain, chahe unka activity score kitna hi acha ho."}</p>
          <div class="btn-row">
            <input id="cblSymbol" placeholder="${getLang() === "en" ? "e.g. DOGEUSDT" : "misaal: DOGEUSDT"}" style="max-width:160px;text-transform:uppercase;">
            <input id="cblReason" placeholder="${getLang() === "en" ? "Reason (optional)" : "Wajah (optional)"}" style="max-width:220px;">
            <button class="btn" id="btnAddCoinBlacklist">${getLang() === "en" ? "Add" : "Jodein"}</button>
          </div>
          <div class="table-wrap" style="margin-top:8px;"><table>
            <thead><tr><th>${getLang() === "en" ? "Symbol" : "Symbol"}</th><th>${getLang() === "en" ? "Reason" : "Wajah"}</th><th>${getLang() === "en" ? "Added" : "Joda Gaya"}</th><th></th></tr></thead>
            <tbody>${(coinBlacklistRes.blacklist || []).map(b => `
              <tr>
                <td>${esc(b.symbol)}</td>
                <td style="font-size:12px;">${esc(b.reason || "-")}</td>
                <td style="font-size:12px;">${esc((b.added_at || "").slice(0, 16).replace("T", " "))}</td>
                <td><button class="btn-ghost cbl-remove" data-symbol="${esc(b.symbol)}">${getLang() === "en" ? "Remove" : "Hataayein"}</button></td>
              </tr>`).join("") || `<tr><td colspan="4">${getLang() === "en" ? "No coins blacklisted." : "Koi coin blacklist nahi."}</td></tr>`}</tbody>
          </table></div>
        </div>

        </div>

        <div class="pt-tab-panel" data-pt-tab="challenge">
        <div class="section-title">${getLang() === "en" ? "Best Portfolio Suggestion" : "Best Portfolio Suggestion"} ${helpIcon("best_portfolio_suggestion")}</div>
        <div id="bestPortfolioBox" class="card"><p class="muted">Loading...</p></div>

        <div class="section-title">Challenge Mode</div>
        <p class="muted plain-note">Set a starting amount, a target, and a number of days. Instead of one blended guess across everything, the system checks each strategy on each coin separately against its own real trade history and tells you honestly which single combination &mdash; if any &mdash; has actually been performing fast enough to get there.</p>
        <div id="challengeBox"><p class="muted">Loading...</p></div>
        </div>

        <div class="pt-tab-panel" data-pt-tab="portfolio">
        <div class="section-title">Portfolio (All Strategies Combined)</div>
        <div class="grid">
          ${portfolioRes ? `
          ${card("Open Positions", fmtNum(portfolioRes.open_position_count))}
          ${card("Total Exposure", `$${portfolioRes.total_exposure.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}`)}
          ${card("Total Open Risk", `$${portfolioRes.total_open_risk.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}`)}
          ${cardClass("Combined Realized PnL", `${portfolioRes.combined_realized_pnl >= 0 ? "+" : ""}$${portfolioRes.combined_realized_pnl.toFixed(2)}`, portfolioRes.combined_realized_pnl > 0 ? "positive" : portfolioRes.combined_realized_pnl < 0 ? "negative" : "")}
          ${card("Correlation Concentration", `${portfolioRes.correlation_concentration_pct}%`)}
          ` : `<div class="muted">Portfolio data not available yet.</div>`}
          ${riskScoreRes && riskScoreRes.risk_score != null ? cardClass(`Portfolio Risk Score ${helpIcon("sharpe_ratio")}`, `${riskScoreRes.risk_score}/100`, riskScoreRes.risk_score >= 70 ? "positive" : riskScoreRes.risk_score >= 40 ? "" : "negative") : card("Portfolio Risk Score", "Not enough data")}
        </div>
        ${riskScoreRes && riskScoreRes.risk_score != null ? `<div class="muted" style="font-size:12px;">Based on ${riskScoreRes.strategies_with_data} strategies with enough trade history -- average Sharpe ${helpIcon("sharpe_ratio")} ${riskScoreRes.avg_sharpe}, worst single-strategy drawdown ${helpIcon("max_drawdown")} ${riskScoreRes.worst_drawdown_pct}%.</div>` : ""}

        ${(corrWarningsRes.warnings || []).length ? `
        <div class="section-title">Correlation Warnings ${helpIcon("correlation_warning")}</div>
        <div class="card">
          ${corrWarningsRes.warnings.map(w => `
            <div style="padding:4px 0;border-bottom:1px solid var(--border,#333);font-size:13px;">
              <span class="pill pill-pending">Info</span> ${esc(w.message)}
            </div>`).join("")}
        </div>` : ""}

        ${(dupExposureRes.warnings || []).length ? `
        <div class="section-title">${getLang() === "en" ? "Duplicate Exposure Warnings" : "Duplicate Exposure Warnings"} ${helpIcon("duplicate_exposure_warning")}</div>
        <div class="card">
          ${dupExposureRes.warnings.map(w => `
            <div style="padding:4px 0;border-bottom:1px solid var(--border,#333);font-size:13px;">
              <span class="pill pill-pending">${getLang() === "en" ? "Info" : "Info"}</span> ${esc(w.message)}
            </div>`).join("")}
        </div>` : ""}

        ${(exposureRes.exposure || []).length ? `
        <div class="section-title">Exposure Per Coin (All Strategies)</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Coin</th><th>Open Positions</th><th>Strategies Involved</th><th>Total Notional</th><th>Total Risk</th></tr></thead>
          <tbody>${exposureRes.exposure.slice(0, 15).map(e => `
            <tr>
              <td>${esc(e.symbol)}</td>
              <td>${e.position_count}</td>
              <td>${e.strategy_count}${e.strategy_count >= 3 ? ` <span class="pill pill-pending">Concentrated</span>` : ""}</td>
              <td>$${e.total_notional.toFixed(2)}</td>
              <td>$${e.total_risk.toFixed(2)}</td>
            </tr>`).join("")}</tbody>
        </table></div>` : ""}

        ${(strategyExposureRes.exposure || []).length ? `
        <div class="section-title">Exposure Per Strategy ${helpIcon("portfolio_heat_map")}</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Strategy</th><th>Open Positions</th><th>Coins</th><th>Total Notional</th><th>Total Risk</th></tr></thead>
          <tbody>${strategyExposureRes.exposure.slice(0, 15).map(e => `
            <tr>
              <td>${esc(strategyNameById[e.strategy_id] || e.strategy_id)}</td>
              <td>${e.position_count}</td>
              <td>${e.coin_count}</td>
              <td>$${e.total_notional.toFixed(2)}</td>
              <td>$${e.total_risk.toFixed(2)}</td>
            </tr>`).join("")}</tbody>
        </table></div>` : ""}

        ${directionExposureRes.long ? `
        <div class="section-title">Exposure By Direction ${helpIcon("portfolio_heat_map")}</div>
        <div class="grid">
          ${card("Long", `${directionExposureRes.long.position_count} positions -- $${directionExposureRes.long.total_notional.toFixed(2)} (${directionExposureRes.long.pct_of_total_notional}%)`)}
          ${card("Short", `${directionExposureRes.short.position_count} positions -- $${directionExposureRes.short.total_notional.toFixed(2)} (${directionExposureRes.short.pct_of_total_notional}%)`)}
        </div>` : ""}

        ${(strategyCorrMatrixRes.strategies || []).length >= 2 ? `
        <div class="section-title">Strategy Correlation Matrix ${helpIcon("strategy_correlation")}</div>
        <div class="table-wrap"><table>
          <thead><tr><th></th>${strategyCorrMatrixRes.strategies.map(sid => `<th style="font-size:11px;">${esc((strategyNameById[sid] || sid).slice(0, 14))}</th>`).join("")}</tr></thead>
          <tbody>${strategyCorrMatrixRes.strategies.map((sid, i) => `
            <tr>
              <td style="font-size:11px;font-weight:600;">${esc((strategyNameById[sid] || sid).slice(0, 14))}</td>
              ${strategyCorrMatrixRes.matrix[i].map(c => {
                if (c == null) return `<td class="muted" style="text-align:center;">-</td>`;
                const bg = c >= 0.7 ? "rgba(220,50,50,0.35)" : c >= 0.4 ? "rgba(220,150,50,0.25)" : c <= -0.4 ? "rgba(50,150,220,0.25)" : "transparent";
                return `<td style="text-align:center;background:${bg};">${c.toFixed(2)}</td>`;
              }).join("")}
            </tr>`).join("")}</tbody>
        </table></div>
        <p class="muted" style="font-size:12px;">Based on each strategy's daily realized PnL over the last 30 days (needs at least ${strategyCorrMatrixRes.min_aligned_days || 10} overlapping days -- shown as "-" otherwise). Red = strategies that tend to win/lose on the same days (less real diversification than it looks); blue = strategies that tend to move opposite each other.</p>
        ` : ""}

        ${(coinHeatmapRes.coins || []).length ? `
        <div class="section-title">Coin-Performance Heatmap ${helpIcon("coin_heatmap")}</div>
        <p class="muted" style="font-size:12px;">Click a coin to see every strategy's own performance on it, side by side.</p>
        <div class="table-wrap"><table>
          <thead><tr><th>Coin</th><th>Strategies Traded It</th><th>Consistency</th><th>Avg Win Rate</th><th>Total PnL</th></tr></thead>
          <tbody>${coinHeatmapRes.coins.slice(0, 20).map(c => {
            const bg = c.consistency_pct >= 70 ? "rgba(50,180,80,0.2)" : c.consistency_pct >= 40 ? "rgba(220,150,50,0.2)" : "rgba(220,50,50,0.2)";
            return `<tr style="background:${bg};cursor:pointer;" class="pt-coin-deep-dive-row" data-symbol="${esc(c.symbol)}">
              <td>${esc(c.symbol)}</td>
              <td>${c.profitable_strategy_count}/${c.strategy_count} profitable</td>
              <td>${c.consistency_pct.toFixed(0)}%</td>
              <td>${c.avg_win_rate.toFixed(1)}%</td>
              <td class="${c.total_pnl >= 0 ? "pill-up" : "pill-down"}">${c.total_pnl.toFixed(2)}</td>
            </tr>`;
          }).join("")}</tbody>
        </table></div>
        <div id="ptCoinDeepDive" class="card" style="display:none;"></div>` : ""}
        </div>

        <div class="pt-tab-panel" data-pt-tab="analytics">
        <div class="section-title">Analytics</div>
        <div id="ptAnalyticsBox"></div>
        </div>

        <div class="pt-tab-panel" data-pt-tab="overview">
        <div class="section-title">${t("Daily Goal")} (${goalPct}%)</div>
        <div class="card">
          <div class="progress-bar"><div class="progress-bar-fill" style="width:${goalProgress}%;"></div></div>
          <div class="muted" style="margin-top:6px;font-size:12px;">Today's realized PnL: ${todaysPnlPct.toFixed(2)}% of ${goalPct}% goal (${todaysTrades.length} trades closed today)</div>
        </div>

        <div class="section-title">${t("Control Center")}</div>
        ${acctDrawdown.paused ? `
        <div class="card" style="border:2px solid var(--orange,#d68910);background:rgba(214,137,16,0.08);margin-bottom:10px;">
          <div style="font-weight:700;color:var(--orange,#d68910);">⛔ Account-Wide Drawdown Circuit-Breaker ACTIVE -- new trades paused for every strategy</div>
          <div class="muted" style="font-size:12px;margin-top:4px;">${esc(acctDrawdown.paused_reason || "-")}</div>
          <div class="muted" style="font-size:12px;">Existing open positions are unaffected -- only new entries are blocked.</div>
          <div class="btn-row" style="margin-top:8px;">
            <button class="btn" id="ptAcctDrawdownResume">Resume Account-Wide Trading</button>
          </div>
        </div>` : `
        <div class="muted" style="font-size:12px;margin-bottom:10px;">Account drawdown from peak: ${acctDrawdown.drawdown_pct != null ? acctDrawdown.drawdown_pct.toFixed(1) : "0.0"}% (circuit-breaker trips at ${settings.account_drawdown_pause_pct_threshold ?? 20}%)</div>`}
        ${killSwitch.active ? `
        <div class="card" style="border:2px solid var(--red,#c0392b);background:rgba(192,57,43,0.08);margin-bottom:10px;">
          <div style="font-weight:700;color:var(--red,#c0392b);">🛑 KILL SWITCH ACTIVE -- all trading is halted</div>
          <div class="muted" style="font-size:12px;margin-top:4px;">Reason: ${esc(killSwitch.reason || "-")} &middot; Activated by ${esc(killSwitch.activated_by || "-")} at ${esc((killSwitch.activated_at || "").slice(0,19))}</div>
          <div class="muted" style="font-size:12px;">Engine cannot be started again until this is deactivated below.</div>
          <div class="btn-row" style="margin-top:8px;">
            <button class="btn" id="ptKillSwitchDeactivate">Deactivate Kill Switch</button>
          </div>
        </div>` : ""}
        <div class="btn-row">
          <button class="btn" id="ptStart" ${status.running || killSwitch.active ? "disabled" : ""}>${t("Start Engine")}</button>
          <button class="btn-ghost" id="ptStop" ${status.running ? "" : "disabled"}>${t("Stop Engine")}</button>
          <button class="btn-ghost" id="ptRunTick">${t("Run One Tick Now")}</button>
          <label style="display:flex;align-items:center;gap:6px;width:auto;">
            <input type="checkbox" id="ptDryRun" ${settings.dry_run ? "checked" : ""} style="width:auto;"> Dry Run Mode
          </label>
          <button class="btn-ghost" id="ptResetBalance" style="border-color:var(--red,#c0392b);color:var(--red,#c0392b);">${t("Reset Balance")}</button>
          ${!killSwitch.active ? `<button class="btn" id="ptKillSwitchActivate" style="background:var(--red,#c0392b);border-color:var(--red,#c0392b);color:#fff;">🛑 EMERGENCY STOP</button>` : ""}
          <span id="ptStatusMsg" class="muted"></span>
        </div>
        ${status.running ? `<div class="muted pt-engine-status-line" style="font-size:12px;">Started ${esc((status.started_at||"").slice(0,19))} -- tick #${status.tick_count}${
          /* `last at ${(last_tick_at||"-").slice(11,19)}` rendered a dangling
             "last at " with nothing after it before the first tick completes:
             slicing a 1-character "-" at [11,19] yields an empty string. A
             full 50-coin x 18-strategy pass takes many minutes, so that
             half-sentence is what the CEO sees for the whole first tick.
             Now the clause only appears once there IS a last tick. */
          status.last_tick_at ? `, last at ${esc(String(status.last_tick_at).slice(11,19))}` : ` (first tick still running)`
        }</div>` : ""}
        </div>

        <div class="pt-tab-panel" data-pt-tab="settings">
        <div class="section-title">Engine Settings</div>
        <div class="card" style="max-width:560px;">
          <div class="two-col">
            <div class="form-row"><label>Max Open Trades</label><input id="ptMaxOpen" type="number" value="${settings.max_open_trades}"></div>
            <div class="form-row"><label>Cooldown (minutes)</label><input id="ptCooldown" type="number" value="${settings.cooldown_minutes}"></div>
            <div class="form-row"><label>Risk % per Trade</label><input id="ptRiskPct" type="number" step="0.1" value="${settings.risk_pct_default}"></div>
            <div class="form-row"><label>Initial Balance</label><input id="ptBalance" type="number" value="${settings.initial_balance}"></div>
            <div class="form-row"><label>Coin Filter Top-N</label><input id="ptTopN" type="number" value="${settings.coin_filter_top_n}"></div>
            <div class="form-row"><label>Tick Interval (seconds)</label><input id="ptTickInterval" type="number" value="${settings.tick_interval_seconds}"></div>
            <div class="form-row"><label>Signal Priority Rule</label>
              <select id="ptPriorityRule">
                ${["confidence", "win_rate", "profit", "manual"].map(v => `<option ${v === settings.priority_rule ? "selected" : ""}>${v}</option>`).join("")}
              </select>
            </div>
            <div class="form-row"><label>Opposite Signal Policy</label>
              <select id="ptOppositePolicy">
                ${["block", "allow", "close_and_reverse"].map(v => `<option ${v === settings.opposite_signal_policy ? "selected" : ""}>${v}</option>`).join("")}
              </select>
            </div>
            <div class="form-row"><label>Daily Goal %</label><input id="ptDailyGoal" type="number" step="0.1" value="${settings.daily_goal_pct}"></div>
            <div class="form-row"><label>${getLang() === "en" ? "Ensemble Voting: Min. Agreeing Strategies" : "Ensemble Voting: Min. Agreeing Strategies"} ${helpIcon("ensemble_voting")}</label><input id="ptEnsembleMinAgree" type="number" min="1" step="1" value="${settings.ensemble_voting_min_agreeing_strategies}"></div>
          </div>
          <span id="ptSettingsStatus" class="muted"></span>
        </div>

        <div class="section-title">${getLang() === "en" ? "Position Size Calculator" : "Position Size Calculator"} ${helpIcon("position_size_calculator")}</div>
        <div class="card" style="max-width:560px;">
          <p class="muted" style="font-size:12px;margin-top:0;">${getLang() === "en"
            ? "A what-if tool -- given a balance, entry, stop, and risk %, see exactly what size would be opened. Purely a calculation; never opens a real trade."
            : "Ek what-if tool -- balance, entry, stop, aur risk % dekar, exact size dekhein jo khulti. Sirf calculation hai; koi asal trade nahi khulti."}</p>
          <div class="two-col">
            <div class="form-row"><label>${getLang() === "en" ? "Balance" : "Balance"}</label><input id="pscBalance" type="number" value="10000"></div>
            <div class="form-row"><label>${getLang() === "en" ? "Risk %" : "Risk %"}</label><input id="pscRiskPct" type="number" step="0.1" value="1"></div>
            <div class="form-row"><label>${getLang() === "en" ? "Entry Price" : "Entry Price"}</label><input id="pscEntry" type="number" step="any"></div>
            <div class="form-row"><label>${getLang() === "en" ? "Stop-Loss" : "Stop-Loss"}</label><input id="pscStop" type="number" step="any"></div>
            <div class="form-row"><label>${getLang() === "en" ? "Take-Profit (optional)" : "Take-Profit (optional)"}</label><input id="pscTarget" type="number" step="any"></div>
            <div class="form-row"><label>${getLang() === "en" ? "Leverage" : "Leverage"}</label><input id="pscLeverage" type="number" step="0.1" value="1"></div>
          </div>
          <div class="btn-row" style="margin-top:8px;">
            <button class="btn-ghost" id="btnCalcPositionSize">${getLang() === "en" ? "Calculate" : "Calculate Karein"}</button>
          </div>
          <div id="pscResult" style="margin-top:8px;font-size:13px;"></div>
        </div>

        <div class="section-title">${getLang() === "en" ? "Time-of-Day Trading Filter" : "Time-of-Day Trading Filter"} ${helpIcon("time_of_day_filter")}</div>
        <div class="card" style="max-width:560px;">
          <p class="muted" style="font-size:12px;margin-top:0;">${getLang() === "en"
            ? "Blocks NEW entries during a UTC hour window -- existing open positions are never affected. Off by default."
            : "UTC ke ek time window mein NAYE trades block karta hai -- pehle se khuli positions par asar nahi hota. Default mein OFF hai."}</p>
          <label style="display:flex;align-items:center;gap:6px;width:auto;margin-bottom:8px;">
            <input type="checkbox" id="ptTimeFilterEnabled" style="width:auto;" ${settings.time_filter_enabled ? "checked" : ""}> ${getLang() === "en" ? "Enable" : "Chalu Karein"}
          </label>
          <div class="two-col">
            <div class="form-row"><label>${getLang() === "en" ? "Block From (UTC)" : "Kab Se Block (UTC)"}</label><input id="ptTimeFilterStart" type="time" value="${esc(settings.time_filter_block_start_utc || "00:00")}"></div>
            <div class="form-row"><label>${getLang() === "en" ? "Block Until (UTC)" : "Kab Tak Block (UTC)"}</label><input id="ptTimeFilterEnd" type="time" value="${esc(settings.time_filter_block_end_utc || "00:00")}"></div>
          </div>
          <div class="btn-row" style="margin-top:8px;">
            <button class="btn-ghost" id="btnSaveTimeFilter">${getLang() === "en" ? "Save" : "Save Karein"}</button>
          </div>
          <span id="ptTimeFilterStatus" class="muted"></span>
        </div>

        <div class="section-title">${getLang() === "en" ? "Profit-Lock Trailing Stop" : "Profit-Lock Trailing Stop"} ${helpIcon("profit_lock")}</div>
        <div class="card" style="max-width:560px;">
          <p class="muted" style="font-size:12px;margin-top:0;">${getLang() === "en"
            ? "Once a trade moves far enough in its favor, its stop-loss trails up to lock in part of that gain -- it only ever tightens, never loosens. Off by default."
            : "Jab trade kaafi favor mein chali jaaye, uska stop-loss upar trail hota hai takay munafa lock ho -- yeh sirf tight hota hai, kabhi loose nahi. Default mein OFF hai."}</p>
          <label style="display:flex;align-items:center;gap:6px;width:auto;margin-bottom:8px;">
            <input type="checkbox" id="ptProfitLockEnabled" style="width:auto;" ${settings.profit_lock_enabled ? "checked" : ""}> ${getLang() === "en" ? "Enable" : "Chalu Karein"}
          </label>
          <div class="two-col">
            <div class="form-row"><label>${getLang() === "en" ? "Trigger (R-multiple)" : "Trigger (R-multiple)"}</label><input id="ptProfitLockTriggerR" type="number" step="0.1" value="${settings.profit_lock_trigger_r}"></div>
            <div class="form-row"><label>${getLang() === "en" ? "Lock In (% of gain)" : "Lock In (% of gain)"}</label><input id="ptProfitLockTrailPct" type="number" step="1" value="${settings.profit_lock_trail_pct}"></div>
          </div>
          <div class="btn-row" style="margin-top:8px;">
            <button class="btn-ghost" id="btnSaveProfitLock">${getLang() === "en" ? "Save" : "Save Karein"}</button>
          </div>
          <span id="ptProfitLockStatus" class="muted"></span>
        </div>

        ${(riskPctRecsRes.recommendations || []).length ? `
        <div class="section-title">${getLang() === "en" ? "Risk % Recommendations" : "Risk % Recommendations"} ${helpIcon("risk_pct_recommendation")}</div>
        <div class="card">
          <p class="muted" style="font-size:12px;margin-top:0;">${getLang() === "en"
            ? "Suggestions only -- nothing here changes automatically. Applying one just fills in that strategy's existing risk-per-trade override."
            : "Sirf suggestions hain -- yahan kuch bhi apne aap nahi badalta. Apply karne se sirf us strategy ka pehle se maujood risk-per-trade override set hota hai."}</p>
          ${riskPctRecsRes.recommendations.map(r => `
            <div style="padding:6px 0;border-top:1px solid var(--border,#333);font-size:13px;display:flex;justify-content:space-between;align-items:center;gap:8px;">
              <span><b>${esc(r.strategy_name)}</b> -- ${esc(r.reason)}</span>
              <button class="btn-ghost risk-pct-apply" data-id="${r.strategy_id}" data-value="${r.recommended_risk_pct}">${getLang() === "en" ? "Apply" : "Apply Karein"}</button>
            </div>`).join("")}
        </div>` : ""}

        <div class="grid">
          ${card("Strategies Available", fmtNum((strategiesRes.strategies || []).length))}
          ${card("Lessons Available (active)", fmtNum(runningLessons.length))}
        </div>

        <div class="section-title">Per-Strategy Controls</div>
        <p class="muted plain-note">Every strategy runs its own separate account, so every one of these settings applies to that strategy alone and changes nothing about any other. "Controls" opens the on/off switch, pause and resume, its own risk % and open-position limits, and a stats reset that archives the old numbers rather than deleting them.</p>
        <div class="table-wrap"><table>
          <thead><tr>
            <th>Strategy</th><th>Backtest PF ${helpIcon("profit_factor")}</th><th>Running</th>
            <th>Risk % Used</th><th>Max Open</th><th>Open Now</th><th></th>
          </tr></thead>
          <tbody>${allStrategyRows.map(p => {
            const cfg = paperConfigs[p.strategy_id] || {};
            const pf = backtestPfById[p.strategy_id];
            const pausedEntry = pausedIds[p.strategy_id];
            return `
            <tr>
              <td style="max-width:230px;">${esc(p.strategy_name || p.strategy_id)}</td>
              <td><span class="${pf != null ? (pf > 1.0 ? "positive" : "negative") : ""}">${pf != null ? pf.toFixed(3) : "-"}</span></td>
              <td>${cfg.enabled === false
                ? '<span class="pill pill-muted">Off</span>'
                : pausedEntry
                  ? `<span class="pill pill-pending" title="${esc(pausedEntry.reason || "")}">Paused</span>`
                  : '<span class="pill pill-bullish">Running</span>'}</td>
              <td>${cfg.risk_pct_override != null
                ? `${cfg.risk_pct_override}% <span class="muted">(its own)</span>`
                : `${settings.risk_pct_default}% <span class="muted">(shared default)</span>`}</td>
              <td>${cfg.max_open_trades_override != null
                ? `${cfg.max_open_trades_override} <span class="muted">(its own)</span>`
                : `${settings.max_open_trades} <span class="muted">(shared default)</span>`}</td>
              <td>${fmtNum(p.open_positions)}</td>
              <td>
                <div class="pt-action-group">
                  <button class="btn-ghost pt-strategy-periods" data-id="${esc(p.strategy_id)}" data-name="${esc(p.strategy_name || p.strategy_id)}">By Period</button>
                  <button class="btn-ghost pt-controls" data-id="${esc(p.strategy_id)}" data-name="${esc(p.strategy_name || p.strategy_id)}">Controls</button>
                </div>
              </td>
            </tr>`;
          }).join("") || '<tr><td colspan="7">No strategies are active in paper trading yet.</td></tr>'}</tbody>
        </table></div>

        <div class="section-title">Telegram</div>
        <div class="card settings-card">
          <p class="muted plain-note">Turning signals on or off, the proxy settings for when the network block is lifted, and the freshness rule all live on the Telegram page, next to the log of what actually got delivered.</p>
          <a class="btn-ghost" href="#telegram_dashboard">Open Telegram settings</a>
        </div>
        </div>

        <div class="pt-tab-panel" data-pt-tab="overview">
        ${confidenceFilterHtml()}

        <div class="section-title">Open Positions</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Coin</th><th>Direction</th><th>Entry</th><th>SL</th><th>TP</th><th>Size</th><th>Confidence ${helpIcon("confidence_score")}</th><th>Confluence ${helpIcon("confluence_score")}</th><th>Source</th><th>Session</th><th></th></tr></thead>
          <tbody>${(positionsRes.positions || []).map(p => `
            <tr data-confidence="${p.confidence != null ? p.confidence : ""}">
              <td>${esc(p.symbol)}</td>
              <td><span class="pill ${p.direction === "long" ? "pill-bullish" : "pill-bearish"}">${esc(p.direction)}</span></td>
              <td>${p.entry_price}</td>
              <td>${p.stop_loss != null ? p.stop_loss.toFixed(6) : "-"}</td>
              <td>${p.take_profit != null ? p.take_profit.toFixed(6) : "-"}</td>
              <td>${p.size.toFixed(4)}</td>
              <td>${p.confidence != null ? p.confidence + "%" : "-"}</td>
              <td class="pt-confluence-cell" data-position-id="${p.id}">-</td>
              <td>${esc(p.strategy_name || (p.lesson_ids||[]).length + " lesson(s)")}</td>
              <td>${esc(p.session || "-")}</td>
              <td><button class="btn-ghost pt-close-position" data-id="${p.id}">Close</button></td>
            </tr>`).join("") || '<tr><td colspan="11">No open positions.</td></tr>'}</tbody>
        </table></div>
        </div>

        <div class="pt-tab-panel" data-pt-tab="history">
        <div class="section-title">Closed Trades (most recent 30 of ${allTimeSummary.closed_trades})</div>
        <div class="btn-row" style="margin-bottom:8px;">
          <button class="btn-ghost" id="btnExportTradeJournal">${getLang() === "en" ? "Export Trade Journal (PDF)" : "Trade Journal Export Karein (PDF)"}</button>
        </div>
        <div class="table-wrap"><table>
          <thead><tr><th>Strategy</th><th>Coin</th><th>Direction</th><th>Entry</th><th>Exit</th><th>PnL</th><th>PnL%</th><th>Result</th><th>Why</th><th></th></tr></thead>
          <tbody>${trades.slice(0, 30).map((t, idx) => `
            <tr>
              <td>${esc(t.strategy_name || "(lesson-only)")}</td>
              <td>${esc(t.symbol)}</td>
              <td><span class="pill ${t.direction === "long" ? "pill-bullish" : "pill-bearish"}">${esc(t.direction)}</span></td>
              <td>${t.entry_price}</td>
              <td>${t.exit_price != null ? t.exit_price : "-"}</td>
              <td class="${(t.pnl||0) >= 0 ? "pill-up" : "pill-down"}">${t.pnl != null ? t.pnl.toFixed(2) : "-"}</td>
              <td class="${(t.pnl_pct||0) >= 0 ? "pill-up" : "pill-down"}">${t.pnl_pct != null ? t.pnl_pct.toFixed(2) : "-"}%</td>
              <td style="font-size:12px;">${esc(t.win_loss_tag || t.exit_reason || "-")}</td>
              <td style="font-size:12px;max-width:220px;">${esc(t.reason_plain || "-")}</td>
              <td>
                <button class="btn-ghost pt-view-trade" data-idx="${idx}">Replay</button>
                <button class="btn-ghost pt-trade-note" data-id="${t.id}" data-note="${esc(t.user_note || "")}" title="${esc(t.user_note || "Add a personal note")}">${t.user_note ? "📝" : "🗒"}</button>
              </td>
            </tr>`).join("") || '<tr><td colspan="10">No closed trades yet.</td></tr>'}</tbody>
        </table></div>
        <div id="ptTradeDetail" class="card" style="display:none;white-space:pre-wrap;font-family:Consolas,monospace;font-size:12px;"></div>

        <div class="section-title">No-Trade Journal &amp; Decision Log</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Time</th><th>Coin</th><th>Decision</th><th>Reason</th><th>Confidence</th></tr></thead>
          <tbody>${(decisionsRes.decisions || []).map(d => `
            <tr>
              <td>${esc((d.created_at||"").slice(11,19))}</td>
              <td>${esc(d.symbol)}</td>
              <td><span class="pill ${d.decision === "opened" ? "pill-completed" : d.decision === "dry_run" ? "pill-pending" : "pill-error"}">${esc(d.decision)}</span></td>
              <td>${esc(d.reason || "-")}</td>
              <td>${d.confidence != null ? d.confidence + "%" : "-"}</td>
            </tr>`).join("") || '<tr><td colspan="5">No decisions logged yet.</td></tr>'}</tbody>
        </table></div>
        </div>

        <div class="pt-tab-panel" data-pt-tab="analytics">
        <div class="section-title">Strategy Comparison -- Profitable vs. Under Evaluation</div>
        <p class="muted" style="font-size:12.5px; margin:-4px 0 12px;">
          Every strategy currently active in paper trading, split by its real backtest result (Profit Factor &gt; 1.0 = Profitable).
          Both groups below show the exact same fields -- nothing is hidden or given less detail because a strategy is still under evaluation.
        </p>
        <div class="btn-row">
          <button class="btn-ghost" id="ptBulkFlag">Flag Selected for Telegram</button>
          <button class="btn-ghost" id="ptBulkUnflag">Unflag Selected</button>
          <button class="btn-ghost" id="ptExportComparison">Export to Excel</button>
          <span id="ptBulkStatus" class="muted"></span>
        </div>
        <div class="period-tabs" style="margin:12px 0;">
          <button class="period-tab ${ptStrategySectionFilter === "profitable" ? "active" : ""}" data-pt-section-filter="profitable">Profitable Strategies (${profitableRows.length})</button>
          <button class="period-tab ${ptStrategySectionFilter === "evaluation" ? "active" : ""}" data-pt-section-filter="evaluation">Under Evaluation (${evaluationRows.length})</button>
        </div>
        <div data-pt-section="profitable" style="display:${ptStrategySectionFilter === "profitable" ? "" : "none"};">
          ${strategyComparisonTableHtml(profitableRows, backtestPfById, "positive")}
        </div>
        <div data-pt-section="evaluation" style="display:${ptStrategySectionFilter === "evaluation" ? "" : "none"};">
          ${strategyComparisonTableHtml(evaluationRows, backtestPfById, "negative")}
        </div>
        <div id="ptStrategyDetail" class="card" style="display:none;white-space:pre-wrap;font-family:Consolas,monospace;font-size:12px;"></div>

        <div class="two-col">
          <div>
            <div class="section-title">Session-Wise Performance</div>
            <div class="table-wrap"><table>
              <thead><tr><th>Session</th><th>Trades</th><th>Win Rate</th><th>PnL</th></tr></thead>
              <tbody>${(sessionsRes.sessions || []).map(s => `
                <tr><td>${esc(s.session)}</td><td>${s.closed_trades}</td>
                <td>${s.win_rate.toFixed(1)}%</td>
                <td class="${s.total_pnl >= 0 ? "pill-up" : "pill-down"}">${s.total_pnl.toFixed(2)}</td></tr>`).join("") || '<tr><td colspan="4">No data yet.</td></tr>'}</tbody>
            </table></div>
          </div>
          <div>
            <div class="section-title">By Hour of Day (UTC)</div>
            <div class="table-wrap" style="max-height:240px;overflow-y:auto;"><table>
              <thead><tr><th>Hour</th><th>Trades</th><th>Win Rate</th><th>PnL</th></tr></thead>
              <tbody>${(hourOfDayRes.hours || []).map(h => `
                <tr><td>${String(h.hour_utc).padStart(2, "0")}:00</td><td>${h.closed_trades}</td>
                <td>${h.win_rate.toFixed(1)}%</td>
                <td class="${h.total_pnl >= 0 ? "pill-up" : "pill-down"}">${h.total_pnl.toFixed(2)}</td></tr>`).join("") || '<tr><td colspan="4">No data yet.</td></tr>'}</tbody>
            </table></div>
          </div>
        </div>

        <div class="two-col">
          <div>
            <div class="section-title">Lesson Performance</div>
            <div class="table-wrap"><table>
              <thead><tr><th>Lesson</th><th>Used</th><th>Win Rate</th><th>PnL</th><th>Score</th></tr></thead>
              <tbody>${(lessonPerfRes.performance || []).map(p => `
                <tr><td>${esc(p.lesson_title || p.lesson_id)}</td><td>${p.usage_count}</td>
                <td>${p.usage_count ? ((p.wins/p.usage_count)*100).toFixed(1) : "0.0"}%</td>
                <td>${p.total_pnl.toFixed(2)}</td><td>${p.score}</td></tr>`).join("") || '<tr><td colspan="5">No data yet.</td></tr>'}</tbody>
            </table></div>
          </div>
        </div>

        <div class="section-title">Self-Learning Insights (flagged for review, nothing auto-applied)</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Pattern</th><th>Trades</th><th>Win Rate</th></tr></thead>
          <tbody>${(candidatesRes.candidates || []).slice(0, 15).map(c => `
            <tr><td>${esc(c.pattern_description)}</td><td>${c.sample_size}</td><td>${Number(c.win_rate).toFixed(0)}%</td></tr>`).join("")
            || '<tr><td colspan="3">No repeated patterns flagged yet -- needs more closed trades.</td></tr>'}</tbody>
        </table></div>

        <div class="section-title">Pattern Reliability -- Statistical Gate ${helpIcon("pattern_reliability")}</div>
        <p class="muted" style="margin-top:-8px;">This is exactly what Pattern Auto-Avoid and Lesson Auto-Apply act on -- every strategy + coin + market condition combination needs at least ${patternReliabilityRes.min_sample_size} trades before any conclusion is trusted.</p>
        <div class="table-wrap"><table>
          <thead><tr><th>Strategy</th><th>Coin</th><th>Market</th><th>Session</th><th>Sample Size</th><th>Win Rate</th><th>95% Confidence Interval</th><th>Conclusion</th></tr></thead>
          <tbody>${(patternReliabilityRes.patterns || []).slice(0, 40).map(r => `
            <tr>
              <td>${esc(r.strategy_name || r.strategy_id)}</td>
              <td>${esc(r.symbol)}</td>
              <td>${esc(r.market_state)}</td>
              <td>${esc(r.session)}</td>
              <td>${r.sample_size} / ${patternReliabilityRes.min_sample_size}</td>
              <td>${r.win_rate_pct}%</td>
              <td>${r.ci_lower_pct != null ? `${r.ci_lower_pct}% - ${r.ci_upper_pct}%` : "-"}</td>
              <td><span class="pill ${r.status === "reliable_good" ? "pill-bullish" : r.status === "reliable_bad" ? "pill-bearish" : r.status === "reliable_inconclusive" ? "pill-neutral" : "pill-muted"}">${esc(r.conclusion)}</span></td>
            </tr>`).join("") || '<tr><td colspan="8">No pattern data yet -- needs closed trades.</td></tr>'}</tbody>
        </table></div>
        </div>
      `;

      startScanCycle((status.last_summary && status.last_summary.shortlisted) || []);

      function applyPtTab(tabId) {
        activePtTab = tabId;
        content.querySelectorAll("[data-pt-tab-btn]").forEach(btn => {
          btn.classList.toggle("active", btn.dataset.ptTabBtn === tabId);
        });
        content.querySelectorAll("[data-pt-tab]").forEach(panel => {
          panel.style.display = panel.dataset.ptTab === tabId ? "" : "none";
        });
      }
      applyPtTab(activePtTab);
      content.querySelectorAll("[data-pt-tab-btn]").forEach(btn => {
        btn.onclick = () => applyPtTab(btn.dataset.ptTabBtn);
      });

      // Master Task 2, Part 2: Profitable / Under Evaluation toggle -- both
      // sections are already in the DOM (identical row detail either way),
      // this just shows/hides which one is visible, no re-fetch needed.
      content.querySelectorAll("[data-pt-section-filter]").forEach(btn => {
        btn.onclick = () => {
          ptStrategySectionFilter = btn.dataset.ptSectionFilter;
          content.querySelectorAll("[data-pt-section-filter]").forEach(b => b.classList.toggle("active", b === btn));
          content.querySelectorAll("[data-pt-section]").forEach(section => {
            section.style.display = section.dataset.ptSection === ptStrategySectionFilter ? "" : "none";
          });
        };
      });
      content.querySelectorAll(".pt-controls").forEach(btn => {
        btn.onclick = () => openStrategyControlsModal(btn.dataset.id, btn.dataset.name, () => render());
      });
      wireStrategyPeriodDrilldowns(content);

      loadPaperAnalytics("ptAnalyticsBox", "pt", "today");
      loadChallenge();
      loadBestPortfolio();

      document.getElementById("ptStart").onclick = async () => {
        // Master Task 3, Phase 0.8h: Start/Stop are real trading state
        // changes -- a confirm prompt (already the convention for the kill
        // switch / account-drawdown-resume buttons above) prevents an
        // accidental click.
        if (!confirm("Start the Paper Trading engine? It will begin scanning for real signals and opening trades (or dry-run entries, if Dry Run Mode is on).")) return;
        try {
          await apiPost("/api/paper-trading/start");
          appendLog("Paper Trading engine started.");
          document.getElementById("ptStatusMsg").textContent = "✓ Done -- engine started.";
        } catch (e) {
          document.getElementById("ptStatusMsg").textContent = `✗ Failed: ${e.message}`;
          showToast({ title: "Start Engine failed", body: e.message, isError: true });
        }
        render();
      };
      document.getElementById("ptStop").onclick = async () => {
        if (!confirm("Stop the Paper Trading engine? It will stop scanning for new signals (existing open positions stay open and keep being monitored).")) return;
        try {
          await apiPost("/api/paper-trading/stop");
          document.getElementById("ptStatusMsg").textContent = "✓ Done -- engine stopped.";
        } catch (e) {
          document.getElementById("ptStatusMsg").textContent = `✗ Failed: ${e.message}`;
          showToast({ title: "Stop Engine failed", body: e.message, isError: true });
          render();
          return;
        }
        appendLog("Paper Trading engine stopped.");
        render();
      };
      const killActivateBtn = document.getElementById("ptKillSwitchActivate");
      if (killActivateBtn) killActivateBtn.onclick = async () => {
        if (!confirm("EMERGENCY STOP: this immediately halts the engine, stops all Telegram signals, and closes every open position at the current market price. Continue?")) return;
        const reason = prompt("Reason for kill switch (optional):", "") || "manual emergency stop";
        await apiPost("/api/paper-trading/kill-switch/activate", { reason, close_positions: true });
        appendLog("KILL SWITCH ACTIVATED.");
        render();
      };
      const killDeactivateBtn = document.getElementById("ptKillSwitchDeactivate");
      if (killDeactivateBtn) killDeactivateBtn.onclick = async () => {
        if (!confirm("Deactivate the kill switch? Trading will stay OFF until you press Start Engine again.")) return;
        await apiPost("/api/paper-trading/kill-switch/deactivate", {});
        appendLog("Kill switch deactivated.");
        render();
      };
      const acctDrawdownResumeBtn = document.getElementById("ptAcctDrawdownResume");
      if (acctDrawdownResumeBtn) acctDrawdownResumeBtn.onclick = async () => {
        if (!confirm("Resume account-wide trading? Every strategy will be allowed to open new trades again.")) return;
        await apiPost("/api/paper-trading/account-drawdown-resume", {});
        appendLog("Account-wide drawdown circuit-breaker resumed.");
        render();
      };
      const btnAddCustomRule = document.getElementById("btnAddCustomRule");
      if (btnAddCustomRule) btnAddCustomRule.onclick = async () => {
        const status = document.getElementById("carStatus");
        const threshold = parseFloat(document.getElementById("carThreshold").value);
        if (isNaN(threshold)) { status.textContent = "Enter a threshold number."; return; }
        const metric = document.getElementById("carMetric").value;
        const strategyId = document.getElementById("carStrategy").value || null;
        if (metric !== "account_drawdown_pct" && !strategyId) { status.textContent = "Pick a strategy for this metric."; return; }
        try {
          await apiPost("/api/paper-trading/custom-alert-rules", {
            name: `${metric} ${document.getElementById("carComparison").value} ${threshold}`,
            metric, comparison: document.getElementById("carComparison").value, threshold, strategy_id: strategyId,
          });
          status.textContent = "Added.";
          render();
        } catch (e) { status.textContent = `Failed: ${e.message}`; }
      };
      document.querySelectorAll(".car-toggle").forEach(cb => cb.onchange = async () => {
        await apiPost(`/api/paper-trading/custom-alert-rules/${cb.dataset.id}/enabled?enabled=${cb.checked}`, {});
      });
      document.querySelectorAll(".car-delete").forEach(btn => btn.onclick = async () => {
        await apiSend("DELETE", `/api/paper-trading/custom-alert-rules/${btn.dataset.id}`);
        render();
      });
      const btnAddCoinBlacklist = document.getElementById("btnAddCoinBlacklist");
      if (btnAddCoinBlacklist) btnAddCoinBlacklist.onclick = async () => {
        const symbol = document.getElementById("cblSymbol").value.trim().toUpperCase();
        if (!symbol) return;
        const reason = document.getElementById("cblReason").value.trim() || null;
        await apiPost("/api/paper-trading/coin-blacklist", { symbol, reason });
        render();
      };
      document.querySelectorAll(".cbl-remove").forEach(btn => btn.onclick = async () => {
        await apiSend("DELETE", `/api/paper-trading/coin-blacklist/${btn.dataset.symbol}`);
        render();
      });
      document.querySelectorAll(".risk-pct-apply").forEach(btn => btn.onclick = async () => {
        // Reuses the EXACT SAME, already-validated per-strategy override
        // endpoint the manual risk-pct-override UI already calls -- this
        // suggestion never has its own separate apply path.
        await apiPost(`/api/paper-trading/strategy-config/${btn.dataset.id}/overrides`, {
          risk_pct_override: parseFloat(btn.dataset.value),
        });
        appendLog(`Applied recommended risk %: ${btn.dataset.value}% for this strategy.`);
        render();
      });
      document.getElementById("ptRunTick").onclick = async () => {
        document.getElementById("ptStatusMsg").textContent = "Running tick...";
        const res = await apiPost("/api/paper-trading/run-tick-now");
        document.getElementById("ptStatusMsg").textContent =
          `Tick done: ${res.summary.opened} opened, ${res.summary.closed} closed, ${res.summary.rejected} rejected.`;
        render();
      };
      document.getElementById("ptDryRun").addEventListener("change", async (e) => {
        await autosave("POST", "/api/paper-trading/settings", { dry_run: e.target.checked });
        appendLog(`Dry Run mode ${e.target.checked ? "enabled" : "disabled"}.`);
      });
      document.getElementById("ptResetBalance").onclick = async () => {
        const p = await apiGet("/api/paper-trading/reset-balance/preview");
        const msg = getLang() === "en"
          ? `Resetting the balance will do this:\n\n` +
            `- Combined balance will go from $${p.current_combined_balance.toFixed(2)} back to $${p.reset_combined_balance.toFixed(2)} ` +
            `(${p.strategies_affected} strategy book(s), each back to its $${p.initial_balance.toFixed(2)} starting balance).\n` +
            `- ${p.closed_trades_preserved} closed trades, lessons, evolution data, and all statistics stay COMPLETELY SAFE -- nothing gets deleted.\n` +
            (p.open_positions_left_running > 0
              ? `- ${p.open_positions_left_running} trade(s) are currently open -- they will KEEP RUNNING, not be closed. When they do close, their result will add onto the new balance.\n`
              : `- There are no open trades right now.\n`) +
            `\nConfirm?`
          : `Balance Reset karne se yeh hoga:\n\n` +
            `- Combined balance $${p.current_combined_balance.toFixed(2)} se wapas $${p.reset_combined_balance.toFixed(2)} ho jayega ` +
            `(${p.strategies_affected} strategy book(s), har ek apne $${p.initial_balance.toFixed(2)} starting balance par wapas).\n` +
            `- ${p.closed_trades_preserved} band ho chuki trades, lessons, evolution data, aur saari statistics BILKUL SAFE rahengi -- kuch bhi delete nahi hoga.\n` +
            (p.open_positions_left_running > 0
              ? `- Abhi ${p.open_positions_left_running} trade(s) chal rahi hain -- yeh CHALTI RAHENGI, band nahi hongi. Jab woh close hongi, unka result naye balance mein add ho jayega.\n`
              : `- Abhi koi open trade nahi hai.\n`) +
            `\nConfirm karein?`;
        if (!confirm(msg)) return;
        document.getElementById("ptStatusMsg").textContent = "Resetting balance...";
        const res = await apiPost("/api/paper-trading/reset-balance", { confirm: true });
        appendLog(`Balance reset: ${res.strategies_reset} strategy book(s), combined balance back to starting amount.`);
        document.getElementById("ptStatusMsg").textContent = "Balance reset done.";
        render();
      };

      const saveEngineSettings = debounce(async () => {
        const status = document.getElementById("ptSettingsStatus");
        status.textContent = "Saving...";
        try {
          await autosave("POST", "/api/paper-trading/settings", {
            max_open_trades: parseInt(document.getElementById("ptMaxOpen").value, 10),
            cooldown_minutes: parseInt(document.getElementById("ptCooldown").value, 10),
            risk_pct_default: parseFloat(document.getElementById("ptRiskPct").value),
            initial_balance: parseFloat(document.getElementById("ptBalance").value),
            coin_filter_top_n: parseInt(document.getElementById("ptTopN").value, 10),
            tick_interval_seconds: parseInt(document.getElementById("ptTickInterval").value, 10),
            priority_rule: document.getElementById("ptPriorityRule").value,
            opposite_signal_policy: document.getElementById("ptOppositePolicy").value,
            daily_goal_pct: parseFloat(document.getElementById("ptDailyGoal").value),
            ensemble_voting_min_agreeing_strategies: parseInt(document.getElementById("ptEnsembleMinAgree").value, 10),
          });
          status.textContent = "Saved";
        } catch (e) {
          status.textContent = "Save failed (will retry)";
        }
      }, 600);
      ["ptMaxOpen", "ptCooldown", "ptRiskPct", "ptBalance", "ptTopN", "ptTickInterval", "ptDailyGoal", "ptEnsembleMinAgree"].forEach(id => {
        document.getElementById(id).addEventListener("input", saveEngineSettings);
      });
      ["ptPriorityRule", "ptOppositePolicy"].forEach(id => {
        document.getElementById(id).addEventListener("change", saveEngineSettings);
      });

      document.getElementById("btnCalcPositionSize").onclick = async () => {
        const resultEl = document.getElementById("pscResult");
        const entry = parseFloat(document.getElementById("pscEntry").value);
        if (!entry || entry <= 0) {
          resultEl.innerHTML = `<p class="muted">${getLang() === "en" ? "Enter an entry price." : "Entry price dalein."}</p>`;
          return;
        }
        const stopVal = document.getElementById("pscStop").value;
        const targetVal = document.getElementById("pscTarget").value;
        try {
          const r = await apiPost("/api/paper-trading/position-size-calculator", {
            balance: parseFloat(document.getElementById("pscBalance").value) || 0,
            entry_price: entry,
            stop_loss: stopVal ? parseFloat(stopVal) : null,
            risk_pct: parseFloat(document.getElementById("pscRiskPct").value) || 1.0,
            take_profit: targetVal ? parseFloat(targetVal) : null,
            leverage: parseFloat(document.getElementById("pscLeverage").value) || 1.0,
          });
          resultEl.innerHTML = `
            <div class="two-col">
              ${card(getLang() === "en" ? "Size" : "Size", r.size)}
              ${card(getLang() === "en" ? "Notional" : "Notional", `$${r.notional.toLocaleString()}`)}
              ${card(getLang() === "en" ? "Risk Amount" : "Risk Amount", r.risk_amount != null ? `$${r.risk_amount.toLocaleString()}` : "-")}
              ${card(getLang() === "en" ? "Reward Amount" : "Reward Amount", r.reward_amount != null ? `$${r.reward_amount.toLocaleString()}` : "-")}
              ${card(getLang() === "en" ? "Risk:Reward" : "Risk:Reward", r.risk_reward_ratio != null ? `1:${r.risk_reward_ratio}` : "-")}
            </div>`;
        } catch (e) {
          resultEl.innerHTML = `<p class="muted">${getLang() === "en" ? "Could not calculate" : "Calculate nahi ho saka"}: ${esc(e.message)}</p>`;
        }
      };
      document.getElementById("btnSaveTimeFilter").onclick = async () => {
        const status = document.getElementById("ptTimeFilterStatus");
        status.textContent = getLang() === "en" ? "Saving..." : "Save ho raha hai...";
        try {
          await apiPost("/api/paper-trading/settings", {
            time_filter_enabled: document.getElementById("ptTimeFilterEnabled").checked,
            time_filter_block_start_utc: document.getElementById("ptTimeFilterStart").value || "00:00",
            time_filter_block_end_utc: document.getElementById("ptTimeFilterEnd").value || "00:00",
          });
          status.textContent = getLang() === "en" ? "Saved." : "Save ho gaya.";
        } catch (e) {
          status.textContent = getLang() === "en" ? "Save failed." : "Save nahi ho saka.";
        }
      };

      document.getElementById("btnSaveProfitLock").onclick = async () => {
        const status = document.getElementById("ptProfitLockStatus");
        status.textContent = getLang() === "en" ? "Saving..." : "Save ho raha hai...";
        try {
          await apiPost("/api/paper-trading/settings", {
            profit_lock_enabled: document.getElementById("ptProfitLockEnabled").checked,
            profit_lock_trigger_r: parseFloat(document.getElementById("ptProfitLockTriggerR").value),
            profit_lock_trail_pct: parseFloat(document.getElementById("ptProfitLockTrailPct").value),
          });
          status.textContent = getLang() === "en" ? "Saved." : "Save ho gaya.";
        } catch (e) {
          status.textContent = getLang() === "en" ? "Save failed." : "Save nahi ho saka.";
        }
      };

      document.querySelectorAll(".pt-close-position").forEach(btn => {
        btn.onclick = async () => {
          await apiPost(`/api/paper-trading/positions/${btn.dataset.id}/close`);
          appendLog("Position closed manually.");
          render();
        };
      });

      document.querySelectorAll(".pt-override").forEach(btn => {
        btn.onclick = async () => {
          const nowActive = btn.dataset.active !== "1";
          const res = await apiPost(`/api/paper-trading/override/${btn.dataset.id}`, { manual_alert: nowActive });
          if (nowActive && res.telegram_send_result) {
            appendLog(res.telegram_send_result.ok
              ? `Telegram signal SENT for strategy ${btn.dataset.id}.`
              : `Telegram send FAILED for ${btn.dataset.id}: ${res.telegram_send_result.error}`);
          } else {
            appendLog(nowActive
              ? `Strategy ${btn.dataset.id} flagged for Telegram alert (manual override).`
              : `Manual Telegram flag removed for ${btn.dataset.id}.`);
          }
          render();
        };
      });

      // Manual Override -- Bulk Action (Remaining Dashboard Enhancements,
      // item 3): flag/unflag several strategies for Telegram in one click
      // instead of one at a time -- reuses the exact same single-strategy
      // /api/paper-trading/override/{id} endpoint per selected row, just
      // looped, so no backend change is needed and every safety check that
      // endpoint already does (real telegram_send_result, honest failure
      // reporting) still applies to each one individually.
      // Two sections (Profitable / Under Evaluation) each have their own
      // "select all" checkbox now -- each only selects rows within its own
      // section, matching what's actually visible to the person clicking it.
      content.querySelectorAll(".pt-select-all-section").forEach(selectAllBox => {
        selectAllBox.onchange = () => {
          const section = selectAllBox.closest("table");
          section.querySelectorAll(".pt-bulk-select").forEach(cb => { cb.checked = selectAllBox.checked; });
        };
      });
      function selectedStrategyIds() {
        return [...document.querySelectorAll(".pt-bulk-select:checked")].map(cb => cb.dataset.id);
      }
      async function bulkSetOverride(active) {
        const status = document.getElementById("ptBulkStatus");
        const ids = selectedStrategyIds();
        if (!ids.length) { status.textContent = "Select at least one strategy first."; return; }
        status.textContent = `${active ? "Flagging" : "Unflagging"} ${ids.length} strategy(ies)...`;
        const results = await Promise.all(ids.map(id =>
          apiPost(`/api/paper-trading/override/${id}`, { manual_alert: active }).catch(e => ({ ok: false, error: e.message }))
        ));
        const okCount = results.filter(r => r.ok !== false).length;
        status.textContent = `${okCount}/${ids.length} strategy(ies) ${active ? "flagged" : "unflagged"} successfully.`;
        appendLog(`Bulk Manual Override: ${okCount}/${ids.length} strategies ${active ? "flagged for" : "unflagged from"} Telegram.`);
        render();
      }
      const bulkFlagBtn = document.getElementById("ptBulkFlag");
      if (bulkFlagBtn) bulkFlagBtn.onclick = () => bulkSetOverride(true);
      const bulkUnflagBtn = document.getElementById("ptBulkUnflag");
      if (bulkUnflagBtn) bulkUnflagBtn.onclick = () => bulkSetOverride(false);

      // Strategy Comparison -- Export (Remaining Dashboard Enhancements,
      // item 4): a real .xlsx of exactly what's in the table above,
      // generated server-side (GET is read-only, safe to open directly).
      const exportBtn = document.getElementById("ptExportComparison");
      if (exportBtn) {
        exportBtn.onclick = () => {
          window.open("/api/paper-trading/strategy-comparison/export?period=all", "_blank");
        };
      }

      document.querySelectorAll(".pt-genealogy").forEach(btn => {
        btn.onclick = async () => {
          const res = await apiGet(`/api/paper-trading/genealogy/${btn.dataset.id}`);
          const box = document.getElementById("ptStrategyDetail");
          box.style.display = "block";
          const timeline = res.timeline || [];
          const labels = {
            version_saved: "Config Saved", auto_avoid_triggered: "Auto-Avoid TRIGGERED",
            auto_avoid_cleared: "Auto-Avoid cleared", auto_lesson_applied: "Auto-Lesson APPLIED",
            auto_lesson_cleared: "Auto-Lesson cleared",
          };
          box.textContent = `History -- ${btn.dataset.name}\n(includes manual saves AND automatic self-learning events -- when Pattern Auto-Avoid or Lesson Auto-Apply changed this strategy's behavior)\n\n` +
            (timeline.length
              ? timeline.map(e => `[${(e.at || "").slice(0, 19).replace("T", " ")}] ${labels[e.type] || e.type}${e.symbol ? ` (${e.symbol})` : ""}\n    ${e.detail}`).join("\n\n")
              : "No history recorded for this strategy yet.");
        };
      });

      document.querySelectorAll(".pt-readiness").forEach(btn => {
        btn.onclick = async () => {
          const res = await apiGet(`/api/paper-trading/readiness/${btn.dataset.id}`);
          const box = document.getElementById("ptStrategyDetail");
          box.style.display = "block";
          box.textContent = `Real Trading Readiness -- ${btn.dataset.name}\n\n` +
            `Verdict: ${res.ready_for_real_trading ? "READY to consider for real trading" : "NOT YET ready"}\n\n` +
            res.checklist.map(c => `${c.passed ? "[PASS]" : "[FAIL]"} ${c.label} (${c.detail})`).join("\n") +
            `\n\nThis is informational only -- it never starts real trading or moves money by itself.`;
        };
      });

      document.querySelectorAll(".pt-coin-deep-dive-row").forEach(row => {
        row.onclick = async () => {
          const symbol = row.dataset.symbol;
          const res = await apiGet(`/api/paper-trading/coin-deep-dive/${encodeURIComponent(symbol)}`);
          const box = document.getElementById("ptCoinDeepDive");
          box.style.display = "block";
          box.innerHTML = `
            <div class="section-title" style="margin-top:0;">${esc(symbol)} -- Every Strategy's Performance</div>
            <div class="table-wrap"><table>
              <thead><tr><th>Strategy</th><th>Closed Trades</th><th>Win Rate</th><th>Total PnL</th></tr></thead>
              <tbody>${(res.strategies || []).map(s => `
                <tr>
                  <td>${esc(strategyNameById[s.strategy_id] || s.strategy_id)}</td>
                  <td>${s.closed_trades}</td>
                  <td>${s.win_rate.toFixed(1)}%</td>
                  <td class="${s.total_pnl >= 0 ? "pill-up" : "pill-down"}">${s.total_pnl.toFixed(2)}</td>
                </tr>`).join("") || `<tr><td colspan="4">No data.</td></tr>`}</tbody>
            </table></div>
            <div class="muted" style="font-size:12px;margin-top:6px;">${res.profitable_strategy_count}/${res.strategy_count} strategies profitable on ${esc(symbol)} -- ${res.total_closed_trades} total closed trades, ${res.total_pnl >= 0 ? "+" : ""}$${res.total_pnl.toFixed(2)} combined.</div>`;
        };
      });

      document.querySelectorAll(".pt-view-trade").forEach(btn => {
        btn.onclick = () => {
          const t = trades[parseInt(btn.dataset.idx, 10)];
          const box = document.getElementById("ptTradeDetail");
          box.style.display = "block";
          const r = t.reflection || {};
          box.textContent =
            `${t.symbol} ${t.direction} -- entry ${t.entry_price} -> exit ${t.exit_price}\n` +
            `PnL: ${t.pnl} (${t.pnl_pct}%)  Duration: ${r.duration_minutes || "-"} min\n` +
            `Worst point against this trade (MAE): ${t.mae_amount != null ? "$" + t.mae_amount.toFixed(2) : "-"}  ` +
            `Best point in its favor (MFE): ${t.mfe_amount != null ? "$" + t.mfe_amount.toFixed(2) : "-"}\n\n` +
            `Why Enter: ${r.why_enter || t.entry_reason || "-"}\n` +
            `Why Exit: ${r.why_exit || t.exit_reason || "-"}\n\n` +
            `Success: ${(r.success || []).join(" | ") || "-"}\n` +
            `Mistakes: ${(r.mistakes || []).join(" | ") || "-"}\n\n` +
            `Your Note: ${t.user_note || "(none -- click 🗒 in the table to add one)"}\n\n` +
            `Market State at Entry: ${JSON.stringify(t.market_snapshot || {}, null, 2)}`;
        };
      });
      document.querySelectorAll(".pt-trade-note").forEach(btn => {
        btn.onclick = async () => {
          const note = prompt("Your note on this trade:", btn.dataset.note || "");
          if (note === null) return;
          await apiPost(`/api/paper-trading/positions/${btn.dataset.id}/note`, { note });
          render();
        };
      });
      const exportJournalBtn = document.getElementById("btnExportTradeJournal");
      if (exportJournalBtn) exportJournalBtn.onclick = () => {
        window.open("/api/paper-trading/trade-journal/export-pdf", "_blank");
      };

      wireConfidenceFilter();

      // Confluence Score isn't computed ahead of time for open positions --
      // fetch it per position (bounded by however many are actually open)
      // using the existing retroactive-scoring endpoint, same one already
      // used by Telegram signal messages. Best-effort: a failed fetch just
      // leaves that cell as "-" rather than breaking the rest of the page.
      document.querySelectorAll(".pt-confluence-cell").forEach(cell => {
        apiGet(`/api/paper-trading/confluence/${cell.dataset.positionId}`)
          .then(res => { cell.textContent = res.total ? `${res.passed}/${res.total}` : "-"; })
          .catch(() => {});
      });
    };

    // Grand Feature Expansion, Phase 5 Feature 11: Best Combination
    // Auto-Suggest, extended to a multi-strategy portfolio. Purely
    // informational -- loaded independently like Challenge Mode below,
    // never touches trading behavior.
    async function loadBestPortfolio() {
      const box = document.getElementById("bestPortfolioBox");
      if (!box) return;
      const en = getLang() === "en";
      const r = await apiGet("/api/paper-trading/challenge/best-portfolio").catch(() => null);
      if (!r || !r.portfolio.length) {
        box.innerHTML = `<p class="muted">${esc((r && r.reason) || (en ? "Not enough real trade history yet." : "Abhi kaafi real trade history nahi hai."))}</p>`;
        return;
      }
      box.innerHTML = `
        <p class="muted" style="font-size:12px;margin-top:0;">${esc(r.reason)}</p>
        ${r.portfolio.map(p => `
          <div style="padding:6px 0;border-top:1px solid var(--border,#333);font-size:13px;">
            <b>${esc(p.strategy_name)}</b> -- ${esc(p.symbol)} &middot;
            ${p.total_closed_trades} ${en ? "trades" : "trades"} &middot;
            ${en ? "win rate" : "win rate"} ${p.win_rate_pct}% &middot;
            <span class="${p.total_pnl >= 0 ? "positive" : "negative"}">${p.total_pnl >= 0 ? "+" : ""}$${p.total_pnl.toFixed(2)}</span>
          </div>`).join("")}
        <div class="muted" style="font-size:12px;margin-top:8px;">${en ? "Combined PnL" : "Combined PnL"}: <b class="${r.combined_pnl >= 0 ? "positive" : "negative"}">${r.combined_pnl >= 0 ? "+" : ""}$${r.combined_pnl.toFixed(2)}</b></div>`;
    }

    // Batch 9, Task 4: Challenge Mode. Deliberately loaded independently
    // of the big Promise.all above -- it's a small, self-contained
    // tracking/reporting feature (never touches trading behavior), so it
    // shouldn't slow down or risk breaking the main page load.
    async function loadChallenge() {
      const box = document.getElementById("challengeBox");
      if (!box) return;
      const en = getLang() === "en";
      const c = await apiGet("/api/paper-trading/challenge").catch(() => ({ configured: false }));

      function confidencePill(conf) {
        if (!conf) return "";
        if (!conf.reliable) return `<span class="pill pill-muted">${en ? "Unproven" : "Saabit Nahi"} (${conf.sample_size}/${conf.min_sample_size})</span>`;
        if (conf.status === "reliable_good") return `<span class="pill pill-bullish">${en ? "Statistically Confirmed" : "Aamaar Ke Mutabiq Tasdeeq Shuda"}</span>`;
        if (conf.status === "reliable_bad") return `<span class="pill pill-bearish">${en ? "Confirmed Weak" : "Kamzor Tasdeeq Shuda"}</span>`;
        return `<span class="pill pill-muted">${en ? "Inconclusive" : "Wazeh Nahi"}</span>`;
      }
      function consistencyPill(cons) {
        if (!cons || !cons.checked) return `<span class="pill pill-muted">${en ? "Not enough history" : "Kaafi History Nahi"}</span>`;
        return cons.concentrated
          ? `<span class="pill pill-bearish">${en ? "Concentrated (possible fluke)" : "Ek Hi Waqt Mein Sameta (Fluke Ho Sakta)"}</span>`
          : `<span class="pill pill-bullish">${en ? "Consistent Over Time" : "Waqt Ke Saath Consistent"}</span>`;
      }

      // ---- Recommended-paths / What-If explorer (Level 2 + Level 3) ----
      async function renderRecommendations(container, start_amount, target_amount, days) {
        container.innerHTML = `<p class="muted">${en ? "Analyzing real trade history..." : "Real trade history dekh rahe hain..."}</p>`;
        let result;
        try {
          result = await apiPost("/api/paper-trading/challenge/recommend", { start_amount, target_amount, days });
        } catch (e) {
          container.innerHTML = `<p class="muted">${en ? "Could not compute recommendations." : "Recommendations nahi ban sakin."}</p>`;
          return;
        }
        if (!result.paths.length) {
          container.innerHTML = `<p class="muted">${en
            ? "No strategy-coin combination has any closed trades yet -- start paper trading first."
            : "Abhi tak kisi strategy-coin combination ka koi trade band nahi hua -- pehle paper trading shuru karein."}</p>`;
          return;
        }
        const fallbackHtml = (!result.any_achievable && result.fallback) ? `
          <div class="card" style="border-color:var(--yellow,#c9a227);">
            <p><b>${en ? "This exact target isn't realistic yet from any real combination." : "Yeh target kisi bhi real combination se abhi realistic nahi hai."}</b></p>
            <p>${en
              ? `But based on "${esc(result.fallback.based_on_strategy_name)}" on ${esc(result.fallback.based_on_symbol)} (${result.fallback.based_on_sample_size} real trades), a realistic amount in the same ${days} days would be ~$${result.fallback.realistic_amount_in_same_days.toFixed(2)}${result.fallback.days_needed_for_original_target ? `, or reaching your original target would realistically take ~${result.fallback.days_needed_for_original_target.toFixed(0)} days.` : "."}`
              : `Lekin "${esc(result.fallback.based_on_strategy_name)}" (${esc(result.fallback.based_on_symbol)}, ${result.fallback.based_on_sample_size} real trades) ke mutabiq, isi ${days} din mein ek realistic amount ~$${result.fallback.realistic_amount_in_same_days.toFixed(2)} ban sakta hai${result.fallback.days_needed_for_original_target ? `, ya aap ka asal target ~${result.fallback.days_needed_for_original_target.toFixed(0)} din mein realistically mumkin hai.` : "."}`}</p>
          </div>` : "";

        container.innerHTML = fallbackHtml + result.paths.map(p => `
          <div class="card" style="max-width:680px;">
            <p><b>${esc(p.strategy_name)}</b> -- ${esc(p.symbol)}
              ${p.achievable_at_this_pace ? `<span class="pill pill-bullish">${en ? "Achievable" : "Mumkin"}</span>` : `<span class="pill pill-muted">${en ? "Below required pace" : "Zaroori Pace Se Kam"}</span>`}
              ${confidencePill(p.confidence)} ${consistencyPill(p.consistency)}
            </p>
            <p class="muted">${en ? "Win rate" : "Win Rate"}: ${p.win_rate_pct}% (${p.sample_size} ${en ? "trades" : "trades"}) --
              ${en ? "profit factor" : "Profit Factor"}: ${p.profit_factor != null ? p.profit_factor : "-"} --
              ${en ? "max drawdown" : "Max Drawdown"}: $${p.max_drawdown} --
              ${en ? "demonstrated pace" : "Demonstrated Pace"}: ${p.demonstrated_daily_rate_pct.toFixed(2)}%/${en ? "day" : "din"}
              ${p.projected_days_to_target ? ` -- ${en ? "projected" : "andaza"}: ${p.projected_days_to_target.toFixed(0)} ${en ? "days" : "din"}` : ""}</p>
            <p class="muted" style="font-size:12px;">${esc(p.confidence.conclusion)}${p.consistency.note ? " -- " + esc(p.consistency.note) : ""}</p>
            <button class="btn-ghost ch-start-path" data-sid="${esc(p.strategy_id)}" data-sym="${esc(p.symbol)}">${en ? "Start This Challenge" : "Yeh Challenge Shuru Karein"}</button>
          </div>`).join("");

        container.querySelectorAll(".ch-start-path").forEach(btn => {
          btn.onclick = async () => {
            await apiPost("/api/paper-trading/challenge", {
              start_amount, target_amount, days,
              scope_strategy_id: btn.dataset.sid, scope_symbol: btn.dataset.sym,
            });
            loadChallenge();
          };
        });
      }

      if (!c.configured) {
        box.innerHTML = `
          <div class="card" style="max-width:480px;">
            <p class="muted">${en
              ? "No challenge set. Enter your own starting amount, target amount, and days -- the system will show real, per-strategy-per-coin recommendations with honest confidence levels, not one blended guess."
              : "Abhi koi challenge set nahi hai. Apna starting amount, target amount, aur din daaliye -- system har real strategy-coin combination ke liye alag, honest recommendations dikhayega, sirf ek andaza nahi."}</p>
            <label>${en ? "Starting Amount ($)" : "Shuru Ka Amount ($)"}<input type="number" id="chStart" step="0.01" min="0.01"></label>
            <label>${en ? "Target Amount ($)" : "Target Amount ($)"}<input type="number" id="chTarget" step="0.01" min="0.01"></label>
            <label>${en ? "Time Period (days)" : "Time Period (din)"}<input type="number" id="chDays" step="1" min="1"></label>
            <label style="display:flex;align-items:center;gap:8px;width:auto;">
              <input type="checkbox" id="chTelegram" style="width:auto;">
              <span>${en ? "Include in Daily Telegram Report" : "Daily Telegram Report Mein Shamil Karein"}</span>
            </label>
            <div class="btn-row">
              <button class="btn" id="chAnalyze">${en ? "See Real Recommendations" : "Real Recommendations Dekhein"}</button>
              <button class="btn-ghost" id="chSave">${en ? "Start Blended (System-Wide)" : "System-Wide Challenge Shuru Karein"}</button>
            </div>
            <span id="chMsg" class="muted"></span>
          </div>
          <div id="chRecommendations"></div>`;
        const readInputs = () => ({
          start_amount: parseFloat(document.getElementById("chStart").value),
          target_amount: parseFloat(document.getElementById("chTarget").value),
          days: parseInt(document.getElementById("chDays").value, 10),
        });
        document.getElementById("chAnalyze").onclick = async () => {
          const { start_amount, target_amount, days } = readInputs();
          const msgEl = document.getElementById("chMsg");
          if (!start_amount || !target_amount || !days) {
            msgEl.textContent = en ? "All three fields are required." : "Teeno fields zaroori hain.";
            return;
          }
          msgEl.textContent = "";
          await renderRecommendations(document.getElementById("chRecommendations"), start_amount, target_amount, days);
        };
        document.getElementById("chSave").onclick = async () => {
          const msgEl = document.getElementById("chMsg");
          const { start_amount, target_amount, days } = readInputs();
          const telegram_report_enabled = document.getElementById("chTelegram").checked;
          if (!start_amount || !target_amount || !days) {
            msgEl.textContent = en ? "All three fields are required." : "Teeno fields zaroori hain.";
            return;
          }
          try {
            await apiPost("/api/paper-trading/challenge", { start_amount, target_amount, days, telegram_report_enabled });
            loadChallenge();
          } catch (e) {
            msgEl.textContent = e.message || (en ? "Failed to save." : "Save nahi hua.");
          }
        };
        return;
      }

      const realisticPill = c.realistic === null
        ? `<span class="pill pill-muted">${en ? "Not Enough History Yet" : "Abhi Kaafi History Nahi"}</span>`
        : c.realistic
          ? `<span class="pill pill-bullish">${en ? "Realistic" : "Realistic"}</span>`
          : `<span class="pill pill-bearish">${en ? "NOT Realistic" : "REALISTIC NAHI"}</span>`;
      const pacePill = c.ahead_of_pace
        ? `<span class="pill pill-bullish">${en ? "Ahead of Pace" : "Pace Se Aage"}</span>`
        : `<span class="pill pill-bearish">${en ? "Behind Pace" : "Pace Se Peeche"}</span>`;
      const scopeLine = c.scope_strategy_id
        ? `<p class="muted">${en ? "Tracking a specific combination" : "Ek khaas combination track ho raha hai"}: <b>${esc(c.scope_strategy_id)}</b> / <b>${esc(c.scope_symbol)}</b></p>`
        : `<p class="muted">${en ? "Tracking system-wide (all strategies blended)" : "Poore system ki blended pace track ho rahi hai"}</p>`;
      const driftBanner = (c.drift && c.drift.checked && c.drift.drifted) ? `
        <div class="card" style="border-color:var(--red,#c0392b);">
          <p><b>⚠️ ${en ? "Performance Drift Warning" : "Performance Drift Warning"}</b></p>
          <p>${esc(c.drift.note)}</p>
        </div>` : "";
      const finishLine = c.projected_finish_date
        ? `<p class="muted">${en ? "Projected finish (at real realized pace)" : "Andaazan mukammal hone ki tareekh (real pace ke mutabiq)"}: ${new Date(c.projected_finish_date).toLocaleDateString()}</p>`
        : "";

      box.innerHTML = `
        ${driftBanner}
        <div class="grid">
          ${card(en ? "Starting Amount" : "Shuru Ka Amount", `$${c.start_amount.toFixed(2)}`)}
          ${card(en ? "Target Amount" : "Target Amount", `$${c.target_amount.toFixed(2)}`)}
          ${card(en ? "Current Amount (Real Trades)" : "Abhi Ka Amount (Real Trades)", `$${c.current_amount.toFixed(2)}`)}
          ${card(en ? "Progress" : "Progress", `${c.progress_pct.toFixed(1)}%`)}
          ${card(en ? "Days Elapsed / Remaining" : "Din Guzre / Baaki", `${c.elapsed_days.toFixed(1)} / ${c.remaining_days.toFixed(1)}`)}
          ${cardClass(en ? "Pace" : "Pace", pacePill, "")}
          ${cardClass(en ? "Realistic?" : "Realistic?", realisticPill, "")}
        </div>
        <div class="card" style="max-width:640px;">
          ${scopeLine}
          <p><b>${en ? "Required pace" : "Zaroori Pace"}:</b> ${c.required_daily_rate_pct.toFixed(2)}%/${en ? "day" : "din"}
          ${c.real_demonstrated_daily_rate_pct != null
            ? ` -- <b>${en ? "real demonstrated pace" : "real pace"}:</b> ${c.real_demonstrated_daily_rate_pct.toFixed(2)}%/${en ? "day" : "din"} (${c.closed_trades_used_for_baseline} ${en ? "real closed trades" : "real closed trades"})`
            : ""}</p>
          ${finishLine}
          <p>${esc(c.honest_note)}</p>
          <p class="muted" style="font-size:12px;">${en ? "Note: Challenge Mode is tracking/analysis only -- starting or updating it never changes risk %, position sizing, or any trading behavior." : "Note: Challenge Mode sirf tracking/analysis hai -- ise shuru ya update karne se risk %, position sizing, ya koi bhi trading behavior kabhi nahi badalta."}</p>
        </div>
        <button class="btn-ghost" id="chClear">${en ? "Clear Challenge" : "Challenge Hataayein"}</button>
      `;
      document.getElementById("chClear").onclick = async () => {
        await apiPost("/api/paper-trading/challenge/clear");
        loadChallenge();
      };
    }

    await render();
    // Master Task 3, Phase 0.8d: a real-time WebSocket event (onLive below)
    // already re-renders the instant a trade opens/closes, but this page
    // also shows account-drawdown/kill-switch state, challenge progress,
    // and other data that can change without a "paper" channel event --
    // and a dropped/reconnecting WebSocket (see connectWs's own retry
    // loop) must never leave this page silently stale in the meantime.
    autoRefresh(render, 30);
    onLive((msg) => {
      if (msg.channel !== "paper") return;
      // Batch 10, Task 3: a real "position_opened" event (paper_trading.
      // engine's own _emit, unchanged) pauses the scan cycle and surfaces
      // a "Match Found" toast with a real explanation/grade/freshness
      // detail view -- presentation only, never influences which
      // position actually opened or when.
      if (msg.type === "position_opened" && msg.position) {
        clearInterval(_scanCycleTimer);
        const pos = msg.position;
        const en = getLang() === "en";
        showToast({
          title: en ? `Match Found -- ${pos.symbol}` : `Match Mil Gaya -- ${pos.symbol}`,
          body: `${(pos.direction || "").toUpperCase()} -- ${pos.strategy_name || pos.strategy_id || "-"}`,
          actionLabel: en ? "Why This Signal?" : "Yeh Signal Kyun?",
          onAction: () => showSignalMatchDetail(pos.id),
          timeoutMs: 20000,
        });
        showSignalMatchDetail(pos.id);
      }
      render().catch(console.error);
    });

    async function showSignalMatchDetail(positionId) {
      const box = document.getElementById("ptSignalMatchDetail");
      if (!box) return;
      const en = getLang() === "en";
      box.style.display = "block";
      box.innerHTML = `<p class="muted">${en ? "Loading..." : "Load ho raha hai..."}</p>`;
      let d;
      try {
        d = await apiGet(`/api/paper-trading/signal-detail/${positionId}`);
      } catch (e) {
        box.innerHTML = `<p class="muted">${en ? "Couldn't load" : "Load nahi hua"}: ${esc(e.message)}</p>`;
        return;
      }
      const pos = d.position;
      box.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
          <div><b>${esc(pos.symbol)}</b> ${(pos.direction || "").toUpperCase()} -- ${esc(pos.strategy_name || pos.strategy_id || "-")}</div>
          <span class="pill ${d.grade.grade === "A+" || d.grade.grade === "A" ? "pill-bullish" : d.grade.grade === "B" ? "pill-muted" : "pill-bearish"}">${esc(d.grade.grade)}</span>
        </div>
        <p style="font-size:13px;">${esc(d.explanation_text)}</p>
        <p class="muted" style="font-size:12px;">${esc(d.grade.reason)}</p>
        <p class="muted" style="font-size:12px;">${en ? "Freshness" : "Taazgi"}: ${d.freshness.fresh
          ? (en ? "Fresh" : "Taaza")
          : esc(d.freshness.reason || (en ? "Not fresh" : "Taaza Nahi"))}</p>`;
    }
  }

  // ------------------------------------------------------------ SETTINGS
  async function renderSettings() {
    const s = await apiGet("/api/settings");
    content.innerHTML = `
      <div class="section-title">Settings</div>
      <div class="card" style="max-width:480px;">
        <div class="form-row"><label>Exchange</label>
          <select id="setExchange">${s.available_exchanges.map(e => `<option ${e===s.exchange?'selected':''}>${e}</option>`).join("")}</select>
        </div>
        <div class="form-row"><label>Default Risk %</label><input id="setRisk" type="number" step="0.1" value="${s.default_risk_pct}"></div>
        <div class="form-row"><label>Refresh Speed (seconds)</label><input id="setRefresh" type="number" value="${s.refresh_speed_seconds}"></div>
        <div class="form-row"><label>Database Location (read-only)</label><input value="${esc(s.database_location)}" disabled></div>
        <div class="btn-row"><button class="btn" id="btnSaveSettings">Save Settings</button><span id="setSaveStatus" class="muted"></span></div>
      </div>
      <div class="section-title">System Health</div>
      <div class="grid" id="healthGrid">
        ${cardId("healthUptime", "Server Uptime", "...")}
        ${cardId("healthCpu", "CPU Usage", "...")}
        ${cardId("healthRam", "Memory Usage", "...")}
        ${cardId("healthDbSize", "Database Size", "...")}
        ${cardId("healthActive", "Active Processes", "...")}
      </div>
      <div class="card" id="healthErrorsCard" style="margin-bottom:22px;">
        <div class="label">Recent Errors (from logs)</div>
        <div id="healthErrors" class="activity-feed muted">Loading...</div>
      </div>

      <div class="section-title">Voice Alerts ${helpIcon("voice_alerts")}</div>
      <div class="card" style="max-width:480px;">
        <p class="muted" style="font-size:12px;margin-top:0;">When the kill switch or the account-wide drawdown circuit-breaker activates, this browser tab speaks it out loud immediately -- useful if the dashboard isn't the thing you're actively looking at.</p>
        <label style="display:flex;align-items:center;gap:6px;width:auto;">
          <input type="checkbox" id="voiceAlertsMuted" style="width:auto;"> Mute voice alerts on this browser
        </label>
        <div class="btn-row" style="margin-top:8px;">
          <button class="btn-ghost" id="btnTestVoiceAlert">Test Voice Alert</button>
        </div>
      </div>

      <div class="section-title">${getLang() === "en" ? "Beginner Mode" : "Beginner Mode"}</div>
      <div class="card" style="max-width:480px;">
        <p class="muted" style="font-size:12px;margin-top:0;">${getLang() === "en"
          ? `Highlights every "?" help icon across the app so it's obvious you can click any of them for a plain-language explanation -- useful if you're new to trading or to SINDHU itself. A per-browser display setting only; it never hides or changes any real number.`
          : `App mein har "?" help icon ko highlight karta hai taake pata chale aap kisi bhi icon par click karke plain-language explanation dekh sakte hain -- agar aap trading ya SINDHU mein naye hain to useful hai. Sirf is browser ka display setting hai; koi asal number nahi chhupata ya badalta.`}</p>
        <label style="display:flex;align-items:center;gap:6px;width:auto;">
          <input type="checkbox" id="beginnerModeToggle" style="width:auto;"> ${getLang() === "en" ? "Turn on Beginner Mode" : "Beginner Mode Chalu Karein"}
        </label>
        <div class="btn-row" style="margin-top:8px;">
          <button class="btn-ghost" id="btnRetakeTour">${getLang() === "en" ? "Take the Tour Again" : "Dobara Tour Lein"}</button>
        </div>
      </div>

      <div class="section-title">Backup</div>
      <div class="card">
        <div class="btn-row"><button class="btn" id="btnBackupNow">Create Backup Now</button></div>
        <div id="backupList" class="table-wrap"></div>
      </div>

      <div class="section-title">${getLang() === "en" ? "Weekly Snapshot" : "Weekly Snapshot"} ${helpIcon("weekly_snapshot")}</div>
      <div class="card">
        <p class="muted" style="font-size:12px;margin-top:0;">${getLang() === "en"
          ? "A separate, once-a-week database snapshot, kept for about 2 months -- distinct from the rolling backup above, which keeps only its last 10 copies (roughly 1-2 days at the default interval)."
          : "Ek alag, hafte mein ek baar database snapshot, taqreeban 2 mahine ke liye rakha jata hai -- upar wali rolling backup se alag, jo sirf apni aakhri 10 copies rakhti hai (default interval par taqreeban 1-2 din)."}</p>
        <div class="btn-row"><button class="btn" id="btnWeeklySnapshotNow">${getLang() === "en" ? "Create Weekly Snapshot Now" : "Abhi Weekly Snapshot Banayein"}</button></div>
        <div id="weeklySnapshotList" class="table-wrap"></div>
      </div>

      <div class="section-title">${getLang() === "en" ? "Automated Weekly Digest" : "Automated Weekly Digest"} ${helpIcon("infra_weekly_digest")}</div>
      <div class="card">
        <p class="muted" style="font-size:12px;margin-top:0;">${getLang() === "en"
          ? "A weekly summary of SYSTEM health -- backups, incidents, database/disk size -- separate from the trading and evolution weekly reports."
          : "System ki weekly halat -- backups, incidents, database/disk size -- trading aur evolution ke weekly reports se alag."}</p>
        <div id="infraDigestBody"></div>
        <div class="btn-row" style="margin-top:8px;">
          <button class="btn-ghost" id="btnGenInfraDigest">${getLang() === "en" ? "Generate Now" : "Abhi Banayein"}</button>
        </div>
      </div>

      <div class="section-title">Telegram Integration</div>
      <div class="card" style="max-width:480px;">
        <div class="form-row"><label>Bot Token (write-only -- never shown again after saving)</label>
          <input id="tgToken" type="password" placeholder="Enter to set/replace"></div>
        <div class="form-row"><label>Channel ID</label><input id="tgChannelId" placeholder="e.g. -1001234567890"></div>
        <div class="form-row"><label>Rate Limit (messages per hour)</label><input id="tgRateLimit" type="number"></div>
        <div class="form-row"><label><input id="tgAutoSend" type="checkbox" style="width:auto;"> Enable automatic high-confidence sending (OFF by default -- a deliberate safety choice)</label></div>
        <div class="btn-row">
          <button class="btn" id="btnSaveTelegram">Save Settings</button>
          <button class="btn-ghost" id="btnTestTelegram">Send Test Message</button>
          <span id="tgStatus" class="muted"></span>
        </div>
      </div>

      <div class="section-title">Telegram Proxy (for networks that block Telegram)</div>
      <div class="card" style="max-width:520px;">
        <p class="muted" style="font-size:12px;margin-top:0;">If Telegram is blocked on this network (some ISPs block it), route Telegram messages through a proxy server instead of connecting directly. Leave this off if Telegram already works normally.</p>
        <div class="form-row"><label><input id="tgProxyEnabled" type="checkbox" style="width:auto;"> Route Telegram traffic through a proxy</label></div>
        <div class="form-row"><label>Proxy URL (write-only -- never shown again after saving)</label>
          <input id="tgProxyUrl" type="password" placeholder="socks5://user:pass@host:port or http://user:pass@host:port"></div>
        <div class="btn-row">
          <button class="btn" id="btnSaveTelegramProxy">Save Proxy Settings</button>
          <button class="btn-ghost" id="btnTestProxy">Test Proxy Connection</button>
          <span id="tgProxyStatus" class="muted"></span>
        </div>
      </div>
      <div class="section-title">Silent Hours (Do-Not-Disturb)</div>
      <div class="card" style="max-width:480px;">
        <p class="muted" style="font-size:12px;margin-top:0;">Signals still send and are fully logged during this window -- only the phone notification sound/vibration is muted (Telegram's own silent-message feature). Times are in UTC.</p>
        <div class="form-row"><label><input id="tgSilentEnabled" type="checkbox" style="width:auto;"> Enable Silent Hours</label></div>
        <div class="form-row"><label>Start (UTC, HH:MM)</label><input id="tgSilentStart" placeholder="23:00"></div>
        <div class="form-row"><label>End (UTC, HH:MM)</label><input id="tgSilentEnd" placeholder="07:00"></div>
        <div class="btn-row">
          <button class="btn" id="btnSaveTelegramSilentHours">Save</button>
          <span id="tgSilentStatus" class="muted"></span>
        </div>
      </div>

      <div class="section-title">Multi-Channel Routing</div>
      <div class="card" style="max-width:520px;">
        <p class="muted" style="font-size:12px;margin-top:0;">Send a specific strategy's signals to a DIFFERENT Telegram channel than the default above -- same bot, just a different destination. Leave a strategy's box empty to keep it on the default channel.</p>
        <div id="tgChannelOverridesBox" class="table-wrap"></div>
      </div>

      <div class="section-title">Telegram Message Log</div>
      <div class="table-wrap"><table>
        <thead><tr><th>Time</th><th>Trigger</th><th>Strategy</th><th>Result</th></tr></thead>
        <tbody id="tgLogBody"><tr><td colspan="4">Loading...</td></tr></tbody>
      </table></div>`;

    function fmtUptime(seconds) {
      const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60);
      return h > 0 ? `${h}h ${m}m` : `${m}m ${Math.floor(seconds % 60)}s`;
    }
    async function loadHealth() {
      const h = await apiGet("/api/system/health");
      document.getElementById("healthUptime").textContent = fmtUptime(h.uptime_seconds);
      document.getElementById("healthCpu").textContent = `${h.cpu_percent.toFixed(0)}%`;
      document.getElementById("healthRam").textContent = `${h.ram_percent.toFixed(0)}%`;
      document.getElementById("healthDbSize").textContent = fmtBytes(h.database_size_bytes);
      document.getElementById("healthActive").textContent = h.active_process_count;
      const errBox = document.getElementById("healthErrors");
      if (!h.recent_errors.length) {
        errBox.innerHTML = `<div class="muted">No recent errors -- looking healthy.</div>`;
      } else {
        errBox.innerHTML = h.recent_errors.map(line => `<div class="activity-item">${esc(line)}</div>`).join("");
      }
    }
    loadHealth();
    autoRefresh(loadHealth, 15);

    async function saveSettings() {
      const status = document.getElementById("setSaveStatus");
      status.textContent = "Saving...";
      try {
        await autosave("POST", "/api/settings", {
          exchange: document.getElementById("setExchange").value,
          default_risk_pct: parseFloat(document.getElementById("setRisk").value),
          refresh_speed_seconds: parseInt(document.getElementById("setRefresh").value, 10),
        });
        status.textContent = "Saved";
      } catch (e) {
        status.textContent = "Save failed (will retry)";
      }
    }
    // Auto Save: every field change persists immediately (debounced) --
    // the button stays for explicit, instant confirmation.
    const debouncedSaveSettings = debounce(saveSettings, 500);
    ["setExchange", "setRisk", "setRefresh"].forEach(id => {
      const el = document.getElementById(id);
      el.addEventListener("input", debouncedSaveSettings);
      el.addEventListener("change", debouncedSaveSettings);
    });
    document.getElementById("btnSaveSettings").onclick = saveSettings;

    const voiceAlertsMutedEl = document.getElementById("voiceAlertsMuted");
    voiceAlertsMutedEl.checked = localStorage.getItem("sindhu_voice_alerts_muted") === "true";
    voiceAlertsMutedEl.onchange = () => {
      localStorage.setItem("sindhu_voice_alerts_muted", voiceAlertsMutedEl.checked ? "true" : "false");
    };
    document.getElementById("btnTestVoiceAlert").onclick = () => {
      _speak("This is a test of the SINDHU voice alert.");  // bypasses mute -- a deliberate manual test
    };

    const beginnerModeEl = document.getElementById("beginnerModeToggle");
    beginnerModeEl.checked = localStorage.getItem("sindhu_beginner_mode") === "true";
    beginnerModeEl.onchange = () => {
      localStorage.setItem("sindhu_beginner_mode", beginnerModeEl.checked ? "true" : "false");
      applyBeginnerModeClass();
    };
    document.getElementById("btnRetakeTour").onclick = () => {
      location.hash = "#home";
      setTimeout(startOnboardingTour, 300);
    };

    async function loadBackups() {
      const b = await apiGet("/api/backup/list");
      document.getElementById("backupList").innerHTML = `<table>
        <thead><tr><th>Name</th><th>Size</th><th>Modified</th></tr></thead>
        <tbody>${b.backups.map(x => `<tr><td>${esc(x.name)}</td><td>${fmtBytes(x.size_bytes)}</td><td>${esc(x.modified_at.slice(0,19))}</td></tr>`).join("")}</tbody>
      </table>`;
    }
    document.getElementById("btnBackupNow").onclick = async () => {
      await apiPost("/api/backup/create");
      appendLog("Manual backup created.");
      loadBackups();
    };
    loadBackups();

    async function loadWeeklySnapshots() {
      const s = await apiGet("/api/weekly-snapshot/list");
      document.getElementById("weeklySnapshotList").innerHTML = `<table>
        <thead><tr><th>Name</th><th>Size</th><th>Modified</th></tr></thead>
        <tbody>${s.snapshots.map(x => `<tr><td>${esc(x.name)}</td><td>${fmtBytes(x.size_bytes)}</td><td>${esc(x.modified_at.slice(0,19))}</td></tr>`).join("") || '<tr><td colspan="3">No weekly snapshots yet.</td></tr>'}</tbody>
      </table>`;
    }
    document.getElementById("btnWeeklySnapshotNow").onclick = async () => {
      await apiPost("/api/weekly-snapshot/create-now");
      appendLog("Weekly snapshot created.");
      loadWeeklySnapshots();
    };
    loadWeeklySnapshots();

    async function loadInfraDigest() {
      const d = await apiGet("/api/infra-weekly-digest?limit=1");
      const body = document.getElementById("infraDigestBody");
      body.innerHTML = d.digests.length
        ? `<div style="white-space:pre-wrap;font-size:13px;">${esc(d.digests[0].report_text)}</div>
           <div class="muted" style="font-size:11px;margin-top:6px;">${esc((d.digests[0].created_at || "").slice(0, 19))}</div>`
        : `<p class="muted">${getLang() === "en" ? "No weekly digest generated yet." : "Abhi tak koi weekly digest nahi bani."}</p>`;
    }
    document.getElementById("btnGenInfraDigest").onclick = async () => {
      await apiPost("/api/infra-weekly-digest/generate-now");
      appendLog("Infrastructure weekly digest generated.");
      loadInfraDigest();
    };
    loadInfraDigest();

    async function loadTelegramSettings() {
      const s = await apiGet("/api/paper-trading/telegram/settings").catch(() => null);
      if (!s) return;
      document.getElementById("tgChannelId").value = s.channel_id || "";
      document.getElementById("tgRateLimit").value = s.rate_limit_per_hour;
      document.getElementById("tgAutoSend").checked = s.auto_send_enabled;
      document.getElementById("tgToken").placeholder = s.token_configured ? "Token already set -- enter to replace" : "Enter to set/replace";
      document.getElementById("tgProxyEnabled").checked = !!s.proxy_enabled;
      document.getElementById("tgProxyUrl").placeholder = s.proxy_configured ? "Proxy URL already set -- enter to replace" : "socks5://user:pass@host:port or http://user:pass@host:port";
      document.getElementById("tgSilentEnabled").checked = !!s.silent_hours_enabled;
      document.getElementById("tgSilentStart").value = s.silent_hours_start_utc || "23:00";
      document.getElementById("tgSilentEnd").value = s.silent_hours_end_utc || "07:00";
    }
    document.getElementById("btnSaveTelegramSilentHours").onclick = async () => {
      const status = document.getElementById("tgSilentStatus");
      status.textContent = "Saving...";
      await apiPost("/api/paper-trading/telegram/settings", {
        silent_hours_enabled: document.getElementById("tgSilentEnabled").checked,
        silent_hours_start_utc: document.getElementById("tgSilentStart").value.trim() || "23:00",
        silent_hours_end_utc: document.getElementById("tgSilentEnd").value.trim() || "07:00",
      });
      status.textContent = "Saved.";
    };
    async function loadTelegramChannelOverrides() {
      const [s, stratsRes] = await Promise.all([
        apiGet("/api/paper-trading/telegram/settings").catch(() => ({ strategy_channel_overrides: {} })),
        apiGet("/api/backtesting/strategies").catch(() => ({ strategies: [] })),
      ]);
      const overrides = s.strategy_channel_overrides || {};
      const strategies = stratsRes.strategies || [];
      const box = document.getElementById("tgChannelOverridesBox");
      box.innerHTML = `<table>
        <thead><tr><th>Strategy</th><th>Channel ID</th><th></th></tr></thead>
        <tbody>${strategies.map(st => `
          <tr>
            <td>${esc(st.name)}</td>
            <td><input class="tg-channel-override-input" data-strategy-id="${esc(st.id)}" value="${esc(overrides[st.id] || "")}" placeholder="default channel"></td>
            <td><button class="btn-ghost tg-channel-override-save" data-strategy-id="${esc(st.id)}" style="font-size:12px;">Save</button></td>
          </tr>`).join("") || `<tr><td colspan="3">No strategies yet.</td></tr>`}</tbody>
      </table>`;
      box.querySelectorAll(".tg-channel-override-save").forEach(btn => btn.onclick = async () => {
        const sid = btn.dataset.strategyId;
        const input = box.querySelector(`.tg-channel-override-input[data-strategy-id="${CSS.escape(sid)}"]`);
        await apiPost(`/api/paper-trading/telegram/channel-override/${encodeURIComponent(sid)}`, {
          channel_id: input.value.trim() || null,
        });
        appendLog(`Telegram routing updated for ${sid}.`);
      });
    }
    async function loadTelegramLog() {
      const r = await apiGet("/api/paper-trading/telegram/log").catch(() => ({ messages: [] }));
      document.getElementById("tgLogBody").innerHTML = r.messages.map(m => `
        <tr>
          <td>${esc((m.sent_at||"").slice(0,19))}</td>
          <td>${esc(m.trigger_type)}</td>
          <td>${esc(m.strategy_name || "-")}</td>
          <td>${m.success ? '<span class="pill pill-completed">Sent</span>' : `<span class="pill pill-error" title="${esc(m.error||"")}">Failed</span>`}</td>
        </tr>`).join("") || '<tr><td colspan="4">No messages yet.</td></tr>';
    }
    document.getElementById("btnSaveTelegram").onclick = async () => {
      const status = document.getElementById("tgStatus");
      status.textContent = "Saving...";
      const body = {
        channel_id: document.getElementById("tgChannelId").value.trim(),
        rate_limit_per_hour: parseInt(document.getElementById("tgRateLimit").value, 10) || 10,
        auto_send_enabled: document.getElementById("tgAutoSend").checked,
      };
      const token = document.getElementById("tgToken").value.trim();
      if (token) body.bot_token = token;
      await apiPost("/api/paper-trading/telegram/settings", body);
      document.getElementById("tgToken").value = "";
      status.textContent = "Saved.";
      loadTelegramSettings();
    };
    document.getElementById("btnTestTelegram").onclick = async () => {
      const status = document.getElementById("tgStatus");
      status.textContent = "Sending test message...";
      const r = await apiPost("/api/paper-trading/telegram/test", {}, 120000);
      status.textContent = r.ok ? "Test message sent successfully -- check your channel." : `Failed: ${r.error}`;
      loadTelegramLog();
    };
    document.getElementById("btnSaveTelegramProxy").onclick = async () => {
      const status = document.getElementById("tgProxyStatus");
      status.textContent = "Saving...";
      const body = { proxy_enabled: document.getElementById("tgProxyEnabled").checked };
      const url = document.getElementById("tgProxyUrl").value.trim();
      if (url) body.proxy_url = url;
      await apiPost("/api/paper-trading/telegram/settings", body);
      document.getElementById("tgProxyUrl").value = "";
      status.textContent = "Saved.";
      loadTelegramSettings();
    };
    document.getElementById("btnTestProxy").onclick = async () => {
      const status = document.getElementById("tgProxyStatus");
      status.textContent = "Testing proxy connection...";
      const r = await apiPost("/api/paper-trading/telegram/test-proxy", {}, 120000);
      status.textContent = r.ok ? `Proxy works -- outbound IP is ${r.exit_ip}.` : `Failed: ${r.error}`;
    };
    loadTelegramSettings();
    loadTelegramChannelOverrides();
    loadTelegramLog();
  }

  // ------------------------------------------------------------ KNOWLEDGE
  async function renderKnowledge() {
    const [report, categoriesRes] = await Promise.all([
      apiGet("/api/knowledge/report"),
      apiGet("/api/knowledge/categories"),
    ]);
    const categories = categoriesRes.categories;

    content.innerHTML = `
      <div class="section-title">Knowledge</div>
      <div class="grid">
        ${cardId("kScoreVal", "Knowledge Score", `${report.knowledge_score}%`)}
        ${cardId("kTotalVal", "Total Lessons", fmtNum(report.total_lessons))}
        ${cardId("kActiveVal", "Active Lessons", fmtNum(report.active_lessons))}
        ${cardId("kDisabledVal", "Disabled Lessons", fmtNum(report.disabled_lessons))}
        ${cardId("kAppliedVal", "Lessons Applied", fmtNum(report.lessons_applied))}
        ${cardId("kRejectedVal", "Trades Rejected", fmtNum(report.trades_rejected_by_lessons))}
        ${cardId("kApprovedVal", "Trades Approved", fmtNum(report.trades_approved_by_lessons))}
      </div>

      <div class="two-col">
        <div>
          <div class="section-title" id="formTitle">New Lesson</div>
          <div class="card">
            <div class="form-row"><label>Title</label><input id="lTitle"></div>
            <div class="form-row"><label>Category</label>
              <select id="lCategory">${categories.map(c => `<option>${esc(c)}</option>`).join("")}</select>
            </div>
            <div class="form-row"><label>Description (parsed the same way as strategy rules -- e.g. "avoid buying when RSI above 70")</label>
              <textarea id="lDescription" style="min-height:80px;"></textarea>
            </div>
            <div class="form-row"><label>Priority</label>
              <select id="lPriority"><option>Low</option><option selected>Medium</option><option>High</option><option>Critical</option></select>
            </div>
            <div class="form-row"><label>Status</label>
              <select id="lStatus"><option selected>active</option><option>disabled</option><option>draft</option></select>
            </div>
            <div class="form-row"><label>Notes</label><textarea id="lNotes" style="min-height:50px;"></textarea></div>
            <div class="form-row">
              <label><input type="checkbox" id="lApplyBT" checked style="width:auto;"> Apply in Backtesting</label>
              <label><input type="checkbox" id="lApplyPT" checked style="width:auto;"> Apply in Paper Trading</label>
              <label><input type="checkbox" id="lApplyEV" checked style="width:auto;"> Apply in Evolution</label>
            </div>
            <div class="btn-row">
              <button class="btn" id="btnSaveLesson">Save Lesson</button>
              <button class="btn-ghost" id="btnClearForm">Clear</button>
              <span id="lSaveStatus" class="muted"></span>
            </div>
          </div>
        </div>

        <div>
          <div class="section-title">Lesson Categories</div>
          <div class="card">${Object.entries(report.categories || {}).map(([c, n]) => `${esc(c)}: ${n}`).join(" &nbsp;|&nbsp; ") || "No lessons yet"}</div>
          <div class="section-title">Recent Lessons</div>
          <div class="card">${(report.recent_lessons || []).map(l => esc(l.title)).join(", ") || "None"}</div>
          <div class="section-title">Best Lessons</div>
          <div id="bestLessonsBox" class="card"></div>
          <div class="section-title">Worst Lessons</div>
          <div id="worstLessonsBox" class="card"></div>
        </div>
      </div>

      <div class="section-title">All Lessons</div>
      <div class="btn-row">
        <input id="lessonSearch" placeholder="Search lessons..." style="max-width:240px;">
        <select id="lessonCategoryFilter" style="max-width:200px;">
          <option value="">All Categories</option>
          ${categories.map(c => `<option>${esc(c)}</option>`).join("")}
        </select>
      </div>
      <div class="table-wrap"><table>
        <thead><tr>
          <th>Title</th><th>Category</th><th>Priority</th><th>Status</th>
          <th>Used</th><th>Approved</th><th>Rejected</th><th>Impact</th><th></th>
        </tr></thead>
        <tbody id="lessonsTableBody"></tbody>
      </table></div>`;

    let editingId = null;
    let creatingLesson = false;

    async function refreshKnowledgeStats() {
      const r = await apiGet("/api/knowledge/report").catch(() => null);
      if (!r) return;
      document.getElementById("kScoreVal").textContent = `${r.knowledge_score}%`;
      document.getElementById("kTotalVal").textContent = fmtNum(r.total_lessons);
      document.getElementById("kActiveVal").textContent = fmtNum(r.active_lessons);
      document.getElementById("kDisabledVal").textContent = fmtNum(r.disabled_lessons);
      document.getElementById("kAppliedVal").textContent = fmtNum(r.lessons_applied);
      document.getElementById("kRejectedVal").textContent = fmtNum(r.trades_rejected_by_lessons);
      document.getElementById("kApprovedVal").textContent = fmtNum(r.trades_approved_by_lessons);
    }

    async function loadLessons() {
      const q = document.getElementById("lessonSearch").value;
      const category = document.getElementById("lessonCategoryFilter").value;
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      if (category) params.set("category", category);
      const res = await apiGet(`/api/knowledge/lessons?${params.toString()}`);

      const used = res.lessons.filter(l => l.stats.times_used > 0);
      const byImpactDesc = [...used].sort((a, b) => b.estimated_impact_pct - a.estimated_impact_pct);
      const lessonLine = l => `<div>${esc(l.title)} <span class="muted">(${l.estimated_impact_pct}%, ${l.stats.times_used} used)</span></div>`;
      document.getElementById("bestLessonsBox").innerHTML = byImpactDesc.slice(0, 3).map(lessonLine).join("") || `<span class="muted">Not enough usage data yet.</span>`;
      document.getElementById("worstLessonsBox").innerHTML = byImpactDesc.slice(-3).reverse().map(lessonLine).join("") || `<span class="muted">Not enough usage data yet.</span>`;

      document.getElementById("lessonsTableBody").innerHTML = res.lessons.map(l => `
        <tr>
          <td>${esc(l.title)}</td>
          <td>${esc(l.category)}</td>
          <td>${esc(l.priority)}</td>
          <td><span class="pill pill-${l.status === 'active' ? 'completed' : 'pending'}">${esc(l.status)}</span></td>
          <td>${l.stats.times_used}</td>
          <td>${l.stats.trades_approved}</td>
          <td>${l.stats.trades_rejected}</td>
          <td>${l.estimated_impact_pct}%</td>
          <td>
            <button class="btn-ghost lesson-edit" data-id="${l.id}">Edit</button>
            <button class="btn-ghost lesson-toggle" data-id="${l.id}" data-status="${l.status}">${l.status === 'active' ? 'Disable' : 'Enable'}</button>
            <button class="btn-ghost lesson-dup" data-id="${l.id}">Duplicate</button>
            <button class="btn-ghost lesson-del" data-id="${l.id}">Delete</button>
          </td>
        </tr>`).join("") || `<tr><td colspan="9">No lessons yet -- create one above.</td></tr>`;

      document.querySelectorAll(".lesson-edit").forEach(btn => btn.onclick = async () => {
        const res = await apiGet(`/api/knowledge/lessons/${btn.dataset.id}`);
        editingId = btn.dataset.id;
        document.getElementById("formTitle").textContent = "Edit Lesson";
        document.getElementById("lTitle").value = res.title;
        document.getElementById("lCategory").value = res.category;
        document.getElementById("lDescription").value = res.description || "";
        document.getElementById("lPriority").value = res.priority;
        document.getElementById("lStatus").value = res.status;
        document.getElementById("lNotes").value = res.notes || "";
        document.getElementById("lApplyBT").checked = res.apply_backtesting;
        document.getElementById("lApplyPT").checked = res.apply_paper_trading;
        document.getElementById("lApplyEV").checked = res.apply_evolution;
        window.scrollTo(0, 0);
      });
      document.querySelectorAll(".lesson-toggle").forEach(btn => btn.onclick = async () => {
        const newStatus = btn.dataset.status === "active" ? "disabled" : "active";
        await apiPost(`/api/knowledge/lessons/${btn.dataset.id}/status`, { status: newStatus });
        loadLessons();
      });
      document.querySelectorAll(".lesson-dup").forEach(btn => btn.onclick = async () => {
        await apiPost(`/api/knowledge/lessons/${btn.dataset.id}/duplicate`, {});
        loadLessons();
      });
      document.querySelectorAll(".lesson-del").forEach(btn => btn.onclick = async () => {
        await apiSend("DELETE", `/api/knowledge/lessons/${btn.dataset.id}`);
        loadLessons();
      });
    }

    document.getElementById("lessonSearch").addEventListener("input", () => loadLessons());
    document.getElementById("lessonCategoryFilter").addEventListener("change", () => loadLessons());

    document.getElementById("btnClearForm").onclick = () => {
      editingId = null;
      document.getElementById("formTitle").textContent = "New Lesson";
      document.getElementById("lTitle").value = "";
      document.getElementById("lDescription").value = "";
      document.getElementById("lNotes").value = "";
      document.getElementById("lStatus").value = "active";
      document.getElementById("lPriority").value = "Medium";
      document.getElementById("lSaveStatus").textContent = "";
    };

    function collectLessonForm() {
      return {
        title: document.getElementById("lTitle").value,
        category: document.getElementById("lCategory").value,
        description: document.getElementById("lDescription").value,
        priority: document.getElementById("lPriority").value,
        status: document.getElementById("lStatus").value,
        notes: document.getElementById("lNotes").value,
        apply_backtesting: document.getElementById("lApplyBT").checked,
        apply_paper_trading: document.getElementById("lApplyPT").checked,
        apply_evolution: document.getElementById("lApplyEV").checked,
      };
    }

    async function saveLessonNow() {
      const body = collectLessonForm();
      if (!body.title.trim()) return;
      if (editingId) {
        await autosave("PUT", `/api/knowledge/lessons/${editingId}`, body);
      } else {
        if (creatingLesson) return;
        creatingLesson = true;
        try {
          const res = await autosave("POST", "/api/knowledge/lessons", body);
          editingId = res.id;
        } finally {
          creatingLesson = false;
        }
      }
      loadLessons();
      refreshKnowledgeStats();
    }

    // Auto Save: a draft is created on the first keystroke and every
    // field after that updates the same record (editingId), so typing
    // never creates duplicate lessons.
    const doAutosaveLesson = debounce(async () => {
      const status = document.getElementById("lSaveStatus");
      status.textContent = "Saving...";
      try {
        await saveLessonNow();
        status.textContent = "Saved";
      } catch (e) {
        status.textContent = "Save failed (will retry)";
      }
    }, 700);

    ["lTitle", "lCategory", "lDescription", "lPriority", "lStatus", "lNotes", "lApplyBT", "lApplyPT", "lApplyEV"]
      .forEach(id => {
        const el = document.getElementById(id);
        el.addEventListener("input", doAutosaveLesson);
        el.addEventListener("change", doAutosaveLesson);
      });

    document.getElementById("btnSaveLesson").onclick = async () => {
      if (!document.getElementById("lTitle").value.trim()) { alert("Title is required."); return; }
      await saveLessonNow();
      appendLog(`Lesson saved: ${document.getElementById("lTitle").value}`);
    };

    onLive((msg) => {
      if (msg.channel === "sync" && msg.entity === "lesson") {
        loadLessons();
        refreshKnowledgeStats();
      }
    });

    await loadLessons();
  }

  // ------------------------------------------------------------ KNOWLEDGE COMPILER
  function docTypePill(docType) {
    const cls = docType === "STRATEGY" || docType === "MIXED" ? "pill-completed" : "pill-pending";
    return `<span class="pill ${cls}">${esc(docType)}</span>`;
  }

  function statusPill(status) {
    const cls = status === "READY_FOR_BACKTEST" ? "pill-completed" : "pill-pending";
    return `<span class="pill ${cls}">${esc(status)}</span>`;
  }

  function renderCompiledResult(doc) {
    const sectionsList = (doc.sections || [])
      .map(s => `<span class="pill">${esc(s.heading || s.kind)}</span>`).join(" ") || `<span class="muted">No headers detected -- whole document treated as one body section.</span>`;

    const strategiesHtml = (doc.strategies || []).map(s => `
      <div class="card">
        <div><b>${esc(s.config.name)}</b> ${statusPill(s.status)} ${s.saved_strategy_id ? `<span class="muted">saved as ${esc(s.saved_strategy_id)}</span>` : ""}</div>
        <div class="muted">Entry conditions: ${s.config.entry_conditions.length} &nbsp;|&nbsp; Exit conditions: ${s.config.exit_conditions.length}
          &nbsp;|&nbsp; SL: ${esc(s.config.stop_loss.type)} &nbsp;|&nbsp; TP: ${esc(s.config.take_profit.type)} &nbsp;|&nbsp; Risk: ${s.config.risk_pct ?? "-"}%</div>
        ${s.resolved_defaults.length ? `<div><b>Auto-resolved defaults:</b><ul>${s.resolved_defaults.map(d => `<li>${esc(d)}</li>`).join("")}</ul></div>` : ""}
        ${s.clarification_notes.length ? `<div><b>Needs clarification:</b><ul>${s.clarification_notes.map(d => `<li>${esc(d)}</li>`).join("")}</ul></div>` : ""}
      </div>`).join("") || `<div class="muted">No executable strategy detected in this document.</div>`;

    const lessonsHtml = (doc.lessons || []).length ? `
      <div class="table-wrap"><table>
        <thead><tr><th>Title</th><th>Category</th><th>Kind</th><th>Status</th><th>Tags</th><th>Saved</th></tr></thead>
        <tbody>${doc.lessons.map(l => `
          <tr>
            <td>${esc(l.lesson.title)}</td>
            <td>${esc(l.lesson.category)}</td>
            <td>${esc(l.kind)}</td>
            <td><span class="pill pill-${l.lesson.status === 'active' ? 'completed' : 'pending'}">${esc(l.lesson.status)}</span></td>
            <td>${(l.lesson.tags || []).map(esc).join(", ")}</td>
            <td>${l.saved ? "New" : "Duplicate (existing)"}</td>
          </tr>`).join("")}</tbody>
      </table></div>` : `<div class="muted">No lessons extracted from this document.</div>`;

    return `
      <div class="card">
        <div><b>${esc(doc.title)}</b> ${docTypePill(doc.doc_type)} ${statusPill(doc.status)}
          <span class="muted">confidence ${Math.round(doc.classification_confidence * 100)}% &nbsp;|&nbsp; source: ${esc(doc.source_type)}</span></div>
        <div style="margin-top:8px;"><b>Sections detected:</b> ${sectionsList}</div>
        <div style="margin-top:8px;"><b>Concepts recognized:</b> ${(doc.concepts_used || []).map(c => `<span class="pill">${esc(c)}</span>`).join(" ") || `<span class="muted">None</span>`}</div>
      </div>
      <div class="section-title">Extracted Strategies</div>
      ${strategiesHtml}
      <div class="section-title">Extracted Lessons</div>
      ${lessonsHtml}
    `;
  }

  async function renderKnowledgeCompiler() {
    const myToken = activeRouteToken;
    content.innerHTML = `
      <div class="section-title">Knowledge Compiler</div>
      <div class="card">
        <div class="form-row"><label>Title (optional -- auto-detected from a leading "Title:"/"Strategy Name:" line if left blank)</label>
          <input id="kcTitle" placeholder="e.g. BOS Liquidity Sweep Strategy">
        </div>
        <div class="form-row"><label>Source (optional hint)</label>
          <select id="kcSource">
            <option value="">Auto-detect</option>
            <option value="youtube_transcript">YouTube Transcript</option>
            <option value="notebooklm">NotebookLM Report</option>
            <option value="chatgpt">ChatGPT Report</option>
            <option value="claude">Claude Report</option>
            <option value="pdf_text">PDF (converted to text)</option>
            <option value="book_notes">Book Notes</option>
            <option value="article">Article / Blog Post</option>
            <option value="journal">Trading Journal</option>
          </select>
        </div>
        <div class="form-row"><label>What kind of content is this? (helps SINDHU avoid guessing wrong)</label>
          <select id="kcContentType">
            <option value="mixed" selected>Mixed (both / not sure)</option>
            <option value="strategy">Strategy (entry/exit/risk rules)</option>
            <option value="lesson">Lesson (knowledge, psychology, notes -- no strategy)</option>
          </select>
        </div>
        <div class="form-row"><label>Paste strategy, lesson, transcript, report, or notes -- English, Roman Urdu, or mixed</label>
          <textarea id="kcText" style="min-height:260px;" placeholder="Paste anything: a strategy, a lesson, a YouTube transcript, a NotebookLM/ChatGPT/Claude report, book notes..."></textarea>
        </div>
        <div class="btn-row">
          <button class="btn" id="btnCompile">Compile</button>
          <span id="kcStatus" class="muted"></span>
        </div>
      </div>
      <div id="kcResult"></div>
      <div class="section-title">Recently Compiled Documents</div>
      <div class="table-wrap"><table>
        <thead><tr><th>Title</th><th>Type</th><th>Status</th><th>Strategies</th><th>Lessons</th><th>Compiled</th></tr></thead>
        <tbody id="kcHistoryBody"></tbody>
      </table></div>
    `;

    async function loadHistory() {
      const res = await apiGet("/api/knowledge-compiler/documents?limit=20").catch(() => ({ documents: [] }));
      if (isStaleRoute(myToken)) return;
      document.getElementById("kcHistoryBody").innerHTML = res.documents.map(d => `
        <tr>
          <td>${esc(d.title)}</td>
          <td>${docTypePill(d.doc_type)}</td>
          <td>${statusPill(d.status)}</td>
          <td>${(d.strategy_ids || []).length}</td>
          <td>${(d.lesson_ids || []).length}</td>
          <td>${timeAgo(d.created_at)}</td>
        </tr>`).join("") || `<tr><td colspan="6">No documents compiled yet.</td></tr>`;
    }

    document.getElementById("btnCompile").onclick = async () => {
      const text = document.getElementById("kcText").value;
      if (!text.trim()) { alert("Paste some text first."); return; }
      const status = document.getElementById("kcStatus");
      status.textContent = "Compiling...";
      try {
        const doc = await apiPost("/api/knowledge-compiler/compile", {
          text,
          title: document.getElementById("kcTitle").value || null,
          source_hint: document.getElementById("kcSource").value || null,
          content_type: document.getElementById("kcContentType").value,
        });
        if (isStaleRoute(myToken)) return;
        status.textContent = "Compiled.";
        document.getElementById("kcResult").innerHTML = renderCompiledResult(doc);
        loadHistory();
      } catch (e) {
        status.textContent = `Failed: ${e.message}`;
      }
    };

    await loadHistory();
  }

  // ------------------------------------------------------------ AI Integration Center
  function aiStatusPill(status) {
    const cls = status === "ok" ? "pill-completed" : status === "error" ? "pill-error" : "pill-muted";
    return `<span class="pill ${cls}">${esc(status || "not_configured")}</span>`;
  }

  function providerCard(p, activeProvider) {
    const isActive = activeProvider === p.name;
    return `
      <div class="card" data-provider="${p.name}">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <b style="text-transform:capitalize;">${esc(p.name)}</b>
          <span>
            ${aiStatusPill(p.last_test_status)}
            ${isActive ? '<span class="pill pill-completed">ACTIVE</span>' : ""}
          </span>
        </div>
        <div class="form-row" style="margin-top:10px;">
          <label>API Key ${p.has_api_key ? `(current: ${esc(p.api_key_masked)})` : "(not set)"}</label>
          <input type="password" class="ai-key" placeholder="Paste API key to set/replace">
        </div>
        <div class="form-row"><label>Model</label><input class="ai-model" value="${esc(p.model || "")}"></div>
        <div style="display:flex; gap:8px;">
          <div class="form-row" style="flex:1;"><label>Temperature</label><input class="ai-temperature" type="number" step="0.1" min="0" max="2" value="${p.temperature}"></div>
          <div class="form-row" style="flex:1;"><label>Max Tokens</label><input class="ai-max_tokens" type="number" value="${p.max_tokens}"></div>
        </div>
        <div style="display:flex; gap:8px;">
          <div class="form-row" style="flex:1;"><label>Timeout (s)</label><input class="ai-timeout" type="number" value="${p.timeout}"></div>
          <div class="form-row" style="flex:1;"><label>Retry Count</label><input class="ai-retry_count" type="number" value="${p.retry_count}"></div>
        </div>
        <div style="display:flex; gap:8px;">
          <div class="form-row" style="flex:1;"><label>Daily Quota</label><input class="ai-daily_quota" type="number" placeholder="unlimited" value="${p.daily_quota ?? ""}"></div>
          <div class="form-row" style="flex:1;"><label>Monthly Quota</label><input class="ai-monthly_quota" type="number" placeholder="unlimited" value="${p.monthly_quota ?? ""}"></div>
        </div>
        <div style="display:flex; gap:8px;">
          <div class="form-row" style="flex:1;"><label>Cost / 1K in ($)</label><input class="ai-cost_per_1k_input" type="number" step="0.001" value="${p.cost_per_1k_input ?? 0}"></div>
          <div class="form-row" style="flex:1;"><label>Cost / 1K out ($)</label><input class="ai-cost_per_1k_output" type="number" step="0.001" value="${p.cost_per_1k_output ?? 0}"></div>
        </div>
        <div class="btn-row">
          <button class="btn btn-ghost ai-save">Save</button>
          <button class="btn btn-ghost ai-test">Test Connection</button>
          <button class="btn btn-ghost ai-enable">${p.enabled ? "Disable" : "Enable"}</button>
          <button class="btn btn-ghost ai-activate" ${p.enabled ? "" : "disabled"}>${isActive ? "Deactivate" : "Set Active"}</button>
        </div>
        <div class="ai-test-result muted"></div>
      </div>`;
  }

  function queueStatusPill(status) {
    const cls = status === "completed" ? "pill-completed" : status === "failed" ? "pill-error"
      : status === "processing" ? "pill-running" : "pill-muted";
    return `<span class="pill ${cls}">${esc(status)}</span>`;
  }

  function importReportHtml(report) {
    const labels = {
      missing_rules: "Missing Rules", unknown_indicators: "Unknown Indicators",
      unknown_pattern: "Unknown Pattern", unknown_session: "Unknown Session",
      unknown_risk_rule: "Unknown Risk Rule", other: "Other Notes",
    };
    const nonEmpty = Object.entries(report || {}).filter(([, items]) => items && items.length);
    if (!nonEmpty.length) return `<div class="muted">No issues -- nothing needs clarification.</div>`;
    return nonEmpty.map(([key, items]) => `
      <div style="margin-top:6px;"><b>${labels[key] || key}:</b>
        <ul>${items.map(i => `<li>${esc(i)}</li>`).join("")}</ul>
      </div>`).join("");
  }

  async function renderAiCenter() {
    const myToken = activeRouteToken;
    content.innerHTML = `
      <div class="section-title">AI Integration Center</div>
      <div class="card">
        <div class="muted">AI is NOT part of the trading engine -- it is used ONCE, at import time, to directly understand
        and extract a complete strategy or lesson (entry/exit/stop-loss/take-profit/risk/confirmation rules, indicators,
        timeframes, sessions, psychology) with no manual rewriting. After import, SINDHU never needs AI again to run it.
        If AI is unavailable, disabled, or fails, SINDHU falls back to pure rule-based parsing and keeps working exactly
        as before -- nothing ever stops.</div>
      </div>

      <div class="section-title">AI Center Overview</div>
      <div id="aiDashboardGrid" class="grid"><div class="muted">Loading...</div></div>

      <div class="section-title">Providers</div>
      <div id="aiProviderGrid" class="grid" style="grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));"><div class="muted">Loading...</div></div>

      <div class="section-title">Import Document</div>
      <div class="card">
        <div class="form-row"><label>Title (optional)</label><input id="aiTitle" placeholder="e.g. BOS Liquidity Sweep Strategy"></div>
        <div class="form-row"><label>Source (optional hint)</label>
          <select id="aiSource">
            <option value="">Auto-detect</option>
            <option value="youtube_transcript">YouTube Transcript</option>
            <option value="notebooklm">NotebookLM Report</option>
            <option value="chatgpt">ChatGPT Report</option>
            <option value="claude">Claude Report</option>
            <option value="pdf_text">PDF</option>
            <option value="book_notes">Book Notes</option>
            <option value="article">Article / Blog Post</option>
            <option value="journal">Trading Journal</option>
          </select>
        </div>
        <div class="form-row"><label>What kind of content is this? (applies to text, file, and YouTube import below -- helps SINDHU avoid guessing wrong)</label>
          <select id="aiContentType">
            <option value="mixed" selected>Mixed (both / not sure)</option>
            <option value="strategy">Strategy (entry/exit/risk rules)</option>
            <option value="lesson">Lesson (knowledge, psychology, notes -- no strategy)</option>
          </select>
        </div>
        <div class="form-row"><label>Paste strategy, lesson, transcript, or report text</label>
          <textarea id="aiText" style="min-height:220px;" placeholder="Paste anything..."></textarea>
        </div>
        <div class="form-row"><label><input type="checkbox" id="aiUseAi" checked> Use AI assistance (falls back to rule-based automatically if unavailable)</label></div>
        <div class="btn-row">
          <button class="btn" id="btnAiImportText">Import Now</button>
          <button class="btn btn-ghost" id="btnAiQueueText">Add to Queue</button>
          <span id="aiTextStatus" class="muted"></span>
        </div>
        <div class="form-row" style="margin-top:10px;"><label>Or upload a file (PDF, DOCX, TXT, MD)</label>
          <input type="file" id="aiFile" accept=".pdf,.docx,.txt,.md,.csv,.xlsx">
        </div>
        <div class="btn-row">
          <button class="btn" id="btnAiImportFile">Import File</button>
          <span id="aiFileStatus" class="muted"></span>
        </div>
        <div class="form-row" style="margin-top:10px;"><label>Or paste a YouTube video link</label>
          <input id="aiYoutubeUrl" placeholder="https://www.youtube.com/watch?v=...">
        </div>
        <div class="btn-row">
          <button class="btn" id="btnAiImportYoutube">Import from YouTube</button>
          <button class="btn btn-ghost" id="btnAiQueueYoutube">Add to Queue</button>
          <span id="aiYoutubeStatus" class="muted"></span>
        </div>
      </div>
      <div id="aiImportResult"></div>

      <div class="section-title">Import Queue</div>
      <div class="card">
        <div class="btn-row">
          <button class="btn btn-ghost" id="btnAiRetryFailed">Retry Failed Imports</button>
          <button class="btn btn-ghost" id="btnAiRefreshQueue">Refresh</button>
          <span id="aiQueueStatus" class="muted"></span>
        </div>
        <div class="table-wrap"><table>
          <thead><tr><th>Title</th><th>Status</th><th>AI</th><th>Time</th><th>Queued</th><th></th></tr></thead>
          <tbody id="aiQueueBody"><tr><td colspan="6">Loading...</td></tr></tbody>
        </table></div>
      </div>

      <div class="section-title">Self-Building Dictionary</div>
      <div class="card">
        <div class="muted" style="margin-bottom:8px;">Terms SINDHU discovered on its own during imports (not part of the built-in dictionary) -- saved permanently, no AI needed to reuse them afterward.</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Term</th><th>Definition</th><th>Category</th><th>Aliases</th><th>Related Concepts</th><th>Discovered</th></tr></thead>
          <tbody id="aiDictionaryBody"><tr><td colspan="6">Loading...</td></tr></tbody>
        </table></div>
      </div>

      <div class="section-title">AI Center Settings</div>
      <div class="card">
        <div class="btn-row">
          <button class="btn btn-ghost" id="btnAiClearCache">Clear Cache</button>
          <span id="aiCacheStatus" class="muted"></span>
        </div>
        <div style="margin-top:10px;"><b>API Usage Monitor</b></div>
        <div class="table-wrap"><table>
          <thead><tr><th>Provider</th><th>Status</th><th>Today</th><th>This Month</th><th>Daily Left</th><th>Monthly Left</th><th>Avg Latency</th><th>Avg Tokens</th><th>Est. Cost</th><th>Last Used</th></tr></thead>
          <tbody id="aiUsageBody"><tr><td colspan="10">Loading...</td></tr></tbody>
        </table></div>
        <div style="margin-top:14px;"><b>Recent Logs</b></div>
        <div class="table-wrap"><table>
          <thead><tr><th>Provider</th><th>Endpoint</th><th>Status</th><th>Latency</th><th>Error</th><th>When</th></tr></thead>
          <tbody id="aiLogsBody"><tr><td colspan="6">Loading...</td></tr></tbody>
        </table></div>
      </div>
    `;

    async function loadProviders() {
      const res = await apiGet("/api/ai/providers").catch(() => ({ providers: [], active_provider: null }));
      if (isStaleRoute(myToken)) return;
      const grid = document.getElementById("aiProviderGrid");
      grid.innerHTML = res.providers.map(p => providerCard(p, res.active_provider)).join("");

      grid.querySelectorAll(".card").forEach(card => {
        const name = card.dataset.provider;
        const result = card.querySelector(".ai-test-result");

        card.querySelector(".ai-save").onclick = async () => {
          const dq = card.querySelector(".ai-daily_quota").value;
          const mq = card.querySelector(".ai-monthly_quota").value;
          const body = {
            model: card.querySelector(".ai-model").value || null,
            temperature: parseFloat(card.querySelector(".ai-temperature").value),
            max_tokens: parseInt(card.querySelector(".ai-max_tokens").value, 10),
            timeout: parseInt(card.querySelector(".ai-timeout").value, 10),
            retry_count: parseInt(card.querySelector(".ai-retry_count").value, 10),
            daily_quota: dq ? parseInt(dq, 10) : null,
            monthly_quota: mq ? parseInt(mq, 10) : null,
            cost_per_1k_input: parseFloat(card.querySelector(".ai-cost_per_1k_input").value) || 0,
            cost_per_1k_output: parseFloat(card.querySelector(".ai-cost_per_1k_output").value) || 0,
          };
          const key = card.querySelector(".ai-key").value;
          if (key) body.api_key = key;
          result.textContent = "Saving...";
          try {
            await apiPost(`/api/ai/providers/${name}/config`, body);
            result.textContent = "Saved.";
            loadProviders();
          } catch (e) { result.textContent = `Failed: ${e.message}`; }
        };

        card.querySelector(".ai-test").onclick = async () => {
          result.textContent = "Testing connection...";
          try {
            const r = await apiPost(`/api/ai/providers/${name}/test`);
            result.textContent = r.ok ? `Connected (${r.latency_ms}ms).` : `Failed: ${r.message}`;
            loadProviders();
          } catch (e) { result.textContent = `Failed: ${e.message}`; }
        };

        card.querySelector(".ai-enable").onclick = async () => {
          const endpoint = card.querySelector(".ai-enable").textContent === "Enable" ? "enable" : "disable";
          await apiPost(`/api/ai/providers/${name}/${endpoint}`).catch(() => {});
          loadProviders();
        };

        card.querySelector(".ai-activate").onclick = async () => {
          const isActive = card.querySelector(".ai-activate").textContent === "Deactivate";
          if (isActive) await apiPost("/api/ai/providers/deactivate").catch(() => {});
          else await apiPost(`/api/ai/providers/${name}/activate`).catch(() => {});
          loadProviders();
        };
      });
    }

    function qualityScoreHtml(q) {
      if (!q) return "";
      const hiddenRuleStat = q.hidden_rule_count
        ? `<div><div class="muted">Inferred Fields</div><div style="font-size:20px; font-weight:700;">${q.hidden_rule_count} <span class="muted" style="font-size:13px; font-weight:400;">(avg ${q.avg_hidden_rule_confidence_pct}% confidence)</span></div></div>`
        : "";
      return `
        <div class="card">
          <b>Knowledge Quality Score</b>
          <div style="display:flex; gap:18px; flex-wrap:wrap; margin-top:8px;">
            <div><div class="muted">Completeness</div><div style="font-size:20px; font-weight:700;">${q.completeness_pct}%</div></div>
            <div><div class="muted">Confidence</div><div style="font-size:20px; font-weight:700;">${q.confidence_pct}%</div></div>
            <div><div class="muted">Knowledge Score</div><div style="font-size:20px; font-weight:700;">${q.knowledge_score}</div></div>
            <div><div class="muted">Automation Ready</div>${q.automation_ready ? '<span class="pill pill-completed">YES</span>' : '<span class="pill pill-muted">NO</span>'}</div>
            <div><div class="muted">Backtesting Ready</div>${q.backtesting_ready ? '<span class="pill pill-completed">YES</span>' : '<span class="pill pill-muted">NO</span>'}</div>
            ${hiddenRuleStat}
          </div>
        </div>`;
    }

    function newDictionaryEntriesHtml(entries) {
      if (!entries || !entries.length) return "";
      return `
        <div class="card">
          <b>New Terms Discovered</b>
          <ul>${entries.map(e => `<li><b>${esc(e.canonical_name.toUpperCase())}</b> -- ${esc(e.definition)}</li>`).join("")}</ul>
        </div>`;
    }

    function hiddenRulesHtml(fields) {
      if (!fields || !fields.length) return "";
      return `
        <div class="card">
          <b>Inferred Fields</b>
          <div class="muted" style="margin-bottom:6px;">Strategy fields SINDHU completed from context rather than reading them explicitly -- each with its confidence and the evidence it was based on.</div>
          <div class="table-wrap"><table>
            <thead><tr><th>Field</th><th>Confidence</th><th>Reason</th><th>Evidence</th></tr></thead>
            <tbody>${fields.map(f => `
              <tr>
                <td>${esc(f.field)}</td>
                <td>${Math.round((f.confidence || 0) * 100)}%</td>
                <td>${esc(f.reason || "-")}</td>
                <td class="muted">${esc(f.evidence || "-")}</td>
              </tr>`).join("")}</tbody>
          </table></div>
        </div>`;
    }

    function psychologyNotesHtml(notes) {
      if (!notes || !notes.length) return "";
      return `
        <div class="card">
          <b>Psychology Notes</b>
          <ul>${notes.map(n => `<li>${esc(n)}</li>`).join("")}</ul>
        </div>`;
    }

    function showImportResult(result) {
      const confidencePct = result.quality_score ? result.quality_score.confidence_pct : null;
      const banner = result.ai_assisted
        ? `<div class="card"><span class="pill pill-completed">AI-NATIVE EXTRACTION</span> Directly extracted by <b>${esc(result.ai_provider)}</b>${confidencePct != null ? ` at ${confidencePct}% confidence` : ""} -- no rule-based re-parsing was used.</div>`
        : `<div class="card"><span class="pill pill-muted">RULE-BASED (Offline Mode)</span> ${result.ai_error ? `AI was unavailable (${esc(result.ai_error)}) -- used pure rule-based parsing.` : "Parsed with pure rule-based extraction."}</div>`;
      const scoreHtml = qualityScoreHtml(result.quality_score);
      const dictHtml = newDictionaryEntriesHtml(result.new_dictionary_entries);
      const hiddenHtml = hiddenRulesHtml(result.hidden_rules);
      const psychHtml = psychologyNotesHtml(result.psychology_notes);
      // v8: once a strategy/lesson has actually cleared the acceptance bar
      // (status READY_FOR_BACKTEST), never show the categorized "Missing/
      // Unknown" report -- that framing is reserved for the genuine
      // low-confidence clarification case. A confirmation banner replaces it.
      const isReady = result.document && result.document.status === "READY_FOR_BACKTEST";
      const reportHtml = isReady
        ? `<div class="card"><span class="pill pill-completed">AUTOMATION READY</span> <span class="pill pill-completed">BACKTESTING READY</span> Nothing further needed -- SINDHU understood this document completely.</div>`
        : `<div class="card"><b>Import Report</b>${importReportHtml(result.import_report)}</div>`;
      const docHtml = result.document ? renderCompiledResult(result.document) : `<div class="card muted">Import failed: ${esc(result.error || "unknown error")}</div>`;
      document.getElementById("aiImportResult").innerHTML = banner + scoreHtml + hiddenHtml + psychHtml + dictHtml + reportHtml + docHtml;
    }

    document.getElementById("btnAiImportText").onclick = async () => {
      const text = document.getElementById("aiText").value;
      if (!text.trim()) { alert("Paste some text first."); return; }
      const status = document.getElementById("aiTextStatus");
      status.textContent = "Importing...";
      try {
        const result = await apiPost("/api/ai/import", {
          text,
          title: document.getElementById("aiTitle").value || null,
          source_hint: document.getElementById("aiSource").value || null,
          use_ai: document.getElementById("aiUseAi").checked,
          content_type: document.getElementById("aiContentType").value,
        });
        if (isStaleRoute(myToken)) return;
        status.textContent = "Imported.";
        showImportResult(result);
        loadUsageAndLogs();
      } catch (e) { status.textContent = `Failed: ${e.message}`; }
    };

    document.getElementById("btnAiQueueText").onclick = async () => {
      const text = document.getElementById("aiText").value;
      if (!text.trim()) { alert("Paste some text first."); return; }
      const status = document.getElementById("aiTextStatus");
      status.textContent = "Queuing...";
      try {
        await apiPost("/api/ai/import/queue", {
          items: [{
            text,
            title: document.getElementById("aiTitle").value || null,
            source_hint: document.getElementById("aiSource").value || null,
            use_ai: document.getElementById("aiUseAi").checked,
            content_type: document.getElementById("aiContentType").value,
          }],
        });
        if (isStaleRoute(myToken)) return;
        status.textContent = "Queued.";
        loadQueue();
      } catch (e) { status.textContent = `Failed: ${e.message}`; }
    };

    document.getElementById("btnAiImportFile").onclick = async () => {
      const fileInput = document.getElementById("aiFile");
      if (!fileInput.files.length) { alert("Choose a file first."); return; }
      const status = document.getElementById("aiFileStatus");
      status.textContent = "Uploading...";
      const fd = new FormData();
      fd.append("file", fileInput.files[0]);
      if (document.getElementById("aiTitle").value) fd.append("title", document.getElementById("aiTitle").value);
      fd.append("use_ai", document.getElementById("aiUseAi").checked);
      fd.append("content_type", document.getElementById("aiContentType").value);
      try {
        const result = await apiUpload("/api/ai/import/upload", fd);
        if (isStaleRoute(myToken)) return;
        status.textContent = "Imported.";
        showImportResult(result);
        loadUsageAndLogs();
      } catch (e) { status.textContent = `Failed: ${e.message}`; }
    };

    document.getElementById("btnAiImportYoutube").onclick = async () => {
      const url = document.getElementById("aiYoutubeUrl").value;
      if (!url.trim()) { alert("Paste a YouTube link first."); return; }
      const status = document.getElementById("aiYoutubeStatus");
      status.textContent = "Fetching transcript and importing...";
      try {
        const result = await apiPost("/api/ai/import/youtube", {
          url,
          title: document.getElementById("aiTitle").value || null,
          use_ai: document.getElementById("aiUseAi").checked,
          content_type: document.getElementById("aiContentType").value,
        });
        if (isStaleRoute(myToken)) return;
        status.textContent = "Imported.";
        showImportResult(result);
        loadUsageAndLogs();
      } catch (e) { status.textContent = `Failed: ${e.message}`; }
    };

    document.getElementById("btnAiQueueYoutube").onclick = async () => {
      const url = document.getElementById("aiYoutubeUrl").value;
      if (!url.trim()) { alert("Paste a YouTube link first."); return; }
      const status = document.getElementById("aiYoutubeStatus");
      status.textContent = "Queuing...";
      try {
        await apiPost("/api/ai/import/queue", {
          items: [{
            text: url,
            title: document.getElementById("aiTitle").value || null,
            use_ai: document.getElementById("aiUseAi").checked,
            input_kind: "youtube",
            content_type: document.getElementById("aiContentType").value,
          }],
        });
        if (isStaleRoute(myToken)) return;
        status.textContent = "Queued.";
        loadQueue();
      } catch (e) { status.textContent = `Failed: ${e.message}`; }
    };

    document.getElementById("btnAiClearCache").onclick = async () => {
      const status = document.getElementById("aiCacheStatus");
      status.textContent = "Clearing...";
      try {
        await apiPost("/api/ai/cache/clear");
        status.textContent = "Cache cleared.";
      } catch (e) { status.textContent = `Failed: ${e.message}`; }
    };

    async function loadUsageAndLogs() {
      const [usage, logs] = await Promise.all([
        apiGet("/api/ai/usage").catch(() => ({ summary: [] })),
        apiGet("/api/ai/logs?limit=50").catch(() => ({ logs: [] })),
      ]);
      if (isStaleRoute(myToken)) return;
      document.getElementById("aiUsageBody").innerHTML = usage.summary.map(s => `
        <tr>
          <td style="text-transform:capitalize;">${esc(s.provider)}</td>
          <td><span class="pill ${s.provider_status === 'enabled' ? 'pill-completed' : 'pill-muted'}">${esc(s.provider_status)}</span></td>
          <td>${fmtNum(s.daily_requests)}</td>
          <td>${fmtNum(s.monthly_requests)}</td>
          <td>${s.daily_remaining == null ? "-" : fmtNum(s.daily_remaining)}</td>
          <td>${s.monthly_remaining == null ? "-" : fmtNum(s.monthly_remaining)}</td>
          <td>${s.avg_latency_ms ? Math.round(s.avg_latency_ms) + "ms" : "-"}</td>
          <td>${s.avg_tokens ? fmtNum(s.avg_tokens) : "-"}</td>
          <td>$${(s.estimated_cost || 0).toFixed(4)}</td>
          <td>${timeAgo(s.last_used_at)}</td>
        </tr>`).join("") || `<tr><td colspan="10">No AI calls yet.</td></tr>`;
      document.getElementById("aiLogsBody").innerHTML = logs.logs.map(l => `
        <tr>
          <td style="text-transform:capitalize;">${esc(l.provider)}</td>
          <td>${esc(l.endpoint)}</td>
          <td><span class="pill ${l.status === 'success' ? 'pill-completed' : 'pill-error'}">${esc(l.status)}</span></td>
          <td>${l.latency_ms != null ? l.latency_ms + "ms" : "-"}</td>
          <td>${esc(l.error_message || "-")}</td>
          <td>${timeAgo(l.created_at)}</td>
        </tr>`).join("") || `<tr><td colspan="6">No log entries yet.</td></tr>`;
    }

    async function loadDashboard() {
      const d = await apiGet("/api/ai/dashboard").catch(() => null);
      if (!d || isStaleRoute(myToken)) return;
      const cards = [
        ["Total Strategies", d.total_strategies], ["Total Lessons", d.total_lessons],
        ["Dictionary Size", d.dictionary_size], ["Patterns", d.pattern_count],
        ["Indicators", d.indicator_count], ["Success Rate", d.success_rate_pct != null ? d.success_rate_pct + "%" : "-"],
        ["Failed Imports", d.failed_imports], ["Total AI Calls", d.total_ai_calls],
        ["Inferred Fields", d.total_hidden_rules_detected || 0],
      ];
      document.getElementById("aiDashboardGrid").innerHTML = cards.map(([label, value]) => `
        <div class="card"><div class="label">${esc(label)}</div><div class="value">${esc(value)}</div></div>
      `).join("");
    }

    async function loadQueue() {
      const res = await apiGet("/api/ai/import/queue?limit=50").catch(() => ({ items: [] }));
      if (isStaleRoute(myToken)) return;
      document.getElementById("aiQueueBody").innerHTML = res.items.map(it => `
        <tr>
          <td>${esc(it.title || "Untitled")}</td>
          <td>${queueStatusPill(it.status)}</td>
          <td>${it.ai_assisted ? `<span class="pill pill-completed">${esc(it.ai_provider || "AI")}</span>` : '<span class="pill pill-muted">rule-based</span>'}</td>
          <td>${it.processing_time_ms != null ? it.processing_time_ms + "ms" : "-"}</td>
          <td>${timeAgo(it.created_at)}</td>
          <td>${it.status === "failed" ? `<button class="btn btn-ghost queue-retry" data-id="${it.id}">Retry</button>` : ""}</td>
        </tr>`).join("") || `<tr><td colspan="6">Queue is empty.</td></tr>`;
      document.querySelectorAll(".queue-retry").forEach(btn => {
        btn.onclick = async () => {
          await apiPost(`/api/ai/import/queue/${btn.dataset.id}/retry`).catch(() => {});
          loadQueue();
        };
      });
    }

    document.getElementById("btnAiRetryFailed").onclick = async () => {
      const status = document.getElementById("aiQueueStatus");
      status.textContent = "Retrying...";
      try {
        const r = await apiPost("/api/ai/import/queue/retry-failed");
        status.textContent = `Re-queued ${r.retried} item(s).`;
        loadQueue();
      } catch (e) { status.textContent = `Failed: ${e.message}`; }
    };
    document.getElementById("btnAiRefreshQueue").onclick = loadQueue;

    async function loadDictionary() {
      const res = await apiGet("/api/ai/dictionary").catch(() => ({ entries: [] }));
      if (isStaleRoute(myToken)) return;
      document.getElementById("aiDictionaryBody").innerHTML = res.entries.map(e => `
        <tr>
          <td><b>${esc(e.canonical_name.toUpperCase())}</b>${e.usage_notes ? `<div class="muted" style="font-size:12px;">${esc(e.usage_notes)}</div>` : ""}</td>
          <td>${esc(e.definition || "-")}</td>
          <td>${esc(e.category || "-")}</td>
          <td>${(e.aliases || []).map(esc).join(", ") || "-"}</td>
          <td>${(e.related_concepts || []).map(esc).join(", ") || "-"}</td>
          <td>${timeAgo(e.created_at)}</td>
        </tr>`).join("") || `<tr><td colspan="6">No self-discovered terms yet.</td></tr>`;
    }

    await Promise.all([loadProviders(), loadUsageAndLogs(), loadDashboard(), loadQueue(), loadDictionary()]);
  }

  // ------------------------------------------------------------ SINDHU CEO (control room)
  // Every card's summary and every control in its expanded view calls the
  // exact same REST endpoints the module's own dedicated page already
  // uses -- this is a new way to reach existing functionality (a single
  // in-place command center), not a reimplementation of any backend logic.
  const CEO_MODULES = [
    "home", "feature_control", "market", "data", "strategies", "clarification_center", "knowledge", "knowledge_compiler",
    "ai_center", "backtesting", "backtest_history", "pipeline_history", "paper_trading", "challenge_mode",
    "evolution", "sindhu_strategy", "web_sourced_strategies", "external_signals", "reports", "settings",
  ];
  const CEO_LABELS = {
    home: "Dashboard", feature_control: "Control Center",
    market: "Market", data: "Data", strategies: "Strategies",
    clarification_center: "Clarification",
    knowledge: "Knowledge", knowledge_compiler: "Knowledge Compiler", ai_center: "AI Center",
    backtesting: "Backtesting", backtest_history: "Backtest History",
    pipeline_history: "Pipeline History",
    paper_trading: "Paper Trading", challenge_mode: "Challenge Mode", evolution: "Evolution", sindhu_strategy: "SINDHU Strategy",
    web_sourced_strategies: "Web-Sourced Strategies", external_signals: "External Signal Tracker",
    reports: "Reports", settings: "Settings",
  };
  const FEATURE_CATEGORY_ORDER = ["Risk & Safety", "Self-Learning", "Signals", "Other"];

  // Shared between the standalone "Control Center" page (its real,
  // dedicated sidebar home -- Navigation Reorganization) and the SINDHU
  // CEO page's own card (which now just links there instead of keeping a
  // second, separate implementation) -- one body-renderer + one set of
  // toggle handlers, reused by both, so there is exactly one place this
  // logic lives.
  function featureControlBodyHtml(fc) {
    const byCategory = {};
    fc.features.forEach(f => { (byCategory[f.category] = byCategory[f.category] || []).push(f); });
    return `
      <div class="card" style="display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:16px;">
        <div>
          <b>Pause All Automation</b>
          <div class="muted" style="font-size:12px;">Safely turns off every automated feature below at once. Paper Trading keeps running and no data is lost -- flip it back on any time.</div>
        </div>
        <label class="switch">
          <input type="checkbox" id="fcMasterPause" ${fc.master_pause_all ? "checked" : ""}>
          <span class="slider"></span>
        </label>
      </div>
      ${FEATURE_CATEGORY_ORDER.filter(cat => byCategory[cat]).map(cat => `
        <div class="section-title">${esc(cat)}</div>
        <div class="card" style="margin-bottom:16px;">
          ${byCategory[cat].map(f => `
            <div class="ceo-task-row" data-feature-row="${esc(f.id)}" style="opacity:${fc.master_pause_all ? 0.55 : 1};">
              <div class="ceo-task-info">
                <div class="ceo-task-title">${esc(f.name)}${f.auto_manual ? ` <span class="muted" style="font-size:11px;">(AUTO/MANUAL)</span>` : ""}</div>
                <div class="ceo-task-sub">${esc(f.description)}</div>
                <div class="muted" style="font-size:11.5px;margin-top:2px;">${esc(f.name)} -- ${f.enabled ? "ON" : "OFF"} -- ${esc(f.status || "")}</div>
              </div>
              <label class="switch">
                <input type="checkbox" class="fc-toggle" data-feature-id="${esc(f.id)}" ${f.enabled ? "checked" : ""} ${fc.master_pause_all ? "disabled" : ""}>
                <span class="slider"></span>
              </label>
            </div>`).join("")}
        </div>`).join("")}
    `;
  }

  function wireFeatureControlHandlers(refresh) {
    document.getElementById("fcMasterPause").onchange = async (e) => {
      await apiPost("/api/feature-control/master-pause", { enabled: e.target.checked });
      refresh();
    };
    content.querySelectorAll(".fc-toggle").forEach(el => {
      el.onchange = async (e) => {
        await apiPost("/api/feature-control/toggle", { feature_id: el.dataset.featureId, enabled: e.target.checked });
        refresh();
      };
    });
  }

  // ------------------------------------------------------------ CONTROL CENTER (dedicated page)
  // Previously only reachable as one card inside the SINDHU CEO grid --
  // Navigation Audit (see conversation) flagged this as the single
  // clearest "hard to find" item on the whole dashboard, since it's the
  // one place that controls every automated feature at once. Now a real,
  // first-class sidebar page.
  async function renderControlCenter() {
    const myToken = activeRouteToken;
    async function render() {
      const fc = await apiGet("/api/feature-control/state").catch(() => ({ master_pause_all: false, features: [] }));
      if (isStaleRoute(myToken)) return;
      content.innerHTML = `
        <div class="section-title">Control Center</div>
        <p class="muted" style="margin-top:-10px;">Every automated background feature, in one place -- turn any one off, or pause all of them at once, without touching Paper Trading itself.</p>
        ${featureControlBodyHtml(fc)}`;
      wireFeatureControlHandlers(render);
    }
    await render();
  }

  function statusDot(level) {
    // level: "active" (green, pulsing) | "attention" (amber) | "idle" (grey)
    return `<span class="status-dot status-${level}"></span>`;
  }

  async function renderCEO() {
    const myToken = activeRouteToken;
    let expandedId = null;          // null = grid view
    let ceoPendingRunStrategyId = null; // set by Strategies "Run" -> read by Backtesting expand

    async function fetchAll() {
      const [home, market, data, strategies, knowledgeReport, lessons, kcDocs, aiDash,
             history, paperStatus, paperPositions, paperAnalytics, bestWorst, settings, jobsRes,
             pipelineHistoryRes, evolutionStatus, evolutionChampions, evolutionStrategies,
             sindhuDailyLog, sindhuCandidates, featureControl, clarificationAll, challenge,
             externalSignalsComparison] = await Promise.all([
        apiGet("/api/home").catch(() => null),
        apiGet("/api/market").catch(() => ({ coins: [], exchange: "-" })),
        apiGet("/api/data").catch(() => ({ coins: [], total_coins: 0, missing_data: [] })),
        apiGet("/api/backtesting/strategies").catch(() => ({ strategies: [] })),
        apiGet("/api/knowledge/report").catch(() => ({})),
        apiGet("/api/knowledge/lessons").catch(() => ({ lessons: [] })),
        apiGet("/api/knowledge-compiler/documents").catch(() => ({ documents: [] })),
        apiGet("/api/ai/dashboard").catch(() => ({})),
        apiGet("/api/backtest-history?limit=20").catch(() => ({ batches: [] })),
        apiGet("/api/paper-trading/status").catch(() => ({ running: false })),
        apiGet("/api/paper-trading/positions").catch(() => ({ positions: [] })),
        apiGet("/api/paper-trading/analytics?period=all").catch(() => null),
        apiGet("/api/reports/best-worst/strategies").catch(() => ({ ranking: [] })),
        apiGet("/api/settings").catch(() => ({})),
        apiGet("/api/jobs").catch(() => ({ jobs: [] })),
        apiGet("/api/automation/pipeline-history?limit=20").catch(() => ({ runs: [] })),
        apiGet("/api/evolution/status").catch(() => ({ running: false, governor: {} })),
        apiGet("/api/evolution/champions").catch(() => ({ champions: [] })),
        apiGet("/api/evolution/strategies").catch(() => ({ strategies: [] })),
        apiGet("/api/sindhu-strategy/daily-log").catch(() => ({ candidates_generated: 0, ai_calls_used: 0 })),
        apiGet("/api/sindhu-strategy/candidates").catch(() => ({ candidates: [] })),
        apiGet("/api/feature-control/state").catch(() => ({ master_pause_all: false, features: [] })),
        apiGet("/api/backtesting/clarification/all").catch(() => ({ groups: [], total_issues: 0, strategy_count: 0 })),
        apiGet("/api/paper-trading/challenge").catch(() => ({ configured: false })),
        apiGet("/api/external-signals/comparison").then(r => r.channels || []).catch(() => []),
      ]);
      return {
        home, market, data, strategies: strategies.strategies || [],
        knowledgeReport, lessons: lessons.lessons || [], kcDocs: kcDocs.documents || [],
        aiDash, history: history.batches || [], paperStatus, paperPositions: paperPositions.positions || [],
        paperAnalytics, bestWorst, settings, jobs: jobsRes.jobs || [],
        pipelineRuns: pipelineHistoryRes.runs || [],
        evolutionStatus, evolutionChampions: evolutionChampions.champions || [],
        evolutionStrategies: evolutionStrategies.strategies || [],
        sindhuDailyLog, sindhuCandidates: sindhuCandidates.candidates || [],
        featureControl, clarificationAll, challenge, externalSignalsComparison,
      };
    }

    function runningJobOf(jobs, kind) { return jobs.find(j => j.kind === kind && j.status === "running"); }

    function cardSummary(id, d) {
      const jobs = d.jobs;
      switch (id) {
        case "home": {
          const anyRunning = jobs.some(j => j.status === "running") || (d.paperStatus && d.paperStatus.running);
          return {
            level: anyRunning ? "active" : "idle",
            text: d.home
              ? `${fmtNum(d.home.total_coins)} coins, ${fmtNum(d.home.total_candles)} candles -- CPU ${d.home.cpu_percent}%, RAM ${d.home.ram_percent}%`
              : "Could not load.",
          };
        }
        case "clarification_center": {
          const ca = d.clarificationAll || { total_issues: 0, strategy_count: 0 };
          return {
            level: ca.total_issues ? "attention" : "idle",
            text: ca.total_issues
              ? `${ca.total_issues} question(s) waiting across ${ca.strategy_count} strategy(ies)`
              : "Nothing waiting -- all strategies clear.",
          };
        }
        case "feature_control": {
          const fc = d.featureControl || { master_pause_all: false, features: [] };
          const onCount = fc.features.filter(f => f.enabled).length;
          return {
            level: fc.master_pause_all ? "attention" : "idle",
            text: fc.master_pause_all
              ? "All automation PAUSED"
              : `${onCount}/${fc.features.length} automated feature(s) ON`,
          };
        }
        case "market":
          return { level: "idle", text: `${d.market.coins.length} coins tracked on ${esc(d.market.exchange || "-")}` };
        case "data": {
          const dl = runningJobOf(jobs, "download");
          const missing = d.data.missing_data || [];
          const level = dl ? "active" : missing.length ? "attention" : "idle";
          const text = dl
            ? `Syncing -- ${dl.progress.done || 0}/${dl.progress.total || d.data.total_coins} coins (${esc(dl.progress.current_coin || "")})`
            : missing.length
              ? `${missing.length}/${d.data.total_coins} coin(s) have no data yet`
              : `${d.data.total_coins} coins synced`;
          return { level, text, progressPct: dl && dl.progress.total ? (dl.progress.done / dl.progress.total * 100) : null };
        }
        case "strategies": {
          const needsClar = d.strategies.filter(s => s.status !== "READY_FOR_BACKTEST").length;
          return {
            level: needsClar ? "attention" : "idle",
            text: `${d.strategies.length} saved${needsClar ? `, ${needsClar} need clarification` : ""}`,
          };
        }
        case "knowledge": {
          const active = d.lessons.filter(l => l.status === "active").length;
          return {
            level: "idle",
            text: `${d.lessons.length} lessons (${active} active) -- knowledge score ${d.knowledgeReport.knowledge_score ?? "-"}%`,
          };
        }
        case "knowledge_compiler":
          return { level: "idle", text: `${d.kcDocs.length} document(s) compiled` };
        case "ai_center": {
          const pending = d.aiDash.pending_imports || 0;
          const learned = d.aiDash.learned_correction_patterns || 0;
          return {
            level: pending ? "active" : (d.aiDash.failed_imports ? "attention" : "idle"),
            text: `${d.aiDash.total_strategies ?? 0} strategies, ${d.aiDash.total_lessons ?? 0} lessons imported${pending ? `, ${pending} pending` : ""}`
              + (learned ? ` -- ${learned} question type(s) auto-answered from learned patterns` : ""),
          };
        }
        case "backtesting": {
          const bt = runningJobOf(jobs, "backtest") || runningJobOf(jobs, "pipeline");
          return {
            level: bt ? "active" : "idle",
            text: bt
              ? `${esc(bt.progress.current_strategy || "Running")} -- ${bt.progress.done || 0}/${bt.progress.total || "?"} coins`
              : "No backtest running",
            progressPct: bt && bt.progress.total ? (bt.progress.done / bt.progress.total * 100) : null,
          };
        }
        case "backtest_history": {
          const best = d.history.slice().sort((a, b) => (b.avg_profit_pct || -Infinity) - (a.avg_profit_pct || -Infinity))[0];
          return {
            level: "idle",
            text: `${d.history.length} completed batch(es)${best ? ` -- best: ${esc(best.strategy)} (${best.avg_profit_pct}%)` : ""}`,
          };
        }
        case "pipeline_history": {
          const runs = d.pipelineRuns;
          const running = runs.find(r => r.status === "running");
          return {
            level: running ? "active" : "idle",
            text: running
              ? `Running: ${esc(running.strategy_name)} (${esc(running.stage)})`
              : `${runs.length} run(s) recorded${runs.length ? ` -- most recent: ${esc(runs[0].strategy_name)} (${esc(runs[0].status)})` : ""}`,
          };
        }
        case "paper_trading": {
          const s = d.paperStatus;
          const a = d.paperAnalytics && d.paperAnalytics.summary;
          return {
            level: s.running ? "active" : "idle",
            text: s.running
              ? `Balance $${Number(s.balance).toFixed(2)}, ${s.open_trades} open, ${a ? `${a.active_strategies} strategies, ${a.win_rate.toFixed(1)}% win rate all-time` : ""}`
              : "Engine stopped",
          };
        }
        case "challenge_mode": {
          const c = d.challenge;
          if (!c || !c.configured) return { level: "idle", text: "No challenge set -- tracking/analysis only, never touches trading behavior" };
          const drifted = c.drift && c.drift.checked && c.drift.drifted;
          return {
            level: drifted ? "attention" : (c.ahead_of_pace ? "active" : "idle"),
            text: drifted
              ? `⚠️ Drift detected on ${c.scope_strategy_id || "combo"}/${c.scope_symbol || ""}`
              : `${c.progress_pct.toFixed(1)}% progress -- $${c.current_amount.toFixed(2)} of $${c.target_amount.toFixed(2)} -- ${c.ahead_of_pace ? "ahead of pace" : "behind pace"}`,
          };
        }
        case "external_signals": {
          const rows = d.externalSignalsComparison || [];
          if (!rows.length) return { level: "idle", text: "No channels added yet -- completely separate from your own Paper Trading" };
          const eligible = rows.filter(r => r.is_proven_sample_size && r.total_pnl > 0).length;
          const totalTrades = rows.reduce((s, r) => s + (r.closed_trades || 0), 0);
          return {
            level: eligible ? "active" : "idle",
            text: `${rows.length} channel(s) tracked, ${totalTrades} closed trades so far${eligible ? `, ${eligible} eligible for forwarding` : ""}`,
          };
        }
        case "evolution": {
          const running = d.evolutionStatus.running;
          const champ = d.evolutionChampions.find(c => c.category === "strategy");
          return {
            level: running ? "active" : "idle",
            text: running
              ? `Running -- ${d.evolutionStrategies.length} BOT strategies${champ ? `, champion: ${esc(String(champ.value))}` : ""}`
              : `Stopped -- ${d.evolutionStrategies.length} BOT strategies tracked`,
          };
        }
        case "sindhu_strategy": {
          const log = d.sindhuDailyLog;
          return {
            level: log.candidates_generated >= 11 ? "idle" : "attention",
            text: `${log.candidates_generated || 0}/11 candidates today (AI used: ${log.ai_calls_used ? "yes" : "no"}) -- ${d.sindhuCandidates.length} total ever`,
          };
        }
        case "reports":
          return {
            level: "idle",
            text: d.bestWorst.best_strategy
              ? `Best: ${esc(d.bestWorst.best_strategy)} -- Worst: ${esc(d.bestWorst.worst_strategy || "-")}`
              : "No completed backtests yet",
          };
        case "settings":
          return { level: "idle", text: `${esc(d.settings.exchange || "-")} -- ${d.settings.num_coins ?? "-"} coins -- ${esc(d.settings.theme || "-")} theme` };
        default:
          return { level: "idle", text: "" };
      }
    }

    function allTasksList(d) {
      const tasks = d.jobs.filter(j => j.status === "running").map(j => ({
        kind: "job", id: j.id, jobKind: j.kind,
        title: `${j.kind === "backtest" ? "Backtest" : j.kind === "download" ? "Data Download" : j.kind === "pipeline" ? "Automation Pipeline" : j.kind}`,
        sub: [
          j.progress.current_strategy, j.progress.current_coin,
          j.progress.total != null ? `${j.progress.done || 0}/${j.progress.total}` : null,
          j.progress.stage_label || j.progress.stage,
        ].filter(Boolean).join(" -- ") || "Running...",
        pct: j.progress.total ? (j.progress.done / j.progress.total * 100) : (j.progress.bar_pct || null),
      }));
      if (d.paperStatus && d.paperStatus.running) {
        tasks.push({
          kind: "paper", id: "paper_trading", jobKind: "paper_trading",
          title: "Paper Trading Engine",
          sub: `Balance $${Number(d.paperStatus.balance).toFixed(2)} -- tick #${d.paperStatus.tick_count} -- ${d.paperStatus.open_trades} open`,
          pct: null,
        });
      }
      return tasks;
    }

    // ------------------------------------------------------------ grid
    function moduleCardHtml(id, d) {
      const s = cardSummary(id, d);
      return `
        <div class="ceo-card" data-ceo-card="${id}">
          <div class="ceo-card-head">
            <div class="ceo-card-title">${esc(CEO_LABELS[id])}</div>
            ${statusDot(s.level)}
          </div>
          <div class="ceo-card-summary">${s.text}</div>
          ${s.progressPct != null ? `<div class="progress-bar"><div class="progress-bar-fill" style="width:${s.progressPct}%"></div></div>` : ""}
        </div>`;
    }

    function tasksCardHtml(d) {
      const tasks = allTasksList(d);
      return `
        <div class="ceo-card ceo-card-tasks" data-ceo-card="all_tasks">
          <div class="ceo-card-head">
            <div class="ceo-card-title">⚡ All Tasks</div>
            ${statusDot(tasks.length ? "active" : "idle")}
          </div>
          <div class="ceo-card-summary">${tasks.length ? `${tasks.length} task(s) running right now` : "Nothing running -- all quiet"}</div>
        </div>`;
    }

    // A showGrid() triggered by a debounced live-update or the 15s
    // autoRefresh can still be awaiting its fetchAll() when the user clicks
    // a card to expand it -- without this guard, that stale grid render
    // lands right after the expand and silently clobbers it back to the
    // grid, so the click looks like it "didn't work." showGridSeq is bumped
    // by showExpanded() below so any in-flight or pending showGrid() knows
    // it's been superseded and skips its own render.
    let showGridSeq = 0;
    async function showGrid() {
      const mySeq = ++showGridSeq;
      expandedId = null;
      const d = await fetchAll();
      if (isStaleRoute(myToken) || mySeq !== showGridSeq) return;
      content.innerHTML = `
        <div class="section-title">SINDHU CEO -- Control Room</div>
        <div class="muted" style="margin:-10px 0 16px;font-size:12.5px;">Every module in one place. Click any card to monitor and control it without leaving this page.</div>
        <div class="ceo-grid">
          ${tasksCardHtml(d)}
          ${CEO_MODULES.map(id => moduleCardHtml(id, d)).join("")}
        </div>`;
      // Cards for pages that are ALREADY their own real top-level page
      // (not an in-CEO "expand" panel) just link straight there, instead
      // of duplicating a second implementation inside this file.
      const CEO_DIRECT_LINK_CARDS = { feature_control: "control_center", web_sourced_strategies: "web_sourced_strategies", clarification_center: "clarification_center", challenge_mode: "paper_trading" };
      document.querySelectorAll("[data-ceo-card]").forEach(el => {
        const directTarget = CEO_DIRECT_LINK_CARDS[el.dataset.ceoCard];
        el.onclick = () => directTarget ? (location.hash = `#${directTarget}`) : showExpanded(el.dataset.ceoCard);
      });
    }

    // ------------------------------------------------------------ expanded views
    function expandedShell(title, bodyHtml) {
      content.innerHTML = `
        <div class="ceo-expanded-head">
          <h2>${esc(title)}</h2>
          <button class="ceo-close-btn" id="ceoClose" title="Back to CEO grid">&times;</button>
        </div>
        ${bodyHtml}`;
      document.getElementById("ceoClose").onclick = () => showGrid();
    }

    async function showExpanded(id) {
      showGridSeq++; // supersede any pending/in-flight showGrid() so it can't clobber this expand
      if (refreshTimer) { clearTimeout(refreshTimer); refreshTimer = null; }
      expandedId = id;
      try {
        if (id === "all_tasks") return await expandAllTasks();
        if (id === "home") return await expandHome();
        if (id === "market") return await expandMarket();
        if (id === "data") return await expandData();
        if (id === "strategies") return await expandStrategies();
        if (id === "knowledge") return await expandKnowledge();
        if (id === "knowledge_compiler") return await expandKnowledgeCompiler();
        if (id === "ai_center") return await expandAiCenter();
        if (id === "backtesting" || id === "backtest_history") return await expandBacktesting(id);
        if (id === "pipeline_history") return await expandPipelineHistory();
        if (id === "paper_trading") return await expandPaperTrading();
        if (id === "evolution") return await expandEvolution();
        if (id === "sindhu_strategy") return await expandSindhuStrategy();
        if (id === "reports") return await expandReports();
        if (id === "settings") return await expandSettings();
      } catch (e) {
        expandedShell(CEO_LABELS[id] || id, `<div class="card">Failed to load: ${esc(e.message)}</div>`);
      }
    }

    // ---- All Tasks
    async function expandAllTasks() {
      const d = await fetchAll();
      if (isStaleRoute(myToken)) return;
      const tasks = allTasksList(d);
      expandedShell("⚡ All Tasks -- every background job, in one place", `
        <div class="card">
          ${tasks.length ? tasks.map(t => `
            <div class="ceo-task-row" data-task-id="${esc(t.id)}" data-task-kind="${t.kind}">
              <div class="ceo-task-info">
                <div class="ceo-task-title">${esc(t.title)}</div>
                <div class="ceo-task-sub">${esc(t.sub)}</div>
              </div>
              ${t.pct != null ? `<div class="progress-bar"><div class="progress-bar-fill" style="width:${t.pct}%"></div></div>` : ""}
              <div class="btn-row" style="width:auto;">
                ${t.kind === "job" ? `
                  <button class="btn-ghost ceo-task-pause" data-id="${t.id}">Pause</button>
                  <button class="btn-ghost ceo-task-resume" data-id="${t.id}">Resume</button>
                  <button class="btn-ghost ceo-task-stop" data-id="${t.id}">Stop</button>
                ` : `
                  <button class="btn-ghost ceo-task-stop-paper">Stop</button>
                `}
              </div>
            </div>`).join("") : `<div class="muted">Nothing running right now.</div>`}
        </div>`);
      content.querySelectorAll(".ceo-task-pause").forEach(b => b.onclick = async () => { await apiPost(`/api/jobs/${b.dataset.id}/pause`); expandAllTasks(); });
      content.querySelectorAll(".ceo-task-resume").forEach(b => b.onclick = async () => { await apiPost(`/api/jobs/${b.dataset.id}/resume`); expandAllTasks(); });
      content.querySelectorAll(".ceo-task-stop").forEach(b => b.onclick = async () => { await apiPost(`/api/jobs/${b.dataset.id}/stop`); expandAllTasks(); });
      const stopPaperBtn = content.querySelector(".ceo-task-stop-paper");
      if (stopPaperBtn) stopPaperBtn.onclick = async () => { await apiPost("/api/paper-trading/stop").catch(() => {}); expandAllTasks(); };
    }

    // ---- Dashboard
    async function expandHome() {
      const d = await fetchAll();
      if (isStaleRoute(myToken)) return;
      const h = d.home;
      expandedShell("Dashboard", !h ? `<div class="card">Could not load.</div>` : `
        <div class="grid">
          ${card("CPU Usage", `${h.cpu_percent}%`)}
          ${card("RAM Usage", `${h.ram_percent}%`)}
          ${card("Disk Usage", fmtBytes(h.disk_usage_bytes))}
          ${card("Database Size", fmtBytes(h.database_size_bytes))}
          ${card("Total Coins", fmtNum(h.total_coins))}
          ${card("Total Candles", fmtNum(h.total_candles))}
          ${card("Knowledge Score", `${h.knowledge_score}%`)}
          ${card("Exchange", esc(h.exchange))}
        </div>
        <div class="section-title">Quick Actions</div>
        <div class="btn-row">
          <button class="btn-ghost" id="ceoStart">Start Download</button>
          <button class="btn-ghost" id="ceoPause">Pause Current Task</button>
          <button class="btn-ghost" id="ceoStop">Stop Current Task</button>
          <button class="btn-ghost" id="ceoBackup">Backup Now</button>
          <button class="btn-ghost" id="ceoRestart">Restart Services</button>
          <span id="ceoHomeStatus" class="muted"></span>
        </div>`);
      if (!h) return;
      const status = document.getElementById("ceoHomeStatus");
      document.getElementById("ceoStart").onclick = async () => { await apiPost("/api/data/download"); status.textContent = "Download started."; };
      document.getElementById("ceoPause").onclick = async () => { if (h.current_task) { await apiPost(`/api/jobs/${h.current_task.id}/pause`); status.textContent = "Paused."; } };
      document.getElementById("ceoStop").onclick = async () => { if (h.current_task) { await apiPost(`/api/jobs/${h.current_task.id}/stop`); status.textContent = "Stopped."; } };
      document.getElementById("ceoBackup").onclick = async () => { await apiPost("/api/backup/create"); status.textContent = "Backup created."; };
      document.getElementById("ceoRestart").onclick = async () => { await apiPost("/api/system/restart-services"); status.textContent = "Services soft-restarted."; };
    }

    // ---- Market
    async function expandMarket() {
      const d = await fetchAll();
      if (isStaleRoute(myToken)) return;
      const signalCls = s => s === "Bullish" ? "pill-bullish" : s === "Bearish" ? "pill-bearish" : "pill-neutral";
      expandedShell("Market", `
        <div class="table-wrap"><table>
          <thead><tr><th>Coin</th><th>Price</th><th>Change</th><th>Signal</th><th>Volatility</th></tr></thead>
          <tbody>${d.market.coins.map(c => `
            <tr>
              <td>${esc(c.symbol)}</td><td>${c.price}</td>
              <td class="${c.change_pct >= 0 ? 'pill-up' : 'pill-down'}">${c.change_pct.toFixed(2)}%</td>
              <td><span class="pill ${signalCls(c.signal)}">${esc(c.signal)}</span></td>
              <td>${c.volatility_pct != null ? c.volatility_pct + "%" : "-"}</td>
            </tr>`).join("") || '<tr><td colspan="5">No market data yet.</td></tr>'}</tbody>
        </table></div>`);
    }

    // ---- Data
    async function expandData() {
      const d = await fetchAll();
      if (isStaleRoute(myToken)) return;
      expandedShell("Data", `
        <div class="grid">
          ${card("Downloaded Coins", fmtNum(d.data.total_coins))}
          ${card("Database Size", fmtBytes(d.data.database_size_bytes))}
          ${card("Missing Data", d.data.missing_data.length ? d.data.missing_data.join(", ") : "None")}
        </div>
        <div class="btn-row"><button class="btn" id="ceoDlBtn">Start / Resume Download</button><span id="ceoDlStatus" class="muted"></span></div>
        <div class="table-wrap"><table>
          <thead><tr><th>Coin</th><th>Candles</th><th>Status</th></tr></thead>
          <tbody>${d.data.coins.map(c => `<tr><td>${esc(c.symbol)}</td><td>${fmtNum(c.candles)}</td><td><span class="pill pill-${c.status}">${esc(c.status)}</span></td></tr>`).join("")}</tbody>
        </table></div>`);
      document.getElementById("ceoDlBtn").onclick = async () => {
        await apiPost("/api/data/download");
        document.getElementById("ceoDlStatus").textContent = "Download started.";
      };
    }

    // ---- Strategies (reuses the exact same clarification flow: openClarifyBox/issueControlHtml)
    // A batch's stored status can say "running" long after the process
    // that was running it has died (crash, kill, interrupted server
    // restart) -- backtest_batches has no heartbeat, so a stuck batch looks
    // identical to a genuinely active one unless we cross-check against
    // job_manager's live job list (the one source of truth for "is
    // something actually happening right now"). One backtest/pipeline job
    // runs at a time system-wide, matched here by strategy name (the only
    // identifier progress carries), so this match is unambiguous.
    function ceoLastBacktestCell(r, runningJob) {
      if (!r) return `<span class="muted">Never run</span>`;
      if (r.status === "running") {
        if (runningJob) {
          const p = runningJob.progress || {};
          const coinInfo = p.total != null ? ` (${p.done}/${p.total} coins)` : "";
          return `<span class="pill pill-running">Running now${coinInfo}${p.current_coin ? ` -- ${esc(p.current_coin)}` : ""}</span>`;
        }
        return `<span class="pill pill-error" title="Batch ${esc(r.batch_id)} is marked running but no active job is processing it -- it was interrupted (crash/restart) and never finished.">Interrupted -- never finished</span>`;
      }
      if (r.status !== "completed") return `<span class="pill pill-pending">${esc(r.status)}</span>`;
      const pnlCls = r.avg_profit_pct > 0 ? "positive" : r.avg_profit_pct < 0 ? "negative" : "";
      return `${fmtNum(r.total_trades)} trades, ${r.win_rate}% win, <span class="${pnlCls}">${r.avg_profit_pct}%</span>`;
    }

    async function expandStrategies() {
      const d = await fetchAll();
      if (isStaleRoute(myToken)) return;
      const runningBacktestJob = d.jobs.find(j => (j.kind === "backtest" || j.kind === "pipeline") && j.status === "running");
      const rows = d.strategies.map(s => {
        const matchingJob = runningBacktestJob && runningBacktestJob.progress
          && runningBacktestJob.progress.current_strategy === s.name ? runningBacktestJob : null;
        return `
        <tr data-strat-row="${s.id}">
          <td class="ceo-strat-name">${esc(s.name)}</td>
          <td>${strategyStatusPill(s.status)}</td>
          <td>${ceoLastBacktestCell(s.last_batch_result, matchingJob)}</td>
          <td>
            <button class="btn-ghost ceo-strat-rename" data-id="${s.id}" data-name="${esc(s.name)}">Rename</button>
            <button class="btn-ghost ceo-strat-run" data-id="${s.id}" data-name="${esc(s.name)}">Run</button>
            ${s.status !== "READY_FOR_BACKTEST" ? `<button class="btn-ghost ceo-strat-clarify" data-id="${s.id}" data-name="${esc(s.name)}">Clarify</button>` : ""}
            <button class="btn-ghost ceo-strat-del" data-id="${s.id}" data-name="${esc(s.name)}">Delete</button>
          </td>
        </tr>`;
      }).join("");
      expandedShell("Strategies", `
        <div class="table-wrap"><table>
          <thead><tr><th>Name</th><th>Status</th><th>Last Backtest</th><th></th></tr></thead>
          <tbody>${rows || '<tr><td colspan="4">No saved strategies yet.</td></tr>'}</tbody>
        </table></div>
        <div id="clarifyBox" style="display:none;margin-top:16px;">
          <div class="section-title" id="clarifyTitle">Clarification Needed</div>
          <div id="clarifyBody"></div>
        </div>`);

      content.querySelectorAll(".ceo-strat-rename").forEach(btn => btn.onclick = async () => {
        const row = content.querySelector(`[data-strat-row="${btn.dataset.id}"] .ceo-strat-name`);
        const newName = prompt("New name for this strategy:", btn.dataset.name);
        if (!newName || !newName.trim() || newName === btn.dataset.name) return;
        const full = await apiGet(`/api/backtesting/strategies/${btn.dataset.id}`);
        full.config.name = newName.trim();
        await apiPost("/api/backtesting/strategies", { config: full.config, strategy_id: btn.dataset.id });
        row.textContent = newName.trim();
        btn.dataset.name = newName.trim();
      });
      content.querySelectorAll(".ceo-strat-run").forEach(btn => btn.onclick = async () => {
        if (!confirm(`Run a full backtest for "${btn.dataset.name}" across all coins now?`)) return;
        try {
          await apiPost("/api/backtesting/run", { strategy_id: btn.dataset.id, all_coins: true, lang: getLang() });
          ceoPendingRunStrategyId = btn.dataset.id;
          showExpanded("backtesting");
        } catch (e) { alert(`Could not start: ${e.message}`); }
      });
      content.querySelectorAll(".ceo-strat-del").forEach(btn => btn.onclick = async () => {
        if (!confirm(`Delete strategy "${btn.dataset.name}"? This cannot be undone.`)) return;
        await apiSend("DELETE", `/api/backtesting/strategies/${btn.dataset.id}`);
        expandStrategies();
      });
      content.querySelectorAll(".ceo-strat-clarify").forEach(btn => btn.onclick = () => {
        openClarifyBox(btn.dataset.id, btn.dataset.name, () => expandStrategies());
      });
    }

    // ---- Knowledge (Lessons)
    async function expandKnowledge() {
      const d = await fetchAll();
      if (isStaleRoute(myToken)) return;
      const rows = d.lessons.map(l => `
        <tr data-lesson-row="${l.id}">
          <td class="ceo-lesson-title">${esc(l.title)}</td>
          <td>${esc(l.category)}</td>
          <td><span class="pill pill-${l.status === 'active' ? 'completed' : 'pending'}">${esc(l.status)}</span></td>
          <td>
            <button class="btn-ghost ceo-lesson-rename" data-id="${l.id}" data-title="${esc(l.title)}">Rename</button>
            <button class="btn-ghost ceo-lesson-del" data-id="${l.id}" data-title="${esc(l.title)}">Delete</button>
          </td>
        </tr>`).join("");
      expandedShell("Knowledge -- Lessons", `
        <div class="grid">${card("Knowledge Score", `${d.knowledgeReport.knowledge_score ?? "-"}%`)}${card("Total Lessons", fmtNum(d.lessons.length))}</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Title</th><th>Category</th><th>Status</th><th></th></tr></thead>
          <tbody>${rows || '<tr><td colspan="4">No lessons yet.</td></tr>'}</tbody>
        </table></div>`);
      content.querySelectorAll(".ceo-lesson-rename").forEach(btn => btn.onclick = async () => {
        const newTitle = prompt("New title for this lesson:", btn.dataset.title);
        if (!newTitle || !newTitle.trim() || newTitle === btn.dataset.title) return;
        const full = await apiGet(`/api/knowledge/lessons/${btn.dataset.id}`);
        await apiSend("PUT", `/api/knowledge/lessons/${btn.dataset.id}`, {
          title: newTitle.trim(), category: full.category, description: full.description,
          priority: full.priority, notes: full.notes, status: full.status,
          apply_backtesting: full.apply_backtesting, apply_paper_trading: full.apply_paper_trading,
          apply_evolution: full.apply_evolution,
        });
        expandKnowledge();
      });
      content.querySelectorAll(".ceo-lesson-del").forEach(btn => btn.onclick = async () => {
        if (!confirm(`Delete lesson "${btn.dataset.title}"? This cannot be undone.`)) return;
        await apiSend("DELETE", `/api/knowledge/lessons/${btn.dataset.id}`);
        expandKnowledge();
      });
    }

    // ---- Knowledge Compiler
    async function expandKnowledgeCompiler() {
      const d = await fetchAll();
      if (isStaleRoute(myToken)) return;
      expandedShell("Knowledge Compiler", `
        <div class="card">
          <div class="form-row"><label>Paste text to compile</label><textarea id="ceoKcText" style="min-height:140px;" placeholder="Paste strategy/lesson text..."></textarea></div>
          <div class="form-row"><label>Content type</label>
            <select id="ceoKcType"><option value="mixed" selected>Mixed</option><option value="strategy">Strategy</option><option value="lesson">Lesson</option></select>
          </div>
          <div class="btn-row"><button class="btn" id="ceoKcCompile">Compile</button><span id="ceoKcStatus" class="muted"></span></div>
        </div>
        <div class="section-title">Compiled Documents</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Title</th><th>Type</th><th>Status</th><th>Compiled</th></tr></thead>
          <tbody>${d.kcDocs.map(doc => `
            <tr><td>${esc(doc.title)}</td><td>${esc(doc.doc_type)}</td>
            <td><span class="pill pill-${doc.status === 'READY_FOR_BACKTEST' ? 'completed' : 'pending'}">${esc(doc.status)}</span></td>
            <td>${timeAgo(doc.created_at)}</td></tr>`).join("") || '<tr><td colspan="4">No documents compiled yet.</td></tr>'}</tbody>
        </table></div>`);
      document.getElementById("ceoKcCompile").onclick = async () => {
        const text = document.getElementById("ceoKcText").value;
        if (!text.trim()) { alert("Paste some text first."); return; }
        const status = document.getElementById("ceoKcStatus");
        status.textContent = "Compiling...";
        try {
          await apiPost("/api/knowledge-compiler/compile", { text, content_type: document.getElementById("ceoKcType").value });
          status.textContent = "Compiled.";
          expandKnowledgeCompiler();
        } catch (e) { status.textContent = `Failed: ${e.message}`; }
      };
    }

    // ---- AI Center
    async function expandAiCenter() {
      const d = await fetchAll();
      if (isStaleRoute(myToken)) return;
      expandedShell("AI Center", `
        <div class="grid">
          ${card("Strategies Imported", fmtNum(d.aiDash.total_strategies))}
          ${card("Lessons Imported", fmtNum(d.aiDash.total_lessons))}
          ${card("Pending Imports", fmtNum(d.aiDash.pending_imports))}
          ${card("Failed Imports", fmtNum(d.aiDash.failed_imports))}
        </div>
        <div class="card">
          <div class="form-row"><label>What kind of content is this?</label>
            <select id="ceoAiType"><option value="mixed" selected>Mixed (not sure)</option><option value="strategy">Strategy</option><option value="lesson">Lesson</option></select>
          </div>
          <div class="form-row"><label>Paste strategy, lesson, transcript, or report text</label>
            <textarea id="ceoAiText" style="min-height:200px;" placeholder="Paste anything..."></textarea>
          </div>
          <div class="btn-row"><button class="btn" id="ceoAiImport">Import Now</button><span id="ceoAiStatus" class="muted"></span></div>
          <div id="ceoAiResult"></div>
        </div>`);
      document.getElementById("ceoAiImport").onclick = async () => {
        const text = document.getElementById("ceoAiText").value;
        if (!text.trim()) { alert("Paste some text first."); return; }
        const status = document.getElementById("ceoAiStatus");
        status.textContent = "Importing -- this runs the full pipeline (import -> auto-backtest -> optimizer -> re-backtest -> compare -> paper trading)...";
        try {
          const result = await apiPost("/api/ai/import", {
            text, use_ai: true, content_type: document.getElementById("ceoAiType").value,
          });
          status.textContent = "Imported.";
          const doc = result.document;
          const savedStrategies = doc ? doc.strategies.filter(s => s.saved_strategy_id).length : 0;
          const savedLessons = doc ? doc.lessons.filter(l => l.saved).length : 0;
          document.getElementById("ceoAiResult").innerHTML = `
            <div class="card">
              <span class="pill ${result.ai_assisted ? 'pill-completed' : 'pill-muted'}">${result.ai_assisted ? `AI-assisted (${esc(result.ai_provider)})` : "Rule-based"}</span>
              Saved ${savedStrategies} strategy(ies), ${savedLessons} lesson(s).
              ${doc && doc.status === "READY_FOR_BACKTEST" ? `<div style="margin-top:8px;"><span class="pill pill-completed">READY FOR BACKTEST</span> The automation pipeline was triggered automatically -- check the Backtesting or All Tasks card.</div>` : ""}
            </div>`;
        } catch (e) { status.textContent = `Failed: ${e.message}`; }
      };
    }

    // ---- Backtesting + Backtest History (combined, per Part 4.2)
    async function expandBacktesting(focusId) {
      const d = await fetchAll();
      if (isStaleRoute(myToken)) return;
      const job = runningJobOf(d.jobs, "backtest") || runningJobOf(d.jobs, "pipeline");
      const readyToRun = ceoPendingRunStrategyId
        ? d.strategies.find(s => s.id === ceoPendingRunStrategyId) : null;
      const latestBatch = d.history[0]; // most recently completed batch, if any

      expandedShell(focusId === "backtest_history" ? "Backtest History" : "Backtesting", `
        ${readyToRun && !job ? `
        <div class="card">
          Ready to run: <b>${esc(readyToRun.name)}</b>
          <div class="btn-row" style="margin-top:8px;">
            <button class="btn" id="ceoRunNow">Run Now (all coins)</button>
            <button class="btn-ghost" id="ceoRunCancel">Cancel</button>
          </div>
        </div>` : ""}
        <div class="section-title">Live Status</div>
        ${job ? `
        <div class="grid">
          ${card("Strategy", esc(job.progress.current_strategy || "-"))}
          ${card("Coin", esc(job.progress.current_coin || "-"))}
          ${card("Stage", esc(job.progress.stage_label || job.progress.current_stage || job.progress.stage || "-"))}
          ${card("Coins Progress", job.progress.total != null ? `${job.progress.done}/${job.progress.total}` : "-")}
        </div>
        <div class="progress-bar"><div class="progress-bar-fill" style="width:${job.progress.total ? (job.progress.done / job.progress.total * 100) : 0}%"></div></div>
        <div class="btn-row" style="margin-top:10px;">
          <button class="btn-ghost" id="ceoBtPause">Pause</button>
          <button class="btn-ghost" id="ceoBtResume">Resume</button>
          <button class="btn-ghost" id="ceoBtStop">Stop</button>
        </div>
        <div class="section-title">Live Log</div>
        <div class="card" id="ceoBtLog" style="height:180px;overflow-y:auto;font-family:Consolas,monospace;font-size:12px;white-space:pre-wrap;"></div>
        ` : `<div class="card muted">No backtest or pipeline running right now.</div>`}

        <div id="ceoZeroTradeBox"></div>

        <div class="section-title">Auto-Optimizer: Original vs Optimized</div>
        <div id="ceoOptComparisonBox">${job
          ? `<div class="card muted">A run is in progress -- the comparison will appear here once it finishes (or check the last completed run below).</div>`
          : `<div class="muted">Loading comparison...</div>`}</div>

        <div class="section-title">Recent Results</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Strategy</th><th>Trades</th><th>Win Rate</th><th>Profit %</th><th>When</th></tr></thead>
          <tbody>${d.history.slice(0, 15).map(b => `
            <tr><td>${esc(b.display_name || b.strategy)}</td><td>${fmtNum(b.total_trades)}</td><td>${b.win_rate}%</td>
            <td class="${b.avg_profit_pct > 0 ? 'positive' : b.avg_profit_pct < 0 ? 'negative' : ''}">${b.avg_profit_pct}%</td>
            <td>${timeAgo(b.created_at)}</td></tr>`).join("") || '<tr><td colspan="5">No completed backtests yet.</td></tr>'}</tbody>
        </table></div>`);

      // Same shared endpoint + renderer as Backtest History (see
      // comparisonBoxHtml/loadComparisonBox) -- per the standing CEO-parity
      // rule, this can never show different numbers than that page.
      if (!job && latestBatch) {
        loadComparisonBox(document.getElementById("ceoOptComparisonBox"), latestBatch.batch_id).catch(console.error);
        loadZeroTradeBox(document.getElementById("ceoZeroTradeBox"), latestBatch.batch_id).catch(console.error);
      } else if (!job) {
        document.getElementById("ceoOptComparisonBox").innerHTML = `<div class="card muted">No completed backtests yet.</div>`;
      }

      if (readyToRun && !job) {
        document.getElementById("ceoRunNow").onclick = async () => {
          try {
            await apiPost("/api/backtesting/run", { strategy_id: readyToRun.id, all_coins: true, lang: getLang() });
            expandBacktesting(focusId);
          } catch (e) { alert(`Could not start: ${e.message}`); }
        };
        document.getElementById("ceoRunCancel").onclick = () => { ceoPendingRunStrategyId = null; expandBacktesting(focusId); };
      }
      if (job) {
        document.getElementById("ceoBtPause").onclick = async () => { await apiPost(`/api/jobs/${job.id}/pause`); };
        document.getElementById("ceoBtResume").onclick = async () => { await apiPost(`/api/jobs/${job.id}/resume`); };
        document.getElementById("ceoBtStop").onclick = async () => { await apiPost(`/api/jobs/${job.id}/stop`); expandBacktesting(focusId); };
      }
    }

    // ---- Paper Trading
    async function expandPaperTrading() {
      const d = await fetchAll();
      if (isStaleRoute(myToken)) return;
      const s = d.paperStatus;
      expandedShell("Paper Trading", `
        <div class="grid">
          ${cardClass("Engine Status", s.running ? "<span class=\"pill pill-completed\">Running</span>" : "<span class=\"pill pill-muted\">Stopped</span>", "")}
          ${card("Balance", `$${Number(s.balance).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}`)}
          ${card("Open Trades", fmtNum(s.open_trades))}
          ${card("Queue", fmtNum(s.queue))}
        </div>
        <div class="btn-row">
          <button class="btn" id="ceoPtStart" ${s.running ? "disabled" : ""}>Start Engine</button>
          <button class="btn-ghost" id="ceoPtStop" ${s.running ? "" : "disabled"}>Stop Engine</button>
          <span id="ceoPtStatus" class="muted"></span>
        </div>
        <div class="section-title">Open Positions</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Coin</th><th>Direction</th><th>Entry</th><th>Size</th><th>Strategy</th></tr></thead>
          <tbody>${d.paperPositions.map(p => `
            <tr><td>${esc(p.symbol)}</td><td><span class="pill ${p.direction === 'long' ? 'pill-bullish' : 'pill-bearish'}">${esc(p.direction)}</span></td>
            <td>${p.entry_price}</td><td>${p.size.toFixed(4)}</td><td>${esc(p.strategy_name || "-")}</td></tr>`).join("") || '<tr><td colspan="5">No open positions.</td></tr>'}</tbody>
        </table></div>

        <div class="section-title">Analytics</div>
        <div id="ceoPtAnalyticsBox"></div>`);
      document.getElementById("ceoPtStart").onclick = async () => {
        try { await apiPost("/api/paper-trading/start"); expandPaperTrading(); }
        catch (e) { document.getElementById("ceoPtStatus").textContent = `Failed: ${e.message}`; }
      };
      document.getElementById("ceoPtStop").onclick = async () => {
        try { await apiPost("/api/paper-trading/stop"); expandPaperTrading(); }
        catch (e) { document.getElementById("ceoPtStatus").textContent = `Failed: ${e.message}`; }
      };
      // Same shared endpoint + renderer as the standalone Paper Trading
      // page (see loadPaperAnalytics/paperAnalyticsSectionHtml) -- per the
      // standing CEO-parity rule, so this view can never disagree with it.
      loadPaperAnalytics("ceoPtAnalyticsBox", "ceoPt", "today");
    }

    // ---- Evolution Engine (same /api/evolution/* endpoints as the
    // standalone Evolution page, per the standing CEO-parity rule)
    async function expandEvolution() {
      const d = await fetchAll();
      if (isStaleRoute(myToken)) return;
      const s = d.evolutionStatus;
      const gov = s.governor || {};
      const champions = d.evolutionChampions;
      const championRow = (label, cat) => {
        const c = champions.find(x => x.category === cat);
        return `<tr><td>${label}</td><td>${c ? esc(String(c.value)) : "-"}</td><td>${c ? Number(c.score).toFixed(2) : "-"}</td></tr>`;
      };
      expandedShell("Evolution Engine", `
        <div class="grid">
          ${cardClass("Status", s.running ? "<span class=\"pill pill-completed\">Running</span>" : "<span class=\"pill pill-muted\">Stopped</span>", "")}
          ${card("CPU / RAM", `${(gov.cpu_percent ?? 0).toFixed ? gov.cpu_percent.toFixed(1) : gov.cpu_percent}% / ${(gov.ram_percent ?? 0).toFixed ? gov.ram_percent.toFixed(1) : gov.ram_percent}%`)}
          ${card("BOT Strategies", fmtNum(d.evolutionStrategies.length))}
        </div>
        <div class="btn-row">
          <button class="btn" id="ceoEvoStart" ${s.running ? "disabled" : ""}>Start Engine</button>
          <button class="btn-ghost" id="ceoEvoStop" ${s.running ? "" : "disabled"}>Stop Engine</button>
          <button class="btn-ghost" id="ceoEvoRunTick">Run One Tick Now</button>
          <span id="ceoEvoStatus" class="muted"></span>
        </div>
        <div class="section-title">Champion Engine</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Category</th><th>Champion</th><th>Score</th></tr></thead>
          <tbody>
            ${championRow("Strategy", "strategy")}${championRow("Lesson", "lesson")}${championRow("Coin", "coin")}
            ${championRow("Session", "session")}${championRow("Timeframe", "timeframe")}${championRow("Market Condition", "market_condition")}
          </tbody>
        </table></div>
        <p class="muted">Full generation history, self-generated lessons, and DNA correlations are on the dedicated Evolution page.</p>`);
      document.getElementById("ceoEvoStart").onclick = async () => {
        try { await apiPost("/api/evolution/start"); expandEvolution(); }
        catch (e) { document.getElementById("ceoEvoStatus").textContent = `Failed: ${e.message}`; }
      };
      document.getElementById("ceoEvoStop").onclick = async () => {
        try { await apiPost("/api/evolution/stop"); expandEvolution(); }
        catch (e) { document.getElementById("ceoEvoStatus").textContent = `Failed: ${e.message}`; }
      };
      document.getElementById("ceoEvoRunTick").onclick = async () => {
        document.getElementById("ceoEvoStatus").textContent = "Running one tick...";
        try { await apiPost("/api/evolution/run-tick"); expandEvolution(); }
        catch (e) { document.getElementById("ceoEvoStatus").textContent = `Failed: ${e.message}`; }
      };
    }

    // ---- SINDHU Strategy Generator (same /api/sindhu-strategy/* endpoints
    // as the standalone page, per the standing CEO-parity rule)
    async function expandSindhuStrategy() {
      const d = await fetchAll();
      if (isStaleRoute(myToken)) return;
      const log = d.sindhuDailyLog;
      const candidates = d.sindhuCandidates.slice().sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
      expandedShell("SINDHU Strategy", `
        <div class="grid">
          ${card("Candidates Today", `${fmtNum(log.candidates_generated)} / 11`)}
          ${cardClass("AI Call Used Today", log.ai_calls_used ? "<span class=\"pill pill-bullish\">Yes (1/1)</span>" : "<span class=\"pill pill-muted\">Not yet (0/1)</span>", "")}
          ${card("Total Candidates", fmtNum(d.sindhuCandidates.length))}
        </div>
        <div class="btn-row">
          <button class="btn" id="ceoSstratGenerate">Generate Today's Candidates Now</button>
          <span id="ceoSstratStatus" class="muted"></span>
        </div>
        <div class="table-wrap"><table>
          <thead><tr><th>Name</th><th>Label</th><th>Evolution Score</th></tr></thead>
          <tbody>${candidates.slice(0, 20).map(c => `
            <tr>
              <td>${esc(c.name)}</td>
              <td><span class="pill ${c.made_with_ai ? "pill-bullish" : "pill-muted"}">${c.made_with_ai ? "Made with AI" : "Made without AI"}</span></td>
              <td>${c.evolution_score != null ? Number(c.evolution_score).toFixed(2) : "not backtested yet"}</td>
            </tr>`).join("") || '<tr><td colspan="3">No candidates yet.</td></tr>'}</tbody>
        </table></div>`);
      document.getElementById("ceoSstratGenerate").onclick = async () => {
        document.getElementById("ceoSstratStatus").textContent = "Generating...";
        try {
          const res = await apiPost("/api/sindhu-strategy/generate", {}, 180000);
          document.getElementById("ceoSstratStatus").textContent = `Created ${res.count} candidate(s).`;
          expandSindhuStrategy();
        } catch (e) { document.getElementById("ceoSstratStatus").textContent = `Failed: ${e.message}`; }
      };
    }

    // ---- Automation Pipeline History
    async function expandPipelineHistory() {
      const d = await fetchAll();
      if (isStaleRoute(myToken)) return;
      const list = d.pipelineRuns;
      expandedShell("Pipeline History", `
        <p class="muted">Every automation run, permanently -- same pipeline_jobs data used for crash-recovery resume.</p>
        <div class="table-wrap"><table>
          <thead><tr><th>Started</th><th>Strategy</th><th>Status</th><th></th></tr></thead>
          <tbody>${list.map(r => `
            <tr>
              <td>${esc((r.created_at || "").slice(0, 19))}</td>
              <td>${esc(r.strategy_name || r.strategy_id)}</td>
              <td>${pipelineStatusBadge(r)}</td>
              <td><button class="btn-ghost ceo-pph-view" data-id="${esc(r.job_id)}">View</button></td>
            </tr>`).join("") || '<tr><td colspan="4">No automation pipeline runs yet.</td></tr>'}</tbody>
        </table></div>
        <div id="ceoPphDetail"></div>`);
      document.querySelectorAll(".ceo-pph-view").forEach(btn => {
        btn.onclick = () => loadPipelineRunDetail(document.getElementById("ceoPphDetail"), btn.dataset.id);
      });
    }

    // ---- Reports
    async function expandReports() {
      const d = await fetchAll();
      if (isStaleRoute(myToken)) return;
      expandedShell("Reports", `
        <div class="section-title">Best / Worst Strategies</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Strategy</th><th>Avg Profit %</th><th>Batches</th></tr></thead>
          <tbody>${(d.bestWorst.ranking || []).map(r => `
            <tr><td>${esc(r.strategy)}</td><td class="${r.avg_profit_pct > 0 ? 'positive' : r.avg_profit_pct < 0 ? 'negative' : ''}">${r.avg_profit_pct}%</td><td>${r.batches}</td></tr>`).join("") || '<tr><td colspan="3">No completed backtests yet.</td></tr>'}</tbody>
        </table></div>
        <div class="section-title">Recent Batches</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Strategy</th><th>Profit %</th><th>When</th><th></th></tr></thead>
          <tbody>${d.history.slice(0, 15).map(b => `
            <tr><td>${esc(b.display_name || b.strategy)}</td><td class="${b.avg_profit_pct > 0 ? 'positive' : b.avg_profit_pct < 0 ? 'negative' : ''}">${b.avg_profit_pct}%</td>
            <td>${timeAgo(b.created_at)}</td><td><a href="/api/reports/${b.batch_id}/export/csv" class="btn-ghost" style="text-decoration:none;display:inline-block;">Export CSV</a></td></tr>`).join("") || '<tr><td colspan="4">No completed backtests yet.</td></tr>'}</tbody>
        </table></div>`);
    }

    // ---- Settings
    async function expandSettings() {
      const d = await fetchAll();
      if (isStaleRoute(myToken)) return;
      const st = d.settings;
      expandedShell("Settings", `
        <div class="card" style="max-width:520px;">
          <div class="form-row"><label>Exchange</label>
            <select id="ceoSetExchange">${(st.available_exchanges || []).map(e => `<option ${e === st.exchange ? "selected" : ""}>${esc(e)}</option>`).join("")}</select>
          </div>
          <div class="form-row"><label>Quote Asset</label><input id="ceoSetQuote" value="${esc(st.quote_asset || "")}"></div>
          <div class="form-row"><label>Number of Coins</label><input id="ceoSetNumCoins" type="number" value="${st.num_coins ?? 50}"></div>
          <div class="form-row"><label>Default Risk %</label><input id="ceoSetRisk" type="number" step="0.1" value="${st.default_risk_pct ?? 1}"></div>
          <div class="form-row"><label>Theme</label>
            <select id="ceoSetTheme"><option value="dark" ${st.theme === "dark" ? "selected" : ""}>Dark</option><option value="light" ${st.theme === "light" ? "selected" : ""}>Light</option></select>
          </div>
          <div class="btn-row"><button class="btn" id="ceoSetSave">Save Settings</button><span id="ceoSetStatus" class="muted"></span></div>
        </div>`);
      document.getElementById("ceoSetSave").onclick = async () => {
        const status = document.getElementById("ceoSetStatus");
        status.textContent = "Saving...";
        try {
          await autosave("POST", "/api/settings", {
            exchange: document.getElementById("ceoSetExchange").value,
            quote_asset: document.getElementById("ceoSetQuote").value,
            num_coins: parseInt(document.getElementById("ceoSetNumCoins").value, 10),
            default_risk_pct: parseFloat(document.getElementById("ceoSetRisk").value),
            theme: document.getElementById("ceoSetTheme").value,
          });
          document.documentElement.setAttribute("data-theme", document.getElementById("ceoSetTheme").value);
          status.textContent = "Saved.";
        } catch (e) { status.textContent = `Failed (queued for retry): ${e.message}`; }
      };
    }

    // ------------------------------------------------------------ boot + live updates
    // fetchAll() fires ~13 parallel requests. Paper Trading alone broadcasts
    // very frequently (every tick, every position open/close), so a naive
    // "re-render on every WS message" handler fires a fresh fetchAll() many
    // times per second -- Chrome's per-origin connection pool exhausts
    // almost immediately (net::ERR_INSUFFICIENT_RESOURCES) and every card
    // silently falls back to its empty/failed state. Debounce bursts into
    // one refresh, and never let two refreshes overlap in flight.
    let refreshTimer = null;
    let refreshInFlight = false;
    let refreshQueuedAgain = false;
    function scheduleRefresh(fn) {
      if (refreshTimer) return;
      refreshTimer = setTimeout(async () => {
        refreshTimer = null;
        if (refreshInFlight) { refreshQueuedAgain = true; return; }
        refreshInFlight = true;
        try { await fn(); } catch (e) { console.error(e); }
        refreshInFlight = false;
        if (refreshQueuedAgain) { refreshQueuedAgain = false; scheduleRefresh(fn); }
      }, 800);
    }

    await showGrid();

    onLive((msg) => {
      if (isStaleRoute(myToken)) return;
      const relevant = msg.channel === "job" || msg.channel === "progress" || msg.channel === "sync";
      if (!relevant) return;
      if (expandedId === null) { scheduleRefresh(showGrid); return; }
      if ((expandedId === "backtesting" || expandedId === "backtest_history") && (msg.channel === "job" || msg.channel === "progress")) {
        scheduleRefresh(() => expandBacktesting(expandedId));
      } else if (expandedId === "all_tasks") {
        scheduleRefresh(expandAllTasks);
      }
    });
    onLive((msg) => {
      if (msg.channel === "log" && expandedId === "backtesting") {
        const box = document.getElementById("ceoBtLog");
        if (box) {
          const div = document.createElement("div");
          div.textContent = msg.message;
          box.appendChild(div);
          box.scrollTop = box.scrollHeight;
        }
      }
    });
    autoRefresh(() => { if (expandedId === null) return scheduleRefresh(showGrid) || Promise.resolve(); return Promise.resolve(); }, 15);
  }

  // Fire-and-forget diagnostics beacon: reports what viewport/UA a REAL
  // browser (mobile or otherwise) actually has, once per page load, so a
  // "mobile layout isn't showing on my phone"-style report can be checked
  // against the real device's own numbers in sindhu.log instead of only a
  // simulated viewport -- never awaited, never allowed to affect load.
  function reportClientDiagnostics() {
    try {
      apiPost("/api/system/client-diagnostics", {
        innerWidth: window.innerWidth, innerHeight: window.innerHeight,
        devicePixelRatio: window.devicePixelRatio, userAgent: navigator.userAgent,
      }).catch(() => {});
    } catch (e) { /* never let a diagnostics beacon break page load */ }
  }

  // ------------------------------------------------------------ init
  (async function init() {
    await ensureToken();
    await renderNav();
    connectWs();
    reportClientDiagnostics();
    route();
  })();
})();
