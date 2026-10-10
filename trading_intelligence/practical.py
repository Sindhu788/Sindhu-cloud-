"""Causal research adapters around existing SINDHU concepts. No execution IO."""
import pandas as pd
from backtest_engine import concepts as c
from trading_intelligence.research import validate_candles,INTERVALS

def false_breakouts(df,lookback=20):
    if lookback<2:raise ValueError('At least two prior bars required')
    high=df.high.rolling(lookback).max().shift(1)
    low=df.low.rolling(lookback).min().shift(1)
    failed_up=((df.high>high)&(df.close<=high)&(df.close>=low)).fillna(False)
    failed_down=((df.low<low)&(df.close>=low)&(df.close<=high)).fillna(False)
    return failed_up,failed_down

def structure_events(df,lookback=2):
    """One break event per confirmed pivot, even if price stays beyond it."""
    highs,lows=c.swing_points(df,lookback);up,down=c.break_of_structure(df,lookback)
    high_id=low_id=None;used_high=used_low=None;bull=[];bear=[]
    for i in range(len(df)):
        if highs.iloc[i]:high_id=i
        if lows.iloc[i]:low_id=i
        a=bool(up.iloc[i] and high_id is not None and high_id!=used_high)
        b=bool(down.iloc[i] and low_id is not None and low_id!=used_low)
        if a:used_high=high_id
        if b:used_low=low_id
        bull.append(a);bear.append(b)
    return pd.Series(bull,index=df.index),pd.Series(bear,index=df.index)

def closed_trend_context(lower_rows,higher_rows,lower_tf='1h',higher_tf='4h',period=20):
    """A native HTF candle is unavailable until its own close (not its open)."""
    if higher_tf not in INTERVALS or lower_tf not in INTERVALS or INTERVALS[higher_tf]<=INTERVALS[lower_tf] or not 2<=period<=200:
        raise ValueError('Need a larger fixed higher timeframe and valid EMA period')
    lower=validate_candles(lower_rows,lower_tf);higher=validate_candles(higher_rows,higher_tf)
    for frame,tf in [(lower,lower_tf),(higher,higher_tf)]:
        if any(int(t.timestamp()*1000)%INTERVALS[tf] for t in frame.index):raise ValueError('UTC timeframe alignment required')
    left=pd.DataFrame({'decision_at':lower.index+pd.to_timedelta(INTERVALS[lower_tf],unit='ms'),
                       'lower_close':lower.close.to_numpy(),'lower_ema':c.ema(lower.close,period).to_numpy()})
    right=pd.DataFrame({'available_at':higher.index+pd.to_timedelta(INTERVALS[higher_tf],unit='ms'),
                        'higher_close':higher.close.to_numpy(),'higher_ema':c.ema(higher.close,period).to_numpy(),
                        'higher_bars':range(1,len(higher)+1)})
    return pd.merge_asof(left,right,left_on='decision_at',right_on='available_at',direction='backward')

def multi_timeframe_decision(lower_rows,higher_rows,lower_tf='1h',higher_tf='4h',period=20):
    row=closed_trend_context(lower_rows,higher_rows,lower_tf,higher_tf,period).iloc[-1]
    enough=len(lower_rows)>=period and pd.notna(row.higher_bars) and row.higher_bars>=period
    lower='bullish' if row.lower_close>row.lower_ema else 'bearish' if row.lower_close<row.lower_ema else 'neutral'
    higher='neutral' if pd.isna(row.higher_close) else 'bullish' if row.higher_close>row.higher_ema else 'bearish' if row.higher_close<row.higher_ema else 'neutral'
    agreement=enough and lower==higher and lower!='neutral'
    return {'decision':'PAPER_CANDIDATE' if agreement else 'NO_TRADE','execution_allowed':False,
            'lower_trend':lower,'higher_trend':higher,'higher_closed_at':None if pd.isna(row.available_at) else row.available_at.isoformat(),
            'reason':'Closed native timeframe agreement; research only' if agreement else 'Insufficient closed context or conflicting/neutral trends'}
