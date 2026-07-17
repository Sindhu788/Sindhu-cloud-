import asyncio
import os
import socket
import threading
import time
import webbrowser
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from data_engine import storage
from data_engine.logging_setup import log
from sindhu_web import broadcast
from sindhu_web.security import token_guard_middleware, get_or_create_token
from sindhu_web.api import (
    home, market, data, backtesting, reports, settings as settings_api, backup, jobs, ws,
    knowledge, network as network_api, activity as activity_api, search as search_api,
    system as system_api, paper_trading as paper_trading_api, knowledge_compiler as knowledge_compiler_api,
    ai_integration as ai_integration_api, automation_pipeline as automation_pipeline_api,
    clarification as clarification_api,
)

_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


async def _broadcast_loop():
    """Drains the thread-safe queue that job threads publish() into and
    forwards each message to every connected WebSocket client."""
    loop = asyncio.get_event_loop()
    q = broadcast.get_queue()
    while True:
        message = await loop.run_in_executor(None, q.get)
        dead = []
        for client in list(broadcast.clients):
            try:
                await client.send_json(message)
            except Exception:
                dead.append(client)
        for client in dead:
            broadcast.clients.discard(client)


def _warm_caches():
    """Pre-computes the few genuinely expensive endpoint payloads in the
    background at startup.

    sindhu_web.cache already serves a stale value while refreshing, so a
    warm cache never blocks a request -- but the very FIRST call for a key
    has nothing to serve and must compute inline. For /api/market that
    meant one unlucky user waiting ~57s after every restart (a 66s Binance
    get_tickers() call plus a 50-coin indicator pass), and ~8s for
    /api/data. Doing that work here, off the request path, means whoever
    opens those pages first gets an already-populated cache instead."""
    import time as _time
    for label, fn in (
        ("market", lambda: market.get_market()),
        ("data", lambda: data.get_data_overview()),
        ("home", lambda: home.get_home()),
    ):
        try:
            t0 = _time.perf_counter()
            fn()
            log(f"Cache warmed: {label} ({(_time.perf_counter() - t0) * 1000:.0f}ms)")
        except Exception as exc:
            log(f"Cache warm for {label} failed (non-fatal): {exc!r}")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    storage.init_db()
    backup.start_auto_backup_thread()
    threading.Thread(target=_warm_caches, daemon=True).start()
    task = asyncio.create_task(_broadcast_loop())
    yield
    task.cancel()


def create_app():
    app = FastAPI(title="SINDHU Dashboard API", lifespan=_lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _token_guard(request: Request, call_next):
        return await token_guard_middleware(request, call_next)

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception):
        log(f"API ERROR on {request.method} {request.url.path}: {exc!r}")
        return JSONResponse({"detail": "internal error", "error": repr(exc)}, status_code=500)

    for router in (home.router, market.router, data.router, backtesting.router,
                   reports.router, settings_api.router, backup.router, jobs.router, ws.router,
                   knowledge.router, network_api.router, activity_api.router, search_api.router,
                   system_api.router, paper_trading_api.router, knowledge_compiler_api.router,
                   ai_integration_api.router, automation_pipeline_api.router, clarification_api.router):
        app.include_router(router)

    @app.get("/api/token")
    def get_token():
        return {"token": get_or_create_token()}

    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/")
    def index():
        # Cache-bust app.js/app.css with each file's own mtime so a browser
        # (or an automated CDP session) can never serve a stale script/style
        # after a deploy -- every real change gets a genuinely new URL
        # instead of relying on the browser to notice the file changed.
        index_path = os.path.join(_STATIC_DIR, "index.html")
        with open(index_path, "r", encoding="utf-8") as f:
            html = f.read()
        js_path = os.path.join(_STATIC_DIR, "js", "app.js")
        css_path = os.path.join(_STATIC_DIR, "css", "app.css")
        js_v = int(os.path.getmtime(js_path)) if os.path.exists(js_path) else 0
        css_v = int(os.path.getmtime(css_path)) if os.path.exists(css_path) else 0
        html = html.replace('/static/js/app.js"', f'/static/js/app.js?v={js_v}"')
        html = html.replace('/static/css/app.css"', f'/static/css/app.css?v={css_v}"')
        # The root document itself must never be cached -- a cached "/" means
        # a browser (or an automated CDP session reusing one tab across many
        # restarts) keeps re-using an old <script src> reference forever,
        # even after the cache-busted URL above changes on the server.
        return HTMLResponse(html, headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"})

    return app


app = create_app()


def _dual_stack_socket(port):
    """A single listening socket serving BOTH IPv4 and IPv6.

    Binding plain "0.0.0.0" listens on IPv4 only. On Windows, "localhost"
    resolves to the IPv6 address ::1 FIRST, so every browser request to
    http://localhost:8420 spent ~2 SECONDS failing the IPv6 attempt before
    falling back to IPv4 (measured: 2029ms to ::1 vs 0.7ms to 127.0.0.1).
    That 2s tax applied to every request -- API calls AND static files --
    which is what made the whole dashboard feel broken and unusable.

    Explicitly clearing IPV6_V6ONLY (it defaults to 1 on Windows) makes one
    "::" socket accept IPv4 connections too, so both ::1 and 127.0.0.1
    connect instantly. Falls back to a normal IPv4 socket if the platform
    refuses dual-stack, so this can never stop the server from starting."""
    try:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("::", port))
        sock.listen(2048)
        sock.set_inheritable(True)
        return sock
    except OSError as exc:
        log(f"Dual-stack (IPv6+IPv4) bind failed ({exc!r}); falling back to IPv4-only.")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", port))
        sock.listen(2048)
        sock.set_inheritable(True)
        return sock


def run(host="0.0.0.0", port=8420, open_browser=True):
    import uvicorn

    if open_browser:
        def _open():
            time.sleep(1.2)
            webbrowser.open(f"http://127.0.0.1:{port}")
        threading.Thread(target=_open, daemon=True).start()

    sock = _dual_stack_socket(port)
    config = uvicorn.Config(app, log_level="info")
    uvicorn.Server(config).run(sockets=[sock])
