"""Temporary loopback-only UI QA against fresh data; never starts engines.

The fixed account is deliberately a synthetic test fixture. Never use this
launcher for deployment, real data, or a public interface.
"""
import os
from pathlib import Path
import platform
import socket
import tempfile


def main():
    root=Path(__file__).resolve().parents[1]
    qa_root=root/'data'/'qa_intelligence_previews'
    qa_root.mkdir(parents=True,exist_ok=True)
    os.environ['SINDHU_DATA_DIR']=tempfile.mkdtemp(prefix='preview_',dir=qa_root)
    os.environ['DATABASE_URL']=''
    os.environ['SINDHU_CLOUD_MODE']='0'
    os.environ['SINDHU_PUBLIC_SIGNAL_OWNER']='disabled'
    # Host WMI is unreliable; Python has an environment-based fallback.
    if os.name=='nt':
        def no_wmi(*args,**kwargs):raise OSError('WMI unavailable in QA')
        platform._wmi_query=no_wmi
    from sindhu_web import auth
    auth.set_credentials('qa-review','synthetic-qa-only')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    print(f'Isolated QA preview: http://127.0.0.1:{port}/login',flush=True)
    import uvicorn
    uvicorn.run('cloud_runtime.app:app',host='127.0.0.1',port=port,
                lifespan='off',access_log=False,log_level='warning')


if __name__=='__main__':main()
