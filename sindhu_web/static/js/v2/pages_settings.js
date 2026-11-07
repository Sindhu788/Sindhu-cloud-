/* Settings v2 (master plan V2 PG6 / W8 + U10): six groups; every setting has a label, one-line help, unit, valid range and inline
   validation with the SAME rules as the server (/api/v2/settings-schema); each change is saved on its own ("Saved" toast); changes
   that add risk ask first. Secrets (bot token, DATABASE_URL, DASHBOARD_PASSWORD) are never shown or edited here. */
(function () {
  "use strict";
  const S2 = window.S2, esc = S2.esc, icon = S2.icon;

  const GROUPS = [["wallet", "Wallet & Risk"], ["signals", "Signals"], ["data", "Data"], ["notify", "Notifications"], ["security", "Security"], ["look", "Appearance"]];
  const PAPER_GROUP = {
    wallet: ["risk_pct_default", "max_open_trades", "max_open_positions_per_coin", "max_portfolio_risk_pct_per_coin", "cooldown_minutes",
             "cooling_off_loss_streak", "cooling_off_hours", "daily_goal_pct"],
    data: ["coin_filter_top_n", "tick_interval_seconds", "lookback_days"],
  };
  const ENUMS = {
    priority_rule: { label: "Which signal wins", help: "when two strategies want the same coin", opts: ["confidence_and_win_rate", "confidence", "win_rate", "profit", "manual"] },
    opposite_signal_policy: { label: "Opposite signal", help: "a new signal against an open position", opts: ["block", "allow", "close_and_reverse"] },
  };
  // differences found by tools/parity_check.py (docs/PARITY.md, master plan A22); owner decides, nothing is synced automatically
  const PARITY = [["coin_filter_top_n", "10", "50"], ["risk_pct_default", "0.5", "1.0"], ["tick_interval_seconds", "30", "60"],
    ["telegram bot token", "not set", "set (Render env)"], ["telegram master_send_enabled", "off", "on (Cloud is the single publisher)"]];

  function rangeText(r) {
    const lo = r.min, hi = r.max;
    if (lo !== null && lo !== undefined && hi !== null && hi !== undefined) return `${lo}-${hi} ${r.unit || ""}`.trim();
    if (lo !== null && lo !== undefined) return `${r.min_inclusive === false ? "above" : "at least"} ${lo} ${r.unit || ""}`.trim();
    return "";
  }
  function validate(r, raw) {
    if (raw === "" || raw === null || raw === undefined) return "Value chahiye";
    const v = Number(raw);
    if (isNaN(v)) return "Number likho";
    if ((r.kind === "int" || r.int) && !Number.isInteger(v)) return "Poora number (decimal nahi)";
    if (r.min !== null && r.min !== undefined && (r.min_inclusive === false ? v <= r.min : v < r.min)) return `Kam se kam ${r.min_inclusive === false ? "above " : ""}${r.min}`;
    if (r.max !== null && r.max !== undefined && v > r.max) return `Zyada se zyada ${r.max}`;
    return null;
  }

  function numberField(id, r, value, onSave) {
    const wrap = S2.h("div", { class: "field-row" });
    const left = S2.h("div", { class: "field" }, S2.h("label", { for: "f_" + id }, r.label), S2.h("span", { class: "help" }, `${r.help || ""}${rangeText(r) ? " · allowed " + rangeText(r) : ""}`));
    const inp = S2.h("input", { class: "input", id: "f_" + id, inputmode: "decimal", value: value === null || value === undefined ? "" : value, "aria-describedby": "e_" + id, autocomplete: "off" });
    const err = S2.h("span", { class: "error", id: "e_" + id, role: "alert" });
    const right = S2.h("div", { class: "field" }, S2.h("div", { class: "input-unit" }, inp, S2.h("span", { class: "unit" }, r.unit || "")), err);
    wrap.appendChild(left); wrap.appendChild(right);
    let last = value;
    const commit = async () => {
      const msg = validate(r, inp.value.trim());
      right.classList.toggle("invalid", !!msg); inp.setAttribute("aria-invalid", msg ? "true" : "false"); err.textContent = msg || "";
      if (msg || Number(inp.value) === Number(last)) return;
      const nv = Number(inp.value);
      if (r.danger_up && Number(last) < nv) {
        const ok = await S2.confirm("Risk barhana hai?", `${r.label}: ${last} -> ${nv} ${r.unit || ""}. This lets the system take more risk. Paper only, but please be sure.`, "Yes, increase", true);
        if (!ok) { inp.value = last; return; }
      }
      try { await onSave(nv); last = nv; S2.toast(`Saved ✓ ${r.label}: ${nv} ${r.unit || ""}`); }
      catch (e) {
        const se = e.data && e.data.detail && e.data.detail.errors ? Object.values(e.data.detail.errors)[0] : e.message;
        right.classList.add("invalid"); err.textContent = "Server: " + se; inp.value = last;
      }
    };
    inp.addEventListener("change", commit);
    inp.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); inp.blur(); } });
    return wrap;
  }
  function toggleField(id, label, help, value, onSave, dangerOn) {
    const wrap = S2.h("div", { class: "field-row" });
    wrap.appendChild(S2.h("div", { class: "field" }, S2.h("span", { class: "field-label", id: "l_" + id }, label), S2.h("span", { class: "help" }, help)));
    const cb = S2.h("input", { type: "checkbox", id: "f_" + id, "aria-labelledby": "l_" + id });
    cb.checked = !!value;
    wrap.appendChild(S2.h("div", {}, S2.h("label", { class: "toggle" }, cb, S2.h("span", { class: "track" }), S2.h("span", { class: "t-2" }, value ? "On" : "Off"))));
    cb.addEventListener("change", async () => {
      const nv = cb.checked;
      if (nv && dangerOn) { const ok = await S2.confirm(dangerOn[0], dangerOn[1], "Turn on", true); if (!ok) { cb.checked = false; return; } }
      try { await onSave(nv); cb.parentNode.lastChild.textContent = nv ? "On" : "Off"; S2.toast(`Saved ✓ ${label}: ${nv ? "on" : "off"}`); }
      catch (e) { cb.checked = !nv; S2.toast("Save failed: " + e.message, "err"); }
    });
    return wrap;
  }
  function selectField(id, def, value, onSave) {
    const wrap = S2.h("div", { class: "field-row" });
    wrap.appendChild(S2.h("div", { class: "field" }, S2.h("label", { for: "f_" + id }, def.label), S2.h("span", { class: "help" }, def.help)));
    const sel = S2.h("select", { class: "select", id: "f_" + id });
    def.opts.forEach(x => { const op = S2.h("option", { value: x }, x.replace(/_/g, " ")); if (x === value) op.selected = true; sel.appendChild(op); });
    wrap.appendChild(S2.h("div", { class: "field" }, sel));
    sel.addEventListener("change", async () => { try { await onSave(sel.value); S2.toast(`Saved ✓ ${def.label}`); } catch (e) { S2.toast("Save failed: " + e.message, "err"); } });
    return wrap;
  }
  function readonlyRow(label, help, valueHtml) {
    return S2.h("div", { class: "field-row" }, S2.h("div", { class: "field" }, S2.h("span", { class: "field-label" }, label), S2.h("span", { class: "help" }, help)),
      S2.h("div", { html: valueHtml }));
  }

  async function render(el, o) {
    const [schema, paper, tg, det] = await Promise.all([
      S2.api("/api/v2/settings-schema"), S2.api("/api/paper-trading/settings"),
      S2.api("/api/paper-trading/telegram/settings").catch(() => ({})), S2.api("/health/details").catch(() => ({})),
    ]);
    if (o.stale()) return;
    const savePaper = async (k, v) => S2.api("/api/paper-trading/settings", { method: "POST", body: { [k]: v } });
    const saveWallet = async (k, v) => S2.api("/api/wallet/settings", { method: "POST", body: { [k]: v } });
    const saveTg = async (k, v) => S2.api("/api/paper-trading/telegram/settings", { method: "POST", body: { [k]: v } });
    const current = o.q.g || "wallet";
    el.innerHTML = `<div class="ds-grid"><nav class="span-3" aria-label="Settings groups"><div class="card" style="padding:6px">${GROUPS.map(([id, lbl]) =>
      `<a class="btn ghost set-nav" href="#/settings?g=${id}" ${id === current ? 'aria-current="page"' : ""}>${esc(lbl)}</a>`).join("")}</div>
      <div class="card" style="margin-top:12px"><div class="card-h"><h3>Local vs Cloud</h3></div><div class="card-b" style="font-size:12px">
        <p class="t-2" style="margin-bottom:8px">Settings that differ (parity check). Change them on the side you want; nothing syncs by itself.</p>
        <table class="tbl dense"><thead><tr><th>Setting</th><th>Local</th><th>Cloud</th></tr></thead><tbody>${PARITY.map(p => `<tr><td>${esc(p[0])}</td><td class="mono">${esc(p[1])}</td><td class="mono">${esc(p[2])}</td></tr>`).join("")}</tbody></table>
        <p class="t-hint" style="margin-top:8px">This server: config hash <span class="mono">${esc(det.config_hash || "--")}</span></p></div></div></nav>
      <section class="span-9"><div class="card"><div class="card-h"><h3 id="sgTitle"></h3></div><div class="card-b" id="sgBody"></div></div></section></div>`;
    document.getElementById("sgTitle").textContent = (GROUPS.find(g => g[0] === current) || GROUPS[0])[1];
    const body = document.getElementById("sgBody");
    const P = schema.paper || {};
    if (current === "wallet") {
      body.appendChild(S2.h("p", { class: "t-hint", style: "margin-bottom:4px" }, "MAIN_WALLET ($100 paper). Limits can be made stricter at any time; looser values ask first."));
      for (const [k, r] of Object.entries(schema.wallet || {})) body.appendChild(numberField("w_" + k, r, (schema.wallet_values || {})[k], v => saveWallet(k, v)));
      body.appendChild(S2.h("h4", { style: "margin:20px 0 4px" }, "Research books (every strategy's own paper book)"));
      for (const k of PAPER_GROUP.wallet) if (P[k]) body.appendChild(numberField(k, Object.assign({ danger_up: (schema.danger_fields || []).includes(k) }, P[k]), paper[k], v => savePaper(k, v)));
      body.appendChild(readonlyRow("Kill switch", "stops every new paper entry; open positions keep their stops", `<span class="t-2">Use the button in the top bar.</span>`));
      body.appendChild(readonlyRow("Same-coin cap, Wilson 25, Evolution 100, freshness, drawdown breaker", "fixed safety gates", `<span class="badge">fixed in code</span>`));
    } else if (current === "signals") {
      for (const [k, def] of Object.entries(ENUMS)) body.appendChild(selectField(k, def, paper[k], v => savePaper(k, v)));
      body.appendChild(readonlyRow("Public signals", "automatic Telegram signals to the public channel",
        det.config_summary && det.config_summary.telegram && det.config_summary.telegram.public_signals_allowed
          ? `<span class="badge live">ON</span> <span class="t-hint">set by SINDHU_PUBLIC_SIGNALS on Render</span>`
          : `<span class="badge">OFF</span> <span class="t-hint">only the owner can turn this on: Render env SINDHU_PUBLIC_SIGNALS=1 (OWNER_TODO)</span>`));
      body.appendChild(readonlyRow("Who may publish", "only Profitable and Challenge groups; FAILED strategies never", `<span class="mono">${esc(tg.channel_group_filter || "profitable_challenge")}</span> <span class="badge">fixed</span>`));
      if ("auto_send_enabled" in tg) body.appendChild(toggleField("tg_auto", "Auto-send signals", "send qualifying signals without asking", tg.auto_send_enabled, v => saveTg("auto_send_enabled", v),
        ["Auto-send on?", "Qualifying signals will be sent automatically (public signals still need the Render switch)."]));
      if ("min_confidence_pct_to_send" in tg) body.appendChild(numberField("tg_conf", { label: "Minimum confidence to send", help: "lower = more signals", unit: "%", min: 0, max: 100 }, tg.min_confidence_pct_to_send, v => saveTg("min_confidence_pct_to_send", v)));
      if ("rate_limit_per_hour" in tg) body.appendChild(numberField("tg_rate", { label: "Max signals per hour", help: "rate limit", unit: "per h", min: 1, max: 60, int: true, danger_up: true }, tg.rate_limit_per_hour, v => saveTg("rate_limit_per_hour", v)));
    } else if (current === "data") {
      for (const k of PAPER_GROUP.data) if (P[k]) body.appendChild(numberField(k, P[k], paper[k], v => savePaper(k, v)));
      const c = det.candles;
      body.appendChild(readonlyRow("Candle source", "where prices come from", c ? `<span class="mono">live exchange (OKX), in memory only</span>` : `<span class="mono">local database</span>`));
    } else if (current === "notify") {
      const t = (det.config_summary || {}).telegram || {};
      body.appendChild(readonlyRow("Telegram bot", "token lives in Render env only", t.bot_token_set ? `<span class="badge live">configured</span>` : `<span class="badge">not set</span>`));
      body.appendChild(readonlyRow("Owner chat (alerts, commands)", "OWNER_CHAT_ID on Render", `<span class="t-2">${tg.personal_chat_id_set || tg.personal_chat_id ? "set" : "not set: see OWNER_TODO step OWNER_CHAT_ID"}</span>`));
      if ("silent_hours_enabled" in tg) body.appendChild(toggleField("tg_silent", "Silent hours", `no messages ${tg.silent_hours_start_utc || "--"}-${tg.silent_hours_end_utc || "--"} UTC`, tg.silent_hours_enabled, v => saveTg("silent_hours_enabled", v)));
      if ("send_close_followups" in tg) body.appendChild(toggleField("tg_follow", "Close follow-ups", "send a message when a signalled trade closes", tg.send_close_followups, v => saveTg("send_close_followups", v)));
    } else if (current === "security") {
      body.innerHTML = `<div class="stack">
        <div class="notice">${icon("lock")}<div><strong>Two ways to sign in.</strong> 1) Username <span class="mono">owner</span> + the DASHBOARD_PASSWORD set on Render.
          2) The saved account. Forgot it? On the laptop: <span class="mono">python -m tools.reset_dashboard_user --list</span>, then <span class="mono">--reset &lt;name&gt;</span> (add <span class="mono">--cloud</span> for Cloud). Steps: docs/OWNER_TODO.md.</div></div>
        <form id="pwForm" class="stack-sm" style="max-width:420px" autocomplete="on">
          <h4>Change the saved account's password</h4>
          <input type="text" name="username" autocomplete="username" hidden>
          <div class="field"><label for="pwCur">Current password</label><input class="input" id="pwCur" type="password" autocomplete="current-password" required></div>
          <div class="field"><label for="pwNew">New password</label><input class="input" id="pwNew" type="password" autocomplete="new-password" minlength="8" required><span class="help">at least 8 characters</span></div>
          <div class="field" id="pwErrF"><span class="error" id="pwErr" role="alert"></span></div>
          <div><button class="btn primary" type="submit">Change password</button></div></form>
        <div id="totpBox"></div>
        <p class="t-hint">Sessions end after 12 hours without use. Logout is in the account menu (top right).</p></div>`;
      document.getElementById("pwForm").addEventListener("submit", async e => {
        e.preventDefault();
        const cur = document.getElementById("pwCur").value, nw = document.getElementById("pwNew").value;
        const ef = document.getElementById("pwErrF"), er = document.getElementById("pwErr");
        if (nw.length < 8) { ef.classList.add("invalid"); er.textContent = "Naya password kam se kam 8 characters"; return; }
        try { await S2.api("/api/auth/change-password", { method: "POST", body: { current_password: cur, new_password: nw }, noRedirect: true }); ef.classList.remove("invalid"); S2.toast("Saved ✓ password changed"); e.target.reset(); }
        catch (err) { ef.classList.add("invalid"); er.textContent = err.status === 401 ? "Current password galat hai" : err.message; }
      });
      if (S2.renderTotp) S2.renderTotp(document.getElementById("totpBox"));
    } else if (current === "look") {
      const seg = S2.h("div", { class: "segmented", role: "group", "aria-label": "Theme" });
      ["dark", "light"].forEach(t => {
        const b = S2.h("button", { type: "button", "aria-pressed": String(document.documentElement.getAttribute("data-theme") === t) }, t === "dark" ? "Dark (graphite)" : "Light (paper)");
        b.addEventListener("click", () => { document.getElementById("themeBtn").click(); S2.route(); }); seg.appendChild(b);
      });
      body.appendChild(S2.h("div", { class: "field-row" }, S2.h("div", { class: "field" }, S2.h("span", { class: "field-label" }, "Theme"), S2.h("span", { class: "help" }, "remembered on this device")), S2.h("div", {}, seg)));
      body.appendChild(readonlyRow("Motion", "follows your system 'reduce motion' setting", `<span class="t-2">${matchMedia("(prefers-reduced-motion: reduce)").matches ? "reduced" : "normal"}</span>`));
      body.appendChild(readonlyRow("Keyboard", "Ctrl/⌘+K opens the command palette, ? shows shortcuts", `<span class="kbd">Ctrl</span> <span class="kbd">K</span>`));
    }
  }

  S2.pages.settings = { title: "Settings", crumb: "Wallet, signals, data, security", render };
})();
