import csv,io,zipfile
from pathlib import Path
import pytest
from market_history.core import normalize_timestamp,utc_ms,aggregate,validate_stream,archive_rows,bucket_bounds

def candles(start,n):
    return [{'timestamp':start+i*60000,'open':10.,'high':12.,'low':9.,'close':11.,'volume':2.} for i in range(n)]

@pytest.mark.parametrize('scale,unit',[(.001,'s'),(1,'ms'),(1000,'us'),(1000000,'ns')])
def test_timestamp_units(scale,unit):
    t=utc_ms('2025-11-01');assert normalize_timestamp(str(int(t*scale)))==(t,unit)

def test_calendar_month_and_monday_week():
    start=utc_ms('2026-02-01');end=utc_ms('2026-03-01')
    assert bucket_bounds(start,'1M')==(start,end)
    assert bucket_bounds(utc_ms('2026-02-08'),'1w')==(utc_ms('2026-02-02'),utc_ms('2026-02-09'))
    assert bucket_bounds(utc_ms('2025-12-31'),'1M')[1]==utc_ms('2026-01-01')

@pytest.mark.parametrize('timeframe,n',[('1m',1),('5m',5),('15m',15),('30m',30),('1h',60),('4h',240),('1d',1440)])
def test_complete_fixed_buckets(timeframe,n):
    result=list(aggregate(candles(utc_ms('2026-02-01'),n),timeframe))
    assert len(result)==1 and result[0]['volume']==n*2
    if n>1:assert not list(aggregate(candles(utc_ms('2026-02-01'),n-1),timeframe))

def test_gaps_duplicates_and_invalid_prices():
    start=utc_ms('2025-11-01');rows=candles(start,10);rows.pop(3)
    assert validate_stream(iter(rows),start,start+600000)['missing_minutes']==1
    assert len(list(aggregate(rows,'5m')))==1
    with pytest.raises(ValueError,match='Duplicate'):validate_stream(iter(rows+[rows[-1]]),start,start+600000)
    rows[0]['low']=15
    with pytest.raises(ValueError,match='OHLCV'):validate_stream(rows,start,start+600000)

def test_archive_exact_microseconds_and_close_boundary(tmp_path):
    t=utc_ms('2025-11-01');path=tmp_path/'one.zip'
    row=[t*1000,10,12,9,11,2,(t+60000)*1000-1,22,3,1,11,0]
    with zipfile.ZipFile(path,'w') as z:z.writestr('one.csv',','.join(map(str,row))+'\n')
    assert list(archive_rows(path,t,t+60000))[0]['timestamp']==t

def test_resample_does_not_publish_incomplete_month():
    assert not list(aggregate(candles(utc_ms('2026-02-01'),1440*27),'1M'))
    result=list(aggregate(candles(utc_ms('2026-02-01'),1440*28),'1M'))
    assert len(result)==1 and result[0]['volume']==1440*28*2

def test_weekly_aggregation_starts_monday_and_omits_partial_edges():
    start=utc_ms('2026-02-01') # Sunday, first day is a partial UTC week.
    result=list(aggregate(candles(start,9*1440),'1w'))
    assert len(result)==1 and result[0]['timestamp']==utc_ms('2026-02-02')
    assert result[0]['volume']==7*1440*2

def test_real_parquet_roundtrip(tmp_path):
    from market_history.parquet_io import write_rows,read_rows
    from market_history.core import checked
    rows=candles(utc_ms('2025-11-01'),30)
    rows[0].update(open=100.12345678,high=101.,low=99.,close=100.,volume=0.)
    path=tmp_path/'roundtrip.parquet';write_rows(path,iter(rows))
    assert path.read_bytes()[:4]==b'PAR1' and path.read_bytes()[-4:]==b'PAR1'
    assert [checked(r) for r in read_rows(path)]==rows

def test_writer_lock_rejects_a_second_writer(tmp_path):
    from market_history.downloader import writer_lock
    with writer_lock(tmp_path):
        with pytest.raises(OSError):
            with writer_lock(tmp_path):pass

def test_orphan_final_file_recovers_without_overwrite(tmp_path,monkeypatch):
    from market_history.downloader import Download
    from market_history.parquet_io import write_rows
    from market_history.core import sha256
    start=utc_ms('2025-11-01');end=start+60000
    archive=tmp_path/'source.zip'
    row=[start*1000,10,12,9,11,2,end*1000-1,22,3,1,11,0]
    with zipfile.ZipFile(archive,'w') as z:z.writestr('one.csv',','.join(map(str,row))+'\n')
    final=tmp_path/'BTCUSDT/2025-11/candles-1m.parquet';final.parent.mkdir(parents=True)
    write_rows(final,iter(candles(start,1)))
    original=sha256(final);download=Download(tmp_path)
    monkeypatch.setattr(download,'archive',lambda *args:archive)
    download.partition('BTCUSDT','2025-11',start,end)
    record=download.manifest['partitions']['BTCUSDT/2025-11']
    assert record['complete'] and record['path']=='BTCUSDT/2025-11/candles-1m.parquet'
    assert sha256(final)==original

def test_full_verifier_blocks_incomplete_dataset(tmp_path):
    import json
    from market_history.verify import verify
    (tmp_path/'manifest.json').write_text(json.dumps({'partitions':{}}))
    with pytest.raises(ValueError,match='incomplete'):verify(tmp_path)
    assert not (tmp_path/'verification.json').exists()
