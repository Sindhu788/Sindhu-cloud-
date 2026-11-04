"""Starts the SINDHU local supervisor DETACHED from whoever runs this (a terminal, an agent session, a task): the supervisor keeps
running after the starter exits or is closed. Uses only normal Windows process flags - no scheduled task, no registry, no service,
no security setting. Safe to run twice: the supervisor lock refuses a second supervisor.
Usage: D:\\sindhu_venv_stable\\Scripts\\python.exe D:\\sindhu_runtime\\launch_detached.py [--wait]"""
import os
import subprocess
import sys
import time
import urllib.request

PY = r"D:\sindhu_venv_stable\Scripts\python.exe"
SUP = r"D:\sindhu_runtime\supervise_local.py"
DETACHED_PROCESS = 0x00000008
NEW_GROUP = 0x00000200
NO_WINDOW = 0x08000000
BREAKAWAY = 0x01000000


def healthy():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8420/health", timeout=3) as r:
            return b'"ok"' in r.read()
    except Exception:
        return False


def main():
    if healthy():
        print("SINDHU local app is already running: http://127.0.0.1:8420")
        return 0
    flags = DETACHED_PROCESS | NEW_GROUP | NO_WINDOW
    try:
        subprocess.Popen([PY, SUP], creationflags=flags | BREAKAWAY, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:       # the parent job does not allow breakaway: start without it
        subprocess.Popen([PY, SUP], creationflags=flags, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("Starting SINDHU local app (takes about 1 minute) ...")
    if "--wait" in sys.argv:
        for _ in range(60):
            if healthy():
                print("Ready: http://127.0.0.1:8420")
                return 0
            time.sleep(3)
        print("Not ready after 3 minutes - see D:\\sindhu_runtime\\supervisor.log and server.log")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
