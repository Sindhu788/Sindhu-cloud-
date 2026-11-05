"""Master plan A4 (P27 + S1): the per-exchange token bucket never exceeds its rate in a burst, halves after a 429/50011 for 10 minutes,
caps parallel requests, and the ccxt client paces through it. Uses a fake clock: no real waiting."""
import threading

from data_engine.exchanges import rate_limit


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def test_burst_never_exceeds_the_configured_rate():
    c = Clock()
    b = rate_limit.Bucket("okx", rate=8.0, burst=8.0, parallel=3, clock=c, sleep=c.sleep)
    starts = []
    for _ in range(200):
        b.take()
        starts.append(c.t)
    # any 1-second window holds at most rate + burst requests; over the whole run the average is <= the rate
    for i, t0 in enumerate(starts):
        in_window = sum(1 for t in starts[i:] if t < t0 + 1.0)
        assert in_window <= 8 + 8
    assert (len(starts) - 8) / starts[-1] <= 8.0 + 1e-6


def test_after_a_rate_limit_answer_the_rate_halves_for_ten_minutes():
    c = Clock()
    b = rate_limit.Bucket("okx", rate=8.0, burst=1.0, parallel=3, clock=c, sleep=c.sleep)
    b.take()
    b.rate_limited()
    assert b.rate() == 4.0 and b.stats()["slowed"]
    t = c.t
    for _ in range(40):
        b.take()
    assert c.t - t >= 40 / 4.0 - 0.3
    c.t += 600
    assert b.rate() == 8.0 and not b.stats()["slowed"]


def test_rate_comes_from_environment(monkeypatch):
    monkeypatch.setenv("SINDHU_RATE_OKX", "5")
    assert rate_limit.Bucket("okx").base_rate == 5.0
    monkeypatch.setenv("SINDHU_RATE_OKX", "nonsense")
    assert rate_limit.Bucket("okx").base_rate == 8.0
    assert rate_limit.Bucket("gate").base_rate == 10.0


def test_parallel_cap():
    b = rate_limit.Bucket("x", rate=1000, parallel=2)
    inside, peak, lock = [0], [0], threading.Lock()
    gate = threading.Event()

    def work():
        with b.parallel:
            with lock:
                inside[0] += 1
                peak[0] = max(peak[0], inside[0])
            gate.wait(0.2)
            with lock:
                inside[0] -= 1

    ths = [threading.Thread(target=work) for _ in range(6)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    assert peak[0] == 2


def test_ccxt_client_goes_through_the_bucket(monkeypatch):
    from data_engine.exchanges import ccxt_client
    rate_limit.reset()
    taken = []
    real = rate_limit.bucket

    def spy(ex_id):
        b = real(ex_id)
        orig = b.take
        b.take = lambda: taken.append(ex_id) or orig()
        return b

    monkeypatch.setattr(rate_limit, "bucket", spy)
    client = ccxt_client.CCXTClient("okx")
    assert client._retry(lambda: 42) == 42
    assert taken == ["okx"]
    rate_limit.reset()
