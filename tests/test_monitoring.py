from datetime import datetime, timezone

from paper_trading import monitoring as m
monitoring = m


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


def _snap(**kw):
    base = dict(stale_rejections_recent=0, engine_enabled=True, engine_running=True, seconds_since_last_scan=30,
                telegram_failures_recent=0, consecutive_failed_scans=0, db_ok=True, just_restarted=False)
    base.update(kw)
    return base


def test_stale_data_alert_needs_n_consecutive_checks_then_recovers_once():
    w = m.Watchdog()
    for _ in range(m.STALE_STREAK_TO_ALERT - 1):
        assert w.check(_snap(stale_rejections_recent=3)) == []
    ev = w.check(_snap(stale_rejections_recent=3))
    assert [e[1] for e in ev] == ["stale_data"] and ev[0][0] == "alert"
    assert w.check(_snap()) == []                                   # one clean check is not enough
    ev = w.check(_snap())
    assert [(e[0], e[1]) for e in ev] == [("recovery", "stale_data")]
    assert w.check(_snap()) == []


def test_scanner_stalled_engine_stopped_db_and_error_spike_conditions():
    w = m.Watchdog()
    codes = lambda ev: {e[1] for e in ev if e[0] == "alert"}
    assert codes(w.check(_snap(engine_running=False))) == {"engine_stopped"}
    assert codes(w.check(_snap(seconds_since_last_scan=m.SCAN_STALL_MIN * 60 + 1))) >= {"scanner_stalled"}
    assert "db_unreachable" in codes(w.check(_snap(db_ok=False)))
    assert "error_spike" in codes(w.check(_snap(consecutive_failed_scans=3)))
    assert "telegram_failures" in codes(w.check(_snap(telegram_failures_recent=3)))
    assert "restarted" in codes(w.check(_snap(just_restarted=True)))


def test_alerts_are_rate_limited_and_recovery_only_follows_a_sent_alert():
    clock, sent = Clock(), []
    lim = m.Limiter(clock=clock)
    send = lambda text: sent.append(text) or True
    ev = [("alert", "db_unreachable", "db down")]
    assert m.deliver(ev, lim, send) == [("db_unreachable", True)]
    assert m.deliver(ev, lim, send) == [("db_unreachable", False)]       # within 60 min: suppressed
    clock.t += 61 * 60
    assert m.deliver(ev, lim, send) == [("db_unreachable", True)]
    assert m.deliver([("recovery", "db_unreachable", "back")], lim, send) == [("db_unreachable", True)]
    assert m.deliver([("recovery", "never_alerted", "x")], lim, send) == [("never_alerted", False)]
    assert len(sent) == 3 and all(s.startswith("[SINDHU monitor]") for s in sent)


def test_failed_send_does_not_start_the_rate_limit_window():
    lim = m.Limiter(clock=Clock())
    assert m.deliver([("alert", "x", "msg")], lim, lambda t: False) == [("x", False)]
    assert m.deliver([("alert", "x", "msg")], lim, lambda t: True) == [("x", True)]


def test_alerts_use_the_private_owner_chat_only_never_the_public_channel(test_db, monkeypatch):
    from paper_trading import telegram_bot
    calls = []
    monkeypatch.setattr(telegram_bot, "_raw_send", lambda text, channel_id_override=None, **k: calls.append(channel_id_override) or (True, None))
    telegram_bot.save_settings(bot_token="1:T", channel_id="PUBLIC", personal_chat_id="OWNER")
    assert m._owner_send("hello") is True and calls == ["OWNER"]
    telegram_bot.save_settings(personal_chat_id="")
    calls.clear()
    assert m._owner_send("hello") is False and calls == []                # no owner chat -> nothing sent anywhere


def test_limiter_state_is_persisted_across_restarts(test_db):
    clock = Clock()
    a = m._persistent_limiter()
    a._clock = clock
    a.mark("stale_data")
    b = m._persistent_limiter()
    b._clock = clock
    assert b.allow("stale_data") is False


def test_daily_summary_text_and_once_per_day(test_db):
    from data_engine import storage
    sent = []
    lim = m.Limiter(clock=Clock())
    now = datetime(2026, 11, 4, 19, 0, tzinfo=timezone.utc)
    assert m.maybe_send_daily_summary(send=lambda t: sent.append(t) or True, limiter=lim, now=now) is True
    assert m.maybe_send_daily_summary(send=lambda t: sent.append(t) or True, limiter=lim, now=now) is False
    assert m.maybe_send_daily_summary(send=lambda t: sent.append(t) or True, limiter=m.Limiter(clock=Clock()),
                                      now=datetime(2026, 11, 4, 9, 0, tzinfo=timezone.utc)) is False   # before 18:00 UTC
    assert len(sent) == 1 and "Daily health" in sent[0] and "signals sent" in sent[0]
    with storage.get_conn() as c:
        assert "scans" in m.build_daily_summary(c)


def test_engine_loop_calls_the_watchdog_and_the_owner_chat_warning_exists():
    import inspect
    from paper_trading import engine, ops_checks
    src = inspect.getsource(engine)
    assert "monitoring.watchdog_tick(self)" in src and "_last_watchdog_at" in src
    assert "no_owner_chat" in inspect.getsource(ops_checks)


# ---------------------------------------------------------------- Day 3: sleep-aware alerts
def _s3(**kw):
    base = dict(db_ok=True, engine_enabled=True, engine_running=True, stale_rejections_recent=0, telegram_failures_recent=0,
                consecutive_failed_scans=0, seconds_since_last_scan=60, seconds_since_activity=60, in_wake_grace=False)
    base.update(kw)
    return base


def test_asleep_then_woke_raises_no_stall_or_stale_alert():
    wd = monitoring.Watchdog()
    for _ in range(8):   # just woke: huge nominal age, empty caches => stale rejections, but inside the wake grace
        ev = wd.check(_s3(in_wake_grace=True, seconds_since_activity=5, seconds_since_last_scan=None, stale_rejections_recent=10))
        assert not [e for e in ev if e[1] in ("scanner_stalled", "stale_data")]
    assert wd.stale_streak == 0


def test_running_but_stalled_alerts_with_pinger_hint():
    wd = monitoring.Watchdog()
    ev = wd.check(_s3(seconds_since_activity=25 * 60, seconds_since_external_ping=None))
    stalled = [e for e in ev if e[1] == "scanner_stalled"]
    assert stalled and "no scan progress for 25 min" in stalled[0][2] and "no external pinger" in stalled[0][2]
    ev = wd.check(_s3(seconds_since_activity=10))
    assert [e for e in ev if e[0] == "recovery" and e[1] == "scanner_stalled"]


def test_slow_but_moving_cold_scan_is_not_stalled():
    wd = monitoring.Watchdog()
    ev = wd.check(_s3(seconds_since_last_scan=40 * 60, seconds_since_activity=30))   # no scan FINISHED for 40 min, but progress 30 s ago
    assert not [e for e in ev if e[1] == "scanner_stalled"]


def test_stale_data_still_alerts_after_grace_and_recovers():
    wd = monitoring.Watchdog()
    codes = []
    for _ in range(monitoring.STALE_STREAK_TO_ALERT):
        codes += [e for e in wd.check(_s3(stale_rejections_recent=4)) if e[1] == "stale_data"]
    assert codes and codes[-1][0] == "alert"
    out = []
    for _ in range(monitoring.RECOVER_STREAK + 1):
        out += wd.check(_s3())
    assert [e for e in out if e[0] == "recovery" and e[1] == "stale_data"]


def test_restart_alert_is_rate_limited_to_six_hours_and_owner_only():
    sent = []
    t = [1000.0]
    lim = monitoring.Limiter(clock=lambda: t[0])
    ev = [("alert", "restarted", "restarted")]
    assert monitoring.deliver(ev, lim, lambda m: sent.append(m) or True) == [("restarted", True)]
    t[0] += 3 * 3600
    assert monitoring.deliver(ev, lim, lambda m: sent.append(m) or True) == [("restarted", False)]
    t[0] += 4 * 3600
    assert monitoring.deliver(ev, lim, lambda m: sent.append(m) or True) == [("restarted", True)]
    assert len(sent) == 2


def test_wake_grace_after_long_gap_between_watchdog_runs(monkeypatch):
    monitoring._last_check_wall, monitoring._grace_until = None, 0.0
    assert monitoring._frozen_recently(1000.0) is False
    assert monitoring._frozen_recently(1060.0) is False
    assert monitoring._frozen_recently(1060.0 + 400) is True      # process was frozen ~400 s
    t = 1460.0
    while t < 1460.0 + 520:                                       # normal 60 s cadence resumes: still inside the 600 s grace
        t += 60
        assert monitoring._frozen_recently(t) is True
    assert monitoring._frozen_recently(1460.0 + 660) is False
