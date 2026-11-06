"""Master plan C6: Playwright screenshots of dashboard pages at phone (390x844) and laptop (1440x900), logged in with the QA test account
(tools/dashboard_baseline.py), plus console errors per page. Usage (stable venv):
python tools/ui_screens.py --base http://127.0.0.1:8422 --out docs/ui/before [--pages home,paper_trading,...]"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dashboard_baseline import session_cookie

DEFAULT_PAGES = ["wallet", "home", "paper_trading", "strategies", "backtesting", "settings", "ceo"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8422")
    ap.add_argument("--out", required=True)
    ap.add_argument("--pages", default=",".join(DEFAULT_PAGES))
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    os.makedirs(a.out, exist_ok=True)
    cookies = session_cookie(a.base)
    report = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for label, vp in (("phone", {"width": 390, "height": 844}), ("laptop", {"width": 1440, "height": 900})):
            ctx = b.new_context(viewport=vp)
            ctx.add_cookies(cookies)
            page = ctx.new_page()
            errs = []
            page.on("console", lambda m: errs.append(m.text[:160]) if m.type == "error" else None)
            page.on("pageerror", lambda e: errs.append("PAGEERROR " + str(e)[:160]))
            page.goto(a.base + "/", wait_until="domcontentloaded")
            page.wait_for_timeout(2500)
            for pid in a.pages.split(","):
                errs.clear()
                t0 = time.time()
                page.evaluate(f"location.hash = '#{pid}'")
                page.wait_for_timeout(3500)
                hscroll = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 2")
                path = os.path.join(a.out, f"{pid}_{label}.png")
                page.screenshot(path=path, full_page=False)
                report.append({"page": pid, "size": label, "console_errors": len(errs), "first_error": errs[:1], "horizontal_scroll": hscroll,
                               "seconds": round(time.time() - t0, 1)})
            ctx.close()
        b.close()
    with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    for r in report:
        print(json.dumps(r))


if __name__ == "__main__":
    main()
