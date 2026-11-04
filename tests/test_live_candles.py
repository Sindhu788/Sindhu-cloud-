"""data_engine/live_candles.py -- the direct-from-exchange OHLCV source the
lightweight cloud runner uses instead of the klines_1m-backed database path.

Uses a fake exchange client (no real network calls) so this suite stays
fast and deterministic. The module WAS also verified against the real
Binance API by hand during development (single-page fetch, incremental
cache hit, and 5-page pagination all confirmed against live data -- see
DEPLOYMENT_CHECKPOINT.md) -- that network-dependent verification is
recorded there rather than re-run automatically on every test run.
"""

import pandas as pd
import pytest

from data_engine import live_candles


class _FakeClient:
    """Mimics ExchangeClient.get_ohlcv()'s REAL shape as discovered against
    live Binance data: raw rows can carry MORE than the 9 fields the rest
    of the codebase standardizes on (Binance's raw kline has 12) -- this
    fake deliberately includes those extra trailing fields so a test
    regresses immediately if _normalize_row's slicing is ever removed."""

    def __init__(self, candles_by_symbol):
        self.candles_by_symbol = candles_by_symbol
        self.calls = []

    def get_ohlcv(self, symbol, interval, since_ms=None, limit=1000):
        self.calls.append((symbol, interval, since_ms, limit))
        rows = self.candles_by_symbol.get(symbol, [])
        page = [r for r in rows if r[0] >= (since_ms or 0)][:limit]
        return page


def _make_candles(start_ms, count, interval_ms, price=100.0):
    rows = []
    for i in range(count):
        t = start_ms + i * interval_ms
        # 12 raw fields, matching real Binance's kline response shape --
        # the trailing 3 (taker_buy_base, taker_buy_quote, ignore) must
        # never reach the output dataframe.
        rows.append((t, price, price + 1, price - 1, price, 10.0, t + interval_ms - 1,
                     1000.0, 5, 0.0, 0.0, "0"))
    return rows


@pytest.fixture(autouse=True)
def _clear_cache_and_client(monkeypatch):
    live_candles.clear_cache()
    yield
    live_candles.clear_cache()


def test_normalize_row_slices_and_casts_exactly_like_storage_insert_klines():
    """Must match data_engine.storage.insert_klines's own r[0]..r[8]
    slice+cast exactly -- that function already proves this is the right
    shape for _rows_to_df, so a live-fetched row must be indistinguishable
    from a stored one once normalized."""
    raw = (1000, "1.5", "2.5", "0.5", "1.8", "10.25", 1059, "100.5", "7", "extra1", "extra2", "extra3")
    normalized = live_candles._normalize_row(raw)
    assert normalized == (1000, 1.5, 2.5, 0.5, 1.8, 10.25, 1059, 100.5, 7)
    assert len(normalized) == 9


def test_single_page_fetch_returns_correct_shape(monkeypatch):
    interval_ms = 15 * 60_000
    start = 1_700_000_000_000
    candles = _make_candles(start, 20, interval_ms)
    client = _FakeClient({"BTCUSDT": candles})
    monkeypatch.setattr(live_candles, "get_exchange_client", lambda ex: client)

    df = live_candles.get_ohlcv_live("binance", "BTCUSDT", "15m",
                                      start_ms=start, end_ms=start + 20 * interval_ms)
    assert list(df.columns) == ["open", "high", "low", "close", "volume", "quote_volume", "trades"]
    assert len(df) == 20
    assert str(df.index.tz) == "UTC"


def test_incremental_refresh_only_requests_new_candles(monkeypatch):
    """The whole point of the in-memory cache: a second call for the same
    (exchange, symbol, interval) must not re-fetch the whole history --
    only whatever is newer than what's already cached."""
    interval_ms = 60_000
    start = 1_700_000_000_000
    candles = _make_candles(start, 100, interval_ms)
    client = _FakeClient({"ETHUSDT": candles})
    monkeypatch.setattr(live_candles, "get_exchange_client", lambda ex: client)

    # end_ms is inclusive (matches data_engine.resample's own [start, end]
    # convention), so candle #50 (open_time == end1 exactly) is the 51st
    # row returned.
    end1 = start + 50 * interval_ms
    df1 = live_candles.get_ohlcv_live("binance", "ETHUSDT", "1m", start_ms=start, end_ms=end1)
    assert len(df1) == 51
    first_call_count = len(client.calls)

    end2 = start + 99 * interval_ms
    df2 = live_candles.get_ohlcv_live("binance", "ETHUSDT", "1m", start_ms=start, end_ms=end2)
    assert len(df2) == 100
    # A fresh (uncached) fetch of this same range would need pagination
    # calls proportional to the FULL history; the incremental path issues
    # far fewer since only "since last cached candle" is requested.
    assert len(client.calls) - first_call_count <= 2


def test_pagination_stitches_multiple_pages_into_one_series(monkeypatch):
    """Binance caps a single response at 1000 rows -- a request for more
    than that must transparently issue multiple page requests and combine
    them into one continuous series, exactly like the local downloader's
    own incremental-fetch loop does."""
    interval_ms = 60_000
    start = 1_700_000_000_000
    total = 2500  # needs 3 pages at limit=1000
    candles = _make_candles(start, total, interval_ms)
    client = _FakeClient({"BTCUSDT": candles})
    monkeypatch.setattr(live_candles, "get_exchange_client", lambda ex: client)
    monkeypatch.setattr(live_candles, "_PAGE_LIMIT", 1000)

    end = start + total * interval_ms
    df = live_candles.get_ohlcv_live("binance", "BTCUSDT", "1m", start_ms=start, end_ms=end)
    assert len(df) == total
    assert df.index.is_monotonic_increasing
    assert not df.index.has_duplicates
    assert len(client.calls) >= 3


def test_unsupported_interval_raises_a_clear_error(monkeypatch):
    client = _FakeClient({})
    monkeypatch.setattr(live_candles, "get_exchange_client", lambda ex: client)
    with pytest.raises(ValueError):
        live_candles.get_ohlcv_live("binance", "BTCUSDT", "10m", start_ms=0, end_ms=1)


def test_no_candles_available_returns_empty_dataframe_with_correct_columns(monkeypatch):
    client = _FakeClient({"BTCUSDT": []})
    monkeypatch.setattr(live_candles, "get_exchange_client", lambda ex: client)
    df = live_candles.get_ohlcv_live("binance", "BTCUSDT", "1h", start_ms=0, end_ms=10_000_000)
    assert df.empty
    assert list(df.columns) == ["open", "high", "low", "close", "volume", "quote_volume", "trades"]


def test_old_rows_are_trimmed_beyond_max_retention(monkeypatch):
    interval_ms = 86_400_000  # 1d candles
    start = 1_700_000_000_000
    # 40 days of daily candles -- more than _MAX_RETENTION_DAYS (25)
    candles = _make_candles(start, 40, interval_ms)
    client = _FakeClient({"BTCUSDT": candles})
    monkeypatch.setattr(live_candles, "get_exchange_client", lambda ex: client)

    end = start + 40 * interval_ms
    live_candles.get_ohlcv_live("binance", "BTCUSDT", "1d", start_ms=None, end_ms=end)    # default window = _MAX_RETENTION_DAYS
    cached = live_candles._cache[("binance", "BTCUSDT", "1d")]
    span_days = (cached.index.max() - cached.index.min()).days
    assert span_days <= live_candles._MAX_RETENTION_DAYS


def test_a_long_lookback_is_kept_and_downloaded_only_once(monkeypatch):
    """The higher-timeframe filter asks for 90 days of 1h candles on every candidate: that must not re-download 90 days each time."""
    interval_ms = 3_600_000
    now = 1_800_000_000_000
    first = now - 90 * 86_400_000
    candles = _make_candles(first, 90 * 24 + 1, interval_ms)
    client = _FakeClient({"BTCUSDT": candles})
    monkeypatch.setattr(live_candles, "get_exchange_client", lambda ex: client)
    full_fetches = []
    real = live_candles._fetch_range

    def spy(c, symbol, interval, start, end):
        full_fetches.append(start)
        return real(c, symbol, interval, start, end)

    monkeypatch.setattr(live_candles, "_fetch_range", spy)
    for _ in range(4):
        df = live_candles.get_ohlcv_live("binance", "BTCUSDT", "1h", start_ms=first, end_ms=now)
        assert len(df) >= 90 * 24
    assert full_fetches.count(first) == 1                 # one full download; the other three calls only look for newer candles
    span_days = (live_candles._cache[("binance", "BTCUSDT", "1h")].index.max() - live_candles._cache[("binance", "BTCUSDT", "1h")].index.min()).days
    assert 85 <= span_days <= live_candles._MAX_KEEP_DAYS


def test_a_coin_with_less_history_than_asked_is_not_re_downloaded_forever(monkeypatch):
    interval_ms = 86_400_000
    now = 1_800_000_000_000
    candles = _make_candles(now - 40 * interval_ms, 41, interval_ms)       # listed 40 days ago
    client = _FakeClient({"NEWUSDT": candles})
    monkeypatch.setattr(live_candles, "get_exchange_client", lambda ex: client)
    starts = []
    real = live_candles._fetch_range
    monkeypatch.setattr(live_candles, "_fetch_range", lambda c, s, i, st, en: starts.append(st) or real(c, s, i, st, en))
    ask = now - 365 * interval_ms
    for _ in range(3):
        live_candles.get_ohlcv_live("binance", "NEWUSDT", "1d", start_ms=ask, end_ms=now)
    assert starts.count(ask) == 1


def test_keep_window_never_exceeds_the_hard_bound(monkeypatch):
    interval_ms = 86_400_000
    now = 1_800_000_000_000
    candles = _make_candles(now - 700 * interval_ms, 701, interval_ms)
    client = _FakeClient({"OLDUSDT": candles})
    monkeypatch.setattr(live_candles, "get_exchange_client", lambda ex: client)
    live_candles.get_ohlcv_live("binance", "OLDUSDT", "1d", start_ms=now - 700 * interval_ms, end_ms=now)
    cached = live_candles._cache[("binance", "OLDUSDT", "1d")]
    assert (cached.index.max() - cached.index.min()).days <= live_candles._MAX_KEEP_DAYS


def test_same_series_is_not_re_requested_within_15_seconds(monkeypatch):
    interval_ms = 60_000
    now = 1_800_000_000_000
    candles = _make_candles(now - 30 * interval_ms, 31, interval_ms)
    client = _FakeClient({"BTCUSDT": candles})
    monkeypatch.setattr(live_candles, "get_exchange_client", lambda ex: client)
    calls = []
    real = live_candles._fetch_range
    monkeypatch.setattr(live_candles, "_fetch_range", lambda c, s, i, st, en: calls.append(st) or real(c, s, i, st, en))
    for _ in range(6):
        live_candles.get_ohlcv_live("binance", "BTCUSDT", "1m", start_ms=now - 30 * interval_ms, end_ms=now)
    assert len(calls) <= 2          # 1 full download (+ at most 1 refresh), not 6 requests
