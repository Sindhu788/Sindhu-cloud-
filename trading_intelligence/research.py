"""Bounded OHLCV validation and reproducible, chronological research helpers."""
import csv
import hashlib
import io
import json
import math

import numpy as np
import pandas as pd

INTERVALS = {"1m":60_000,"5m":300_000,"15m":900_000,"30m":1_800_000,
             "1h":3_600_000,"4h":14_400_000,"1d":86_400_000}


def validate_candles(rows, timeframe="1h", *, max_rows=10000):
    if timeframe not in INTERVALS:
        raise ValueError("Unsupported timeframe")
    if not rows or len(rows) > max_rows:
        raise ValueError(f"Supply 1..{max_rows} candles")
    required = ("timestamp", "open", "high", "low", "close", "volume")
    clean = []
    for row in rows:
        if any(k not in row for k in required):
            raise ValueError("Each candle needs timestamp, open, high, low, close, volume")
        if any(isinstance(row[k], bool) for k in required):
            raise ValueError("Boolean candle values are invalid")
        try:
            values = {k: float(row[k]) for k in required}
        except (ValueError, TypeError):
            raise ValueError("Candle values must be numeric") from None
        if not all(math.isfinite(v) for v in values.values()):
            raise ValueError("NaN/infinite candle values are invalid")
        if values["timestamp"] < 0 or values["timestamp"] != int(values["timestamp"]):
            raise ValueError("Timestamp must be integer UTC milliseconds")
        if min(values[k] for k in ("open","high","low","close")) <= 0 or values["volume"] < 0:
            raise ValueError("Prices must be positive and volume nonnegative")
        if not (values["low"] <= min(values["open"],values["close"]) <=
                max(values["open"],values["close"]) <= values["high"]):
            raise ValueError("OHLC candle bounds are inconsistent")
        values["timestamp"] = int(values["timestamp"])
        clean.append(values)
    stamps = [r["timestamp"] for r in clean]
    if any(b <= a for a,b in zip(stamps,stamps[1:])):
        raise ValueError("Duplicate or unordered timestamps; input is never silently sorted")
    step = INTERVALS[timeframe]
    if any((b-a) != step for a,b in zip(stamps,stamps[1:])):
        raise ValueError("Missing candles or inconsistent timeframe")
    frame = pd.DataFrame(clean)
    frame.index = pd.to_datetime(frame.pop("timestamp"), unit="ms", utc=True)
    return frame


def import_csv(text, timeframe="1h"):
    if len(text.encode("utf-8")) > 2_000_000:
        raise ValueError("CSV exceeds the 2 MB research limit")
    return validate_candles(list(csv.DictReader(io.StringIO(text))), timeframe)


def dataset_hash(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",",":"), allow_nan=False).encode()).hexdigest()


def chronological_split(n, train=0.6, validation=0.2, embargo=1):
    if n < 10 or not 0 < train < 1 or not 0 < validation < 1-train or embargo < 0:
        raise ValueError("Invalid chronological split")
    a,b = int(n*train),int(n*(train+validation))
    splits = {"train":(0,a),"validation":(a+embargo,b),"test":(b+embargo,n)}
    if any(end <= start for start,end in splits.values()):
        raise ValueError("Not enough candles after embargo")
    return splits


def walk_forward(n, train_bars=100, test_bars=30, embargo=1):
    if min(train_bars,test_bars) < 1 or embargo < 0:
        raise ValueError("Invalid walk-forward windows")
    return [{"train":(0,end),"test":(end+embargo,min(end+embargo+test_bars,n))}
            for end in range(train_bars,n-embargo,test_bars)]


def prefix_invariant(function, frame, cuts=None):
    """Compare earlier outputs before/after future bars are appended."""
    full = function(frame.copy())
    for cut in cuts or [max(3,len(frame)//2),len(frame)-1]:
        prefix = function(frame.iloc[:cut].copy())
        fs = full if isinstance(full,tuple) else (full,)
        ps = prefix if isinstance(prefix,tuple) else (prefix,)
        if any(not np.allclose(a.iloc[:cut].to_numpy(dtype=float), b.to_numpy(dtype=float),
                               equal_nan=True) for a,b in zip(fs,ps)):
            return False
    return True


def baseline_backtest(rows, timeframe="1h", *, period=20, fee_bps=10, slippage_bps=5,
                      initial_balance=1000.0, data_label="historical"):
    """Long/flat SMA baseline; signals use previous close, fills use next open.

    Explicit assumed costs (not exchange quotations). Positions are valued at
    each close and liquidated at the final close including costs.
    """
    if data_label not in ("historical","synthetic") or not 2 <= period <= 200:
        raise ValueError("Invalid research label or period")
    if not all(math.isfinite(x) for x in (fee_bps,slippage_bps,initial_balance)) or min(fee_bps,slippage_bps)<0 or max(fee_bps,slippage_bps)>1000 or initial_balance<=0:
        raise ValueError("Invalid cost/balance assumptions")
    df=validate_candles(rows,timeframe)
    if len(df)<period+2:
        raise ValueError("Insufficient warmup candles")
    from backtest_engine.concepts import sma
    previous_signal=(df.close>sma(df.close,period)).shift(1).fillna(False)
    cash=initial_balance;qty=0.0;fee=fee_bps/10000;slip=slippage_bps/10000
    equity=[initial_balance];fills=[]
    for i,(_,bar) in enumerate(df.iterrows()):
        if previous_signal.iloc[i] and not qty:
            price=float(bar.open)*(1+slip);qty=cash/(price*(1+fee));cash=0.0
            fills.append({"bar":i,"side":"buy","price":price,"quantity":qty})
        elif not previous_signal.iloc[i] and qty:
            price=float(bar.open)*(1-slip);cash=qty*price*(1-fee);qty=0.0
            fills.append({"bar":i,"side":"sell","price":price})
        equity.append(cash+qty*float(bar.close))
    if qty:
        price=float(df.close.iloc[-1])*(1-slip);cash=qty*price*(1-fee)
        fills.append({"bar":len(df)-1,"side":"sell","price":price,"reason":"end_of_dataset"})
        equity[-1]=cash
    peak=equity[0];dd=0.0
    for value in equity:peak=max(peak,value);dd=max(dd,(peak-value)/peak*100)
    hold=initial_balance/(float(df.open.iloc[0])*(1+slip)*(1+fee))*float(df.close.iloc[-1])*(1-slip)*(1-fee)
    return {"dataset_sha256":dataset_hash(rows),"data_label":data_label,"period":period,
            "fee_bps":fee_bps,"slippage_bps":slippage_bps,"final_balance":cash,
            "net_return_pct":(cash/initial_balance-1)*100,"max_drawdown_pct":dd,
            "buy_hold_return_pct":(hold/initial_balance-1)*100,"cash_return_pct":0,
            "fills":fills,"bars":len(rows),"profitability_proven":False}


def research_validation(rows, timeframe="1h", periods=(10,20,30), *, data_label="historical"):
    """Choose a parameter on training only; validation/test never reselect it."""
    validate_candles(rows,timeframe)
    splits=chronological_split(len(rows))
    smallest=min(b-a for a,b in splits.values())
    scores={p:baseline_backtest(rows[:splits['train'][1]],timeframe,period=p,data_label=data_label)['net_return_pct']
            for p in periods if 2<=p<smallest-1}
    if not scores:raise ValueError("Insufficient training data")
    winner=max(scores,key=scores.get)
    out={"selected_period":winner,"train_trials":scores,"splits":splits,"selection_basis":"train only"}
    for name in ("validation","test"):
        a,b=splits[name]
        out[name]=baseline_backtest(rows[a:b],timeframe,period=winner,data_label=data_label)
    out['overfit_warning']=out['validation']['net_return_pct']<0 or len(scores)>1
    out['warning']='Multiple parameter trials require independent replication; test results do not approve trading.'
    return out


def walk_forward_evaluation(rows, timeframe="1h", *, periods=(5,10,20),
                            train_bars=100, test_bars=40, data_label="historical"):
    """Expanding training only selects each fold; each test starts flat.

    Short partial folds are omitted explicitly, never silently padded with
    invented candles. Test-window warmup is deliberately excluded from trading.
    """
    validate_candles(rows,timeframe)
    folds=[];skipped=0
    for windows in walk_forward(len(rows),train_bars,test_bars):
        a,b=windows['train'];c,d=windows['test']
        candidates=[p for p in periods if 2<=p<min(b-a,d-c)-1]
        if not candidates:
            skipped+=1
            continue
        trials={p:baseline_backtest(rows[a:b],timeframe,period=p,data_label=data_label)['net_return_pct']
                for p in candidates}
        winner=max(trials,key=trials.get)
        folds.append({'windows':windows,'train_trials':trials,'selected_period':winner,
                      'test':baseline_backtest(rows[c:d],timeframe,period=winner,data_label=data_label)})
    if not folds:raise ValueError('Insufficient candles for a complete walk-forward evaluation')
    return {'folds':folds,'skipped_short_folds':skipped,'data_label':data_label,
            'dataset_sha256':dataset_hash(rows),'selection_basis':'Each training prefix only',
            'warning':'Multiple trials risk overfitting. Independent replication required.',
            'profitability_proven':False}
