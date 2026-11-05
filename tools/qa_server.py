"""Start / stop the ISOLATED dashboard QA server (own data folder `D:\\sindhu_runtime\\smoke_data`, port 8421, safe start, Telegram owner disabled). It never touches the
real local database or settings, so settings-save tests are safe. Usage: python tools/qa_server.py start|stop|status"""
import os
import subprocess
import sys
import time
import urllib.request

PORT = 8421
ENV = {"SINDHU_DATA_DIR": r"D:\sindhu_runtime\smoke_data", "SINDHU_SAFE_START": "1", "SINDHU_OPEN_BROWSER": "0", "SINDHU_PUBLIC_SIGNAL_OWNER": "disabled",
       "SINDHU_STRATEGY_LIBRARY_DIR": r"D:\sindhu_runtime\strategy_library", "PORT": str(PORT)}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = r"D:\sindhu_venv_stable\Scripts\python.exe"


def healthy():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=3) as r:
            return b"ok" in r.read()
    except Exception:
        return False


def start():
    if healthy():
        print("QA server already running on", PORT); return
    env = dict(os.environ, **ENV)
    for k in list(env):                                    # the QA server must not see any credential
        if any(m in k.upper() for m in ("TOKEN", "SECRET", "PASSWORD", "DATABASE_URL", "CHAT_ID")):
            del env[k]
    flags = 0x00000008 | 0x00000200 | 0x08000000
    log = open(r"D:\sindhu_runtime\qa_server.log", "ab")
    subprocess.Popen([PY, "web_main.py"], cwd=ROOT, env=env, creationflags=flags, stdin=subprocess.DEVNULL, stdout=log, stderr=log, close_fds=True)
    for _ in range(90):
        if healthy():
            print("QA server ready on", PORT); return
        time.sleep(1)
    print("QA server did not become healthy in 90 s")


def stop():
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          f"Get-NetTCPConnection -LocalPort {PORT} -State Listen -ErrorAction SilentlyContinue | ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force }}"],
                         capture_output=True, text=True)
    print("stopped" if not healthy() else "still running", out.stderr.strip()[:100])


if __name__ == "__main__":
    {"start": start, "stop": stop, "status": lambda: print("healthy" if healthy() else "down")}[sys.argv[1] if len(sys.argv) > 1 else "status"]()
