"""Telegram Integration (Section A): a self-contained sending layer built
entirely on top of already-verified features (Confluence Scoring, Manual
Override, Drawdown Protection, Correlation Warnings, Trade Reasoning) --
nothing here computes a new trade decision or touches the trading loop,
it only formats and sends messages about decisions already made elsewhere.

Security: the bot token is stored in data/config/telegram_settings.json
(same JSON-config pattern as every other setting in this project) and is
NEVER returned by any GET endpoint or written to the log -- only a
"token_configured": true/false boolean is ever exposed after saving.

Proxy support: api.telegram.org is network-blocked in some countries at
the ISP/network level (TLS-handshake/SNI-based interference -- confirmed
via direct diagnostic testing, not a code-side timeout bug: DNS resolves
fine, a raw TCP connect succeeds instantly, but the actual HTTPS exchange
with that specific host stalls/resets while every other host works
normally). proxy_url (same write-only treatment as bot_token -- never
returned in plaintext, since it may embed a username:password) routes
ALL Telegram API calls through a configured SOCKS5 or HTTP proxy instead
of connecting directly, so this works unattended/24-7 without a manually
toggled VPN. Accepts any URL scheme Python's `requests` library itself
understands: "socks5://[user:pass@]host:port" (requires the PySocks
package, already added to requirements.txt) or "http://[user:pass@]host:port".
"""

import math
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests

from data_engine import config as base_config, db_backend, storage, feature_toggles
from paper_trading import confluence as confluence_mod, pattern_stats, signal_explainer
from paper_trading import strategy_groups

# Lightweight cloud runner support: on a fresh deploy (or any restart of a
# container with no persistent volume mounted at data/config/), the local
# telegram_settings.json this file normally persists to does not exist yet
# -- these two env vars, if set, seed the very first save of that file so
# the bot works immediately after deploy without a manual dashboard step.
# Once the file exists, save_settings()/load_settings() read and write it
# exactly as before; these env vars are consulted only for that first
# seed (data_engine.config.load_or_seed's existing behavior -- the JSON
# file wins over these defaults on every call after the first). Local
# laptop behavior is unchanged when both env vars are unset (the
# overwhelmingly common case: the CEO configures the bot from the
# dashboard's Telegram Settings screen instead).
_DEFAULTS = {
    "bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
    "channel_id": os.environ.get("TELEGRAM_CHANNEL_ID", ""),
    "master_send_enabled": True,  # Telegram Dashboard's master switch -- see _master_enabled() below
    "auto_send_enabled": False,   # non-negotiable: OFF by default
    "auto_send_min_confluence_ratio": 1.0,  # require ALL counted factors aligned (e.g. 4/4) by default -- conservative
    # Batch 6, Task 3: the ratio alone can be satisfied by as few as 1/1
    # counted factor (the other 3 were "neutral" -- not enough data, so
    # excluded from the denominator) -- a real signal could clear a
    # 100% ratio on genuinely thin support. High Confidence now ALSO
    # requires this many factors to have been counted AND aligned, on
    # top of the ratio -- tightens the bar using the same already-
    # computed confluence numbers, no new factors, HIGH tier only (the
    # Low tier's fallback purpose and the 25-trade Wilson gate are both
    # untouched).
    "auto_send_min_confluence_count": 3,
    "rate_limit_per_hour": 10,
    "send_close_followups": True,
    "proxy_enabled": False,
    "proxy_url": "",  # e.g. "socks5://user:pass@host:1080" or "http://user:pass@host:8080"
    # Batch 3, Task 4 (Part B) -- Signal Freshness Gate: a signal is
    # useless once price has likely moved past the intended entry.
    "signal_freshness_minutes": 15,   # a signal older than this is withheld, not sent as normal
    "signal_price_drift_pct": 0.5,    # if live price has moved this % away from entry_price, withheld
    # Batch 5, Task 3: which language new signal messages are written in --
    # "ur" (Roman Urdu, the CEO's everyday register) or "en". Deterministic
    # template choice, not an AI translation call.
    "language": "ur",
    # Confidence filtering: only High Confidence tier signals (evaluate_
    # auto_send -- full confluence + the 25-trade Wilson gate) were sent to
    # Telegram while this defaulted to True. Flipped to False, 2026-09-12:
    # at real trading scale (~150 strategies sharing ~80 trades/day) almost
    # no single (strategy, coin, condition) pattern reaches 25 trades for
    # weeks, so High tier essentially never fired and zero messages were
    # reaching the channel. Low tier (evaluate_auto_send_low_tier) still
    # requires the full confluence bar and non-negative live PnL -- it only
    # skips the sample-size/statistical-significance check -- so this does
    # NOT touch the shared Wilson-gate constant (paper_trading.pattern_stats.
    # MIN_SAMPLE_SIZE) that Evolution/validation-gate/auto-avoid/lesson-
    # auto-apply also rely on; it only changes which already-computed tier
    # gets sent to Telegram. Kept as a setting (not hardcoded) so it can be
    # flipped back from the Settings page by anyone who wants High-Confidence
    # -only again.
    "auto_send_high_confidence_only": False,
    # Grand Feature Expansion, Phase 2 Feature 22: Multi-Channel Support --
    # {strategy_id: channel_id} overrides. A strategy with no entry here
    # keeps going to the one default `channel_id` above, exactly as
    # before this feature; this is purely additive routing, not a second
    # bot token or a second set of credentials.
    "strategy_channel_overrides": {},
    # Grand Feature Expansion, Phase 2 Feature 24: Silent Hours / Do-Not-
    # Disturb. UTC hour:minute strings (this codebase is UTC-everywhere,
    # see _now_iso() -- no timezone library needed, the CEO just accounts
    # for their own UTC offset when setting these). Signals are still
    # generated, sent, and fully logged during this window -- only the
    # phone notification is muted (Telegram's own disable_notification
    # flag), never a queued/delayed/withheld send.
    "silent_hours_enabled": False,
    "silent_hours_start_utc": "23:00",
    "silent_hours_end_utc": "07:00",
    # Grand Master Batch, Phase 4 Item 15: Quiet Mode -- a manual, one-off
    # "mute me for a day" override, distinct from the recurring nightly
    # schedule above. None/absent means off. An ISO timestamp means muted
    # until that moment. Unlike Silent Hours (Item 5, below), this is a
    # deliberate CEO action covering literally every notification with no
    # high-confidence exception -- see is_quiet_mode_active()/_effective_
    # silent() for why the two behave differently.
    "quiet_mode_until": None,
    # Master 15-Item task, Items 6 & 10: the CEO's own personal Telegram
    # chat id (a DIRECT MESSAGE with the bot, never the public/shared
    # `channel_id` above) -- used for anything that must stay private:
    # Emergency Downtime Alerts and the Weekly/Monthly performance
    # reports. Same bot token, just a different destination via
    # _raw_send's existing channel_id_override parameter -- not a second
    # bot, no new credentials. Empty until the CEO provides it (one-time
    # manual step -- Telegram gives no API way to discover a user's chat
    # id without them messaging the bot first).
    "personal_chat_id": "",
    # Phase 2.3 (5-Phase Improvement Batch): Minimum Take-Profit Distance
    # Filter -- the CEO executes every trade by hand, so a signal whose TP
    # sits a fraction of a percent from entry leaves no realistic reaction
    # window. Threshold depends on the signal's own trading style (derived
    # from its timeframe -- see trading_style_for_timeframe), each
    # independently configurable rather than one hardcoded number, using
    # the LOW end of each style's standard TP-distance range as the
    # minimum acceptable: Scalping ~0.5-1%, Intraday ~1-2%, Swing ~3-5%.
    # No per-strategy leverage value exists for live paper-trading
    # strategies anywhere in this codebase (only backtest settings and the
    # unrelated external_signals ingest path have one), so this is NOT
    # leverage-adjusted -- documented here rather than silently guessed.
    "min_tp_distance_filter_enabled": True,
    "min_tp_distance_pct_scalping": 0.5,
    "min_tp_distance_pct_intraday": 1.0,
    "min_tp_distance_pct_swing": 3.0,
    "min_tp_distance_pct_default": 1.0,  # used when a style can't be determined from the timeframe
    # Phase 3.4: an ADDITIONAL filter layer on top of (never a replacement
    # for) the existing Confluence ratio/count and Wilson 25-trade gates --
    # those still run exactly as before. Uses paper_trading.confidence.
    # score's own 0-100 ranking value, already computed and stored on
    # every position. 0 = disabled (no filtering at all) so this changes
    # nothing until the CEO deliberately raises it from Settings.
    "min_confidence_pct_to_send": 0,
}

DISCLAIMER = ("This is an experimental signal from a system still under development. "
              "Not financial advice. Trade at your own risk.")

# Telegram-facing brand name only -- every message sent to the channel
# says "Trade Vision" instead of "SINDHU". This is purely cosmetic and
# purely scoped to this file's message text: the dashboard, database,
# internal labels, logs, and every other user-facing surface keep the
# real "SINDHU" name unchanged. Telegram's own bot display name/username
# (set via @BotFather) is a Telegram-account-level setting outside this
# codebase and isn't something a code change can alter.
TELEGRAM_BRAND = "Trade Vision"

_UNSET = object()  # sentinel: "caller didn't pass live_price, fetch it" vs. explicit None ("already tried, no price")

_API_CONNECT_TIMEOUT = 15
_API_READ_TIMEOUT = 30
_API_MAX_ATTEMPTS = 3
_API_RETRY_BACKOFF_SECONDS = 2


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


_SETTINGS_KEY = "telegram_settings"


def load_settings():
    # Cloud persistence: same reasoning as paper_trading/config.py -- on a
    # host with DATABASE_URL set, these settings live in Postgres
    # (cloud_settings) instead of the local file, which is ephemeral on
    # most cloud hosts and would otherwise silently revert a CEO's saved
    # choice (auto-send on/off, confidence thresholds, ...) after every
    # restart/redeploy/sleep-wake. Local laptop behavior is unchanged.
    if db_backend.IS_POSTGRES:
        saved = storage.get_cloud_setting(_SETTINGS_KEY)
        merged = dict(_DEFAULTS)
        if saved:
            merged.update(saved)
        # Bug fix (URGENT, 2026-09-06): if a telegram_settings row was ever
        # saved to cloud_settings BEFORE TELEGRAM_BOT_TOKEN/TELEGRAM_
        # CHANNEL_ID existed as env vars (e.g. an earlier deploy, or simply
        # loading/saving the Settings page once with nothing configured
        # yet), that row explicitly persists bot_token/channel_id as empty
        # strings -- merged.update(saved) above then permanently shadows
        # the env-var defaults forever, even after the env vars are added
        # and the service redeployed, since saved always wins. Confirmed
        # live: CEO added both env vars and redeployed, dashboard still
        # showed "Bot Set Up: No" / "Channel Set: No". An empty string was
        # never a deliberately-configured value, so fall back to the env
        # var specifically in that case -- never overrides a real saved
        # (non-empty) value, so an intentional later change/clear via the
        # dashboard is still fully respected.
        if not merged.get("bot_token") and os.environ.get("TELEGRAM_BOT_TOKEN"):
            merged["bot_token"] = os.environ["TELEGRAM_BOT_TOKEN"]
        if not merged.get("channel_id") and os.environ.get("TELEGRAM_CHANNEL_ID"):
            merged["channel_id"] = os.environ["TELEGRAM_CHANNEL_ID"]
        return merged
    return base_config.load_or_seed("telegram_settings.json", _DEFAULTS)


def save_settings(**fields):
    settings = load_settings()
    settings.update({k: v for k, v in fields.items() if v is not None})
    if db_backend.IS_POSTGRES:
        storage.save_cloud_setting(_SETTINGS_KEY, settings, _now_iso())
    else:
        base_config.save_config("telegram_settings.json", settings)
    return settings


def public_settings():
    """Safe-to-display view -- never includes the raw token."""
    s = load_settings()
    return {
        "token_configured": bool(s.get("bot_token")),
        "channel_id": s.get("channel_id", ""),
        "master_send_enabled": s.get("master_send_enabled", True),
        "auto_send_enabled": s.get("auto_send_enabled", False),
        "auto_send_min_confluence_ratio": s.get("auto_send_min_confluence_ratio", 1.0),
        "auto_send_min_confluence_count": s.get("auto_send_min_confluence_count", _DEFAULTS["auto_send_min_confluence_count"]),
        "rate_limit_per_hour": s.get("rate_limit_per_hour", 10),
        "send_close_followups": s.get("send_close_followups", True),
        "proxy_enabled": s.get("proxy_enabled", False),
        "proxy_configured": bool(s.get("proxy_url")),
        "signal_freshness_minutes": s.get("signal_freshness_minutes", _DEFAULTS["signal_freshness_minutes"]),
        "signal_price_drift_pct": s.get("signal_price_drift_pct", _DEFAULTS["signal_price_drift_pct"]),
        "language": s.get("language", _DEFAULTS["language"]),
        "strategy_channel_overrides": s.get("strategy_channel_overrides", {}),
        "silent_hours_enabled": s.get("silent_hours_enabled", False),
        "silent_hours_start_utc": s.get("silent_hours_start_utc", _DEFAULTS["silent_hours_start_utc"]),
        "silent_hours_end_utc": s.get("silent_hours_end_utc", _DEFAULTS["silent_hours_end_utc"]),
        # Grand Master Batch, Phase 4 Item 15: exposes both the raw value
        # (so the dashboard can show exactly when it expires) and the
        # already-computed boolean (so the dashboard never has to
        # reimplement the "is it still in the future" check itself).
        "quiet_mode_until": s.get("quiet_mode_until"),
        "quiet_mode_active": is_quiet_mode_active(),
        "personal_chat_id": s.get("personal_chat_id", ""),
        # Full System Verification Audit (2026-09-13): these existed in
        # _DEFAULTS/save_settings already but were never added here, so
        # the dashboard's own Settings page (GET /api/paper-trading/
        # telegram/settings -> this function) could never actually show
        # their real current state -- a real visibility gap, not stale
        # data, but incomplete either way.
        "auto_send_high_confidence_only": s.get("auto_send_high_confidence_only", _DEFAULTS["auto_send_high_confidence_only"]),
        "min_confidence_pct_to_send": s.get("min_confidence_pct_to_send", _DEFAULTS["min_confidence_pct_to_send"]),
        "min_tp_distance_filter_enabled": s.get("min_tp_distance_filter_enabled", _DEFAULTS["min_tp_distance_filter_enabled"]),
        "min_tp_distance_pct_scalping": s.get("min_tp_distance_pct_scalping", _DEFAULTS["min_tp_distance_pct_scalping"]),
        "min_tp_distance_pct_intraday": s.get("min_tp_distance_pct_intraday", _DEFAULTS["min_tp_distance_pct_intraday"]),
        "min_tp_distance_pct_swing": s.get("min_tp_distance_pct_swing", _DEFAULTS["min_tp_distance_pct_swing"]),
        "min_tp_distance_pct_default": s.get("min_tp_distance_pct_default", _DEFAULTS["min_tp_distance_pct_default"]),
    }


def channel_for_strategy(strategy_id):
    """Grand Feature Expansion, Phase 2 Feature 22: the destination this
    strategy's real-time signals go to -- its own override if one is
    configured, else None (meaning "use the one default channel_id"),
    exactly the shape _raw_send's channel_id_override expects."""
    if not strategy_id:
        return None
    return load_settings().get("strategy_channel_overrides", {}).get(strategy_id)


def set_strategy_channel_override(strategy_id, channel_id):
    """channel_id=None (or empty) removes the override, reverting this
    strategy to the one default channel."""
    settings = load_settings()
    overrides = dict(settings.get("strategy_channel_overrides", {}))
    if channel_id:
        overrides[strategy_id] = channel_id
    else:
        overrides.pop(strategy_id, None)
    save_settings(strategy_channel_overrides=overrides)
    return overrides


def _parse_hhmm(s):
    hh, mm = s.split(":")
    return int(hh) * 60 + int(mm)


def is_within_silent_hours(now=None):
    """Grand Feature Expansion, Phase 2 Feature 24. Handles an overnight
    window (e.g. 23:00 -> 07:00, which spans midnight) the same way a
    same-day window (e.g. 13:00 -> 14:00) does -- both are just "is the
    current minute-of-day inside [start, end)", the wraparound is simply
    whether start > end."""
    settings = load_settings()
    if not settings.get("silent_hours_enabled", False):
        return False
    now = now or datetime.now(timezone.utc)
    current = now.hour * 60 + now.minute
    try:
        start = _parse_hhmm(settings.get("silent_hours_start_utc", "23:00"))
        end = _parse_hhmm(settings.get("silent_hours_end_utc", "07:00"))
    except (ValueError, AttributeError):
        return False
    if start == end:
        return False  # a zero-width window means "always off", not "always on"
    if start < end:
        return start <= current < end
    return current >= start or current < end  # overnight wraparound


def is_quiet_mode_active(now=None):
    """Grand Master Batch, Phase 4 Item 15. True while a manual "mute me
    for a day" override (set_quiet_mode) is still in effect. Engine
    behavior is completely untouched by this -- trading keeps running
    exactly as normal, this only affects whether a notification alerts."""
    until = load_settings().get("quiet_mode_until")
    if not until:
        return False
    now = now or datetime.now(timezone.utc)
    try:
        return now < datetime.fromisoformat(until)
    except (ValueError, TypeError):
        return False


def set_quiet_mode(hours=24):
    """Starts (or extends/restarts) Quiet Mode for `hours` hours from now."""
    if hours <= 0:
        raise ValueError("hours must be positive")
    until = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
    save_settings(quiet_mode_until=until)
    return until


def clear_quiet_mode():
    """Manual early "unmute" -- also self-clears naturally once `hours`
    elapses (is_quiet_mode_active just stops returning True), but a CEO
    who wants sound back on sooner shouldn't have to wait it out.

    Bug note: save_settings(**fields) treats None as "field not provided"
    (its update() dict-comprehension filters `if v is not None`, by
    design -- so a partial save like save_settings(bot_token="x") never
    wipes out other unrelated fields) -- so save_settings(quiet_mode_
    until=None) would be silently ignored and leave the old timestamp in
    place. This writes the settings dict directly instead, the one place
    that genuinely needs None to mean "cleared", not "omitted"."""
    settings = load_settings()
    settings["quiet_mode_until"] = None
    if db_backend.IS_POSTGRES:
        storage.save_cloud_setting(_SETTINGS_KEY, settings, _now_iso())
    else:
        base_config.save_config("telegram_settings.json", settings)


def _effective_silent(force_alert=False):
    """The single place that decides whether a Telegram send's phone
    alert is muted, combining both mute mechanisms:

    - Quiet Mode (Item 15): a deliberate, manual "mute literally
      everything for a day" action -- covers every message with NO
      exception, including a high-confidence signal, because muting
      everything is the entire point of a CEO choosing to trigger it.
    - Silent Hours (Item 5): a recurring nightly schedule meant to hold
      back only routine/non-urgent notifications -- `force_alert=True`
      (a genuinely high-confidence signal, see send_signal_for_position)
      bypasses this one so something worth waking up for still can.

    Either way the message itself is still generated, sent, and fully
    logged -- muting only ever affects the phone alert/sound, never
    whether or when something is delivered."""
    if is_quiet_mode_active():
        return True
    if force_alert:
        return False
    return is_within_silent_hours()


def _master_enabled():
    """Telegram Dashboard's master ON/OFF switch: when OFF, NOTHING gets
    sent -- not a manual override, not the automatic high-confidence rule,
    not a close-result follow-up -- regardless of how strong the
    confidence gating looks. Checked first, before any other gate, in
    both send_signal_for_position() (the single real-send entry point
    shared by Manual Override and the automatic rule) and
    send_close_followup(), so there is exactly one place this can be
    bypassed by accident: nowhere. send_test_message() is intentionally
    NOT gated by this -- it's a deliberate connectivity check the CEO runs
    while configuring the bot, not a trade signal."""
    return load_settings().get("master_send_enabled", True)


def _rate_limited():
    settings = load_settings()
    limit = settings.get("rate_limit_per_hour", 10)
    since = (datetime.now(timezone.utc).timestamp() - 3600)
    since_iso = datetime.fromtimestamp(since, tz=timezone.utc).isoformat()
    sent = storage.count_telegram_messages_since(since_iso)
    return sent >= limit


def _build_proxies(settings):
    """Returns a requests-style {"http": url, "https": url} dict if a
    proxy is configured and enabled, else None (direct connection,
    today's default/original behavior -- nothing changes for anyone who
    never touches this setting). Both proxy entries point at the SAME
    url on purpose: Telegram's API is HTTPS-only, but requests still
    needs an "http" key present for some urllib3/proxy combinations to
    route correctly, and a single proxy server conventionally handles
    both schemes."""
    if not settings.get("proxy_enabled"):
        return None
    url = (settings.get("proxy_url") or "").strip()
    if not url:
        return None
    return {"http": url, "https": url}


def _raw_send(text, channel_id_override=None, force_alert=False):
    """Real HTTP call to the Telegram Bot API -- no simulation. Returns
    (success: bool, error: str|None).

    Retries up to _API_MAX_ATTEMPTS times (short backoff between attempts)
    on connection-level failures (timeout, connection reset, DNS/network
    errors) -- these are transient-network-shaped failures worth retrying.
    A real API response (even an error one, e.g. bad chat_id) is NOT
    retried -- that's a genuine, immediate answer from Telegram, retrying
    it would just get the same answer again.

    If proxy_enabled + proxy_url are configured, every request routes
    through that proxy instead of connecting directly -- see the module
    docstring for why (api.telegram.org is network-blocked in some
    countries at the ISP level, confirmed via direct diagnostic testing,
    not fixable by timeout/retry tuning alone).

    channel_id_override (Grand Feature Expansion, Phase 2 Feature 22:
    Multi-Channel Support): set by send_signal_for_position() when the
    signal's strategy has a configured routing override -- same bot token,
    a different destination chat/channel. Every other caller (daily/weekly
    reports, test sends, close-followups) omits this and keeps using the
    one default channel_id, unchanged.

    force_alert (Grand Master Batch, Phase 4 Item 5): set by
    send_signal_for_position() for a genuinely high-confidence signal --
    see _effective_silent()'s docstring for why this bypasses Silent
    Hours but never Quiet Mode."""
    settings = load_settings()
    token = settings.get("bot_token")
    channel_id = channel_id_override or settings.get("channel_id")
    if not token or not channel_id:
        return False, "Telegram bot token or channel ID not configured yet"
    proxies = _build_proxies(settings)
    # Grand Feature Expansion, Phase 2 Feature 24 / Grand Master Batch,
    # Phase 4 Items 5 & 15: Silent Hours + Quiet Mode. The message is
    # still sent and fully logged as normal either way -- Telegram's own
    # disable_notification flag just mutes the phone alert/sound, nothing
    # is withheld or delayed.
    silent = _effective_silent(force_alert)

    last_err = None
    for attempt in range(1, _API_MAX_ATTEMPTS + 1):
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": channel_id, "text": text, "parse_mode": "HTML", "disable_notification": silent},
                timeout=(_API_CONNECT_TIMEOUT, _API_READ_TIMEOUT),
                proxies=proxies,
            )
            data = resp.json()
            if resp.status_code == 200 and data.get("ok"):
                return True, None
            return False, data.get("description", f"HTTP {resp.status_code}")
        except requests.RequestException as e:
            # Full System Verification Audit (2026-09-13): a real,
            # pre-existing gap -- requests/urllib3 exceptions frequently
            # embed the full request URL in their own repr(), and that
            # URL contains the raw bot token (see the f-string above).
            # This module's own docstring claims the token is "NEVER...
            # written to the log", which this branch violated. Redacted
            # before it ever reaches last_err, so it can never land in
            # telegram_message_log.error or any diagnostic that reads it.
            last_err = re.sub(r"/bot\d+:[A-Za-z0-9_-]+", "/bot[REDACTED]", repr(e))
            if attempt < _API_MAX_ATTEMPTS:
                time.sleep(_API_RETRY_BACKOFF_SECONDS)
    # Grand Master Batch, Phase 4 Item 8: this branch is reached ONLY after
    # every retry hit a genuine connection-level failure -- Telegram never
    # actually answered at all (as opposed to answering with a real
    # rejection, e.g. bad chat_id, which returns immediately above without
    # reaching here) -- i.e. exactly "Telegram itself is down" from here.
    # Best-effort backup alert via the existing ntfy.sh hook (paper_trading/
    # push_notifications.py, previously built but never wired to anything)
    # so the CEO's phone still gets SOMETHING. Never lets a push failure
    # (including "no ntfy_topic configured yet") change this function's
    # own return value -- the real Telegram failure is still what's
    # reported/logged.
    try:
        from paper_trading import push_notifications
        push_notifications.send_push(
            "SINDHU: Telegram is unreachable",
            f"Telegram delivery failed after {_API_MAX_ATTEMPTS} attempts -- the message below could not be sent:\n\n{text[:300]}",
            priority="high",
        )
    except Exception:
        pass
    return False, f"failed after {_API_MAX_ATTEMPTS} attempts: {last_err}"


def check_telegram_reachability():
    """Real, credential-independent network test: can THIS server reach
    api.telegram.org at all, direct (never through a configured proxy --
    that's what test_proxy_connectivity()/send_test_message() are for).
    Needs no bot token or channel id, so it works even before either is
    configured -- unlike send_test_message(), which requires both.

    Added 2026-09-13: earlier diagnosis that "Telegram is network-blocked"
    was based on testing from the CEO's own local machine/ISP -- a real,
    confirmed finding there, but never actually verified against wherever
    this specific process is running. A cloud deployment's outbound network
    path is completely independent of the CEO's home/office ISP, so that
    local finding does not automatically apply here; this is the live,
    from-here check instead of carrying that assumption over unverified.
    Classifies failures the same way telegram_delivery._NETWORK_MARKERS
    does, so "blocked/unreachable" vs. "reachable, just no valid token"
    (a 404 from the bare domain, since no bot path was given) are told
    apart correctly."""
    start = time.time()
    # Booleans only (public_settings()'s own existing safe-disclosure
    # design -- never the raw token/proxy credentials), included here so
    # one call answers both "can this server reach Telegram" and "is a
    # bot/channel actually configured yet" together.
    config = public_settings()
    result = {
        "bot_token_configured": config["token_configured"],
        "channel_id_configured": bool(config["channel_id"]),
        "master_send_enabled": config["master_send_enabled"],
        "auto_send_enabled": config["auto_send_enabled"],
        "proxy_enabled": config["proxy_enabled"],
    }
    try:
        resp = requests.get("https://api.telegram.org", timeout=(_API_CONNECT_TIMEOUT, _API_READ_TIMEOUT))
        elapsed_ms = round((time.time() - start) * 1000)
        # The bare domain (no /bot<token>/... path) always answers 404 from
        # a REACHABLE Telegram edge -- any HTTP response at all (regardless
        # of status code) proves the network path works; only a raised
        # exception below means it doesn't.
        result.update({"reachable": True, "http_status": resp.status_code, "latency_ms": elapsed_ms})
    except requests.RequestException as e:
        elapsed_ms = round((time.time() - start) * 1000)
        result.update({"reachable": False, "error": repr(e), "elapsed_ms": elapsed_ms})
    return result


def test_proxy_connectivity():
    """Separate, lighter-weight check than send_test_message(): confirms
    the CONFIGURED PROXY ITSELF is reachable and can reach the public
    internet at all (via https://api.ipify.org, a tiny plain-text "what's
    my IP" endpoint), without needing a valid bot token/channel or
    touching Telegram. Useful for isolating "is my proxy server even
    working" from "is Telegram reachable through it" as two separate
    questions when troubleshooting."""
    settings = load_settings()
    proxies = _build_proxies(settings)
    if proxies is None:
        return {"ok": False, "error": "No proxy is configured/enabled -- nothing to test."}
    try:
        resp = requests.get("https://api.ipify.org?format=json", proxies=proxies,
                             timeout=(_API_CONNECT_TIMEOUT, _API_READ_TIMEOUT))
        if resp.status_code == 200:
            return {"ok": True, "exit_ip": resp.json().get("ip")}
        return {"ok": False, "error": f"HTTP {resp.status_code}"}
    except requests.RequestException as e:
        return {"ok": False, "error": repr(e)}


def send_test_message():
    """A1: real connection confirmation -- not simulated. Not rate-limited
    or logged to the trade audit trail (it's a connectivity check, not a
    trade signal), but still uses the exact same send path A2/A3 use."""
    ok, err = _raw_send(f"{TELEGRAM_BRAND} test message -- connection successful.\n\n{DISCLAIMER}")
    return {"ok": ok, "error": err}


def send_private_message(text):
    """Master 15-Item task, Items 6 & 10: sends to the CEO's own private
    `personal_chat_id` (a DM with the bot) instead of the shared/public
    `channel_id` -- same bot token, same real HTTP send path as every
    other message (_raw_send), just a different destination via its
    existing channel_id_override parameter. Used by the Emergency
    Downtime Alert watchdog and the Weekly/Monthly report sender; never
    used for a normal trade signal (those always go to the public
    channel). Returns {"ok": bool, "error": str|None} -- if
    personal_chat_id has never been set, ok=False with a clear reason
    rather than silently falling back to the public channel (a private-
    only message must never leak to the shared channel by accident)."""
    settings = load_settings()
    personal_chat_id = settings.get("personal_chat_id")
    if not personal_chat_id:
        return {"ok": False, "error": "personal_chat_id is not configured yet -- Settings > Telegram"}
    ok, err = _raw_send(text, channel_id_override=personal_chat_id)
    return {"ok": ok, "error": err}


def send_private_document(file_path, caption=None):
    """Master 15-Item task, Item 10: sends a real FILE (the Weekly/Monthly
    PDF performance report) to the CEO's private personal_chat_id via
    Telegram's sendDocument API -- distinct from every other function in
    this file, which only ever sends sendMessage text. Same proxy/retry
    conventions as _raw_send, just a different Telegram endpoint and a
    multipart file body instead of a JSON text body. Returns
    {"ok": bool, "error": str|None}."""
    settings = load_settings()
    token = settings.get("bot_token")
    personal_chat_id = settings.get("personal_chat_id")
    if not token or not personal_chat_id:
        return {"ok": False, "error": "bot_token or personal_chat_id is not configured yet -- Settings > Telegram"}
    proxies = _build_proxies(settings)
    silent = _effective_silent()

    last_err = None
    for attempt in range(1, _API_MAX_ATTEMPTS + 1):
        try:
            with open(file_path, "rb") as f:
                resp = requests.post(
                    f"https://api.telegram.org/bot{token}/sendDocument",
                    data={"chat_id": personal_chat_id, "caption": caption or "", "disable_notification": silent},
                    files={"document": (os.path.basename(file_path), f, "application/pdf")},
                    timeout=(_API_CONNECT_TIMEOUT, _API_READ_TIMEOUT * 2),  # a PDF upload is larger than a text message
                    proxies=proxies,
                )
            data = resp.json()
            if resp.status_code == 200 and data.get("ok"):
                return {"ok": True, "error": None}
            return {"ok": False, "error": data.get("description", f"HTTP {resp.status_code}")}
        except requests.RequestException as e:
            # Same token-in-URL redaction as _raw_send above -- this
            # function builds its own separate sendDocument request with
            # the token embedded in the URL (line above), so it has the
            # exact same exposure risk on a connection-level exception.
            last_err = re.sub(r"/bot\d+:[A-Za-z0-9_-]+", "/bot[REDACTED]", repr(e))
            if attempt < _API_MAX_ATTEMPTS:
                time.sleep(_API_RETRY_BACKOFF_SECONDS)
    return {"ok": False, "error": f"failed after {_API_MAX_ATTEMPTS} attempts: {last_err}"}


def _format_price(value):
    """DISPLAY-ONLY rounding for the Telegram message text -- the
    underlying stored Entry/SL/TP/live-price floats used by the trading
    and backtest engines are never touched, only what gets rendered here.

    Standard price-tick style rounding: 3 decimal places is the FLOOR
    (never fewer, even for a $50,000 coin -- "50000.123", not "50000"),
    but prices below $1 get more decimals as needed to keep roughly 4
    significant figures, since a flat 3-decimal round would wipe out a
    low-priced coin's actual price movement (e.g. a $0.0003091 coin would
    display as "0.000", which is meaningless)."""
    if value is None:
        return "-"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if v == 0:
        return "0.000"
    magnitude = abs(v)
    if magnitude >= 1:
        decimals = 3
    else:
        exponent = math.floor(math.log10(magnitude))
        decimals = max(3, -exponent + 3)
    return f"{v:.{decimals}f}"


def _fetch_live_price(exchange, symbol):
    """Best-effort real current price via the same exchange client used
    everywhere else in the app (data_engine.exchanges.registry) -- never
    estimated. Returns None (the line is simply omitted from the message)
    on any failure, since a stale or wrong "live" price would be worse
    than not showing one at all."""
    if not exchange:
        return None
    try:
        from data_engine.exchanges.registry import get_exchange_client
        client = get_exchange_client(exchange)
        coins_cfg = base_config.load_or_seed("coins.json", base_config.DEFAULTS["coins.json"])
        tickers = client.get_tickers(coins_cfg["quote_asset"])
        ticker = tickers.get(symbol)
        return ticker["price"] if ticker else None
    except Exception:
        return None


# --------------------------------------------------------------- Task 4 (Batch 3, Part B): Signal Freshness Gate

def signal_age_minutes(position, now_ms=None):
    """Real elapsed minutes since this signal's position opened, or None
    if entry_time isn't recorded (never blocks on missing data -- a
    position without a timestamp can't be judged stale, it's simply not
    checked)."""
    entry_time_ms = position.get("entry_time")
    if not entry_time_ms:
        return None
    now_ms = now_ms if now_ms is not None else datetime.now(timezone.utc).timestamp() * 1000
    return max(0.0, (now_ms - entry_time_ms) / 60000.0)


def is_signal_stale(position, now_ms=None, max_age_minutes=None):
    """True if this signal is older than the configured freshness window
    (default 15 minutes) -- by the time it would reach Telegram, price
    has likely already moved away from the intended entry. A position
    with no entry_time is never treated as stale (nothing to judge)."""
    age = signal_age_minutes(position, now_ms=now_ms)
    if age is None:
        return False
    limit = max_age_minutes if max_age_minutes is not None else load_settings().get(
        "signal_freshness_minutes", _DEFAULTS["signal_freshness_minutes"])
    return age > limit


def price_has_moved_away(position, live_price, max_drift_pct=None):
    """True if the current live price has moved more than the configured
    threshold (default 0.5%) away from this signal's entry price, in
    EITHER direction -- a big enough move either way means the specific
    entry this signal was built around no longer reflects the market, so
    the opportunity described in the message would already be gone.
    Never blocks when either price is unavailable (nothing to compare)."""
    entry_price = position.get("entry_price")
    if not entry_price or live_price is None:
        return False
    limit = max_drift_pct if max_drift_pct is not None else load_settings().get(
        "signal_price_drift_pct", _DEFAULTS["signal_price_drift_pct"])
    drift_pct = abs(live_price - entry_price) / entry_price * 100.0
    return drift_pct > limit


def freshness_check(position, now_ms=None):
    """The single gate send_signal_for_position() consults -- combines
    the age check and the price-drift check (which needs a real live
    price fetch, so this is the one place both live checks happen
    together). Returns (ok: bool, reason: str|None, live_price: float|None)
    -- live_price is returned either way so callers/format_signal_message
    don't have to fetch it twice."""
    if is_signal_stale(position, now_ms=now_ms):
        age = signal_age_minutes(position, now_ms=now_ms)
        limit = load_settings().get("signal_freshness_minutes", _DEFAULTS["signal_freshness_minutes"])
        return False, f"signal is {age:.0f} minutes old (limit {limit} minutes) -- too stale to send", None

    live_price = _fetch_live_price(position.get("exchange"), position["symbol"])
    if price_has_moved_away(position, live_price):
        limit = load_settings().get("signal_price_drift_pct", _DEFAULTS["signal_price_drift_pct"])
        return False, (
            f"live price ({live_price}) has moved more than {limit}% away from the entry price "
            f"({position.get('entry_price')}) -- the opportunity has likely already passed"
        ), live_price
    return True, None, live_price


# --------------------------------------------------------------- Phase 2.4: Trading Style + Duration
# Derived purely from the position's own recorded timeframe (already
# stored on every paper_positions row -- no guessing, no new lookups).
# Never invents a style for a timeframe it doesn't recognize.
_STYLE_BY_TIMEFRAME = {
    "1m": ("scalping", "Scalping", "minutes to ~1 hour"),
    "3m": ("scalping", "Scalping", "minutes to ~1 hour"),
    "5m": ("scalping", "Scalping", "minutes to ~1 hour"),
    "15m": ("intraday", "Intraday", "a few hours to 1 day"),
    "30m": ("intraday", "Intraday", "a few hours to 1 day"),
    "1h": ("intraday", "Intraday", "a few hours to 1 day"),
    "2h": ("intraday", "Intraday", "a few hours to 1 day"),
    "4h": ("intraday", "Intraday", "a few hours to 1 day"),
    "6h": ("swing", "Swing", "several days"),
    "8h": ("swing", "Swing", "several days"),
    "12h": ("swing", "Swing", "several days"),
    "1d": ("swing", "Swing", "several days to weeks"),
    "3d": ("swing", "Swing", "several days to weeks"),
    "1w": ("swing", "Swing", "several days to weeks"),
}


def trading_style_for_timeframe(timeframe):
    """Returns (style_key, style_label, duration_text), or (None, None,
    None) when the timeframe is missing or not one of this project's
    recognized values -- never guessed."""
    entry = _STYLE_BY_TIMEFRAME.get((timeframe or "").strip().lower())
    return entry if entry else (None, None, None)


# --------------------------------------------------------------- Phase 2.3: Minimum Take-Profit Distance Filter

def min_tp_distance_check(position):
    """Rejects a signal whose take-profit sits closer to entry than a safe
    manual-execution reaction threshold (see _DEFAULTS for the reasoning
    and per-style values). Never blocks when the filter is off, or when
    entry/TP price is missing -- nothing meaningful to judge."""
    settings = load_settings()
    if not settings.get("min_tp_distance_filter_enabled", _DEFAULTS["min_tp_distance_filter_enabled"]):
        return True, None
    entry = position.get("entry_price")
    tp = position.get("take_profit")
    if not entry or not tp:
        return True, None
    tp_distance_pct = abs(tp - entry) / entry * 100.0
    style_key, style_label, _ = trading_style_for_timeframe(position.get("timeframe"))
    threshold_key = f"min_tp_distance_pct_{style_key}" if style_key else "min_tp_distance_pct_default"
    threshold = settings.get(threshold_key, _DEFAULTS[threshold_key])
    if tp_distance_pct < threshold:
        style_note = f" for {style_label}" if style_label else ""
        return False, (
            f"take-profit is only {tp_distance_pct:.2f}% away from entry -- below the "
            f"{threshold:.2f}% minimum reaction-time threshold{style_note}"
        )
    return True, None


# --------------------------------------------------------------- Phase 3.4: Minimum Confidence % Filter

def min_confidence_check(position):
    """An ADDITIONAL filter layer on top of (never a replacement for) the
    existing Confluence ratio/count and Wilson 25-trade gates -- those
    already ran by the time an automatic send reaches here. Off by
    default (threshold 0), so this changes nothing until the CEO
    deliberately raises it from Settings. Never blocks when the
    position's confidence score wasn't computed (nothing to judge)."""
    threshold = load_settings().get("min_confidence_pct_to_send", _DEFAULTS["min_confidence_pct_to_send"])
    if not threshold or threshold <= 0:
        return True, None
    confidence_pct = position.get("confidence")
    if confidence_pct is None:
        return True, None
    if confidence_pct < threshold:
        return False, f"confidence {confidence_pct:.0f}% is below the configured minimum of {threshold:.0f}%"
    return True, None


# --------------------------------------------------------------- Phase 2.6: Duplicate-Signal Protection

def duplicate_signal_check(position):
    """The same strategy+coin+direction shouldn't reach Telegram twice
    inside one freshness window -- reuses signal_freshness_minutes (the
    existing Signal Freshness Gate's own setting) rather than inventing a
    second, competing duration."""
    strategy_id = position.get("strategy_id")
    symbol = position.get("symbol")
    direction = position.get("direction")
    if not strategy_id or not symbol or not direction:
        return True, None
    minutes = load_settings().get("signal_freshness_minutes", _DEFAULTS["signal_freshness_minutes"])
    since_iso = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    if storage.has_recent_telegram_signal_for(
        strategy_id, symbol, direction, since_iso, exclude_position_id=position.get("id"),
    ):
        return False, (
            f"a signal for this exact strategy+coin+direction was already sent within "
            f"the last {minutes} minutes"
        )
    return True, None


_LABELS = {
    # Grand Master Batch, Phase 2.4 removed the signal message down to 5
    # fields, which left most of these bilingual labels (confidence,
    # statistical confidence, Why This Trade, footer brand, profitability/
    # challenge-mode labels, per-signal expiry note, HIGH CONFIDENCE
    # marker, group-name-as-text labels) with no remaining reader --
    # trimmed to just what send_signal_for_position/send_close_followup/
    # send_breakeven_notification still actually use.
    "ur": {
        "strategy": "Strategy", "entry": "Entry",
        "stop_loss": "Stop-Loss", "take_profit": "Take-Profit",
        "unknown_strategy": "Pata Nahi",
        "breakeven_moved": "✅ Stop-loss break-even par move ho gaya -- ab yeh trade risk-free hai.",
        "duration": "Duration",
    },
    "en": {
        "strategy": "Strategy", "entry": "Entry",
        "stop_loss": "Stop-Loss", "take_profit": "Take-Profit",
        "unknown_strategy": "Unknown",
        "breakeven_moved": "✅ Stop-loss moved to break-even -- this trade is now risk-free.",
        "duration": "Duration",
    },
}

# Phase 2.2: reuses paper_trading.strategy_groups' existing 3-way
# classification (the same one the Groups tab / Group C's own
# CHALLENGE_TELEGRAM_MARKER already rely on) -- no new classification
# logic, just a visual marker on top of an already-computed group.
_GROUP_MARKER_EMOJI = {"profitable": "\U0001F535", "losing": "\U0001F534", "challenge": "\U0001F7E3"}
# A strategy that hasn't traded enough yet to be bucketed into a group
# (strategy_groups.get_group() returns None) still needs a status emoji --
# every signal message should be emoji-led, not just the already-classified
# ones -- so it gets this neutral "not yet classified" marker instead of no
# emoji at all.
_UNCLASSIFIED_MARKER_EMOJI = "\U000026AA"


def format_signal_message(position, confluence_result=None, reliability_result=None, high_confidence=False,
                           live_price=_UNSET, lang=None, explanation_text=None, grade_result=None):
    """Grand Master Batch, Phase 2.4: deliberately reduced, on the CEO's
    explicit instruction, to exactly 5 things -- coin + status emoji
    (which strategy_groups.get_group() bucket the strategy is currently
    in: profitable/losing/challenge), Entry, Stop-Loss, Take-Profit, and
    an estimated Duration (from trading_style_for_timeframe). Every other
    line this function used to build (confidence %, trading-style name,
    quality grade, statistical confidence/win rate, confluence factors,
    AI explanation, entry reason, timestamp/age, per-signal expiry note,
    challenge-mode tags, profit-lock note, HIGH CONFIDENCE marker,
    footer/disclaimers) is intentionally gone from the message body --
    none of that data was deleted anywhere, it's all still on the
    dashboard, this function just no longer renders it into the Telegram
    text. confluence_result/reliability_result/high_confidence/
    live_price/explanation_text/grade_result are kept as parameters
    (every existing call site still passes them) but are no longer used
    here; lang still selects ur/en for the two labels that remain.

    Direction (LONG/SHORT) is also gone from the body per the same
    literal instruction ("exactly these fields, nothing more") -- it is
    still recoverable from the position record itself (position["direction"]),
    just not printed in the message text."""
    if lang not in ("ur", "en"):
        lang = load_settings().get("language", "ur")
    L = _LABELS[lang]
    symbol = position["symbol"]

    group_key = strategy_groups.get_group(position.get("strategy_id")) if position.get("strategy_id") else None
    status_emoji = _GROUP_MARKER_EMOJI.get(group_key, _UNCLASSIFIED_MARKER_EMOJI)
    _, _, duration_text = trading_style_for_timeframe(position.get("timeframe"))

    lines = [
        f"{status_emoji} <b>{symbol}</b>",
        f"{L['entry']}: {_format_price(position.get('entry_price'))}",
        f"{L['stop_loss']}: {_format_price(position.get('stop_loss'))}",
        f"{L['take_profit']}: {_format_price(position.get('take_profit'))}",
        f"{L['duration']}: {duration_text}" if duration_text else f"{L['duration']}: --",
    ]
    return "\n".join(lines)


def _pattern_reliability_for(strategy_id, symbol, market_state, session):
    """The exact same statistical gate the Genuine Evolution Engine uses
    for Pattern Auto-Avoid / Lesson Auto-Apply (paper_trading.pattern_stats
    -- Wilson score interval, minimum 25 trades), reused here rather than
    inventing a new confidence threshold for Telegram. Returns
    pattern_stats.classify()'s full result dict.

    Master Task 6, 1.2 (Wilson Gate Broadening): grouped at the (strategy,
    coin) level, not the exact (strategy, coin, market_state, session)
    combination anymore -- the old per-condition grouping fragmented each
    strategy's history into 500+ groups too narrow to ever individually
    reach the 25-trade minimum even when the strategy had a meaningful
    sample size on that coin overall. market_state/session are kept in
    the signature (callers are unaffected) but no longer narrow the
    group -- this fixes over-fragmentation only; the 25-trade minimum
    itself is untouched."""
    stats = storage.get_paper_strategy_coin_reliability_stats(strategy_id, symbol)
    return pattern_stats.classify(stats["wins"], stats["trades"])


def send_signal_for_position(position_id, trigger_type="manual", high_confidence=False, retry_id=None):
    """The one real-send entry point both Manual Override (A2) and the
    automatic rule (A3) call. Rate-limited, always logged (success or
    failure) to telegram_message_log -- a full audit trail, per A4.

    high_confidence (Task 4, Priority Batch 1): only ever set True by the
    automatic sender, and only when evaluate_auto_send_tier() genuinely
    returned "high" for THIS position -- adds the distinct High Confidence
    marker to the message. Manual sends never pass this (defaults False),
    so a CEO-triggered send is never mislabeled as an automatic
    high-confidence call.

    retry_id (Grand Feature Expansion, Phase 2 Feature 11): set ONLY by
    sweep_pending_telegram_retries() when re-attempting a previously
    queued failed send -- tells this call not to enqueue a SECOND retry
    row on renewed failure (the sweep itself updates the existing row)."""
    pos = storage.get_paper_position(position_id)
    now = _now_iso()
    if not pos:
        storage.log_telegram_message(position_id, None, None, trigger_type, "", False, "position not found", now)
        return {"ok": False, "error": "position not found"}

    from paper_trading import kill_switch
    if kill_switch.is_active():
        storage.log_telegram_message(
            position_id, pos.get("strategy_id"), pos.get("strategy_name"), trigger_type,
            "", False, "kill switch is active -- Telegram sending halted", now,
        )
        return {"ok": False, "error": "kill switch is active -- Telegram sending halted"}

    if not _master_enabled():
        storage.log_telegram_message(
            position_id, pos.get("strategy_id"), pos.get("strategy_name"), trigger_type,
            "", False, "Telegram sending is turned off (master switch)", now,
        )
        return {"ok": False, "error": "Telegram sending is turned off (master switch)"}

    if _rate_limited():
        storage.log_telegram_message(
            position_id, pos.get("strategy_id"), pos.get("strategy_name"), trigger_type,
            "", False, "rate limit reached for this hour", now,
        )
        return {"ok": False, "error": "rate limit reached for this hour"}

    # Task 4 (Batch 3, Part B): Signal Freshness Gate -- applies to every
    # send through this one shared entry point (manual AND automatic,
    # including the hourly sweep from Batch 2, which calls this same
    # function and therefore automatically respects this gate too -- see
    # sweep_unsent_qualifying_signals's docstring). A stale signal, or one
    # whose live price has already moved away from the entry, is never
    # sent as a normal signal.
    fresh_ok, fresh_reason, live_price = freshness_check(pos)
    if not fresh_ok:
        storage.log_telegram_message(
            position_id, pos.get("strategy_id"), pos.get("strategy_name"), trigger_type,
            "", False, fresh_reason, now,
        )
        return {"ok": False, "error": fresh_reason}

    # Phase 2.3: Minimum Take-Profit Distance Filter.
    tp_ok, tp_reason = min_tp_distance_check(pos)
    if not tp_ok:
        storage.log_telegram_message(
            position_id, pos.get("strategy_id"), pos.get("strategy_name"), trigger_type,
            "", False, tp_reason, now,
        )
        return {"ok": False, "error": tp_reason}

    # Phase 2.6: Duplicate-Signal Protection.
    dup_ok, dup_reason = duplicate_signal_check(pos)
    if not dup_ok:
        storage.log_telegram_message(
            position_id, pos.get("strategy_id"), pos.get("strategy_name"), trigger_type,
            "", False, dup_reason, now,
        )
        return {"ok": False, "error": dup_reason}

    # Phase 3.4: Minimum Confidence % Filter (additional layer, off by default).
    conf_ok, conf_reason = min_confidence_check(pos)
    if not conf_ok:
        storage.log_telegram_message(
            position_id, pos.get("strategy_id"), pos.get("strategy_name"), trigger_type,
            "", False, conf_reason, now,
        )
        return {"ok": False, "error": conf_reason}

    exchanges_cfg = base_config.load_or_seed("exchanges.json", base_config.DEFAULTS["exchanges.json"])
    exchange = exchanges_cfg["default"]
    try:
        conf = confluence_mod.score_confluence(
            pos.get("strategy_id"), pos["symbol"], exchange,
            pos.get("market_state"), pos.get("session"), pos["direction"],
        )
    except Exception:
        conf = None
    try:
        reliability = _pattern_reliability_for(
            pos.get("strategy_id"), pos["symbol"], pos.get("market_state"), pos.get("session"),
        )
    except Exception:
        reliability = None

    explanation_lines = signal_explainer.explain_signal_lines(conf, reliability)
    grade_result = signal_explainer.grade_signal(conf, reliability)
    text = format_signal_message(pos, conf, reliability, high_confidence=high_confidence, live_price=live_price,
                                  explanation_text=explanation_lines, grade_result=grade_result)
    # Grand Master Batch, Phase 2.4: the old CHALLENGE_TELEGRAM_MARKER
    # append (a ",,,teen,,," suffix) that used to distinguish a Group C
    # ("Challenge") signal is removed here -- format_signal_message() now
    # puts the same 🟣 Challenge-group emoji directly in the message
    # header for every signal from a Challenge-group strategy, which
    # already achieves the one thing this append existed for. Appending
    # both would put the same status on the message twice, which the
    # explicit "exactly these fields, nothing more" instruction rules out.
    ok, err = _raw_send(text, channel_id_override=channel_for_strategy(pos.get("strategy_id")), force_alert=high_confidence)
    storage.log_telegram_message(
        position_id, pos.get("strategy_id"), pos.get("strategy_name"), trigger_type, text, ok, err, now,
        # The log column is plain TEXT (also read back by
        # storage.list_telegram_signal_outcomes for the Telegram dashboard) --
        # joined back into one string here, distinct from the bulleted list
        # form used just above for the actual Telegram message text.
        explanation_text=" ".join(explanation_lines), quality_grade=grade_result["grade"],
        grade_reason=grade_result["reason"],
    )
    # Grand Feature Expansion, Phase 2 Feature 11: Delivery Retry Queue.
    # Only a genuine TRANSIENT delivery failure is queued -- _raw_send's
    # own docstring is explicit that a real Telegram API response (even an
    # error one, e.g. a bad chat_id) is never worth retrying, only its
    # "failed after N attempts" network-exhaustion case is. Never queues
    # from inside a RETRY attempt itself (retry_id passed) -- that path's
    # own caller (sweep_pending_retries) updates the SAME queue row
    # instead of creating a new one.
    if not ok and retry_id is None and err and err.startswith("failed after"):
        storage.enqueue_telegram_retry(position_id, trigger_type, high_confidence, now)
    return {"ok": ok, "error": err, "message": text}


# --------------------------------------------------------------- A3: automatic high-confidence rule

def evaluate_auto_send(position_id):
    """A3's documented rule -- ALL of the following, checked fresh each
    time (never cached, correctness over speed for a safety gate):
      1. auto_send_enabled is explicitly True in settings (OFF by default).
      2. Confluence ratio (passed/total factors) >= auto_send_min_confluence_ratio
         (default 1.0 -- i.e. every counted factor must be aligned; this is
         deliberately the strictest possible starting point since this is a
         gate for an UNSUPERVISED external message, not just a display label).
      3. The EXACT (strategy, coin, market condition, session) pattern is
         statistically reliable per the Genuine Evolution Engine's own
         Wilson-score gate (pattern_stats.classify() -- minimum 25 real
         trades, 95% confidence interval) AND that pattern's true win rate
         is confidently good, not just "not confidently bad" -- reused
         as-is, no new threshold invented for Telegram specifically. Below
         25 trades for this exact pattern, automatic sending is blocked
         regardless of how strong the confluence looks, since one raw
         percentage from a handful of trades is not a real edge yet.
      4. The strategy is NOT currently paused by Drawdown Protection.
      5. No open position already exists on this same symbol from a
         DIFFERENT strategy in the correlation-flagged set (cheap proxy:
         reuses confluence's own "coin not already crowded" factor).
      6. The strategy's live realized PnL this session is >= 0 (a "positive
         live PnL trend" reading, in the plainest possible form: not
         currently net negative).
    Returns (should_send: bool, reason: str) -- reason is always populated,
    even when True, for auditability."""
    settings = load_settings()
    if not settings.get("auto_send_enabled", False):
        return False, "automatic sending is turned off in Settings"
    if feature_toggles.is_master_paused():
        return False, "all automation is currently paused (master switch)"

    pos = storage.get_paper_position(position_id)
    if not pos:
        return False, "position not found"

    strategy_id = pos.get("strategy_id")
    paused, pause_reason, _ = storage.is_strategy_paused(strategy_id)
    if paused:
        return False, f"strategy is paused by Drawdown Protection: {pause_reason}"

    exchanges_cfg = base_config.load_or_seed("exchanges.json", base_config.DEFAULTS["exchanges.json"])
    exchange = exchanges_cfg["default"]
    conf = confluence_mod.score_confluence(
        strategy_id, pos["symbol"], exchange, pos.get("market_state"), pos.get("session"), pos["direction"],
    )
    if conf["total"] == 0:
        return False, "not enough data yet to score confluence"
    ratio = conf["passed"] / conf["total"]
    min_ratio = settings.get("auto_send_min_confluence_ratio", 1.0)
    if ratio < min_ratio:
        return False, f"confluence {conf['label']} below the required bar"
    # Batch 6, Task 3: the ratio alone can be satisfied by a small number
    # of counted factors (the rest were "neutral" -- not enough data, and
    # so excluded from the denominator). High Confidence additionally
    # requires a minimum ABSOLUTE count of aligned factors, tightening
    # the bar with the same already-computed numbers -- no new factors,
    # HIGH tier only.
    min_count = settings.get("auto_send_min_confluence_count", _DEFAULTS["auto_send_min_confluence_count"])
    if conf["passed"] < min_count:
        return False, (
            f"confluence {conf['label']} has too few factors actually counted/aligned "
            f"(needs at least {min_count}, only {conf['passed']} counted)"
        )

    reliability = _pattern_reliability_for(strategy_id, pos["symbol"], pos.get("market_state"), pos.get("session"))
    if reliability["status"] != "reliable_good":
        return False, (
            f"this exact pattern isn't statistically confident yet -- {reliability['conclusion']} "
            f"(needs {pattern_stats.MIN_SAMPLE_SIZE} recorded trades for this strategy+coin+condition)"
        )

    pnl_total = storage.get_paper_realized_pnl_total(strategy_id)
    if pnl_total < 0:
        return False, f"strategy's live PnL this session is currently negative (${pnl_total:.2f})"

    return True, (
        f"passed all automatic-send checks (confluence {conf['label']}, "
        f"{reliability['win_rate_pct']:.0f}% win rate over {reliability['sample_size']} trades, "
        f"live PnL ${pnl_total:.2f})"
    )


# --------------------------------------------------------------- Task 4 (Priority Batch 1): dual-tier auto-send

def evaluate_auto_send_low_tier(position_id):
    """The LOWER of the two auto-send tiers. Same base safety checks as
    evaluate_auto_send() above (auto_send_enabled, not globally paused,
    strategy not paused by Drawdown Protection, the same configured
    confluence floor, live PnL not negative) -- but, unlike
    evaluate_auto_send() (the HIGH tier, left completely untouched by this
    change, 25-trade Wilson gate and all), does NOT require the pattern to
    already be statistically confirmed.

    This is what keeps signal flow going: before this tier existed, a real
    signal with perfect confluence but not yet enough trade history for
    this exact (strategy, coin, condition) combo was blocked outright by
    evaluate_auto_send(). Now it's still sent -- just without the High
    Confidence marker, since that marker is reserved for signals that have
    cleared the statistical gate too. Never touches
    paper_trading.pattern_stats or its 25-trade minimum.

    Returns (should_send: bool, reason: str)."""
    settings = load_settings()
    if not settings.get("auto_send_enabled", False):
        return False, "automatic sending is turned off in Settings"
    if feature_toggles.is_master_paused():
        return False, "all automation is currently paused (master switch)"

    pos = storage.get_paper_position(position_id)
    if not pos:
        return False, "position not found"

    strategy_id = pos.get("strategy_id")
    paused, pause_reason, _ = storage.is_strategy_paused(strategy_id)
    if paused:
        return False, f"strategy is paused by Drawdown Protection: {pause_reason}"

    exchanges_cfg = base_config.load_or_seed("exchanges.json", base_config.DEFAULTS["exchanges.json"])
    exchange = exchanges_cfg["default"]
    conf = confluence_mod.score_confluence(
        strategy_id, pos["symbol"], exchange, pos.get("market_state"), pos.get("session"), pos["direction"],
    )
    if conf["total"] == 0:
        return False, "not enough data yet to score confluence"
    ratio = conf["passed"] / conf["total"]
    min_ratio = settings.get("auto_send_min_confluence_ratio", 1.0)
    if ratio < min_ratio:
        return False, f"confluence {conf['label']} below the required bar"

    pnl_total = storage.get_paper_realized_pnl_total(strategy_id)
    if pnl_total < 0:
        return False, f"strategy's live PnL this session is currently negative (${pnl_total:.2f})"

    return True, (
        f"passed the standard auto-send checks (confluence {conf['label']}, live PnL ${pnl_total:.2f}) -- "
        f"not yet statistically confirmed by the 25-trade gate, sent at the standard tier without the "
        f"High Confidence marker"
    )


def evaluate_auto_send_tier(position_id):
    """Tries the HIGH tier first (evaluate_auto_send -- real confluence +
    the real 25-trade Wilson gate).

    Confidence filtering: with auto_send_high_confidence_only=True, a
    Low-tier-only qualifying signal is deliberately NOT sent to Telegram --
    it is still fully generated and stays visible everywhere the dashboard
    already shows signal activity (paper_decision_log, the Signal Tracker
    page, and /api/paper-trading/telegram/delivery-log's "never sent"
    bucket, which surfaces exactly the reason text returned here), it just
    never reaches the channel. Defaults to False (see _DEFAULTS above) so
    Low tier sends normally -- flip it back to True from Settings for
    anyone who deliberately wants High-Confidence-only again.

    Returns (tier: "high" | "low" | None, reason: str)."""
    should_send_high, reason_high = evaluate_auto_send(position_id)
    if should_send_high:
        return "high", reason_high
    should_send_low, reason_low = evaluate_auto_send_low_tier(position_id)
    if not should_send_low:
        _record_near_miss(position_id, reason_low)
        return None, reason_low
    if load_settings().get("auto_send_high_confidence_only", _DEFAULTS["auto_send_high_confidence_only"]):
        _record_near_miss(position_id, reason_low)
        return None, (
            f"qualified for the Low Confidence tier but not sent -- only High Confidence "
            f"signals are sent to Telegram ({reason_low})"
        )
    return "low", reason_low


def _record_near_miss(position_id, reason):
    """Master Task 5, Part 1.5: Near-Miss Log. Called every time
    evaluate_auto_send_tier() lands on None -- i.e. a real signal was
    generated but did not reach High Confidence. Logged ONCE per position
    (storage.has_near_miss_for_position guards this, and the table's own
    UNIQUE(position_id) constraint is the final backstop), the first time
    this function runs for it, whether that's the real-time check right
    after the position opened or a later hourly sweep re-check.

    Purely observational: recomputes the exact same confluence + pattern
    reliability numbers the gate functions above already computed for their
    own decision (cheap, read-only), just so this permanent record captures
    HOW FAR SHORT the signal fell, not only that it fell short. Never
    raises -- a logging failure must never break the real send path."""
    try:
        settings = load_settings()
        if not settings.get("auto_send_enabled", False) or feature_toggles.is_master_paused():
            return  # automation itself is off -- not a real "signal fell short" event
        if storage.has_near_miss_for_position(position_id):
            return
        pos = storage.get_paper_position(position_id)
        if not pos:
            return
        strategy_id = pos.get("strategy_id")
        exchanges_cfg = base_config.load_or_seed("exchanges.json", base_config.DEFAULTS["exchanges.json"])
        exchange = exchanges_cfg["default"]
        conf = confluence_mod.score_confluence(
            strategy_id, pos["symbol"], exchange, pos.get("market_state"), pos.get("session"), pos["direction"],
        )
        if conf.get("total", 0) == 0:
            return  # nothing meaningful to log yet -- not a real near-miss, just no data
        reliability = _pattern_reliability_for(strategy_id, pos["symbol"], pos.get("market_state"), pos.get("session"))
        record = {
            "position_id": position_id, "strategy_id": strategy_id, "strategy_name": pos.get("strategy_name"),
            "symbol": pos["symbol"],
            "confluence_ratio": conf["passed"] / conf["total"], "confluence_passed": conf["passed"],
            "confluence_total": conf["total"],
            "confluence_required_ratio": settings.get("auto_send_min_confluence_ratio", 1.0),
            "confluence_required_count": settings.get("auto_send_min_confluence_count", _DEFAULTS["auto_send_min_confluence_count"]),
            "pattern_status": reliability.get("status"), "pattern_trades": reliability.get("sample_size"),
            "pattern_required": reliability.get("min_sample_size", pattern_stats.MIN_SAMPLE_SIZE),
            "pattern_win_rate_pct": reliability.get("win_rate_pct"),
            "live_pnl": storage.get_paper_realized_pnl_total(strategy_id) if strategy_id else None,
            "reason": reason,
        }
        storage.save_near_miss(record, _now_iso())
    except Exception:
        pass


# --------------------------------------------------------------- A5: two-way awareness (close follow-up)

def send_close_followup(closed_position):
    """Called after a trade closes (see position_manager._close()) -- only
    sends a follow-up if a signal was actually sent for this exact position
    earlier (storage.has_telegram_signal_for_position), so the channel
    never gets a "result" message for a trade nobody was told about."""
    settings = load_settings()
    if not settings.get("master_send_enabled", True):
        return None
    if not settings.get("send_close_followups", True) or feature_toggles.is_master_paused():
        return None
    position_id = closed_position["id"]
    if not storage.has_telegram_signal_for_position(position_id):
        return None

    lang = settings.get("language", "ur")
    en = lang == "en"
    L = _LABELS[lang if lang in _LABELS else "ur"]
    pnl = closed_position.get("pnl") or 0.0
    outcome = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BREAK-EVEN"
    outcome_icon = "\U0001F7E2" if pnl > 0 else "\U0001F534" if pnl < 0 else "⚪"
    strategy_label = "Strategy" if en else L["strategy"]
    coin_label = "Coin" if en else "Coin"
    exit_label = "Exit" if en else "Exit (Bahar)"
    result_label = "Result" if en else "Result (Nateeja)"
    lines = [
        f"{outcome_icon} <b>{TELEGRAM_BRAND} Result -- {outcome}</b>",
        "─" * 18,
        f"• {strategy_label}: {closed_position.get('strategy_name') or L['unknown_strategy']}",
        f"• {coin_label}: {closed_position['symbol']}",
        f"• {exit_label}: {_format_price(closed_position.get('exit_price'))} ({closed_position.get('exit_reason', '-')})",
        f"• {result_label}: {'+' if pnl >= 0 else ''}{pnl:.2f} ({closed_position.get('pnl_pct', 0):.2f}%)",
        "",
        DISCLAIMER,
    ]
    text = "\n".join(lines)
    ok, err = _raw_send(text, channel_id_override=channel_for_strategy(closed_position.get("strategy_id")))
    storage.log_telegram_message(
        position_id, closed_position.get("strategy_id"), closed_position.get("strategy_name"),
        "close_followup", text, ok, err, _now_iso(),
    )
    return {"ok": ok, "error": err}


def send_breakeven_notification(position):
    """Master Task 3, Phase 2.22: a brief, purely informational update when
    an OPEN trade's stop-loss has just moved to break-even (Profit-Lock
    Trailing Stop, paper_trading/profit_lock.py, reaching/crossing the
    entry price) -- detected and called from position_manager.
    monitor_and_close() at the exact point it already updates the stop, no
    new trading logic added there beyond that comparison. Same gating and
    'only if a signal was already sent for this position' rule as
    send_close_followup(), so the channel never gets an update about a
    trade nobody was told about."""
    settings = load_settings()
    if not settings.get("master_send_enabled", True) or feature_toggles.is_master_paused():
        return None
    position_id = position["id"]
    if not storage.has_telegram_signal_for_position(position_id):
        return None

    lang = settings.get("language", "ur")
    L = _LABELS[lang if lang in _LABELS else "ur"]
    lines = [
        L["breakeven_moved"],
        f"• {L['strategy']}: {position.get('strategy_name') or L['unknown_strategy']}",
        f"• {position['symbol']} -- {L['stop_loss']}: {_format_price(position.get('stop_loss'))}",
    ]
    text = "\n".join(lines)
    ok, err = _raw_send(text, channel_id_override=channel_for_strategy(position.get("strategy_id")))
    storage.log_telegram_message(
        position_id, position.get("strategy_id"), position.get("strategy_name"),
        "breakeven_notification", text, ok, err, _now_iso(),
    )
    return {"ok": ok, "error": err}


# --------------------------------------------------------------- Task 4 (Batch 2): hourly fresh-signal sweep

def sweep_unsent_qualifying_signals():
    """A recurring (>=hourly, called from paper_trading.engine's own tick
    loop -- see SWEEP_INTERVAL_SECONDS there) safety-net check: any
    currently OPEN position that never had a Telegram signal sent for it
    is re-evaluated through the EXACT SAME dual-tier gating
    (evaluate_auto_send_tier -- full confluence + the real 25-trade Wilson
    gate for High, the same minus the Wilson requirement for Low) used at
    open-time, in case it only started qualifying afterward (e.g. this
    exact strategy+coin+condition pattern crossed the 25-trade reliability
    threshold from OTHER trades closing since this position opened). Never
    a looser or bypassed check than the real-time path -- if a position
    didn't qualify then and still doesn't now, this sweep is a no-op for
    it, exactly like the real-time path would have been.

    Naturally never re-sends: a position with any successful signal
    already logged (storage.has_telegram_signal_for_position) is skipped
    outright, before gating is even evaluated -- there's no way for this
    function to fire twice for the same position.

    Returns a list of {"position_id", "tier"} for every signal actually
    sent this sweep (empty list = nothing qualified, or auto-send is off)."""
    if not load_settings().get("auto_send_enabled", False):
        return []
    sent = []
    for pos in storage.get_open_paper_positions():
        if storage.has_telegram_signal_for_position(pos["id"]):
            continue
        tier, reason = evaluate_auto_send_tier(pos["id"])
        if tier is None:
            continue
        result = send_signal_for_position(pos["id"], trigger_type="automatic", high_confidence=(tier == "high"))
        if result.get("ok"):
            sent.append({"position_id": pos["id"], "tier": tier})
    return sent


# ----------------------------------------- Grand Feature Expansion, Phase 2 Feature 11
# Delivery Retry Queue: re-attempts every PENDING queued send. A row is
# marked 'abandoned' (and a dashboard-visible alert raised) once it has
# failed this many total attempts -- never retried forever.
MAX_RETRY_ATTEMPTS = 5


def sweep_pending_telegram_retries():
    """Called periodically (see paper_trading.engine's tick loop). Returns
    {"delivered": [...], "abandoned": [...], "still_pending": [...]}
    (each a list of position_ids) for visibility/testing."""
    result = {"delivered": [], "abandoned": [], "still_pending": []}
    for row in storage.list_pending_telegram_retries():
        send_result = send_signal_for_position(
            row["position_id"], trigger_type=row["trigger_type"],
            high_confidence=bool(row["high_confidence"]), retry_id=row["id"],
        )
        new_status = storage.record_telegram_retry_attempt(
            row["id"], send_result["ok"], send_result.get("error"), _now_iso(), MAX_RETRY_ATTEMPTS,
        )
        result[{"delivered": "delivered", "abandoned": "abandoned", "pending": "still_pending"}[new_status]].append(
            row["position_id"]
        )
        if new_status == "abandoned":
            pos = storage.get_paper_position(row["position_id"])
            storage.create_paper_alert(
                "telegram_delivery_abandoned", pos.get("strategy_id") if pos else None,
                pos.get("strategy_name") if pos else None,
                f"A Telegram signal for position {row['position_id']} could not be delivered after "
                f"{MAX_RETRY_ATTEMPTS} attempts (last error: {send_result.get('error')}) and has been "
                f"given up on. The trade itself was unaffected -- only the Telegram notification failed.",
                "warning", _now_iso(),
            )
    return result


# --------------------------------------------------------------- Task 3 (Batch 2): no-signal alert

NO_SIGNAL_ALERT_HOURS = 24


def _humanize_hours(hours, en):
    """Turn a raw hour count into something a non-technical reader parses
    instantly. The dashboard alert read "in the last 752 hours", which
    nobody can convert to "about a month" at a glance. Presentation only
    -- the `hours_since` field in the payload keeps its exact raw value,
    so nothing that reads the number is affected."""
    hours = int(hours)
    if hours < 48:
        return f"{hours} hours" if en else f"{hours} ghanton"
    days = hours // 24
    if days < 14:
        return f"{days} days" if en else f"{days} dinon"
    weeks = days // 7
    if weeks < 9:
        return f"about {weeks} weeks" if en else f"takreeban {weeks} hafton"
    months = days // 30
    return f"about {months} month{'s' if months != 1 else ''}" if en else f"takreeban {months} maheenon"


def no_signal_alert_status(now_iso=None, lang="ur"):
    """Dashboard alert (Overview + Telegram Signals page) for an extended
    signal drought -- 24+ hours with zero signals sent to Telegram, any
    tier. Nothing to separately "clear": this is computed fresh from the
    real last-sent timestamp on every call, so it automatically stops
    firing the instant a new signal actually sends -- there's no separate
    stored "alert active" flag that could go stale or need resetting.

    now_iso: injectable for tests; defaults to the real current time.
    lang: "ur" (default) or "en" -- Batch 5, Task 3, plain deterministic
    template choice, no AI translation call.

    Returns {"stale": bool, "last_sent_at": iso|None, "hours_since": float|None,
             "message": str|None} -- message is a plain, non-technical
    sentence when stale, else None."""
    en = lang == "en"
    now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
    last_sent_iso = storage.get_last_telegram_signal_sent_at()

    if last_sent_iso is None:
        return {
            "stale": True, "last_sent_at": None, "hours_since": None,
            "message": ("No signals have been sent to Telegram yet." if en
                        else "Abhi tak Telegram par koi signal nahi bheja gaya."),
        }

    last_sent = datetime.fromisoformat(last_sent_iso)
    if last_sent.tzinfo is None:
        last_sent = last_sent.replace(tzinfo=timezone.utc)
    hours_since = (now - last_sent).total_seconds() / 3600.0
    stale = hours_since >= NO_SIGNAL_ALERT_HOURS
    return {
        "stale": stale, "last_sent_at": last_sent_iso, "hours_since": round(hours_since, 1),
        "message": (
            (f"No signals have been sent to Telegram for {_humanize_hours(hours_since, True)}." if en
             else f"Pichle {_humanize_hours(hours_since, False)} mein Telegram par koi signal nahi bheja gaya.")
            if stale else None
        ),
    }
