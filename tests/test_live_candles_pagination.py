"""Regression: exchanges that cap a request at 100-300 rows must still be paged to the present.
Cloud (OKX, 300 rows/page) stopped after page one and every frame was ~a week stale."""
from data_engine import live_candles as lc

STEP = 3_600_000


class CappedClient:
    """Fake exchange: returns at most `cap` candles starting at since_ms, oldest first."""
    def __init__(self, cap, first_open, last_open):
        self.cap, self.first_open, self.last_open, self.calls = cap, first_open, last_open, 0

    def get_ohlcv(self, symbol, interval, since_ms=None, limit=1000):
        self.calls += 1
        t = max(since_ms or self.first_open, self.first_open)
        rows = []
        while t <= self.last_open and len(rows) < min(self.cap, limit):
            rows.append([t, 1.0, 2.0, 0.5, 1.5, 10.0, t + STEP - 1, 15.0, 1])
            t += STEP
        return rows


def test_range_fetch_reaches_now_even_when_the_exchange_caps_pages_at_300(monkeypatch):
    monkeypatch.setattr(lc, "REQUEST_DELAY_SECONDS", 0)
    start = 1_700_000_000_000 - (1_700_000_000_000 % STEP)
    last = start + 999 * STEP                                   # 1000 hourly candles available
    client = CappedClient(300, start, last)
    rows = lc._fetch_range(client, "ZRO/USDT", "1h", start, last + STEP)
    assert rows[0][0] == start and rows[-1][0] == last and len(rows) == 1000
    assert client.calls >= 4                                    # 300 + 300 + 300 + 100


def test_range_fetch_stops_when_the_cursor_does_not_advance(monkeypatch):
    monkeypatch.setattr(lc, "REQUEST_DELAY_SECONDS", 0)

    class Stuck:
        calls = 0
        def get_ohlcv(self, symbol, interval, since_ms=None, limit=1000):
            Stuck.calls += 1
            return [[1_000_000, 1, 1, 1, 1, 1, 0, 0, 0]]        # always the same old candle

    rows = lc._fetch_range(Stuck(), "X/USDT", "1h", 0, 10 * STEP)
    assert Stuck.calls <= 3 and len(rows) >= 1
