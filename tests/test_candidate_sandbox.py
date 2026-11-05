import socket
import threading

import pytest

from data_platform import sandbox


@pytest.fixture
def locked():
    unlock = sandbox.lock_network()
    yield
    unlock()


def test_scrub_removes_credentials_keeps_everything_else_and_reports_names_only():
    env = {"TELEGRAM_BOT_TOKEN": "t0k", "DATABASE_URL": "postgres://u:p@h/db", "CLOUD_SYNC_SECRET": "s", "OKX_API_KEY": "k", "ADMIN_PASSWORD": "p",
           "personal_chat_id": "1", "PATH": "/bin", "SINDHU_DATA_DIR": "x", "HOME": "/h"}
    removed = sandbox.scrub_environment(env)
    assert removed == sorted(["TELEGRAM_BOT_TOKEN", "DATABASE_URL", "CLOUD_SYNC_SECRET", "OKX_API_KEY", "ADMIN_PASSWORD", "personal_chat_id"])
    for k in ("TELEGRAM_BOT_TOKEN", "DATABASE_URL", "CLOUD_SYNC_SECRET", "OKX_API_KEY", "ADMIN_PASSWORD", "personal_chat_id"):
        assert k not in env
    assert env["PATH"] == "/bin" and env["HOME"] == "/h" and env["SINDHU_DATA_DIR"] == "x"
    assert env["SINDHU_SANDBOX"] == "1" and env["SINDHU_CLOUD_SYNC_DISABLED"] == "1"
    assert not any("t0k" in str(v) or "postgres" in str(v) for v in removed)           # values never leak into the report


def test_outgoing_connections_to_the_internet_are_blocked(locked):
    for host, port in (("api.telegram.org", 443), ("sindhu-cloud-1.onrender.com", 443), ("8.8.8.8", 53), ("203.0.113.5", 80)):
        with pytest.raises(sandbox.SandboxNetworkError):
            socket.create_connection((host, port), timeout=1)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with pytest.raises(sandbox.SandboxNetworkError):
                s.connect((host, port))
            with pytest.raises(sandbox.SandboxNetworkError):
                s.connect_ex((host, port))
        finally:
            s.close()
    with pytest.raises(sandbox.SandboxNetworkError):
        socket.getaddrinfo("api.telegram.org", 443)


def test_http_libraries_cannot_send_to_telegram_or_cloud(locked):
    import requests
    with pytest.raises(Exception):
        requests.post("https://api.telegram.org/bot000/sendMessage", data={"chat_id": "1", "text": "x"}, timeout=2)
    with pytest.raises(Exception):
        requests.get("https://sindhu-cloud-1.onrender.com/health", timeout=2)


def test_loopback_still_works_and_unlock_restores(locked):
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1); port = srv.getsockname()[1]
    t = threading.Thread(target=lambda: srv.accept()[0].close(), daemon=True); t.start()
    c = socket.create_connection(("127.0.0.1", port), timeout=2); c.close(); srv.close()


def test_unlock_restores_normal_behaviour():
    orig = socket.create_connection
    unlock = sandbox.lock_network()
    assert socket.create_connection is not orig
    unlock()
    assert socket.create_connection is orig


def test_candidate_tool_entry_point_installs_scrub_and_lock_before_doing_anything(tmp_path):
    """Run the real entry point in a fresh process with a fake token in the environment; it fails on the missing library AFTER installing the sandbox."""
    import os
    import subprocess
    import sys
    code = (
        "import os, socket, sys\n"
        "from data_platform import candidate_eval\n"
        "try:\n"
        "    candidate_eval.main(['--library-dir', r'%s', '--strategy-id', 'nope', '--out-root', r'%s'])\n"
        "except Exception:\n"
        "    pass\n"
        "blocked = False\n"
        "try:\n"
        "    socket.create_connection(('api.telegram.org', 443), timeout=1)\n"
        "except OSError as e:\n"
        "    blocked = type(e).__name__ == 'SandboxNetworkError'\n"
        "print('token_gone=%%s blocked=%%s sandbox=%%s' %% ('TELEGRAM_BOT_TOKEN' not in os.environ, blocked, os.environ.get('SINDHU_SANDBOX')))\n"
    ) % (str(tmp_path / "lib"), str(tmp_path / "out"))
    env = dict(os.environ, TELEGRAM_BOT_TOKEN="fake-token-for-test", PYTHONPATH=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60,
                       cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert "token_gone=True blocked=True sandbox=1" in r.stdout, r.stdout + r.stderr


def test_dossier_is_built_from_results_and_marks_missing_claim(tmp_path):
    from data_platform import candidate_eval
    res = {"trades": 1200, "coins_run": 50, "pf_x1": 0.9, "pf_x1_5": 0.8, "pf_x2": 0.7, "pf_gross": 1.0, "win_rate": 40.0, "label": "FAILED", "reason": "pooled PF 0.90 after costs"}
    rig = {"pf_ci": [0.8, 1.0], "obs_mean_net_pct": -0.1, "null_mean_pct": -0.09, "null_p": 0.4, "sma4h_mean_net_pct": -0.2, "rsi1h_mean_net_pct": -0.3}
    candidate_eval.build_dossier(str(tmp_path), "abc", "", res, rig, "FAILED", {"name": "Test", "entry_tf": "15m", "timeframes": {"entry": "15m"}, "risk_pct": 1}, ["X"], 1.5)
    text = (tmp_path / "DOSSIER.md").read_text(encoding="utf-8")
    assert "NOT FILLED" in text and "**Label: FAILED.**" in text and "Do not promote" in text and "1 environment variables" in text
    assert "ROBUST" not in text.split("## 3")[0].replace("**Label: FAILED.**", "")
