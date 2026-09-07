"""Master 15-Item task, Item 8: Mobile Push Notifications decision.

Decided: ntfy.sh over browser Web Push. Web Push needs a real browser
subscription flow (service worker registration, VAPID keys, a
subscription object stored per device, and the dashboard tab open at
least once to register) -- meaningfully more moving parts for a solo,
part-time project. ntfy.sh needs none of that: pick a topic name (an
arbitrary string, effectively a shared secret -- no account, no signup,
on either the sending or receiving side for basic use) and POST to
https://ntfy.sh/<topic>; the CEO's phone gets a real push notification
via the free ntfy app subscribed to that same topic name. Simpler path,
exactly as this task's own instructions asked for.

Security note (documented, not hidden): a free ntfy.sh topic is a public
server -- anyone who learns the topic name can subscribe to it (read) or
publish to it (write). This is acceptable for one-way informational
alerts (nothing secret or actionable-without-context is ever sent here),
same threat model as the topic name itself being the only real
protection. Self-hosting ntfy, or ntfy.sh's own paid tier, would add
authentication if that ever becomes a real concern -- not needed for
this task's scope.
"""
import requests

from paper_trading import config as pt_config

NTFY_BASE_URL = "https://ntfy.sh"
_REQUEST_TIMEOUT_SECONDS = 15


def send_push(title, message, priority="default"):
    """Real HTTP POST to ntfy.sh -- no simulation. Returns
    {"ok": bool, "error": str|None}, same shape as telegram_bot's send
    functions for consistency. priority: ntfy's own scale
    ("min"/"low"/"default"/"high"/"urgent") -- "urgent" also makes the
    phone bypass silent/DND mode, reserved for the Emergency Downtime
    Alert, not routine signals.

    If ntfy_topic has never been configured, returns ok=False with a
    clear reason rather than silently no-op'ing or guessing a topic."""
    topic = pt_config.load().get("ntfy_topic")
    if not topic:
        return {"ok": False, "error": "ntfy_topic is not configured yet -- Settings > Notifications"}
    try:
        resp = requests.post(
            f"{NTFY_BASE_URL}/{topic}",
            data=message.encode("utf-8"),
            headers={"Title": title, "Priority": priority},
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        if resp.status_code == 200:
            return {"ok": True, "error": None}
        return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except requests.RequestException as e:
        return {"ok": False, "error": repr(e)}
