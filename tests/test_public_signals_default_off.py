"""Master plan A14 (P1 + P13): automatic public Telegram signals are OFF by code default, even when the saved settings say
auto_send_enabled=True (as Cloud's did); the owner allows them only with SINDHU_PUBLIC_SIGNALS=1. Every signal message carries the
backtest validation class and the disclaimer."""
import pytest

from paper_trading import telegram_bot


@pytest.fixture
def saved_settings_say_on(monkeypatch):
    monkeypatch.setattr(telegram_bot, "load_settings", lambda: {"auto_send_enabled": True, "auto_send_high_confidence_only": False})


def test_default_is_off_and_nothing_public_is_sent(monkeypatch, test_db, saved_settings_say_on):
    monkeypatch.delenv("SINDHU_PUBLIC_SIGNALS", raising=False)
    assert telegram_bot.public_signals_allowed() is False
    ok, reason = telegram_bot.evaluate_auto_send(12345)
    assert ok is False and reason == telegram_bot.PUBLIC_SIGNALS_OFF_REASON
    raw_sends = []
    monkeypatch.setattr(telegram_bot, "_raw_send", lambda *a, **k: raw_sends.append(a) or (True, None))
    assert telegram_bot.sweep_unsent_qualifying_signals() == []
    assert raw_sends == []


@pytest.mark.parametrize("value", ["0", "", "false", "off", "no"])
def test_only_an_explicit_yes_turns_them_on(monkeypatch, value):
    monkeypatch.setenv("SINDHU_PUBLIC_SIGNALS", value)
    assert telegram_bot.public_signals_allowed() is False


def test_owner_env_switch_allows_the_normal_gates_to_run(monkeypatch, test_db, saved_settings_say_on):
    monkeypatch.setenv("SINDHU_PUBLIC_SIGNALS", "1")
    ok, reason = telegram_bot.evaluate_auto_send(987654321)          # no such position: the NEXT gate answers
    assert ok is False and reason == "position not found"


def test_validation_class_lookup():
    import json, os
    path = os.path.join(os.path.dirname(telegram_bot.__file__), "validation_classes.json")
    classes = json.load(open(path, encoding="utf-8"))["classes"]
    counts = {}
    for v in classes.values():
        counts[v["class"]] = counts.get(v["class"], 0) + 1
    assert counts == {"FAILED": 36, "FRAGILE": 1, "INSUFFICIENT_DATA": 5}     # docs/BACKTEST_RESULTS.md: 0 ROBUST, 1 FRAGILE, 36, 5
    some_failed = next(k for k, v in classes.items() if v["class"] == "FAILED")
    assert telegram_bot.validation_class(some_failed) == "FAILED"
    assert telegram_bot.validation_class("not-a-strategy") == "NOT VALIDATED"
    assert telegram_bot.validation_class(None) == "NOT VALIDATED"


def test_every_signal_message_ends_with_validation_class_and_disclaimer(test_db):
    pos = {"symbol": "BTC/USDT", "direction": "long", "entry_price": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
           "timeframe": "1h", "confidence": 70, "strategy_id": "not-a-strategy"}
    lines = telegram_bot.format_signal_message(pos, lang="en").split("\n")
    assert lines[-2] == "Backtest validation: NOT VALIDATED"
    assert lines[-1] == "Paper-trading research signal. Not financial advice. Past results do not predict future results."


def test_queued_retries_wait_without_using_attempts_while_off(monkeypatch, test_db):
    monkeypatch.delenv("SINDHU_PUBLIC_SIGNALS", raising=False)
    from data_engine import storage
    monkeypatch.setattr(storage, "list_pending_telegram_retries", lambda: [{"id": 1, "position_id": 7, "trigger_type": "x", "high_confidence": 0}])
    called = []
    monkeypatch.setattr(telegram_bot, "send_signal_for_position", lambda *a, **k: called.append(a))
    monkeypatch.setattr(storage, "record_telegram_retry_attempt", lambda *a, **k: called.append(a))
    assert telegram_bot.sweep_pending_telegram_retries() == {"delivered": [], "abandoned": [], "still_pending": [7]}
    assert called == []
