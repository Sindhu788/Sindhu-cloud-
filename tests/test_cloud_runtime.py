"""cloud_runtime/app.py -- the lightweight, cloud-deployable FastAPI app.

Covers what unit tests can prove about app assembly without spinning up a
real server: which routers/routes exist, that heavy local-only subsystems
are never imported by pulling this module in, and that the cloud-only nav
never advertises a page this runner cannot actually serve. The full
request/response cycle (login flow, session gate, a real engine tick
against a live exchange with zero local data present) was verified by
hand against a real running instance -- see DEPLOYMENT_CHECKPOINT.md Step
2g for that record; it is not repeated here since it makes real network
calls and takes ~30s.
"""

import subprocess
import sys
import textwrap

import pytest


@pytest.fixture(scope="module")
def cloud_app():
    import cloud_runtime.app as mod
    return mod


@pytest.fixture(scope="module")
def isolated_import_graph():
    """The real 'what does importing cloud_runtime.app pull in' question
    can only be answered in a FRESH process: this test file runs inside
    pytest's single shared process alongside every other test file, and
    plenty of THOSE legitimately import evolution_engine.engine, home.py,
    etc. for their own purposes -- checking sys.modules in-process would
    just be reading contamination from unrelated tests, not a real
    property of cloud_runtime.app itself. Spawns a clean `python -c`
    subprocess that imports ONLY cloud_runtime.app and reports its own
    sys.modules -- the same technique used to verify this by hand while
    building the module (see DEPLOYMENT_CHECKPOINT.md Step 2e)."""
    script = textwrap.dedent("""
        import sys, json
        before = set(sys.modules)
        import cloud_runtime.app
        after = set(sys.modules)
        print(json.dumps(sorted(after - before)))
    """)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, cwd=None, timeout=60,
    )
    assert result.returncode == 0, f"subprocess import failed:\n{result.stderr}"
    import json
    return set(json.loads(result.stdout.strip().splitlines()[-1]))


def test_importing_cloud_runtime_never_imports_the_batch_backtest_runner(isolated_import_graph):
    """The actual batch/backtest RUNNER (as opposed to the strategy config
    loader and shared trade-mechanics code, which cloud_runtime.app's own
    module docstring explains are required) must never be pulled in."""
    forbidden = [
        "backtest_engine.runner",
        "backtest_engine.mtf_worker",
        "backtest_engine.optimizer",
        "backtest_engine.verification_engine",
        "automation_pipeline",
        "ai_integration.deep_understanding",
        "ai_integration.multi_pass_extraction",
        "ai_integration.sentence_level_extraction",
    ]
    hits = [m for m in isolated_import_graph for f in forbidden if m == f or m.startswith(f + ".")]
    assert hits == [], f"cloud_runtime.app pulled in forbidden heavy module(s): {sorted(set(hits))}"


def test_importing_cloud_runtime_never_imports_the_evolution_governor(isolated_import_graph):
    """evolution_engine.lesson_generator/generation_manager are
    deliberately imported (see module docstring); the actual Governor/
    tick-loop (evolution_engine.engine/governor) must never be."""
    assert "evolution_engine.engine" not in isolated_import_graph
    assert "evolution_engine.governor" not in isolated_import_graph


def test_importing_cloud_runtime_never_imports_the_heavy_home_endpoint(isolated_import_graph):
    """The cosmetic topbar stub inside cloud_runtime.app must be its own
    tiny function, not an accidental import of sindhu_web.api.home (which
    pulls in backtest_engine.reports and knowledge_engine)."""
    assert "sindhu_web.api.home" not in isolated_import_graph


def test_cloud_nav_only_lists_pages_this_runner_actually_mounts(cloud_app):
    """Every page id the cloud nav advertises must correspond to a route
    this runner really serves -- a stale nav entry would put a dead link
    in the cloud sidebar with no way to notice except a user clicking it."""
    page_ids = {p["id"] for p in cloud_app._CLOUD_NAV_PAGES}
    assert page_ids == {"paper_trading", "telegram_dashboard", "strategy_overview", "signal_tracker", "challenge_mode"}
    for group in (p["group"] for p in cloud_app._CLOUD_NAV_PAGES):
        assert group in cloud_app._CLOUD_NAV_GROUPS


def _all_route_paths(app):
    """FastAPI's newer versions keep an app.include_router(...) call as a
    lazy `_IncludedRouter` wrapper (its routes only resolve at actual
    request-dispatch time) rather than eagerly flattening it into
    app.routes -- confirmed by reading its `original_router` attribute,
    which holds the real APIRouter with its own populated `.routes`."""
    paths = set()
    for r in app.routes:
        if hasattr(r, "path"):
            paths.add(r.path)
        elif type(r).__name__ == "_IncludedRouter":
            paths.update(rr.path for rr in r.original_router.routes if hasattr(rr, "path"))
    return paths


def test_app_mounts_exactly_the_expected_routers(cloud_app):
    route_paths = _all_route_paths(cloud_app.app)
    # A representative sample from each intentionally-mounted router.
    assert "/api/paper-trading/status" in route_paths
    assert "/api/paper-trading/strategy-overview" in route_paths
    assert "/api/paper-trading/signal-tracker/feed" in route_paths
    assert "/api/paper-trading/signal-tracker/match-table" in route_paths
    assert "/api/paper-trading/cloud-sync/status" in route_paths
    assert "/api/paper-trading/cloud-sync/download" in route_paths
    assert "/api/auth/login" in route_paths
    assert "/ws/logs" in route_paths
    # A page this runner does NOT serve must not have leaked in via some
    # other import path.
    assert "/api/backtesting/run" not in route_paths
    assert "/api/evolution/status" not in route_paths


def test_get_home_stub_returns_a_minimal_shape(cloud_app):
    result = cloud_app.app.routes
    stub_route = next(r for r in result if getattr(r, "path", None) == "/api/home")
    body = stub_route.endpoint()
    assert body == {"version": cloud_app.APP_VERSION, "system_health": "OK"}


def test_health_endpoint_exists_and_is_trivial(cloud_app):
    """The uptime-pinger endpoint (cron-job.org et al.) must stay a
    near-zero-cost request -- no database read, no exchange call -- while
    still surfacing the two flags most likely to explain "why can't I
    reach the dashboard" (see the endpoint's own docstring for the real
    incident that motivated exposing these)."""
    route = next(r for r in cloud_app.app.routes if getattr(r, "path", None) == "/health")
    body = route.endpoint()
    assert body["status"] == "ok"
    assert set(body) == {"status", "cloud_mode", "live_candles_only", "db_backend"}
    assert isinstance(body["cloud_mode"], bool)
    assert isinstance(body["live_candles_only"], bool)
    assert body["db_backend"] in ("postgres", "local_file (ephemeral on most hosts)")


def test_health_endpoint_reports_db_backend_honestly(cloud_app, monkeypatch):
    """DATABASE_URL being unset (or not reaching the process) is exactly
    the misconfiguration Part 1's persistence fix depends on someone being
    able to notice from outside -- /health must reflect the REAL live
    db_backend.IS_POSTGRES flag, not a cached/assumed value, in both
    directions."""
    from data_engine import db_backend
    route = next(r for r in cloud_app.app.routes if getattr(r, "path", None) == "/health")

    monkeypatch.setattr(db_backend, "IS_POSTGRES", False)
    assert route.endpoint()["db_backend"] == "local_file (ephemeral on most hosts)"

    monkeypatch.setattr(db_backend, "IS_POSTGRES", True)
    assert route.endpoint()["db_backend"] == "postgres"


def test_health_endpoint_is_exempt_from_the_login_gate():
    """An external pinger has no session cookie and must not be asked for
    one -- otherwise the very thing meant to keep the free tier awake
    would itself get a 401 every time."""
    from sindhu_web.security import _LOGIN_EXEMPT_PATHS
    assert "/health" in _LOGIN_EXEMPT_PATHS


def test_health_endpoint_survives_the_lan_check_even_when_misconfigured():
    """A real deploy had SINDHU_CLOUD_MODE evaluating False (the env var
    was never actually set on the host) and /health returned the SAME
    "access restricted to the local network" 403 as every other path --
    a chicken-and-egg dead end, since /health is the one endpoint meant to
    let the CEO diagnose exactly that misconfiguration. /health must now
    bypass the LAN check unconditionally, BEFORE CLOUD_MODE is even
    consulted -- verified here with CLOUD_MODE forced off and a real
    non-LAN client IP, the exact combination that reproduced the bug."""
    import asyncio

    from fastapi import Request
    from sindhu_web import security

    async def _run():
        scope = {
            "type": "http", "method": "GET", "path": "/health",
            "headers": [], "query_string": b"", "client": ("8.8.8.8", 12345),
        }
        request = Request(scope)

        async def call_next(_req):
            return "reached the real handler"

        return await security.token_guard_middleware(request, call_next)

    original_cloud_mode = security.CLOUD_MODE
    security.CLOUD_MODE = False
    try:
        result = asyncio.run(_run())
    finally:
        security.CLOUD_MODE = original_cloud_mode
    assert result == "reached the real handler"


def test_index_html_response_defaults_to_paper_trading_not_home(cloud_app, tmp_path, monkeypatch):
    """A logged-in visitor with no hash in the URL must land on Paper
    Trading, not app.js's own default of #home (which calls endpoints
    this runner never mounts)."""
    import os
    from sindhu_web import auth

    monkeypatch.setattr(auth, "is_valid_session", lambda token: True)
    index_path = os.path.join(cloud_app._STATIC_DIR, "index.html")
    with open(index_path, encoding="utf-8") as f:
        raw_html = f.read()
    assert "<body>" in raw_html  # sanity: the substitution target really exists

    index_route = next(r for r in cloud_app.app.routes if getattr(r, "path", None) == "/")
    from starlette.requests import Request as StarletteRequest

    class _FakeRequest:
        cookies = {}

    response = index_route.endpoint(_FakeRequest())
    assert b"location.hash='#paper_trading'" in response.body
