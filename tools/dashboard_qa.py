"""Dashboard QA with Playwright (Day 8). Modes:
  profile   load one page (default #ceo) and print the network timeline: number of API calls, slowest calls, time to settle, console errors
  pages     open every sidebar page, check console/page errors and http errors, time to settle (desktop or mobile viewport)
Usage: python tools/dashboard_qa.py profile [--base http://127.0.0.1:8421] [--hash ceo] [--mobile] [--runs 3]
       python tools/dashboard_qa.py pages   [--base ...] [--mobile]
Read-only against Cloud (--base https://sindhu-cloud-1.onrender.com): only unauthenticated pages can be checked; no credentials are ever typed."""
import argparse
import json
import statistics
import sys
import time

from playwright.sync_api import sync_playwright


def settle(page, quiet_ms=1200, max_ms=40000):
    """Wait until no request has started or finished for quiet_ms; returns seconds taken."""
    t0 = time.time(); last = [time.time()]
    page.on("request", lambda r: last.__setitem__(0, time.time()))
    page.on("requestfinished", lambda r: last.__setitem__(0, time.time()))
    page.on("requestfailed", lambda r: last.__setitem__(0, time.time()))
    while (time.time() - last[0]) * 1000 < quiet_ms and (time.time() - t0) * 1000 < max_ms:
        page.wait_for_timeout(100)
    return last[0] - t0


def profile(args):
    out = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for run in range(args.runs):
            ctx = b.new_context(viewport={"width": 390, "height": 844} if args.mobile else {"width": 1440, "height": 900})
            page = ctx.new_page()
            reqs, errs = [], []
            page.on("console", lambda m: errs.append(m.text[:120]) if m.type == "error" else None)
            page.on("pageerror", lambda e: errs.append("PAGEERROR " + str(e)[:120]))
            page.on("requestfinished", lambda r: reqs.append((r.url, r.timing)))
            t0 = time.time()
            page.goto(f"{args.base}/#{args.hash}", wait_until="domcontentloaded")
            took = settle(page)
            api = [(u, t) for u, t in reqs if "/api/" in u]
            def dur(t):
                return max((t.get("responseEnd", 0) or 0), 0) / 1000.0
            slow = sorted(api, key=lambda x: -dur(x[1]))[:6]
            out.append({"run": run + 1, "settle_s": round(took, 2), "api_calls": len(api), "all_requests": len(reqs), "errors": len(errs),
                        "slowest": [(u.split("/api/")[-1][:60], round(dur(t), 2)) for u, t in slow], "error_samples": errs[:3]})
            ctx.close()
        b.close()
    for o in out:
        print(json.dumps(o))
    print("settle median %.2f s over %d runs (first run is the cold one)" % (statistics.median(o["settle_s"] for o in out), len(out)))


def pages(args):
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 390, "height": 844} if args.mobile else {"width": 1440, "height": 900})
        page = ctx.new_page()
        errs = []
        page.on("console", lambda m: errs.append(m.text[:140]) if m.type == "error" else None)
        page.on("pageerror", lambda e: errs.append("PAGEERROR " + str(e)[:140]))
        bad_http = []
        page.on("response", lambda r: bad_http.append(f"{r.status} {r.url.split('/api/')[-1][:50]}") if r.status >= 400 and "/api/" in r.url else None)
        page.goto(f"{args.base}/", wait_until="domcontentloaded"); settle(page)
        ids = page.eval_on_selector_all("#navList a[data-id]", "els => els.map(e => e.getAttribute('data-id'))")
        rows = []
        for pid in ids:
            errs.clear(); bad_http.clear()
            t0 = time.time()
            page.evaluate(f"location.hash = '#{pid}'")
            took = settle(page, quiet_ms=1000, max_ms=25000)
            hscroll = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 2")
            rows.append((pid, round(took, 2), len(errs), len(bad_http), hscroll, (errs[:1] + bad_http[:1])))
        b.close()
    print("| Page | Settle s | Console/page errors | HTTP >= 400 | Horizontal scroll | First problem |")
    print("|---|---|---|---|---|---|")
    for pid, took, ne, nh, hs, first in rows:
        print(f"| {pid} | {took} | {ne} | {nh} | {'YES' if hs else 'no'} | {first[0] if first else ''} |")
    print(f"\n{len(rows)} pages; with console errors: {sum(1 for r in rows if r[2])}; with http errors: {sum(1 for r in rows if r[3])}; horizontal scroll: {sum(1 for r in rows if r[4])}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["profile", "pages"])
    ap.add_argument("--base", default="http://127.0.0.1:8421")
    ap.add_argument("--hash", default="ceo")
    ap.add_argument("--mobile", action="store_true")
    ap.add_argument("--runs", type=int, default=3)
    a = ap.parse_args()
    {"profile": profile, "pages": pages}[a.mode](a)
