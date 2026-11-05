import os
import random
import threading
import time

import ccxt

from data_engine.exchanges.base import ExchangeClient
from data_engine.config import MAX_RETRIES


_retry_log_count = [0]


def _log_retry(exchange_id, attempt, err, sleep_s):
    """Diagnosis (Day 4): every retry used to be silent, so a scan stuck in backoff looked like 'nothing happens'. One short line per
    retry (first 200 chars of the public exchange error, no credentials are ever in these errors), at most 300 lines per process."""
    if _retry_log_count[0] >= 300:
        return
    try:                                      # master plan A4/S1: the same exchange + error type at most once a minute (with a count)
        from paper_trading import log_dedup
        ok, suppressed = log_dedup.should_log(f"exchange-retry:{exchange_id}", err, every=60)
        if not ok:
            return
    except Exception:
        suppressed = 0
    _retry_log_count[0] += 1
    if suppressed:
        print(f"[exchange-retry] {exchange_id}: {suppressed} more retries of this error in the last minute", flush=True)
    print(f"[exchange-retry] {exchange_id} attempt {attempt}/{MAX_RETRIES} {type(err).__name__}: {str(err)[:200]!r} - sleeping {sleep_s}s", flush=True)


# ------------------------------------------------------------------ circuit breaker (Day 5)
# Root cause of the Cloud scan stalls (Render log, 4 Nov 2026): Bybit answers every request from Render with HTTP 403 "The Amazon
# CloudFront distribution is configured to block access from your country". ccxt reports that as RateLimitExceeded, so the old
# retry loop slept 2+4+6+8+10 s (30 s) for EVERY call to Bybit, and the confluence gate (telegram_bot, exchanges.json "default" =
# bybit on Cloud) made such calls for every signal, one after the other. A geo-block is not temporary: fail at once and remember it.
GEO_BLOCK_MARKERS = ("block access from your country", "restricted location", " 451 ", "451 unavailable", "geo")
BREAKER_GEO_SECONDS = int(os.environ.get("SINDHU_BREAKER_GEO_SECONDS", "900"))
BREAKER_FAIL_SECONDS = int(os.environ.get("SINDHU_BREAKER_FAIL_SECONDS", "120"))
BREAKER_AFTER_FAILURES = 3
REQUEST_TIMEOUT_MS = int(os.environ.get("SINDHU_EXCHANGE_TIMEOUT_MS", "10000"))
CALL_BUDGET_S = float(os.environ.get("SINDHU_EXCHANGE_CALL_BUDGET_S", "45"))
_breaker_lock = threading.Lock()
_breaker = {}          # exchange id -> {"open_until": ts, "fails": n, "why": str}


class ExchangeUnavailable(RuntimeError):
    """Raised at once (no waiting) while an exchange's circuit is open."""


def breaker_state(exchange_id):
    with _breaker_lock:
        st = _breaker.get(exchange_id)
        return dict(st) if st else {"open_until": 0.0, "fails": 0, "why": ""}


def breaker_reset(exchange_id=None):
    with _breaker_lock:
        if exchange_id is None:
            _breaker.clear()
        else:
            _breaker.pop(exchange_id, None)


def _breaker_open(exchange_id, seconds, why):
    with _breaker_lock:
        st = _breaker.setdefault(exchange_id, {"open_until": 0.0, "fails": 0, "why": ""})
        st["open_until"] = time.time() + seconds
        st["why"] = why
    print(f"[exchange-breaker] {exchange_id} OPEN for {seconds}s: {why[:160]}", flush=True)


def _is_geo_block(err):
    t = str(err).lower()
    return any(m in t for m in GEO_BLOCK_MARKERS if m != "geo") or ("403" in t and "forbidden" in t and "country" in t)


def _jitter(seconds):
    return seconds * (1.0 + random.uniform(0.0, 0.25))


class CCXTClient(ExchangeClient):
    """Generic exchange client backed by the ccxt library. Works for any
    ccxt exchange id (okx, bybit, bitget, gate, ...) using only public
    endpoints -- no API keys needed for OHLCV history.

    ccxt's unified fetch_ohlcv only returns (timestamp, open, high, low,
    close, volume) -- it doesn't expose close_time/quote_volume/trade count
    the way Binance's raw REST klines do. Those three fields are
    approximated here (close_time from the timeframe's duration,
    quote_volume from volume*close, trades left at 0) so the shared storage
    schema still applies across every exchange; Binance itself still stores
    exact values via its own adapter.
    """

    def __init__(self, exchange_id):
        self.id = exchange_id
        self._tl = threading.local()       # one ccxt instance per thread: a ccxt object (session, rate-limit clock) is not thread-safe
        self._override = None              # tests / callers may inject a fake exchange object
        self._shared_markets = None
        self._markets_lock = threading.Lock()
        self._markets_loaded = False

    @property
    def _exchange(self):
        if self._override is not None:
            return self._override
        ex = getattr(self._tl, "ex", None)
        if ex is None:
            cfg = {"enableRateLimit": True, "timeout": REQUEST_TIMEOUT_MS}
            if self.id == "okx":
                cfg["options"] = {"fetchMarkets": {"types": ["spot"]}}      # we only trade spot: OKX otherwise also loads swaps/futures/options (~100 MB per instance)
            ex = getattr(ccxt, self.id)(cfg)
            with self._markets_lock:                              # ONE thread loads the market list; the others reuse it (Day 5: 4 prefetch
                if self._shared_markets is None:                  # threads each loading their own copy pushed Cloud memory to 464 of 512 MB)
                    try:
                        ex.load_markets()
                        self._shared_markets = ex.markets
                    except Exception:
                        pass
                elif self._shared_markets:
                    try:
                        ex.set_markets(self._shared_markets)
                    except Exception:
                        pass
            self._tl.ex = ex
        return ex

    @_exchange.setter
    def _exchange(self, value):
        self._override = value

    def _ensure_markets(self):
        if not self._markets_loaded:
            self._retry(self._exchange.load_markets)
            try:
                self._shared_markets = self._exchange.markets
            except Exception:
                pass
            self._markets_loaded = True

    def _retry(self, fn, *args, **kwargs):
        st = breaker_state(self.id)
        if st["open_until"] > time.time():
            raise ExchangeUnavailable(f"{self.id}: circuit open for another {int(st['open_until'] - time.time())}s ({st['why'][:80]})")
        last_err = None
        started = time.monotonic()
        waited = 0.0
        from data_engine.exchanges import rate_limit
        pacer = rate_limit.bucket(self.id)
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                pacer.take()                                   # master plan A4: token bucket per exchange
                with pacer.parallel:                           # and at most N requests in flight per exchange
                    result = fn(*args, **kwargs)
                with _breaker_lock:
                    if self.id in _breaker:
                        _breaker[self.id]["fails"] = 0
                return result
            except (ccxt.NetworkError, ccxt.ExchangeNotAvailable, ccxt.RequestTimeout, ccxt.RateLimitExceeded) as e:
                last_err = e
                if _is_geo_block(e):            # permanent for this IP: no retries, remember it
                    _breaker_open(self.id, BREAKER_GEO_SECONDS, f"geo-block: {str(e)[:120]}")
                    raise ExchangeUnavailable(f"{self.id}: blocked from this location ({str(e)[:80]!r})")
                if isinstance(e, ccxt.RateLimitExceeded) or "50011" in str(e) or "Too Many Requests" in str(e):
                    pacer.rate_limited()                       # master plan A4/S1: half the request rate for 10 minutes
                base = 5 * attempt if isinstance(e, ccxt.RateLimitExceeded) else 2 * attempt
                wait = _jitter(base)
                if max(time.monotonic() - started, waited) + wait > CALL_BUDGET_S:        # bounded total time per call
                    break
                _log_retry(self.id, attempt, e, round(wait, 1))
                time.sleep(wait)
                waited += wait
        with _breaker_lock:
            stt = _breaker.setdefault(self.id, {"open_until": 0.0, "fails": 0, "why": ""})
            stt["fails"] += 1
            tripped = stt["fails"] >= BREAKER_AFTER_FAILURES
        if tripped:
            _breaker_open(self.id, BREAKER_FAIL_SECONDS, f"{BREAKER_AFTER_FAILURES} calls in a row failed: {last_err!r}")
        raise RuntimeError(f"{self.id}: request failed after {MAX_RETRIES} retries: {last_err!r}")

    def get_tradeable_symbols(self, quote):
        self._ensure_markets()
        result = {}
        for market in self._exchange.markets.values():
            if not market.get("spot"):
                continue
            if market.get("quote") != quote:
                continue
            if market.get("active") is False:
                continue
            result[market["base"]] = market["symbol"]
        return result

    def get_ohlcv(self, symbol, interval, since_ms=None, limit=1000):
        raw = self._retry(
            self._exchange.fetch_ohlcv, symbol, timeframe=interval, since=since_ms, limit=limit
        )
        if not raw:
            return []

        duration_ms = ccxt.Exchange.parse_timeframe(interval) * 1000
        rows = []
        for open_time, o, h, l, c, v in raw:
            close_time = open_time + duration_ms - 1
            quote_volume = (v or 0.0) * (c or 0.0)
            rows.append((open_time, o, h, l, c, v or 0.0, close_time, quote_volume, 0))
        return rows

    def get_tickers(self, quote):
        # Bug fix, 2026-09-07 (found while switching the cloud default to
        # bybit for the Binance-451 fix): fetch_tickers() with NO symbols
        # argument returns whatever market type the exchange treats as its
        # own default -- confirmed live on bybit, that default is
        # PERPETUAL FUTURES (keys like "BTC/USDT:USDT"), not spot, even
        # though get_tradeable_symbols() above correctly filters to spot-
        # only markets. The old code's `symbol.endswith(f"/{quote}")`
        # check then matched ZERO of those keys (a perp key ends with
        # ":USDT", not "/USDT"), so this silently returned an EMPTY dict
        # on bybit -- no error, just no live prices, which is exactly the
        # shape of bug that shows up as a dashboard stuck on empty/loading
        # placeholders. Fixed by explicitly requesting only real spot
        # symbols (same market.get("spot") filter as get_tradeable_symbols
        # above) instead of trusting fetch_tickers()'s un-scoped default.
        self._ensure_markets()
        spot_symbols = [
            m["symbol"] for m in self._exchange.markets.values()
            if m.get("spot") and m.get("quote") == quote and m.get("active") is not False
        ]
        if not spot_symbols:
            return {}
        raw = self._retry(self._exchange.fetch_tickers, spot_symbols)
        result = {}
        for symbol, t in raw.items():
            if not symbol.endswith(f"/{quote}"):
                continue
            result[symbol] = {
                "price": t.get("last"),
                "change_pct": t.get("percentage"),
                "volume": t.get("quoteVolume"),
            }
        return result
