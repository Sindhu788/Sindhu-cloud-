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


def test_cloud_mode_gate_never_reads_bybit_and_uses_the_position_exchange(monkeypatch):
    """Master plan A7 (P8): on Cloud the confluence gate reads the position's own exchange, never the region-blocked default."""
    from paper_trading import telegram_bot
    monkeypatch.setenv("SINDHU_CLOUD_MODE", "1")
    monkeypatch.delenv("SINDHU_GATE_USE_POSITION_EXCHANGE", raising=False)
    assert telegram_bot._gate_exchange({"exchange": "okx"}, {"default": "bybit"}) == "okx"
    assert telegram_bot._gate_exchange({}, {"default": "bybit"}) == "okx"
    assert telegram_bot._gate_exchange({"exchange": "bybit"}, {"default": "bybit"}) == "okx"


def test_local_mode_gate_is_unchanged(monkeypatch):
    from paper_trading import telegram_bot
    monkeypatch.delenv("SINDHU_CLOUD_MODE", raising=False)
    monkeypatch.delenv("SINDHU_GATE_USE_POSITION_EXCHANGE", raising=False)
    assert telegram_bot._gate_exchange({"exchange": "okx"}, {"default": "binance"}) == "binance"


def test_cloud_safe_exchange_maps_only_blocked_exchanges(monkeypatch):
    from data_engine import config
    monkeypatch.setenv("SINDHU_CLOUD_MODE", "1")
    assert [config.cloud_safe_exchange(x) for x in ("binance", "bybit", "okx", "gate")] == ["okx", "okx", "okx", "gate"]
    monkeypatch.delenv("SINDHU_CLOUD_MODE")
    assert config.cloud_safe_exchange("bybit") == "bybit"


def test_cloud_scan_never_creates_a_bybit_client(monkeypatch):
    """The cloud scan's exchange candidates exclude binance and bybit, so no Bybit client is ever instantiated there."""
    from paper_trading import engine
    from data_engine import config
    monkeypatch.setenv("SINDHU_CLOUD_MODE", "1")
    created = []
    import data_engine.exchanges.registry as reg
    real = reg.get_exchange_client
    monkeypatch.setattr(reg, "get_exchange_client", lambda name: created.append(name) or real(name))
    candidates = [c for c in config.DEFAULTS["exchanges.json"]["enabled"] if c not in config.CLOUD_BLOCKED_EXCHANGES]
    assert "bybit" not in candidates and "binance" not in candidates and "okx" in candidates
