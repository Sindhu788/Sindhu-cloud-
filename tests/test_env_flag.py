"""data_engine.config.env_flag() -- the shared boolean-environment-
variable parser used by sindhu_web/security.py's SINDHU_CLOUD_MODE,
data_engine/resample.py's and paper_trading/engine.py's
SINDHU_LIVE_CANDLES.

Why this exists: a real Railway/Render deploy set SINDHU_CLOUD_MODE and
still got "access restricted to the local network" on every request. The
code was reading it with a strict `== "1"` comparison -- any other way of
typing a boolean into a PaaS dashboard (a literal `true`, trailing
whitespace from a copy-paste) left the flag silently off, with nothing in
the app's behavior to reveal that. This is the fix, and these tests pin
down exactly which real-world input shapes it must accept.
"""

import pytest

from data_engine.config import env_flag


@pytest.mark.parametrize("value", ["1", "true", "True", "TRUE", "yes", "Yes", "on", "On", "  1  ", "1\n", " true "])
def test_recognized_truthy_spellings(monkeypatch, value):
    monkeypatch.setenv("SINDHU_TEST_FLAG", value)
    assert env_flag("SINDHU_TEST_FLAG") is True


@pytest.mark.parametrize("value", ["0", "false", "False", "no", "off", "", "   ", "random-garbage"])
def test_recognized_falsy_or_unrecognized_spellings(monkeypatch, value):
    monkeypatch.setenv("SINDHU_TEST_FLAG", value)
    assert env_flag("SINDHU_TEST_FLAG") is False


def test_unset_variable_is_false(monkeypatch):
    monkeypatch.delenv("SINDHU_TEST_FLAG", raising=False)
    assert env_flag("SINDHU_TEST_FLAG") is False


def test_cloud_mode_and_live_candles_both_use_the_shared_parser():
    """Regression guard: both flags must go through the SAME lenient
    parser, not a stray `== "1"` reintroduced in just one of the three
    files that read a flag like this.

    Run in a fresh subprocess rather than reloading these modules
    in-process: paper_trading.engine defines a module-level singleton
    (`engine = PaperTradingEngine()`) at import time, and other modules
    already hold a reference to that exact object -- reloading it here
    would silently create a second, disconnected instance and could
    corrupt state for any test that runs afterward in this same pytest
    session."""
    import json
    import os
    import subprocess
    import sys

    script = (
        "import json\n"
        "from sindhu_web import security\n"
        "from data_engine import resample\n"
        "from paper_trading import engine\n"
        "print(json.dumps({'cloud_mode': security.CLOUD_MODE, "
        "'resample_live': resample.LIVE_CANDLES_ONLY, "
        "'engine_live': engine.LIVE_CANDLES_ONLY}))"
    )
    env = dict(os.environ, SINDHU_CLOUD_MODE="true", SINDHU_LIVE_CANDLES="yes")
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, env=env, timeout=60,
    )
    assert result.returncode == 0, f"subprocess failed:\n{result.stderr}"
    flags = json.loads(result.stdout.strip().splitlines()[-1])
    assert flags == {"cloud_mode": True, "resample_live": True, "engine_live": True}
