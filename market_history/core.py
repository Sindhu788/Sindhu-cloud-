"""Streaming UTC validation and aggregation; never fills missing candles."""
import calendar
import csv
import hashlib
import io
import math
from datetime import datetime,timedelta,timezone
from pathlib import Path
import zipfile

MINUTE=60_000
FIELDS=('timestamp','open','high','low','close','volume')
STEPS={'1m':MINUTE,'5m':5*MINUTE,'15m':15*MINUTE,'30m':30*MINUTE,'1h':60*MINUTE,'4h':240*MINUTE,'1d':1440*MINUTE}

def utc_ms(value):return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()*1000)

def normalize_timestamp(value):
    """Infer seconds/ms/us/ns by plausible UTC date, retaining exact integers."""
    raw=int(value);matches=[]
    for unit,divisor in [('s',.001),('ms',1),('us',1000),('ns',1000000)]:
        if divisor<1:stamp=raw*1000
        else:
            if raw%divisor:continue
            stamp=raw//divisor
        if utc_ms('2009-01-01')<=stamp<utc_ms('2100-01-01'):matches.append((stamp,unit))
    if len(matches)!=1:raise ValueError('Ambiguous or invalid timestamp unit')
    return matches[0]

def checked(row):
    if set(FIELDS)-row.keys():raise ValueError('Missing OHLCV columns')
    t=row['timestamp']
    if isinstance(t,bool) or not isinstance(t,int) or t%MINUTE:raise ValueError('Unaligned UTC minute timestamp')
    values=[float(row[k]) for k in FIELDS[1:]]
    if not all(math.isfinite(v) for v in values):raise ValueError('Non-finite OHLCV')
    o,h,l,c,v=values
    if min(o,h,l,c)<=0 or v<0 or not l<=min(o,c)<=max(o,c)<=h:raise ValueError('Invalid OHLCV prices/volume')
    return dict(zip(FIELDS,(t,*values)))

def archive_rows(path,start,end):
    with zipfile.ZipFile(path) as archive:
        members=archive.infolist()
        if len(members)!=1 or not members[0].filename.endswith('.csv') or members[0].file_size>64*1024**2:raise ValueError('Unexpected or oversized archive member')
        with archive.open(members[0]) as raw:
            reader=csv.reader(io.TextIOWrapper(raw,encoding='utf-8-sig'))
            previous=None;unit=None
            for values in reader:
                if len(values)!=12:raise ValueError('Expected 12 Binance Spot columns')
                stamp,current=normalize_timestamp(values[0])
                if unit is not None and current!=unit:raise ValueError('Mixed timestamp units')
                unit=current
                if previous is not None and stamp<=previous:raise ValueError('Duplicate/unordered archive candles')
                previous=stamp
                row=checked(dict(zip(FIELDS,(stamp,*map(float,values[1:6])))))
                # Close timestamps are inclusive (one source unit before next minute).
                close=int(values[6]);scale={'s':1,'ms':1000,'us':1000000,'ns':1000000000}[unit]
                if close!=int(values[0])+60*scale-1:raise ValueError('Invalid candle close timestamp')
                if start<=stamp<end:yield row

def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024**2),b''):digest.update(chunk)
    return digest.hexdigest()

def validate_stream(rows,start,end):
    count=0;previous=None;first=None;gaps=0
    for original in rows:
        row=checked(original);stamp=row['timestamp']
        if not start<=stamp<end:raise ValueError('Candle outside requested interval')
        if previous is not None:
            if stamp<=previous:raise ValueError('Duplicate/unordered partition candles')
            gaps+=(stamp-previous)//MINUTE-1
        else:first=stamp
        previous=stamp;count+=1
    expected=(end-start)//MINUTE
    missing=expected-count
    if missing<0:raise ValueError('Too many candles')
    return {'rows':count,'expected_rows':expected,'missing_minutes':missing,'internal_missing_minutes':gaps,
            'duplicates':0,'first_timestamp':first,'last_timestamp':previous,
            'complete':count==expected and first==start and previous==end-MINUTE}

def bucket_bounds(stamp,timeframe):
    if timeframe in STEPS:
        size=STEPS[timeframe];begin=stamp//size*size;return begin,begin+size
    dt=datetime.fromtimestamp(stamp/1000,timezone.utc)
    if timeframe=='1w':
        begin=dt.replace(hour=0,minute=0,second=0,microsecond=0)-timedelta(days=dt.weekday())
        finish=begin+timedelta(days=7)
    elif timeframe=='1M':
        begin=dt.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
        finish=begin+timedelta(days=calendar.monthrange(begin.year,begin.month)[1])
    else:raise ValueError('Unsupported timeframe')
    return int(begin.timestamp()*1000),int(finish.timestamp()*1000)

def aggregate(rows,timeframe):
    """O(1) aggregation; partial edge/gap buckets are omitted, never fabricated."""
    bucket=None;first=None;last=None;count=0;previous=None
    for original in rows:
        row=checked(original);stamp=row['timestamp']
        if previous is not None and stamp<=previous:raise ValueError('Duplicate/unordered source candles')
        previous=stamp;begin,end=bucket_bounds(stamp,timeframe)
        if bucket is None or bucket['timestamp']!=begin:
            if bucket and first==bucket['timestamp'] and last==finish-MINUTE and count==(finish-first)//MINUTE:yield bucket
            bucket={'timestamp':begin,'open':row['open'],'high':row['high'],'low':row['low'],'close':row['close'],'volume':row['volume']}
            first=stamp;finish=end;count=1
        else:
            bucket['high']=max(bucket['high'],row['high']);bucket['low']=min(bucket['low'],row['low'])
            bucket['close']=row['close'];bucket['volume']+=row['volume'];count+=1
        last=stamp
    if bucket and first==bucket['timestamp'] and last==finish-MINUTE and count==(finish-first)//MINUTE:yield bucket

def parquet_rows(path):
    from market_history.parquet_io import read_rows
    yield from read_rows(path)

def read_coin(root,coin,timeframe='1m',require_complete=True):
    """Read only manifest-verified immutable final partitions, never .part files."""
    import json
    manifest=json.loads((Path(root)/'manifest.json').read_text())
    if require_complete:
        receipt_path=Path(root)/'verification.json'
        if not receipt_path.exists():raise ValueError('Historical dataset incomplete or full integrity verification pending; backtesting is blocked')
        receipt=json.loads(receipt_path.read_text())
        if not receipt.get('complete') or receipt.get('manifest_sha256')!=sha256(Path(root)/'manifest.json'):
            raise ValueError('Full integrity checkpoint does not match the current manifest')
    partitions=sorted((v for k,v in manifest['partitions'].items() if k.startswith(coin+'/')),key=lambda v:v['start'])
    if require_complete and (len(partitions)!=13 or not all(v.get('complete') for v in partitions)):
        raise ValueError('Historical dataset incomplete; full backtesting is blocked')
    def source():
        for part in partitions:
            if not part.get('complete'):continue
            path=Path(root)/part['path']
            if sha256(path)!=part['parquet_sha256']:raise ValueError('Partition checksum mismatch')
            yield from parquet_rows(path)
    yield from aggregate(source(),timeframe)
