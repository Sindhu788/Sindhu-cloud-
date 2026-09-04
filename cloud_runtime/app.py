"""The lightweight, cloud-deployable SINDHU app -- Paper Trading engine +
Telegram signal system + a login-gated dashboard for those two sections,
and nothing else.

WHY THIS FILE EXISTS SEPARATELY FROM sindhu_web/server.py: that module's
own import list pulls in every heavy router (backtesting, evolution,
AI Center, the strategy import/extraction pipeline, automation pipeline)
as a side effect of import, and its module-level `app = create_app()`
builds that full app the INSTANT sindhu_web.server is imported -- there is
no way to "import just a little bit" of it. This file builds its own,
separate, minimal FastAPI app instead, importing only what the paper
trading engine, the Telegram signal system, and the login gate actually
need.

WHAT IS DELIBERATELY IMPORTED FROM backtest_engine/ and evolution_engine/
despite the deployment task's "don't bring the backtest engine, optimizer,
or Evolution Engine into this runner" rule -- and why each is fine:
  - backtest_engine.strategy_library: the strategy LIBRARY (JSON files
    under strategies/library/<id>/), not the backtest RUNNER. Loading a
    strategy's already-saved config is explicitly required by Step 2 of
    the deployment task.
  - backtest_engine.validator / backtest_engine.engine: pure-Python trade
    mechanics (signal validation, fill/exit simulation) shared by BOTH the
    offline backtester and the live paper trading engine so the two agree
    on what a "valid trade" and a "stop-loss hit" mean. paper_trading's
    OWN risk_manager.py and position_manager.py import backtest_engine.
    engine directly -- there is no way to run the paper trading engine
    (explicitly required) without it. Confirmed zero database coupling,
    zero optimizer/Governor coupling (DEPLOYMENT_CHECKPOINT.md Step 0).
  - evolution_engine.lesson_generator / generation_manager: called
    unconditionally from position_manager.py's own close() path to
    auto-generate "BOT" lessons/strategies from trade history. Confirmed
    (DEPLOYMENT_CHECKPOINT.md Step 0) to import only pure Python +
    data_engine.storage -- zero coupling to the heavy Governor/tick-loop
    system ("Evolution Engine" in the sense the deployment task's GLOBAL
    RULES mean it). evolution_engine.engine (the actual Governor/tick-loop)
    is never imported.
Never imported, anywhere in this file's dependency graph: backtest_engine's
batch runner (runner.py/mtf_worker.py), the optimizer, evolution_engine.
engine/governor, ai_integration's extraction pipeline, or
automation_pipeline.

Entry point for Railway (see Procfile):
    uvicorn cloud_runtime.app:app --host 0.0.0.0 --port $PORT
"""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from data_engine import storage
from data_engine.logging_setup import log
from sindhu_web import auth, broadcast
from sindhu_web.api import auth as auth_api
from sindhu_web.api import paper_trading as paper_trading_api
from sindhu_web.api import ws
from sindhu_web.security import get_or_create_token, token_guard_middleware

_STATIC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sindhu_web", "static"
)

APP_VERSION = "5.1-cloud"

# Only the pages this runner actually mounts routers for. The local app's
# full nav (sindhu_web/api/home.py NAV_PAGES) lists dozens of pages
# (Backtesting, Evolution, AI Center, ...) this runner never serves --
# listing them here would put dead links in the cloud sidebar.
#
# "strategy_overview" is deliberately its own id, NOT "strategies" -- that
# id already belongs to the local app's full Strategy Library page
# (renderStrategies in app.js, backed by /api/backtesting/strategies and
# other routers this runner never mounts). Reusing that id here would make
# the SAME shared PAGES{} entry try to render on a runner that can't serve
# it. renderStrategyOverview (app.js) is a new, separate function built
# specifically against endpoints this runner already mounts
# (paper_trading_api's /api/paper-trading/strategy-overview).
_CLOUD_NAV_PAGES = [
    {"id": "paper_trading", "label": "Paper Trading", "enabled": True, "icon": "wallet", "group": "Paper Trading"},
    {"id": "strategy_overview", "label": "Strategies", "enabled": True, "icon": "layers", "group": "Paper Trading"},
    {"id": "telegram_dashboard", "label": "Telegram Signals", "enabled": True, "icon": "send", "group": "Paper Trading"},
    # Part 7 (nav audit, this task): "signal_tracker" was a genuine
    # oversight, not a deliberate exclusion like every other local-only
    # page -- its page (renderSignalTracker, app.js) only ever calls
    # paper_trading_api endpoints already mounted here
    # (/api/paper-trading/signal-tracker/feed and /match-table), same
    # router as every other page in this list. signal_tracker.py's
    # backtest-comparison lookup was hardened (see paper_trading/
    # signal_tracker.py's _backtest_win_rate) to degrade to "no backtest
    # data available" rather than crash on this runner's curated Postgres
    # schema, which never stores backtest_batches/backtest_results.
    {"id": "signal_tracker", "label": "Signal Tracker", "enabled": True, "icon": "activity", "group": "Paper Trading"},
    # Master Task 3, Phase 2.1: qualifies for the cloud nav (unlike Phase
    # 1's Self-Learning Engine) -- renderChallengeMode() (app.js) calls
    # only /api/paper-trading/challenges/* endpoints, all part of
    # paper_trading_api.router, already mounted above.
    {"id": "challenge_mode", "label": "Challenge Mode", "enabled": True, "icon": "target", "group": "Paper Trading"},
]
_CLOUD_NAV_GROUPS = ["Paper Trading"]


async def _broadcast_loop():
    """Identical in spirit to sindhu_web/server.py's own broadcast loop --
    duplicated rather than imported so this file never has to import
    sindhu_web.server (see module docstring)."""
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


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Dispatches to the curated Postgres schema when DATABASE_URL is set
    # (data_engine/db_backend.py), or a normal local SQLite file otherwise
    # -- so this same runner also works for a quick local smoke test
    # against a throwaway SQLite file, with no Postgres server required.
    storage.init_db()

    # Same "resume only if it was already running" contract as the local
    # app's lifespan (sindhu_web/server.py) -- a fresh deploy or restart
    # never silently leaves the engine off just because nobody was there
    # to flip it back on, but also never force-starts it against the
    # CEO's explicit choice.
    from paper_trading.engine import resume_engine_on_startup
    resume_engine_on_startup()

    from paper_trading import telegram_bot as _telegram_bot
    _tg_enabled = _telegram_bot.load_settings().get("master_send_enabled", True)
    log(f"[cloud-runtime] Telegram sending is currently {'ON' if _tg_enabled else 'OFF'} "
        f"(restored from the last saved setting).")

    # Part 6 (24h cloud-to-local sync): started ONLY here, never from the
    # local laptop's full app (sindhu_web/server.py) -- this is a
    # cloud-runtime-only backup mechanism, per this task's own scope rule.
    from paper_trading import cloud_sync
    cloud_sync.start_cloud_sync_scheduler_thread()

    # Grand Feature Expansion, Phase 2 Features 20-21: /status, /pause,
    # /resume Telegram bot commands. Long-polling, so it needs no public
    # webhook URL/setup step -- works identically here and on the local
    # laptop (see sindhu_web/server.py's own lifespan for that side).
    from paper_trading import telegram_commands
    telegram_commands.start_command_polling_thread()

    # Master Task 3, Phase 2.20: Challenge Mode's achievability-trend
    # snapshots -- Challenge Mode is already fully cloud-reachable (its own
    # cloud_settings dual-write), so this runs here too, not just on the
    # local laptop's server.py.
    from paper_trading.challenge_multi import start_achievability_snapshot_scheduler_thread
    start_achievability_snapshot_scheduler_thread()

    task = asyncio.create_task(_broadcast_loop())
    yield
    task.cancel()


def create_app():
    app = FastAPI(title="SINDHU Cloud (Lightweight)", lifespan=_lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Same middleware the local app uses, unmodified -- the login-session
    # gate always applies; the LAN-only check inside it is skipped only
    # when SINDHU_CLOUD_MODE=1 is set (see sindhu_web/security.py).
    @app.middleware("http")
    async def _token_guard(request: Request, call_next):
        return await token_guard_middleware(request, call_next)

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception):
        # Logs the real exception server-side for diagnosis, but the
        # response never includes a traceback or any internal detail --
        # see cloud_runtime/README.md's security notes.
        log(f"[cloud-runtime] API ERROR on {request.method} {request.url.path}: {exc!r}")
        return JSONResponse({"detail": "internal error"}, status_code=500)

    for router in (paper_trading_api.router, ws.router, auth_api.router):
        app.include_router(router)

    @app.get("/api/token")
    def get_token():
        return {"token": get_or_create_token()}

    @app.get("/api/nav")
    def get_nav():
        return {"pages": _CLOUD_NAV_PAGES, "groups": _CLOUD_NAV_GROUPS}

    # The topbar's version/health pill (app.js refreshTopbarStatus(), runs
    # on every page regardless of route) polls /api/home -- the real one
    # lives in sindhu_web/api/home.py, which is NOT mounted here (it pulls
    # in backtest_engine.reports and knowledge_engine). This stub keeps
    # that cosmetic pill populated without importing any of that.
    @app.get("/api/home")
    def get_home_stub():
        return {"version": APP_VERSION, "system_health": "OK"}

    @app.get("/health")
    def health_check():
        """For an external uptime pinger (e.g. cron-job.org) to keep a
        free-tier host from sleeping the app after ~15 minutes idle.
        Exempt from the login gate (see sindhu_web/security.py's
        _LOGIN_EXEMPT_PATHS) so the pinger needs no credentials.
        Reads two already-computed module-level flags -- no database
        read, no exchange call -- so this stays a near-zero-cost request
        an external service can hit every few minutes.

        cloud_mode/live_candles_only are included deliberately: a real
        deploy once returned "access restricted to the local network" on
        every request with no way to tell, from the outside, whether that
        was because SINDHU_CLOUD_MODE genuinely wasn't set on the host or
        because of some other bug -- this makes that immediately visible
        without needing dashboard access or a redeploy to check. Neither
        value is a secret; they're just which mode the process is in.

        db_backend answers the same kind of question for DATABASE_URL:
        "postgres" means login credentials/sessions and all Paper Trading
        data genuinely survive a restart; "local_file (ephemeral on most
        hosts)" means DATABASE_URL isn't set (or isn't reaching this
        process) and login/trading state will be wiped on the next
        restart/redeploy/sleep-wake cycle -- the exact bug Part 1 fixed
        for the Postgres case. No connection string or credential is ever
        exposed here, only which of the two modes the process picked."""
        from data_engine.resample import LIVE_CANDLES_ONLY
        from sindhu_web.security import CLOUD_MODE
        from data_engine import db_backend
        return {
            "status": "ok",
            "cloud_mode": CLOUD_MODE,
            "live_candles_only": LIVE_CANDLES_ONLY,
            "db_backend": "postgres" if db_backend.IS_POSTGRES else "local_file (ephemeral on most hosts)",
        }

    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/login")
    def login_page(request: Request):
        session_token = request.cookies.get(auth.SESSION_COOKIE)
        if auth.is_valid_session(session_token):
            return RedirectResponse(url="/")
        return FileResponse(os.path.join(_STATIC_DIR, "login.html"))

    @app.get("/")
    def index(request: Request):
        session_token = request.cookies.get(auth.SESSION_COOKIE)
        if not auth.is_valid_session(session_token):
            return RedirectResponse(url="/login")
        index_path = os.path.join(_STATIC_DIR, "index.html")
        with open(index_path, "r", encoding="utf-8") as f:
            html = f.read()
        js_path = os.path.join(_STATIC_DIR, "js", "app.js")
        css_path = os.path.join(_STATIC_DIR, "css", "app.css")
        js_v = int(os.path.getmtime(js_path)) if os.path.exists(js_path) else 0
        css_v = int(os.path.getmtime(css_path)) if os.path.exists(css_path) else 0
        html = html.replace('/static/js/app.js"', f'/static/js/app.js?v={js_v}"')
        html = html.replace('/static/css/app.css"', f'/static/css/app.css?v={css_v}"')
        # app.js's router defaults an empty location.hash to "#home", which
        # calls endpoints this runner never mounts. Landing straight on
        # Paper Trading is the one small, cloud-only HTML tweak needed to
        # avoid that -- done here as a string substitution on the response,
        # NOT as an edit to the shared index.html file, so the local app's
        # own default page is completely untouched.
        html = html.replace(
            "<body>",
            "<body><script>if(!location.hash){location.hash='#paper_trading';}</script>",
            1,
        )
        return HTMLResponse(
            html,
            headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"},
        )

    return app


app = create_app()
