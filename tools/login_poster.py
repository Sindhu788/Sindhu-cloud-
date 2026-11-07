"""Master plan V2 LG3: render the login poster (shown when WebGL is missing, motion is reduced, the device is slow, or before the
scene starts) from the SAME scene, with the deterministic demo data, in headless Chromium. Output: static/css/img/login-poster.webp
(<= 80 KB). Usage (stable venv, QA server running): python tools/login_poster.py [--base http://127.0.0.1:8422]"""
import argparse
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "sindhu_web", "static", "css", "img", "login-poster.webp")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8422")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    from PIL import Image
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        ctx = b.new_context(viewport={"width": 1600, "height": 1000}, color_scheme="dark", bypass_csp=True)
        page = ctx.new_page()
        page.goto(a.base + "/login?scene=force", wait_until="load")
        page.wait_for_function("document.getElementById('lgCanvas').classList.contains('on')", timeout=60000)
        page.wait_for_timeout(9000)
        page.add_style_tag(content=".lg-caption{display:none}")
        png = page.locator(".lg-right").screenshot()
        b.close()
    img = Image.open(io.BytesIO(png)).convert("RGB")
    img.thumbnail((1280, 1280))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    for q in (70, 60, 50, 40, 30):
        buf = io.BytesIO()
        img.save(buf, "WEBP", quality=q, method=6)
        if buf.tell() <= 80 * 1024:
            break
    open(OUT, "wb").write(buf.getvalue())
    print(OUT, img.size, buf.tell(), "bytes, quality", q)


if __name__ == "__main__":
    main()
