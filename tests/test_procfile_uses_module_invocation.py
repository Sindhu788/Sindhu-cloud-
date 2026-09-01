"""Regression test for a real deploy failure: the Procfile originally
said `uvicorn cloud_runtime.app:app ...` (the bare console-script entry
point), which does NOT add the working directory to sys.path -- only
`python -m uvicorn` does. That gap surfaced as a real Render deploy
crashing with `ModuleNotFoundError: No module named 'data_engine'` at
cloud_runtime/app.py's own import line, reproduced locally before fixing:
bare `uvicorn` exits immediately; `python -m uvicorn` serves normally.

This test does not re-run a real server (that's covered by hand -- see
DEPLOYMENT_CHECKPOINT.md); it just makes sure nobody reintroduces the
bare form into the Procfile or render.yaml without noticing.
"""

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_procfile_invokes_uvicorn_as_a_python_module():
    text = (_REPO_ROOT / "Procfile").read_text(encoding="utf-8")
    assert "python -m uvicorn" in text
    assert not re.search(r"(?<!-m )(?<!python -m )\buvicorn\b(?!\.)", text.replace("python -m uvicorn", "")), (
        "Procfile invokes bare `uvicorn` somewhere -- this fails with "
        "ModuleNotFoundError on Render/Railway; use `python -m uvicorn` instead"
    )


def test_render_yaml_start_command_invokes_uvicorn_as_a_python_module():
    render_yaml = _REPO_ROOT / "render.yaml"
    assert render_yaml.exists(), "render.yaml should exist for Render Blueprint deploys"
    text = render_yaml.read_text(encoding="utf-8")
    match = re.search(r"startCommand:\s*(.+)", text)
    assert match, "render.yaml has no startCommand"
    assert "python -m uvicorn" in match.group(1)
