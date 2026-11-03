"""Public-signal delivery guard (SINDHU_PUBLIC_SIGNAL_OWNER) and 60 s missed-signal sweep."""


def test_main_cloud_public_sender_ownership_and_private_notifications():
    from paper_trading.signal_ownership import public_delivery_allowed
    settings={'channel_id':'public','personal_chat_id':'private'}
    assert not public_delivery_allowed(settings,'public',environ={})
    assert public_delivery_allowed(settings,'public',environ={'SINDHU_CLOUD_MODE':'1'})
    assert public_delivery_allowed(settings,'private',environ={})
    assert not public_delivery_allowed(settings,'strategy-channel',environ={})
    assert not public_delivery_allowed(settings,'public',environ={'SINDHU_PUBLIC_SIGNAL_OWNER':'invalid'})
    assert not public_delivery_allowed(settings,'public',environ={'SINDHU_PUBLIC_SIGNAL_OWNER':'main','SINDHU_CLOUD_MODE':'1'})


def test_non_owner_sender_returns_before_any_network_call(monkeypatch):
    from paper_trading import telegram_bot
    monkeypatch.delenv('SINDHU_TELEGRAM_DRY_RUN',raising=False)
    monkeypatch.delenv('SINDHU_CLOUD_MODE',raising=False)
    monkeypatch.delenv('SINDHU_PUBLIC_SIGNAL_OWNER',raising=False)
    monkeypatch.setattr(telegram_bot,'load_settings',lambda:{'channel_id':'public'})
    monkeypatch.setattr(telegram_bot.requests,'post',lambda *a,**k:pytest.fail('Unexpected network call'))
    ok,error=telegram_bot._raw_send('Synthetic QA message')
    assert not ok and 'publisher' in error


def test_public_delivery_decision_explains_why_a_signal_is_withheld():
    from paper_trading.signal_ownership import public_delivery_decision
    settings = {'channel_id': 'public'}
    ok, why = public_delivery_decision(settings, 'public', environ={'SINDHU_CLOUD_MODE': '1'})
    assert ok and why == ''
    ok, why = public_delivery_decision(settings, 'public', environ={})
    assert not ok and 'SINDHU_PUBLIC_SIGNAL_OWNER' in why and "role 'main'" in why
    ok, why = public_delivery_decision(settings, 'public', environ={'SINDHU_PUBLIC_SIGNAL_OWNER': 'any'})
    assert ok
    ok, why = public_delivery_decision(settings, 'public', environ={'SINDHU_PUBLIC_SIGNAL_OWNER': 'bogus'})
    assert not ok and 'fail closed' in why


def test_withheld_signal_is_logged_not_silent(monkeypatch):
    from paper_trading import telegram_bot
    from data_engine import logging_setup
    lines = []
    monkeypatch.setattr(logging_setup, 'log', lambda m: lines.append(m))
    telegram_bot._WITHHELD_LOG.update(reason=None, at=0.0)
    monkeypatch.setenv('SINDHU_PUBLIC_SIGNAL_OWNER', 'cloud')
    monkeypatch.delenv('SINDHU_CLOUD_MODE', raising=False)
    monkeypatch.setattr(telegram_bot, 'load_settings', lambda: {'bot_token': 'x', 'channel_id': 'public'})
    ok, msg = telegram_bot._raw_send('hello')
    assert ok is False and 'Public delivery blocked' in msg
    assert any('signal NOT sent' in m for m in lines)


def test_disabled_owner_withholds_everywhere_with_a_clear_reason():
    from paper_trading.signal_ownership import public_delivery_decision
    for env in ({'SINDHU_PUBLIC_SIGNAL_OWNER': 'disabled'},
                {'SINDHU_PUBLIC_SIGNAL_OWNER': 'disabled', 'SINDHU_CLOUD_MODE': '1'}):
        ok, why = public_delivery_decision({'channel_id': 'public'}, 'public', environ=env)
        assert not ok and "'disabled'" in why


def test_missed_signal_sweep_runs_every_60s_inside_the_freshness_window():
    # The 60 s missed-signal recheck exists in main (changed from hourly on 2026-09-14);
    # it must stay far inside the 15-minute freshness window, which must NOT be widened.
    from paper_trading import engine, telegram_bot
    assert engine.TELEGRAM_SWEEP_INTERVAL_SECONDS == 60
    assert telegram_bot._DEFAULTS["signal_freshness_minutes"] == 15
    assert telegram_bot._DEFAULTS["signal_price_drift_pct"] == 0.5
    assert engine.TELEGRAM_SWEEP_INTERVAL_SECONDS < telegram_bot._DEFAULTS["signal_freshness_minutes"] * 60


def test_delivery_blockers_lists_every_reason_signals_would_not_go_out():
    from paper_trading.signal_ownership import delivery_blockers, delivery_report
    ready = {'bot_token': 't', 'channel_id': 'c', 'master_send_enabled': True, 'auto_send_enabled': True}
    assert delivery_blockers(ready, {'SINDHU_CLOUD_MODE': '1'}) == []
    assert 'READY' in delivery_report(ready, {'SINDHU_CLOUD_MODE': '1'})[0]
    env = {'SINDHU_CLOUD_MODE': '1', 'SINDHU_TELEGRAM_DRY_RUN': '1', 'SINDHU_PUBLIC_SIGNAL_OWNER': 'disabled', 'SINDHU_SAFE_START': '1'}
    text = ' | '.join(delivery_blockers(ready, env))
    assert 'DRY_RUN' in text and 'SAFE_START' in text and 'disabled' in text
    assert any('token' in b for b in delivery_blockers({'channel_id': 'c'}, {'SINDHU_CLOUD_MODE': '1'}))
    assert any('auto_send' in b for b in delivery_blockers(dict(ready, auto_send_enabled=False), {'SINDHU_CLOUD_MODE': '1'}))
