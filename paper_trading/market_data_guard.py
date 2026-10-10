"""Closed-bar validation for the live paper scanner, never offline backtests."""
import re
import time
import numpy as np
import pandas as pd


class MarketDataRejected(ValueError):
    """A constant, credential-free explanation for the decision journal."""


def closed_recent_frame(frame, timeframe, now_ms=None):
    now_ms=int(time.time()*1000) if now_ms is None else now_ms
    if frame is None or frame.empty:
        raise MarketDataRejected('Market data is empty.')
    if not isinstance(frame.index,pd.DatetimeIndex) or frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise MarketDataRejected('Market timestamps must be unique and increasing.')
    index=frame.index.tz_localize('UTC') if frame.index.tz is None else frame.index.tz_convert('UTC')
    if timeframe=='1M':
        closes=index+pd.offsets.MonthBegin(1)
    else:
        match=re.fullmatch(r'([1-9][0-9]*)([mhdw])',timeframe)
        if not match:
            raise MarketDataRejected('Unsupported live timeframe.')
        duration=int(match[1])*{'m':60000,'h':3600000,'d':86400000,'w':604800000}[match[2]]
        closes=index+pd.to_timedelta(duration,unit='ms')
    now=pd.Timestamp(now_ms,unit='ms',tz='UTC')
    if (index>now).any():
        raise MarketDataRejected('Future market timestamps rejected.')
    closed=frame.loc[closes<=now].copy()
    close_index=closes[closes<=now]
    if closed.empty:
        raise MarketDataRejected('No closed market candle is available.')
    tail=closed.tail(20)
    required=['open','high','low','close','volume']
    if any(c not in tail for c in required):
        raise MarketDataRejected('Required OHLCV fields are missing.')
    values=tail[required].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values[:,:4]<=0).any() or (values[:,4]<0).any():
        raise MarketDataRejected('Non-finite or invalid market prices/volume rejected.')
    o,h,l,c,v=values.T
    if (h<np.maximum(o,c)).any() or (l>np.minimum(o,c)).any() or (h<l).any():
        raise MarketDataRejected('Invalid OHLC bounds rejected.')
    recent=min(20,len(close_index))
    if recent>1 and (close_index[-recent:-1] != index[closes<=now][-recent+1:]).any():
        raise MarketDataRejected('Gaps in recent market candles rejected.')
    last_close=int(close_index[-1].timestamp()*1000)
    last_open=int((closed.index[-1].tz_localize('UTC') if closed.index.tz is None else closed.index[-1]).timestamp()*1000)
    period=last_close-last_open
    age=now_ms-last_close
    if age>period:
        raise MarketDataRejected('Stale closed market candles rejected.')
    return closed,{'timeframe':timeframe,'last_closed_at_ms':last_close,'observed_at_ms':now_ms,
                   'age_ms':age,'period_ms':period,'status':'fresh_at_observation'}
