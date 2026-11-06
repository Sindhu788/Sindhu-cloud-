/* Backtests (master plan V2 PG5 / W7): verdicts in plain words, Part B results with equity + drawdown charts and metrics,
   library backtest table (filters by verdict / timeframe). Heavy data is paginated; charts load only when a result is opened. */
(function () {
  "use strict";
  const S2 = window.S2, esc = S2.esc, icon = S2.icon, f = S2.fmt;

  const VERDICTS = [
    ["ROBUST", "Passed every pre-registered rule: profit out-of-sample, walk-forward, neighbours, costs x1.5, and the multiple-testing check. Still only a candidate: paper first, then a forward test."],
    ["FRAGILE", "Not a loss in the test, but at least one rule failed (often: the result could be luck once 44 tested strategies are counted). Not used in the wallet as proof of anything."],
    ["FAILED", "Lost money out-of-sample, or profit factor after costs was 1.0 or less. No edge found."],
    ["INSUFFICIENT_DATA", "Too few trades to judge (fewer than 300 in total or 30 out-of-sample). Not good, not bad: unknown."],
  ];
  const PREREG_HASH = "6abba148";

  function metricsGrid(m) {
    const rows = [["Total return", f.signedPct(m.total_return_pct)], ["CAGR", f.signedPct(m.cagr_pct)], ["Sharpe", f.num(m.sharpe, 2)], ["Sortino", f.num(m.sortino, 2)],
      ["Max drawdown", f.pct(m.max_drawdown_pct)], ["Profit factor", f.num(m.profit_factor, 2)], ["Positions", f.num(m.positions, 0)], ["Win rate", f.pct(m.win_rate_pct, 1)],
      ["Exposure", f.pct(m.exposure_pct, 1)], ["t-stat", f.num(m.t_stat, 2)], ["Period", `${String(m.start || "").slice(0, 10)} .. ${String(m.end || "").slice(0, 10)}`]];
    return `<dl class="kv">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("")}</dl>`;
  }

  async function benchDetail(host, bench, id) {
    const u = bench.units.find(x => x.id === id); if (!u) return;
    const btc = bench.units.find(x => x.id === "bench__btc_buy_hold");
    const x = u.equity_weekly.map(p => Math.round(Date.parse(p[0]) / 1000));
    const eq = u.equity_weekly.map(p => p[1]);
    const btcMap = new Map((btc ? btc.equity_weekly : []).map(p => [p[0], p[1]]));
    const btcEq = u.equity_weekly.map(p => (btcMap.has(p[0]) ? btcMap.get(p[0]) : null));
    let peak = -Infinity; const dd = eq.map(v => { peak = Math.max(peak, v); return -((peak - v) / peak) * 100; });
    const wf = Object.entries(u.walk_forward || {}).map(([y, m]) => `<tr><td>${esc(y)}</td><td class="num ${S2.cls(m.total_return_pct)}">${f.signedPct(m.total_return_pct)}</td>
      <td class="num">${f.num(m.sharpe, 2)}</td><td class="num">${f.pct(m.max_drawdown_pct)}</td><td class="num">${f.num(m.positions, 0)}</td></tr>`).join("");
    const vd = u.verdict_detail || {};
    const checks = vd.checks ? Object.entries(vd.checks).map(([k, v]) => `<li>${v ? icon("circle-check", "up") : icon("circle-x", "down")} ${esc(k)}</li>`).join("") : "";
    host.innerHTML = `<div class="card"><div class="card-h"><h3>${esc(u.name)}</h3>${u.verdict ? S2.badge(u.verdict) : '<span class="badge">benchmark</span>'}
        <span class="t-hint">$100 start, costs 0.15 % per side</span></div>
      <div class="card-b"><div class="chart" id="bxEq"></div></div>
      <div class="card-h" style="border-top:1px solid var(--line-soft)"><h3>Drawdown</h3></div><div class="card-b"><div class="chart" id="bxDd" style="min-height:140px"></div></div>
      <div class="card-b"><div class="ds-grid">
        <div class="span-4"><div class="label-caps">In-sample 2018-2023</div>${metricsGrid((u.metrics || {}).IS || {})}</div>
        <div class="span-4"><div class="label-caps">Out-of-sample 2024 - Oct 2026</div>${metricsGrid((u.metrics || {}).OOS || {})}</div>
        <div class="span-4"><div class="label-caps">Walk-forward test years</div><table class="tbl dense"><thead><tr><th>Year</th><th class="num">Return</th><th class="num">Sharpe</th><th class="num">Max DD</th><th class="num">Pos.</th></tr></thead><tbody>${wf}</tbody></table>
          ${checks ? `<div class="label-caps" style="margin-top:12px">ROBUST rules</div><ul style="list-style:none;padding:0;margin:6px 0 0;font-size:13px;display:grid;gap:4px">${checks}</ul>` : ""}
          <p class="t-hint" style="margin-top:8px">Bootstrap p (OOS) ${f.num(u.oos_block_bootstrap_p, 3)} &middot; pooled PF ${f.num(u.pooled_pf_full, 2)} &middot; turnover ${f.num(u.turnover_per_year_x, 1)}x / year</p></div>
      </div></div></div>`;
    const series = [{ label: u.name.split(" (")[0], values: eq, color: "accent", fill: true }];
    if (btc && id !== btc.id) series.push({ label: "BTC buy-and-hold", values: btcEq, color: "text-3" });
    await S2.chart(document.getElementById("bxEq"), { x, series, yFmt: v => "$" + Math.round(v) });
    await S2.chart(document.getElementById("bxDd"), { x, height: 140, series: [{ label: "Drawdown", values: dd, color: "loss", fill: true }], yFmt: v => Number(v).toFixed(0) + "%" });
  }

  async function render(el, o) {
    o.actions.innerHTML = `<a class="btn sm" href="/legacy#backtesting">${icon("external-link")}Run a backtest (old page)</a>`;
    el.innerHTML = `
      <div class="card"><div class="card-h"><h3>What the verdicts mean</h3><span class="t-hint">rules fixed before any result was seen</span></div>
        <div class="card-b"><div class="ds-grid">${VERDICTS.map(([k, t]) => `<div class="span-3 stack-sm">${S2.badge(k)}<p class="t-2" style="font-size:13px">${esc(t)}</p></div>`).join("")}</div>
        <p class="t-hint" style="margin-top:12px">Pre-registration: <span class="mono">docs/BENCHMARK_PREREGISTRATION_V2.md</span> (commit 7388c1b, file hash <span class="mono">${PREREG_HASH}</span>) &middot;
        data: Binance daily candles, hashes in <span class="mono">D:\\sindhu_data\\daily\\manifest_daily.json</span></p></div></div>
      <h2 style="margin:24px 0 8px">Part B: daily portfolio strategies vs benchmarks</h2>
      <div id="bxBench">${S2.skeleton(4)}</div><div id="bxDetail" style="margin-top:16px"></div>
      <h2 style="margin:24px 0 8px">Strategy library backtests</h2>
      <div id="bxLib">${S2.skeleton(6)}</div>`;
    const bench = await S2.api("/api/v2/benchmark").catch(e => ({ error: e }));
    if (o.stale()) return;
    if (bench.error) document.getElementById("bxBench").innerHTML = `<div class="card">${S2.errorBlock(bench.error)}</div>`;
    else {
      document.getElementById("bxBench").innerHTML = "";
      S2.table(document.getElementById("bxBench"), {
        rows: bench.units, search: false, pageSize: 10,
        columns: [
          { key: "name", label: "Strategy / benchmark" }, { key: "verdict", label: "Verdict", render: v => (v ? S2.badge(v) : '<span class="badge">benchmark</span>') },
          { key: "oos_ret", label: "OOS return", num: true, get: r => ((r.metrics || {}).OOS || {}).total_return_pct, fmt: v => f.signedPct(v), cls: v => S2.cls(v) },
          { key: "oos_sh", label: "OOS Sharpe", num: true, get: r => ((r.metrics || {}).OOS || {}).sharpe, fmt: v => f.num(v, 2) },
          { key: "oos_dd", label: "OOS max DD", num: true, get: r => ((r.metrics || {}).OOS || {}).max_drawdown_pct, fmt: v => f.pct(v) },
          { key: "full_ret", label: "2018-2026 return", num: true, get: r => ((r.metrics || {}).FULL || {}).total_return_pct, fmt: v => f.signedPct(v, 0), cls: v => S2.cls(v) },
          { key: "p", label: "Bootstrap p", num: true, get: r => r.oos_block_bootstrap_p, fmt: v => f.num(v, 3) },
          { key: "open", label: "", sort: false, render: (v, r) => `<button class="btn sm" type="button" data-bx="${esc(r.id)}">Open</button>` },
        ],
      });
      document.getElementById("bxBench").addEventListener("click", e => { const b = e.target.closest("[data-bx]"); if (b) benchDetail(document.getElementById("bxDetail"), bench, b.dataset.bx); });
      if (o.q.b) benchDetail(document.getElementById("bxDetail"), bench, o.q.b);
    }
    const [lib, val] = await Promise.all([S2.api("/api/backtesting/strategies", { timeout: 30000 }).catch(e => ({ error: e })), S2.api("/api/v2/validation").catch(() => ({ classes: {} }))]);
    if (o.stale()) return;
    if (lib.error) { document.getElementById("bxLib").innerHTML = `<div class="card">${S2.errorBlock(lib.error)}</div>`; return; }
    const classes = val.classes || {};
    const rows = (lib.strategies || []).filter(s => !(String(s.archived) === "true" || s.archived === true)).map(s => {
      const b = s.backtest_snapshot || {}, c = classes[s.id] || {};
      return { id: s.id, name: s.name, vclass: c.class || "NOT VALIDATED", tf: c.entry_tf || "--", trades: b.total_trades, win: b.win_rate, pf: b.profit_factor,
               pnl: b.net_pnl, at: b.computed_at, batch: b.batch_id, label: s.performance_label, factors: s.performance_failed_factors };
    });
    document.getElementById("bxLib").innerHTML = "";
    S2.table(document.getElementById("bxLib"), { rows, csv: "library_backtests", sortKey: "trades",
      filters: [{ key: "vclass", label: "Verdict" }, { key: "tf", label: "TF" }],
      columns: [{ key: "name", label: "Strategy", render: v => esc(String(v).slice(0, 60)), cls: "wrap" }, { key: "vclass", label: "Verdict", render: v => S2.badge(v) },
        { key: "tf", label: "TF" }, { key: "trades", label: "Trades", num: true, fmt: v => f.num(v, 0) }, { key: "win", label: "Win rate", num: true, fmt: v => f.pct(v, 1) },
        { key: "pf", label: "PF", num: true, fmt: v => (v === null || v === undefined ? "--" : Number(v).toFixed(2)) },
        { key: "pnl", label: "Net P&L", num: true, fmt: f.signedMoney, cls: v => S2.cls(v) }, { key: "at", label: "Computed", fmt: v => (v ? f.utc(v).slice(0, 10) : "--") }],
      emptyTitle: "Koi backtest nahi",
      expand: r => `<div class="ds-grid"><div class="span-6"><dl class="kv"><dt>Batch</dt><dd>${esc(r.batch || "--")}</dd><dt>Status</dt><dd>${esc(r.label || "--")}</dd></dl>
        <p class="t-hint" style="margin-top:8px">Library batches keep summary numbers only (no stored equity curve). Open the old Backtesting page to re-run with charts.</p></div>
        <div class="span-6"><div class="label-caps">What is missing</div><p class="t-2" style="font-size:13px">${esc(Array.isArray(r.factors) ? r.factors.join("; ") : String(r.factors || "--")).slice(0, 600)}</p></div></div>` });
  }

  S2.pages.backtests = { title: "Backtests", crumb: "Results, verdicts, charts", render };
})();
