from paper_trading import telegram_bot

POS = {"id": "p1", "symbol": "BTCUSDT", "direction": "long", "entry_price": 100.0, "stop_loss": 95.0, "take_profit": 110.0, "confidence": 46.3,
       "timeframe": "15m", "strategy_id": None, "strategy_name": "S", "exchange": "okx"}


def test_confidence_line_is_shown_by_default(monkeypatch, test_db):
    monkeypatch.delenv("SINDHU_HIDE_CONFIDENCE", raising=False)
    assert "Confidence: 46.3%" in telegram_bot.format_signal_message(dict(POS), lang="en")


def test_flag_hides_only_the_confidence_line(monkeypatch, test_db):
    monkeypatch.setenv("SINDHU_HIDE_CONFIDENCE", "1")
    text = telegram_bot.format_signal_message(dict(POS), lang="en")
    assert "Confidence" not in text and "46.3" not in text
    assert "Entry:" in text and "Stop-Loss:" in text and "Take-Profit:" in text      # the trading fields are untouched


def test_flag_values_that_mean_off_keep_the_line(monkeypatch, test_db):
    for v in ("0", "", "no", "off"):
        monkeypatch.setenv("SINDHU_HIDE_CONFIDENCE", v)
        assert "Confidence: 46.3%" in telegram_bot.format_signal_message(dict(POS), lang="en")


def test_disclaimer_and_validation_class_are_always_on_whatever_the_old_flag_says(monkeypatch, test_db):
    """Master plan A14 (P13) replaced the Day 7 opt-in flag: every signal message ends with the validation class and the disclaimer."""
    outs = []
    for v in (None, "0", "1"):
        if v is None:
            monkeypatch.delenv("SINDHU_SIGNAL_DISCLAIMER", raising=False)
        else:
            monkeypatch.setenv("SINDHU_SIGNAL_DISCLAIMER", v)
        outs.append(telegram_bot.format_signal_message(dict(POS), lang="en"))
    assert outs[0] == outs[1] == outs[2]
    lines = outs[0].splitlines()
    assert lines[-1] == telegram_bot.SIGNAL_DISCLAIMER and lines[-2].startswith("Backtest validation: ")
