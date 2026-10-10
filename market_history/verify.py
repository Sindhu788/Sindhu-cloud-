"""Read-only full verification plus an atomic machine checkpoint when ready."""
import argparse,hashlib,json
from pathlib import Path
from market_history.core import parquet_rows,checked,sha256,validate_stream
from market_history.downloader import COINS,partitions,atomic_json

def verify(root):
    root=Path(root);path=root/'manifest.json';manifest=json.loads(path.read_text())
    expected={coin+'/'+month for coin in COINS for month,_,_ in partitions()}
    parts=manifest['partitions']
    if set(parts)!=expected or not all(p.get('complete') for p in parts.values()):raise ValueError('Full dataset is incomplete; historical backtesting remains blocked')
    total=0
    for key,part in sorted(parts.items()):
        file=root/part['path']
        if sha256(file)!=part['parquet_sha256']:raise ValueError('Parquet checksum mismatch: '+key)
        digest=hashlib.sha256()
        def rows():
            for row in parquet_rows(file):
                row=checked(row);digest.update(json.dumps(row,sort_keys=True,separators=(',',':')).encode());yield row
        result=validate_stream(rows(),part['start'],part['end'])
        if not result['complete'] or digest.hexdigest()!=part['values_sha256']:raise ValueError('Full candle integrity failed: '+key)
        for name,value in part['source_sha256'].items():
            if sha256(root/'raw'/key.split('/')[0]/name)!=value:raise ValueError('Source archive changed: '+name)
        total+=result['rows']
    if total!=5_256_000:raise ValueError('Unexpected yearly candle count')
    receipt={'complete':True,'manifest_sha256':sha256(path),'records_verified':total,'coins':10,'missing_minutes':0,'duplicates':0}
    atomic_json(root/'verification.json',receipt)
    return receipt

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);args=parser.parse_args()
    print(json.dumps(verify(args.root)),flush=True)
