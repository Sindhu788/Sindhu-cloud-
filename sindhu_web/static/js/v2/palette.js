/* Command palette and shortcuts (master plan V2 PG10 / W12): Ctrl/Cmd+K jumps to any page, coin or strategy; "g h" Home, "g t" Trades,
   "g s" Strategies, "g b" Backtests, "g y" System, "g ," Settings; "?" lists the shortcuts. Keyboard only; nothing changes on phones. */
(function () {
  "use strict";
  const S2 = window.S2, esc = S2.esc, icon = S2.icon;
  let extra = null;

  async function loadExtra() {
    if (extra) return extra;
    extra = [];
    try {
      const ov = await S2.api("/api/paper-trading/strategy-overview", { noRedirect: true });
      (ov.strategies || []).forEach(s => extra.push({ label: s.name, hint: "strategy", go: () => { location.hash = "#/strategies"; } }));
    } catch (e) { /* pages still work */ }
    try {
      const w = await S2.api("/api/wallet?journal_limit=200", { noRedirect: true });
      const coins = new Set((w.journal || []).map(j => j.symbol).filter(Boolean));
      coins.forEach(c => extra.push({ label: c, hint: "coin: wallet journal", go: () => { location.hash = "#/trades?tab=journal"; } }));
    } catch (e) { /* ignore */ }
    return extra;
  }

  function items() {
    const base = S2.NAV.map(n => ({ label: n.label, hint: "page", icon: n.icon, go: () => S2.go(n.id) }))
      .concat([{ label: "More / Legacy", hint: "page", icon: "ellipsis", go: () => S2.go("more") }, { label: "UI kit", hint: "page", icon: "layers", go: () => S2.go("ui-kit") },
        { label: "Old dashboard", hint: "legacy", icon: "external-link", go: () => { location.href = "/legacy"; } }]);
    return base.concat(extra || []);
  }

  function open() {
    if (document.querySelector(".palette")) return;
    const prev = document.activeElement;
    const box = S2.h("div", { class: "palette", role: "dialog", "aria-modal": "true", "aria-label": "Command palette" });
    box.innerHTML = `<div class="box"><input class="input" type="text" placeholder="Page, coin or strategy..." aria-label="Search" role="combobox" aria-expanded="true" aria-controls="palList">
      <ul id="palList" role="listbox"></ul></div>`;
    document.body.appendChild(box);
    const inp = box.querySelector("input"), ul = box.querySelector("ul");
    let sel = 0, list = [];
    const draw = () => {
      const q = inp.value.trim().toLowerCase();
      list = items().filter(i => !q || i.label.toLowerCase().includes(q)).slice(0, 40);
      sel = Math.min(sel, Math.max(0, list.length - 1));
      ul.innerHTML = list.length ? list.map((it, i) => `<li role="option" data-i="${i}" aria-selected="${i === sel}">${it.icon ? icon(it.icon) : ""}<span>${esc(it.label)}</span><span class="t-hint">${esc(it.hint)}</span></li>`).join("")
        : `<li class="t-3">No match</li>`;
    };
    const close = () => { box.remove(); if (prev && prev.focus) prev.focus(); };
    const pick = i => { const it = list[i]; close(); if (it) it.go(); };
    inp.addEventListener("input", () => { sel = 0; draw(); });
    inp.addEventListener("keydown", e => {
      if (e.key === "ArrowDown") { e.preventDefault(); sel = Math.min(list.length - 1, sel + 1); draw(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); sel = Math.max(0, sel - 1); draw(); }
      else if (e.key === "Enter") { e.preventDefault(); pick(sel); }
      else if (e.key === "Escape") { e.preventDefault(); close(); }
    });
    ul.addEventListener("click", e => { const li = e.target.closest("[data-i]"); if (li) pick(Number(li.dataset.i)); });
    box.addEventListener("mousedown", e => { if (e.target === box) close(); });
    draw(); inp.focus();
    loadExtra().then(() => { if (box.isConnected) draw(); });
  }

  function help() {
    S2.modal({ title: "Keyboard shortcuts", cancel: false, ok: "Close", body: S2.h("div", { html: `<dl class="kv" style="grid-template-columns:auto 1fr">
      <dt><span class="kbd">Ctrl</span> <span class="kbd">K</span></dt><dd style="text-align:left">Command palette</dd>
      <dt><span class="kbd">g</span> <span class="kbd">h</span></dt><dd style="text-align:left">Home</dd><dt><span class="kbd">g</span> <span class="kbd">t</span></dt><dd style="text-align:left">Trades</dd>
      <dt><span class="kbd">g</span> <span class="kbd">s</span></dt><dd style="text-align:left">Strategies</dd><dt><span class="kbd">g</span> <span class="kbd">b</span></dt><dd style="text-align:left">Backtests</dd>
      <dt><span class="kbd">g</span> <span class="kbd">y</span></dt><dd style="text-align:left">System</dd><dt><span class="kbd">g</span> <span class="kbd">,</span></dt><dd style="text-align:left">Settings</dd>
      <dt><span class="kbd">?</span></dt><dd style="text-align:left">This list</dd></dl>` }) });
  }

  const G = { h: "home", t: "trades", s: "strategies", b: "backtests", y: "system", ",": "settings" };
  let gAt = 0;
  document.addEventListener("keydown", e => {
    const tag = (e.target && e.target.tagName) || "";
    const typing = /INPUT|TEXTAREA|SELECT/.test(tag) || (e.target && e.target.isContentEditable);
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); open(); return; }
    if (typing || e.ctrlKey || e.metaKey || e.altKey || document.querySelector(".modal-bg, .palette")) return;
    if (e.key === "?") { e.preventDefault(); help(); return; }
    if (e.key === "g") { gAt = Date.now(); return; }
    if (gAt && Date.now() - gAt < 1200 && G[e.key]) { e.preventDefault(); gAt = 0; S2.go(G[e.key]); }
  });
  S2.palette = open;
})();
