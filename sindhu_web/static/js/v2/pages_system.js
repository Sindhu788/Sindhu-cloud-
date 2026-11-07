/* System (master plan V2 PG7 / W9): Cloud/local health (/health/details), last scans and per-stage timing, database share of the scan,
   memory trend, data freshness with a drill-down, background checks, soak summary, versions; plain links to Render and UptimeRobot. */
(function () {
  "use strict";
  const S2 = window.S2, esc = S2.esc, icon = S2.icon, f = S2.fmt;

  const ok = v => (v ? `<span class="up">${icon("circle-check")} ok</span>` : `<span class="down">${icon("circle-x")} problem</span>`);

  async function render(el, o) {
    o.actions.innerHTML = `<button class="btn sm" id="syRefresh" type="button">${icon("refresh-cw")}Refresh</button>`;
    const [det, sys, health] = await Promise.all([S2.api("/health/details", { timeout: 20000 }), S2.api("/api/v2/system").catch(() => ({})),
      fetch("/health", { credentials: "same-origin" }).then(r => r.json()).catch(() => ({}))]);
    if (o.stale()) return;
    document.getElementById("syRefresh").onclick = () => S2.route();
    const sc = det.self_check || {}, mem = det.memory || {}, ls = sys.last_stages || {}, db = ls.scan_db || {}, lat = det.db_latency || {};
    const raw = sc.checks || [];
    const checks = (Array.isArray(raw) ? raw.map(c => [c.name, c]) : Object.entries(raw)).filter(([k, v]) => v && typeof v === "object" && "ok" in v);
    el.innerHTML = `
      <div class="ds-grid">
        <div class="card span-3"><div class="stat"><span class="k">Trading</span><span class="v ${det.trading === "enabled" ? "up" : "down"}">${esc(det.trading || "--")}</span><span class="d">${Object.keys(det.config_errors || {}).length} config errors</span></div></div>
        <div class="card span-3"><div class="stat"><span class="k">Memory (RSS)</span><span class="v">${f.num(mem.rss_mb, 0)} MB</span><span class="d">soft ${esc(mem.soft_mb)} / hard ${esc(mem.hard_mb)} MB &middot; ${esc(mem.level || "--")}</span></div></div>
        <div class="card span-3"><div class="stat"><span class="k">Scans finished</span><span class="v">${f.num(det.scans_finished, 0)}</span><span class="d">since start ${esc(f.ago(health.started_at))}</span></div></div>
        <div class="card span-3"><div class="stat"><span class="k">Database round trip</span><span class="v">${lat.p50_ms !== null && lat.p50_ms !== undefined ? f.num(lat.p50_ms, 0) + " ms" : "--"}</span>
          <span class="d">${lat.samples ? `p95 ${f.num(lat.p95_ms, 0)} ms, ${lat.samples} x SELECT 1, ${esc(f.ago(lat.at))}` : "measured on Cloud (Postgres) only"}</span></div></div>
      </div>
      <div class="ds-grid" style="margin-top:16px">
        <div class="card span-6"><div class="card-h"><h3>Last scan, per stage</h3><span class="t-hint">${ls.at ? esc(f.ago(ls.at)) : "no scan finished yet"}</span></div>
          <div class="card-b">${ls.total_s ? `<dl class="kv"><dt>Total</dt><dd>${f.dur(ls.total_s)}</dd>
            <dt>Database (scan thread)</dt><dd>${db.share_pct !== undefined ? `${esc(db.share_pct)} % &middot; ${f.num(db.statements, 0)} statements ${f.num(db.statement_s, 0)} s, ${f.num(db.commits, 0)} commits ${f.num(db.commit_s, 0)} s` : "--"}</dd>
            <dt>RSS at end</dt><dd>${f.num(ls.rss_mb, 0)} MB</dd></dl>
            <p class="t-hint mono" style="margin-top:10px;white-space:pre-wrap;word-break:break-word">${esc(ls.stages || "")}</p>
            <p class="t-hint mono" style="white-space:pre-wrap;word-break:break-word">${esc(ls.candles || "")}</p>
            ${(db.top || []).length ? `<div class="label-caps" style="margin-top:10px">Slowest statements</div><ol style="margin:4px 0 0;padding-left:18px;font-size:12px">${db.top.map(t => `<li><span class="mono">${esc(t[1])}x ${esc(t[2])} s</span> <span class="t-3">${esc(t[0])}</span></li>`).join("")}</ol>` : ""}`
            : S2.empty("Abhi koi scan poora nahi hua", "Engine start ke baad pehla scan khatam hone par timing yahan aayegi.", "clock")}</div></div>
        <div class="card span-6"><div class="card-h"><h3>Memory trend</h3><span class="t-hint">one point per minute, this instance</span></div><div class="card-b"><div class="chart" id="syMem"></div></div></div>
      </div>
      <div class="ds-grid" style="margin-top:16px">
        <div class="card span-6"><div class="card-h"><h3>Data freshness</h3></div><div class="card-b" id="syFresh"></div></div>
        <div class="card span-6"><div class="card-h"><h3>Background checks</h3><span class="t-hint">self-check ${esc(f.ago(sc.at || sc.checked_at))}</span></div><div class="card-b">
          ${checks.length ? `<dl class="kv">${checks.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${ok(v.ok)} <span class="t-3">${esc(typeof v.detail === "object" ? Object.entries(v.detail || {}).map(([a, b]) => a + " " + b).join(", ") : (v.detail || ""))}</span></dd>`).join("")}</dl>` : S2.empty("Self-check abhi chala nahi", "Start ke ~20 s baad chalta hai.", "clock")}
          <dl class="kv" style="margin-top:12px"><dt>Database breaker</dt><dd>${det.db_breaker ? (det.db_breaker.open ? '<span class="down">open</span>' : '<span class="up">closed</span>') : "--"}</dd>
          <dt>Full-refetch queue</dt><dd>${det.refetch_queue ? `${esc(det.refetch_queue.queue)} waiting (limit ${esc(det.refetch_queue.limit === null ? "none" : det.refetch_queue.limit)} per scan)` : "--"}</dd>
          <dt>Top-coins list on disk</dt><dd>${det.top_coins_cache ? `${esc(det.top_coins_cache.coins)} coins, saved ${esc(f.ago(det.top_coins_cache.saved_at_utc))}` : "--"}</dd>
          <dt>Log lines, last full hour</dt><dd>${det.log_lines && det.log_lines.last_full_hour !== null && det.log_lines.last_full_hour !== undefined ? f.num(det.log_lines.last_full_hour, 0) : "--"}</dd></dl></div></div>
      </div>
      <div class="ds-grid" style="margin-top:16px">
        <div class="card span-6"><div class="card-h"><h3>Recent scans</h3></div><div class="card-b flush" id="syScans"></div></div>
        <div class="card span-6"><div class="card-h"><h3>Versions and links</h3></div><div class="card-b"><dl class="kv">
          <dt>Server commit</dt><dd>${esc(health.commit || det.commit || "--")}</dd><dt>UI build</dt><dd>${esc(sys.build || "--")}</dd>
          <dt>Database</dt><dd>${esc(health.db_backend || "--")}</dd><dt>Config hash</dt><dd>${esc(det.config_hash || "--")}</dd></dl>
          <div class="row wrap" style="margin-top:12px"><a class="btn sm" href="https://dashboard.render.com/web/srv-dabhrd8jo6nc739e08k0/logs" target="_blank" rel="noopener noreferrer">${icon("external-link")}Render logs</a>
          <a class="btn sm" href="https://dashboard.uptimerobot.com/monitors" target="_blank" rel="noopener noreferrer">${icon("external-link")}UptimeRobot</a>
          <a class="btn sm" href="/health/details" target="_blank" rel="noopener">${icon("file-text")}/health/details</a></div>
          ${sys.soak_report ? `<div class="label-caps" style="margin-top:16px">Soak report</div><pre class="mono t-2" style="font-size:11px;white-space:pre-wrap;margin:6px 0 0">${esc(sys.soak_report)}</pre>` : ""}</div></div>
      </div>`;
    const c = det.candles;
    document.getElementById("syFresh").innerHTML = c && c.series ? `<dl class="kv"><dt>Series</dt><dd>${f.num(c.series, 0)}</dd><dt>Fresh</dt><dd class="up">${f.num(c.fresh, 0)}</dd>
      <dt>Data purana</dt><dd class="${c.stale ? "warnc" : ""}">${f.num(c.stale, 0)}</dd><dt>Oldest</dt><dd>${f.dur(c.oldest_age_s)}</dd></dl>
      ${(c.stale_examples || []).length ? `<details style="margin-top:10px"><summary class="t-2" style="cursor:pointer">Show stale series (${c.stale_examples.length})</summary>
        <div class="row wrap" style="margin-top:8px;gap:6px">${c.stale_examples.map(s => `<span class="badge stale">${esc(s)}</span>`).join("")}</div></details>` : ""}`
      : S2.empty("Local mode", "Candles come from the local database here; freshness is tracked on Cloud.", "database");
    S2.table(document.getElementById("syScans"), { rows: sys.scans || [], search: false, pageSize: 10,
      columns: [{ key: "completed_at", label: "Finished (UTC)", fmt: f.utc }, { key: "outcome", label: "Outcome", render: v => (v === "complete" ? `<span class="up">complete</span>` : `<span class="warnc">${esc(v)}</span>`) },
        { key: "coins_scanned", label: "Coins", num: true }, { key: "accepted", label: "Opened", num: true }, { key: "errors", label: "Errors", num: true, cls: v => (v ? "down" : "") },
        { key: "dur", label: "Took", num: true, get: r => (Date.parse(r.completed_at) - Date.parse(r.started_at)) / 1000, fmt: f.dur }],
      emptyTitle: "Koi scan record nahi", emptyText: "Scan receipts are written when the engine runs." });
    const hist = sys.memory_history || [];
    S2.chart(document.getElementById("syMem"), { x: hist.map(p => p[0]), series: [{ label: "RSS MB", values: hist.map(p => p[1]), color: "accent", fill: true }],
      yFmt: v => Math.round(v) + " MB", emptyText: "Memory points start one minute after the engine starts" });
  }

  S2.pages.system = { title: "System", crumb: "Health, scans, data, jobs", render };
})();
