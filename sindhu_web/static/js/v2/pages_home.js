/* Home v2 (master plan V2 PG2 / W4): MAIN_WALLET first. Data: cached /api/summary (30 s) + /api/wallet/equity; charts lazy-load. */
(function () {
  "use strict";
  const S2 = window.S2, esc = S2.esc, icon = S2.icon, f = S2.fmt;

  const EVENT_TEXT = { opened: "Opened", closed: "Closed", rejected: "Skipped", paused: "Paused", unpause: "Un-paused", daily_limit: "Daily limit" };

  function eventRow(e) {
    const ev = String(e.event || "");
    const what = EVENT_TEXT[ev] || ev;
    const pnlMatch = ev === "closed" && e.notional !== null ? "" : "";
    const sym = e.symbol ? `<span class="mono">${esc(e.symbol)}</span> ` : "";
    const strat = e.strategy_name ? `<span class="t-3"> &middot; ${esc(String(e.strategy_name).slice(0, 48))}</span>` : "";
    const val = e.notional ? `<span class="mono t-2">${f.money(e.notional)}</span>` : "";
    return `<li><time datetime="${esc(e.created_at)}" title="${esc(f.utc(e.created_at))}">${esc(f.time(e.created_at))}</time>
      <div><strong>${esc(what)}</strong> ${sym}${strat}${e.reason && ev !== "opened" ? `<div class="t-3" style="font-size:12px">${esc(String(e.reason).slice(0, 140))}</div>` : ""}${pnlMatch}</div>${val}</li>`;
  }

  function healthText(sys, ks) {
    if (ks && ks.active) return { v: "Stopped", cls: "down", d: "Kill switch is on" };
    if (!sys) return { v: "Unknown", cls: "warnc", d: "Health not reachable" };
    if (sys.trading === "disabled_config_error") return { v: "Blocked", cls: "down", d: "Config error: see System" };
    if (sys.db_breaker && sys.db_breaker.open) return { v: "Degraded", cls: "warnc", d: "Database breaker open" };
    if (sys.self_check_ok === false) return { v: "Check", cls: "warnc", d: "Self-check found a problem" };
    return { v: "OK", cls: "up", d: "Trading enabled, self-check ok" };
  }

  async function render(el, o) {
    o.actions.innerHTML = `<button class="btn sm" id="homeRefresh" type="button">${icon("refresh-cw")}Refresh</button>`;
    el.innerHTML = `
      <div class="ds-grid" id="homeStats">${[1, 2, 3, 4].map(() => `<div class="card span-3"><div class="stat"><span class="sk w-40"></span><span class="sk h-32"></span><span class="sk w-60"></span></div></div>`).join("")}</div>
      <div class="ds-grid" style="margin-top:16px">
        <div class="card span-8"><div class="card-h"><h3>Equity</h3><span class="t-hint" id="eqHint">MAIN_WALLET, $ after fees</span></div>
          <div class="card-b"><div class="chart" id="eqChart"></div></div>
          <div class="card-h" style="border-top:1px solid var(--line-soft)"><h3>Drawdown</h3><span class="t-hint">% below the highest equity so far</span></div>
          <div class="card-b"><div class="chart" id="ddChart" style="min-height:140px"></div></div></div>
        <div class="card span-4"><div class="card-h"><h3>Last 10 wallet events</h3><a class="t-hint" href="#/trades?tab=journal">Journal</a></div>
          <div class="card-b flush" id="homeEvents">${S2.skeleton(6)}</div></div>
      </div>
      <div class="ds-grid" style="margin-top:16px">
        <div class="card span-6"><div class="card-h"><h3>Scanner</h3><span class="t-hint" id="scanHint"></span></div><div class="card-b" id="homeScan">${S2.skeleton(3)}</div></div>
        <div class="card span-6"><div class="card-h"><h3>Data freshness</h3><a class="t-hint" href="#/system">System</a></div><div class="card-b" id="homeFresh">${S2.skeleton(3)}</div></div>
      </div>`;

    async function load(force) {
      let s;
      try { s = await S2.api("/api/summary" + (force ? "?refresh=true" : ""), { timeout: 25000 }); }
      catch (e) { if (!o.stale()) { document.getElementById("homeStats").innerHTML = `<div class="card span-12">${S2.errorBlock(e, "homeRetry")}</div>`; const b = document.getElementById("homeRetry"); if (b) b.onclick = () => load(true); } return; }
      if (o.stale()) return;
      const w = s.wallet || {};
      const hl = healthText(s.system, s.kill_switch);
      const dayPct = w.day_start_equity ? (w.day_pnl / w.day_start_equity) * 100 : null;
      const totPct = w.start_balance ? ((w.equity - w.start_balance) / w.start_balance) * 100 : null;
      const maxOpen = (w.rules || {}).max_open_positions;
      document.getElementById("homeStats").innerHTML = `
        <div class="card span-3"><div class="stat"><span class="k">${icon("wallet")}Wallet equity</span><span class="v big">${f.money(w.equity)}</span>
          <span class="d"><span class="${S2.cls(totPct)}">${f.signedPct(totPct)}</span> since start (${f.money(w.start_balance)}) &middot; cash ${f.money(w.cash)}</span></div></div>
        <div class="card span-3"><div class="stat"><span class="k">${icon("clock")}Today (UTC)</span><span class="v ${S2.cls(w.day_pnl)}">${f.signedMoney(w.day_pnl)}</span>
          <span class="d">${f.signedPct(dayPct)} &middot; ${w.entries_blocked_today ? '<span class="down">daily limit hit: no new entries</span>' : `limit -${esc((w.rules || {}).daily_loss_limit_pct)}%`}</span></div></div>
        <div class="card span-3"><div class="stat"><span class="k">${icon("arrow-left-right")}Open positions</span><span class="v">${esc(w.open_positions ?? "--")}<span class="t-3" style="font-size:16px"> / ${esc(maxOpen ?? "--")}</span></span>
          <span class="d">${esc(w.closed_trades ?? 0)} closed &middot; realized <span class="${S2.cls(w.realized_pnl)}">${f.signedMoney(w.realized_pnl)}</span></span></div></div>
        <div class="card span-3"><div class="stat"><span class="k">${icon("activity")}System</span><span class="v ${hl.cls}">${esc(hl.v)}</span><span class="d">${esc(hl.d)}</span></div></div>`;
      const ev = (w.last_events || []).slice(0, 10);
      const evAll = await S2.api("/api/wallet?journal_limit=10").then(x => x.journal || ev).catch(() => ev);
      if (o.stale()) return;
      document.getElementById("homeEvents").innerHTML = evAll.length ? `<ul class="events">${evAll.slice(0, 10).map(eventRow).join("")}</ul>`
        : S2.empty("Abhi koi wallet event nahi", "Jab koi strategy signal deti hai aur saare gates pass hote hain, wallet trade kholta hai. Har faisla yahan dikhega.", "wallet");
      const eg = s.engine || {};
      const nextAt = eg.next_tick_at ? Date.parse(eg.next_tick_at) : null;
      const progress = eg.scan_in_progress ? `Scanning coin ${esc(eg.scan_index ?? "?")} of ${esc(eg.scan_total ?? "?")}` : "Idle between scans";
      document.getElementById("homeScan").innerHTML = `<dl class="kv">
        <dt>Status</dt><dd>${eg.running ? esc(progress) : '<span class="warnc">engine not running</span>'}</dd>
        <dt>Last scan</dt><dd>${eg.last_tick_at ? esc(f.ago(eg.last_tick_at)) : "--"}</dd>
        <dt>Last scan took</dt><dd>${f.dur(eg.last_tick_seconds)}</dd>
        <dt>Next scan in</dt><dd id="nextScan">--</dd></dl>`;
      const tick = () => {
        const n = document.getElementById("nextScan"); if (!n) return false;
        if (eg.scan_in_progress) n.textContent = "running now"; else if (!nextAt) n.textContent = "--";
        else { const left = Math.round((nextAt - Date.now()) / 1000); n.textContent = left > 0 ? f.dur(left) : "any moment"; }
        return true;
      };
      tick();
      const iv = setInterval(() => { if (!tick()) clearInterval(iv); }, 1000);
      S2._cleanup = () => clearInterval(iv);
      const c = (s.system || {}).candles;
      document.getElementById("homeFresh").innerHTML = c && c.series ? `<dl class="kv">
        <dt>Series in memory</dt><dd>${f.num(c.series, 0)}</dd><dt>Fresh</dt><dd class="up">${f.num(c.fresh, 0)}</dd>
        <dt>Data purana (stale)</dt><dd class="${c.stale ? "warnc" : ""}">${f.num(c.stale, 0)}</dd>
        <dt>Oldest</dt><dd>${f.dur(c.oldest_age_s)}</dd></dl>
        ${c.stale ? `<p class="t-hint" style="margin-top:8px">Stale = not refreshed in this scan yet. A coin is checked again when the scanner reaches it.</p>` : ""}`
        : S2.empty("Local mode", "Is computer par candles database se aati hain; freshness Cloud par dikhti hai.", "database");
      document.getElementById("scanHint").textContent = "summary " + (s.cached ? `cached ${Math.round(s.age_s)} s` : "fresh");
    }

    async function charts() {
      let d;
      try { d = await S2.api("/api/wallet/equity"); } catch (e) { document.getElementById("eqChart").innerHTML = S2.errorBlock(e); return; }
      if (o.stale()) return;
      const pts = (d.points || []).filter(p => !isNaN(Date.parse(p.t)));
      const x = pts.map(p => Math.round(Date.parse(p.t) / 1000));
      const eq = pts.map(p => p.equity);
      let peak = -Infinity;
      const dd = eq.map(v => { peak = Math.max(peak, v); return peak > 0 ? -((peak - v) / peak) * 100 : 0; });
      document.getElementById("eqHint").textContent = `${pts.length - 2 > 0 ? pts.length - 2 : 0} closed trades, start ${f.money(d.start_balance)}`;
      const note = "Pehla trade band hone ke baad curve dikhega";
      if (pts.length <= 2) {             // only "start" and "now": nothing closed yet, a flat line would say nothing
        document.getElementById("eqChart").innerHTML = `<div class="chart-empty">${note}. Abhi equity ${f.money(eq[eq.length - 1])}.</div>`;
        document.getElementById("ddChart").innerHTML = `<div class="chart-empty" style="min-height:140px">${note}</div>`;
        return;
      }
      await S2.chart(document.getElementById("eqChart"), { x, series: [{ label: "Equity", values: eq, color: "accent", fill: true }], yFmt: v => "$" + Number(v).toFixed(2), emptyText: note });
      await S2.chart(document.getElementById("ddChart"), { x, height: 140, series: [{ label: "Drawdown", values: dd, color: "loss", fill: true }], yFmt: v => Number(v).toFixed(1) + "%", emptyText: note });
    }

    document.getElementById("homeRefresh").addEventListener("click", () => { load(true); charts(); });
    await load(false);
    const idle = window.requestIdleCallback || (fn => setTimeout(fn, 200));
    idle(() => { if (!o.stale()) charts(); });
  }

  S2.pages.home = { title: "Home", crumb: "MAIN_WALLET · $100 paper", render };
})();
