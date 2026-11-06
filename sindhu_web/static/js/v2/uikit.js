/* UI kit (master plan V2 DS2): every component on one page; the theme toggle in the top bar shows both themes. Behind login. */
(function () {
  "use strict";
  const S2 = window.S2, icon = S2.icon;

  function render(el) {
    el.innerHTML = `<div class="stack">
      <div class="card"><div class="card-h"><h3>Buttons</h3></div><div class="card-b row wrap">
        <button class="btn primary" type="button">${icon("check")}Primary</button><button class="btn" type="button">Secondary</button>
        <button class="btn ghost" type="button">Ghost</button><button class="btn danger" type="button">${icon("power")}Danger</button>
        <button class="btn danger outline" type="button">Danger outline</button><button class="btn sm" type="button">Small</button>
        <button class="btn lg primary" type="button">Large</button><button class="btn loading" type="button" id="kLoad"><span class="spin"></span>Saving...</button>
        <button class="btn" type="button" disabled>Disabled</button><button class="btn icon-only" type="button" aria-label="Refresh" data-tip="Tooltip">${icon("refresh-cw")}</button></div></div>
      <div class="card"><div class="card-h"><h3>Inputs and fields</h3></div><div class="card-b">
        <div class="field-row"><div class="field"><label for="k1">Text</label><span class="help">help text in one line</span></div><div class="field"><input class="input" id="k1" placeholder="Type here"></div></div>
        <div class="field-row"><div class="field"><label for="k2">Number with unit</label><span class="help">allowed 0.05-2 %</span></div><div class="field"><div class="input-unit"><input class="input" id="k2" value="1.00" inputmode="decimal"><span class="unit">%</span></div></div></div>
        <div class="field-row"><div class="field"><label for="k3">Invalid value</label><span class="help">shows the error under the field</span></div><div class="field invalid"><input class="input" id="k3" value="80" aria-invalid="true"><span class="error">Zyada se zyada 25</span></div></div>
        <div class="field-row"><div class="field"><label for="k4">Select</label></div><div class="field"><select class="select" id="k4"><option>block</option><option>allow</option></select></div></div>
        <div class="field-row"><div class="field"><span class="field-label">Toggle</span></div><label class="toggle"><input type="checkbox" checked aria-label="Toggle"><span class="track"></span><span class="t-2">On</span></label></div>
        <div class="field-row"><div class="field"><span class="field-label">Segmented</span></div><div class="segmented" role="group" aria-label="Segmented"><button type="button" aria-pressed="true">Wallet</button><button type="button" aria-pressed="false">Research</button></div></div>
      </div></div>
      <div class="ds-grid"><div class="card span-3"><div class="stat"><span class="k">${icon("wallet")}Stat card</span><span class="v big">$104.27</span><span class="d"><span class="up">+4.27%</span> since start</span></div></div>
        <div class="card span-3"><div class="stat"><span class="k">Loss</span><span class="v down">-$1.80</span><span class="d">today</span></div></div>
        <div class="card span-6"><div class="card-h"><h3>Badges</h3></div><div class="card-b row wrap">${["ROBUST", "FRAGILE", "FAILED", "INSUFFICIENT_DATA", "PAPER", "RESEARCH", "PAUSED", "STALE", "LIVE"].map(b => S2.badge(b)).join("")}</div></div></div>
      <div id="kTabs"></div><div id="kTabBody" class="card" style="margin-top:-1px"></div>
      <div id="kTable"></div>
      <div class="ds-grid"><div class="card span-6"><div class="card-h"><h3>Loading (skeleton)</h3></div><div class="card-b">${S2.skeleton(4)}</div></div>
        <div class="card span-6"><div class="card-h"><h3>Empty and error</h3></div><div class="card-b">${S2.empty("Abhi kuch nahi", "Empty states say what will appear and when.")}${S2.errorBlock({ timeout: true, message: "example" })}</div></div></div>
      <div class="card"><div class="card-h"><h3>Chart</h3><span class="t-hint">uPlot ${"1.6.31"}, lazy-loaded</span></div><div class="card-b"><div class="chart" id="kChart"></div></div></div>
      <div class="card"><div class="card-h"><h3>Modal, toast, notice</h3></div><div class="card-b stack-sm">
        <div class="row wrap"><button class="btn" type="button" id="kModal">Open modal</button><button class="btn" type="button" id="kToast">Show toast</button><button class="btn" type="button" id="kToastE">Error toast</button></div>
        <div class="notice">${icon("info")}<div>A neutral notice.</div></div><div class="notice warn">${icon("triangle-alert")}<div>A warning notice (stale data).</div></div>
        <div class="notice err">${icon("circle-x")}<div>An error notice.</div></div></div></div></div>`;
    S2.tabs(document.getElementById("kTabs"), [{ id: "a", label: "Open", count: 3 }, { id: "b", label: "Closed", count: 12 }, { id: "c", label: "Journal" }],
      id => { document.getElementById("kTabBody").innerHTML = `<div class="card-b t-2">Tab ${id}</div>`; });
    const rows = Array.from({ length: 47 }, (_, i) => ({ coin: ["BTC/USDT", "ETH/USDT", "SOL/USDT"][i % 3], pnl: Math.round((Math.sin(i) * 3.2) * 100) / 100, size: 5 + (i % 9) * 1.5, cls: ["ROBUST", "FRAGILE", "FAILED"][i % 3] }));
    S2.table(document.getElementById("kTable"), { rows, csv: "ui_kit_example", filters: [{ key: "cls", label: "Class" }],
      columns: [{ key: "coin", label: "Coin", render: v => `<span class="mono">${v}</span>` }, { key: "cls", label: "Class", render: v => S2.badge(v) },
        { key: "size", label: "Size $", num: true, fmt: v => S2.fmt.money(v) }, { key: "pnl", label: "P&L $", num: true, fmt: S2.fmt.signedMoney, cls: v => S2.cls(v) }],
      expand: r => `<span class="t-2">Row detail for ${r.coin}</span>` });
    const now = Math.round(Date.now() / 1000);
    let eq = 100; const x = [], y = [];
    for (let i = 0; i < 60; i++) { x.push(now - (60 - i) * 3600); eq += Math.sin(i / 4) * 0.6 + 0.05; y.push(Math.round(eq * 100) / 100); }
    S2.chart(document.getElementById("kChart"), { x, series: [{ label: "Example equity", values: y, color: "accent", fill: true }], yFmt: v => "$" + v.toFixed(0) });
    document.getElementById("kModal").onclick = () => S2.confirm("Example modal", "Focus stays inside; Esc closes.", "OK");
    document.getElementById("kToast").onclick = () => S2.toast("Saved ✓ example");
    document.getElementById("kToastE").onclick = () => S2.toast("Something failed (example)", "err");
  }
  S2.pages["ui-kit"] = { title: "UI kit", crumb: "Design system v2 components", render };
})();
