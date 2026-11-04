from data_engine import storage
from paper_trading import scan_telemetry as st


def _count(c, sql="SELECT COUNT(*) FROM paper_scan_log"):
    try:
        return c.execute(sql).fetchone()[0]
    except Exception:
        return 0


def test_unfinished_scan_becomes_interrupted_receipt_once(test_db):
    with storage.get_conn() as c:
        assert st.beat(c, "s1", "scheduled_or_manual_tick", "2026-11-04T08:00:00+00:00", "coins", idx=3, total=10, symbol="ETH/USDT", coins_scanned=3, force=True)
    with storage.get_conn() as c:
        r = st.recover_interrupted(c)
        assert r and r["outcome"] == "interrupted" and "coin 3/10 ETH/USDT" in r["reason"] and r["coins_scanned"] == 3
        assert _count(c) == 1
        assert st.recover_interrupted(c) is None      # idempotent: already marked idle
        assert _count(c) == 1


def test_finished_scan_leaves_no_interrupted_receipt(test_db):
    with storage.get_conn() as c:
        st.beat(c, "s1", "k", "2026-11-04T08:00:00+00:00", "coins", force=True)
        c.execute("UPDATE paper_scan_heartbeat SET phase='idle' WHERE id='current'")
    with storage.get_conn() as c:
        assert st.recover_interrupted(c) is None and _count(c) == 0


def test_beat_is_throttled_within_same_phase(test_db):
    st._last_beat.update(t=0.0, phase=None)
    with storage.get_conn() as c:
        assert st.beat(c, "s1", "k", "t", "coins", idx=1, force=True)
        assert not st.beat(c, "s1", "k", "t", "coins", idx=2)          # same phase, < 5 s
        assert st.beat(c, "s1", "k", "t", "finishing")                 # phase change always written
        assert c.execute("SELECT COUNT(*) FROM paper_scan_heartbeat").fetchone()[0] == 1


def test_recovery_with_no_table_or_no_row_is_silent(test_db):
    with storage.get_conn() as c:
        assert st.recover_interrupted(c) is None


def test_engine_scan_writes_receipt_and_goes_idle(test_db, monkeypatch):
    from paper_trading.engine import PaperTradingEngine
    monkeypatch.delenv("SINDHU_SAFE_START", raising=False)
    e = PaperTradingEngine()
    e._run_scan("manual", lambda: None)
    with storage.get_conn() as c:
        assert _count(c) == 1
        assert c.execute("SELECT phase FROM paper_scan_heartbeat WHERE id='current'").fetchone()[0] == "idle"
    e._recover_interrupted_scan()           # nothing to recover after a clean scan
    with storage.get_conn() as c:
        assert _count(c) == 1


def test_housekeeping_never_raises_and_records_time(test_db, monkeypatch):
    from paper_trading.engine import PaperTradingEngine
    e = PaperTradingEngine()
    monkeypatch.setattr(e, "_housekeeping_impl", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    e._housekeeping()
    assert e._last_housekeeping_at is not None


def test_light_housekeeping_skips_the_slow_hourly_jobs_but_full_runs_them(test_db, monkeypatch):
    from paper_trading import engine as eng
    seen = []
    monkeypatch.setattr(eng.signal_tracker, "check_and_alert_divergence", lambda: seen.append("divergence") or [])
    monkeypatch.setattr(eng.insights, "sweep_win_rate_decay_alerts", lambda: seen.append("decay") or [])
    monkeypatch.setattr(eng.custom_alerts, "sweep_custom_alert_rules", lambda: seen.append("custom") or [])
    monkeypatch.setattr(eng.telegram_bot, "sweep_unsent_qualifying_signals", lambda: seen.append("sweep") or [])
    monkeypatch.setattr(eng.telegram_bot, "sweep_pending_telegram_retries", lambda: seen.append("retry") or {"delivered": 0, "abandoned": 0})
    e = eng.PaperTradingEngine()
    e._housekeeping(light=True)
    assert "sweep" in seen and not {"divergence", "decay", "custom"} & set(seen)
    e._housekeeping()
    assert {"divergence", "decay", "custom"} <= set(seen)


def test_stall_reporter_logs_where_a_stuck_scan_is_waiting(test_db):
    import threading, time
    from paper_trading import engine as eng
    e = eng.PaperTradingEngine()
    logs = []
    e._log = logs.append
    release = threading.Event()

    def stuck_function():
        release.wait(5)               # the "hung network call"

    e._current_scan = {"kind": "k", "started_at": "t", "coins_scanned": 0, "errors": 0}
    e._scan_activity_ts = time.time() - 1000
    t = threading.Thread(target=stuck_function, daemon=True); t.start()
    r = threading.Thread(target=e._stall_reporter, args=(t,), kwargs=dict(check_every=0.05, stall_after=1, repeat_after=60), daemon=True)
    r.start(); time.sleep(0.4); release.set(); t.join(); r.join(2)
    assert len(logs) == 1 and "no progress" in logs[0] and "stuck_function" in logs[0]


def test_housekeeper_runs_on_its_own_thread_every_interval_without_overlapping(test_db, monkeypatch):
    import threading, time
    from paper_trading import engine as eng
    e = eng.PaperTradingEngine()
    calls, active, overlap = [], [0], [False]

    def fake(light=False):
        with e._hk_lock:
            active[0] += 1
            overlap[0] = overlap[0] or active[0] > 1
            calls.append(light)
            time.sleep(0.12)                                   # slower than the interval: the loop must skip, not pile up
            active[0] -= 1

    monkeypatch.setattr(e, "_housekeeping", fake)
    alive = threading.Event()
    t = threading.Thread(target=alive.wait, daemon=True); t.start()          # stands for the engine thread
    h = threading.Thread(target=e._housekeeper_loop, args=(t,), kwargs=dict(every=0.05), daemon=True); h.start()
    time.sleep(0.6)
    e._stop_flag.set(); alive.set(); h.join(2)
    assert 2 <= len(calls) <= 6 and all(c is True for c in calls) and not overlap[0]
    assert not h.is_alive()


def test_the_coin_loop_no_longer_runs_housekeeping_itself():
    import pathlib
    from paper_trading import engine as eng
    src = pathlib.Path(eng.__file__).read_text(encoding="utf-8")
    loop = src[src.index("for entry in shortlist:"):src.index("self._beat('finishing'")]
    assert "_housekeeping(" not in loop
