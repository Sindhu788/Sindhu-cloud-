/* SINDHU v2 app shell (master plan V2 PG1 / W3): sidebar (desktop), bottom tabs + More sheet (phone), top bar with the paper-trading
   tag, kill switch, data-freshness dot, theme toggle and user menu; hash router; footer with the build tag. */
(function () {
  "use strict";
  const S2 = window.S2, h = S2.h, esc = S2.esc, icon = S2.icon;
  S2.pages = S2.pages || {};

  const NAV = [
    { id: "home", label: "Home", icon: "house" },
    { id: "trades", label: "Trades", icon: "arrow-left-right" },
    { id: "strategies", label: "Strategies", icon: "layers" },
    { id: "backtests", label: "Backtests", icon: "flask-conical" },
    { id: "settings", label: "Settings", icon: "settings" },
    { id: "system", label: "System", icon: "activity" },
  ];
  const TABBAR = ["home", "trades", "strategies", "backtests"];
  // old hash ids (legacy app) -> new page; anything else opens in /legacy so no bookmark breaks
  const OLD = { wallet: "home", paper_trading: "trades", strategies: "strategies", backtesting: "backtests", settings: "settings",
                configuration_panel: "settings", control_center: "system", project_status: "system" };
  S2.NAV = NAV;

  let ctx = { theme: "dark" };
  const state = { ks: null, fresh: null, details: null, timer: null, route: null };

  function setTheme(t) {
    ctx.theme = t;
    document.documentElement.setAttribute("data-theme", t);
    try { localStorage.setItem("sindhu_theme", t); } catch (e) { /* private mode */ }
    const b = document.getElementById("themeBtn");
    if (b) { b.innerHTML = icon(t === "dark" ? "sun" : "moon"); b.setAttribute("aria-label", t === "dark" ? "Light theme" : "Dark theme"); b.dataset.tip = t === "dark" ? "Light theme" : "Dark theme"; }
    window.dispatchEvent(new CustomEvent("s2:theme", { detail: t }));
  }

  function shellHtml() {
    const nav = NAV.map(n => `<a href="#/${n.id}" data-id="${n.id}">${icon(n.icon, "lg")}<span class="lbl">${n.label}</span></a>`).join("");
    const tabs = TABBAR.map(id => { const n = NAV.find(x => x.id === id); return `<a href="#/${id}" data-id="${id}">${icon(n.icon)}<span>${n.label}</span></a>`; }).join("") +
      `<a href="#/more" data-id="more">${icon("ellipsis")}<span>More</span></a>`;
    return `
    <a class="sr-only" href="#main">Skip to content</a>
    <div class="shell" id="shell">
      <aside class="side" aria-label="Main menu">
        <div class="brand"><span class="mark">S</span><span class="word">SINDHU</span></div>
        <nav>${nav}<div class="sep"></div>
          <a href="#/more" data-id="more">${icon("ellipsis", "lg")}<span class="lbl">More / Legacy</span></a>
        </nav>
        <div class="foot"><span>Paper trading only</span><span class="mono" id="sideBuild"></span></div>
        <button class="btn ghost sm" id="railBtn" type="button" aria-label="Collapse menu" style="margin:8px 4px 0">${icon("panel-left")}</button>
      </aside>
      <div class="main">
        <header class="topbar2">
          <span class="paper" title="No real money is used anywhere in SINDHU">PAPER<span class="long"> TRADING</span> &mdash; real paisa nahi</span>
          <span class="row" style="gap:6px" id="freshBox" data-tip="Candle data freshness"><span class="dot" id="freshDot"></span><span class="t-hint" id="freshTxt">data ...</span></span>
          <span class="grow"></span>
          <span class="t-hint mono" id="clock" aria-label="UTC time"></span>
          <span id="ksBox" class="row" style="gap:8px"></span>
          <button class="btn ghost icon-only" id="themeBtn" type="button"></button>
          <span style="position:relative">
            <button class="btn ghost icon-only" id="userBtn" type="button" aria-haspopup="menu" aria-expanded="false" aria-label="Account" data-tip="Account">${icon("user")}</button>
            <div class="menu" id="userMenu" role="menu" hidden>
              <a href="#/settings?g=security" role="menuitem">${icon("lock")}Password &amp; login</a>
              <a href="/legacy" role="menuitem">${icon("external-link")}Old dashboard (legacy)</a>
              <button type="button" role="menuitem" id="logoutBtn">${icon("log-out")}Logout</button>
            </div>
          </span>
        </header>
        <main id="main" class="page" tabindex="-1"></main>
        <footer class="app-foot"><span>SINDHU paper-trading research desk</span><span class="mono" id="buildTag"></span>
          <span>Not financial advice. Past results do not predict future results.</span></footer>
      </div>
    </div>
    <nav class="tabbar" aria-label="Main menu (phone)">${tabs}</nav>`;
  }

  function build() { try { return JSON.parse(document.getElementById("sindhu-build").textContent || '""'); } catch (e) { return ""; } }

  async function logout() {
    try { await S2.api("/api/auth/logout", { method: "POST", body: {}, noRedirect: true }); } catch (e) { /* go to login anyway */ }
    location.href = "/login";
  }

  function drawKillSwitch() {
    const box = document.getElementById("ksBox"); if (!box) return;
    const ks = state.ks;
    if (!ks) { box.innerHTML = ""; return; }
    box.innerHTML = ks.active
      ? `<span class="ks-on">${icon("power")}<span class="lbl"> Trading stopped</span></span><button class="btn sm" id="ksBtn" type="button">Resume</button>`
      : `<button class="btn sm danger outline" id="ksBtn" type="button" data-tip="Stops all new paper entries">${icon("power")}<span class="lbl-ks">Kill switch</span></button>`;
    document.getElementById("ksBtn").addEventListener("click", toggleKs);
  }

  async function toggleKs() {
    const active = state.ks && state.ks.active;
    const ok = active
      ? await S2.confirm("Resume trading?", "New paper entries will be allowed again. Every safety gate still applies.", "Resume", false)
      : await S2.confirm("Stop all trading now?", "No new paper entries until you resume. Open positions stay open and keep their stops.", "Stop trading", true);
    if (!ok) return;
    try {
      if (active) await S2.api("/api/paper-trading/kill-switch/deactivate", { method: "POST", body: { actor: "owner (dashboard v2)" } });
      else await S2.api("/api/paper-trading/kill-switch/activate", { method: "POST", body: { reason: "owner pressed the kill switch (dashboard v2)", close_positions: false, actor: "owner (dashboard v2)" } });
      S2.toast(active ? "Trading resumed" : "Trading stopped. Positions stay open.", active ? "" : "warn");
    } catch (e) { S2.toast("Kill switch change failed: " + e.message, "err"); }
    refreshStatus();
  }

  async function refreshStatus() {
    if (document.hidden) return;
    try { state.ks = await S2.api("/api/paper-trading/kill-switch/status", { noRedirect: true }); } catch (e) { /* keep last */ }
    drawKillSwitch();
    try {
      const d = state.details = await S2.api("/health/details", { noRedirect: true, timeout: 15000 });
      const c = d.candles;
      const dot = document.getElementById("freshDot"), txt = document.getElementById("freshTxt");
      if (c && c.series) {
        const share = c.stale / c.series;
        dot.className = "dot " + (share > 0.5 ? "bad" : share > 0.2 ? "warn" : "ok");
        txt.textContent = `${c.fresh}/${c.series} fresh`;
      } else { dot.className = "dot"; txt.textContent = "data: local"; }
    } catch (e) {
      document.getElementById("freshDot").className = "dot bad";
      document.getElementById("freshTxt").textContent = "server slow";
    }
  }

  function tickClock() { const el = document.getElementById("clock"); if (el) el.textContent = new Date().toISOString().slice(11, 16) + " UTC"; }

  function parseHash() {
    let raw = (location.hash || "").replace(/^#\/?/, "");
    let q = {};
    const i = raw.indexOf("?");
    if (i >= 0) { new URLSearchParams(raw.slice(i + 1)).forEach((v, k) => { q[k] = v; }); raw = raw.slice(0, i); }
    return { id: raw || "home", q };
  }

  async function route() {
    const { id: rawId, q } = parseHash();
    let id = rawId;
    if (!S2.pages[id]) {
      if (OLD[id]) { location.replace("#/" + OLD[id]); return; }
      if (/^[a-z_]+$/.test(id) && id !== "404") { location.href = "/legacy#" + id; return; }
      id = "404";
    }
    state.route = id;
    document.querySelectorAll("[data-id]").forEach(a => { if (a.dataset.id === id) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
    const page = S2.pages[id];
    const main = document.getElementById("main");
    document.title = (page.title ? page.title + " - " : "") + "SINDHU";
    main.innerHTML = `<div class="page-h"><div><div class="crumb">${esc(page.crumb || "SINDHU")}</div><h1>${esc(page.title)}</h1></div>
      <div class="actions" id="pageActions"></div></div><div id="pageBody">${S2.skeleton(4, "h-24")}</div>`;
    if (S2._cleanup) { try { S2._cleanup(); } catch (e) { /* ignore */ } S2._cleanup = null; }
    const token = (S2._routeToken = (S2._routeToken || 0) + 1);
    try {
      await page.render(document.getElementById("pageBody"), { q, actions: document.getElementById("pageActions"), stale: () => token !== S2._routeToken, ctx });
    } catch (e) {
      if (token === S2._routeToken) document.getElementById("pageBody").innerHTML = S2.errorBlock(e, "pageRetry");
      const b = document.getElementById("pageRetry"); if (b) b.addEventListener("click", route);
    }
    if (q.focus !== "keep") main.focus({ preventScroll: true });
  }
  S2.route = route;
  S2.go = id => { location.hash = "#/" + id; };

  S2.pages["404"] = {
    title: "Page not found", crumb: "SINDHU",
    render(el) {
      el.innerHTML = `<div class="card"><div class="empty">${icon("circle-help")}<h4>Yeh page nahi mila</h4>
        <p>Link purana ho sakta hai. Neeche se apni jagah chuno, ya purane dashboard mein dekho.</p>
        <div class="row wrap"><a class="btn primary" href="#/home">${icon("house")}Home</a><a class="btn" href="/legacy">${icon("external-link")}Old dashboard</a></div></div></div>`;
    },
  };

  function start() {
    let t = "dark";
    try { t = localStorage.getItem("sindhu_theme") || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"); } catch (e) { /* default */ }
    document.getElementById("app").innerHTML = shellHtml();
    setTheme(t);
    const b = build();
    document.getElementById("buildTag").textContent = "build " + b;
    document.getElementById("sideBuild").textContent = b;
    document.getElementById("themeBtn").addEventListener("click", () => setTheme(ctx.theme === "dark" ? "light" : "dark"));
    const ub = document.getElementById("userBtn"), um = document.getElementById("userMenu");
    ub.addEventListener("click", e => { e.stopPropagation(); const open = um.hidden; um.hidden = !open; ub.setAttribute("aria-expanded", String(open)); if (open) um.querySelector("a,button").focus(); });
    document.addEventListener("click", e => { if (!um.hidden && !um.contains(e.target)) { um.hidden = true; ub.setAttribute("aria-expanded", "false"); } });
    um.addEventListener("keydown", e => { if (e.key === "Escape") { um.hidden = true; ub.focus(); } });
    document.getElementById("logoutBtn").addEventListener("click", logout);
    const shell = document.getElementById("shell");
    try { if (localStorage.getItem("sindhu_rail") === "1") shell.classList.add("collapsed"); } catch (e) { /* ignore */ }
    document.getElementById("railBtn").addEventListener("click", () => {
      shell.classList.toggle("collapsed");
      try { localStorage.setItem("sindhu_rail", shell.classList.contains("collapsed") ? "1" : "0"); } catch (e) { /* ignore */ }
    });
    window.addEventListener("hashchange", route);
    window.addEventListener("offline", () => S2.toast("Internet chala gaya. Data purana ho sakta hai.", "warn"));
    window.addEventListener("online", () => { S2.toast("Internet wapas aa gaya"); refreshStatus(); });
    document.addEventListener("visibilitychange", () => { if (!document.hidden) refreshStatus(); });
    tickClock(); setInterval(tickClock, 15000);
    refreshStatus(); state.timer = setInterval(refreshStatus, 60000);
    route();
  }
  S2.status = state;
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start); else setTimeout(start, 0);
})();
