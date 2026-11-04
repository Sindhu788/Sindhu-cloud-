import threading
import time
import types

import pandas as pd

from data_engine import live_candles as lc


def _fake_rows(n=3):
    base = int(time.time() * 1000) // 3_600_000 * 3_600_000 - n * 3_600_000
    return [(base + i * 3_600_000, 1, 2, 0.5, 1.5, 10, base + i * 3_600_000 + 3_599_999, 15, 5) for i in range(n)]


def test_different_series_download_in_parallel_but_the_same_series_never_twice(monkeypatch):
    lc.clear_cache()
    active, peak, calls = [0], [0], []
    gate = threading.Lock()

    def slow_fetch(client, symbol, interval, start, end):
        with gate:
            active[0] += 1; peak[0] = max(peak[0], active[0]); calls.append((symbol, interval))
        time.sleep(0.15)
        with gate:
            active[0] -= 1
        return _fake_rows()

    monkeypatch.setattr(lc, "_fetch_range", slow_fetch)
    monkeypatch.setattr(lc, "get_exchange_client", lambda ex: object())
    ts = [threading.Thread(target=lc.get_ohlcv_live, args=("okx", s, "1h")) for s in ("A/USDT", "B/USDT", "C/USDT")]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert peak[0] >= 2                       # parallel across series
    calls.clear()
    same = [threading.Thread(target=lc.get_ohlcv_live, args=("okx", "A/USDT", "1h")) for _ in range(4)]
    [t.start() for t in same]; [t.join() for t in same]
    assert len([c for c in calls if c[0] == "A/USDT"]) <= 4 and peak[0] < 6   # warm series: incremental fetches only, never a pile-up
    lc.clear_cache()


def test_prefetch_warms_exactly_the_series_the_loop_will_ask_for_and_swallows_errors(monkeypatch):
    from paper_trading import engine as eng
    import data_engine.resample as rs
    asked, lock = [], threading.Lock()
    monkeypatch.setattr(eng, "LIVE_CANDLES_ONLY", True)
    monkeypatch.setattr(eng.market_state, "classify", lambda ex, sym: None if sym == "BAD/USDT" else {"market_state": "ranging"})
    strat = lambda *tfs: {"config": types.SimpleNamespace(timeframes={f"r{i}": t for i, t in enumerate(tfs)})}
    monkeypatch.setattr(eng.strategy_matcher, "relevant_strategies", lambda sym, st: [strat("1h", "15m"), strat("15m")] if sym != "ERR/USDT" else (_ for _ in ()).throw(RuntimeError("x")))

    def rec(ex, sym, tf, start, end):
        with lock:
            asked.append((sym, tf))
        return pd.DataFrame()

    monkeypatch.setattr(rs, "get_ohlcv", rec)
    e = eng.PaperTradingEngine()
    e._prefetch_candles("okx", ["AAA/USDT", "BBB/USDT", "BAD/USDT", "ERR/USDT"], {"lookback_days": 20})
    assert sorted(asked) == sorted([("AAA/USDT", "1h"), ("AAA/USDT", "15m"), ("BBB/USDT", "1h"), ("BBB/USDT", "15m")])


def test_prefetch_can_be_switched_off_and_is_skipped_without_live_candles(monkeypatch):
    from paper_trading import engine as eng
    import data_engine.resample as rs
    called = []
    monkeypatch.setattr(rs, "get_ohlcv", lambda *a, **k: called.append(a))
    monkeypatch.setattr(eng.market_state, "classify", lambda ex, sym: {"market_state": "ranging"})
    monkeypatch.setattr(eng.strategy_matcher, "relevant_strategies", lambda s, m: [{"config": types.SimpleNamespace(timeframes={"entry": "1h"})}])
    e = eng.PaperTradingEngine()
    monkeypatch.setattr(eng, "LIVE_CANDLES_ONLY", True)
    monkeypatch.setenv("SINDHU_PREFETCH_WORKERS", "0")
    e._prefetch_candles("okx", ["A/USDT", "B/USDT"], {})
    monkeypatch.delenv("SINDHU_PREFETCH_WORKERS")
    monkeypatch.setattr(eng, "LIVE_CANDLES_ONLY", False)
    e._prefetch_candles("okx", ["A/USDT", "B/USDT"], {})
    assert called == []
