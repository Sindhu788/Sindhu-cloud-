"""Master plan A17 (P38 + P39): config validation refuses NEW entries only; /health/details is public and has no secrets."""
import json

import pytest
from fastapi.testclient import TestClient

from paper_trading import self_check


@pytest.fixture(autouse=True)
def fresh():
    self_check._state.update({"config_checked_at": 0.0, "config_errors": {}, "self_check": None})
    yield
    self_check._state.update({"config_checked_at": 0.0, "config_errors": {}, "self_check": None})


def test_valid_defaults_have_no_errors(test_db):
    assert self_check.validate_config() == {}
    assert self_check.trading_state() == "enabled"


def test_invalid_setting_disables_trading(test_db, monkeypatch):
    from paper_trading import config as pt_config
    real = pt_config.load
    monkeypatch.setattr(pt_config, "load", lambda: {**real(), "risk_pct_default": 500.0})
    errs = self_check.validate_config()
    assert "risk_pct_default" in errs
    self_check._state["config_checked_at"] = 0
    assert self_check.trading_state() == "disabled_config_error"


def test_wallet_limits_are_validated(test_db, monkeypatch):
    from paper_trading import wallet
    monkeypatch.setattr(wallet, "settings", lambda: {**wallet.DEFAULTS, "risk_per_trade_pct": 5.0})
    assert "wallet.risk_per_trade_pct" in self_check.validate_config()


def test_engine_refuses_new_entries_on_config_error_but_keeps_running(test_db):
    from paper_trading.engine import PaperTradingEngine
    eng = PaperTradingEngine.__new__(PaperTradingEngine)
    eng._config_block = {"risk_pct_default": "bad"}
    logged = []
    eng._log_decision = lambda *a, **k: logged.append(a)
    assert eng._process_coin("okx", "BTC/USDT", {}, {}) == (0, 1)
    assert "config error" in logged[0][4]


def test_offline_self_check_and_details_have_no_secrets(test_db, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:SECRET-TOKEN-VALUE")
    monkeypatch.setenv("DATABASE_URL_FAKE", "postgresql://user:pw@host/db")
    res = self_check.run_self_check(network=False)
    assert res["ok"] and {c["name"] for c in res["checks"]} == {"database", "data_folder"}
    d = self_check.details()
    blob = json.dumps(d, default=str)
    assert "SECRET-TOKEN-VALUE" not in blob and "pw@host" not in blob
    assert len(d["config_hash"]) == 16 and d["trading"] == "enabled"


def test_health_details_is_public(test_db, monkeypatch):
    from sindhu_web import auth
    monkeypatch.setattr(auth, "is_valid_session", lambda t: (_ for _ in ()).throw(AssertionError("no session lookup")))
    import cloud_runtime.app as cloud
    r = TestClient(cloud.app).get("/health/details")
    assert r.status_code == 200 and r.json()["status"] == "ok" and "config_hash" in r.json()
