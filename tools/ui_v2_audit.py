"""Master plan V2 F2 / PG11: per-page UI audit on the ISOLATED local QA server.

For every dashboard page (hash route) it does a full, cold page load in a fresh browser context and records:
- screenshot at phone 390x844 and laptop 1440x900 (and, with --themes, dark + light),
- number of requests and transferred bytes (PerformanceResourceTiming transferSize + navigation entry),
- LCP and CLS via PerformanceObserver (Playwright + Chromium, NOT Lighthouse),
- console errors and horizontal scroll.
Static JS/CSS gzip sizes are computed from the files on disk (the SPA serves the same bundle for every page).

Usage (stable venv): python tools/ui_v2_audit.py --base http://127.0.0.1:8422 --out docs/ui/v2/before [--pages a,b] [--themes dark,light]
Logs in with the throwaway QA account of tools/dashboard_baseline.py (credentials never printed)."""
import argparse
import gzip
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dashboard_baseline import session_cookie  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALL_PAGES = ("wallet,home,market,data,backtesting,reports,settings,knowledge,strategies,paper_trading,knowledge_compiler,ai_center,"
             "backtest_history,pipeline_history,evolution,evolution_history,sindhu_strategy,signal_tracker,strategy_lab,self_learning,"
             "challenge_mode,strategy_wizard,web_sourced_strategies,control_center,telegram_dashboard,ceo,clarification_center,"
             "external_signals,compare,live_logs,project_status,incidents,strategy_lifecycle,strategy_overview,risk_department,"
             "memory_core,configuration_panel,practice_mode")

PERF_INIT = """
window.__lcp = 0; window.__cls = 0;
try {
  new PerformanceObserver(l => { for (const e of l.getEntries()) window.__lcp = Math.max(window.__lcp, e.startTime); })
    .observe({type: 'largest-contentful-paint', buffered: true});
  new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__cls += e.value; })
    .observe({type: 'layout-shift', buffered: true});
} catch (e) {}
"""

COLLECT = r"""() => {
  const res = performance.getEntriesByType('resource');
  let js = 0, css = 0;
  for (const r of res) { if (/\.m?js(\?|$)/.test(r.name)) js += (r.encodedBodySize || 0); else if (/\.css(\?|$)/.test(r.name)) css += (r.encodedBodySize || 0); }
  const nav = performance.getEntriesByType('navigation')[0];
  let bytes = nav ? (nav.transferSize || 0) : 0;
  for (const r of res) bytes += (r.transferSize || 0);
  return {requests: res.length + 1, transfer_bytes: bytes, js_bytes: js, css_bytes: css, lcp_ms: Math.round(window.__lcp || 0),
          cls: Math.round((window.__cls || 0) * 1000) / 1000,
          hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth + 2};
}"""


def static_sizes():
    out = {}
    base = os.path.join(ROOT, "sindhu_web", "static")
    for sub in ("js", "css"):
        d = os.path.join(base, sub)
        for fn in sorted(os.listdir(d)):
            p = os.path.join(d, fn)
            if os.path.isfile(p) and fn.endswith((".js", ".css")):
                raw = open(p, "rb").read()
                out[f"{sub}/{fn}"] = {"raw": len(raw), "gzip": len(gzip.compress(raw, 6))}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8422")
    ap.add_argument("--out", required=True)
    ap.add_argument("--pages", default=ALL_PAGES)
    ap.add_argument("--themes", default="")
    ap.add_argument("--settle-ms", type=int, default=4000)
    ap.add_argument("--axe", default="", help="path to axe.min.js (axe-core) for an accessibility scan per page")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    os.makedirs(a.out, exist_ok=True)
    cookies = session_cookie(a.base)
    themes = [t for t in a.themes.split(",") if t] or [""]
    rows = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for theme in themes:
            for label, vp in (("phone", {"width": 390, "height": 844}), ("laptop", {"width": 1440, "height": 900})):
                for pid in a.pages.split(","):
                    ctx = b.new_context(viewport=vp, color_scheme=(theme or "dark") if theme else None, bypass_csp=bool(a.axe))
                    ctx.add_cookies(cookies)
                    if theme:
                        ctx.add_init_script(f"try{{localStorage.setItem('sindhu_theme','{theme}')}}catch(e){{}}")
                    ctx.add_init_script(PERF_INIT)
                    page = ctx.new_page()
                    errs = []
                    page.on("console", lambda m: errs.append(m.text[:160]) if m.type == "error" else None)
                    page.on("pageerror", lambda e: errs.append("PAGEERROR " + str(e)[:160]))
                    t0 = time.time()
                    try:
                        page.goto(f"{a.base}{pid}" if pid.startswith("/") and not pid.startswith("/#") else f"{a.base}/#{pid}", wait_until="load", timeout=60000)
                        page.wait_for_timeout(a.settle_ms)
                        m = page.evaluate(COLLECT)
                        if a.axe:
                            page.add_script_tag(path=a.axe)
                            ax = page.evaluate("""async () => { const r = await axe.run(document, {resultTypes: ['violations']});
                              return r.violations.map(v => ({id: v.id, impact: v.impact, nodes: v.nodes.length})); }""")
                            m["axe_serious"] = [v for v in ax if v["impact"] in ("serious", "critical")]
                            m["axe_other"] = [v for v in ax if v["impact"] not in ("serious", "critical")]
                        safe = pid.strip("/#").replace("/", "_").replace("?", "_").replace("=", "-") or "root"
                        name = f"{safe}_{label}" + (f"_{theme}" if theme else "") + ".png"
                        page.screenshot(path=os.path.join(a.out, name), full_page=False)
                    except Exception as e:  # keep auditing the other pages
                        m = {"error": str(e)[:200]}
                    m.update({"page": pid, "size": label, "theme": theme or "default", "console_errors": len(errs),
                              "first_error": errs[:1], "seconds": round(time.time() - t0, 1)})
                    rows.append(m)
                    print(json.dumps(m), flush=True)
                    ctx.close()
        b.close()
    report = {"measured_with": "Playwright Chromium + PerformanceObserver (not Lighthouse)", "base": a.base,
              "static_files": static_sizes(), "pages": rows}
    with open(os.path.join(a.out, "audit.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)


if __name__ == "__main__":
    main()
