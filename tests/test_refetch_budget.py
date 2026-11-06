"""Master plan V2 R2 (P27): at most K heavy (full) downloads per scan; the rest wait in refetch_queue for a later scan."""
import pandas as pd
import pytest

from data_engine import live_candles as lc


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    lc.clear_cache()
    lc.refetch_queue.clear()
    lc.set_refetch_budget(None)
    calls = []

    def fake_range(client, symbol, interval, start_ms, end_ms):
        calls.append((symbol, interval))
        step = lc._INTERVAL_MS[interval]
        return [[t, 1.0, 1.0, 1.0, 1.0, 1.0, t + step - 1, 1.0, 1] for t in range(start_ms - start_ms % step, end_ms - step, step)][-50:]

    monkeypatch.setattr(lc, "_fetch_range", fake_range)
    monkeypatch.setattr(lc, "get_exchange_client", lambda ex: object())
    yield calls
    lc.clear_cache()
    lc.refetch_queue.clear()
    lc.set_refetch_budget(None)


NOW = 1_790_000_000_000


def _get(sym, days=20):
    return lc.get_ohlcv_live("okx", sym, "1m", start_ms=NOW - days * 86_400_000, end_ms=NOW)


def test_only_k_cold_series_per_scan_the_rest_are_queued(_clean):
    lc.set_refetch_budget(3)
    got, deferred = [], []
    for s in ["A/USDT", "B/USDT", "C/USDT", "D/USDT", "E/USDT"]:
        try:
            _get(s)
            got.append(s)
        except lc.RefetchDeferred:
            deferred.append(s)
    assert got == ["A/USDT", "B/USDT", "C/USDT"] and deferred == ["D/USDT", "E/USDT"]
    st = lc.refetch_state()
    assert st["queue"] == 2 and st["used_this_scan"] == 3 and st["queued"] == ["D/USDT 1m", "E/USDT 1m"]
    # next scan: the budget resets and the queue drains
    lc.set_refetch_budget(3)
    _get("D/USDT"); _get("E/USDT")
    assert lc.refetch_state()["queue"] == 0


def test_no_limit_means_every_cold_series_downloads(_clean):
    lc.set_refetch_budget(None)
    for s in "ABCDEFG":
        _get(s + "/USDT")
    assert lc.refetch_state()["queue"] == 0


def test_small_windows_do_not_use_the_budget(_clean):
    lc.set_refetch_budget(0)
    df = lc.get_ohlcv_live("okx", "A/USDT", "1h", start_ms=NOW - 10 * 86_400_000, end_ms=NOW)   # 240 candles < 1000
    assert isinstance(df, pd.DataFrame)


def test_deferred_is_a_normal_per_coin_error_not_a_crash(_clean):
    lc.set_refetch_budget(0)
    with pytest.raises(RuntimeError):
        _get("Z/USDT")


def test_engine_gives_the_first_scan_no_limit_then_k(monkeypatch):
    from paper_trading import engine
    monkeypatch.setattr(engine, "_SCANS_FINISHED", 0)
    engine._set_refetch_budget()
    assert lc.refetch_state()["limit"] is None
    monkeypatch.setattr(engine, "_SCANS_FINISHED", 1)
    monkeypatch.setenv("SINDHU_REFETCH_BUDGET", "3")
    engine._set_refetch_budget()
    assert lc.refetch_state()["limit"] == 3


def test_health_details_shows_the_queue():
    from paper_trading import self_check
    d = self_check.details()
    assert "refetch_queue" in d and d["refetch_queue"]["queue"] == 0
    assert "top_coins_cache" in d
