"""Candle fingerprint logger (Day 6 Step 15). OFF by default (SINDHU_CANDLE_FINGERPRINT unset): then note() returns immediately.
When ON (set the variable to 1 on the live service) it prints ONE log line per symbol/timeframe whenever the last CLOSED candle changes:
    [candle-fp] okx BTC/USDT 15m t=1790000000000 o=.. h=.. l=.. c=.. v=.. fp=<12 hex>
so that the owner can later compare what Cloud really saw (OKX) with the Binance dataset (tools/compare_fingerprints.py). No database writes, no network,
a few microseconds per call; at most MAX_LINES lines per process."""
import hashlib
import os

MAX_LINES = 5000
_last = {}
_count = 0


def enabled(env=None):
    env = os.environ if env is None else env
    return str(env.get("SINDHU_CANDLE_FINGERPRINT", "")).strip().lower() in ("1", "true", "yes", "on")


def fingerprint(open_time_ms, o, h, l, c, v):
    return hashlib.sha256(f"{int(open_time_ms)}|{o:.10g}|{h:.10g}|{l:.10g}|{c:.10g}|{v:.10g}".encode()).hexdigest()[:12]


def note(exchange, symbol, interval, frame, log=print, env=None):
    """frame: a closed-candles DataFrame with a UTC DatetimeIndex and open/high/low/close/volume columns."""
    global _count
    if not enabled(env) or _count >= MAX_LINES:
        return None
    try:
        if frame is None or len(frame) == 0:
            return None
        t = int(frame.index[-1].timestamp() * 1000)
        key = (exchange, symbol, interval)
        if _last.get(key) == t:
            return None
        _last[key] = t
        r = frame.iloc[-1]
        o, h, l, c, v = (float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]), float(r["volume"]))
        line = (f"[candle-fp] {exchange} {symbol} {interval} t={t} o={o:.10g} h={h:.10g} l={l:.10g} c={c:.10g} v={v:.10g} "
                f"fp={fingerprint(t, o, h, l, c, v)}")
        _count += 1
        log(line)
        return line
    except Exception:
        return None            # a logging helper must never break a scan
