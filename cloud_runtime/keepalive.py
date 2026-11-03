"""Optional self keep-alive for hosts that put idle services to sleep (Render free plan).

Off by default. Set SINDHU_KEEPALIVE_URL to the service's own public base URL
(e.g. https://sindhu-cloud-1.onrender.com) to ping its /health every
SINDHU_KEEPALIVE_MINUTES (default 10). A request through the public URL counts as inbound
traffic, so the service is not put to sleep and the paper engine / Telegram sweep keep running.
Note: free instance hours are shared across all free services of an account (750 h/month).
"""
import os
import threading
import time
import urllib.request

_started = False


def _ping(url):
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=30) as r:
            return r.status
    except Exception:
        return None


def start_if_configured(log=print):
    global _started
    url = os.environ.get("SINDHU_KEEPALIVE_URL", "").strip()
    if not url or _started:
        return False
    try:
        minutes = max(1.0, float(os.environ.get("SINDHU_KEEPALIVE_MINUTES", "10")))
    except ValueError:
        minutes = 10.0
    _started = True

    def loop():
        while True:
            time.sleep(minutes * 60)
            _ping(url)

    threading.Thread(target=loop, daemon=True, name="keepalive").start()
    log(f"[cloud-runtime] keep-alive enabled: pinging own /health every {minutes:g} min")
    return True
