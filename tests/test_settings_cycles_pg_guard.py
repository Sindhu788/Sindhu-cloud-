"""Master plan V2 R7: the Postgres settings test never runs against production and is BLOCKED without TEST_DATABASE_URL."""
import importlib.util
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("settings_cycles", os.path.join(ROOT, "tools", "settings_cycles.py"))
sc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sc)


def test_missing_test_url_is_blocked(monkeypatch):
    monkeypatch.setattr(sc, "_dotenv", lambda name: "")
    with pytest.raises(SystemExit) as e:
        sc.safe_test_url()
    assert "BLOCKED" in str(e.value)


def test_production_url_is_refused(monkeypatch):
    prod = "postgresql://u:p@ep-prod-123.us-east-2.aws.neon.tech/neondb?sslmode=require"
    monkeypatch.setattr(sc, "_dotenv", lambda name: prod.replace("u:p", "other:x") if name == "TEST_DATABASE_URL" else prod)
    with pytest.raises(SystemExit) as e:
        sc.safe_test_url()
    assert "REFUSED" in str(e.value)


def test_a_branch_url_is_accepted(monkeypatch):
    prod = "postgresql://u:p@ep-prod-123.us-east-2.aws.neon.tech/neondb"
    branch = "postgresql://u:p@ep-branch-456.us-east-2.aws.neon.tech/neondb"
    monkeypatch.setattr(sc, "_dotenv", lambda name: branch if name == "TEST_DATABASE_URL" else prod)
    assert sc.safe_test_url() == branch
