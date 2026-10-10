"""Deterministic educational analysis using SINDHU's existing causal concepts."""
import math
from dataclasses import dataclass

import numpy as np

from backtest_engine import concepts as c
from trading_intelligence import VERSION
from trading_intelligence.research import validate_candles, INTERVALS


def _last(series):
    value=series.iloc[-1]
    return float(value) if value is not None and math.isfinite(float(value)) else None


def chart_shapes(df):
    """Experimental geometric candidates, never an assertion of intent/profit."""
    highs,lows=c.swing_points(df,2)
    hp=[(i-2,float(df.high.iloc[i-2])) for i in range(max(2,len(df)-80),len(df)) if highs.iloc[i]]
    lp=[(i-2,float(df.low.iloc[i-2])) for i in range(max(2,len(df)-80),len(df)) if lows.iloc[i]]
    price=float(df.close.iloc[-1]); tolerance=price*.005
    found=[]
    for pivots,kind,opposite in ((hp,'double_top',df.low),(lp,'double_bottom',df.high)):
        if len(pivots)>=2:
            (i,a),(j,b)=pivots[-2:]
            neckline=float(opposite.iloc[i:j+1].min() if kind=='double_top' else opposite.iloc[i:j+1].max())
            if j-i>=3 and abs(a-b)<=tolerance and (price<neckline if kind=='double_top' else price>neckline):
                found.append(kind)
        if len(pivots)>=3:
            (i,a),(j,b),(k,d)=pivots[-3:]
            head=b>max(a,d)+tolerance if kind=='double_top' else b<min(a,d)-tolerance
            neckline=float(opposite.iloc[i:k+1].min() if kind=='double_top' else opposite.iloc[i:k+1].max())
            if abs(a-d)<=tolerance and head and (price<neckline if kind=='double_top' else price>neckline):
                found.append('head_shoulders' if kind=='double_top' else 'inverse_head_shoulders')
    if len(hp)>=2 and len(lp)>=2:
        (hi,h1),(hj,h2)=hp[-2:];(li,l1),(lj,l2)=lp[-2:]
        hs=(h2-h1)/(hj-hi);ls=(l2-l1)/(lj-li);flat=price*.0005
        if abs(hs)<=flat and ls>flat:found.append('ascending_triangle')
        elif abs(ls)<=flat and hs < -flat:found.append('descending_triangle')
        elif hs < -flat and ls>flat:found.append('symmetrical_triangle')
        elif hs>flat and ls>hs+flat:found.append('rising_wedge')
        elif ls < -flat and hs<ls-flat:found.append('falling_wedge')
        elif abs(hs-ls)<=flat:found.append('channel')
    if len(df)>=20:
        impulse=float(df.close.iloc[-11]/df.close.iloc[-20]-1)
        recent=df.iloc[-10:]
        slope=float(np.polyfit(np.arange(10),recent.close,1)[0])/price
        tight=float((recent.high.max()-recent.low.min())/price)<abs(impulse)*.6
        if abs(impulse)>.02 and tight and impulse*slope<0:found.append('flag')
        if abs(impulse)>.02 and 'symmetrical_triangle' in found:found.append('pennant')
    return sorted(set(found))


def detect(df):
    result={}
    for name,function in (("engulfing",c.engulfing_candle),("pin_bar",c.pin_bar),
                          ("star",c.morning_evening_star),("fvg",c.fair_value_gap),
                          ("bos",c.break_of_structure),("choch",c.change_of_character),
                          ("liquidity_sweep",c.liquidity_sweep)):
        bull,bear=function(df)
        result[name+'_bullish']=bool(bull.iloc[-1]);result[name+'_bearish']=bool(bear.iloc[-1])
    result['doji']=bool(c.doji_pattern(df).iloc[-1]);result['inside_bar']=bool(c.inside_bar(df).iloc[-1])
    support,resistance=c.support_resistance(df)
    result['support']=_last(support);result['resistance']=_last(resistance)
    ob=c.order_blocks(df)
    result['order_block']={k:_last(s) for k,s in zip(('bull_low','bull_high','bear_low','bear_high'),ob)}
    result['chart_shapes']=chart_shapes(df)
    indicators={name:_last(fun(df.close,period)) for name,fun,period in
                [('ema20',c.ema,20),('ema50',c.ema,50),('sma20',c.sma,20),('rsi14',c.rsi,14)]}
    line,signal,hist=c.macd(df.close)
    indicators.update(macd=_last(line),macd_signal=_last(signal),atr14=_last(c.atr(df)),vwap=_last(c.vwap_daily(df)))
    mid=c.sma(df.close,20);std=df.close.rolling(20).std(ddof=0)
    indicators['bollinger_upper']=_last(mid+2*std);indicators['bollinger_lower']=_last(mid-2*std)
    indicators['obv']=_last((np.sign(df.close.diff()).fillna(0)*df.volume).cumsum())
    up=df.high.diff();down=-df.low.diff()
    plus=up.where((up>down)&(up>0),0).ewm(alpha=1/14,adjust=False).mean()
    minus=down.where((down>up)&(down>0),0).ewm(alpha=1/14,adjust=False).mean()
    dx=((plus-minus).abs()/(plus+minus).replace(0,np.nan))*100
    indicators['adx14']=_last(dx.ewm(alpha=1/14,adjust=False).mean())
    result['indicators']=indicators
    return result


@dataclass(frozen=True)
class Evidence:
    name: str
    family: str
    direction: str
    strength: float=1.0


def evaluate_evidence(evidence, *, enough_data=True, invalidated=False):
    """Cap correlated evidence to one vote per family; any conflict abstains."""
    allowed={'trend','price_action','volume'};groups={}
    for e in evidence:
        if e.family not in allowed or e.direction not in ('bullish','bearish','neutral') or not math.isfinite(e.strength) or not 0<=e.strength<=1:
            raise ValueError('Invalid evidence')
        if e.direction=='neutral' or e.strength==0:continue
        group=groups.setdefault(e.family,{})
        group[e.direction]=max(group.get(e.direction,0),e.strength)
    directions={d for g in groups.values() for d in g}
    reasons=[]
    if not enough_data:reasons.append('insufficient closed candles')
    if invalidated:reasons.append('setup invalidated')
    if len(directions)>1:reasons.append('conflicting evidence')
    if len(groups)<2:reasons.append('fewer than two evidence families')
    elif sum(max(group.values())>=.5 for group in groups.values())<2:
        reasons.append('fewer than two strong evidence families')
    decision='NO_TRADE' if reasons else 'PAPER_CANDIDATE'
    return {'decision':decision,'direction':next(iter(directions)) if len(directions)==1 else 'neutral',
            'reasons':reasons or ['agreement across capped evidence families; research only'],
            'families':groups,'confidence_probability':None,'execution_allowed':False,
            'warning':'Families are a conservative grouping, not proof of statistical independence.'}


def analyze(rows,timeframe='1h',data_label='synthetic',as_of_ms=None):
    if data_label not in ('synthetic','historical','live'):raise ValueError('Explicit data label required')
    df=validate_candles(rows,timeframe,max_rows=2000)
    detections=detect(df);ind=detections['indicators'];evidence=[]
    if len(df)>=50:
        for name in ('ema20','sma20','vwap'):
            if ind[name] is not None:
                direction='bullish' if df.close.iloc[-1]>ind[name] else 'bearish' if df.close.iloc[-1]<ind[name] else 'neutral'
                evidence.append(Evidence(name,'trend',direction))
    for name,value in detections.items():
        if name.endswith(('_bullish','_bearish')) and value:
            evidence.append(Evidence(name,'price_action',name.rsplit('_',1)[1]))
    if len(df)>=21 and df.volume.iloc[-1] > df.volume.iloc[-21:-1].mean()*1.5:
        direction='bullish' if df.close.iloc[-1]>df.open.iloc[-1] else 'bearish' if df.close.iloc[-1]<df.open.iloc[-1] else 'neutral'
        evidence.append(Evidence('volume_expansion','volume',direction))
    enough=len(df)>=50
    if data_label=='live':
        closed_at=int(df.index[-1].timestamp()*1000)+INTERVALS[timeframe]
        enough=enough and as_of_ms is not None and closed_at<=as_of_ms<closed_at+2*INTERVALS[timeframe]
    result=evaluate_evidence(evidence,enough_data=enough)
    atr_pct=None if ind['atr14'] is None else ind['atr14']/float(df.close.iloc[-1])*100
    spread=abs(ind['ema20']-ind['ema50'])/float(df.close.iloc[-1])*100
    result.update(version=VERSION,data_label=data_label,timeframe=timeframe,detections=detections,
                  evidence=[e.__dict__ for e in evidence],regime='NOT TESTED' if len(df)<50 or atr_pct is None else 'volatile' if atr_pct>=3 else 'trending' if spread>=.5 else 'ranging',
                  unsupported_data=['open_interest','funding','order_book'],
                  educational_only=True,automatic_strategy_approval=False)
    return result


def position_size(balance,entry,stop,risk_pct=1,fee_bps=10,slippage_bps=5):
    vals=(balance,entry,stop,risk_pct,fee_bps,slippage_bps)
    if not all(math.isfinite(x) for x in vals) or min(balance,entry,stop)<=0 or entry==stop or not 0<risk_pct<=2 or min(fee_bps,slippage_bps)<0:
        raise ValueError('Invalid balance, prices, costs or risk (maximum 2%)')
    cost=entry*2*(fee_bps+slippage_bps)/10000
    qty=min(balance*risk_pct/100/(abs(entry-stop)+cost),balance/(entry*(1+(fee_bps+slippage_bps)/10000)))
    return {'quantity':qty,'planned_loss_including_assumed_costs':qty*(abs(entry-stop)+cost),
            'risk_budget':balance*risk_pct/100,'assumption':'No gap beyond stop; gaps can increase losses.'}
