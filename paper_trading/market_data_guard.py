"""Closed-bar validation for the live paper scanner, never offline backtests."""
import re
import threading
import time
from collections import deque
import numpy as np
import pandas as pd


class MarketDataRejected(ValueError):
    """A constant, credential-free explanation for the decision journal."""


# Recovery: a rejected candle frame used to be skipped silently. Every rejection
# is now logged as a WARNING and counted here so the health check can show how
# many symbols were skipped (and why) instead of signals just going missing.
_REJECTIONS = deque(maxlen=5000)   # (epoch_seconds, timeframe, reason)
_REJECTIONS_LOCK = threading.Lock()
_TOTAL_REJECTED = 0


def _reject(reason, timeframe):
    global _TOTAL_REJECTED
    with _REJECTIONS_LOCK:
        _REJECTIONS.append((time.time(), str(timeframe), reason))
        _TOTAL_REJECTED += 1
    try:
        from data_engine.logging_setup import log
        log(f"[market-data] WARNING candle frame rejected ({timeframe}): {reason} -- this symbol is skipped this tick")
    except Exception:
        pass
    raise MarketDataRejected(reason)


def rejection_summary(window_seconds=3600, now=None):
    """Counts of rejected candle frames in the last window, grouped by reason."""
    now = time.time() if now is None else now
    with _REJECTIONS_LOCK:
        recent = [r for r in _REJECTIONS if now - r[0] <= window_seconds]
        total = _TOTAL_REJECTED
    by_reason = {}
    for _, _, reason in recent:
        by_reason[reason] = by_reason.get(reason, 0) + 1
    return {"window_seconds": window_seconds, "rejected_in_window": len(recent),
            "total_since_start": total, "by_reason": by_reason}


def closed_recent_frame(frame, timeframe, now_ms=None):
    now_ms=int(time.time()*1000) if now_ms is None else now_ms
    if frame is None or frame.empty:
        _reject('Market data is empty.', timeframe)
    if not isinstance(frame.index,pd.DatetimeIndex) or frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        _reject('Market timestamps must be unique and increasing.', timeframe)
    index=frame.index.tz_localize('UTC') if frame.index.tz is None else frame.index.tz_convert('UTC')
    if timeframe=='1M':
        closes=index+pd.offsets.MonthBegin(1)
    else:
        match=re.fullmatch(r'([1-9][0-9]*)([mhdw])',timeframe)
        if not match:
            _reject('Unsupported live timeframe.', timeframe)
        duration=int(match[1])*{'m':60000,'h':3600000,'d':86400000,'w':604800000}[match[2]]
        closes=index+pd.to_timedelta(duration,unit='ms')
    now=pd.Timestamp(now_ms,unit='ms',tz='UTC')
    if (index>now).any():
        _reject('Future market timestamps rejected.', timeframe)
    closed=frame.loc[closes<=now].copy()
    close_index=closes[closes<=now]
    if closed.empty:
        _reject('No closed market candle is available.', timeframe)
    tail=closed.tail(20)
    required=['open','high','low','close','volume']
    if any(c not in tail for c in required):
        _reject('Required OHLCV fields are missing.', timeframe)
    values=tail[required].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values[:,:4]<=0).any() or (values[:,4]<0).any():
        _reject('Non-finite or invalid market prices/volume rejected.', timeframe)
    o,h,l,c,v=values.T
    if (h<np.maximum(o,c)).any() or (l>np.minimum(o,c)).any() or (h<l).any():
        _reject('Invalid OHLC bounds rejected.', timeframe)
    recent=min(20,len(close_index))
    if recent>1 and (close_index[-recent:-1] != index[closes<=now][-recent+1:]).any():
        _reject('Gaps in recent market candles rejected.', timeframe)
    last_close=int(close_index[-1].timestamp()*1000)
    last_open=int((closed.index[-1].tz_localize('UTC') if closed.index.tz is None else closed.index[-1]).timestamp()*1000)
    period=last_close-last_open
    age=now_ms-last_close
    if age>period:
        _reject('Stale closed market candles rejected.', timeframe)
    return closed,{'timeframe':timeframe,'last_closed_at_ms':last_close,'observed_at_ms':now_ms,
                   'age_ms':age,'period_ms':period,'status':'fresh_at_observation'}
