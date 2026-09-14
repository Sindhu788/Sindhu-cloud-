"""2026-09-14 fix: renderPaperTrading()'s "Self-Learning Progress by
Strategy" section used a bare `en` identifier that was never declared in
that closure (a different sibling closure elsewhere in the same outer
function happened to declare its own local `en` for an unrelated purpose --
that's exactly why a same-function-body text/regex scan can't reliably
tell the two apart). This threw "ReferenceError: en is not defined" the
instant that section rendered, caught by route()'s try/catch and shown to
the user as "Failed to load page" on the Paper Trading tab.

Actually EXECUTING app.js with a real JS engine is the only fully reliable
way to catch a bug like this, so this test shells out to the Node.js
harness at tests/frontend_harness/check_pages_render.mjs, which loads the
real app.js in a sandboxed vm context (with just enough document/window/
localStorage/fetch stubs to run), calls every top-level page in PAGES with
a mocked fetch, and reports which ones throw. Confirmed live (see the fix
commit) that this harness both catches the original bug when reverted and
passes cleanly on the fix.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HARNESS = _REPO_ROOT / "tests" / "frontend_harness" / "check_pages_render.mjs"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed in this environment")
def test_every_dashboard_page_renders_without_throwing():
    result = subprocess.run(
        ["node", str(_HARNESS)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    try:
        output = json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        pytest.fail(f"harness produced no parseable output.\nstdout: {result.stdout}\nstderr: {result.stderr}")

    if output.get("fatal"):
        pytest.fail(f"harness failed to load app.js at all: {output['fatal']}\n{output.get('stack', '')}")

    failing = {pid: r for pid, r in output.get("pages", {}).items() if not r.get("ok")}
    assert not failing, (
        "these dashboard pages throw when rendered (would show \"Failed to "
        "load page\" to the user): "
        + "; ".join(f"{pid}: {r.get('error')}" for pid, r in failing.items())
    )
