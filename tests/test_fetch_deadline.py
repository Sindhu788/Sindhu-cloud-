"""Master plan A5 (P5): a slow exchange cannot stall a scan. A per-thread download deadline stops the page loop; a cold download keeps
what it already received and the next call resumes after it; the engine sets the deadline per coin; the prefetch phase has a budget."""
import time

import pytest

from data_engine import live_candles

M = 60_000
T0 = 1_790_000_000_000 - (1_790_000_000_000 % M)


class SlowExchange:
    def __init__(self, page_seconds=0.0, page=100):
        self.page_seconds, self.page, self.calls = page_seconds, page, 0

    def get_ohlcv(self, symbol, interval, since_ms=None, limit=1000):
        self.calls += 1
        time.sleep(self.page_seconds)
        rows, t = [], since_ms - since_ms % M
        while t < T0 and len(rows) < self.page:
            rows.append([t, 1.0, 2.0, 0.5, 1.5, 3.0, t + M - 1, 3.0, 1])
            t += M
        return rows


@pytest.fixture
def ex(monkeypatch):
    e = SlowExchange(page_seconds=0.05)
    live_candles.clear_cache()
    monkeypatch.setattr(live_candles, "get_exchange_client", lambda name: e)
    monkeypatch.setattr(live_candles, "REQUEST_DELAY_SECONDS", 0)
    yield e
    live_candles.set_fetch_deadline(None)
    live_candles.clear_cache()


def test_deadline_stops_a_slow_download_and_the_next_call_resumes(ex):
    start = T0 - 3000 * M                                  # 30 pages of 100 rows at 0.05 s = 1.5 s total
    live_candles.set_fetch_deadline(time.monotonic() + 0.3)
    t = time.monotonic()
    with pytest.raises(live_candles.FetchDeadlineExceeded):
        live_candles.get_ohlcv_live("okx", "LTC/USDT", "1m", start, T0)
    assert time.monotonic() - t < 0.8                       # stopped near the deadline, not after all 30 pages
    first_calls = ex.calls
    assert 2 <= first_calls < 30
    live_candles.set_fetch_deadline(None)
    df = live_candles.get_ohlcv_live("okx", "LTC/USDT", "1m", start, T0)
    assert len(df) == 3000 and not df.index.duplicated().any()
    assert ex.calls - first_calls <= 30 - first_calls + 1  # resumed: only the remaining pages, not the whole window again


def test_no_deadline_means_unchanged_behaviour(ex):
    ex.page_seconds = 0.0
    live_candles.set_fetch_deadline(None)
    df = live_candles.get_ohlcv_live("okx", "BTC/USDT", "1m", T0 - 500 * M, T0)
    assert len(df) == 500


def test_deadline_is_per_thread(ex):
    import threading
    live_candles.set_fetch_deadline(time.monotonic() - 1)   # already past, on THIS thread only
    out = {}

    def other():
        out["n"] = len(live_candles.get_ohlcv_live("okx", "ETH/USDT", "1m", T0 - 200 * M, T0))

    th = threading.Thread(target=other)
    th.start(); th.join()
    assert out["n"] == 200
    with pytest.raises(live_candles.FetchDeadlineExceeded):
        live_candles.get_ohlcv_live("okx", "SOL/USDT", "1m", T0 - 200 * M, T0)


def test_engine_sets_a_per_coin_deadline_from_the_budget(monkeypatch):
    from paper_trading import engine
    monkeypatch.setattr(engine, "LIVE_CANDLES_ONLY", True)
    monkeypatch.setenv("SINDHU_COIN_FETCH_BUDGET_S", "42")
    seen = []
    monkeypatch.setattr(live_candles, "set_fetch_deadline", seen.append)
    before = time.monotonic()
    engine._set_coin_fetch_deadline()
    engine._set_coin_fetch_deadline(clear=True)
    assert 41 < seen[0] - before < 43 and seen[1] is None


def test_engine_deadline_is_not_set_outside_live_candle_mode(monkeypatch):
    from paper_trading import engine
    monkeypatch.setattr(engine, "LIVE_CANDLES_ONLY", False)
    seen = []
    monkeypatch.setattr(live_candles, "set_fetch_deadline", seen.append)
    engine._set_coin_fetch_deadline()
    assert seen == []


def test_bad_budget_value_falls_back_to_default(monkeypatch):
    from paper_trading import engine
    monkeypatch.setenv("SINDHU_PREFETCH_BUDGET_S", "abc")
    assert engine._budget_seconds("SINDHU_PREFETCH_BUDGET_S", 600) == 600.0
    monkeypatch.setenv("SINDHU_PREFETCH_BUDGET_S", "-5")
    assert engine._budget_seconds("SINDHU_PREFETCH_BUDGET_S", 600) == 1.0
