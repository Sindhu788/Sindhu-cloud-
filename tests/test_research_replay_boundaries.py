from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from backtest_engine.configured_strategy import ConfiguredStrategy
from backtest_engine.strategy_config import Condition
from trading_intelligence.historical_lab import FrozenReplay


@pytest.mark.parametrize("window,expected", [(1,[False,False,True,False]),(2,[False,False,True,True])])
def test_event_window_excludes_unknown_and_future_values(window, expected):
    frame=pd.DataFrame({"bias_bull_bos":[np.nan,False,True,False],"bias_bear_bos":[False]*4})
    strategy=ConfiguredStrategy(SimpleNamespace(name='isolated'))
    condition=Condition(type='concept',name='bos',role='bias',direction='bullish',lookback_bars=window)
    assert [strategy._eval(condition,frame,i) for i in range(4)] == expected


def test_frozen_replay_respects_strict_split_end_and_spot_filter():
    index=pd.date_range('2026-01-01',periods=5,freq='h',tz='UTC')
    frame=pd.DataFrame({'close':[100.]*5},index=index)
    calls=[]
    class Strategy:
        config=SimpleNamespace()
        def on_bar(self,frame,i,position):
            calls.append(i)
            return SimpleNamespace(action='sell' if i==2 else 'buy')
    replay=FrozenReplay(Strategy(),frame,index[1],index[3],True)
    results=[replay.on_bar(frame,i,None) for i in range(5)]
    assert calls == [1,2]
    assert [x.action if x else None for x in results] == [None,'buy',None,None,None]
