from paper_trading import instance_state as ist


def _reset():
    ist._pings.clear()


def test_pinger_detected_only_with_regular_external_pings():
    _reset()
    assert ist.ping_summary(1000.0)["pinger_active"] is False
    for i in range(5):
        ist.note_health_ping("cron-job.org", now=1000.0 + 60 * i)
    s = ist.ping_summary(1000.0 + 60 * 4 + 30)
    assert s["pinger_active"] and s["external_pings_seen"] == 5 and s["average_gap_seconds"] == 60.0
    assert ist.ping_summary(1000.0 + 3 * 3600)["pinger_active"] is False     # pings stopped long ago


def test_render_own_probe_does_not_count_as_a_pinger():
    _reset()
    for i in range(6):
        ist.note_health_ping("Render/1.0", now=2000.0 + 30 * i)
    s = ist.ping_summary(2000.0 + 200)
    assert s["pinger_active"] is False and s["external_pings_seen"] == 0 and s["seconds_since_last_render_probe"] is not None


def test_health_endpoint_records_ping_without_db(test_db):
    from fastapi.testclient import TestClient
    import cloud_runtime.app as cloud
    _reset()
    c = TestClient(cloud.app)
    assert c.get("/health", headers={"user-agent": "UptimeRobot/2.0"}).status_code == 200
    assert ist.ping_summary()["external_pings_seen"] == 1


def test_wake_grace_window():
    assert ist.in_wake_grace(ist.PROCESS_STARTED_AT + 60) is True
    assert ist.in_wake_grace(ist.PROCESS_STARTED_AT + ist.WAKE_GRACE_SECONDS + 1) is False
