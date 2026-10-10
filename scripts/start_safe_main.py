"""Start the real local dashboard with legacy background engines paused."""
import os
import platform
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.update(DATABASE_URL='',SINDHU_SAFE_START='1',SINDHU_TELEGRAM_DRY_RUN='1',
                  SINDHU_PUBLIC_SIGNAL_OWNER='disabled',SINDHU_OPEN_BROWSER='0',SINDHU_CLOUD_MODE='0')
os.environ.pop('SINDHU_DATA_DIR',None)
if os.name=='nt':
    def unavailable_wmi(*args,**kwargs):raise OSError('WMI unavailable')
    platform._wmi_query=unavailable_wmi

if __name__=='__main__':
    from sindhu_web.server import run
    run(host='127.0.0.1',port=8420,open_browser=False)
