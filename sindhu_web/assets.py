"""Master plan V2 DS3 (N4): fingerprinted, pre-compressed static assets.

- Every file under static/css, static/js and static/vendor gets a content-hash URL: /assets/<dir>/<name>.<hash10>.<ext>
  served with `Cache-Control: public, max-age=31536000, immutable`. A changed file gets a new URL, so a browser can never keep old
  CSS/JS after a deploy. HTML pages are served with `no-cache` and point at the current URLs.
- The v2 app is one bundle: BUNDLE_FILES are concatenated (each is a self-contained IIFE) into the virtual file js/v2.bundle.js.
- CSS url(...) references to fonts/images are rewritten to their hashed URLs before the CSS itself is hashed.
- Gzip (and brotli when the `brotli` module is installed) is computed ONCE per process for text files over 1 KB and kept in memory
  (about 0.5 MB). Render has no build step besides pip install, so "at build" here means "at the first request after start".
- The build tag (commit + asset hash) is shown in the footer so the owner can see that a new design is live.
No CDN, no network, no database: pure file reads."""
import gzip
import hashlib
import json
import os
import re
import subprocess
import threading

from fastapi import Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
ASSET_DIRS = ("css", "js", "vendor")
BUNDLE_NAME = "js/v2.bundle.js"
BUNDLE_FILES = ["js/v2/ds.js", "js/v2/shell.js", "js/v2/pages_home.js", "js/v2/pages_trades.js", "js/v2/pages_strategies.js",
                "js/v2/pages_backtests.js", "js/v2/pages_settings.js", "js/v2/pages_system.js", "js/v2/pages_more.js",
                "js/v2/uikit.js", "js/v2/palette.js"]
LOGIN_BUNDLE_NAME = "js/login.bundle.js"
LOGIN_BUNDLE_FILES = ["js/v2/login.js"]
IMMUTABLE = "public, max-age=31536000, immutable"
NO_CACHE = "no-cache"
_TYPES = {".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
          ".svg": "image/svg+xml", ".woff2": "font/woff2", ".json": "application/json", ".txt": "text/plain; charset=utf-8",
          ".md": "text/plain; charset=utf-8", ".webp": "image/webp", ".png": "image/png"}
_TEXT = {".js", ".mjs", ".css", ".svg", ".json", ".txt", ".md"}

_lock = threading.Lock()
_state = {"manifest": None, "by_url": None, "build": None}

try:  # optional
    import brotli as _brotli  # type: ignore
except Exception:  # pragma: no cover - not installed on the laptop or Render today
    _brotli = None


def _h(data):
    return hashlib.sha256(data).hexdigest()[:10]


def _hashed_url(logical, digest):
    base, ext = os.path.splitext(logical)
    return f"/assets/{base}.{digest}{ext}"


def _read(logical):
    with open(os.path.join(STATIC_DIR, *logical.split("/")), "rb") as f:
        return f.read()


def _list_files():
    out = []
    for d in ASSET_DIRS:
        root = os.path.join(STATIC_DIR, d)
        for dirpath, _dirs, files in os.walk(root):
            for fn in files:
                rel = os.path.relpath(os.path.join(dirpath, fn), STATIC_DIR).replace(os.sep, "/")
                out.append(rel)
    return sorted(out)


_CSS_URL = re.compile(r"""url\((["']?)([^)"']+)\1\)""")


def _rewrite_css(logical, data, manifest):
    text = data.decode("utf-8")
    base_dir = os.path.dirname(logical)

    def sub(m):
        ref = m.group(2)
        if ref.startswith(("data:", "http:", "https:", "/", "#")):
            return m.group(0)
        target = os.path.normpath(os.path.join(base_dir, ref)).replace(os.sep, "/")
        e = manifest.get(target)
        return f'url("{e["url"]}")' if e else m.group(0)

    return _CSS_URL.sub(sub, text).encode("utf-8")


def _entry(logical, data, virtual=False):
    ext = os.path.splitext(logical)[1].lower()
    digest = _h(data)
    e = {"logical": logical, "url": _hashed_url(logical, digest), "hash": digest, "size": len(data), "type": _TYPES.get(ext, "application/octet-stream"),
         "data": data, "gz": None, "br": None}
    if ext in _TEXT and len(data) > 1024:
        e["gz"] = gzip.compress(data, 9, mtime=0)
        if _brotli is not None:
            try:
                e["br"] = _brotli.compress(data, quality=9)
            except Exception:
                e["br"] = None
    if not virtual and (e["gz"] is not None or ext in (".woff2", ".png", ".webp")):
        e["data"] = None  # real files are read from disk when a client cannot take the compressed copy (keeps memory low)
    return e


def _build():
    files = _list_files()
    manifest = {}
    # 1) everything that is not CSS (fonts, vendor js, svg, our js)
    for logical in files:
        if not logical.endswith(".css"):
            manifest[logical] = _entry(logical, _read(logical))
    # 2) bundles (concatenated IIFEs)
    for name, parts in ((BUNDLE_NAME, BUNDLE_FILES), (LOGIN_BUNDLE_NAME, LOGIN_BUNDLE_FILES)):
        chunks = []
        for p in parts:
            if os.path.exists(os.path.join(STATIC_DIR, *p.split("/"))):
                chunks.append(f"/* {p} */\n".encode() + _read(p) + b"\n;\n")
        manifest[name] = _entry(name, b"".join(chunks), virtual=True)
    # 3) CSS last, after its url() targets have hashed URLs
    for logical in files:
        if logical.endswith(".css"):
            manifest[logical] = _entry(logical, _rewrite_css(logical, _read(logical), manifest), virtual=True)
    by_url = {e["url"]: e for e in manifest.values()}
    combined = _h("".join(e["hash"] for _, e in sorted(manifest.items())).encode())
    return manifest, by_url, f"{_commit()}-{combined[:6]}"


def _commit():
    c = os.environ.get("RENDER_GIT_COMMIT") or os.environ.get("SINDHU_COMMIT")
    if c:
        return c[:7]
    try:
        out = subprocess.run(["git", "rev-parse", "--short=7", "HEAD"], cwd=os.path.dirname(STATIC_DIR), capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return "dev"


def state():
    with _lock:
        if _state["manifest"] is None or os.environ.get("SINDHU_ASSETS_DEV") == "1":
            _state["manifest"], _state["by_url"], _state["build"] = _build()
        return _state["manifest"], _state["by_url"], _state["build"]


def reset():
    with _lock:
        _state.update(manifest=None, by_url=None, build=None)


def url(logical):
    m, _, _ = state()
    e = m.get(logical)
    return e["url"] if e else "/static/" + logical


def build_tag():
    return state()[2]


_STATIC_REF = re.compile(r"""/static/((?:css|js|vendor)/[A-Za-z0-9_./-]+?)(?:\?v=\d+)?(?=["'])""")


def render_html(name, extra=None):
    """Read static/<name>, point every /static/(css|js|vendor)/... reference at its hashed URL, fill {{ASSETS_JSON}} and {{BUILD}}."""
    m, _, build = state()
    with open(os.path.join(STATIC_DIR, name), encoding="utf-8") as f:
        html = f.read()
    html = _STATIC_REF.sub(lambda mm: m[mm.group(1)]["url"] if mm.group(1) in m else mm.group(0), html)
    public = {k: e["url"] for k, e in m.items() if k.startswith("vendor/") or k.endswith(".bundle.js") or k.startswith("css/")}
    html = html.replace("{{ASSETS_JSON}}", json.dumps(public, separators=(",", ":")).replace("</", "<\\/"))
    html = html.replace("{{BUILD}}", build)
    for k, v in (extra or {}).items():
        html = html.replace("{{" + k + "}}", v)
    return html


def html_response(name, extra=None, status_code=200):
    return HTMLResponse(render_html(name, extra), status_code=status_code, headers={"Cache-Control": NO_CACHE})


def serve(request: Request, path: str):
    _, by_url, _ = state()
    e = by_url.get("/assets/" + path)
    if e is None:
        return PlainTextResponse("not found", status_code=404, headers={"Cache-Control": "no-store"})
    headers = {"Cache-Control": IMMUTABLE, "ETag": f'"{e["hash"]}"', "Vary": "Accept-Encoding", "X-Content-Type-Options": "nosniff"}
    if request.headers.get("if-none-match") == headers["ETag"]:
        return Response(status_code=304, headers=headers)
    accept = request.headers.get("accept-encoding", "")
    if e.get("br") is not None and "br" in accept:
        headers["Content-Encoding"] = "br"
        return Response(e["br"], media_type=e["type"], headers=headers)
    if e.get("gz") is not None and "gzip" in accept:
        headers["Content-Encoding"] = "gzip"
        return Response(e["gz"], media_type=e["type"], headers=headers)
    data = e["data"] if e["data"] is not None else _read(e["logical"])
    return Response(data, media_type=e["type"], headers=headers)


def register(app):
    """Mount /assets/... on a FastAPI app (both the local server and the Cloud app)."""
    @app.get("/assets/{path:path}", include_in_schema=False)
    def _assets(request: Request, path: str):
        return serve(request, path)

    @app.head("/assets/{path:path}", include_in_schema=False)
    def _assets_head(request: Request, path: str):
        r = serve(request, path)
        return Response(status_code=r.status_code, headers={k: v for k, v in r.headers.items() if k.lower() != "content-length"})


def memory_bytes():
    m, _, _ = state()
    return sum(len(e["data"] or b"") + len(e["gz"] or b"") + len(e["br"] or b"") for e in m.values())


def legacy_response(cloud):
    """The old dashboard (static/index.html, unchanged app.js) at /legacy, with hashed asset URLs and the v2 tokens."""
    html = render_html("index.html")
    if cloud:
        html = html.replace('<html lang="en" data-theme="dark">', '<html lang="en" data-theme="dark" data-default-hash="wallet">', 1)
    return HTMLResponse(html, headers={"Cache-Control": NO_CACHE})


def register_pages(app, cloud):
    """/, /legacy and /ui-kit for both servers. Login is checked here (the security middleware leaves "/" to the page itself)."""
    from fastapi.responses import RedirectResponse
    from sindhu_web import auth

    def _logged_in(request):
        return auth.is_valid_session(request.cookies.get(auth.SESSION_COOKIE))

    @app.get("/", include_in_schema=False)
    def index(request: Request):
        if not _logged_in(request):
            return RedirectResponse(url="/login")
        return html_response("app2.html")

    @app.get("/legacy", include_in_schema=False)
    def legacy(request: Request):
        if not _logged_in(request):
            return RedirectResponse(url="/login")
        return legacy_response(cloud)

    @app.get("/ui-kit", include_in_schema=False)
    def ui_kit(request: Request):
        if not _logged_in(request):
            return RedirectResponse(url="/login")
        return RedirectResponse(url="/#/ui-kit")
