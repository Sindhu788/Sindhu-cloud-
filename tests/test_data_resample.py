import datetime as dt

import numpy as np
import pytest

from data_platform import resample


def frame(start_iso, minutes, drop=()):
    t0 = int(dt.datetime.fromisoformat(start_iso).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
    idx = [i for i in range(minutes) if i not in drop]
    n = len(idx)
    ot = np.array([t0 + i * 60_000 for i in idx], dtype="int64")
    rng = np.random.default_rng(3)
    close = 100 + np.cumsum(rng.normal(0, 0.1, n))
    open_ = np.concatenate([[100.0], close[:-1]])
    high = np.maximum(open_, close) + rng.random(n) * 0.05
    low = np.minimum(open_, close) - rng.random(n) * 0.05
    return {"open_time": ot, "open": open_, "high": high, "low": low, "close": close, "volume": rng.random(n) + 1,
            "quote_volume": rng.random(n) * 100, "trades": rng.integers(1, 50, n).astype("int32"),
            "taker_buy_base": rng.random(n), "taker_buy_quote": rng.random(n) * 50}


def test_ohlcv_rules_are_exact_for_every_timeframe():
    a = frame("2026-03-02T00:00:00", 7 * 1440)               # Monday 00:00 UTC, one full week
    for tf, k in resample.TIMEFRAMES_MIN.items():
        r = resample.resample(a, tf)
        n = (7 * 1440) // k
        assert len(r["open_time"]) == n
        for j in (0, n - 1):
            sl = slice(j * k, (j + 1) * k)
            assert r["open"][j] == a["open"][sl][0] and r["close"][j] == a["close"][sl][-1]
            assert r["high"][j] == a["high"][sl].max() and r["low"][j] == a["low"][sl].min()
            assert np.isclose(r["volume"][j], a["volume"][sl].sum()) and r["trades"][j] == a["trades"][sl].sum()
            assert r["open_time"][j] == a["open_time"][sl][0]


def test_a_window_with_a_missing_minute_is_dropped_never_filled():
    a = frame("2026-03-02T00:00:00", 120, drop={7})          # minute 7 missing -> 5m window 5..9 and the 15m window 0..14 and 1h window 0 are incomplete
    assert 5 * 60_000 + a["open_time"][0] not in resample.resample(a, "5m")["open_time"]
    assert len(resample.resample(a, "5m")["open_time"]) == 120 // 5 - 1
    assert len(resample.resample(a, "15m")["open_time"]) == 120 // 15 - 1
    assert len(resample.resample(a, "1h")["open_time"]) == 1                                 # only the second hour survives


def test_a_window_with_the_right_count_but_a_gap_inside_is_not_accepted():
    a = frame("2026-03-02T00:00:00", 10)
    a["open_time"] = a["open_time"].copy()
    a["open_time"][4] += 60_000 * 10                          # duplicated-looking jump: same count, not consecutive
    assert len(resample.resample(a, "5m")["open_time"]) <= 1


def test_daily_candles_open_at_00_utc_and_weekly_candles_on_monday():
    a = frame("2026-03-01T22:00:00", 10 * 1440)              # starts on a Sunday evening
    d = resample.resample(a, "1d")
    assert all(dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).hour == 0 for t in d["open_time"])
    w = resample.resample(frame("2026-02-23T00:00:00", 21 * 1440), "1w")                    # 2026-02-23 is a Monday
    days = {dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).strftime("%A") for t in w["open_time"]}
    assert days == {"Monday"} and len(w["open_time"]) == 3
    partial = resample.resample(frame("2026-02-25T00:00:00", 14 * 1440), "1w")             # begins Wednesday: first (partial) week dropped
    assert len(partial["open_time"]) == 1


def test_no_monthly_timeframe_and_empty_input():
    with pytest.raises(ValueError):
        resample.resample(frame("2026-03-02T00:00:00", 60), "1M")
    assert len(resample.resample(frame("2026-03-02T00:00:00", 0), "5m")["open_time"]) == 0
