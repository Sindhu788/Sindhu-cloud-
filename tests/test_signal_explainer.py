"""Batch 7, Task 3: "Why This Signal" -- paper_trading/signal_explainer.py
builds a short Roman Urdu explanation purely from the SAME confluence and
reliability dicts already computed at signal-send time. No AI, no new
data -- these tests use hand-built confluence/reliability dicts shaped
exactly like paper_trading.confluence.score_confluence() and
paper_trading.pattern_stats.classify() already return.
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from data_engine import config as base_config, storage
from paper_trading import signal_explainer, telegram_bot


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    yield


@pytest.fixture(autouse=True)
def no_real_live_price(monkeypatch):
    monkeypatch.setattr(telegram_bot, "_fetch_live_price", lambda *a, **k: None)


def _open_position(**overrides):
    pos = {
        "id": "pos1", "strategy_id": "strat1", "strategy_name": "Test Strategy",
        "symbol": "BTCUSDT", "direction": "long", "entry_price": 100.0,
        "stop_loss": 95.0, "take_profit": 110.0, "market_state": "trending_up",
        "session": "london", "entry_reason": "test",
        "exchange": "binance", "size": 1.0, "risk_amount": 5.0,
        "entry_time": int(datetime.now(timezone.utc).timestamp() * 1000),
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    pos.update(overrides)
    storage.open_paper_position(pos)
    return pos


def _confluence(passed, total, aligned_names):
    factors = [{"name": n, "result": True} for n in aligned_names]
    factors += [{"name": f"unaligned_{i}", "result": False} for i in range(total - passed)]
    return {"label": f"test -- {passed}/{total}", "passed": passed, "total": total, "factors": factors}


def _reliable(win_rate_pct, sample_size, ci_lower, ci_upper):
    return {"sample_size": sample_size, "win_rate_pct": win_rate_pct, "reliable": True,
            "status": "reliable_good", "ci_lower_pct": ci_lower, "ci_upper_pct": ci_upper,
            "min_sample_size": 25}


def _insufficient(sample_size):
    return {"sample_size": sample_size, "win_rate_pct": 0.0, "reliable": False,
            "status": "insufficient_data", "ci_lower_pct": None, "ci_upper_pct": None,
            "min_sample_size": 25}


def test_mentions_aligned_factor_names_and_counts():
    conf = _confluence(2, 3, ["Market condition supports this signal", "Strategy not paused for safety"])
    text = signal_explainer.explain_signal(conf, None)
    assert "2/3" in text
    assert "Market condition supports this signal" in text
    assert "Strategy not paused for safety" in text


def test_mentions_real_win_rate_when_reliable():
    reliability = _reliable(64.0, 40, 48.0, 78.0)
    text = signal_explainer.explain_signal(None, reliability)
    assert "64%" in text
    assert "40 trades" in text
    assert "48%" in text and "78%" in text


def test_says_record_still_building_when_not_reliable_yet():
    reliability = _insufficient(10)
    text = signal_explainer.explain_signal(None, reliability)
    assert "10/25" in text
    assert "64%" not in text


def test_degrades_gracefully_when_both_are_none():
    text = signal_explainer.explain_signal(None, None)
    assert text  # never empty/blank
    assert "abhi kaafi data nahi hai" in text


def test_confluence_with_zero_counted_factors_falls_back_to_label_message():
    conf = {"label": "Unrated -- not enough data for any factor yet", "passed": 0, "total": 0, "factors": []}
    text = signal_explainer.explain_signal(conf, None)
    assert "abhi kaafi data nahi hai" in text


def test_combines_both_confluence_and_reliability_in_one_explanation():
    conf = _confluence(3, 3, ["A", "B", "C"])
    reliability = _reliable(70.0, 30, 55.0, 85.0)
    text = signal_explainer.explain_signal(conf, reliability)
    assert "3/3" in text
    assert "70%" in text


# --------------------------------------------------------------- end-to-end wiring

def test_send_signal_for_position_includes_explanation_in_message_and_log(test_db):
    telegram_bot.save_settings(bot_token="dummy", channel_id="123")
    _open_position()
    with patch.object(telegram_bot, "_raw_send", return_value=(True, None)) as mock_send:
        telegram_bot.send_signal_for_position("pos1", trigger_type="manual")

    sent_text = mock_send.call_args[0][0]
    assert "Yeh Signal Kyun" in sent_text

    logged = storage.list_telegram_signal_outcomes()
    assert len(logged) == 1
    assert logged[0]["explanation_text"]  # real explanation text was persisted, not left NULL
    assert logged[0]["explanation_text"] in sent_text
