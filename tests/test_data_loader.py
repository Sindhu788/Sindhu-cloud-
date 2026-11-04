import datetime as dt
import os

import numpy as np
import pytest

pytest.importorskip("pyarrow")
pd = pytest.importorskip("pandas")

from data_platform import downloader, loader, store  # noqa: E402


def ms(s):
    return int(dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def make(root, symbol, period, kind="month"):
    """Write one finished month (or day) of synthetic 1m candles through the real store + manifest."""
    if kind == "month":
        t0, n = ms(period + "-01T00:00:00"), downloader.expected_minutes_month(period)
        path = store.month_path("binance", symbol, period, root)
    else:
        t0, n = ms(period + "T00:00:00"), 1440
        path = store.day_path("binance", symbol, period, root)
    ot = t0 + np.arange(n, dtype="int64") * 60_000
    base = 100 + np.sin(ot / 3e7)
    arr = {"open_time": ot, "open": base, "high": base + 0.5, "low": base - 0.5, "close": base + 0.1, "volume": np.ones(n), "quote_volume": np.ones(n) * 100,
           "trades": np.ones(n, dtype="int32"), "taker_buy_base": np.ones(n), "taker_buy_quote": np.ones(n)}
    rows, sha = store.write_atomic(path, store.table_from_arrays(arr))
    downloader.Manifest(root).put(f"{symbol}/{period}", {"status": "ok", "rows": rows, "sha256": sha})


@pytest.fixture
def root(tmp_path):
    r = str(tmp_path)
    for m in ("2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"):
        make(r, "AAAUSDT", m)
    make(r, "AAAUSDT", "2026-11-01", kind="day")
    return r


def test_holdout_is_the_last_two_complete_months_and_is_fixed_once(root):
    L = loader.CandleLoader(root)
    assert L.protocol["holdout_first_month"] == "2026-09" and L.holdout_start_ms == ms("2026-09-01T00:00:00")
    make(root, "AAAUSDT", "2026-11")           # even if more data arrives later the boundary does not move
    assert loader.CandleLoader(root).holdout_start_ms == ms("2026-09-01T00:00:00")


def test_default_window_stops_at_the_holdout_and_explicit_overreach_is_refused(root):
    L = loader.CandleLoader(root)
    df = L.load("AAAUSDT", "1h")
    assert df.index[-1] < pd.Timestamp("2026-09-01", tz="UTC") and df.index[0] == pd.Timestamp("2026-05-01", tz="UTC")
    with pytest.raises(loader.HoldoutAccessError):
        L.load("AAAUSDT", "1h", end="2026-10-15T00:00:00")
    with pytest.raises(loader.HoldoutAccessError):
        L.load("AAAUSDT", "5m", start="2026-09-10T00:00:00", end="2026-09-11T00:00:00")
    with pytest.raises(loader.HoldoutAccessError):
        L.load("AAAUSDT", "1h", end="2026-10-15T00:00:00", allow_final_exam=True)         # flag alone is not enough: the phrase is required too
    assert L.holdout_access_count() == 0


def test_final_exam_needs_the_flag_and_the_phrase_and_every_look_is_logged(root, monkeypatch):
    L = loader.CandleLoader(root)
    monkeypatch.setenv("SINDHU_FINAL_EXAM", loader.FINAL_EXAM_PHRASE)
    df = L.load("AAAUSDT", "1h", start="2026-09-05T00:00:00", end="2026-09-06T00:00:00", allow_final_exam=True, who="exam-test")
    assert len(df) == 24 and df.attrs["holdout_touched"] is True and L.holdout_access_count() == 1
    L.load("AAAUSDT", "1h", start="2026-09-05T00:00:00", end="2026-09-06T00:00:00", allow_final_exam=True)
    assert L.holdout_access_count() == 2


def test_a_candle_is_invisible_until_it_has_closed(root):
    L = loader.CandleLoader(root)
    t = ms("2026-06-10T10:00:00")
    for tf, k in (("1m", 1), ("5m", 5), ("1h", 60)):
        before = L.load("AAAUSDT", tf, start="2026-06-10T00:00:00", end="2026-06-11T00:00:00", as_of_ms=t + k * 60_000 - 1)
        after = L.load("AAAUSDT", tf, start="2026-06-10T00:00:00", end="2026-06-11T00:00:00", as_of_ms=t + k * 60_000)
        stamp = pd.Timestamp(dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc))
        assert stamp not in before.index and stamp in after.index, tf
        assert after.index.max() == stamp


def test_resampled_candles_equal_the_one_minute_rules_and_carry_a_data_version(root):
    L = loader.CandleLoader(root)
    m1 = L.load("AAAUSDT", "1m", start="2026-06-03T00:00:00", end="2026-06-03T06:00:00")
    h1 = L.load("AAAUSDT", "1h", start="2026-06-03T00:00:00", end="2026-06-03T06:00:00")
    assert len(m1) == 360 and len(h1) == 6
    assert h1["open"].iloc[0] == m1["open"].iloc[0] and h1["close"].iloc[0] == m1["close"].iloc[59]
    assert h1["high"].iloc[0] == m1["high"].iloc[:60].max() and h1["volume"].iloc[0] == 60
    assert h1.attrs["data_version"] == m1.attrs["data_version"] and len(h1.attrs["data_version"]) == 16
    assert list(h1.columns) == loader.OUT_COLUMNS and str(h1.index.tz) == "UTC"


def test_data_version_changes_when_the_data_changes(root):
    v1 = loader.CandleLoader(root).data_version()
    make(root, "BBBUSDT", "2026-05")
    assert loader.CandleLoader(root).data_version() != v1


def test_daily_files_are_used_only_for_months_without_a_monthly_file(root):
    L = loader.CandleLoader(root)
    months = L._months_for("AAAUSDT", ms("2026-10-31T00:00:00"), ms("2026-11-03T00:00:00"))
    assert [p for p, *_ in months] == ["2026-10", "2026-11-01"]
    make(root, "AAAUSDT", "2026-11")
    months = loader.CandleLoader(root)._months_for("AAAUSDT", ms("2026-10-31T00:00:00"), ms("2026-11-03T00:00:00"))
    assert [p for p, *_ in months] == ["2026-10", "2026-11"]
