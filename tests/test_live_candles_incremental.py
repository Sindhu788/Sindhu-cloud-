"""Master plan A2 (P3): incremental candle fetch. A fake exchange (no network) serves a synthetic 1m series whose newest candle is
still forming (its close moves with the clock). Checks: a second scan downloads at most 2 pages per series; a caller that needs a
longer window gets ONLY the missing older segment; a candle cached while forming gets its final values once it has closed; counters."""
import pytest

from data_engine import live_candles

M = 60_000
T0 = 1_790_000_000_000 - (1_790_000_000_000 % M)        # aligned minute


class FakeExchange:
    def __init__(self):
        self.now = T0
        self.calls = []                                   # (since_ms, n_rows)

    def _row(self, t):
        base = 100.0 + (t - T0) / M * 0.01
        if t + M > self.now:                              # forming: close/high depend on how far into the minute we are
            frac = (self.now - t) / M
            return [t, base, base + frac, base - 0.5, base + frac / 2, 1.0, t + M - 1, 1.0, 1]
        return [t, base, base + 1.0, base - 0.5, base + 0.5, 10.0, t + M - 1, 10.0, 5]

    def get_ohlcv(self, symbol, interval, since_ms=None, limit=1000):
        start = max(since_ms, T0 - 40 * 1440 * M)
        start = start - (start % M) + (M if start % M else 0)
        rows, t = [], start
        while t <= self.now and len(rows) < limit:
            rows.append(self._row(t))
            t += M
        self.calls.append((since_ms, len(rows)))
        return rows


@pytest.fixture
def fake(monkeypatch):
    ex = FakeExchange()
    live_candles.clear_cache()
    monkeypatch.setattr(live_candles, "get_exchange_client", lambda name: ex)
    monkeypatch.setattr(live_candles, "REQUEST_DELAY_SECONDS", 0)
    yield ex
    live_candles.clear_cache()


def test_second_scan_downloads_at_most_two_pages(fake):
    fake.now = T0 + 30 * M + 10_000
    start = T0 - 3 * 1440 * M
    live_candles.get_ohlcv_live("binance", "BTC/USDT", "1m", start, fake.now)
    cold_calls = len(fake.calls)
    assert cold_calls >= 4                                 # 3 days of 1m at 1000 rows per page
    fake.calls.clear()
    fake.now += 5 * M                                       # next scan, 5 minutes later
    df = live_candles.get_ohlcv_live("binance", "BTC/USDT", "1m", start, fake.now)
    assert 1 <= len(fake.calls) <= 2, fake.calls
    assert df.index.max().value // 1_000_000 == fake.now - fake.now % M      # newest (forming) candle present


def test_a_longer_window_backfills_only_the_missing_older_segment(fake):
    fake.now = T0 + 10_000
    short = T0 - 3 * 1440 * M
    long_ = T0 - 20 * 1440 * M
    live_candles.get_ohlcv_live("binance", "LTC/USDT", "1m", short, fake.now)
    fake.calls.clear()
    before = live_candles.fetch_stats_snapshot()
    df = live_candles.get_ohlcv_live("binance", "LTC/USDT", "1m", long_, fake.now)
    d = live_candles.fetch_stats_delta(before)
    assert d["backfill"] == 1 and d["cold"] == 0
    first_since = fake.calls[0][0]
    assert first_since == long_                             # starts at the new, older start ...
    rows_older = sum(n for _, n in fake.calls)
    assert rows_older <= 17 * 1440 + 1000                  # ... and stops near where the cache began (not 20 days again)
    assert df.index.min().value // 1_000_000 == long_
    assert not df.index.duplicated().any() and df.index.is_monotonic_increasing
    assert len(df) == 20 * 1440 + 1                         # complete, no gap between the two segments
    fake.calls.clear()
    live_candles.get_ohlcv_live("binance", "LTC/USDT", "1m", long_, fake.now)
    assert sum(n for _, n in fake.calls) <= 2               # third call: covered, nothing re-downloaded


def test_a_candle_cached_while_forming_gets_its_final_values_after_it_closes(fake):
    fake.now = T0 + 20_000                                  # 20 s into minute T0
    start = T0 - 60 * M
    df = live_candles.get_ohlcv_live("binance", "ETH/USDT", "1m", start, fake.now)
    partial = df.loc[df.index.max()]
    assert partial["volume"] == 1.0                          # stored while forming
    fake.now = T0 + 2 * M + 5_000                           # minute T0 has closed (and T0+1 too)
    df = live_candles.get_ohlcv_live("binance", "ETH/USDT", "1m", start, fake.now)
    import pandas as pd
    final = df.loc[pd.to_datetime(T0, unit="ms", utc=True)]
    assert final["volume"] == 10.0 and final["high"] == partial["open"] + 1.0
    assert not df.index.duplicated().any()


def test_no_request_while_the_newest_candle_is_still_forming(fake):
    fake.now = T0 + 5_000
    start = T0 - 30 * M
    live_candles.get_ohlcv_live("binance", "SOL/USDT", "1m", start, fake.now)
    fake.calls.clear()
    fake.now = T0 + 40_000                                  # same minute: nothing new can exist yet
    live_candles.get_ohlcv_live("binance", "SOL/USDT", "1m", start, fake.now)
    assert fake.calls == []


def test_fetch_counters_count_pages_and_rows(fake):
    fake.now = T0 + 1_000
    before = live_candles.fetch_stats_snapshot()
    live_candles.get_ohlcv_live("binance", "XRP/USDT", "1m", T0 - 2500 * M, fake.now)
    d = live_candles.fetch_stats_delta(before)
    assert d["cold"] == 1 and d["requests"] == len(fake.calls) and d["rows"] == 2501
