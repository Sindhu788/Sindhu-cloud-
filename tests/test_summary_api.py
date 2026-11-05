"""Master plan A19 (P10): one cached home summary."""
from fastapi.testclient import TestClient


def test_summary_is_cached_and_has_the_home_cards(test_db, monkeypatch):
    from sindhu_web import security, auth
    from sindhu_web.api import summary
    from paper_trading import wallet
    wallet._reset_for_tests()
    monkeypatch.setattr(security, "_is_lan_client", lambda h: True)
    monkeypatch.setattr(auth, "is_valid_session", lambda t: True)
    summary._cache.update(at=0.0, data=None)
    calls = []
    real = summary._compute
    monkeypatch.setattr(summary, "_compute", lambda: calls.append(1) or real())
    import cloud_runtime.app as cloud
    c = TestClient(cloud.app)
    a = c.get("/api/summary").json()
    b = c.get("/api/summary").json()
    assert a["cached"] is False and b["cached"] is True and len(calls) == 1
    assert a["wallet"]["equity"] == 100.0 and "engine" in a and "system" in a and a["paper_only"] is True
    assert c.get("/api/summary?refresh=true").json()["cached"] is False and len(calls) == 2
