"""Day 5: the Cloud scan stall. Bybit geo-blocks Render with HTTP 403 (reported by ccxt as RateLimitExceeded); the old retry loop slept
30 s per call, for every call, one after the other. These tests reproduce that and prove the fix."""
import threading
import time

import ccxt
import pytest

from data_engine.exchanges import ccxt_client as cc

GEO = ("bybit GET https://api.bybit.com/v5/market/instruments-info?category=spot 403 Forbidden "
       "{error:The Amazon CloudFront distribution is configured to block access from your country}")


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    cc.breaker_reset()
    cc._retry_log_count[0] = 999          # keep the log quiet
    slept = []
    monkeypatch.setattr(cc.time, "sleep", lambda s: slept.append(s))
    yield slept
    cc.breaker_reset()


def _client(exchange_id="bybit"):
    c = cc.CCXTClient.__new__(cc.CCXTClient)
    c.id = exchange_id
    c._tl = threading.local(); c._override = None; c._shared_markets = None; c._markets_lock = threading.Lock(); c._markets_loaded = False
    return c


def old_behaviour_sleep_seconds():
    return sum(2 * a for a in range(1, 6))          # ccxt.RateLimitExceeded is a NetworkError, so the old loop's first branch slept 2+4+6+8+10 = 30 s per geo-blocked call


def test_geo_block_fails_at_once_without_sleeping_and_opens_the_circuit(clean):
    c = _client()
    calls = []

    def blocked():
        calls.append(1)
        raise ccxt.RateLimitExceeded(GEO)

    with pytest.raises(cc.ExchangeUnavailable):
        c._retry(blocked)
    assert len(calls) == 1 and clean == []                       # one attempt, zero seconds slept (old code: 30 s)
    assert old_behaviour_sleep_seconds() == 30
    with pytest.raises(cc.ExchangeUnavailable):
        c._retry(blocked)
    assert len(calls) == 1                                       # circuit open: the exchange is not even asked


def test_circuit_closes_after_the_window(monkeypatch):
    c = _client()
    monkeypatch.setattr(cc, "BREAKER_GEO_SECONDS", 1)
    with pytest.raises(cc.ExchangeUnavailable):
        c._retry(lambda: (_ for _ in ()).throw(ccxt.RateLimitExceeded(GEO)))
    cc._breaker["bybit"]["open_until"] = time.time() - 1
    assert c._retry(lambda: "ok") == "ok"


def test_other_exchanges_are_not_affected_by_one_open_circuit():
    a, b = _client("bybit"), _client("okx")
    with pytest.raises(cc.ExchangeUnavailable):
        a._retry(lambda: (_ for _ in ()).throw(ccxt.RateLimitExceeded(GEO)))
    assert b._retry(lambda: 42) == 42


def test_real_rate_limit_429_still_retries_with_jittered_backoff_and_recovers(clean):
    c = _client("okx")
    n = []

    def flaky():
        n.append(1)
        if len(n) < 3:
            raise ccxt.RateLimitExceeded("okx 50011 Too Many Requests")
        return "ok"

    assert c._retry(flaky) == "ok"
    assert len(n) == 3 and len(clean) == 2
    assert 5 <= clean[0] <= 5 * 1.25 + 0.01 and 10 <= clean[1] <= 10 * 1.25 + 0.01          # 5 s x attempt, +0-25 % jitter


def test_hanging_exchange_is_bounded_by_the_call_budget_and_trips_the_breaker_after_three_calls(clean, monkeypatch):
    monkeypatch.setattr(cc, "CALL_BUDGET_S", 9)
    c = _client("okx")
    for i in range(3):
        with pytest.raises(RuntimeError):
            c._retry(lambda: (_ for _ in ()).throw(ccxt.RequestTimeout("read timed out")))
    assert sum(clean) <= 3 * 9 * 1.3                               # never more than the budget per call
    assert cc.breaker_state("okx")["open_until"] > time.time()     # after 3 failed calls the exchange is left alone for a while
    with pytest.raises(cc.ExchangeUnavailable):
        c._retry(lambda: "never called")


def test_a_success_resets_the_failure_count(clean, monkeypatch):
    monkeypatch.setattr(cc, "CALL_BUDGET_S", 3)
    c = _client("okx")
    for _ in range(2):
        with pytest.raises(RuntimeError):
            c._retry(lambda: (_ for _ in ()).throw(ccxt.RequestTimeout("x")))
    assert c._retry(lambda: 1) == 1
    assert cc.breaker_state("okx")["fails"] == 0


def test_each_thread_gets_its_own_ccxt_instance_and_injected_fakes_still_work(monkeypatch):
    made = []

    class FakeEx:
        def __init__(self, cfg):
            made.append(cfg)
            self.markets = {}

        def set_markets(self, m):
            pass

    monkeypatch.setattr(cc.ccxt, "okx", FakeEx, raising=False)
    c = cc.CCXTClient("okx")
    seen = []
    ts = [threading.Thread(target=lambda: seen.append(c._exchange)) for _ in range(3)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert len({id(o) for o in seen}) == 3 and all(m["timeout"] == cc.REQUEST_TIMEOUT_MS and m["enableRateLimit"] for m in made)
    fake = object()
    c._exchange = fake
    assert c._exchange is fake


def test_market_list_is_loaded_once_and_shared_between_threads(monkeypatch):
    loads = []

    class FakeEx:
        def __init__(self, cfg):
            self.cfg = cfg
            self.markets = None

        def load_markets(self):
            loads.append(1)
            self.markets = {"BTC/USDT": {"symbol": "BTC/USDT"}}

        def set_markets(self, m):
            self.markets = m

    monkeypatch.setattr(cc.ccxt, "okx", FakeEx, raising=False)
    c = cc.CCXTClient("okx")
    seen = []
    ts = [threading.Thread(target=lambda: seen.append(c._exchange)) for _ in range(4)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert len(loads) == 1 and all(o.markets is not None for o in seen)
    assert seen[0].cfg["options"] == {"fetchMarkets": {"types": ["spot"]}}            # OKX: spot only (memory)
