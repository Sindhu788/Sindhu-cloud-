"""Local review server. Legacy engines and every network delivery stay paused."""
import os
import platform
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.update(DATABASE_URL='',SINDHU_DATA_DIR=str(ROOT/'data/recovery_main'),
                  SINDHU_SAFE_START='1',SINDHU_TELEGRAM_DRY_RUN='1',
                  SINDHU_PUBLIC_SIGNAL_OWNER='disabled',SINDHU_OPEN_BROWSER='0',
                  SINDHU_CLOUD_MODE='0',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
if os.name=='nt':
    platform._wmi_query=lambda *a,**k: (_ for _ in ()).throw(OSError('WMI unavailable'))

if __name__=='__main__':
    from data_engine import storage
    from sindhu_web import auth
    storage.init_db()
    if not auth.has_credentials():
        # Reuse the owner's existing local credential record, never mint a
        # session or bypass authentication. No credential values are printed.
        import shutil
        source=Path('D:/sindhu/data/config/auth_credentials.json')
        target=ROOT/'data/recovery_main/config/auth_credentials.json'
        if source.exists() and not target.exists():
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,target)
    from sindhu_web.server import run
    run(host='127.0.0.1',port=8420,open_browser=False)
