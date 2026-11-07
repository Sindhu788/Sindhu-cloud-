/* Trades (master plan V2 PG3 / W5 + P34): Open positions, Closed trades, full wallet Journal, Rejected. MAIN_WALLET first, research
   books (paper, per strategy) one click away. Every table: sort, filter, 20 per page, CSV. */
(function () {
  "use strict";
  const S2 = window.S2, esc = S2.esc, icon = S2.icon, f = S2.fmt;

  function age(iso) {
    const t = typeof iso === "number" ? iso * (iso < 1e12 ? 1000 : 1) : Date.parse(iso);
    if (!t || isNaN(t)) return "--";
    const m = Math.max(0, Math.round((Date.now() - t) / 60000));
    return m < 90 ? `${m} min` : m < 2880 ? `${Math.round(m / 60)} h` : `${Math.round(m / 1440)} d`;
  }
  const tsIso = v => (typeof v === "number" ? new Date(v * (v < 1e12 ? 1000 : 1)).toISOString() : v);
  function parseJson(s) { if (!s) return null; if (typeof s === "object") return s; try { return JSON.parse(s); } catch (e) { return s; } }
  function kvBlock(obj) {
    if (obj === null || obj === undefined || obj === "") return '<span class="t-3">--</span>';
    if (typeof obj !== "object") return `<span>${esc(obj)}</span>`;
    const rows = Object.entries(obj).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(typeof v === "object" ? JSON.stringify(v) : v)}</dd>`).join("");
    return `<dl class="kv" style="max-width:720px">${rows}</dl>`;
  }

  function walletOpenCols(marks) {
    const pnl = p => { const m = marks[p.symbol]; if (!m || !p.qty) return null; return (m - p.entry_price) * p.qty * (p.side === "short" ? -1 : 1) - (p.fee_entry || 0); };
    return [
      { key: "symbol", label: "Coin", render: v => `<span class="mono">${esc(v)}</span>` },
      { key: "strategy_name", label: "Strategy", render: (v, r) => `${esc(String(v || "").slice(0, 40))} ${S2.badge(r.validation_class || "NOT VALIDATED")}` },
      { key: "timeframe", label: "TF" },
      { key: "entry_price", label: "Entry", num: true, fmt: f.price },
      { key: "mark", label: "Last price", num: true, get: r => marks[r.symbol], fmt: f.price },
      { key: "pnl_live", label: "P&L $", num: true, get: pnl, fmt: f.signedMoney, cls: v => S2.cls(v) },
      { key: "pnl_pct", label: "P&L %", num: true, get: r => { const v = pnl(r); return v === null || !r.notional ? null : (v / r.notional) * 100; }, fmt: v => f.signedPct(v), cls: v => S2.cls(v) },
      { key: "stop_loss", label: "Stop", num: true, fmt: f.price },
      { key: "take_profit", label: "Target", num: true, fmt: f.price },
      { key: "notional", label: "Size $", num: true, fmt: v => f.money(v) },
      { key: "opened_at", label: "Age", num: true, fmt: age, csv: r => r.opened_at },
    ];
  }
  const researchOpenCols = marks => [
    { key: "symbol", label: "Coin", render: v => `<span class="mono">${esc(v)}</span>` },
    { key: "strategy_name", label: "Strategy book", render: v => esc(String(v || "").slice(0, 44)) },
    { key: "direction", label: "Side" }, { key: "timeframe", label: "TF" },
    { key: "entry_price", label: "Entry", num: true, fmt: f.price },
    { key: "mark", label: "Last price", num: true, get: r => marks[r.symbol], fmt: f.price },
    { key: "stop_loss", label: "Stop", num: true, fmt: f.price }, { key: "take_profit", label: "Target", num: true, fmt: f.price },
    { key: "risk_amount", label: "Risk $", num: true, fmt: v => f.money(v) },
    { key: "entry_time", label: "Age", num: true, fmt: age, csv: r => tsIso(r.entry_time) },
  ];
  const walletClosedCols = [
    { key: "closed_at", label: "Closed (UTC)", fmt: f.utc }, { key: "symbol", label: "Coin", render: v => `<span class="mono">${esc(v)}</span>` },
    { key: "strategy_name", label: "Strategy", render: (v, r) => `${esc(String(v || "").slice(0, 36))} ${S2.badge(r.validation_class || "NOT VALIDATED")}` },
    { key: "entry_price", label: "Entry", num: true, fmt: f.price }, { key: "exit_price", label: "Exit", num: true, fmt: f.price },
    { key: "notional", label: "Size $", num: true, fmt: v => f.money(v) },
    { key: "fees", label: "Fees $", num: true, get: r => (r.fee_entry || 0) + (r.fee_exit || 0), fmt: v => f.money(v) },
    { key: "pnl", label: "P&L $ (net)", num: true, fmt: f.signedMoney, cls: v => S2.cls(v) },
    { key: "close_reason", label: "Why closed" },
  ];
  const researchClosedCols = [
    { key: "closed_at", label: "Closed (UTC)", fmt: f.utc }, { key: "symbol", label: "Coin", render: v => `<span class="mono">${esc(v)}</span>` },
    { key: "strategy_name", label: "Strategy book", render: v => esc(String(v || "").slice(0, 40)) }, { key: "direction", label: "Side" },
    { key: "entry_price", label: "Entry", num: true, fmt: f.price }, { key: "exit_price", label: "Exit", num: true, fmt: f.price },
    { key: "pnl", label: "P&L $", num: true, fmt: f.signedMoney, cls: v => S2.cls(v) }, { key: "pnl_pct", label: "P&L %", num: true, fmt: v => f.signedPct(v), cls: v => S2.cls(v) },
    { key: "exit_reason", label: "Why closed" },
  ];
  const journalCols = [
    { key: "created_at", label: "Time (UTC)", fmt: f.utc }, { key: "event", label: "Decision", render: v => esc(v) },
    { key: "symbol", label: "Coin", render: v => (v ? `<span class="mono">${esc(v)}</span>` : "--") },
    { key: "strategy_name", label: "Strategy", render: v => esc(String(v || "--").slice(0, 36)) },
    { key: "price", label: "Price", num: true, fmt: f.price }, { key: "notional", label: "Size $", num: true, fmt: v => (v ? f.money(v) : "--") },
    { key: "reason", label: "Reason", render: v => `<span class="t-2">${esc(String(v || "").slice(0, 90))}</span>` },
  ];
  function journalDetail(r) {
    return `<div class="ds-grid" style="padding:4px 0">
      <div class="span-4"><div class="label-caps" style="margin-bottom:6px">Trade</div><dl class="kv">
        <dt>Side</dt><dd>${esc(r.side || "--")}</dd><dt>Timeframe</dt><dd>${esc(r.timeframe || "--")}</dd><dt>Qty</dt><dd>${f.num(r.qty, 6)}</dd>
        <dt>Fees</dt><dd>${f.money(r.fees)}</dd><dt>Stop</dt><dd>${f.price(r.stop_loss)}</dd><dt>Target</dt><dd>${f.price(r.take_profit)}</dd></dl></div>
      <div class="span-4"><div class="label-caps" style="margin-bottom:6px">Gates (every check and its value)</div>${kvBlock(parseJson(r.gates))}</div>
      <div class="span-4"><div class="label-caps" style="margin-bottom:6px">Data sources</div>${kvBlock(parseJson(r.sources))}
        <p class="t-hint" style="margin-top:8px">Full reason: ${esc(r.reason || "--")}</p></div></div>`;
  }

  async function render(el, o) {
    const tabParam = o.q.tab || "open";
    el.innerHTML = `<div id="trTabs"></div><div id="trBody" style="margin-top:16px"></div>`;
    let wal = null, research = null;
    async function getWallet() { if (!wal) wal = await S2.api("/api/wallet?journal_limit=500&closed_limit=500"); return wal; }
    const body = () => document.getElementById("trBody");

    function bookSwitch(current, onPick) {
      const seg = S2.h("div", { class: "segmented", role: "group", "aria-label": "Which book" });
      [["wallet", "MAIN_WALLET"], ["research", "Research books"]].forEach(([id, lbl]) => {
        const b = S2.h("button", { type: "button", "aria-pressed": String(current === id) }, lbl);
        b.addEventListener("click", () => onPick(id)); seg.appendChild(b);
      });
      return seg;
    }

    async function show(tab, book) {
      book = book || "wallet";
      body().innerHTML = S2.skeleton(6);
      try {
        if (tab === "open") {
          const w = await getWallet();
          if (o.stale()) return;
          body().innerHTML = "";
          const marks = w.marks || {};
          if (book === "wallet") {
            S2.table(body(), { columns: walletOpenCols(marks), rows: w.open || [], csv: "wallet_open", toolbar: bookSwitch(book, b => show(tab, b)),
              emptyTitle: "Wallet mein abhi koi position nahi", emptyText: `Wallet tabhi trade kholta hai jab strategy signal sab gates pass kare. Max ${(w.rules || {}).max_open_positions || 4} positions, har ek max ${(w.rules || {}).max_position_pct || 15}% equity.` });
          } else {
            research = research || await S2.api("/api/paper-trading/positions");
            if (o.stale()) return;
            S2.table(body(), { columns: researchOpenCols(marks), rows: research.positions || [], csv: "research_open", toolbar: bookSwitch(book, b => show(tab, b)),
              emptyTitle: "Research books mein koi open position nahi", emptyText: "Research = har strategy ki apni paper book. Yeh wallet nahi hai." });
          }
        } else if (tab === "closed") {
          if (book === "wallet") {
            const w = await getWallet(); if (o.stale()) return; body().innerHTML = "";
            S2.table(body(), { columns: walletClosedCols, rows: w.closed || [], csv: "wallet_closed", sortKey: "closed_at", toolbar: bookSwitch(book, b => show(tab, b)),
              emptyTitle: "Wallet ka abhi koi band trade nahi", emptyText: "Pehla trade band hote hi yahan net P&L (fees ke baad) dikhega." });
          } else {
            const t = await S2.api("/api/paper-trading/trades?limit=500"); if (o.stale()) return; body().innerHTML = "";
            S2.table(body(), { columns: researchClosedCols, rows: t.trades || [], csv: "research_closed", sortKey: "closed_at", toolbar: bookSwitch(book, b => show(tab, b)),
              filters: [{ key: "strategy_name", label: "Strategy" }, { key: "symbol", label: "Coin" }], emptyTitle: "Koi band research trade nahi" });
          }
        } else if (tab === "journal") {
          const w = await getWallet(); if (o.stale()) return; body().innerHTML = "";
          const note = S2.h("p", { class: "t-hint", style: "margin-bottom:8px" }, "Every MAIN_WALLET decision with all gates, values and data sources. Click a row for the full detail.");
          body().appendChild(note);
          S2.table(body(), { columns: journalCols, rows: w.journal || [], csv: "wallet_journal", expand: journalDetail,
            filters: [{ key: "event", label: "Decision" }, { key: "strategy_name", label: "Strategy" }, { key: "symbol", label: "Coin" }],
            emptyTitle: "Journal abhi khali hai", emptyText: "Har wallet faisla (open, skip, close, pause) yahan likha jata hai." });
        } else if (tab === "rejected") {
          if (book === "wallet") {
            const w = await getWallet(); if (o.stale()) return; body().innerHTML = "";
            const rows = (w.journal || []).filter(r => r.event === "rejected");
            S2.table(body(), { columns: journalCols, rows, csv: "wallet_rejected", expand: journalDetail, toolbar: bookSwitch(book, b => show(tab, b)),
              filters: [{ key: "strategy_name", label: "Strategy" }], emptyTitle: "Koi skip nahi", emptyText: "Jab wallet koi signal chhodta hai (gate fail, cash nahi, duplicate), wajah yahan dikhegi." });
          } else {
            const d = await S2.api("/api/paper-trading/decisions?decision=rejected&limit=500"); if (o.stale()) return; body().innerHTML = "";
            S2.table(body(), { columns: [{ key: "created_at", label: "Time (UTC)", fmt: f.utc }, { key: "symbol", label: "Coin", render: v => `<span class="mono">${esc(v)}</span>` },
              { key: "strategy_name", label: "Strategy", render: v => esc(String(v || "").slice(0, 40)) }, { key: "timeframe", label: "TF" },
              { key: "reason", label: "Why rejected", render: v => `<span class="t-2">${esc(String(v || "").slice(0, 120))}</span>` }],
              rows: d.decisions || [], csv: "research_rejected", toolbar: bookSwitch(book, b => show(tab, b)), filters: [{ key: "strategy_name", label: "Strategy" }],
              emptyTitle: "Koi rejected research signal nahi" });
          }
        }
      } catch (e) {
        if (o.stale()) return;
        body().innerHTML = `<div class="card">${S2.errorBlock(e, "trRetry")}</div>`;
        const b = document.getElementById("trRetry"); if (b) b.onclick = () => { wal = null; show(tab, book); };
      }
    }
    S2.tabs(document.getElementById("trTabs"), [{ id: "open", label: "Open positions" }, { id: "closed", label: "Closed trades" },
      { id: "journal", label: "Journal" }, { id: "rejected", label: "Rejected" }], id => show(id), tabParam);
    o.actions.innerHTML = `<button class="btn sm" id="trRefresh" type="button">${icon("refresh-cw")}Refresh</button>`;
    document.getElementById("trRefresh").addEventListener("click", () => { wal = null; research = null; const sel = document.querySelector('#trTabs [aria-selected="true"]'); show(sel ? sel.id.slice(4) : "open"); });
  }

  S2.pages.trades = { title: "Trades", crumb: "Positions, journal, rejections", render };
})();
