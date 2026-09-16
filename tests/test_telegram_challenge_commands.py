"""Investigation Batch 2026-09-17, Parts 2-5: real evidence for the
Telegram /challenge command family (paper_trading/telegram_challenge_
commands.py) -- creation (with auto strategy selection + realism
warnings), /stopchallenge, /resumechallenge, /mychallenges, /report,
/menu, the resource-conflict guard (2.12), the completion/failure/
balance-pause lifecycle (paper_trading/challenge_multi.py), and the
⚫ signal marker (Part 4).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from data_engine import config as base_config, storage
from paper_trading import challenge_multi, telegram_bot, telegram_challenge_commands, telegram_commands


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    telegram_commands._last_update_id = None
    yield


@pytest.fixture(autouse=True)
def no_real_live_price(monkeypatch):
    monkeypatch.setattr(telegram_bot, "_fetch_live_price", lambda *a, **k: None)


@pytest.fixture(autouse=True)
def no_real_reply_network_call(monkeypatch):
    """telegram_commands.handle_update() replies via telegram_commands._reply
    (a direct requests.post, separate from telegram_bot._raw_send which
    individual tests patch for their own assertions) -- without this, every
    test in this file would make a real, slowly-failing network call with
    the fake "test-token" credential."""
    monkeypatch.setattr(telegram_commands, "_reply", lambda chat_id, text: None)


def _configure_bot(chat_id="12345"):
    telegram_bot.save_settings(bot_token="test-token", channel_id=chat_id)


def _update(text, chat_id="12345", update_id=1):
    return {"update_id": update_id, "message": {"chat": {"id": chat_id}, "text": text}}


def _iso(days_ago=0):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _trade(pid, strategy_id, symbol, pnl, risk_amount=5.0, closed_days_ago=1, entry_time_ms=1700000000000):
    storage.open_paper_position({
        "id": pid, "exchange": "binance", "symbol": symbol, "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": risk_amount,
        "entry_time": entry_time_ms, "created_at": _iso(closed_days_ago),
        "strategy_id": strategy_id, "strategy_name": strategy_id,
    })
    storage.close_paper_position(
        pid, 100.0, entry_time_ms + 60000, pnl, pnl, "take_profit", {}, {}, _iso(closed_days_ago),
    )


def _seed_strong_history(strategy_id="stratX", symbol="BTCUSDT", n=30, win_pnl=10.0, loss_pnl=-3.0, win_ratio=0.8):
    wins = int(n * win_ratio)
    for i in range(wins):
        _trade(f"{strategy_id}-w{i}", strategy_id, symbol, win_pnl, closed_days_ago=n - i)
    for i in range(n - wins):
        _trade(f"{strategy_id}-l{i}", strategy_id, symbol, loss_pnl, closed_days_ago=n - wins - i)


# ------------------------------------------------------------- argument parsing


def test_parse_explicit_args():
    parsed, err = telegram_challenge_commands._parse_challenge_args("50 100 14d")
    assert err is None
    assert parsed == {"start_amount": 50.0, "target_amount": 100.0, "days": 14.0, "coins": None, "name": None}


def test_parse_hours_unit():
    parsed, err = telegram_challenge_commands._parse_challenge_args("50 100 36h")
    assert err is None
    assert parsed["days"] == pytest.approx(1.5)


def test_parse_with_coins_and_name():
    parsed, err = telegram_challenge_commands._parse_challenge_args("50 100 14d coins=btc,eth Weekend Challenge")
    assert err is None
    assert parsed["coins"] == ["BTCUSDT", "ETHUSDT"]
    assert parsed["name"] == "Weekend Challenge"


def test_parse_template_conservative():
    parsed, err = telegram_challenge_commands._parse_challenge_args("conservative")
    assert err is None
    assert parsed["start_amount"] == 50.0 and parsed["target_amount"] == 100.0 and parsed["days"] == 14.0


def test_parse_template_aggressive():
    parsed, err = telegram_challenge_commands._parse_challenge_args("aggressive")
    assert err is None
    assert parsed["start_amount"] == 20.0 and parsed["target_amount"] == 50.0 and parsed["days"] == 5.0


def test_parse_rejects_target_not_greater_than_balance():
    parsed, err = telegram_challenge_commands._parse_challenge_args("100 50 14d")
    assert parsed is None
    assert "greater than" in err


def test_parse_rejects_bad_time_format():
    parsed, err = telegram_challenge_commands._parse_challenge_args("50 100 soon")
    assert parsed is None
    assert "Time limit" in err


def test_parse_empty_args_returns_none_no_error():
    parsed, err = telegram_challenge_commands._parse_challenge_args("")
    assert parsed is None and err is None


# ------------------------------------------------------------- /challenge creation


def test_challenge_with_no_args_shows_usage(test_db):
    _configure_bot()
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)):
        reply = telegram_commands.handle_update(_update("/challenge"))
    assert "Usage" in reply


def test_challenge_creates_with_auto_selected_strategy(test_db):
    _configure_bot()
    _seed_strong_history("stratX", "BTCUSDT", n=30, win_ratio=0.8)
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)):
        reply = telegram_commands.handle_update(_update("/challenge 50 100 14d"))
    assert "Challenge created" in reply
    assert "Auto-selected strategy" in reply
    assert "stratX" in reply
    challenges = storage.list_challenges()
    assert len(challenges) == 1
    assert challenges[0]["scope_strategy_id"] == "stratX"
    assert challenges[0]["scope_symbol"] == "BTCUSDT"
    assert challenges[0]["start_amount"] == 50.0
    assert challenges[0]["target_amount"] == 100.0


def test_challenge_with_name_and_coins(test_db):
    _configure_bot()
    _seed_strong_history("stratX", "BTCUSDT", n=30, win_ratio=0.8)
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)):
        reply = telegram_commands.handle_update(_update("/challenge 50 100 14d coins=BTC Weekend Fun"))
    challenge = storage.list_challenges()[0]
    assert challenge["label"] == "Weekend Fun"


def test_challenge_with_no_real_history_creates_unscoped_with_honest_note(test_db):
    _configure_bot()
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)):
        reply = telegram_commands.handle_update(_update("/challenge 50 100 14d"))
    assert "No single strategy" in reply
    challenge = storage.list_challenges()[0]
    assert challenge["scope_strategy_id"] is None


def test_challenge_unrealistic_target_shows_honest_warning(test_db):
    _configure_bot()
    # Weak, slow-growing history -- can't realistically hit a 100x target in 1 day.
    _seed_strong_history("stratX", "BTCUSDT", n=30, win_pnl=1.0, loss_pnl=-1.0, win_ratio=0.55)
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)):
        reply = telegram_commands.handle_update(_update("/challenge 10 10000 1d"))
    assert "may not be realistic" in reply or "Not enough real closed-trade history" in reply


def test_challenge_template_creates_conservative(test_db):
    _configure_bot()
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)):
        telegram_commands.handle_update(_update("/challenge conservative"))
    challenge = storage.list_challenges()[0]
    assert challenge["start_amount"] == 50.0
    assert challenge["target_amount"] == 100.0
    assert challenge["days"] == 14


def test_second_challenge_does_not_claim_the_same_combo_already_active(test_db):
    """2.12: two challenges must never both scope to the exact same
    (strategy, coin) -- that would double-count the same real trades
    toward two different targets."""
    _configure_bot()
    _seed_strong_history("stratX", "BTCUSDT", n=30, win_ratio=0.8)
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)):
        telegram_commands.handle_update(_update("/challenge 50 100 14d", update_id=1))
        telegram_commands.handle_update(_update("/challenge 60 120 14d", update_id=2))
    challenges = storage.list_challenges()
    assert len(challenges) == 2
    scopes = [(c["scope_strategy_id"], c["scope_symbol"]) for c in challenges]
    # Only one may claim (stratX, BTCUSDT); the other falls back to unscoped.
    claimed = [s for s in scopes if s == ("stratX", "BTCUSDT")]
    assert len(claimed) == 1


def test_multiple_active_challenges_allowed_up_to_the_cap(test_db):
    _configure_bot()
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)):
        for i in range(challenge_multi.MAX_ACTIVE_CHALLENGES):
            reply = telegram_commands.handle_update(_update(f"/challenge {50+i} {100+i} 14d", update_id=i + 1))
            assert "Challenge created" in reply
    assert len(storage.list_challenges()) == challenge_multi.MAX_ACTIVE_CHALLENGES


# ------------------------------------------------------------- /stopchallenge, /resumechallenge


def test_stopchallenge_archives_with_final_result(test_db):
    _configure_bot()
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)):
        telegram_commands.handle_update(_update("/challenge 50 100 14d", update_id=1))
    challenge_id = storage.list_challenges()[0]["id"]
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)):
        reply = telegram_commands.handle_update(_update(f"/stopchallenge {challenge_id}", update_id=2))
    assert "stopped" in reply.lower()
    row = storage.get_challenge(challenge_id)
    assert row["archived"] is True
    assert row["final_status"] == "stopped"


def test_stopchallenge_unknown_id_gives_honest_error(test_db):
    _configure_bot()
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)):
        reply = telegram_commands.handle_update(_update("/stopchallenge doesnotexist"))
    assert "unknown challenge id" in reply


def test_resumechallenge_unpauses(test_db):
    _configure_bot()
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)):
        telegram_commands.handle_update(_update("/challenge 50 100 14d", update_id=1))
    challenge_id = storage.list_challenges()[0]["id"]
    storage.update_challenge(challenge_id, _iso(), paused=True)
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)):
        reply = telegram_commands.handle_update(_update(f"/resumechallenge {challenge_id}", update_id=2))
    assert "resumed" in reply.lower()
    assert storage.get_challenge(challenge_id)["paused"] is False


# ------------------------------------------------------------- /mychallenges, /report, /menu


def test_mychallenges_lists_active_and_leaderboard(test_db):
    _configure_bot()
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)):
        telegram_commands.handle_update(_update("/challenge 50 100 14d", update_id=1))
        telegram_commands.handle_update(_update("/challenge 60 120 14d", update_id=2))
        reply = telegram_commands.handle_update(_update("/mychallenges", update_id=3))
    assert "Active challenges" in reply
    assert "Leaderboard" in reply


def test_mychallenges_with_none_active_is_honest(test_db):
    _configure_bot()
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)):
        reply = telegram_commands.handle_update(_update("/mychallenges"))
    assert "No active challenges" in reply


def test_report_shows_all_three_sections(test_db):
    _configure_bot()
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)):
        telegram_commands.handle_update(_update("/challenge 50 100 14d", update_id=1))
        reply = telegram_commands.handle_update(_update("/report", update_id=2))
    assert "Total Trades" in reply
    assert "Group Detail" in reply
    assert "Challenges" in reply


def test_menu_explains_every_marker(test_db):
    _configure_bot()
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)):
        reply = telegram_commands.handle_update(_update("/menu"))
    for marker_word in ("Profitable", "Losing", "Challenge group", "Not yet classified"):
        assert marker_word in reply
    assert "/challenge" in reply and "/report" in reply and "/mychallenges" in reply


def test_help_still_works_and_points_to_menu(test_db):
    _configure_bot()
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)):
        reply = telegram_commands.handle_update(_update("/help"))
    assert "/menu" in reply


# ------------------------------------------------------------- lifecycle: complete / fail / pause


def test_sweep_detects_completion_and_archives(test_db):
    challenge = challenge_multi.create_challenge("Done Soon", 50.0, 60.0, "custom", days=30)
    storage.update_challenge(challenge["id"], _iso(), started_at=_iso(5))  # started 5 days ago
    # current_amount uses the same real risk-multiple rescaling
    # challenge_mode._current_amount always does (r_multiple = pnl /
    # risk_amount, scaled by start_amount * risk_pct_default) -- a small
    # risk_amount against a big pnl clears the $60 target comfortably.
    _trade("w1", "any", "BTCUSDT", 25.0, risk_amount=1.0, closed_days_ago=2)
    events = challenge_multi.sweep_challenge_lifecycle()
    completed = [e for e in events if e["kind"] == "completed" and e["challenge_id"] == challenge["id"]]
    assert len(completed) == 1
    assert storage.get_challenge(challenge["id"])["final_status"] == "completed"
    assert storage.get_challenge(challenge["id"])["archived"] is True


def test_sweep_detects_deadline_failure(test_db):
    started_at = _iso(40)  # 40 days ago
    challenge = challenge_multi.create_challenge("Too Slow", 50.0, 1000.0, "custom", days=30)
    storage.update_challenge(challenge["id"], _iso(), started_at=started_at)
    events = challenge_multi.sweep_challenge_lifecycle()
    failed = [e for e in events if e["kind"] == "failed" and e["challenge_id"] == challenge["id"]]
    assert len(failed) == 1
    assert failed[0]["progress_pct"] < 100.0
    assert storage.get_challenge(challenge["id"])["final_status"] == "failed"


def test_sweep_detects_balance_threshold_and_pauses(test_db):
    challenge = challenge_multi.create_challenge(
        "Risky", 100.0, 200.0, "custom", days=30, scope_strategy_id="stratX", scope_symbol="BTCUSDT",
    )
    storage.update_challenge(challenge["id"], _iso(), started_at=_iso(5))
    # Same real risk-multiple rescaling as above -- risk_amount=1.0 against
    # a big loss drops current_amount well under the 50% pause threshold.
    _trade("loss1", "stratX", "BTCUSDT", -55.0, risk_amount=1.0, closed_days_ago=2)
    events = challenge_multi.sweep_challenge_lifecycle()
    paused = [e for e in events if e["kind"] == "paused" and e["challenge_id"] == challenge["id"]]
    assert len(paused) == 1
    row = storage.get_challenge(challenge["id"])
    assert row["paused"] is True
    assert row["archived"] is False  # paused, never archived automatically


def test_paused_challenge_is_left_alone_by_later_sweeps(test_db):
    challenge = challenge_multi.create_challenge(
        "Risky", 100.0, 200.0, "custom", days=30, scope_strategy_id="stratX", scope_symbol="BTCUSDT",
    )
    storage.update_challenge(challenge["id"], _iso(), started_at=_iso(5))
    _trade("loss1", "stratX", "BTCUSDT", -55.0, risk_amount=1.0, closed_days_ago=2)
    challenge_multi.sweep_challenge_lifecycle()
    assert storage.get_challenge(challenge["id"])["paused"] is True
    events_again = challenge_multi.sweep_challenge_lifecycle()
    assert events_again == []


def test_find_non_conflicting_path_skips_already_claimed_combo(test_db):
    challenge_multi.create_challenge(
        "First", 50.0, 100.0, "custom", days=14, scope_strategy_id="stratX", scope_symbol="BTCUSDT",
    )
    paths = [
        {"strategy_id": "stratX", "symbol": "BTCUSDT"},
        {"strategy_id": "stratY", "symbol": "ETHUSDT"},
    ]
    best = challenge_multi.find_non_conflicting_path(paths)
    assert best["strategy_id"] == "stratY"


def test_find_non_conflicting_path_returns_none_when_everything_claimed(test_db):
    challenge_multi.create_challenge(
        "First", 50.0, 100.0, "custom", days=14, scope_strategy_id="stratX", scope_symbol="BTCUSDT",
    )
    paths = [{"strategy_id": "stratX", "symbol": "BTCUSDT"}]
    assert challenge_multi.find_non_conflicting_path(paths) is None


def test_celebration_summary_has_real_numbers(test_db):
    challenge = challenge_multi.create_challenge(
        "Winner", 50.0, 60.0, "custom", days=14, scope_strategy_id="stratX", scope_symbol="BTCUSDT",
    )
    storage.update_challenge(challenge["id"], _iso(), started_at=_iso(5))
    _trade("w1", "stratX", "BTCUSDT", 8.0, closed_days_ago=3)
    _trade("l1", "stratX", "BTCUSDT", -2.0, closed_days_ago=2)
    summary = challenge_multi.celebration_summary(challenge["id"])
    assert summary["signals_used"] == 2
    assert summary["best_trade"]["pnl"] == 8.0
    assert summary["worst_trade"]["pnl"] == -2.0
    assert summary["profit_factor"] == 4.0


def test_send_lifecycle_event_messages_sends_real_text_for_each_kind():
    events = [
        {"kind": "completed", "challenge_id": "c1", "label": "Winner", "start_amount": 50.0, "target_amount": 60.0,
         "days_taken": 3.0, "signals_used": 2, "profit_factor": 4.0,
         "best_trade": {"symbol": "BTCUSDT", "pnl": 8.0}, "worst_trade": {"symbol": "BTCUSDT", "pnl": -2.0}},
        {"kind": "failed", "challenge_id": "c2", "label": "Loser", "progress_pct": 40.0,
         "current_amount": 60.0, "target_amount": 100.0, "days": 14},
        {"kind": "paused", "challenge_id": "c3", "label": "Risky", "start_amount": 100.0, "current_amount": 40.0,
         "threshold_pct": 50.0},
    ]
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        telegram_challenge_commands.send_lifecycle_event_messages(events)
    assert mock_send.call_count == 3
    texts = [c.args[0] for c in mock_send.call_args_list]
    assert any("Challenge complete" in t for t in texts)
    assert any("Challenge failed" in t for t in texts)
    assert any("paused" in t for t in texts)


# ------------------------------------------------------------- signal marker (Part 4)


def test_signal_marker_appears_for_active_challenge_scope(test_db):
    challenge_multi.create_challenge(
        "Marked", 50.0, 100.0, "custom", days=14, scope_strategy_id="stratX", scope_symbol="BTCUSDT",
    )
    position = {
        "id": "pos1", "symbol": "BTCUSDT", "strategy_id": "stratX", "direction": "long",
        "entry_price": 100.0, "stop_loss": 95.0, "take_profit": 110.0, "confidence": None,
    }
    msg = telegram_bot.format_signal_message(position, lang="en")
    assert "⚫" in msg


def test_signal_marker_absent_for_unrelated_strategy(test_db):
    challenge_multi.create_challenge(
        "Marked", 50.0, 100.0, "custom", days=14, scope_strategy_id="stratX", scope_symbol="BTCUSDT",
    )
    position = {
        "id": "pos1", "symbol": "ETHUSDT", "strategy_id": "stratOther", "direction": "long",
        "entry_price": 100.0, "stop_loss": 95.0, "take_profit": 110.0, "confidence": None,
    }
    msg = telegram_bot.format_signal_message(position, lang="en")
    assert "⚫" not in msg


def test_signal_marker_absent_while_paused(test_db):
    challenge = challenge_multi.create_challenge(
        "Marked", 50.0, 100.0, "custom", days=14, scope_strategy_id="stratX", scope_symbol="BTCUSDT",
    )
    storage.update_challenge(challenge["id"], _iso(), paused=True)
    position = {
        "id": "pos1", "symbol": "BTCUSDT", "strategy_id": "stratX", "direction": "long",
        "entry_price": 100.0, "stop_loss": 95.0, "take_profit": 110.0, "confidence": None,
    }
    msg = telegram_bot.format_signal_message(position, lang="en")
    assert "⚫" not in msg


# ------------------------------------------------------------- daily update (2.15)


def test_send_daily_challenge_updates_sends_once_per_day(test_db):
    _configure_bot()
    challenge_multi.create_challenge("Daily", 50.0, 100.0, "custom", days=14)
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        sent_first = challenge_multi.send_daily_challenge_updates()
        sent_second = challenge_multi.send_daily_challenge_updates()
    assert len(sent_first) == 1
    assert len(sent_second) == 0  # already sent today -- no duplicate
    assert mock_send.call_count == 1


def test_send_daily_challenge_updates_skips_when_bot_not_configured(test_db):
    challenge_multi.create_challenge("Daily", 50.0, 100.0, "custom", days=14)
    with patch.object(telegram_bot, "_raw_send") as mock_send:
        sent = challenge_multi.send_daily_challenge_updates()
    assert sent == []
    mock_send.assert_not_called()
