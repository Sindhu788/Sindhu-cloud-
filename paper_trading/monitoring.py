"""Owner-chat monitoring: stale data, stalled scanner, stopped engine, Telegram failures, error spikes, DB down, restarts,
plus a short daily health summary.

Rules (owner decisions):
  * Alerts go ONLY to the owner's private chat (telegram_bot.send_private_message -> personal_chat_id). Never to the
    public signal channel/groups. If personal_chat_id is not configured nothing is sent (reported as "no owner chat").
  * Every alert code is rate limited (default once per 60 min) and a single "recovered" message follows when the
    condition clears. The limiter state is persisted (cloud_settings) so a Render restart does not re-send.
  * Nothing here changes a gate: stale data is already blocked by paper_trading.market_data_guard; this only TELLS the owner.
"""
import os
import time
from datetime import datetime, timedelta, timezone

DEFAULT_INTERVAL_MIN = 60
STALE_STREAK_TO_ALERT = 5          # consecutive 60 s checks with fresh-data rejections
RECOVER_STREAK = 2                 # consecutive clean checks before "recovered"
SCAN_STALL_MIN = int(os.environ.get("SINDHU_SCAN_STALL_MIN", "20"))
SEND_FAIL_THRESHOLD = 3
ERROR_SPIKE_SCANS = 3
_STATE_KEY = "owner_alert_state"
CODE_INTERVAL_MIN = {"restarted": 360}   # a free instance restarts on every wake: tell the owner at most every 6 h


class Limiter:
    """Per-code rate limit with optional persistence (get_fn() -> dict, put_fn(dict))."""

    def __init__(self, get_fn=None, put_fn=None, clock=time.time):
        self._get, self._put, self._clock = get_fn, put_fn, clock
        self._mem = {}

    def _load(self):
        if self._get:
            try:
                saved = self._get() or {}
                self._mem.update({k: float(v) for k, v in saved.items()})
            except Exception:
                pass
        return self._mem

    def allow(self, code, interval_min=DEFAULT_INTERVAL_MIN):
        last = self._load().get(code)
        return last is None or self._clock() - last >= interval_min * 60

    def mark(self, code):
        self._mem[code] = self._clock()
        if self._put:
            try:
                self._put(dict(self._mem))
            except Exception:
                pass


class Watchdog:
    """Pure state machine. check(snapshot) -> list of (kind, code, message) where kind is 'alert' or 'recovery'."""

    def __init__(self):
        self.stale_streak = 0
        self.clean_streak = 0
        self.active = set()          # alert codes currently raised

    def check(self, snap):
        out = []

        def raise_(code, msg):
            if code not in self.active:
                self.active.add(code)
            out.append(("alert", code, msg))

        def clear(code, msg):
            if code in self.active:
                self.active.discard(code)
                out.append(("recovery", code, msg))

        # Free-plan instances are stopped when idle and started fresh on the next request. For WAKE_GRACE seconds after a (re)start,
        # or after the process was frozen, empty live-candle caches and a first cold scan are EXPECTED, so the stale-data and
        # scanner-stalled alerts neither fire nor count. Real problems outlive the grace period and then alert as usual.
        grace = bool(snap.get("in_wake_grace"))

        # --- stale data (needs N consecutive checks; recovery needs M clean ones)
        if grace:
            pass
        elif snap.get("stale_rejections_recent", 0) > 0:
            self.stale_streak += 1
            self.clean_streak = 0
        else:
            self.clean_streak += 1
            if self.clean_streak >= RECOVER_STREAK:
                self.stale_streak = 0
        if grace:
            pass
        elif self.stale_streak >= STALE_STREAK_TO_ALERT and snap.get("stale_rejections_recent", 0) > 0:
            raise_("stale_data", f"Live market data has been stale/empty for {self.stale_streak} checks in a row. "
                                 "New signals are blocked until it is fresh again.")
        elif self.stale_streak == 0:
            clear("stale_data", "Market data is fresh again. Signals can resume.")

        # --- scanner stalled / engine stopped
        # "age" = time since the scanner last showed ANY sign of life (a finished scan, or progress inside a running scan, or the
        # process start). A long cold scan that is still moving is slow, not stalled.
        age = snap.get("seconds_since_activity", snap.get("seconds_since_last_scan"))
        if snap.get("engine_enabled") and not snap.get("engine_running"):
            raise_("engine_stopped", "Paper trading engine is enabled but NOT running.")
        else:
            clear("engine_stopped", "Paper trading engine is running again.")
        if grace:
            pass
        elif snap.get("engine_running") and age is not None and age > SCAN_STALL_MIN * 60:
            ping = snap.get("seconds_since_external_ping")
            ping_txt = ("no external pinger seen since this restart" if ping is None
                        else f"last external ping {int(ping // 60)} min ago")
            raise_("scanner_stalled", f"The engine is running but showed no scan progress for {int(age // 60)} min "
                                      f"(limit {SCAN_STALL_MIN}); {ping_txt}.")
        elif age is not None and age <= SCAN_STALL_MIN * 60:
            clear("scanner_stalled", "Scanner is making progress again.")

        # --- Telegram send failures
        if snap.get("telegram_failures_recent", 0) >= SEND_FAIL_THRESHOLD:
            raise_("telegram_failures", f"{snap['telegram_failures_recent']} Telegram sends failed in the last 30 min.")
        else:
            clear("telegram_failures", "Telegram sends are working again.")

        # --- error spike
        if snap.get("consecutive_failed_scans", 0) >= ERROR_SPIKE_SCANS:
            raise_("error_spike", f"The last {snap['consecutive_failed_scans']} scans all ended with errors.")
        else:
            clear("error_spike", "Scans are completing without errors again.")

        # --- database
        if snap.get("db_ok") is False:
            raise_("db_unreachable", "The database is unreachable.")
        else:
            clear("db_unreachable", "The database is reachable again.")

        # --- restart (one-shot)
        if snap.get("just_restarted"):
            out.append(("alert", "restarted", "The Cloud server restarted (deploy, crash or wake from sleep)."))
        return out


def deliver(events, limiter, send, prefix="SINDHU monitor"):
    """Send events to the owner chat with rate limiting. Recoveries bypass the limiter but only follow a sent alert.
    Returns list of (code, sent_bool)."""
    results = []
    for kind, code, msg in events:
        key = code if kind == "alert" else f"recovery:{code}"
        if kind == "alert" and not limiter.allow(code, CODE_INTERVAL_MIN.get(code, DEFAULT_INTERVAL_MIN)):
            results.append((code, False))
            continue
        if kind == "recovery" and limiter.allow(code, DEFAULT_INTERVAL_MIN * 24 * 365):
            results.append((code, False))   # no prior alert sent -> nothing to recover from
            continue
        ok = bool(send(f"[{prefix}] {'RECOVERED' if kind == 'recovery' else 'ALERT'}: {msg}"))
        if ok and kind == "alert":
            limiter.mark(code)
        if ok and kind == "recovery":
            limiter.mark(key)
        results.append((code, ok))
    return results


# --------------------------------------------------------------------------- real-world wiring

def _persistent_limiter():
    """Postgres (Cloud): cloud_settings row. SQLite (local): a small json in the config folder."""
    from data_engine import db_backend, storage, config as base_config

    def get():
        if db_backend.IS_POSTGRES:
            return storage.get_cloud_setting(_STATE_KEY) or {}
        return base_config.load_or_seed("owner_alert_state.json", {})

    def put(d):
        if db_backend.IS_POSTGRES:
            storage.save_cloud_setting(_STATE_KEY, d, datetime.now(timezone.utc).isoformat())
        else:
            base_config.save_config("owner_alert_state.json", d)

    return Limiter(get, put)


def _owner_send(text):
    from paper_trading import telegram_bot
    res = telegram_bot.send_private_message(text)
    return bool(res.get("ok"))


def collect_snapshot(engine_obj, started_recently=False):
    """Read-only facts about the running system."""
    from data_engine import storage
    from paper_trading import config as pt_config, market_data_guard
    snap = {"db_ok": True}
    try:
        with storage.get_conn() as c:
            c.execute("SELECT 1").fetchone()
            cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
            try:
                snap["telegram_failures_recent"] = c.execute(
                    "SELECT COUNT(*) FROM telegram_message_log WHERE success = 0 AND sent_at >= ? "
                    "AND COALESCE(error,'') NOT LIKE '%already sent%' AND COALESCE(error,'') NOT LIKE '%too stale%'",
                    (cutoff,)).fetchone()[0]
            except Exception:
                snap["telegram_failures_recent"] = 0
            try:
                rows = c.execute("SELECT outcome FROM paper_scan_log ORDER BY started_at DESC LIMIT ?",
                                 (ERROR_SPIKE_SCANS,)).fetchall()
                n = 0
                for r in rows:
                    if r[0] in ("error", "partial"):
                        n += 1
                    else:
                        break
                snap["consecutive_failed_scans"] = n if len(rows) >= ERROR_SPIKE_SCANS else 0
            except Exception:
                snap["consecutive_failed_scans"] = 0
    except Exception:
        snap["db_ok"] = False
    summary = market_data_guard.rejection_summary(window_seconds=300)
    snap["stale_rejections_recent"] = sum(v for k, v in summary["by_reason"].items() if "Stale" in k or "empty" in k)
    try:
        snap["engine_enabled"] = bool(pt_config.load().get("engine_enabled"))
    except Exception:
        snap["engine_enabled"] = False
    snap["engine_running"] = bool(getattr(engine_obj, "_running", False))
    last = getattr(engine_obj, "_last_tick_at", None)
    snap["seconds_since_last_scan"] = None
    if last:
        try:
            snap["seconds_since_last_scan"] = time.time() - datetime.fromisoformat(str(last).replace("Z", "+00:00")).timestamp()
        except Exception:
            pass
    snap["just_restarted"] = started_recently
    # Sleep-awareness (see Watchdog.check): sign-of-life age, wake grace, external pinger.
    try:
        from paper_trading import instance_state
        now = time.time()
        marks = [now - instance_state.PROCESS_STARTED_AT]
        if snap["seconds_since_last_scan"] is not None:
            marks.append(snap["seconds_since_last_scan"])
        act = getattr(engine_obj, "_scan_activity_ts", None)
        if act:
            marks.append(now - act)
        snap["seconds_since_activity"] = min(marks)
        snap["in_wake_grace"] = instance_state.in_wake_grace(now) or _frozen_recently(now)
        snap["seconds_since_external_ping"] = instance_state.ping_summary(now)["seconds_since_last_external_ping"]
    except Exception:
        pass
    return snap


_last_check_wall = None
FROZEN_GAP_SECONDS = 180      # the watchdog runs about once a minute; a much longer gap means the process was frozen/suspended
_grace_until = 0.0


def _frozen_recently(now):
    """True while inside a wake grace opened by a long gap between watchdog runs (process was suspended, e.g. a sleeping host)."""
    global _last_check_wall, _grace_until
    if _last_check_wall is not None and now - _last_check_wall > FROZEN_GAP_SECONDS:
        _grace_until = now + 600
    _last_check_wall = now
    return now < _grace_until


_watchdog = Watchdog()
_limiter = None
_first_tick = True


def watchdog_tick(engine_obj, send=None, limiter=None):
    """Called about once a minute from the engine loop. Never raises."""
    global _limiter, _first_tick
    try:
        if limiter is None:
            if _limiter is None:
                _limiter = _persistent_limiter()
            limiter = _limiter
        snap = collect_snapshot(engine_obj, started_recently=_first_tick)
        _first_tick = False
        events = _watchdog.check(snap)
        if not events:
            return []
        return deliver(events, limiter, send or _owner_send)
    except Exception:
        return []


# --------------------------------------------------------------------------- daily summary

def build_daily_summary(conn, now=None):
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(hours=24)).isoformat()
    q = lambda sql, p=(): conn.execute(sql, p).fetchall()
    scans = q("SELECT COUNT(*), COALESCE(SUM(errors),0) FROM paper_scan_log WHERE started_at >= ?", (since,))[0] if _has(conn, "paper_scan_log") else (0, 0)
    sent = q("SELECT COUNT(*) FROM telegram_message_log WHERE success = 1 AND trigger_type = 'automatic' AND sent_at >= ?", (since,))[0][0]
    failed = q("SELECT COUNT(*) FROM telegram_message_log WHERE success = 0 AND sent_at >= ?", (since,))[0][0]
    reasons = q("SELECT substr(reason,1,38), COUNT(*) FROM paper_decision_log WHERE created_at >= ? AND decision != 'opened' "
                "GROUP BY 1 ORDER BY 2 DESC LIMIT 3", (since,))
    opened = q("SELECT COUNT(*) FROM paper_decision_log WHERE created_at >= ? AND decision = 'opened'", (since,))[0][0]
    pnl = q("SELECT COALESCE(SUM(realized_pnl_total),0), COUNT(*) FROM paper_account_state")[0]
    restarts = q("SELECT COUNT(*) FROM server_restart_log WHERE started_at >= ?", (since,))[0][0] if _has(conn, "server_restart_log") else None
    top = "; ".join(f"{r[0]} x{r[1]}" for r in reasons) or "none"
    return (f"Daily health (24 h): scans {scans[0]} (scan errors {scans[1]}), trades opened {opened}, signals sent {sent}, "
            f"Telegram failures {failed}. Top rejections: {top}. Paper realized PnL total {round(pnl[0], 2)} across {pnl[1]} books. "
            f"Server restarts: {restarts if restarts is not None else 'n/a'}.")


def _has(conn, table):
    try:
        conn.execute(f"SELECT 1 FROM {table} LIMIT 1")
        return True
    except Exception:
        return False


def maybe_send_daily_summary(send=None, limiter=None, now=None, hour_utc=18):
    """Once per UTC day, after hour_utc (default 18:00 UTC = 23:00 PKT). Returns True if sent."""
    from data_engine import storage
    now = now or datetime.now(timezone.utc)
    if now.hour < hour_utc:
        return False
    limiter = limiter or _limiter or _persistent_limiter()
    code = "daily:" + now.strftime("%Y-%m-%d")
    if not limiter.allow(code, 24 * 60):
        return False
    with storage.get_conn() as c:
        text = build_daily_summary(c, now)
    ok = bool((send or _owner_send)("[SINDHU monitor] " + text))
    if ok:
        limiter.mark(code)
    return ok
