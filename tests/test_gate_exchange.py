from paper_trading import telegram_bot as tb


def test_default_behaviour_is_unchanged_and_flag_switches_to_the_position_exchange(monkeypatch):
    cfg = {"default": "bybit"}
    pos = {"exchange": "okx"}
    monkeypatch.delenv("SINDHU_GATE_USE_POSITION_EXCHANGE", raising=False)
    assert tb._gate_exchange(pos, cfg) == "bybit"          # OFF: exactly as before
    monkeypatch.setenv("SINDHU_GATE_USE_POSITION_EXCHANGE", "1")
    assert tb._gate_exchange(pos, cfg) == "okx"
    assert tb._gate_exchange({}, cfg) == "bybit"           # no exchange on the position -> default
    monkeypatch.setenv("SINDHU_GATE_USE_POSITION_EXCHANGE", "0")
    assert tb._gate_exchange(pos, cfg) == "bybit"


def test_no_gate_site_reads_the_default_exchange_directly_any_more():
    import pathlib
    src = pathlib.Path(tb.__file__).read_text(encoding="utf-8")
    assert 'exchange = exchanges_cfg["default"]' not in src.replace('return exchanges_cfg["default"]', "")
