"""Master plan F2 / C6: measure the dashboard home page on the ISOLATED local QA server (port 8421, own data folder).
Logs in with a throwaway QA test account (created on first use; credentials stored ONLY in <QA data dir>\\qa_credentials.json, outside
git, never printed), then loads the home page N times in a fresh browser context and reports: time until the network is quiet,
number of requests, number of API calls, total transferred bytes, the largest response, console errors.
Usage (stable venv): python tools/dashboard_baseline.py [--base http://127.0.0.1:8421] [--hash home] [--runs 3] [--mobile]"""
import argparse
import json
import os
import secrets
import statistics
import time

import requests

CRED = os.path.join(os.environ.get("SINDHU_QA_DATA_DIR", r"D:\sindhu_runtime\smoke_data"), "qa_credentials.json")


def session_cookie(base):
    if os.path.exists(CRED):
        cred = json.load(open(CRED, encoding="utf-8"))
    else:
        cred = {"username": "qa_tester", "password": secrets.token_urlsafe(18)}
    st = requests.get(base + "/api/auth/status", timeout=20).json()
    s = requests.Session()
    if not st.get("account_exists", st.get("configured", True)) or st.get("needs_setup"):
        r = s.post(base + "/api/auth/setup", json=cred, timeout=20)
        if r.status_code == 200:
            os.makedirs(os.path.dirname(CRED), exist_ok=True)
            json.dump(cred, open(CRED, "w", encoding="utf-8"))
    r = s.post(base + "/api/auth/login", json=cred, timeout=20)
    if r.status_code != 200:
        raise SystemExit(f"login on the QA server failed (HTTP {r.status_code}); status was {sorted(st)}")
    return [{"name": c.name, "value": c.value, "url": base} for c in s.cookies]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8421")
    ap.add_argument("--hash", default="home")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--mobile", action="store_true")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    cookies = session_cookie(a.base)
    out = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        for run in range(a.runs):
            ctx = b.new_context(viewport={"width": 390, "height": 844} if a.mobile else {"width": 1440, "height": 900})
            ctx.add_cookies(cookies)
            page = ctx.new_page()
            reqs, errs, sizes = [], [], {}
            last = [time.time()]
            page.on("request", lambda r: (reqs.append(r.url), last.__setitem__(0, time.time())))
            page.on("requestfinished", lambda r: last.__setitem__(0, time.time()))
            page.on("response", lambda r: sizes.__setitem__(r.url, int(r.headers.get("content-length") or 0)))
            page.on("console", lambda m: errs.append(m.text[:120]) if m.type == "error" else None)
            t0 = time.time()
            page.goto(f"{a.base}/#{a.hash}", wait_until="domcontentloaded")
            while time.time() - last[0] < 1.5 and time.time() - t0 < 60:
                page.wait_for_timeout(100)
            # body sizes when content-length is missing (chunked): ask the browser
            total = page.evaluate("performance.getEntriesByType('resource').reduce((s,e)=>s+(e.transferSize||0),0)")
            biggest = page.evaluate("performance.getEntriesByType('resource').map(e=>[e.transferSize||0,e.name.split('/').slice(3).join('/').slice(0,60)]).sort((x,y)=>y[0]-x[0]).slice(0,3)")
            api = [u for u in reqs if "/api/" in u]
            out.append({"run": run + 1, "settle_s": round(last[0] - t0, 2), "requests": len(reqs), "api_calls": len(api),
                        "transfer_kb": round(total / 1024, 1), "largest": biggest, "console_errors": len(errs), "url": page.url.split("#")[0][-20:]})
            ctx.close()
        b.close()
    for o in out:
        print(json.dumps(o))
    print(f"median settle {statistics.median(o['settle_s'] for o in out):.2f} s, median requests {statistics.median(o['requests'] for o in out)}, "
          f"median api calls {statistics.median(o['api_calls'] for o in out)}")


if __name__ == "__main__":
    main()
