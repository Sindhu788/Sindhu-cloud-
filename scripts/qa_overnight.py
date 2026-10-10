"""Isolated loopback review and tests. No production data, engines or delivery."""
import argparse
import os
import platform
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.update(DATABASE_URL='', SINDHU_DATA_DIR=str(ROOT/'data/overnight_qa'),
                  SINDHU_SAFE_START='1', SINDHU_TELEGRAM_DRY_RUN='1',
                  SINDHU_PUBLIC_SIGNAL_OWNER='disabled', SINDHU_CLOUD_MODE='0',
                  OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
if os.name == 'nt':
    def no_wmi(*args, **kwargs):
        raise OSError('WMI unavailable')
    platform._wmi_query = no_wmi


def main():
    p=argparse.ArgumentParser()
    p.add_argument('mode', choices=['test','serve'])
    p.add_argument('--port', type=int, default=8431)
    args=p.parse_args()
    if args.mode=='test':
        import pytest
        return pytest.main(['-q','tests/test_overnight_quality.py',
                            'tests/test_manual_coin_scan.py',
                            'tests/test_challenge_multi.py','tests/test_challenge_multi_api.py',
                            'tests/test_cloud_settings_persistence.py',
                            'tests/test_telegram_freshness_gate.py','tests/test_telegram_retry_queue.py',
                            'tests/test_phase3_cloud_monitoring.py','tests/test_trading_intelligence.py',
                            '--basetemp='+str(ROOT/'data/overnight_pytest')])
    from data_engine import storage
    from sindhu_web import auth
    storage.init_db()
    if not auth.has_credentials():
        auth.set_credentials('qa-review','synthetic-qa-only')
    import uvicorn
    uvicorn.run('cloud_runtime.app:app',host='127.0.0.1',port=args.port,
                access_log=False,log_level='warning')


if __name__=='__main__':
    raise SystemExit(main())
