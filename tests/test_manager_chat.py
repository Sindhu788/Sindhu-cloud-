"""Batch 4, Task 6 -- Manager Chat. A deterministic, keyword-matched,
strictly read-only Q&A panel. No AI/LLM -- every answer is built from a
real function call against real data, verified here against real
storage/domain functions (not mocks of manager_chat itself), plus an
explicit guarantee that no code path in this module can write anything.
"""

from datetime import datetime, timezone
from unittest import mock

import pytest

from data_engine import config as base_config, storage
from backtest_engine.strategy_config import StrategyConfig, Condition, SLTPSpec
from backtest_engine import strategy_library as lib
from sindhu_web import manager_chat


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(base_config, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(lib, "_LIBRARY_DIR", str(tmp_path / "library"))
    yield


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _close_trade(strategy_id, pnl, pos_id, closed_at=None):
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    storage.open_paper_position({
        "id": pos_id, "exchange": "binance", "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 100.0, "size": 1.0, "risk_amount": 5.0, "entry_time": now_ms,
        "created_at": _now_iso(), "strategy_id": strategy_id, "strategy_name": strategy_id,
    })
    storage.close_paper_position(
        pos_id, exit_price=100.0 + pnl, exit_time=now_ms, pnl=pnl, pnl_pct=pnl,
        exit_reason="take_profit", lifecycle={}, reflection={}, closed_at=closed_at or _now_iso(),
        book_key=strategy_id,
    )


def _make_strategy(name):
    cfg = StrategyConfig(
        name=name, timeframes={"entry": "1h"},
        entry_conditions=[Condition(type="indicator_compare", indicator="rsi", op="<", value=30.0)],
        stop_loss=SLTPSpec(type="fixed_pct", value=1.0), take_profit=SLTPSpec(type="fixed_pct", value=2.0),
        risk_pct=1.0,
    )
    return lib.create(cfg)


# ------------------------------------------------------------ intent routing

def test_unrecognized_question_says_so_and_lists_what_can_be_asked(test_db):
    result = manager_chat.ask("kya mausam kaisa hai", lang="ur")
    assert result["matched"] is False
    assert "samajh nahi aaya" in result["answer"].lower()
    assert "strategy" in result["answer"].lower()  # lists example questions


def test_empty_question_is_handled_gracefully(test_db):
    result = manager_chat.ask("", lang="ur")
    assert result["matched"] is False


def test_unrecognized_question_never_fabricates_a_number(test_db):
    result = manager_chat.ask("asdkjaskdjaksjd random text", lang="ur")
    assert result["matched"] is False
    assert not any(ch.isdigit() for ch in result["answer"])


def test_unrelated_sentence_mentioning_the_word_today_is_not_misrouted(test_db):
    """'aaj'/'today' bare must not trigger the today-activity intent for a
    sentence that isn't actually asking about trading activity."""
    result = manager_chat.ask("mausam kaisa hai aaj", lang="ur")
    assert result["matched"] is False


# ------------------------------------------------------------ best strategy

def test_best_strategy_question_returns_real_top_performer(test_db):
    sid_good = _make_strategy("Good Strategy")
    sid_bad = _make_strategy("Bad Strategy")
    for i in range(5):
        _close_trade(sid_good, pnl=10.0, pos_id=f"good-{i}")
        _close_trade(sid_bad, pnl=-5.0, pos_id=f"bad-{i}")

    result = manager_chat.ask("which strategy is performing best?", lang="en")
    assert result["matched"] is True
    assert result["intent"] == "best_strategy"
    assert "Good Strategy" in result["answer"]
    assert "Bad Strategy" not in result["answer"]


def test_best_strategy_in_urdu(test_db):
    sid = _make_strategy("Only Strategy")
    for i in range(5):
        _close_trade(sid, pnl=10.0, pos_id=f"only-{i}")
    result = manager_chat.ask("sabse acchi strategy kaunsi hai", lang="ur")
    assert result["matched"] is True
    assert "Only Strategy" in result["answer"]


def test_best_strategy_with_no_data_says_so_honestly(test_db):
    result = manager_chat.ask("best strategy?", lang="en")
    assert result["matched"] is True
    assert "no strategy" in result["answer"].lower()


# ------------------------------------------------------------ today

def test_today_question_counts_only_todays_trades(test_db):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT12:00:00+00:00")
    yesterday = "2020-01-01T12:00:00+00:00"
    sid = _make_strategy("Strat")
    _close_trade(sid, pnl=10.0, pos_id="today-trade", closed_at=today)
    _close_trade(sid, pnl=-10.0, pos_id="old-trade", closed_at=yesterday)

    result = manager_chat.ask("what happened today?", lang="en")
    assert result["matched"] is True
    assert result["intent"] == "today"
    assert "1 trades closed" in result["answer"] or "1 trade" in result["answer"]


# ------------------------------------------------------------ signals

def test_signals_recent_question_returns_real_count(test_db):
    storage.log_telegram_message("p1", "s1", "Strat", "manual", "text", True, None, _now_iso())
    storage.log_telegram_message("p2", "s1", "Strat", "manual", "text", True, None, _now_iso())
    storage.log_telegram_message("p3", "s1", "Strat", "manual", "text", False, "err", _now_iso())  # failed -- not counted

    result = manager_chat.ask("how many signals were sent?", lang="en")
    assert result["matched"] is True
    assert result["intent"] == "signals_recent"
    assert "2 signals" in result["answer"]


# ------------------------------------------------------------ balance/pnl

def test_balance_question_matches_real_engine_status(test_db):
    from paper_trading.engine import engine as paper_engine
    sid = _make_strategy("Strat")
    _close_trade(sid, pnl=50.0, pos_id="p1")

    result = manager_chat.ask("what's the balance and pnl?", lang="en")
    status = paper_engine.status()
    assert result["matched"] is True
    assert f"${status['balance']:.2f}" in result["answer"]


# ------------------------------------------------------------ locked strategies

def test_locked_strategies_question_lists_real_locked_ones(test_db):
    locked_id = _make_strategy("Locked Strategy")
    _make_strategy("Fine Strategy")
    storage.save_extraction_fidelity_report("hash1", 5, 2, 3, [
        {"id": 1, "text": "missing rule", "category": "entry", "status": "missing", "captured_as": None},
    ], "groq", _now_iso())
    storage.set_extraction_fidelity_strategy_id("hash1", locked_id)

    result = manager_chat.ask("which strategies are locked?", lang="en")
    assert result["matched"] is True
    assert "Locked Strategy" in result["answer"]
    assert "Fine Strategy" not in result["answer"]


def test_locked_strategies_with_none_locked(test_db):
    _make_strategy("Fine Strategy")
    result = manager_chat.ask("koi strategy lock hai?", lang="ur")
    assert result["matched"] is True
    assert "koi" in result["answer"].lower() and "nahi" in result["answer"].lower()


# ------------------------------------------------------------ maturity level

def test_maturity_level_question_matches_real_computed_level(test_db):
    from knowledge_engine.maturity import compute_maturity_level
    result = manager_chat.ask("what's the system's maturity level?", lang="en")
    expected = compute_maturity_level()
    assert result["matched"] is True
    assert f"Level {expected['level']}/5" in result["answer"]


# ------------------------------------------------------------ read-only guarantee

def test_no_write_function_is_ever_called_by_any_intent(test_db):
    """Patches every real write-capable storage function this module could
    plausibly reach and confirms none of them fire for any supported
    question -- the strict "never changes state" requirement, verified by
    instrumentation rather than just code review."""
    write_fn_names = [
        "open_paper_position", "close_paper_position", "create_batch",
        "update_batch_status", "save_extraction_fidelity_report",
        "set_extraction_fidelity_strategy_id", "log_telegram_message",
        "save_lesson", "reset_paper_balance",
    ]
    patches = [mock.patch.object(storage, name, side_effect=AssertionError(f"{name} must never be called"))
               for name in write_fn_names]
    for p in patches:
        p.start()
    try:
        questions = [
            "which strategy is performing best?", "what happened today?",
            "how many signals were sent?", "what's the balance and pnl?",
            "which strategies are locked?", "what's the maturity level?",
            "random unrecognized text",
        ]
        for q in questions:
            manager_chat.ask(q, lang="en")
            manager_chat.ask(q, lang="ur")
    finally:
        for p in patches:
            p.stop()


def test_ask_never_raises_for_any_supported_question(test_db):
    questions = [
        "which strategy is performing best?", "what happened today?",
        "how many signals were sent?", "what's the balance and pnl?",
        "which strategies are locked?", "what's the maturity level?",
    ]
    for q in questions:
        result = manager_chat.ask(q, lang="en")
        assert isinstance(result["answer"], str) and result["answer"]
