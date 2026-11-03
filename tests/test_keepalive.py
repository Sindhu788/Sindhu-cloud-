from cloud_runtime import keepalive


def test_keepalive_is_off_unless_url_configured(monkeypatch):
    monkeypatch.delenv("SINDHU_KEEPALIVE_URL", raising=False)
    monkeypatch.setattr(keepalive, "_started", False)
    assert keepalive.start_if_configured(lambda m: None) is False


def test_keepalive_starts_once_when_configured(monkeypatch):
    monkeypatch.setenv("SINDHU_KEEPALIVE_URL", "https://example.invalid")
    monkeypatch.setattr(keepalive, "_started", False)
    lines = []
    assert keepalive.start_if_configured(lines.append) is True
    assert keepalive.start_if_configured(lines.append) is False
    assert any("keep-alive enabled" in m for m in lines)
