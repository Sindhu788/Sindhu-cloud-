"""Resumable single-writer Binance Spot archive downloader; $0/public HTTP."""
import argparse
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
import hashlib,json,os,shutil,time
from pathlib import Path
import requests
from market_history.core import archive_rows,sha256,utc_ms,validate_stream,parquet_rows,FIELDS,checked

COINS=('BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT','XRPUSDT','ADAUSDT','DOGEUSDT','LINKUSDT','LTCUSDT','AVAXUSDT')
START=utc_ms('2025-10-10');END=utc_ms('2026-10-10')
BASE='https://data.binance.vision/data/spot'
LIMIT=4*1024**3;RESERVE=5*1024**3

def atomic_json(path,value):
    temp=path.with_suffix(path.suffix+'.part')
    with temp.open('w',encoding='utf-8') as stream:json.dump(value,stream,indent=2);stream.flush();os.fsync(stream.fileno())
    os.replace(temp,path)

@contextmanager
def writer_lock(root):
    with (root/'writer.lock').open('a+b') as stream:
        stream.seek(0,2)
        if not stream.tell():stream.write(b'0');stream.flush()
        stream.seek(0)
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:yield
        finally:
            stream.seek(0)
            if os.name=='nt':msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)

def partitions():
    month=datetime(2025,10,1,tzinfo=timezone.utc)
    while int(month.timestamp()*1000)<END:
        following=(month.replace(day=28)+timedelta(days=4)).replace(day=1)
        yield month.strftime('%Y-%m'),max(START,int(month.timestamp()*1000)),min(END,int(following.timestamp()*1000))
        month=following

class Download:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.session=requests.Session()
        self.session.headers['User-Agent']='Sindhu-public-history-research/1.0'
        path=self.root/'manifest.json'
        self.manifest=json.loads(path.read_text()) if path.exists() else {'version':1,'source':BASE,'start':START,'end':END,'partitions':{},'missing_archives':[]}
        if self.manifest['start']!=START or self.manifest['end']!=END:raise ValueError('Manifest period mismatch')
    def heartbeat(self,status,current=None):
        atomic_json(self.root/'status.json',{'pid':os.getpid(),'status':status,'current':current,'heartbeat_utc':datetime.now(timezone.utc).isoformat(),'completed_partitions':sum(v.get('complete',False) for v in self.manifest['partitions'].values()),'records_verified':sum(v.get('rows',0) for v in self.manifest['partitions'].values())})
    def budget(self,extra=0):
        used=sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file())
        if used+extra>LIMIT or shutil.disk_usage(self.root).free-extra<RESERVE:raise RuntimeError('Storage safety limit reached')
    def fetch(self,url,path):
        if path.exists():return True
        for attempt in range(4):
            try:
                with self.session.get(url,stream=True,timeout=(15,45)) as response:
                    if response.status_code==404:return False
                    response.raise_for_status();size=int(response.headers.get('Content-Length',0))
                    if size>32*1024**2:raise ValueError('Oversized archive response')
                    self.budget(size)
                    partial=path.with_suffix(path.suffix+'.part');path.parent.mkdir(parents=True,exist_ok=True)
                    written=0;began=time.monotonic()
                    with partial.open('wb') as stream:
                        for chunk in response.iter_content(256*1024):
                            written+=len(chunk)
                            if written>32*1024**2:raise ValueError('Archive exceeds safety limit')
                            stream.write(chunk)
                            time.sleep(max(0,written/(2*1024**2)-(time.monotonic()-began)))
                        stream.flush();os.fsync(stream.fileno())
                    os.replace(partial,path);return True
            except requests.RequestException:
                if attempt==3:raise
                time.sleep(2**attempt)
    def archive(self,coin,period,frequency):
        name=f'{coin}-1m-{period}.zip';url=f'{BASE}/{frequency}/klines/{coin}/1m/{name}'
        path=self.root/'raw'/coin/name
        checksum=path.with_suffix('.zip.CHECKSUM')
        if not self.fetch(url+'.CHECKSUM',checksum):
            if url not in self.manifest['missing_archives']:self.manifest['missing_archives'].append(url)
            return None
        expected=checksum.read_text().split()[0]
        if len(expected)!=64 or any(c not in '0123456789abcdefABCDEF' for c in expected):raise ValueError('Invalid source checksum')
        if not self.fetch(url,path):return None
        if sha256(path)!=expected.lower():raise ValueError('Source SHA256 mismatch: '+name)
        if url in self.manifest['missing_archives']:self.manifest['missing_archives'].remove(url)
        return path
    def partition(self,coin,month,start,end):
        key=coin+'/'+month;old=self.manifest['partitions'].get(key)
        if old and old.get('complete'):
            if sha256(self.root/old['path'])!=old['parquet_sha256']:raise ValueError('Existing partition checksum mismatch: '+key)
            return
        self.heartbeat('RUNNING',key);archives=[]
        # An unfinished current month has daily official archives, not a future monthly file.
        now=datetime.now(timezone.utc).strftime('%Y-%m')
        if month<now:
            path=self.archive(coin,month,'monthly')
            if path:archives.append(path)
        else:
            day=datetime.fromtimestamp(start/1000,timezone.utc)
            while int(day.timestamp()*1000)<end:
                path=self.archive(coin,day.strftime('%Y-%m-%d'),'daily')
                if path:archives.append(path)
                day+=timedelta(days=1)
        record={'start':start,'end':end,'complete':False,'rows':0,'expected_rows':(end-start)//60000,'missing_minutes':(end-start)//60000,'duplicates':0}
        if archives:
            from market_history.parquet_io import write_rows
            self.budget(32*1024**2)
            relative=f'{coin}/{month}/candles-1m.parquet';final=self.root/relative;final.parent.mkdir(parents=True,exist_ok=True)
            partial=final.with_suffix('.parquet.part')
            source_digest=hashlib.sha256();stored_digest=hashlib.sha256()
            def digest_rows(rows,digest):
                for row in rows:
                    row=checked(row)
                    digest.update(json.dumps(row,sort_keys=True,separators=(',',':')).encode())
                    yield row
            def source():
                for path in archives:
                    yield from archive_rows(path,start,end)
            if final.exists():
                for row in digest_rows(source(),source_digest):pass
                candidate=final # Recover publication interrupted before manifest checkpoint.
            else:
                write_rows(partial,digest_rows(source(),source_digest));candidate=partial
                with partial.open('ab') as stream:stream.flush();os.fsync(stream.fileno())
            record.update(validate_stream(digest_rows(parquet_rows(candidate),stored_digest),start,end))
            if source_digest.digest()!=stored_digest.digest():raise ValueError('Parquet values differ from source: '+key)
            record.update(path=relative,parquet_sha256=sha256(candidate),values_sha256=stored_digest.hexdigest(),source_sha256={p.name:sha256(p) for p in archives},bytes=candidate.stat().st_size)
            if record['complete']:
                if candidate!=final:os.replace(partial,final)
            else:record.pop('path',None) # partial data is never published as final
        self.manifest['partitions'][key]=record;atomic_json(self.root/'manifest.json',self.manifest)
        self.heartbeat('RUNNING',key)
        print(json.dumps({'partition':key,**{k:record[k] for k in ['rows','missing_minutes','complete']}}),flush=True)
    def run(self,pilot=False):
        with writer_lock(self.root):
            try:
                if pilot:self.partition('BTCUSDT','2025-11',utc_ms('2025-11-01'),utc_ms('2025-12-01'))
                else:
                    for coin in COINS:
                        for month,start,end in partitions():self.partition(coin,month,start,end)
                complete=sum(v.get('complete',False) for v in self.manifest['partitions'].values())
                self.heartbeat('PILOT_PASS' if pilot and self.manifest['partitions'].get('BTCUSDT/2025-11',{}).get('complete') else 'COMPLETED' if complete==130 else 'INCOMPLETE')
            except BaseException as exc:
                self.heartbeat('FAILED',type(exc).__name__+': '+str(exc));raise

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--pilot',action='store_true')
    args=parser.parse_args();Download(args.root).run(args.pilot)

if __name__=='__main__':main()
