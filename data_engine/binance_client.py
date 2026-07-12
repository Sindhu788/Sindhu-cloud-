import time
import requests

from data_engine.config import BINANCE_BASE_URL, MAX_RETRIES

_session = requests.Session()


def _get(path, params=None):
    url = BINANCE_BASE_URL + path
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = _session.get(url, params=params, timeout=15)
        except requests.RequestException:
            time.sleep(2 * attempt)
            continue

        if resp.status_code == 200:
            return resp.json()

        if resp.status_code == 429 or resp.status_code == 418:
            wait = int(resp.headers.get("Retry-After", 5 * attempt))
            time.sleep(wait)
            continue

        if resp.status_code >= 500:
            time.sleep(2 * attempt)
            continue

        resp.raise_for_status()

    raise RuntimeError(f"Failed to GET {path} after {MAX_RETRIES} retries")


def get_ticker_24hr():
    """24h ticker stats for every symbol. Used to rank coins by volume."""
    return _get("/api/v3/ticker/24hr")


def get_exchange_info():
    return _get("/api/v3/exchangeInfo")


def get_klines(symbol, interval, start_time_ms=None, end_time_ms=None, limit=1000):
    """Raw kline rows for a symbol/interval between start_time_ms and end_time_ms (inclusive-ish)."""
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    if start_time_ms is not None:
        params["startTime"] = start_time_ms
    if end_time_ms is not None:
        params["endTime"] = end_time_ms
    return _get("/api/v3/klines", params)
