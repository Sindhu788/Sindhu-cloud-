"""Master 15-Item task, Item 6: Emergency Downtime Alert.

If SINDHU's cloud deployment goes down, nothing INSIDE that same process
can notify anyone -- the whole point of "down" is that nothing there is
running any more. This has to be an external watchdog: a small, separate
script that pings the cloud /health endpoint from somewhere else (this
local machine) and DMs the CEO's own Telegram (never the public/shared
channel -- see telegram_bot.send_private_message) when it stops
responding.

Deliberately the simplest reliable option that needs NO new paid account
or service: reuses the Telegram bot/token this project already has, and
runs as a plain scheduled script (Windows Task Scheduler, "every 5
minutes") rather than standing up a second always-on process of its own
to watch the first one. The one real tradeoff, stated plainly rather than
hidden: this only works while THIS machine is on and the task is
scheduled -- a genuinely 24/7-independent watchdog would need a separate
free external uptime service (e.g. healthchecks.io / UptimeRobot) pinging
/health directly, which needs a new account this script cannot create on
its own. Recommended as a possible upgrade later; not built by default
since the task asked to avoid a new account if avoidable.

State (data/checkpoints/uptime_watchdog_state.json) is kept between runs
so consecutive-failure counting and "only alert once per outage, then
once on recovery" work across separate scheduled invocations, not just
within one process's lifetime.

Usage: python scripts/uptime_watchdog.py [--url URL] [--threshold N]
"""
import sys
import os
import json
import argparse
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

DEFAULT_HEALTH_URL = "https://sindhu-cloud-1.onrender.com/health"
DEFAULT_FAILURE_THRESHOLD = 3  # consecutive failed checks before alerting -- avoids a single transient blip crying wolf
STATE_PATH = os.path.join("data", "checkpoints", "uptime_watchdog_state.json")
CHECK_TIMEOUT_SECONDS = 15


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"consecutive_failures": 0, "alerted_this_outage": False, "last_check": None, "last_status": None}


def _save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def check_health(url):
    """Returns (is_up: bool, detail: str). is_up requires BOTH a real HTTP
    200 AND the JSON body's own status=="ok" -- a 200 with a broken body
    is not treated as healthy."""
    try:
        resp = requests.get(url, timeout=CHECK_TIMEOUT_SECONDS)
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}"
        data = resp.json()
        if data.get("status") != "ok":
            return False, f"unexpected /health body: {data}"
        return True, json.dumps(data)
    except requests.RequestException as e:
        return False, f"unreachable: {e!r}"


def run_check(url=DEFAULT_HEALTH_URL, threshold=DEFAULT_FAILURE_THRESHOLD, send_fn=None):
    """send_fn(text) -> {"ok": bool, "error": str|None}, injected so tests
    can verify the alert-decision logic with a real simulated failure
    (a genuinely unreachable URL) without needing a live Telegram send.
    Defaults to the real telegram_bot.send_private_message."""
    if send_fn is None:
        from paper_trading.telegram_bot import send_private_message
        send_fn = send_private_message

    state = _load_state()
    is_up, detail = check_health(url)
    now = _now_iso()
    result = {"checked_at": now, "url": url, "is_up": is_up, "detail": detail, "alert_sent": None}

    if is_up:
        if state.get("alerted_this_outage"):
            # Was down long enough to alert, now recovered -- one
            # recovery message, then reset for the next possible outage.
            send_result = send_fn(
                f"✅ SINDHU is back UP.\n\n{url}\n{detail}\nRecovered at {now} UTC."
            )
            result["alert_sent"] = "recovery"
            result["send_result"] = send_result
        state["consecutive_failures"] = 0
        state["alerted_this_outage"] = False
    else:
        state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
        if state["consecutive_failures"] >= threshold and not state.get("alerted_this_outage"):
            send_result = send_fn(
                f"⚠️ SINDHU appears to be DOWN.\n\n{url}\n"
                f"{state['consecutive_failures']} consecutive failed health checks.\n"
                f"Last error: {detail}\nDetected at {now} UTC."
            )
            result["alert_sent"] = "down"
            result["send_result"] = send_result
            state["alerted_this_outage"] = True

    state["last_check"] = now
    state["last_status"] = "up" if is_up else "down"
    _save_state(state)
    result["state_after"] = state
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_HEALTH_URL)
    parser.add_argument("--threshold", type=int, default=DEFAULT_FAILURE_THRESHOLD)
    args = parser.parse_args()
    result = run_check(args.url, args.threshold)
    print(json.dumps(result, indent=2, default=str))
