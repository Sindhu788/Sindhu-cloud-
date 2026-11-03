from datetime import datetime, timedelta, timezone

from data_engine import db_size_guard, storage, db_backend
from paper_trading import scan_telemetry


def test_usage_reports_sqlite_size(test_db):
    u = db_size_guard.database_usage()
    assert u["backend"] == "sqlite" and u["size_bytes"] > 0 and u["error"] is None


def test_warning_logged_when_over_threshold(test_db, monkeypatch):
    monkeypatch.setenv("SINDHU_DB_SIZE_LIMIT_MB", "0.001")
    lines = []
    u = db_size_guard.check_and_warn(lines.append)
    assert u["pct"] >= 80 and any("WARNING database is" in m for m in lines)


def test_no_warning_when_far_below_limit(test_db, monkeypatch):
    monkeypatch.setenv("SINDHU_DB_SIZE_LIMIT_MB", "100000")
    lines = []
    db_size_guard.check_and_warn(lines.append)
    assert lines == []


def _receipt(started):
    return dict(started_at=started, completed_at=started, kind="t", outcome="complete", reason="",
                coins_scanned=1, candidates=0, rejected=0, accepted=0, no_trade=0, errors=0)


def test_prune_removes_only_old_scan_receipts_and_nothing_else(test_db):
    now = datetime.now(timezone.utc)
    with storage.get_conn() as c:
        scan_telemetry.write_receipt(c, _receipt((now - timedelta(days=30)).isoformat()))
        scan_telemetry.write_receipt(c, _receipt(now.isoformat()))
        before_decisions = c.execute("SELECT COUNT(*) FROM paper_decision_log").fetchone()[0]
    deleted = db_size_guard.prune_append_only_logs()
    assert deleted == {"paper_scan_log": 1}
    with storage.get_conn() as c:
        assert c.execute("SELECT COUNT(*) FROM paper_scan_log").fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM paper_decision_log").fetchone()[0] == before_decisions


def test_klines_are_never_written_to_postgres(monkeypatch):
    monkeypatch.setattr(db_backend, "IS_POSTGRES", True)
    called = []
    monkeypatch.setattr(storage, "get_conn", lambda: called.append(1))
    assert storage.insert_klines("binance", "BTCUSDT", [(1, 1, 1, 1, 1, 1, 2, 1, 1)]) == 0
    assert called == []
