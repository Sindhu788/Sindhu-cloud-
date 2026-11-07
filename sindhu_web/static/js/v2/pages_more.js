/* More / Legacy (master plan V2 PG8 / W10): every page of the old dashboard stays one click away (nothing removed).
   The list mirrors sindhu_web/api/home.py NAV_PAGES (generated at PG8); pages rebuilt in v2 are marked. Old pages open at /legacy. */
(function () {
  "use strict";
  const S2 = window.S2, esc = S2.esc, icon = S2.icon;
  const LEGACY = [{"id":"ceo","label":"SINDHU CEO","group":"CEO / Orchestrator"},{"id":"home","label":"Dashboard","group":"CEO / Orchestrator"},{"id":"compare","label":"Compare","group":"Research"},{"id":"backtesting","label":"Backtesting","group":"Research"},{"id":"backtest_history","label":"Backtest History","group":"Research"},{"id":"pipeline_history","label":"Pipeline History","group":"Research"},{"id":"web_sourced_strategies","label":"Web-Sourced Strategies","group":"Research"},{"id":"knowledge","label":"Knowledge","group":"Research"},{"id":"concepts","label":"Concepts","group":"Research","url":"/static/concepts.html"},{"id":"market","label":"Market","group":"Data"},{"id":"data","label":"Data","group":"Data"},{"id":"strategies","label":"Strategies","group":"Strategy"},{"id":"sindhu_strategy","label":"SINDHU Strategy","group":"Strategy"},{"id":"knowledge_compiler","label":"Knowledge Compiler","group":"Strategy"},{"id":"ai_center","label":"AI Center","group":"Strategy"},{"id":"clarification_center","label":"Clarification","group":"Strategy"},{"id":"paper_trading","label":"Paper Trading","group":"Trading / Execution"},{"id":"telegram_dashboard","label":"Telegram Signals","group":"Trading / Execution"},{"id":"signal_tracker","label":"Signal Tracker","group":"Trading / Execution"},{"id":"challenge_mode","label":"Challenge Mode","group":"Trading / Execution"},{"id":"external_signals","label":"External Signal Tracker","group":"Trading / Execution"},{"id":"practice_mode","label":"Practice Mode","group":"Trading / Execution"},{"id":"risk_department","label":"Risk","group":"Risk"},{"id":"strategy_lifecycle","label":"Strategy Lifecycle","group":"Learning / Reflection"},{"id":"evolution","label":"Evolution","group":"Learning / Reflection"},{"id":"evolution_history","label":"Evolution History","group":"Learning / Reflection"},{"id":"self_learning","label":"Self-Learning Engine","group":"Learning / Reflection"},{"id":"strategy_lab","label":"Strategy Lab","group":"Learning / Reflection"},{"id":"reports","label":"Reports","group":"Reporting"},{"id":"memory_core","label":"Memory Core","group":"Memory Core"},{"id":"control_center","label":"Control Center","group":"Operations / System"},{"id":"live_logs","label":"Live Logs","group":"Operations / System"},{"id":"project_status","label":"Project Status","group":"Operations / System"},{"id":"incidents","label":"Incidents","group":"Operations / System"},{"id":"settings","label":"Settings","group":"Operations / System"},{"id":"configuration_panel","label":"Configuration Panel","group":"Operations / System"}];
  const REBUILT = { wallet: "home", paper_trading: "trades", strategies: "strategies", backtesting: "backtests", settings: "settings", configuration_panel: "settings", control_center: "system" };

  function render(el, o) {
    o.actions.innerHTML = `<a class="btn sm" href="/legacy">${icon("external-link")}Open the old dashboard</a>`;
    const groups = {};
    LEGACY.forEach(p => { (groups[p.group] = groups[p.group] || []).push(p); });
    const phone = `<div class="card" style="margin-bottom:16px"><div class="card-b"><div class="ds-grid">
      ${S2.NAV.map(n => `<a class="btn span-4" href="#/${n.id}">${icon(n.icon)}${esc(n.label)}</a>`).join("")}
      <a class="btn span-4" href="#/ui-kit">${icon("layers")}UI kit</a></div></div></div>`;
    el.innerHTML = phone + `<p class="t-2" style="margin-bottom:12px">All ${LEGACY.length} pages of the old dashboard. They keep working as before and use the new colours.
      Pages already rebuilt are marked; their old version stays here too.</p><div class="ds-grid">` +
      Object.entries(groups).map(([g, items]) => `<div class="card span-4"><div class="card-h"><h3>${esc(g)}</h3><span class="t-hint">${items.length}</span></div>
        <div class="card-b" style="padding:6px"><ul style="list-style:none;margin:0;padding:0">${items.map(p => `<li><a class="btn ghost set-nav" href="${esc(p.url || "/legacy#" + p.id)}">${esc(p.label)}
          ${REBUILT[p.id] ? `<span class="badge live" style="margin-left:auto">new: ${esc(REBUILT[p.id])}</span>` : ""}</a></li>`).join("")}</ul></div></div>`).join("") + `</div>`;
  }

  S2.pages.more = { title: "More / Legacy", crumb: "Every old page, nothing removed", render };
})();
