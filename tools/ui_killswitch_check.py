"""Master plan C6/A16: drive the dashboard kill-switch button on the ISOLATED QA server: Cancel changes nothing; Confirm activates it
(close_positions=false); Resume (with confirm) deactivates it. Usage: python tools/ui_killswitch_check.py --base http://127.0.0.1:8423"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dashboard_baseline import session_cookie


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8423")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    cookies = session_cookie(a.base)
    out = {}
    posts = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        ctx.add_cookies(cookies)
        page = ctx.new_page()
        page.on("request", lambda r: posts.append((r.url.split("/api/")[-1], r.post_data)) if r.method == "POST" and "kill-switch" in r.url else None)
        page.goto(a.base + "/#wallet", wait_until="domcontentloaded")
        page.wait_for_selector("#ppBanner button.pp-kill", timeout=20000)
        page.wait_for_timeout(1500)
        status = lambda: page.evaluate("fetch('/api/paper-trading/kill-switch/status').then(r=>r.json())")
        out["start_active"] = status()["active"]
        page.click("#ppBanner button.pp-kill")
        page.wait_for_selector(".pp-modal", timeout=5000)
        out["modal_text"] = page.inner_text(".pp-modal")[:120]
        page.click('.pp-modal [data-a="no"]')
        page.wait_for_timeout(800)
        out["after_cancel_active"] = status()["active"]
        out["posts_after_cancel"] = len(posts)
        page.click("#ppBanner button.pp-kill")
        page.click('.pp-modal [data-a="yes"]')
        page.wait_for_timeout(2500)
        out["after_confirm_active"] = status()["active"]
        out["banner_after_confirm"] = page.inner_text("#ppBanner .pp-ks")
        page.click("#ppBanner button.pp-kill")
        page.click('.pp-modal [data-a="yes"]')
        page.wait_for_timeout(2500)
        out["after_resume_active"] = status()["active"]
        out["posts"] = posts
        b.close()
    print(json.dumps(out, indent=1))
    ok = (out["after_cancel_active"] == out["start_active"] is False and out["posts_after_cancel"] == 0 and out["after_confirm_active"] is True
          and out["after_resume_active"] is False and '"close_positions":false' in (posts[0][1] or "").replace(" ", ""))
    print("RESULT", "PASS" if ok else "FAIL")


if __name__ == "__main__":
    main()
