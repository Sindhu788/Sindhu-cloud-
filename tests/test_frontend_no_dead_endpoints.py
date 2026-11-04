"""The dashboard must not call endpoints that were removed with the Codex cleanup (they produced 404 console errors
on the Paper Trading and Strategy Lab pages), and must load the owner warnings banner."""
import os
import re

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sindhu_web", "static")


def _api_paths_called_by_frontend():
    text = open(os.path.join(STATIC, "js", "app.js"), encoding="utf-8").read()
    return set(re.findall(r'(?:apiGet|apiPost|fetch)\(\s*[`"\'](/api/[a-z0-9_\-/]+)', text))


def test_frontend_does_not_call_removed_endpoints():
    called = _api_paths_called_by_frontend()
    removed = [p for p in called if p.startswith(("/api/intelligence", "/api/quality", "/api/paper-trading/catalog"))]
    assert removed == []


def test_index_loads_the_warnings_banner_and_it_exists():
    html = open(os.path.join(STATIC, "index.html"), encoding="utf-8").read()
    assert "/static/js/ops_banner.js" in html
    assert os.path.exists(os.path.join(STATIC, "js", "ops_banner.js"))
