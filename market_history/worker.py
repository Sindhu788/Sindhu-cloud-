"""Standalone downloader entry point, including Windows runtime fallback."""
import os,platform
os.environ.setdefault('OMP_NUM_THREADS','1');os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
if os.name=='nt':
    def no_wmi(*args,**kwargs):raise OSError('WMI unavailable')
    platform._wmi_query=no_wmi
try:
    import psutil
    if os.name=='nt':psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
except (ImportError,OSError):pass
from market_history.downloader import main
if __name__=='__main__':main()
