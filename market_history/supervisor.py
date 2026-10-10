"""Launch once, inspect PID/progress independently; worker owns writer lock."""
import argparse,json,os,subprocess,sys
from pathlib import Path

def main():
    import psutil
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--start',action='store_true')
    args=parser.parse_args();root=args.root;root.mkdir(parents=True,exist_ok=True)
    status_file=root/'status.json';status=json.loads(status_file.read_text()) if status_file.exists() else {}
    pid=status.get('pid');alive=False
    if pid and psutil.pid_exists(pid):
        try:alive='market_history.worker' in psutil.Process(pid).cmdline()
        except psutil.Error:pass
    if args.start and not alive:
        flags=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0
        with (root/'download.log').open('ab',buffering=0) as log:
            process=subprocess.Popen([sys.executable,'-m','market_history.worker','--root',str(root)],cwd=Path(__file__).resolve().parents[1],stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,creationflags=flags,start_new_session=os.name!='nt')
        print(json.dumps({'launched_pid':process.pid,'log':str(root/'download.log'),'verification_pending':True}),flush=True)
        return
    manifest=json.loads((root/'manifest.json').read_text()) if (root/'manifest.json').exists() else {'partitions':{}}
    parts=manifest['partitions'];coins={key.split('/')[0] for key in parts}
    completed=sum(sum(key.startswith(coin+'/') and value.get('complete',False) for key,value in parts.items())==13 for coin in coins)
    print(json.dumps({'process_alive':alive,'status':status,'coins_completed':completed,'partitions_completed':sum(v.get('complete',False) for v in parts.values()),'records_verified':sum(v.get('rows',0) for v in parts.values()),'missing_minutes_observed':sum(v.get('missing_minutes',0) for v in parts.values()),'missing_archives':len(manifest.get('missing_archives',[])),'bytes_used':sum(p.stat().st_size for p in root.rglob('*') if p.is_file()),'log':str(root/'download.log')}),flush=True)

if __name__=='__main__':main()
