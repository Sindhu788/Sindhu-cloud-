from datetime import datetime, timezone

from paper_trading import monitoring as m


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
