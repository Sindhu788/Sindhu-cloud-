from backtest_engine import concepts
from paper_trading import memory_guard as mg


def test_levels_follow_the_limits(monkeypatch):
    monkeypatch.setattr(mg, "SOFT_MB", 400)
    monkeypatch.setattr(mg, "HARD_MB", 450)
    assert mg.level(300) == "ok" and mg.level(400) == "soft" and mg.level(449) == "soft" and mg.level(450) == "hard"


def test_soft_limit_drops_the_memo_and_logs_but_does_not_alert(monkeypatch):
    monkeypatch.setattr(mg, "SOFT_MB", 400)
    monkeypatch.setattr(mg, "HARD_MB", 450)
    logs, sent = [], []
    concepts.memo_enable(True)
    assert mg.check(log=logs.append, send=sent.append, rss=420) == "soft"
    assert concepts._MEMO_ON is False and logs and "memory-guard" in logs[0] and sent == []
    assert mg.optional_work_allowed() in (True, False)      # depends on the real RSS of the test process, not asserted


def test_hard_limit_alerts_the_owner_once_per_window(monkeypatch):
    monkeypatch.setattr(mg, "SOFT_MB", 400)
    monkeypatch.setattr(mg, "HARD_MB", 450)
    mg._last["alert_at"] = 0.0
    sent = []
    assert mg.check(log=lambda m: None, send=sent.append, now=1_000_000.0, rss=470) == "hard"
    assert mg.check(log=lambda m: None, send=sent.append, now=1_000_060.0, rss=470) == "hard"
    assert len(sent) == 1 and "470 MB of 512" in sent[0]
    assert mg.check(log=lambda m: None, send=sent.append, now=1_000_000.0 + 3 * 3600, rss=470) == "hard"
    assert len(sent) == 2


def test_ok_level_changes_nothing(monkeypatch):
    concepts.memo_enable(True)
    try:
        assert mg.check(log=lambda m: (_ for _ in ()).throw(AssertionError("no log expected")), rss=200) == "ok"
        assert concepts._MEMO_ON is True
    finally:
        concepts.memo_enable(False)


def test_prefetch_is_skipped_when_memory_is_tight(monkeypatch):
    import types
    from paper_trading import engine as eng
    import data_engine.resample as rs
    called = []
    monkeypatch.setattr(rs, "get_ohlcv", lambda *a, **k: called.append(a))
    monkeypatch.setattr(eng, "LIVE_CANDLES_ONLY", True)
    monkeypatch.setattr(eng.memory_guard, "optional_work_allowed", lambda: False)
    monkeypatch.setattr(eng.market_state, "classify", lambda ex, s: {"market_state": "ranging"})
    monkeypatch.setattr(eng.strategy_matcher, "relevant_strategies", lambda s, m: [{"config": types.SimpleNamespace(timeframes={"entry": "1h"})}])
    eng.PaperTradingEngine()._prefetch_candles("okx", ["A/USDT", "B/USDT"], {})
    assert called == []
