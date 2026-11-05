import pandas as pd

from data_engine import candle_fingerprint as cf


def frame(close=101.0, n=3):
    idx = pd.date_range("2026-11-05 00:00", periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({"open": [100.0] * n, "high": [102.0] * n, "low": [99.0] * n, "close": [close] * n, "volume": [5.0] * n}, index=idx)


def test_off_by_default_logs_nothing(monkeypatch):
    monkeypatch.delenv("SINDHU_CANDLE_FINGERPRINT", raising=False)
    cf._last.clear(); out = []
    assert cf.note("okx", "BTC/USDT", "15m", frame(), log=out.append) is None and out == []


def test_on_logs_once_per_new_candle_and_is_parseable(monkeypatch):
    monkeypatch.setenv("SINDHU_CANDLE_FINGERPRINT", "1")
    cf._last.clear(); out = []
    cf.note("okx", "BTC/USDT", "15m", frame(), log=out.append)
    cf.note("okx", "BTC/USDT", "15m", frame(), log=out.append)                 # same candle again -> nothing
    cf.note("okx", "ETH/USDT", "15m", frame(), log=out.append)                 # another symbol -> a line
    assert len(out) == 2
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location("cmp", pathlib.Path(__file__).resolve().parents[1] / "tools" / "compare_fingerprints.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    rows = mod.parse("\n".join(out))
    assert rows[0]["symbol"] == "BTCUSDT" and rows[0]["c"] == 101.0 and rows[0]["tf"] == "15m" and len(rows[0]["fp"]) == 12
    res = mod.compare(rows, lambda s, tf, t: (100.0, 102.0, 99.0, 101.0, 5.0) if s == "BTCUSDT" else None)
    assert res[0]["close_bps"] == 0.0 and res[1]["status"] == "no reference"


def test_fingerprint_is_sensitive_and_a_broken_frame_never_raises(monkeypatch):
    assert cf.fingerprint(1, 1, 2, 0.5, 1.5, 9) != cf.fingerprint(1, 1, 2, 0.5, 1.5001, 9)
    monkeypatch.setenv("SINDHU_CANDLE_FINGERPRINT", "1")
    assert cf.note("okx", "X", "1h", pd.DataFrame(), log=lambda s: None) is None
    assert cf.note("okx", "X", "1h", object(), log=lambda s: None) is None
