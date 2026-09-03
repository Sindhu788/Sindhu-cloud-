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
import time
from datetime import datetime, timezone

import requests

from data_engine import config as base_config, db_backend, storage, feature_toggles
from paper_trading import challenge_mode, confluence as confluence_mod, insights, pattern_stats, signal_explainer

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
    # Confidence filtering (this task): only High Confidence tier signals
    # (evaluate_auto_send -- full confluence + the 25-trade Wilson gate) are
    # ever sent to Telegram by default. A Low Confidence signal is still
    # generated and stays visible on the dashboard (paper_decision_log,
    # Signal Tracker, /telegram/delivery-log's "never sent" bucket) with
    # its own reason -- it just never reaches the channel. Kept as a
    # setting (default True) rather than hardcoded, consistent with every
    # other behavior toggle in this file.
    "auto_send_high_confidence_only": True,
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
}

DISCLAIMER = ("This is an experimental signal from a system still under development. "
              "Not financial advice. Trade at your own risk.")

# Appended, without exception, to every signal from a strategy currently
# classified "Profitable" (see _profitability_label) -- distinct wording
# from DISCLAIMER above (which already appears on every message
# regardless of tier or profitability) because this one specifically
# exists to stop a real, positive live track record from reading as a
# promise: a strategy that is profitable so far can still lose money on
# the very next trade.
PROFITABLE_RISK_DISCLAIMER = "⚠️ Risky -- no strategy guarantees profit, trade at your own risk"

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


def _raw_send(text, channel_id_override=None):
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
    one default channel_id, unchanged."""
    settings = load_settings()
    token = settings.get("bot_token")
    channel_id = channel_id_override or settings.get("channel_id")
    if not token or not channel_id:
        return False, "Telegram bot token or channel ID not configured yet"
    proxies = _build_proxies(settings)
    # Grand Feature Expansion, Phase 2 Feature 24: Silent Hours / Do-Not-
    # Disturb. The message is still sent and fully logged as normal --
    # Telegram's own disable_notification flag just mutes the phone
    # alert/sound during the configured window, nothing is withheld.
    silent = is_within_silent_hours()

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
            last_err = repr(e)
            if attempt < _API_MAX_ATTEMPTS:
                time.sleep(_API_RETRY_BACKOFF_SECONDS)
    return False, f"failed after {_API_MAX_ATTEMPTS} attempts: {last_err}"


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


def _reason_text(position):
    """Reuses the existing plain-language reasoning already built for the
    dashboard (paper_trading.insights.humanize_reason) -- no new NLP."""
    try:
        return insights.humanize_reason(position.get("entry_reason"))
    except Exception:
        return position.get("entry_reason") or "No reason recorded."


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


def _direction_emoji(direction):
    return "\U0001F7E2" if direction == "long" else "\U0001F534"  # green / red circle


def _confidence_icon(label):
    if not label:
        return "⚪"  # white circle -- unrated
    if label.startswith("Strong"):
        return "\U0001F7E2"
    if label.startswith("Moderate"):
        return "\U0001F7E1"
    if label.startswith("Weak"):
        return "\U0001F534"
    return "⚪"


def _signal_age_text(entry_time_ms):
    """How long ago this signal's position was opened, in the plainest
    possible form -- entry_time is the same epoch-ms timestamp already
    stored on every paper position, not a new field."""
    if not entry_time_ms:
        return None
    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    delta_s = max(0, (now_ms - entry_time_ms) / 1000)
    if delta_s < 60:
        return "just now"
    minutes = int(delta_s // 60)
    if minutes < 60:
        return f"{minutes}m ago"
    hours, rem_minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {rem_minutes}m ago" if rem_minutes else f"{hours}h ago"
    return f"{hours // 24}d ago"


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


_LABELS = {
    "ur": {
        "high_confidence": "⭐ <b>HIGH CONFIDENCE SIGNAL</b> ⭐",
        "strategy": "Strategy", "levels": "LEVELS", "entry": "Entry",
        "stop_loss": "Stop-Loss", "take_profit": "Take-Profit", "current_price": "Abhi Ka Price",
        "statistical_confidence": "Statistical Confidence", "confidence": "Confidence",
        "win_rate_over": "win rate, pichli {n} trades mein",
        "why_this_trade": "Yeh Trade Kyun", "reason": "Wajah",
        "why_this_signal_heading": "Yeh Signal Kyun", "quality_grade": "Signal Grade",
        "footer_brand": f"{TELEGRAM_BRAND} -- Paper Trading (Nakli Paise)",
        "unknown_strategy": "Pata Nahi",
        "profitable_strategy": "✅ <b>PROFITABLE STRATEGY</b> (live paper-trading record)",
        "strategy_under_evaluation": "\U0001F9EA <b>STRATEGY ABHI UNDER EVALUATION HAI</b> (kaafi trade history nahi hui abhi)",
        "challenge_mode_tag": "\U0001F3C6 <b>CHALLENGE MODE SIGNAL</b>",
    },
    "en": {
        "high_confidence": "⭐ <b>HIGH CONFIDENCE SIGNAL</b> ⭐",
        "strategy": "Strategy", "levels": "LEVELS", "entry": "Entry",
        "stop_loss": "Stop-Loss", "take_profit": "Take-Profit", "current_price": "Current Price",
        "statistical_confidence": "Statistical Confidence", "confidence": "Confidence",
        "win_rate_over": "win rate over {n} recorded trades",
        "why_this_trade": "Why This Trade", "reason": "Reason",
        "why_this_signal_heading": "Yeh Signal Kyun", "quality_grade": "Signal Grade",
        "footer_brand": f"{TELEGRAM_BRAND} -- Paper Trading",
        "unknown_strategy": "Unknown",
        "profitable_strategy": "✅ <b>PROFITABLE STRATEGY</b> (real live paper-trading record)",
        "strategy_under_evaluation": "\U0001F9EA <b>STRATEGY STILL UNDER EVALUATION</b> (not enough trade history yet)",
        "challenge_mode_tag": "\U0001F3C6 <b>CHALLENGE MODE SIGNAL</b>",
    },
}


def format_signal_message(position, confluence_result=None, reliability_result=None, high_confidence=False,
                           live_price=_UNSET, lang=None, explanation_text=None, grade_result=None):
    """lang: "ur" (default, the CEO's everyday register) or "en" -- Batch
    5, Task 3. Deterministic template choice, never an AI translation
    call. Defaults to the stored Telegram setting when not passed
    explicitly (see _DEFAULTS["language"])."""
    if lang not in ("ur", "en"):
        lang = load_settings().get("language", "ur")
    L = _LABELS[lang]
    direction_word = "LONG" if position["direction"] == "long" else "SHORT"
    symbol = position["symbol"]

    lines = []
    if high_confidence:
        # Task 4 (Priority Batch 1): a distinct, unmissable marker for the
        # HIGH tier only -- never added for a regular/lower-tier send, so
        # it always reflects a real tier decision (evaluate_auto_send_tier)
        # rather than being a cosmetic label anyone could mistake for
        # inflated confidence.
        lines.append(L["high_confidence"])
    challenge_tag = _challenge_mode_tag(position, lang)
    if challenge_tag:
        lines.append(challenge_tag)
    profitability_label = _profitability_label(position.get("strategy_id"), lang)
    if profitability_label:
        lines.append(profitability_label)
    lines += [
        f"\U0001F4CA <b>{TELEGRAM_BRAND} Signal</b>",
        "─" * 18,
        f"{_direction_emoji(position['direction'])} <b>{direction_word} {symbol}</b>",
        f"{L['strategy']}: {position.get('strategy_name') or L['unknown_strategy']}",
    ]
    if grade_result:
        lines.append(f"\U0001F3C5 {L['quality_grade']}: <b>{grade_result['grade']}</b> -- {grade_result['reason']}")
    lines += [
        "",
        f"<b>{L['levels']}</b>",
        f"{L['entry']}: {_format_price(position.get('entry_price'))}",
        f"⚠️ {L['stop_loss']}: {_format_price(position.get('stop_loss'))}",
        f"\U0001F3AF {L['take_profit']}: {_format_price(position.get('take_profit'))}",
    ]

    if live_price is _UNSET:
        live_price = _fetch_live_price(position.get("exchange"), symbol)
    if live_price is not None:
        lines.append(f"{L['current_price']}: {_format_price(live_price)}")

    lines.append("")
    # Statistical confidence (Genuine Evolution Engine's Wilson-score gate,
    # min. 25 trades for this exact strategy+coin+condition) takes
    # priority when available -- only ever states a real, recorded win
    # rate pulled from this pattern's own trade history, never a made-up
    # or implied number. Otherwise falls back to the qualitative
    # Confluence Score label, which is always safe to show (it's a count
    # of aligned factors, not a percentage claim).
    if reliability_result and reliability_result.get("reliable"):
        icon = _confidence_icon(confluence_result.get("label") if confluence_result else None)
        lines.append(
            f"{icon} {L['statistical_confidence']}: {reliability_result['win_rate_pct']:.0f}% "
            + L["win_rate_over"].format(n=reliability_result["sample_size"])
            + f" (95% CI {reliability_result['ci_lower_pct']:.0f}%-{reliability_result['ci_upper_pct']:.0f}%)"
        )
    elif confluence_result:
        icon = _confidence_icon(confluence_result.get("label"))
        lines.append(f"{icon} {L['confidence']}: {confluence_result['label']}")

    if confluence_result:
        aligned = [f["name"] for f in confluence_result.get("factors", []) if f.get("result") is True]
        if aligned:
            lines.append("")
            lines.append(f"<b>{L['why_this_trade']}</b>")
            for name in aligned:
                lines.append(f"• {name}")

    if explanation_text:
        lines.append("")
        lines.append(f"<b>{L['why_this_signal_heading']}</b>")
        lines.append(explanation_text)

    reason = _reason_text(position)
    if reason:
        lines.append("")
        lines.append(f"{L['reason']}: {reason}")

    entry_time_ms = position.get("entry_time")
    if entry_time_ms:
        ts = datetime.fromtimestamp(entry_time_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        age = _signal_age_text(entry_time_ms)
        lines.append("")
        lines.append(f"\U0001F551 {ts}" + (f" ({age})" if age else ""))

    lines.append("")
    lines.append(L["footer_brand"])
    lines.append(DISCLAIMER)
    # Task 4.3: without exception, every message from a currently
    # "Profitable" strategy ends with this extra, distinct disclaimer --
    # a real positive live track record must never read as a promise.
    if _is_profitable_label(profitability_label, lang):
        lines.append(PROFITABLE_RISK_DISCLAIMER)
    return "\n".join(lines)


def _profitability_label(strategy_id, lang):
    """Task 4.2: every signal message must say plainly whether it comes
    from a strategy with a real, positive live paper-trading record, or
    one still building that record. Uses LIVE paper-trading history
    (storage.get_paper_account_summary -- the same O(1) running total the
    rest of this file's PnL checks already use), never backtest results:
    the cloud runner's own curated Postgres schema deliberately excludes
    the backtest_* tables (see data_engine/db_backend.py), so a
    backtest-based classification would be unavailable there, and "how
    has this actually performed live" is the more honest thing to tell
    someone about a signal they're about to see anyway. "Profitable"
    requires BOTH a real sample size (the same 25-trade bar
    pattern_stats.MIN_SAMPLE_SIZE uses elsewhere in this file, so this
    isn't a second, softer threshold) and a net positive live PnL --
    anything short of that is "still under evaluation," never a guess."""
    if not strategy_id:
        return None
    summary = storage.get_paper_account_summary(strategy_id)
    L = _LABELS[lang]
    if summary["closed_count"] >= pattern_stats.MIN_SAMPLE_SIZE and summary["realized_pnl_total"] > 0:
        return L["profitable_strategy"]
    return L["strategy_under_evaluation"]


def _is_profitable_label(label, lang):
    return label == _LABELS[lang]["profitable_strategy"]


def _challenge_mode_tag(position, lang):
    """Task 4.4: labels a signal as a Challenge Mode signal when the CEO
    has scoped an active Challenge (paper_trading.challenge_mode) to this
    exact strategy+coin -- Challenge Mode itself never influences trading
    decisions (see challenge_mode.py's own module docstring), this only
    threads its existing scope choice through to the message text so a
    signal counted toward that challenge is visibly distinguishable from
    a regular one."""
    challenge = challenge_mode.load()
    if not challenge.get("enabled"):
        return None
    scope_strategy = challenge.get("scope_strategy_id")
    scope_symbol = challenge.get("scope_symbol")
    if not scope_strategy:
        return None  # system-wide challenge, not scoped to any one signal
    if position.get("strategy_id") != scope_strategy:
        return None
    if scope_symbol and position.get("symbol") != scope_symbol:
        return None
    return _LABELS[lang]["challenge_mode_tag"]


def _pattern_reliability_for(strategy_id, symbol, market_state, session):
    """The exact same statistical gate the Genuine Evolution Engine uses
    for Pattern Auto-Avoid / Lesson Auto-Apply (paper_trading.pattern_stats
    -- Wilson score interval, minimum 25 trades), reused here rather than
    inventing a new confidence threshold for Telegram. Returns
    pattern_stats.classify()'s full result dict for this EXACT
    (strategy, coin, market condition, session) combination."""
    patterns = storage.list_paper_coin_pattern_memory(strategy_id=strategy_id)
    match = next((p for p in patterns if p["symbol"] == symbol and p["market_state"] == market_state
                  and p["session"] == session), None)
    if match is None:
        return pattern_stats.classify(0, 0)
    return pattern_stats.classify(match["wins"], match["trades"])


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

    explanation_text = signal_explainer.explain_signal(conf, reliability)
    grade_result = signal_explainer.grade_signal(conf, reliability)
    text = format_signal_message(pos, conf, reliability, high_confidence=high_confidence, live_price=live_price,
                                  explanation_text=explanation_text, grade_result=grade_result)
    ok, err = _raw_send(text, channel_id_override=channel_for_strategy(pos.get("strategy_id")))
    storage.log_telegram_message(
        position_id, pos.get("strategy_id"), pos.get("strategy_name"), trigger_type, text, ok, err, now,
        explanation_text=explanation_text, quality_grade=grade_result["grade"], grade_reason=grade_result["reason"],
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

    Confidence filtering (this task): with the default
    auto_send_high_confidence_only=True, a Low-tier-only qualifying signal
    is deliberately NOT sent to Telegram -- it is still fully generated
    and stays visible everywhere the dashboard already shows signal
    activity (paper_decision_log, the Signal Tracker page, and
    /api/paper-trading/telegram/delivery-log's "never sent" bucket, which
    surfaces exactly the reason text returned here), it just never reaches
    the channel. Setting auto_send_high_confidence_only to False restores
    the previous behavior (falls back to evaluate_auto_send_low_tier) for
    anyone who deliberately wants that -- off by default, per this task's
    requirement, not a silent behavior removal.

    Returns (tier: "high" | "low" | None, reason: str)."""
    should_send_high, reason_high = evaluate_auto_send(position_id)
    if should_send_high:
        return "high", reason_high
    should_send_low, reason_low = evaluate_auto_send_low_tier(position_id)
    if not should_send_low:
        return None, reason_low
    if load_settings().get("auto_send_high_confidence_only", True):
        return None, (
            f"qualified for the Low Confidence tier but not sent -- only High Confidence "
            f"signals are sent to Telegram ({reason_low})"
        )
    return "low", reason_low


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
