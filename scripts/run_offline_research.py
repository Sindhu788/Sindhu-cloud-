"""Research-only runner: no production DB, workers, credentials or broadcasts."""
import argparse,os,platform,sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ.update(DATABASE_URL='',SINDHU_DATA_DIR=str(ROOT/'data/isolated_qa'),SINDHU_SAFE_START='1',SINDHU_TELEGRAM_DRY_RUN='1',SINDHU_PUBLIC_SIGNAL_OWNER='disabled',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
if os.name=='nt':
    def no_wmi(*args,**kwargs):raise OSError('WMI unavailable')
    platform._wmi_query=no_wmi

def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['audit','exam','test','fixtures']);args=parser.parse_args()
    if args.mode=='audit':
        from trading_intelligence.executable_audit import audit
        result=audit();print(json.dumps({k:v for k,v in result.items() if k!='results'}),flush=True)
        print(json.dumps({'non_pass':[r for r in result['results'] if r['status']!='SMOKE_PASS']}),flush=True)
    elif args.mode=='exam':
        from trading_intelligence.practical_exam import run_exam
        result=run_exam();print(json.dumps(result),flush=True);return bool(result['failed'])
    elif args.mode=='fixtures':
        from scripts.build_practical_fixtures import build
        build()
    else:
        import pytest
        return pytest.main(['-q','tests/test_market_history.py','tests/test_practical_research.py','tests/test_trade_execution_engine.py','tests/test_trading_intelligence.py','-k','not actual_main_cloud_api_qa_with_lifespan_off'])
    return 0

if __name__=='__main__':raise SystemExit(main())
