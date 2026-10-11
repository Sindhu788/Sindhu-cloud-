"""Independent bounded local research worker. Never touches production DBs."""
import argparse
import os
from pathlib import Path
import platform
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.update(DATABASE_URL='',SINDHU_SAFE_START='1',SINDHU_TELEGRAM_DRY_RUN='1',
                  SINDHU_PUBLIC_SIGNAL_OWNER='disabled',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
if os.name=='nt':platform._wmi_query=lambda *a,**k: (_ for _ in ()).throw(OSError('WMI unavailable'))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=Path(r'D:\sindhu\data\market_history'))
    parser.add_argument('--output',type=Path,default=ROOT/'data/overnight_qa/research_lab');parser.add_argument('--wait',action='store_true')
    args=parser.parse_args()
    from trading_intelligence.historical_lab import run_lab,verified_manifest
    while args.wait and not (args.root/'verification.json').exists():time.sleep(30)
    verified_manifest(args.root)
    from market_history.downloader import writer_lock
    args.output.mkdir(parents=True,exist_ok=True)
    with writer_lock(args.output):result=run_lab(args.root,args.output)
    print({'run_id':result['run_id'],'cases':result['coin_cases'],'counts':result['counts']},flush=True)

if __name__=='__main__':main()
