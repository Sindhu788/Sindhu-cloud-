/* SINDHU v2 component helpers (master plan V2 DS2 / W2). Classic script; everything hangs off window.S2. No framework, no CDN. */
(function () {
  "use strict";
  const S2 = (window.S2 = window.S2 || {});

  // ---------- assets (hashed URLs from the server, see sindhu_web/assets.py)
  let _assets = null;
  S2.asset = function (logical) {
    if (!_assets) {
      try { _assets = JSON.parse(document.getElementById("sindhu-assets").textContent || "{}"); } catch (e) { _assets = {}; }
    }
    return _assets[logical] || "/static/" + logical;
  };
  S2.SPRITE = () => S2.asset("vendor/lucide-sprite.svg");

  // ---------- DOM
  S2.esc = function (s) {
    return String(s === null || s === undefined ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  };
  S2.h = function (tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "html") el.innerHTML = v;
      else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
      else if (k === "dataset") Object.assign(el.dataset, v);
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) {
      if (kid === null || kid === undefined || kid === false) continue;
      el.appendChild(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
    return el;
  };
  S2.icon = function (name, cls) {
    return `<svg class="icon ${cls || ""}" aria-hidden="true"><use href="${S2.SPRITE()}#i-${name}"></use></svg>`;
  };
  S2.iconEl = function (name, cls) { const s = document.createElement("span"); s.innerHTML = S2.icon(name, cls); return s.firstChild; };

  // ---------- formatting (units always shown)
  S2.fmt = {
    money(v, dp) { if (v === null || v === undefined || isNaN(v)) return "--"; const n = Number(v); return (n < 0 ? "-$" : "$") + Math.abs(n).toFixed(dp === undefined ? 2 : dp); },
    signedMoney(v) { if (v === null || v === undefined || isNaN(v)) return "--"; const n = Number(v); return (n > 0 ? "+$" : n < 0 ? "-$" : "$") + Math.abs(n).toFixed(2); },
    pct(v, dp) { if (v === null || v === undefined || isNaN(v)) return "--"; return Number(v).toFixed(dp === undefined ? 2 : dp) + "%"; },
    signedPct(v, dp) { if (v === null || v === undefined || isNaN(v)) return "--"; const n = Number(v); return (n > 0 ? "+" : "") + n.toFixed(dp === undefined ? 2 : dp) + "%"; },
    num(v, dp) { if (v === null || v === undefined || isNaN(v)) return "--"; return Number(v).toLocaleString("en-US", { maximumFractionDigits: dp === undefined ? 2 : dp, minimumFractionDigits: dp || 0 }); },
    price(v) { if (v === null || v === undefined || isNaN(v)) return "--"; const n = Number(v); const dp = n >= 1000 ? 2 : n >= 1 ? 4 : n >= 0.01 ? 6 : 8; return n.toFixed(dp); },
    utc(iso) { if (!iso) return "--"; const d = new Date(iso); if (isNaN(d)) return String(iso); return d.toISOString().slice(0, 16).replace("T", " ") + " UTC"; },
    time(iso) { if (!iso) return "--"; const d = new Date(iso); if (isNaN(d)) return "--"; return d.toISOString().slice(11, 16); },
    ago(iso) {
      if (!iso) return "--"; const t = Date.parse(iso); if (isNaN(t)) return "--";
      const s = Math.max(0, Math.round((Date.now() - t) / 1000));
      return s < 90 ? `${s} sec pehle` : s < 5400 ? `${Math.round(s / 60)} min pehle` : s < 172800 ? `${Math.round(s / 3600)} ghante pehle` : `${Math.round(s / 86400)} din pehle`;
    },
    dur(sec) { if (sec === null || sec === undefined || isNaN(sec)) return "--"; sec = Math.round(sec); if (sec < 120) return sec + " s"; if (sec < 7200) return Math.round(sec / 60) + " min"; return (sec / 3600).toFixed(1) + " h"; },
  };
  S2.cls = v => (v > 0 ? "up" : v < 0 ? "down" : "");

  // ---------- API (same-origin cookie session). Every write carries X-Sindhu-Token (fetched from the same-origin /api/token; a
  // cross-site page cannot read it), which is the anti-CSRF check of sindhu_web/security.py.
  let _tok = null;
  async function writeToken(force) {
    if (_tok && !force) return _tok;
    const r = await fetch("/api/token", { credentials: "same-origin" });
    _tok = r.ok ? (await r.json()).token : "";
    return _tok;
  }
  S2.api = async function (path, opts, _retried) {
    opts = opts || {};
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), opts.timeout || 20000);
    const headers = { Accept: "application/json" };
    const write = opts.method && opts.method !== "GET";
    if (opts.body !== undefined) headers["Content-Type"] = "application/json";
    try {
      if (write) headers["X-Sindhu-Token"] = await writeToken(false);
      const r = await fetch(path, { method: opts.method || "GET", headers, body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
        credentials: "same-origin", signal: ctrl.signal });
      const text = await r.text();
      let data = null; try { data = text ? JSON.parse(text) : null; } catch (e) { data = { detail: text.slice(0, 200) }; }
      if (r.status === 401 && write && !_retried && String((data && data.detail) || "").includes("X-Sindhu-Token")) {
        await writeToken(true); return S2.api(path, opts, true);
      }
      if (r.status === 401 && !opts.noRedirect) { location.href = "/login"; throw new Error("login required"); }
      if (!r.ok) { const err = new Error((data && (data.detail || data.message)) || `HTTP ${r.status}`); err.status = r.status; err.data = data; throw err; }
      return data;
    } catch (e) {
      if (e.name === "AbortError") { const err = new Error("Server ne waqt par jawab nahi diya"); err.timeout = true; throw err; }
      throw e;
    } finally { clearTimeout(timer); }
  };

  // ---------- badges
  const BADGE = { ROBUST: "robust", FRAGILE: "fragile", FAILED: "failed", INSUFFICIENT_DATA: "insufficient", INSUFFICIENT: "insufficient",
    PAPER: "paper", RESEARCH: "research", PAUSED: "paused", STALE: "stale", LIVE: "live" };
  const BADGE_TEXT = { INSUFFICIENT_DATA: "Insufficient", STALE: "Data purana" };
  S2.badge = function (kind, text) {
    const k = String(kind || "").toUpperCase();
    return `<span class="badge ${BADGE[k] || ""}">${S2.esc(text || BADGE_TEXT[k] || k.replace(/_/g, " ").toLowerCase() || "--")}</span>`;
  };

  // ---------- toast
  S2.toast = function (msg, kind) {
    let box = document.querySelector(".toasts");
    if (!box) { box = S2.h("div", { class: "toasts", role: "status", "aria-live": "polite" }); document.body.appendChild(box); }
    const t = S2.h("div", { class: "toast " + (kind || "") }, S2.iconEl(kind === "err" ? "circle-x" : kind === "warn" ? "triangle-alert" : "circle-check"), S2.h("div", {}, msg));
    box.appendChild(t);
    setTimeout(() => t.remove(), kind === "err" ? 7000 : 3500);
  };

  // ---------- modal (in-page, focus-trapped, Esc closes)
  S2.modal = function (o) {
    return new Promise(resolve => {
      const prev = document.activeElement;
      const okBtn = S2.h("button", { class: "btn " + (o.danger ? "danger" : "primary"), type: "button" }, o.ok || "OK");
      const cancelBtn = o.cancel === false ? null : S2.h("button", { class: "btn", type: "button" }, o.cancel || "Cancel");
      const body = typeof o.body === "string" ? S2.h("div", { class: "m-b" }, o.body) : S2.h("div", { class: "m-b" }, o.body || "");
      const box = S2.h("div", { class: "modal", role: "dialog", "aria-modal": "true", "aria-labelledby": "s2mT" },
        S2.h("div", { class: "m-h" }, S2.h("h3", { id: "s2mT" }, o.title || "")), body, S2.h("div", { class: "m-f" }, cancelBtn, okBtn));
      const bg = S2.h("div", { class: "modal-bg" }, box);
      const done = v => { bg.remove(); document.removeEventListener("keydown", key, true); if (prev && prev.focus) prev.focus(); resolve(v); };
      const key = e => {
        if (e.key === "Escape") { e.preventDefault(); done(false); }
        if (e.key === "Tab") {
          const f = [...box.querySelectorAll("button, input, select, textarea, a[href], [tabindex]:not([tabindex='-1'])")].filter(x => !x.disabled);
          if (!f.length) return;
          if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
          else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
        }
      };
      okBtn.addEventListener("click", () => done(o.collect ? o.collect(box) : true));
      if (cancelBtn) cancelBtn.addEventListener("click", () => done(false));
      bg.addEventListener("mousedown", e => { if (e.target === bg) done(false); });
      document.addEventListener("keydown", key, true);
      document.body.appendChild(bg);
      (cancelBtn || okBtn).focus();
    });
  };
  S2.confirm = (title, text, ok, danger) => S2.modal({ title, body: text, ok, danger });

  // ---------- loading / empty / error (U7, U9)
  S2.skeleton = function (lines, cls) {
    return `<div class="stack-sm" aria-busy="true" aria-label="Loading">${Array.from({ length: lines || 3 }, (_, i) =>
      `<span class="sk ${cls || ""} ${i === (lines || 3) - 1 ? "w-60" : ""}"></span>`).join("")}</div>`;
  };
  S2.empty = function (title, text, icon) {
    return `<div class="empty">${S2.icon(icon || "info")}<h4>${S2.esc(title)}</h4>${text ? `<p>${S2.esc(text)}</p>` : ""}</div>`;
  };
  S2.errorBlock = function (err, retryId) {
    const offline = navigator.onLine === false;
    const slow = err && (err.timeout || err.status === 502 || err.status === 503);
    const title = offline ? "Internet nahi hai" : slow ? "Cloud jaag raha hai (free plan), 1 minute" : "Yeh data abhi load nahi hua";
    const text = offline ? "Phone ya laptop ka internet band lag raha hai. Connection aate hi Dobara try karo dabao."
      : slow ? "Free server so jaata hai; pehli request par uthne mein ~1 minute lagta hai. Thodi der baad dobara try karo."
      : "Server se jawab nahi aaya ya galti aayi. Baaki page chalta rahega.";
    return `<div class="err-block" role="alert">${S2.icon("triangle-alert")}<h4>${title}</h4><p>${text}</p>` +
      (err && err.message ? `<code>${S2.esc(String(err.message).slice(0, 160))}</code>` : "") +
      (retryId ? `<div><button class="btn sm" id="${retryId}" type="button">${S2.icon("refresh-cw")}Dobara try karo</button></div>` : "") + `</div>`;
  };

  // ---------- tabs
  S2.tabs = function (container, tabs, onChange, initial) {
    const bar = S2.h("div", { class: "tabs", role: "tablist" });
    let current = initial || tabs[0].id;
    const btns = tabs.map(t => {
      const b = S2.h("button", { role: "tab", type: "button", id: "tab-" + t.id, "aria-selected": String(t.id === current), tabindex: t.id === current ? "0" : "-1" });
      b.innerHTML = S2.esc(t.label) + (t.count !== undefined ? `<span class="count">${S2.esc(t.count)}</span>` : "");
      b.addEventListener("click", () => select(t.id));
      b.addEventListener("keydown", e => {
        const i = tabs.findIndex(x => x.id === current);
        if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
          e.preventDefault(); const n = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length]; select(n.id); bar.querySelector("#tab-" + n.id).focus();
        }
      });
      bar.appendChild(b); return b;
    });
    function select(id) {
      current = id;
      btns.forEach((b, i) => { const on = tabs[i].id === id; b.setAttribute("aria-selected", String(on)); b.tabIndex = on ? 0 : -1; });
      onChange(id);
    }
    container.appendChild(bar);
    onChange(current);
    return { select };
  };

  // ---------- table (U5): sticky header, sort, filter, pagination 20, tabular digits, density, CSV export, empty state, expandable rows
  S2.table = function (container, o) {
    const pageSize = o.pageSize || 20;
    let sortKey = o.sortKey || null, sortDir = o.sortDir || "desc", page = 0, q = "", dense = !!o.dense, filters = {};
    const root = S2.h("div", { class: "card" });
    const bar = S2.h("div", { class: "tbl-bar" });
    const search = S2.h("input", { class: "input", type: "search", placeholder: o.searchPlaceholder || "Filter...", "aria-label": "Filter rows" });
    if (o.search !== false) bar.appendChild(search);
    for (const f of o.filters || []) {
      const sel = S2.h("select", { class: "select", "aria-label": f.label });
      sel.appendChild(S2.h("option", { value: "" }, f.label + ": all"));
      const vals = [...new Set(o.rows.map(r => f.get ? f.get(r) : r[f.key]).filter(v => v !== null && v !== undefined && v !== ""))].sort();
      vals.forEach(v => sel.appendChild(S2.h("option", { value: v }, v)));
      sel.addEventListener("change", () => { filters[f.key] = sel.value; page = 0; draw(); });
      bar.appendChild(sel);
    }
    bar.appendChild(S2.h("span", { class: "grow" }));
    const densBtn = S2.h("button", { class: "btn sm ghost", type: "button", "aria-pressed": String(dense), title: "Row density" }, "Dense");
    densBtn.addEventListener("click", () => { dense = !dense; densBtn.setAttribute("aria-pressed", String(dense)); draw(); });
    bar.appendChild(densBtn);
    if (o.csv) {
      const csvBtn = S2.h("button", { class: "btn sm", type: "button" });
      csvBtn.innerHTML = S2.icon("download") + "CSV";
      csvBtn.addEventListener("click", () => S2.downloadCsv(o.csv, o.columns, visibleRows()));
      bar.appendChild(csvBtn);
    }
    if (o.toolbar) bar.appendChild(o.toolbar);
    root.appendChild(bar);
    const wrap = S2.h("div", { class: "tbl-wrap" });
    const foot = S2.h("div", { class: "tbl-foot" });
    root.appendChild(wrap); root.appendChild(foot);
    container.appendChild(root);
    search.addEventListener("input", () => { q = search.value.trim().toLowerCase(); page = 0; draw(); });

    function cell(c, r) { const v = c.get ? c.get(r) : r[c.key]; return v; }
    function visibleRows() {
      let rows = o.rows.slice();
      for (const [k, v] of Object.entries(filters)) if (v) { const f = (o.filters || []).find(x => x.key === k); rows = rows.filter(r => String(f && f.get ? f.get(r) : r[k]) === v); }
      if (q) rows = rows.filter(r => o.columns.some(c => String(cell(c, r) === null || cell(c, r) === undefined ? "" : cell(c, r)).toLowerCase().includes(q)));
      if (sortKey) {
        const c = o.columns.find(x => x.key === sortKey);
        rows.sort((a, b) => {
          let x = cell(c, a), y = cell(c, b);
          const nx = Number(x), ny = Number(y);
          if (x !== null && y !== null && x !== "" && y !== "" && !isNaN(nx) && !isNaN(ny)) { x = nx; y = ny; }
          if (x === y) return 0; if (x === null || x === undefined) return 1; if (y === null || y === undefined) return -1;
          return (x < y ? -1 : 1) * (sortDir === "asc" ? 1 : -1);
        });
      }
      return rows;
    }
    function draw() {
      const rows = visibleRows();
      const pages = Math.max(1, Math.ceil(rows.length / pageSize));
      page = Math.min(page, pages - 1);
      const slice = rows.slice(page * pageSize, page * pageSize + pageSize);
      if (!o.rows.length) { wrap.innerHTML = S2.empty(o.emptyTitle || "Abhi kuch nahi", o.emptyText || ""); foot.innerHTML = ""; return; }
      const head = o.columns.map(c => {
        const sorted = sortKey === c.key ? (sortDir === "asc" ? "ascending" : "descending") : "none";
        return `<th scope="col" class="${c.num ? "num" : ""} ${c.sort === false ? "" : "sortable"}" data-k="${S2.esc(c.key)}" aria-sort="${sorted}"` +
          `${c.sort === false ? "" : ' tabindex="0"'}>${S2.esc(c.label)}${c.sort === false ? "" : `<span class="sort">${sortKey === c.key ? (sortDir === "asc" ? "&#9650;" : "&#9660;") : "&#8645;"}</span>`}</th>`;
      }).join("");
      const body = slice.length ? slice.map((r, i) => {
        const tds = o.columns.map(c => {
          const v = cell(c, r);
          const html = c.render ? c.render(v, r) : S2.esc(c.fmt ? c.fmt(v, r) : (v === null || v === undefined || v === "" ? "--" : v));
          const cc = typeof c.cls === "function" ? c.cls(v, r) : (c.cls || "");
          return `<td class="${c.num ? "num" : ""} ${cc}">${html}</td>`;
        }).join("");
        return `<tr class="${o.expand ? "expandable" : ""}" data-i="${page * pageSize + i}" ${o.expand ? 'tabindex="0" aria-expanded="false"' : ""}>${tds}</tr>`;
      }).join("") : `<tr><td colspan="${o.columns.length}">${S2.empty("Is filter par kuch nahi mila", "Filter hatao ya doosra word likho.", "search")}</td></tr>`;
      wrap.innerHTML = `<table class="tbl ${dense ? "dense" : ""}"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
      wrap.querySelectorAll("th.sortable").forEach(th => {
        const go = () => { const k = th.dataset.k; if (sortKey === k) sortDir = sortDir === "asc" ? "desc" : "asc"; else { sortKey = k; sortDir = "desc"; } draw(); };
        th.addEventListener("click", go); th.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
      });
      if (o.expand) wrap.querySelectorAll("tr.expandable").forEach(tr => {
        const toggle = () => {
          const nx = tr.nextElementSibling;
          if (nx && nx.classList.contains("detail")) { nx.remove(); tr.setAttribute("aria-expanded", "false"); return; }
          const d = S2.h("tr", { class: "detail" }, S2.h("td", { colspan: o.columns.length }));
          const content = o.expand(rows[Number(tr.dataset.i)]);
          if (typeof content === "string") d.firstChild.innerHTML = content; else d.firstChild.appendChild(content);
          tr.after(d); tr.setAttribute("aria-expanded", "true");
        };
        tr.addEventListener("click", toggle); tr.addEventListener("keydown", e => { if (e.key === "Enter") toggle(); });
      });
      foot.innerHTML = `<span class="grow">${rows.length.toLocaleString()} rows${rows.length !== o.rows.length ? ` of ${o.rows.length.toLocaleString()}` : ""}</span>` +
        `<button class="btn sm ghost" type="button" data-p="prev" ${page === 0 ? "disabled" : ""} aria-label="Previous page">${S2.icon("chevron-left")}</button>` +
        `<span class="mono">${page + 1} / ${pages}</span>` +
        `<button class="btn sm ghost" type="button" data-p="next" ${page >= pages - 1 ? "disabled" : ""} aria-label="Next page">${S2.icon("chevron-right")}</button>`;
      foot.querySelectorAll("[data-p]").forEach(b => b.addEventListener("click", () => { page += b.dataset.p === "next" ? 1 : -1; draw(); }));
    }
    draw();
    return { redraw: draw, setRows(rows) { o.rows = rows; draw(); } };
  };

  S2.downloadCsv = function (name, columns, rows) {
    const q = v => { const s = v === null || v === undefined ? "" : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
    const lines = [columns.map(c => q(c.label)).join(",")].concat(rows.map(r => columns.map(c => q(c.csv ? c.csv(r) : c.get ? c.get(r) : r[c.key])).join(",")));
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const a = S2.h("a", { href: URL.createObjectURL(blob), download: `${name}_${new Date().toISOString().slice(0, 10)}.csv` });
    document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  };

  // ---------- charts (U8): uPlot, lazy-loaded once, themed from CSS variables
  let _uplot = null;
  S2.loadScript = function (src) {
    return new Promise((res, rej) => { const s = document.createElement("script"); s.src = src; s.onload = res; s.onerror = rej; document.head.appendChild(s); });
  };
  S2.loadCss = function (href) {
    if (document.querySelector(`link[href="${href}"]`)) return;
    document.head.appendChild(S2.h("link", { rel: "stylesheet", href }));
  };
  S2.uplot = function () {
    if (!_uplot) { S2.loadCss(S2.asset("vendor/uplot-1.6.31.min.css")); _uplot = S2.loadScript(S2.asset("vendor/uplot-1.6.31.iife.min.js")).then(() => window.uPlot); }
    return _uplot;
  };
  function cssVar(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
  // series: [{label, values, color: "accent"|"profit"|"loss"|"warn"|"text-3", fill: true}], x: array of unix seconds
  S2.chart = async function (el, o) {
    if (!o.x || o.x.length < 2) { el.innerHTML = `<div class="chart-empty">${S2.esc(o.emptyText || "Chart ke liye abhi kaafi data nahi")}</div>`; return null; }
    el.innerHTML = `<span class="sk h-160"></span>`;
    let uPlot;
    try { uPlot = await S2.uplot(); } catch (e) { el.innerHTML = `<div class="chart-empty">Chart load nahi hua</div>`; return null; }
    el.innerHTML = "";
    const grid = { stroke: cssVar("--line-soft"), width: 1 }, axisStroke = cssVar("--text-3");
    const width = Math.max(240, el.clientWidth || 600), height = o.height || 220;
    const opts = {
      width, height, padding: [8, 8, 0, 0], cursor: { y: false, points: { size: 6 } }, legend: { show: o.legend !== false, live: true },
      scales: { x: { time: o.time !== false } },
      axes: [{ stroke: axisStroke, grid, ticks: { stroke: grid.stroke }, font: `11px ${cssVar("--font-mono") || "monospace"}` },
             { stroke: axisStroke, grid, ticks: { stroke: grid.stroke }, size: 64, font: `11px ${cssVar("--font-mono") || "monospace"}`,
               values: (u, v) => v.map(x => (o.yFmt ? o.yFmt(x) : x)) }],
      series: [{}].concat(o.series.map(s => {
        const c = cssVar("--" + (s.color || "accent"));
        return { label: s.label, stroke: c, width: 1.5, fill: s.fill ? c + "22" : undefined, points: { show: false },
                 value: (u, v) => (v === null || v === undefined ? "--" : o.yFmt ? o.yFmt(v) : v) };
      })),
    };
    const u = new uPlot(opts, [o.x].concat(o.series.map(s => s.values)), el);
    const ro = new ResizeObserver(() => { if (el.isConnected) u.setSize({ width: Math.max(240, el.clientWidth), height }); else ro.disconnect(); });
    ro.observe(el);
    return u;
  };
})();
