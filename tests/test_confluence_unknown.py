"""Master plan A8 (P14): a missing market-regime input makes confluence UNKNOWN (never "Strong") and UNKNOWN is withheld from public send."""
from unittest.mock import patch

from paper_trading import confluence, telegram_bot


def test_missing_regime_is_unknown_never_strong(test_db):
    with patch.object(confluence.regime_mod, "classify_regime", return_value=None):
        r = confluence.score_confluence("s1", "BTC/USDT", "okx", "trending_up", "asia", "long")
    assert r["unknown"] is True and r["label"].startswith("UNKNOWN") and "Strong" not in r["label"]
    with patch.object(confluence.regime_mod, "classify_regime", side_effect=RuntimeError("403 geo-block")):
        r = confluence.score_confluence("s1", "BTC/USDT", "okx", "trending_up", "asia", "long")
    assert r["unknown"] is True and r["inputs"]["regime_exchange"] == "okx"


def test_real_regime_keeps_the_old_labels(test_db):
    with patch.object(confluence.regime_mod, "classify_regime", return_value={"regime": "trending"}):
        r = confluence.score_confluence("s1", "BTC/USDT", "okx", "trending_up", "asia", "long")
    assert r["unknown"] is False and r["label"].startswith("Strong") and r["inputs"]["regime"] == "trending"


def test_unknown_confluence_is_withheld_by_both_public_gates(test_db, monkeypatch):
    from data_engine import storage
    monkeypatch.setattr(telegram_bot, "load_settings", lambda: {"auto_send_enabled": True, "auto_send_min_confluence_ratio": 0.0,
                                                               "auto_send_min_confluence_count": 0})
    monkeypatch.setattr(storage, "get_paper_position", lambda pid: {"id": pid, "strategy_id": "s1", "symbol": "BTC/USDT",
                                                                     "exchange": "okx", "direction": "long"})
    monkeypatch.setattr(storage, "is_strategy_paused", lambda sid: (False, None, None))
    unknown = {"label": "UNKNOWN -- market regime data unavailable", "passed": 2, "total": 2, "factors": [], "unknown": True}
    with patch.object(telegram_bot.confluence_mod, "score_confluence", return_value=unknown):
        for fn in (telegram_bot.evaluate_auto_send, telegram_bot.evaluate_auto_send_low_tier):
            ok, reason = fn("p1")
            assert ok is False and "UNKNOWN" in reason
