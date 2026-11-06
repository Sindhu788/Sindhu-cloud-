/* Strategies (master plan V2 PG4 / W6): validation badge, MAIN_WALLET status (eligible / paused + reason, manual un-pause with
   confirm), research-book numbers (clearly "Research - not the wallet"), timeframe; Part B daily strategies with FRAGILE and why. */
(function () {
  "use strict";
  const S2 = window.S2, esc = S2.esc, icon = S2.icon, f = S2.fmt;

  async function render(el, o) {
    o.actions.innerHTML = `<a class="btn sm" href="/legacy#strategies">${icon("external-link")}Strategy library (old page)</a>`;
    const [ov, val, sum] = await Promise.all([
      S2.api("/api/paper-trading/strategy-overview", { timeout: 30000 }),
      S2.api("/api/v2/validation").catch(() => ({ classes: {}, benchmark_v2: [] })),
      S2.api("/api/summary").catch(() => ({})),
    ]);
    if (o.stale()) return;
    const classes = val.classes || {};
    const paused = ((sum.wallet || {}).paused_strategies) || {};
    const rows = (ov.strategies || []).map(s => {
      const c = classes[s.strategy_id] || {};
      const p = paused[s.strategy_id];
      return Object.assign({}, s, { vclass: c.class || "NOT VALIDATED", tf: c.entry_tf || "--",
        wallet: p ? "paused" : s.in_paper_trading ? "eligible" : "not active", pause_reason: p ? (p.reason || JSON.stringify(p)) : "" });
    });
    const counts = rows.reduce((a, r) => { a[r.vclass] = (a[r.vclass] || 0) + 1; return a; }, {});
    const active = rows.filter(r => r.in_paper_trading).length;
    el.innerHTML = `
      <div class="ds-grid">
        <div class="card span-3"><div class="stat"><span class="k">Strategies in library</span><span class="v">${rows.length}</span><span class="d">${active} active in paper trading</span></div></div>
        <div class="card span-3"><div class="stat"><span class="k">${S2.badge("ROBUST")}</span><span class="v">${counts.ROBUST || 0}</span><span class="d">passed every backtest rule</span></div></div>
        <div class="card span-3"><div class="stat"><span class="k">${S2.badge("FRAGILE")}</span><span class="v">${counts.FRAGILE || 0}</span><span class="d">some rules passed, not all</span></div></div>
        <div class="card span-3"><div class="stat"><span class="k">${S2.badge("FAILED")}</span><span class="v">${counts.FAILED || 0}</span><span class="d">no edge found in backtests</span></div></div>
      </div>
      <div class="notice" style="margin:16px 0">${icon("info")}<div><strong>Research books are not the wallet.</strong> Every active strategy trades its own paper
        book. MAIN_WALLET ($100) takes a strategy's signal only when every wallet gate passes; a strategy can be paused for the wallet
        automatically (after 20 wallet trades with PF &lt; 0.9 or drawdown &gt; 3 %). Un-pause is manual.</div></div>
      <div id="stTable"></div>
      <h2 style="margin:24px 0 8px">Daily portfolio strategies (Part B, pre-registered)</h2>
      <div class="ds-grid" id="stBench"></div>`;
    const cols = [
      { key: "name", label: "Strategy", render: (v, r) => `<span>${esc(String(v).slice(0, 56))}</span><div class="t-hint mono">${esc(r.strategy_id)}</div>`, cls: "wrap" },
      { key: "vclass", label: "Backtest", render: v => S2.badge(v) },
      { key: "tf", label: "TF" },
      { key: "wallet", label: "Wallet", render: (v, r) => v === "paused"
          ? `${S2.badge("PAUSED")} <button class="btn sm" type="button" data-unpause="${esc(r.strategy_id)}">Un-pause</button>`
          : v === "eligible" ? `<span class="badge live">eligible</span>` : `<span class="t-3">not active</span>` },
      { key: "closed_trades", label: "Research trades", num: true, fmt: v => f.num(v, 0) },
      { key: "win_rate", label: "Win rate", num: true, fmt: v => f.pct(v, 1) },
      { key: "total_pnl", label: "Research P&L", num: true, fmt: f.signedMoney, cls: v => S2.cls(v) },
      { key: "risk_reward", label: "R:R", num: true, fmt: v => (v ? "1:" + Number(v).toFixed(1) : "--") },
      { key: "bt_pf", label: "Backtest PF", num: true, get: r => (r.backtest || {}).profit_factor, fmt: v => (v === null || v === undefined ? "--" : Number(v).toFixed(2)) },
    ];
    S2.table(document.getElementById("stTable"), { columns: cols, rows, csv: "strategies", sortKey: "closed_trades",
      filters: [{ key: "vclass", label: "Backtest" }, { key: "wallet", label: "Wallet" }, { key: "tf", label: "TF" }],
      searchPlaceholder: "Strategy name or id", emptyTitle: "Library khali hai",
      expand: r => `<dl class="kv" style="max-width:640px"><dt>Pause reason</dt><dd>${esc(r.pause_reason || "--")}</dd>
        <dt>Can activate</dt><dd>${r.can_activate ? "yes" : esc(r.activation_blocked_reason || "no")}</dd>
        <dt>Backtest trades</dt><dd>${f.num((r.backtest || {}).total_trades, 0)}</dd><dt>Backtest net P&L</dt><dd>${f.signedMoney((r.backtest || {}).net_pnl)}</dd>
        <dt>Tags</dt><dd>${esc((r.tags || []).join(", ") || "--")}</dd></dl>` });
    document.getElementById("stTable").addEventListener("click", async e => {
      const b = e.target.closest("[data-unpause]"); if (!b) return;
      e.stopPropagation();
      const id = b.dataset.unpause;
      const ok = await S2.confirm("Un-pause for MAIN_WALLET?", "The wallet may take this strategy's signals again. Every wallet gate still applies.", "Un-pause", false);
      if (!ok) return;
      try { await S2.api("/api/wallet/unpause/" + encodeURIComponent(id), { method: "POST", body: {} }); S2.toast("Un-paused. Wallet gates still apply."); S2.route(); }
      catch (err) { S2.toast("Un-pause failed: " + err.message, "err"); }
    });
    const bench = val.benchmark_v2 || [];
    document.getElementById("stBench").innerHTML = bench.length ? bench.map(b => `
      <div class="card span-6"><div class="card-h"><h3>${esc(b.name)}</h3>${S2.badge(b.class)}</div>
        <div class="card-b"><p class="t-2">${esc(b.why)}</p><p class="t-hint" style="margin-top:8px">Timeframe ${esc(b.timeframe)} &middot; local research only &middot;
        <a href="#/backtests?b=${esc(b.id)}">See the backtest</a></p></div></div>`).join("")
      : `<div class="card span-12">${S2.empty("Part B results nahi mile", "paper_trading/benchmark_v2_summary.json is missing.")}</div>`;
  }

  S2.pages.strategies = { title: "Strategies", crumb: "Library, validation, wallet status", render };
})();
