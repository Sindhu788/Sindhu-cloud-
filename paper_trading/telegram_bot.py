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
import time
from datetime import datetime, timezone

import requests

from data_engine import config as base_config, storage, feature_toggles
from paper_trading import confluence as confluence_mod, insights, pattern_stats

_DEFAULTS = {
    "bot_token": "",
    "channel_id": "",
    "master_send_enabled": True,  # Telegram Dashboard's master switch -- see _master_enabled() below
    "auto_send_enabled": False,   # non-negotiable: OFF by default
    "auto_send_min_confluence_ratio": 1.0,  # require ALL counted factors aligned (e.g. 4/4) by default -- conservative
    "rate_limit_per_hour": 10,
    "send_close_followups": True,
    "proxy_enabled": False,
    "proxy_url": "",  # e.g. "socks5://user:pass@host:1080" or "http://user:pass@host:8080"
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

_API_CONNECT_TIMEOUT = 15
_API_READ_TIMEOUT = 30
_API_MAX_ATTEMPTS = 3
_API_RETRY_BACKOFF_SECONDS = 2


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_settings():
    return base_config.load_or_seed("telegram_settings.json", _DEFAULTS)


def save_settings(**fields):
    settings = load_settings()
    settings.update({k: v for k, v in fields.items() if v is not None})
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
        "rate_limit_per_hour": s.get("rate_limit_per_hour", 10),
        "send_close_followups": s.get("send_close_followups", True),
        "proxy_enabled": s.get("proxy_enabled", False),
        "proxy_configured": bool(s.get("proxy_url")),
    }


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


def _raw_send(text):
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
    not fixable by timeout/retry tuning alone)."""
    settings = load_settings()
    token, channel_id = settings.get("bot_token"), settings.get("channel_id")
    if not token or not channel_id:
        return False, "Telegram bot token or channel ID not configured yet"
    proxies = _build_proxies(settings)

    last_err = None
    for attempt in range(1, _API_MAX_ATTEMPTS + 1):
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": channel_id, "text": text, "parse_mode": "HTML"},
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


def format_signal_message(position, confluence_result=None, reliability_result=None, high_confidence=False):
    direction_word = "LONG" if position["direction"] == "long" else "SHORT"
    symbol = position["symbol"]

    lines = []
    if high_confidence:
        # Task 4 (Priority Batch 1): a distinct, unmissable marker for the
        # HIGH tier only -- never added for a regular/lower-tier send, so
        # it always reflects a real tier decision (evaluate_auto_send_tier)
        # rather than being a cosmetic label anyone could mistake for
        # inflated confidence.
        lines.append("⭐ <b>HIGH CONFIDENCE SIGNAL</b> ⭐")
    lines += [
        f"\U0001F4CA <b>{TELEGRAM_BRAND} Signal</b>",
        "─" * 18,
        f"{_direction_emoji(position['direction'])} <b>{direction_word} {symbol}</b>",
        f"Strategy: {position.get('strategy_name') or 'Unknown'}",
        "",
        "<b>LEVELS</b>",
        f"Entry: {_format_price(position.get('entry_price'))}",
        f"⚠️ Stop-Loss: {_format_price(position.get('stop_loss'))}",
        f"\U0001F3AF Take-Profit: {_format_price(position.get('take_profit'))}",
    ]

    live_price = _fetch_live_price(position.get("exchange"), symbol)
    if live_price is not None:
        lines.append(f"Current Price: {_format_price(live_price)}")

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
            f"{icon} Statistical Confidence: {reliability_result['win_rate_pct']:.0f}% win rate over "
            f"{reliability_result['sample_size']} recorded trades (95% CI "
            f"{reliability_result['ci_lower_pct']:.0f}%-{reliability_result['ci_upper_pct']:.0f}%)"
        )
    elif confluence_result:
        icon = _confidence_icon(confluence_result.get("label"))
        lines.append(f"{icon} Confidence: {confluence_result['label']}")

    if confluence_result:
        aligned = [f["name"] for f in confluence_result.get("factors", []) if f.get("result") is True]
        if aligned:
            lines.append("")
            lines.append("<b>Why This Trade</b>")
            for name in aligned:
                lines.append(f"• {name}")

    reason = _reason_text(position)
    if reason:
        lines.append("")
        lines.append(f"Reason: {reason}")

    entry_time_ms = position.get("entry_time")
    if entry_time_ms:
        ts = datetime.fromtimestamp(entry_time_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        age = _signal_age_text(entry_time_ms)
        lines.append("")
        lines.append(f"\U0001F551 {ts}" + (f" ({age})" if age else ""))

    lines.append("")
    lines.append(f"{TELEGRAM_BRAND} -- Paper Trading")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


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


def send_signal_for_position(position_id, trigger_type="manual", high_confidence=False):
    """The one real-send entry point both Manual Override (A2) and the
    automatic rule (A3) call. Rate-limited, always logged (success or
    failure) to telegram_message_log -- a full audit trail, per A4.

    high_confidence (Task 4, Priority Batch 1): only ever set True by the
    automatic sender, and only when evaluate_auto_send_tier() genuinely
    returned "high" for THIS position -- adds the distinct High Confidence
    marker to the message. Manual sends never pass this (defaults False),
    so a CEO-triggered send is never mislabeled as an automatic
    high-confidence call."""
    pos = storage.get_paper_position(position_id)
    now = _now_iso()
    if not pos:
        storage.log_telegram_message(position_id, None, None, trigger_type, "", False, "position not found", now)
        return {"ok": False, "error": "position not found"}

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

    text = format_signal_message(pos, conf, reliability, high_confidence=high_confidence)
    ok, err = _raw_send(text)
    storage.log_telegram_message(
        position_id, pos.get("strategy_id"), pos.get("strategy_name"), trigger_type, text, ok, err, now,
    )
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
    """Tries the HIGH tier first (evaluate_auto_send -- unchanged, real
    confluence + the real 25-trade Wilson gate), falls back to the LOW
    tier (evaluate_auto_send_low_tier) only if High doesn't qualify, so
    signal flow never stops just because nothing currently clears the
    high bar. Returns (tier: "high" | "low" | None, reason: str)."""
    should_send_high, reason_high = evaluate_auto_send(position_id)
    if should_send_high:
        return "high", reason_high
    should_send_low, reason_low = evaluate_auto_send_low_tier(position_id)
    if should_send_low:
        return "low", reason_low
    return None, reason_low


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

    pnl = closed_position.get("pnl") or 0.0
    outcome = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BREAK-EVEN"
    text = (
        f"<b>{TELEGRAM_BRAND} Result -- {outcome}</b>\n"
        f"Strategy: {closed_position.get('strategy_name') or 'Unknown'}\n"
        f"Coin: {closed_position['symbol']}\n"
        f"Exit: {closed_position.get('exit_price', '-')} ({closed_position.get('exit_reason', '-')})\n"
        f"Result: {'+' if pnl >= 0 else ''}{pnl:.2f} ({closed_position.get('pnl_pct', 0):.2f}%)\n\n"
        f"{DISCLAIMER}"
    )
    ok, err = _raw_send(text)
    storage.log_telegram_message(
        position_id, closed_position.get("strategy_id"), closed_position.get("strategy_name"),
        "close_followup", text, ok, err, _now_iso(),
    )
    return {"ok": ok, "error": err}


# --------------------------------------------------------------- Task 3 (Batch 2): no-signal alert

NO_SIGNAL_ALERT_HOURS = 24


def no_signal_alert_status(now_iso=None):
    """Dashboard alert (Overview + Telegram Signals page) for an extended
    signal drought -- 24+ hours with zero signals sent to Telegram, any
    tier. Nothing to separately "clear": this is computed fresh from the
    real last-sent timestamp on every call, so it automatically stops
    firing the instant a new signal actually sends -- there's no separate
    stored "alert active" flag that could go stale or need resetting.

    now_iso: injectable for tests; defaults to the real current time.

    Returns {"stale": bool, "last_sent_at": iso|None, "hours_since": float|None,
             "message": str|None} -- message is a plain, non-technical
    sentence when stale, else None."""
    now = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
    last_sent_iso = storage.get_last_telegram_signal_sent_at()

    if last_sent_iso is None:
        return {
            "stale": True, "last_sent_at": None, "hours_since": None,
            "message": "No signals have been sent to Telegram yet.",
        }

    last_sent = datetime.fromisoformat(last_sent_iso)
    if last_sent.tzinfo is None:
        last_sent = last_sent.replace(tzinfo=timezone.utc)
    hours_since = (now - last_sent).total_seconds() / 3600.0
    stale = hours_since >= NO_SIGNAL_ALERT_HOURS
    return {
        "stale": stale, "last_sent_at": last_sent_iso, "hours_since": round(hours_since, 1),
        "message": (
            f"No signals have been sent to Telegram in the last {int(hours_since)} hours."
            if stale else None
        ),
    }
