(() => {
  "use strict";

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
  function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }

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

  function connectWs() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/logs`);
    ws.onopen = () => {
      connStatus.textContent = "● online"; connStatus.className = "conn-status conn-online";
      flushPending();
    };
    ws.onclose = () => {
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

  const themeToggle = document.getElementById("themeToggle");
  themeToggle.onclick = () => {
    const root = document.documentElement;
    const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    localStorage.setItem("sindhu_theme", next);
    autosave("POST", "/api/settings", { theme: next }).catch(() => {});
  };
  document.documentElement.setAttribute("data-theme", localStorage.getItem("sindhu_theme") || "dark");

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
    const { pages } = await apiGet("/api/nav");
    const list = document.getElementById("navList");
    list.innerHTML = pages.map(p => `
      <li><a href="#${p.id}" data-id="${p.id}" title="${esc(p.label)}">
        <svg viewBox="0 0 24 24">${NAV_ICONS[p.icon] || NAV_ICONS.dashboard}</svg>
        <span class="nav-label">${esc(p.label)}</span>
      </a></li>`).join("");

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

  const PAGES = {
    home: renderHome, market: renderMarket, data: renderData,
    backtesting: renderBacktesting, reports: renderReports, settings: renderSettings,
    knowledge: renderKnowledge, strategies: renderStrategies,
    paper_trading: renderPaperTrading, knowledge_compiler: renderKnowledgeCompiler,
    ai_center: renderAiCenter, backtest_history: renderBacktestHistory,
    pipeline_history: renderPipelineHistory,
    evolution: renderEvolution, sindhu_strategy: renderSindhuStrategy,
    ceo: renderCEO,
  };
  let refreshTimer = null;
  let pendingStrategyLoadId = null;
  let pendingHistoryBatchId = null;
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
    content.innerHTML = `<p class="muted">Loading...</p>`;
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
      const [h, net, act, bw, strats] = await Promise.all([
        apiGet("/api/home"),
        apiGet("/api/network").catch(() => null),
        apiGet("/api/activity?limit=20").catch(() => ({ activity: [] })),
        apiGet("/api/reports/best-worst/strategies").catch(() => ({ ranking: [] })),
        apiGet("/api/backtesting/strategies").catch(() => ({ strategies: [] })),
      ]);
      if (isStaleRoute(myToken)) return;

      const topStrategies = (bw.ranking || []).slice(0, 3);
      const zeroTradeAlerts = (strats.strategies || []).filter(s =>
        s.last_batch_result && s.last_batch_result.status === "completed" && s.last_batch_result.total_trades === 0
      );

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

      content.innerHTML = `
        <div class="section-title">Overview</div>
        <div class="grid">
          ${cardClass("Balance", lb ? `$${Number(lb.final_balance).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2})}` : "No backtests yet", "")}
          ${cardClass("PnL", lb ? `${lb.profit_pct > 0 ? "+" : ""}${lb.profit_pct}%` : "-", pnlClass)}
          ${cardClass("Win Rate", lb ? `${lb.win_rate}%` : "-", "")}
          ${cardClass("Total Trades", lb ? fmtNum(lb.total_trades) : "-", "")}
          ${cardClass("Knowledge Score", `${h.knowledge_score}%`, "")}
          ${cardClass("Evolution Score", `<span class="muted">N/A</span>`, "")}
          ${cardClass("Database Status", `<span class="pill pill-connected">${esc(h.database_status)}</span>`, "")}
          ${cardClass("System Health", esc(h.system_health), "")}
        </div>
        ${lb ? `<div class="muted" style="margin:-12px 0 20px;font-size:12px;">Latest completed backtest: <b>${esc(lb.strategy)}</b> -- there is no live Paper Trading yet, so this reflects the most recent backtest, not a live account.</div>` : ""}

        ${zeroTradeAlerts.length ? `
        <div class="section-title">System Alerts</div>
        <div class="card" style="border-left:3px solid var(--negative, #e5484d);">
          ${zeroTradeAlerts.map(s => `<div>⚠ Strategy <b>${esc(s.name)}</b> produced 0 trades on ${s.last_batch_result.symbols_tested || 0} coins -- check entry conditions (see Backtesting or Reports for the condition-hit breakdown).</div>`).join("")}
        </div>` : ""}

        <div class="section-title">Top Strategies by Profit</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Strategy</th><th>Avg Profit %</th><th>Batches</th></tr></thead>
          <tbody>${topStrategies.map(t => `
            <tr><td>${esc(t.strategy)}</td><td class="${t.avg_profit_pct > 0 ? 'positive' : t.avg_profit_pct < 0 ? 'negative' : ''}">${t.avg_profit_pct}%</td><td>${t.batches}</td></tr>
          `).join("") || '<tr><td colspan="3">No completed backtests yet</td></tr>'}</tbody>
        </table></div>

        <div class="section-title">System Monitor</div>
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
        <div class="section-title">Available Timeframes</div>
        <div class="card">${h.available_timeframes.join(", ")}</div>

        <div class="section-title">Control Center</div>
        <div class="two-col">
          <div class="card">
            <div class="label">Connect from mobile (same WiFi)</div>
            <div class="value" style="font-size:15px;margin:6px 0;">${net ? esc(net.url) : "-"}</div>
            <div class="qr-box">${net ? net.qr_svg : ""}</div>
          </div>
          <div>
            <div class="section-title" style="margin-top:0;">Task Manager</div>
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
    };
    await render();
    autoRefresh(render, settings.refresh_speed_seconds || 10);
    onLive((msg) => { if (msg.channel === "sync") render().catch(console.error); });
  }

  function card(label, value) {
    return `<div class="card"><div class="label">${label}</div><div class="value">${value}</div></div>`;
  }

  function cardClass(label, value, valueClass) {
    return `<div class="card"><div class="label">${label}</div><div class="value ${valueClass || ""}">${value}</div></div>`;
  }

  function cardId(id, label, value) {
    return `<div class="card"><div class="label">${label}</div><div class="value" id="${id}">${value}</div></div>`;
  }

  // ---- Paper Trading analytics: one shared renderer for the Paper Trading
  // page and the SINDHU CEO Paper Trading card's expanded view (CEO-parity
  // rule), both backed by the same /api/paper-trading/analytics endpoint so
  // neither can show a number the other disagrees with.
  const PERIOD_TABS = [
    ["today", "Today"], ["yesterday", "Yesterday"], ["week", "This Week"],
    ["month", "This Month"], ["all", "All-Time"],
  ];

  function pnlSpan(pnl) {
    const v = Number(pnl || 0);
    return `<span class="${v >= 0 ? "pill-up" : "pill-down"}">${v >= 0 ? "+" : ""}$${v.toFixed(2)}</span>`;
  }

  function paperPeriodTabsHtml(idPrefix, activePeriod) {
    return `<div class="period-tabs">${PERIOD_TABS.map(([id, label]) => `
      <button class="period-tab ${id === activePeriod ? "active" : ""}" data-period-tab="${idPrefix}" data-period="${id}">${label}</button>
    `).join("")}</div>`;
  }

  function paperAnalyticsSectionHtml(d) {
    const s = d.summary;
    const isAll = d.period === "all";
    return `
      <div class="grid">
        ${card("Closed Trades", fmtNum(s.closed_trades))}
        ${card("Active Strategies", fmtNum(s.active_strategies))}
        ${cardClass("Total PnL", `${s.total_pnl >= 0 ? "+" : ""}$${s.total_pnl.toFixed(2)}`, s.total_pnl > 0 ? "positive" : s.total_pnl < 0 ? "negative" : "")}
        ${card("Win Rate", `${s.win_rate.toFixed(1)}%`)}
        ${card("Avg Risk:Reward", s.avg_rr != null ? `${s.avg_rr.toFixed(2)}R` : "-")}
        ${card("Open Positions (separate, all-time)", fmtNum(d.open_positions_count))}
      </div>

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
      <div class="table-wrap"><table>
        <thead><tr><th>Strategy</th><th>Closed Trades</th><th>Win Rate</th><th>PnL</th><th>Open Positions</th>${isAll ? "<th>Trading Since</th>" : ""}</tr></thead>
        <tbody>${d.per_strategy.map(p => `
          <tr>
            <td>${esc(p.strategy_name || p.strategy_id)}</td>
            <td>${fmtNum(p.closed_trades)}</td>
            <td>${p.win_rate.toFixed(1)}%</td>
            <td>${pnlSpan(p.total_pnl)}</td>
            <td>${fmtNum(p.open_positions)}</td>
            ${isAll ? `<td>${esc((p.trading_since || "-").slice(0, 10))}</td>` : ""}
          </tr>`).join("") || `<tr><td colspan="${isAll ? 6 : 5}">No strategies active in this period.</td></tr>`}</tbody>
      </table></div>

      <div class="section-title">Strategy Comparison</div>
      ${paperStrategyComparisonHtml(d.per_strategy)}

      <div class="section-title">Per-Coin Breakdown${isAll ? " (All-Time)" : ""}</div>
      <div class="table-wrap"><table>
        <thead><tr><th>Coin</th><th>Closed Trades</th><th>Win Rate</th><th>PnL</th></tr></thead>
        <tbody>${d.per_coin.map(c => `
          <tr><td>${esc(c.symbol)}</td><td>${fmtNum(c.closed_trades)}</td><td>${c.win_rate.toFixed(1)}%</td><td>${pnlSpan(c.total_pnl)}</td></tr>
        `).join("") || '<tr><td colspan="4">No closed trades yet.</td></tr>'}</tbody>
      </table></div>
    `;
  }

  function paperStrategyComparisonHtml(list) {
    if (!list.length) return `<div class="muted">No strategies to compare yet.</div>`;
    const maxAbsPnl = Math.max(1, ...list.map(p => Math.abs(p.total_pnl)));
    return `<div class="table-wrap"><table>
      <thead><tr><th>Strategy</th><th>Trades</th><th>Win Rate</th><th>PnL</th><th style="min-width:140px;"></th></tr></thead>
      <tbody>${list.map(p => `
        <tr>
          <td>${esc(p.strategy_name || p.strategy_id)}</td>
          <td>${fmtNum(p.closed_trades)}</td>
          <td>${p.win_rate.toFixed(1)}%</td>
          <td>${pnlSpan(p.total_pnl)}</td>
          <td><div class="progress-bar"><div class="progress-bar-fill" style="width:${Math.abs(p.total_pnl) / maxAbsPnl * 100}%;background:${p.total_pnl >= 0 ? "var(--green)" : "var(--red)"};"></div></div></td>
        </tr>`).join("")}</tbody>
    </table></div>`;
  }

  async function loadPaperAnalytics(boxId, idPrefix, period) {
    const box = document.getElementById(boxId);
    if (!box) return;
    box.innerHTML = `<p class="muted">Loading...</p>`;
    const data = await apiGet(`/api/paper-trading/analytics?period=${period}`);
    box.innerHTML = paperPeriodTabsHtml(idPrefix, period) + paperAnalyticsSectionHtml(data);
    box.querySelectorAll(`[data-period-tab="${idPrefix}"]`).forEach(btn => {
      btn.onclick = () => loadPaperAnalytics(boxId, idPrefix, btn.dataset.period);
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

  function sparklineSvg(series) {
    if (series.length < 2) return `<div class="muted">Not enough trades for a chart.</div>`;
    return `<svg viewBox="0 0 400 160" preserveAspectRatio="none">${sparklineInner(series, 400, 160, 6)}</svg>`;
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
    const render = async () => {
      const m = await apiGet("/api/market");
      if (isStaleRoute(myToken)) return;
      const signalCls = s => s === "Bullish" ? "pill-bullish" : s === "Bearish" ? "pill-bearish" : "pill-neutral";
      const rows = m.coins.map(c => `
        <tr>
          <td>${esc(c.symbol)}</td>
          <td>${c.price}</td>
          <td class="${c.change_pct >= 0 ? 'pill-up' : 'pill-down'}">${c.change_pct.toFixed(2)}%</td>
          <td>${fmtNum(Math.round(c.volume))}</td>
          <td><span class="pill ${c.trend === 'up' ? 'pill-up' : 'pill-down'}">${c.trend}</span></td>
          <td><span class="pill ${signalCls(c.signal)}">${esc(c.signal || "-")}</span></td>
          <td>${c.volatility_pct != null ? c.volatility_pct + "%" : "-"}</td>
        </tr>`).join("");
      content.innerHTML = `
        <div class="section-title">Market (${esc(m.exchange)} / ${esc(m.quote)})</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Coin</th><th>Price</th><th>24H Change</th><th>Volume</th><th>Trend</th><th>Signal</th><th>Volatility</th></tr></thead>
          <tbody>${rows || '<tr><td colspan="7">No market data</td></tr>'}</tbody>
        </table></div>`;
    };
    await render();
    autoRefresh(render, Math.max(settings.refresh_speed_seconds || 10, 15));
  }

  // ------------------------------------------------------------ DATA
  async function renderData() {
    const myToken = activeRouteToken;
    const render = async () => {
      const d = await apiGet("/api/data");
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
        </div>
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
    return `<span class="pill ${cls}">${esc(status === "READY_FOR_BACKTEST" ? "Ready" : "Needs Clarification")}</span>`;
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
      const res = await apiGet(`/api/backtesting/strategies?q=${encodeURIComponent(q)}`).catch(() => ({ strategies: [] }));
      if (isStaleRoute(myToken)) return;
      const rows = res.strategies.map(s => `
        <tr>
          <td>${s.favourite ? "★" : "☆"}</td>
          <td>${esc(s.name)}</td>
          <td>${(s.concepts_used || []).join(", ") || "-"}</td>
          <td>${Object.entries(s.timeframes || {}).map(([role, tf]) => `${role}:${tf}`).join(", ") || "-"}</td>
          <td>${conditionRolesCell(s.condition_roles)}</td>
          <td>${strategyStatusPill(s.status)}</td>
          <td>${lastBacktestCell(s.last_batch_result)}</td>
          <td>V${s.current_version || 1} <button class="btn-ghost strat-versions" data-id="${s.id}" data-name="${esc(s.name)}">History</button></td>
          <td>
            <button class="btn-ghost strat-edit" data-id="${s.id}">Edit</button>
            ${s.status !== "READY_FOR_BACKTEST" ? `<button class="btn-ghost strat-clarify" data-id="${s.id}" data-name="${esc(s.name)}">Clarify</button>` : ""}
            <button class="btn-ghost strat-fav" data-id="${s.id}" data-fav="${s.favourite}">${s.favourite ? "★" : "☆"}</button>
            <button class="btn-ghost strat-dup" data-id="${s.id}">Duplicate</button>
            <button class="btn-ghost strat-del" data-id="${s.id}" data-name="${esc(s.name)}">Delete</button>
          </td>
        </tr>`).join("");

      content.innerHTML = `
        <div class="section-title">Strategies</div>
        <div class="btn-row">
          <input id="stratLibSearch" placeholder="Search strategies..." style="max-width:280px;" value="${esc(q)}">
          <button class="btn" id="btnNewStrategy">New Strategy</button>
        </div>
        <div class="table-wrap"><table>
          <thead><tr><th></th><th>Name</th><th>Concepts</th><th>Timeframes</th><th>Condition Roles</th><th>Status</th><th>Last Backtest</th><th>Version</th><th></th></tr></thead>
          <tbody>${rows || '<tr><td colspan="9">No saved strategies yet -- create one on the Backtesting page.</td></tr>'}</tbody>
        </table></div>
        <div id="versionHistoryBox" style="display:none;">
          <div class="section-title" id="versionHistoryTitle">Version History</div>
          <div class="table-wrap"><table>
            <thead><tr><th>Version</th><th>Modified</th></tr></thead>
            <tbody id="versionHistoryBody"></tbody>
          </table></div>
        </div>
        <div id="clarifyBox" style="display:none;">
          <div class="section-title" id="clarifyTitle">Clarification Needed</div>
          <div id="clarifyBody"></div>
        </div>`;

      document.getElementById("stratLibSearch").addEventListener("input", debounce(render, 300));
      document.getElementById("btnNewStrategy").onclick = () => { location.hash = "#backtesting"; };

      document.querySelectorAll(".strat-edit").forEach(btn => btn.onclick = () => {
        pendingStrategyLoadId = btn.dataset.id;
        location.hash = "#backtesting";
      });
      document.querySelectorAll(".strat-fav").forEach(btn => btn.onclick = async () => {
        await apiPost(`/api/backtesting/strategies/${btn.dataset.id}/favourite?favourite=${btn.dataset.fav === "true" ? "false" : "true"}`);
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
      document.querySelectorAll(".strat-versions").forEach(btn => btn.onclick = async () => {
        const v = await apiGet(`/api/backtesting/strategies/${btn.dataset.id}/versions`).catch(() => ({ versions: [] }));
        document.getElementById("versionHistoryTitle").textContent = `Version History -- ${btn.dataset.name}`;
        document.getElementById("versionHistoryBody").innerHTML = (v.versions || []).slice().reverse().map(ver => `
          <tr><td>V${ver.version}</td><td>${esc((ver.modified_at || "").slice(0, 19))}</td></tr>
        `).join("") || '<tr><td colspan="2">No version history</td></tr>';
        document.getElementById("versionHistoryBox").style.display = "block";
        document.getElementById("versionHistoryBox").scrollIntoView({ behavior: "smooth", block: "nearest" });
      });
      document.querySelectorAll(".strat-clarify").forEach(btn => btn.onclick = () => {
        openClarifyBox(btn.dataset.id, btn.dataset.name, render);
      });
    };
    await render();
    onLive((msg) => { if (msg.channel === "sync" && msg.entity === "strategy") render().catch(console.error); });
  }

  // Part 1: the clarification flow. issueControlHtml() renders the right
  // control per issue "kind" (free-text redescribe, a small set of
  // suggested options, or a reject button) -- see
  // sindhu_web/api/clarification.py::build_issues() for the shape.
  function issueControlHtml(issue) {
    const reasonBlock = `
      <div><b>${esc(issue.reason)}</b></div>
      ${issue.detail ? `<div class="muted" style="margin-top:2px;">${esc(issue.detail)}</div>` : ""}
      ${issue.ai_reason ? `<div class="muted" style="margin-top:4px;">AI's own note: "${esc(issue.ai_reason)}"${issue.ai_confidence != null ? ` (${Math.round(issue.ai_confidence * 100)}% confidence)` : ""}</div>` : ""}`;

    if (issue.kind === "raw_condition" || issue.kind === "missing_conditions") {
      return `
        <div class="card" data-issue-id="${esc(issue.id)}" data-issue-kind="${issue.kind}">
          ${reasonBlock}
          ${issue.original_text ? `<div class="muted" style="margin-top:6px;">Original text: "${esc(issue.original_text)}"</div>` : ""}
          <div class="form-row" style="margin-top:8px;"><label>Redescribe this rule</label>
            <input class="issue-text-input" placeholder="e.g. RSI 14 below 30, or close above EMA50">
          </div>
          <div class="btn-row">
            <button class="btn btn-ghost issue-apply-edit">Try This Instead</button>
            ${issue.can_reject ? `<button class="btn btn-ghost issue-apply-reject">Remove This Rule</button>` : ""}
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
          <div class="form-row" style="margin-top:8px;"><label>Or redescribe the whole rule</label>
            <input class="issue-text-input" placeholder="e.g. RSI 14 below 30">
          </div>
          <div class="btn-row">
            <button class="btn btn-ghost issue-apply-edit">Try This Instead</button>
            ${issue.can_reject ? `<button class="btn btn-ghost issue-apply-reject">Remove This Rule</button>` : ""}
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
    const box = document.getElementById("clarifyBox");
    const body = document.getElementById("clarifyBody");
    document.getElementById("clarifyTitle").textContent = `Clarification Needed -- ${name}`;
    body.innerHTML = `<div class="muted">Loading...</div>`;
    box.style.display = "block";
    box.scrollIntoView({ behavior: "smooth", block: "nearest" });

    async function load() {
      const data = await apiGet(`/api/backtesting/strategies/${strategyId}/clarification`).catch(() => null);
      if (!data) { body.innerHTML = `<div class="muted">Could not load clarification details.</div>`; return; }
      if (data.status === "READY_FOR_BACKTEST") {
        body.innerHTML = `<div class="card"><span class="pill pill-completed">Ready for Backtesting</span> Nothing left to clarify -- this strategy is fully executable.</div>`;
        return;
      }
      const confidenceNote = data.confidence_pct != null
        ? `<div class="muted" style="margin-bottom:8px;">AI import confidence: ${data.confidence_pct}%</div>` : "";
      body.innerHTML = `
        ${confidenceNote}
        ${data.issues.map(issueControlHtml).join("")}
        <div class="btn-row" style="margin-top:10px;">
          <button class="btn" id="btnApplyClarifications">Apply Changes</button>
          <button class="btn btn-ghost" id="btnCloseClarify">Close</button>
          <span id="clarifyStatus" class="muted"></span>
        </div>`;
      wireIssueCards();
    }

    function wireIssueCards() {
      const pending = new Map();  // issue id -> resolution payload

      body.querySelectorAll(".issue-apply-edit").forEach(btn => btn.onclick = () => {
        const card = btn.closest("[data-issue-id]");
        const text = card.querySelector(".issue-text-input").value;
        if (!text || !text.trim()) { alert("Type a replacement description first."); return; }
        pending.set(card.dataset.issueId, { id: card.dataset.issueId, action: "edit", text });
        btn.textContent = "Queued ✓";
      });
      body.querySelectorAll(".issue-apply-reject").forEach(btn => btn.onclick = () => {
        const card = btn.closest("[data-issue-id]");
        pending.set(card.dataset.issueId, { id: card.dataset.issueId, action: "reject" });
        btn.textContent = "Queued ✓";
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
        if (!pending.size) { alert("Pick or type at least one resolution first."); return; }
        const status = document.getElementById("clarifyStatus");
        status.textContent = "Applying...";
        try {
          const result = await apiPost(`/api/backtesting/strategies/${strategyId}/clarify`, {
            resolutions: Array.from(pending.values()),
          });
          const failedNote = result.failed.length
            ? ` ${result.failed.length} still unresolved: ${result.failed.map(f => esc(f.detail)).join(" | ")}`
            : "";
          if (result.status === "READY_FOR_BACKTEST") {
            status.textContent = "Resolved -- strategy is now Ready for Backtesting." +
              (result.pipeline_job_id ? " Automation pipeline started automatically." : "");
          } else {
            status.textContent = `Applied ${result.applied.length} change(s).${failedNote}`;
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
          renderConfigPreview(res.config, res.valid, res.errors);
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
      if (runningBacktest) {
        currentJobId = runningBacktest.id;
        jobStartTime = Date.parse(runningBacktest.started_at) || Date.now();
        const p = runningBacktest.progress || {};
        if (p.current_strategy) document.getElementById("bCurStrategy").textContent = p.current_strategy;
        if (p.current_coin) document.getElementById("bCurCoin").textContent = p.current_coin;
        if (p.current_timeframe) document.getElementById("bCurTf").textContent = p.current_timeframe;
        if (p.current_stage) document.getElementById("bStage").textContent = p.current_stage;
        if (p.bar_pct != null) document.getElementById("bBarProgressFill").style.width = `${p.bar_pct}%`;
        if (p.total != null) {
          document.getElementById("bProgress").textContent = `${p.done} / ${p.total}`;
          document.getElementById("bProgressFill").style.width = `${(p.done / Math.max(p.total, 1)) * 100}%`;
        }
        appendLog(`Resumed live view of running backtest job: ${currentJobId}`);
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
        renderConfigPreview(res.config, res.valid, res.errors);
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

    function renderConfigPreview(config, valid, errors) {
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
          : "");
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
        renderConfigPreview(currentConfig, loadedValid, loadedErrors);
        return;
      }
      const res = await apiPost("/api/backtesting/parse", { text, name });
      currentConfig = res.config;
      renderConfigPreview(res.config, res.valid, res.errors);
      if (res.valid) doAutosaveStrategy();
    }

    document.getElementById("btnParse").onclick = doParse;
    const debouncedParse = debounce(doParse, 900);
    document.getElementById("stratText").addEventListener("input", debouncedParse);
    document.getElementById("stratName").addEventListener("input", () => { debouncedParse(); doAutosaveStrategy(); });

    document.getElementById("btnSave").onclick = async () => {
      if (!currentConfig) return;
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
        res = await apiPost("/api/backtesting/run", { config: currentConfig, all_coins: true });
      } catch (e) {
        let msg = e.message;
        try { msg = JSON.parse(e.message).detail || msg; } catch (_) {}
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
          `<td>${c.max_drawdown_pct}%</td></tr>`;
      }).join("") || '<tr><td colspan="6">No completed coins in this batch yet.</td></tr>';

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
  async function renderReports() {
    const myToken = activeRouteToken;
    const [list, bw] = await Promise.all([
      apiGet("/api/reports"), apiGet("/api/reports/best-worst/strategies").catch(() => ({})),
    ]);
    if (isStaleRoute(myToken)) return;
    content.innerHTML = `
      <div class="section-title">Reports</div>
      <div class="grid">
        ${card("Best Strategy", esc(bw.best_strategy || "-"))}
        ${card("Worst Strategy", esc(bw.worst_strategy || "-"))}
      </div>
      <div class="section-title">Latest Reports</div>
      <div class="table-wrap"><table>
        <thead><tr><th>Date</th><th>Strategy</th><th>Status</th><th></th></tr></thead>
        <tbody>${list.batches.map(b => `
          <tr>
            <td>${esc(b.created_at.slice(0,19))}</td>
            <td>${esc(b.strategy_name)}</td>
            <td><span class="pill pill-${b.status}">${esc(b.status)}</span></td>
            <td>
              <button class="btn-ghost view-report" data-id="${b.batch_id}">View</button>
              <button class="btn-ghost export-report" data-id="${b.batch_id}" data-fmt="csv">CSV</button>
              <button class="btn-ghost export-report" data-id="${b.batch_id}" data-fmt="excel">Excel</button>
              <button class="btn-ghost export-report" data-id="${b.batch_id}" data-fmt="pdf">PDF</button>
            </td>
          </tr>`).join("")}</tbody>
      </table></div>
      <div id="reportDetail" style="display:none;">
        <div id="reportSummary" class="card" style="white-space:pre-wrap;font-family:Consolas,monospace;font-size:12px;"></div>
        <div id="reportZeroDiagnosis"></div>
        <div class="section-title">Per-Coin Breakdown</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Coin</th><th>Trades</th><th>Win Rate</th><th>Profit %</th><th>Total PnL</th><th>Max Drawdown</th></tr></thead>
          <tbody id="coinBreakdownBody"></tbody>
        </table></div>
        <div class="section-title">Equity Curve</div>
        <div id="equityChartBox" class="chart-box"></div>
        <div class="section-title">Drawdown</div>
        <div id="drawdownChartBox" class="chart-box"></div>
        <div id="zeroTradeSection" style="display:none;">
          <div class="section-title">0-Trade Coins -- Condition-Hit Breakdown</div>
          <div class="table-wrap"><table>
            <thead><tr><th>Coin</th><th>Condition</th><th>True Bars</th><th>Total Bars</th></tr></thead>
            <tbody id="zeroTradeBody"></tbody>
          </table></div>
        </div>
      </div>`;

    const reportDetailIds = {
      detail: "reportDetail", summary: "reportSummary", coinBody: "coinBreakdownBody",
      equityBox: "equityChartBox", drawdownBox: "drawdownChartBox",
      zeroSection: "zeroTradeSection", zeroBody: "zeroTradeBody", zeroDiagnosis: "reportZeroDiagnosis",
    };
    document.querySelectorAll(".view-report").forEach(btn => {
      btn.onclick = () => renderBatchDetailInto(btn.dataset.id, reportDetailIds);
    });
    document.querySelectorAll(".export-report").forEach(btn => {
      btn.onclick = () => {
        // export endpoints are GET (read-only), so they're open by design --
        // no token needed, safe to just navigate to them directly.
        window.open(`/api/reports/${btn.dataset.id}/export/${btn.dataset.fmt}`, "_blank");
      };
    });

    // A backtest finishing (on this device or another) should show up here
    // without a manual refresh -- Reports has no in-progress form to lose,
    // so a full re-render is safe.
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
          <td><button class="btn-ghost view-history" data-id="${b.batch_id}">View</button></td>
        </tr>`;
      }).join("") || '<tr><td colspan="7">No completed backtests yet -- run one from the Backtesting page.</td></tr>';

      document.querySelectorAll(".view-history").forEach(btn => {
        btn.onclick = () => openHistoryDetail(btn.dataset.id);
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
      return renderBatchDetailInto(batchId, histDetailIds);
    }

    const histDetailIds = {
      detail: "histDetail", summary: "histSummary", coinBody: "histCoinBreakdownBody",
      equityBox: "histEquityChartBox", drawdownBox: "histDrawdownChartBox",
      zeroSection: "histZeroTradeSection", zeroBody: "histZeroTradeBody", zeroDiagnosis: "histZeroDiagnosis",
    };

    content.innerHTML = `
      <div class="section-title">Backtest History</div>
      <p class="muted">Every completed backtest batch, permanently -- stored in the database, not just live progress.</p>
      <div class="table-wrap"><table>
        <thead><tr><th>Date</th><th>Strategy</th><th>Coins</th><th>Trades</th><th>Win Rate</th><th>Total PnL</th><th></th></tr></thead>
        <tbody id="histTableBody"><tr><td colspan="7">Loading...</td></tr></tbody>
      </table></div>
      <div id="histDetail" style="display:none;margin-top:16px;">
        <div id="histComparisonBox" class="card" style="display:none;margin-bottom:16px;"></div>
        <div id="histSummary" class="card" style="white-space:pre-wrap;font-family:Consolas,monospace;font-size:12px;"></div>
        <div id="histZeroDiagnosis"></div>
        <div class="section-title">Per-Coin Breakdown</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Coin</th><th>Trades</th><th>Win Rate</th><th>Profit %</th><th>Total PnL</th><th>Max Drawdown</th></tr></thead>
          <tbody id="histCoinBreakdownBody"></tbody>
        </table></div>
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
      </div>`;

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

    content.innerHTML = `
      <div class="section-title">Automation Pipeline History</div>
      <p class="muted">Every automation run (import -&gt; backtest -&gt; optimizer -&gt; paper trading), permanently -- the same data tracked for crash-recovery resume, not a separate log.</p>
      <div class="table-wrap"><table>
        <thead><tr><th>Started</th><th>Strategy</th><th>Status</th><th>Coins</th><th></th></tr></thead>
        <tbody id="pphTableBody"><tr><td colspan="5">Loading...</td></tr></tbody>
      </table></div>
      <div id="pphDetail" style="display:none;margin-top:16px;">
        <div class="section-title">Run Detail</div>
        <div id="pphDetailBox"></div>
      </div>`;

    await renderList();

    // A run reaching a terminal state (or progressing a stage) should
    // appear here without a manual refresh.
    onLive((msg) => {
      if (msg.channel === "job" && (msg.kind === "pipeline")) {
        renderList().catch(console.error);
      }
      if (msg.channel === "automation_pipeline") {
        renderList().catch(console.error);
      }
    });
  }

  // ------------------------------------------------------------ EVOLUTION (Phase 7A, Part A)
  async function renderEvolution() {
    const myToken = activeRouteToken;

    async function render() {
      const [status, championsRes, strategiesRes, lessonsRes, versionsRes, correlationsRes] = await Promise.all([
        apiGet("/api/evolution/status"),
        apiGet("/api/evolution/champions"),
        apiGet("/api/evolution/strategies"),
        apiGet("/api/evolution/lessons"),
        apiGet("/api/evolution/knowledge-versions?limit=1"),
        apiGet("/api/evolution/research/dna-correlations?min_sample=1"),
      ]);
      if (isStaleRoute(myToken)) return;

      const gov = status.governor;
      const champions = championsRes.champions || [];
      const strategies = strategiesRes.strategies || [];
      const lessons = lessonsRes.lessons || [];
      const latestVersion = (versionsRes.versions || [])[0];
      const correlations = correlationsRes.correlations || [];

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
          <thead><tr><th>ID</th><th>Generation</th><th>Origin</th><th>Evolution Score</th><th>Created</th></tr></thead>
          <tbody>
            ${strategies.slice(0, 100).map(s => `
              <tr>
                <td>${esc(s.name)} <span class="muted">(${esc(s.id)})</span></td>
                <td>Gen ${s.generation}</td>
                <td><span class="pill ${s.made_with_ai ? "pill-bullish" : "pill-muted"}">${s.origin}</span></td>
                <td>${s.evolution_score != null ? Number(s.evolution_score).toFixed(2) : "not backtested"}</td>
                <td>${esc((s.created_at || "").slice(0, 19))}</td>
              </tr>`).join("") || '<tr><td colspan="5">No BOT strategies yet -- the Evolution Engine mutates existing lineages, and SINDHU Strategy creates new ones.</td></tr>'}
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

  // ------------------------------------------------------------ PAPER TRADING
  async function renderPaperTrading() {
    const myToken = activeRouteToken;
    const render = async () => {
      const [status, positionsRes, tradesRes, decisionsRes, stratPerfRes, lessonPerfRes,
             settings, strategiesRes, lessonsRes, allTimeAnalytics] = await Promise.all([
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
      ]);
      if (isStaleRoute(myToken)) return;

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

      content.innerHTML = `
        <div class="section-title">Paper Trading</div>
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

        <div class="section-title">Analytics</div>
        <div id="ptAnalyticsBox"></div>

        <div class="section-title">Daily Goal (${goalPct}%)</div>
        <div class="card">
          <div class="progress-bar"><div class="progress-bar-fill" style="width:${goalProgress}%;"></div></div>
          <div class="muted" style="margin-top:6px;font-size:12px;">Today's realized PnL: ${todaysPnlPct.toFixed(2)}% of ${goalPct}% goal (${todaysTrades.length} trades closed today)</div>
        </div>

        <div class="section-title">Control Center</div>
        <div class="btn-row">
          <button class="btn" id="ptStart" ${status.running ? "disabled" : ""}>Start Engine</button>
          <button class="btn-ghost" id="ptStop" ${status.running ? "" : "disabled"}>Stop Engine</button>
          <button class="btn-ghost" id="ptRunTick">Run One Tick Now</button>
          <label style="display:flex;align-items:center;gap:6px;width:auto;">
            <input type="checkbox" id="ptDryRun" ${settings.dry_run ? "checked" : ""} style="width:auto;"> Dry Run Mode
          </label>
          <span id="ptStatusMsg" class="muted"></span>
        </div>
        ${status.running ? `<div class="muted" style="font-size:12px;">Started ${esc((status.started_at||"").slice(0,19))} -- tick #${status.tick_count}, last at ${esc((status.last_tick_at||"-").slice(11,19))}</div>` : ""}

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
          </div>
          <span id="ptSettingsStatus" class="muted"></span>
        </div>

        <div class="grid">
          ${card("Strategies Available", fmtNum((strategiesRes.strategies || []).length))}
          ${card("Lessons Available (active)", fmtNum(runningLessons.length))}
        </div>

        <div class="section-title">Open Positions</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Coin</th><th>Direction</th><th>Entry</th><th>SL</th><th>TP</th><th>Size</th><th>Confidence</th><th>Source</th><th>Session</th><th></th></tr></thead>
          <tbody>${(positionsRes.positions || []).map(p => `
            <tr>
              <td>${esc(p.symbol)}</td>
              <td><span class="pill ${p.direction === "long" ? "pill-bullish" : "pill-bearish"}">${esc(p.direction)}</span></td>
              <td>${p.entry_price}</td>
              <td>${p.stop_loss != null ? p.stop_loss.toFixed(6) : "-"}</td>
              <td>${p.take_profit != null ? p.take_profit.toFixed(6) : "-"}</td>
              <td>${p.size.toFixed(4)}</td>
              <td>${p.confidence != null ? p.confidence + "%" : "-"}</td>
              <td>${esc(p.strategy_name || (p.lesson_ids||[]).length + " lesson(s)")}</td>
              <td>${esc(p.session || "-")}</td>
              <td><button class="btn-ghost pt-close-position" data-id="${p.id}">Close</button></td>
            </tr>`).join("") || '<tr><td colspan="10">No open positions.</td></tr>'}</tbody>
        </table></div>

        <div class="section-title">Closed Trades (most recent 30 of ${allTimeSummary.closed_trades})</div>
        <div class="table-wrap"><table>
          <thead><tr><th>Strategy</th><th>Coin</th><th>Direction</th><th>Entry</th><th>Exit</th><th>PnL</th><th>PnL%</th><th>Exit Reason</th><th>Tags</th><th></th></tr></thead>
          <tbody>${trades.slice(0, 30).map((t, idx) => `
            <tr>
              <td>${esc(t.strategy_name || "(lesson-only)")}</td>
              <td>${esc(t.symbol)}</td>
              <td><span class="pill ${t.direction === "long" ? "pill-bullish" : "pill-bearish"}">${esc(t.direction)}</span></td>
              <td>${t.entry_price}</td>
              <td>${t.exit_price != null ? t.exit_price : "-"}</td>
              <td class="${(t.pnl||0) >= 0 ? "pill-up" : "pill-down"}">${t.pnl != null ? t.pnl.toFixed(2) : "-"}</td>
              <td class="${(t.pnl_pct||0) >= 0 ? "pill-up" : "pill-down"}">${t.pnl_pct != null ? t.pnl_pct.toFixed(2) : "-"}%</td>
              <td>${esc(t.exit_reason || "-")}</td>
              <td>${(t.tags||[]).join(", ") || "-"}</td>
              <td><button class="btn-ghost pt-view-trade" data-idx="${idx}">Replay</button></td>
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

        <div class="two-col">
          <div>
            <div class="section-title">Strategy Performance</div>
            <div class="table-wrap"><table>
              <thead><tr><th>Strategy</th><th>Trades</th><th>Win Rate</th><th>PnL</th><th>Score</th></tr></thead>
              <tbody>${(stratPerfRes.performance || []).map(p => `
                <tr><td>${esc(p.strategy_name || p.strategy_id)}</td><td>${p.trades}</td>
                <td>${p.trades ? ((p.wins/p.trades)*100).toFixed(1) : "0.0"}%</td>
                <td>${p.total_pnl.toFixed(2)}</td><td>${p.score}</td></tr>`).join("") || '<tr><td colspan="5">No data yet.</td></tr>'}</tbody>
            </table></div>
          </div>
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
      `;

      loadPaperAnalytics("ptAnalyticsBox", "pt", "today");

      document.getElementById("ptStart").onclick = async () => {
        await apiPost("/api/paper-trading/start");
        appendLog("Paper Trading engine started.");
        render();
      };
      document.getElementById("ptStop").onclick = async () => {
        await apiPost("/api/paper-trading/stop");
        appendLog("Paper Trading engine stopped.");
        render();
      };
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
          });
          status.textContent = "Saved";
        } catch (e) {
          status.textContent = "Save failed (will retry)";
        }
      }, 600);
      ["ptMaxOpen", "ptCooldown", "ptRiskPct", "ptBalance", "ptTopN", "ptTickInterval", "ptDailyGoal"].forEach(id => {
        document.getElementById(id).addEventListener("input", saveEngineSettings);
      });
      ["ptPriorityRule", "ptOppositePolicy"].forEach(id => {
        document.getElementById(id).addEventListener("change", saveEngineSettings);
      });

      document.querySelectorAll(".pt-close-position").forEach(btn => {
        btn.onclick = async () => {
          await apiPost(`/api/paper-trading/positions/${btn.dataset.id}/close`);
          appendLog("Position closed manually.");
          render();
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
            `PnL: ${t.pnl} (${t.pnl_pct}%)  Duration: ${r.duration_minutes || "-"} min\n\n` +
            `Why Enter: ${r.why_enter || t.entry_reason || "-"}\n` +
            `Why Exit: ${r.why_exit || t.exit_reason || "-"}\n\n` +
            `Success: ${(r.success || []).join(" | ") || "-"}\n` +
            `Mistakes: ${(r.mistakes || []).join(" | ") || "-"}\n\n` +
            `Market State at Entry: ${JSON.stringify(t.market_snapshot || {}, null, 2)}`;
        };
      });
    };

    await render();
    onLive((msg) => {
      if (msg.channel === "paper") render().catch(console.error);
    });
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
      <div class="section-title">Backup</div>
      <div class="card">
        <div class="btn-row"><button class="btn" id="btnBackupNow">Create Backup Now</button></div>
        <div id="backupList" class="table-wrap"></div>
      </div>`;

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

      <div class="section-title">CEO Dashboard</div>
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
          <input type="file" id="aiFile" accept=".pdf,.docx,.txt,.md">
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

      <div class="section-title">CEO Settings</div>
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
    "home", "market", "data", "strategies", "knowledge", "knowledge_compiler",
    "ai_center", "backtesting", "backtest_history", "pipeline_history", "paper_trading",
    "evolution", "sindhu_strategy", "reports", "settings",
  ];
  const CEO_LABELS = {
    home: "Dashboard", market: "Market", data: "Data", strategies: "Strategies",
    knowledge: "Knowledge", knowledge_compiler: "Knowledge Compiler", ai_center: "AI Center",
    backtesting: "Backtesting", backtest_history: "Backtest History",
    pipeline_history: "Pipeline History",
    paper_trading: "Paper Trading", evolution: "Evolution", sindhu_strategy: "SINDHU Strategy",
    reports: "Reports", settings: "Settings",
  };

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
             sindhuDailyLog, sindhuCandidates] = await Promise.all([
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
          return {
            level: pending ? "active" : (d.aiDash.failed_imports ? "attention" : "idle"),
            text: `${d.aiDash.total_strategies ?? 0} strategies, ${d.aiDash.total_lessons ?? 0} lessons imported${pending ? `, ${pending} pending` : ""}`,
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
      document.querySelectorAll("[data-ceo-card]").forEach(el => {
        el.onclick = () => showExpanded(el.dataset.ceoCard);
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
          await apiPost("/api/backtesting/run", { strategy_id: btn.dataset.id, all_coins: true });
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
            await apiPost("/api/backtesting/run", { strategy_id: readyToRun.id, all_coins: true });
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
