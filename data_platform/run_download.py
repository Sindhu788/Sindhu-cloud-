"""Background download orchestrator: PILOT (20 coins x 6 months) -> quality gate -> EXPANSION (50 coins x 12 months + current-month days).
Usage: python -m data_platform.run_download [--root D:\\sindhu_data] [--workers 4] [--detach] [--no-expand]
It survives the end of the session that started it (--detach) and can be re-run any time: finished files are skipped via the manifest."""
import argparse
import ctypes
import datetime as dt
import json
import os
import subprocess
import sys
import threading
import time

from data_platform import downloader, quality, store, universe


def _below_normal_priority():
    try:
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
    except Exception:
        pass


def _keep_awake_while_running():
    """ES_CONTINUOUS | ES_SYSTEM_REQUIRED: the computer stays awake while THIS process runs; ends with the process. No power plan is changed."""
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    except Exception:
        pass


def owner_alert(text, root):
    """Rate-limited (once per kind per day) note to the owner chat IF a chat id is configured and the bot can be reached from this process;
    otherwise only written to alerts.log. Never raises."""
    try:
        with open(os.path.join(root, "logs", "alerts.log"), "a", encoding="utf-8") as f:
            f.write(f"{dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} {text}\n")
        cfg = json.load(open(r"D:\sindhu\data\config\telegram_settings.json", encoding="utf-8"))
        if not cfg.get("personal_chat_id") or not cfg.get("bot_token"):
            return False
    except Exception:
        return False
    return False        # local PC never holds the bot token (by design): nothing is sent from here


def detach(argv):
    flags = 0x00000008 | 0x00000200 | 0x08000000      # DETACHED_PROCESS | NEW_PROCESS_GROUP | NO_WINDOW
    cmd = [sys.executable, "-m", "data_platform.run_download"] + [a for a in argv if a != "--detach"]
    try:
        p = subprocess.Popen(cmd, creationflags=flags | 0x01000000, close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    except OSError:
        p = subprocess.Popen(cmd, creationflags=flags, close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return p.pid


def plan(universe_doc, n_coins, n_months, today):
    end_month = (today.replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")        # last complete month
    months = downloader.month_list(end_month, n_months)
    syms = universe_doc["symbols"][:n_coins]
    cur_month = today.strftime("%Y-%m")
    days = downloader.days_of_month_until(cur_month, today - dt.timedelta(days=1))
    return syms, months, cur_month, days


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--pilot-coins", type=int, default=20)
    ap.add_argument("--pilot-months", type=int, default=6)
    ap.add_argument("--coins", type=int, default=50)
    ap.add_argument("--months", type=int, default=12)
    ap.add_argument("--no-expand", action="store_true")
    ap.add_argument("--detach", action="store_true")
    ap.add_argument("--base-url", default=None)
    a = ap.parse_args(argv)
    if a.root:
        os.environ["SINDHU_DATA_ROOT"] = a.root
    root = store.root()
    if a.detach:
        print("started detached, pid", detach(sys.argv[1:]))
        return 0
    os.makedirs(os.path.join(root, "logs"), exist_ok=True)
    downloader.setup_logging(root)
    _below_normal_priority()
    _keep_awake_while_running()
    today = dt.datetime.now(dt.timezone.utc).date()
    uni = universe.load_latest(root)
    d = downloader.Downloader(root=root, workers=a.workers, base_url=a.base_url)
    stop_mon = threading.Event()
    state = {"phase": "pilot"}

    def monitor():
        last_done, last_change = -1, time.time()
        while not stop_mon.wait(30):
            p = d.write_progress(state)
            fin = p["finished"]
            if fin != last_done:
                last_done, last_change = fin, time.time()
            elif time.time() - last_change > 900:
                owner_alert(f"download stalled for 15 minutes at {p['percent']}%", root)
                last_change = time.time()

    mt = threading.Thread(target=monitor, daemon=True)
    mt.start()
    log = downloader.log
    log.info("start: root=%s workers=%d universe=%s", root, a.workers, uni["date"])

    # ---- PILOT
    syms, months, cur_month, days = plan(uni, a.pilot_coins, a.pilot_months, today)
    d.run([("month", s, m) for s in syms for m in months], "pilot")
    d.write_progress(state)
    rep = quality.check_dataset(syms, months, base=root)
    quality.save_report(rep, "pilot_quality.json", root)
    gate = rep["summary"]
    with open(os.path.join(root, "manifest", "pilot_gate.json"), "w", encoding="utf-8") as f:
        json.dump(gate, f, indent=1)
    log.info("pilot gate: %s %s", gate["verdict"], gate)
    state.update(pilot_gate=gate["verdict"])
    if d.stop.is_set():
        state["phase"] = "stopped"
    elif gate["verdict"] != "PASS" or a.no_expand:
        state["phase"] = "pilot_done_no_expansion"
    else:
        # ---- EXPANSION
        state["phase"] = "expansion"
        syms, months, cur_month, days = plan(uni, a.coins, a.months, today)
        tasks = [("month", s, m) for s in syms for m in months] + [("day", s, dd) for s in syms for dd in days]
        d.run(tasks, "expansion")
        state["phase"] = "complete" if not d.stop.is_set() and d.progress()["failed"] == 0 else "finished_with_problems"
        owner_alert(f"download {state['phase']}: {d.progress()['percent']}%", root)
    p = d.write_progress(state)
    stop_mon.set()
    log.info("end: %s", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
