"""Master plan A21 (P9): the 50-cycle settings test (fixed seed) through the real API; the fresh-process restart part runs in
tools/settings_cycles.py (report: docs/SETTINGS_TEST_REPORT.md)."""
import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))


def test_fifty_cycles_valid_saved_invalid_rejected_old_value_kept(test_db, monkeypatch, tmp_path):
    import settings_cycles
    from data_engine import config as base_config
    from sindhu_web import security, auth
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(security, "_is_lan_client", lambda h: True)
    monkeypatch.setattr(auth, "is_valid_session", lambda t: True)
    monkeypatch.setattr(security, "get_or_create_token", lambda: "t")
    import cloud_runtime.app as cloud
    rows = settings_cycles.run(50, 20261105, TestClient(cloud.app, headers={"X-Sindhu-Token": "t"}), data_dir=None)
    failed = {f: r["notes"] for f, r in rows.items() if r["fail"]}
    assert not failed, failed
    assert sum(r["cycles"] for r in rows.values()) == 50
