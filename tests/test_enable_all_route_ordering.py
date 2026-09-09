"""Regression guard for a real production incident (2026-09-09): the
POST /api/paper-trading/strategy-config/enable-all route was registered
AFTER POST /api/paper-trading/strategy-config/{strategy_id} in this file,
and FastAPI/Starlette matches routes in registration order -- a single
path-segment parameter matches the literal string "enable-all" just fine,
so every real click on "Enable All for Paper Trading" was silently
routed to update_strategy_config(strategy_id="enable-all") instead of
enable_all_for_paper_trading(). That handler happily wrote a bogus
paper_strategy_config row for the fake strategy_id "enable-all", returned
{"ok": True} (a 200, indistinguishable from success), and never enabled a
single real strategy or ran the group sync.

The existing tests in test_enable_all_for_paper_trading.py call
pt_api.enable_all_for_paper_trading() directly as a plain function, which
exercises the handler's logic perfectly but can never catch a routing
mistake like this -- only asking the actual router to resolve the path
can. This environment has no httpx installed (see
test_clarification_page.py's docstring), so this drives Starlette's own
route-matching directly instead of a full TestClient.
"""
from starlette.routing import Match

from sindhu_web.api import paper_trading as pt_api


def _resolve(method, path):
    """Mirrors Starlette's own Router.app dispatch: first route in
    registration order whose .matches() call reports a full match wins."""
    scope = {"type": "http", "method": method, "path": path}
    for route in pt_api.router.routes:
        match, _ = route.matches(scope)
        if match == Match.FULL:
            return route
    return None


def test_enable_all_post_resolves_to_the_dedicated_handler():
    route = _resolve("POST", "/api/paper-trading/strategy-config/enable-all")
    assert route is not None, "no route matched -- enable-all endpoint is unreachable"
    assert route.endpoint is pt_api.enable_all_for_paper_trading, (
        f"POST .../strategy-config/enable-all resolved to {route.endpoint.__name__!r} "
        "instead of enable_all_for_paper_trading -- the {strategy_id} route is "
        "shadowing it again (must stay registered AFTER enable-all)"
    )


def test_single_strategy_post_still_resolves_to_the_per_strategy_handler():
    """Guards the other direction too -- fixing the shadowing must not
    accidentally break normal per-strategy enable/disable."""
    route = _resolve("POST", "/api/paper-trading/strategy-config/some-real-strategy-id")
    assert route is not None
    assert route.endpoint is pt_api.update_strategy_config


def test_enable_all_get_route_does_not_exist():
    """Only POST is defined for enable-all -- a GET must fall through to
    the {strategy_id} GET route (treating "enable-all" as a strategy id),
    not silently 404 or hit the wrong handler."""
    route = _resolve("GET", "/api/paper-trading/strategy-config/enable-all")
    assert route is not None
    assert route.endpoint is pt_api.get_strategy_config
