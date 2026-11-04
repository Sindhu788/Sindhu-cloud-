"""Supervisor for the local SINDHU app (stdlib only, no admin rights, touches no OS security setting).
- starts web_main.py in SAFE mode with the permanent venv, appends output to server.log
- every 30 s GET http://127.0.0.1:8420/health; 3 failures in a row -> restart the app
- if /health ever reports safe_start != true the app is killed and NOT restarted (the local app must never be able to publish signals)
- rotates server.log / supervisor.log above 20 MB into logs_archive (archived, never deleted)
- stops when the file supervisor.stop appears (stop_local.cmd creates it)"""
import json, os, subprocess, sys, time, urllib.request, datetime, shutil

ROOT = r"D:\sindhu_runtime"
PY = r"D:\sindhu_venv_stable\Scripts\python.exe"
APP_DIR = r"D:\sindhu_clean"
URL = "http://127.0.0.1:8420/health"
STOP = os.path.join(ROOT, "supervisor.stop")
LOCK = os.path.join(ROOT, "supervisor.pid")
SLOG = os.path.join(ROOT, "supervisor.log")
ALOG = os.path.join(ROOT, "server.log")
ARCH = os.path.join(ROOT, "logs_archive")
MAX_BYTES = 20 * 1024 * 1024
ENV = dict(os.environ, SINDHU_DATA_DIR="D:/sindhu/data", SINDHU_SAFE_START="1", SINDHU_OPEN_BROWSER="0",
           SINDHU_PUBLIC_SIGNAL_OWNER="disabled", SINDHU_TELEGRAM_DRY_RUN="1",
           SINDHU_STRATEGY_LIBRARY_DIR="D:/sindhu_runtime/strategy_library")


def log(msg):
    rotate(SLOG)
    with open(SLOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}\n")


def rotate(path):
    try:
        if os.path.exists(path) and os.path.getsize(path) > MAX_BYTES:
            os.makedirs(ARCH, exist_ok=True)
            dst = os.path.join(ARCH, os.path.basename(path) + "." + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
            shutil.move(path, dst)
    except Exception:
        pass


def pid_alive(pid):
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return "python" in out.lower()
    except Exception:
        return False


def health():
    try:
        with urllib.request.urlopen(URL, timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def start():
    rotate(ALOG)
    out = open(ALOG, "ab")
    p = subprocess.Popen([PY, "web_main.py"], cwd=APP_DIR, env=ENV, stdout=out, stderr=subprocess.STDOUT,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    log(f"started app pid {p.pid}")
    return p


def wait_ready(proc, seconds=150):
    """Wait until the app answers /health (it needs 40-60 s to import pandas and open the database), or stop/exit/timeout."""
    t0 = time.time()
    while time.time() - t0 < seconds and not os.path.exists(STOP) and proc.poll() is None:
        if health():
            log(f"app ready after {time.time() - t0:.0f}s")
            return True
        time.sleep(3)
    return False


def kill(p):
    try:
        subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
    except Exception:
        pass


def main():
    # one supervisor at a time: a second one would fight the first over port 8420
    try:
        old = int(open(LOCK).read().strip())
        if old != os.getpid() and pid_alive(old):
            log(f"another supervisor (pid {old}) is already running - exiting")
            return
    except Exception:
        pass
    with open(LOCK, "w") as f:
        f.write(str(os.getpid()))
    if os.path.exists(STOP):
        os.remove(STOP)
    try:
        run()
    finally:
        try:
            os.remove(LOCK)
        except Exception:
            pass


def run():
    log("supervisor started")
    proc, fails, unsafe = start(), 0, False
    wait_ready(proc)
    while not os.path.exists(STOP):
        h = health()
        if h and h.get("status") == "ok":
            if h.get("safe_start") is not True:
                log("UNSAFE: /health did not report safe_start=true -> killing app, NOT restarting")
                kill(proc); unsafe = True; break
            fails = 0
        else:
            fails += 1
            log(f"health check failed ({fails}/3)")
        if proc.poll() is not None:
            log(f"app exited with code {proc.returncode}"); fails = 3
        if fails >= 3:
            kill(proc); time.sleep(3)
            proc = start(); fails = 0
            wait_ready(proc)
        for _ in range(15):                 # 30 s between health checks, but notice a stop request within 2 s
            if os.path.exists(STOP):
                break
            time.sleep(2)
    kill(proc)
    log("supervisor stopped" + (" (unsafe app)" if unsafe else ""))


if __name__ == "__main__":
    main()
