"""Master 15-Item task, Item 12: Render free-tier Postgres expiry reminder."""
from sindhu_web.api.settings import _postgres_expiry_notice
from data_engine import db_backend


def test_returns_none_when_not_running_against_postgres(monkeypatch):
    monkeypatch.setattr(db_backend, "IS_POSTGRES", False)
    assert _postgres_expiry_notice({"postgres_free_tier_created_date": "2026-09-05"}) is None


def test_computes_30_day_expiry_and_days_remaining(monkeypatch):
    monkeypatch.setattr(db_backend, "IS_POSTGRES", True)
    result = _postgres_expiry_notice({"postgres_free_tier_created_date": "2026-09-05"})
    assert result["created_date"] == "2026-09-05"
    assert result["expiry_date"] == "2026-10-05"
    assert isinstance(result["days_remaining"], int)
    assert 0 < result["days_remaining"] <= 30


def test_settings_endpoint_includes_postgres_free_tier_field(monkeypatch):
    monkeypatch.setattr(db_backend, "IS_POSTGRES", True)
    from sindhu_web.api.settings import get_settings
    result = get_settings()
    assert "postgres_free_tier" in result
    assert result["postgres_free_tier"]["expiry_date"] == "2026-10-05"
